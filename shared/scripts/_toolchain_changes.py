"""Language-neutral staged project changes, durable journals and fresh evidence.

Architecture files remain authoritative. This layer stores operation intentions
and snapshots, never a second editable project model. Files are byte-preserved.
"""
from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import _archlib
from _toolchain_store import (Store, ToolchainError, encoded, file_state, now,
                              replace_file, safe_path, source_path, uid)

ACTIVE_WRITES = {"prepared", "applying", "recovery_required"}
FINAL = {"accepted", "aborted", "rolled_back"}
IGNORE = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"}


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ToolchainError(f"{label} 必须为非空字符串")
    return value


def _files(project: Path) -> list[str]:
    """Conservative selected verification inputs, with explicit exclusions."""
    result = []
    for directory, dirs, files in os.walk(project, followlinks=False):
        parent = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in IGNORE and
                         not (parent / d).is_symlink() and
                         not getattr(parent / d, "is_junction", lambda: False)() and
                         (parent / d).relative_to(project).as_posix().casefold() != "architecture/toolchain")
        for name in sorted(files):
            path = parent / name
            rel = path.relative_to(project).as_posix()
            source_path(project, rel)
            result.append(rel)
    return result


def fingerprints(project: Path, paths: list[str]) -> dict:
    return {rel: file_state(project, rel) for rel in sorted(set(paths))}


def _check_inputs(project: Path, expected: dict, *, inventory: bool = False):
    paths = set(expected)
    if inventory:
        paths.update(_files(project))
    current = fingerprints(project, list(paths))
    changed = [rel for rel in sorted(paths) if expected.get(rel, {"exists": False, "sha256": None, "size": 0}) != current[rel]]
    if changed:
        raise ToolchainError("工作依据已变化，请重新建立或协调变更: " + ", ".join(changed), "fail")


def _branch(store: Store, conn=None):
    return sorted([[x["id"], x["revision"]] for x in store.list("branch", conn)])


def _document(store: Store, identifier: str, actor=None, conn=None) -> dict:
    value = store.get("change", _text(identifier, "change ID"), conn)
    if value is None:
        raise ToolchainError("变更不存在: " + identifier)
    if actor is not None and value["actor"] != _text(actor, "actor"):
        raise ToolchainError("变更属于其他执行者", "fail")
    return value


def _request(store: Store, action: str, payload: dict, conn):
    request = _text(payload.get("request_id"), "request_id")
    key = action + ":" + request
    digest = hashlib.sha256(encoded(payload)).hexdigest()
    old = store.get("request", key, conn)
    if old and old["digest"] != digest:
        raise ToolchainError("相同 request_id 的输入发生变化", "fail")
    return key, digest, copy.deepcopy(old["result"]) if old else None


def _save_request(store, key, digest, result, conn):
    store.put("request", key, {"id": key, "digest": digest, "result": result}, 0, conn)


def _record(store, document, operation, details, conn):
    document["updated_at"] = now()
    result = store.put("change", document["id"], document, document.get("revision", 0), conn)
    store.event(operation, document["id"], details, document["actor"], conn)
    return result


def _index(project, architecture):
    from _toolchain_query import build_index
    return build_index(project, architecture)


def _scope(index, scope, known_extra=()):
    if not isinstance(scope, list) or not scope or any(not isinstance(x, str) or not x for x in scope):
        raise ToolchainError("scope 必须为非空模块编号数组")
    known = {x["key"] for x in index["objects"] if x["kind"] == "module"} | set(known_extra)
    if len(set(scope)) != len(scope) or set(scope) - known:
        raise ToolchainError("scope 包含重复或未登记模块")
    return list(scope)


def begin(project: Path, architecture: str, payload: dict) -> dict:
    prior = Store(project).get("request", "change.begin:" + _text(payload.get("request_id"), "request_id"))
    if prior is not None:
        if prior["digest"] != hashlib.sha256(encoded(payload)).hexdigest():
            raise ToolchainError("相同 request_id 的输入发生变化", "fail")
        return copy.deepcopy(prior["result"])
    actor, goal = _text(payload.get("actor"), "actor"), _text(payload.get("goal"), "goal")
    index = _index(project, architecture)
    scope = _scope(index, payload.get("scope", payload.get("modules")))
    from _toolchain_query import read_object
    targets = payload.get("targets", ["module:" + quote(m, safe="") for m in scope])
    if not isinstance(targets, list) or not targets:
        raise ToolchainError("targets 必须是非空对象编号数组")
    target_objects = [read_object(index, selector) for selector in targets]
    paths = _files(project)
    extra = payload.get("read_files", [])
    if not isinstance(extra, list):
        raise ToolchainError("read_files 必须为路径数组")
    paths = sorted(set(paths + [source_path(project, rel).relative_to(project).as_posix() for rel in extra]))
    store = Store(project, create=True)
    with store.transaction() as tx:
        key, digest, old = _request(store, "change.begin", payload, tx)
        if old is not None:
            return old
        snapshots = store.capture(paths)
        if any(snapshots.get(rel, {}).get("sha256") != sha for rel, sha in index["input_hashes"].items()):
            raise ToolchainError("建立变更时架构发生变化", "fail")
        identifier = uid("change")
        document = {"id": identifier, "actor": actor, "goal": goal, "architecture": architecture,
                    "scope": scope, "status": "draft", "created_at": now(), "operations": [],
                    "base": snapshots, "architecture_inputs": index["input_hashes"],
                    "participants": {}, "unresolved": [], "branch": _branch(store, tx),
                    "targets": [obj["id"] for obj in target_objects],
                    "target_locations": {obj["id"]: obj["locations"] for obj in target_objects},
                    "input_scope": {"mode": "project regular files", "excluded_directories": sorted(IGNORE),
                                    "excluded_state": "architecture/toolchain/"},
                    "limitations": ["快照不隔离外部编辑器；所有写入仅对遵循协议的客户端协调"]}
        result = _record(store, document, "change.begun", {"goal": goal, "scope": scope, "inputs": snapshots}, tx)
        _save_request(store, key, digest, result, tx)
    return result


def _pointer(document, pointer, value=None, remove=False):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ToolchainError("字段操作需要非根 JSON Pointer")
    parts = pointer[1:].split("/")
    decoded = []
    for part in parts:
        if any(part[i:i+2] not in ("~0", "~1") for i, c in enumerate(part) if c == "~"):
            raise ToolchainError("JSON Pointer 转义无效")
        decoded.append(part.replace("~1", "/").replace("~0", "~"))
    if decoded[0] in ("模块目录", "模块归属事实"):
        raise ToolchainError("禁止写入合成派生字段")
    cursor = document
    for key in decoded[:-1]:
        try:
            cursor = cursor[int(key)] if isinstance(cursor, list) else cursor[key]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ToolchainError("JSON Pointer 父级不存在") from exc
    key = decoded[-1]
    if isinstance(cursor, dict):
        if remove:
            if key not in cursor:
                raise ToolchainError("删除字段不存在")
            del cursor[key]
        else:
            cursor[key] = copy.deepcopy(value)
    elif isinstance(cursor, list):
        if key == "-" and not remove:
            cursor.append(copy.deepcopy(value))
        else:
            if not key.isdigit() or (len(key) > 1 and key.startswith("0")):
                raise ToolchainError("数组 Pointer 下标无效")
            position = int(key)
            if position >= len(cursor):
                raise ToolchainError("数组 Pointer 下标越界")
            if remove:
                del cursor[position]
            else:
                cursor[position] = copy.deepcopy(value)
    else:
        raise ToolchainError("JSON Pointer 父级不是容器")


def _bytes(op):
    if "base64" in op and "text" in op or "base64" not in op and "text" not in op:
        raise ToolchainError("write 需要且只能提供 text 或 base64")
    if "text" in op:
        if not isinstance(op["text"], str):
            raise ToolchainError("text 必须为字符串")
        return op["text"].encode("utf-8")
    try:
        return base64.b64decode(op["base64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ToolchainError("base64 无效") from exc


def _materialize(project, document, store, destination):
    for rel, state in document["base"].items():
        if state["exists"]:
            target = source_path(destination, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(store.blob(state["sha256"]))
    architecture_files = set(document["architecture_inputs"])
    migration_notes = []
    for operation in document["operations"]:
        kind = operation.get("type")
        if kind == "module.create":
            import module_architecture
            module_architecture.add(destination / document["architecture"], operation.get("parent"),
                       operation.get("directory"), operation.get("module"), operation.get("name"),
                       operation.get("responsibility"), destination)
            architecture_files = set(_index(destination, document["architecture"])["input_hashes"])
            continue
        if kind == "module.move":
            architecture_files, notes = _move(destination, document["architecture"], operation,
                                             document["scope"], architecture_files)
            migration_notes.extend(notes)
            continue
        rel = source_path(destination, operation.get("file")).relative_to(destination).as_posix()
        target = source_path(destination, rel)
        if kind in ("set", "remove"):
            if kind == "set" and "value" not in operation:
                raise ToolchainError("set 必须提供 value；显式 null 可用")
            if rel not in architecture_files:
                raise ToolchainError("结构化编辑必须指向已登记的物理权威架构文件")
            data = _archlib.load_json_utf8(target)
            if not isinstance(data, dict):
                raise ToolchainError("权威架构必须为对象")
            _pointer(data, operation.get("pointer"), operation.get("value"), kind == "remove")
            target.write_bytes(encoded_pretty(data))
        elif kind == "write":
            if rel in architecture_files or target.name == "architecture.json":
                raise ToolchainError("架构必须用字段操作或 module.create 创建")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_bytes(operation))
        elif kind == "delete":
            if rel in architecture_files:
                raise ToolchainError("不得用源文件删除操作删除权威架构")
            if not target.is_file():
                raise ToolchainError("要删除的文件不存在")
            target.unlink()
        else:
            raise ToolchainError("未知暂存操作: " + str(kind))
    return {"architecture_files": architecture_files, "migration_notes": migration_notes}


def encoded_pretty(value):
    import json
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _move(root, architecture, operation, scope, architecture_files):
    import module_architecture
    tree, _ = module_architecture.load_tree(root / architecture, root)
    identifier = operation.get("module")
    if identifier not in tree.documents or tree.record(identifier)["父模块"] is None:
        raise ToolchainError("只能移动已登记的非根模块")
    old_parent = tree.record(identifier)["父模块"]
    new_parent = operation.get("parent", old_parent)
    if new_parent not in tree.documents:
        raise ToolchainError("新父模块不存在")
    subtree = {r["编号"] for r in tree.records if identifier in [a["编号"] for a in tree.chain(r["编号"]) ]}
    if new_parent in subtree:
        raise ToolchainError("不能将模块移动到自身或后代")
    if not {old_parent, new_parent}.issubset(scope) or not subtree.issubset(scope):
        raise ToolchainError("移动需要显式包含原父、新父与所有子树模块的 scope", "fail")
    old_dir = root / tree.record(identifier)["目录"]
    new_dir = source_path(root, operation.get("to_directory"))
    parent_dir = root / tree.record(new_parent)["目录"]
    try:
        remainder = new_dir.relative_to(parent_dir)
        new_dir.relative_to(old_dir)
        inside_old = True
    except ValueError:
        inside_old = False
        try:
            remainder = new_dir.relative_to(parent_dir)
        except ValueError as exc:
            raise ToolchainError("新目录必须在新父模块实际目录内") from exc
    if not remainder.parts or inside_old or new_dir.exists():
        raise ToolchainError("目标目录不可用或与原目录重叠", "fail")
    for record in tree.records:
        if record["编号"] not in subtree and record["编号"] != new_parent:
            directory = root / record["目录"]
            if directory in new_dir.parents and record["编号"] not in [a["编号"] for a in tree.chain(new_parent)]:
                raise ToolchainError("目标属于另一个模块", "fail")
    mapping = {}
    for path in old_dir.rglob("*"):
        if path.is_symlink():
            raise ToolchainError("移动模块含链接，拒绝推测迁移")
        if path.is_file():
            mapping[path.relative_to(root).as_posix()] = (new_dir / path.relative_to(old_dir)).relative_to(root).as_posix()
    path_by_id = {mid: mapping.get(p.relative_to(root).as_posix(), p.relative_to(root).as_posix()) for mid, p in tree.paths.items()}
    migration_notes = []
    typed_containers = {"实现清单", "架构落位", "落位", "测试责任矩阵", "接口契约", "文件引用"}
    path_keys = {"文件列表", "文件", "入口文件", "路径", "源码路径", "源码文件", "对应代码文件",
                 "测试", "测试文件", "单元测试", "集成测试", "回归测试", "端到端测试", "验证文件"}
    def rewrite(value, path=(), typed=False, path_value=False):
        if isinstance(value, str):
            physical, separator, suffix = value.partition("::")
            if physical in mapping:
                if path_value:
                    return mapping[physical] + (separator + suffix if separator else "")
                migration_notes.append({"code": "preserved_untyped_path_literal", "pointer": "/" + "/".join(map(str, path)),
                    "value": value, "message": "未声明为路径的值保持原样；由 AI 判断是否确需迁移"})
            return value
        if isinstance(value, list):
            return [rewrite(x, path + (i,), typed, path_value) for i, x in enumerate(value)]
        if isinstance(value, dict):
            return {k: rewrite(v, path + (k,), typed or k in typed_containers,
                               (typed or k in typed_containers) and k in path_keys) for k, v in value.items()}
        return value
    documents = {mid: rewrite(data) for mid, data in tree.documents.items()}
    # Explicit module trees are authoritative declarations as well as routes.
    # Reparent their node, retaining all original attributes and descendants.
    # A module's own local tree remains rooted at that module; its explicit
    # parent field still follows the new physical parent. Partial forests that
    # omit the new parent use a top-level node with an explicit parent ID rather
    # than inventing missing ancestor nodes or leaving the old containment edge.
    def tree_entries(forest):
        pending = [(forest, None)]
        result = []
        while pending:
            siblings, parent = pending.pop()
            if not isinstance(siblings, list):
                continue
            for node in siblings:
                if not isinstance(node, dict):
                    continue
                result.append((node, siblings, parent))
                pending.append((node.get("子模块", []), node.get("编号")))
        return result
    declared_nodes = [node for data in documents.values()
                      for node, _, _ in tree_entries(data.get("模块树", []))
                      if node.get("编号") == identifier]
    if old_parent != new_parent and declared_nodes:
        moved_node = copy.deepcopy(declared_nodes[0])
        for node in declared_nodes[1:]:
            moved_node = _archlib._merge_slice_value(moved_node, node, "模块树." + identifier)
        moved_node["父模块"] = new_parent
        for mid, data in documents.items():
            forest = data.get("模块树")
            if not isinstance(forest, list):
                continue
            entries = tree_entries(forest)
            targets = [node for node, _, _ in entries if node.get("编号") == new_parent]
            for node, siblings, parent in entries:
                if node.get("编号") != identifier:
                    continue
                node["父模块"] = new_parent
                local_root = mid == identifier and siblings is forest
                if local_root or parent == new_parent:
                    continue
                if targets:
                    siblings.remove(node)
                elif parent is not None:
                    siblings.remove(node)
                    forest.append(node)
            for target in targets:
                children = target.setdefault("子模块", [])
                if not isinstance(children, list):
                    raise ToolchainError("模块树子模块必须为数组，不能安全重挂接")
                if not any(isinstance(node, dict) and node.get("编号") == identifier for node in children):
                    children.append(copy.deepcopy(moved_node))
    for mid, data in documents.items():
        children = data["模块路由"]["子模块"]
        if mid == old_parent:
            children[:] = [c for c in children if c["编号"] != identifier]
        if mid == new_parent:
            children.append({"编号": identifier, "路径": "", "职责": documents[identifier]["模块路由"]["职责"]})
        for child in children:
            child["路径"] = (root / path_by_id[child["编号"]]).relative_to((root / path_by_id[mid]).parent).as_posix()
        if data != tree.documents[mid] and mid not in scope:
            raise ToolchainError("迁移需更新其他模块引用，请扩展 scope: " + mid, "fail")
    new_dir.parent.mkdir(parents=True, exist_ok=True)
    os.rename(old_dir, new_dir)
    for mid, data in documents.items():
        (root / path_by_id[mid]).write_bytes(encoded_pretty(data))
    return {mapping.get(rel, rel) for rel in architecture_files}, migration_notes


def _validate_scope(before_index, after_index, document, changed, arch_before, arch_after):
    scope = set(document["scope"])
    def owner(index, rel):
        physical = {loc["file"]: obj["key"] for obj in index["objects"] if obj["kind"] == "module"
                    for loc in obj["locations"] if loc["pointer"] == "/模块路由"}
        if rel in physical:
            return {physical[rel]}
        declared = {f.get("physical_owner") or f["module"] for f in index.get("files", [])
                    if f["path"] == rel and (f.get("ownership") is True or
                    any(loc["pointer"].startswith("/实现清单/") for loc in f["locations"]))}
        if rel in index["input_hashes"]:
            # Central slices may declare several modules; each remains explicit.
            declared.update(obj["module"] or obj["key"] for obj in index["objects"]
                            if obj["kind"] == "module" and any(loc["file"] == rel for loc in obj["locations"]))
        return declared
    def pointer_owners(index, rel, pointer):
        candidates = []
        for obj in index["objects"]:
            for loc in obj["locations"]:
                if loc["file"] != rel:
                    continue
                location = loc["pointer"]
                if pointer == location or pointer.startswith(location + "/"):
                    module = obj["key"] if obj["kind"] == "module" else obj.get("module")
                    if module:
                        candidates.append((len(location), module))
                elif location.startswith(pointer + "/"):
                    module = obj["key"] if obj["kind"] == "module" else obj.get("module")
                    if module:
                        candidates.append((len(pointer), module))
        if candidates:
            depth = max(item[0] for item in candidates)
            return {module for length, module in candidates if length == depth}
        # Global or unassigned facts require explicit project-wide coordination.
        return owner(index, rel)
    for rel in changed:
        owners = owner(before_index, rel) | owner(after_index, rel)
        field_ops = [op for op in document["operations"] if op.get("file") == rel and op.get("type") in ("set", "remove")]
        recursive_owner = any(loc["file"] == rel and loc["pointer"] == "/模块路由"
                              for obj in before_index["objects"] if obj["kind"] == "module" for loc in obj["locations"])
        if rel in arch_before | arch_after and field_ops and not recursive_owner:
            owners = set()
            for operation in field_ops:
                owners.update(pointer_owners(before_index, rel, operation["pointer"]))
                owners.update(pointer_owners(after_index, rel, operation["pointer"]))
        if not owners or not owners.issubset(scope):
            raise ToolchainError("文件未登记或超出明确模块范围: " + rel + " owners=" + str(sorted(owners)), "fail")
        if rel not in arch_before | arch_after and after_index and rel in {f["path"] for f in after_index.get("files", [])}:
            continue
        if rel not in arch_before | arch_after and file_state(Path(after_index["project"]), rel)["exists"]:
            raise ToolchainError("新增或保留源码必须在暂存架构登记: " + rel, "fail")


def _preview(project, document, store, *, cache=False):
    with tempfile.TemporaryDirectory(prefix="taskarch-preview-") as directory:
        root = Path(directory).resolve()
        # frozen baseline first: subsequent operations must not read a newer project
        empty = dict(document, operations=[])
        _materialize(project, empty, store, root)
        before_index = _index(root, document["architecture"])
        arch_before = set(before_index["input_hashes"])
        materialized = _materialize(project, document, store, root)
        after_index = _index(root, document["architecture"])
        arch_after = set(after_index["input_hashes"])
        paths = set(document["base"]) | set(_files(root))
        images = {}
        diffs = []
        for rel in sorted(paths):
            before = document["base"].get(rel, {"exists": False, "sha256": None, "size": 0})
            after = file_state(root, rel)
            if before == after:
                continue
            raw = (root / rel).read_bytes() if after["exists"] else None
            if raw is not None and cache:
                after["sha256"] = store._put_blob(raw)
            images[rel] = {"before": before, "after": after}
            diff = {"file": rel, "before": before, "after": after,
                    "category": "architecture" if rel in arch_before | arch_after else "implementation"}
            old_raw = store.blob(before["sha256"]) if before["exists"] else b""
            try:
                diff["diff"] = "".join(difflib.unified_diff(old_raw.decode("utf-8-sig").splitlines(True),
                                       (raw or b"").decode("utf-8-sig").splitlines(True), fromfile="before/"+rel, tofile="after/"+rel))
            except UnicodeError:
                diff["diff"] = None
                diff["binary"] = True
            diffs.append(diff)
        _validate_scope(before_index, after_index, document, images, arch_before, arch_after)
        import module_architecture
        from _module_tree import ROUTE_FIELD
        merged = _archlib.load_architecture_json(root / document["architecture"], project_root=root)
        if ROUTE_FIELD in merged:
            tree, sources = module_architecture.load_tree(root / document["architecture"], root)
            structure = module_architecture.check(tree, sources)
        else:
            structure = {"status": "pass", "scope": "central-input-load", "errors": [],
                         "说明": "集中模式物理加载和合并有效，完整设计和质量由 verify 判定"}
        if structure["status"] != "pass":
            raise ToolchainError("暂存架构结构校验失败: " + str(structure["errors"]), "fail")
        impacts = []
        if ROUTE_FIELD in merged:
            impacts = [module_architecture.impact(tree, module_id=mid, direction="both") for mid in document["scope"] if mid in tree.documents]
        return {"change": document["id"], "status": "pass", "scope": document["scope"], "changes": diffs,
                "images": images, "structure": structure, "impact": impacts,
                "diagnostics": after_index["diagnostics"] + materialized["migration_notes"], "architecture_files": sorted(arch_before | arch_after),
                "limitations": ["预览仅验证结构与登记；业务设计、实现正确性和质量需真实验证", "迁移精确路径引用，不推测源码或自然语言中的动态路径"]}


def stage(project, payload):
    store = Store(project, create=True)
    with store.transaction() as tx:
        key, digest, old = _request(store, "change.stage", payload, tx)
        if old is not None:
            return old
        document = _document(store, payload.get("id"), payload.get("actor"), tx)
        if document["status"] != "draft":
            raise ToolchainError("只有 draft 变更可以暂存", "fail")
        operations = payload.get("operations")
        if not isinstance(operations, list) or not operations or any(not isinstance(op, dict) for op in operations):
            raise ToolchainError("operations 必须为非空对象数组")
        document["operations"].extend(copy.deepcopy(operations))
        for operation in operations:
            if operation.get("type") == "module.create":
                if operation.get("parent") not in document["scope"]:
                    raise ToolchainError("创建子模块需要父模块在明确 scope 中", "fail")
                new_id = _text(operation.get("module"), "module")
                if new_id not in document["scope"]:
                    document["scope"].append(new_id)
        preview = _preview(project, document, store, cache=True)
        result = _record(store, document, "change.staged", {"operations": operations, "files": [d["file"] for d in preview["changes"]]}, tx)
        _save_request(store, key, digest, result, tx)
    return result


def preview(project, identifier):
    store = Store(project)  # no read-side state creation
    document = _document(store, identifier)
    result = _preview(project, document, store)
    current = fingerprints(project, sorted(set(document["base"]) | set(_files(project))))
    result["current_inputs_match"] = current == document["base"]
    result["current_inputs"] = current
    result["changed_inputs"] = [rel for rel in current if document["base"].get(rel, {"exists": False, "sha256": None, "size": 0}) != current[rel]]
    return result


def coordinate(project, payload):
    store = Store(project, create=True)
    action = payload.get("action", "participant")
    with store.transaction() as tx:
        key, digest, old = _request(store, "change.coordinate", payload, tx)
        if old is not None:
            return old
        document = _document(store, payload.get("id"), conn=tx)
        actor = _text(payload.get("actor"), "actor")
        if document["status"] in FINAL | ACTIVE_WRITES:
            raise ToolchainError("此状态不可协调", "fail")
        if action == "expand":
            if actor != document["actor"] or document["status"] != "draft":
                raise ToolchainError("只有变更发起者可在 draft 扩展范围", "fail")
            expanded = _scope(_index(project, document["architecture"]), payload.get("scope"), document["scope"])
            if not set(document["scope"]).issubset(expanded):
                raise ToolchainError("expand 必须保留原有范围；不得静默移除模块责任", "fail")
            document["scope"] = expanded
            _check_inputs(project, document["base"], inventory=True)
        elif action == "refresh":
            if actor != document["actor"] or document["status"] != "draft":
                raise ToolchainError("只有发起者可在 draft 重新确认依据", "fail")
            current = fingerprints(project, sorted(set(document["base"]) | set(_files(project))))
            if not isinstance(payload.get("expected_current"), dict) or payload["expected_current"] != current:
                raise ToolchainError("refresh 需要先查看并提供完整当前输入摘要", "fail")
            previous_preview = _preview(project, document, store)
            for rel, image in previous_preview["images"].items():
                if file_state(project, rel) != image["before"]:
                    raise ToolchainError("变更自身将写入的文件已有变化，需明确重新设计: " + rel, "fail")
            fresh_index = _index(project, document["architecture"])
            document["base"] = store.capture(sorted(current))
            document["architecture_inputs"] = fresh_index["input_hashes"]
            document["branch"] = _branch(store, tx)
            document["participants"] = {}
            _preview(project, document, store, cache=True)
        elif action == "unresolved":
            if actor != document["actor"] or not isinstance(payload.get("items"), list):
                raise ToolchainError("未决事项需要发起者及 items 数组")
            document["unresolved"] = copy.deepcopy(payload["items"])
        elif action == "participant":
            module = payload.get("module")
            status = payload.get("status")
            if module not in document["scope"] or status not in ("pending", "ready", "blocked"):
                raise ToolchainError("参与者需要 scope 中 module 及 pending/ready/blocked 状态")
            existing = document["participants"].get(module)
            if existing and existing["actor"] != actor:
                raise ToolchainError("模块参与者不同，需要原参与者先释放或协调", "fail")
            document["participants"][module] = {"actor": actor, "status": status,
                "inputs": fingerprints(project, sorted(set(_files(project)) | set(document["base"]) | set(document.get("journal", {}).get("images", {})))), "branch": _branch(store, tx),
                "operations_sha256": hashlib.sha256(encoded(document["operations"])).hexdigest(),
                "note": payload.get("note", ""), "at": now()}
        else:
            raise ToolchainError("未知协调操作")
        result = _record(store, document, "change.coordinated", {"action": action, "actor": actor, "participants": document["participants"], "unresolved": document["unresolved"]}, tx)
        _save_request(store, key, digest, result, tx)
    return result


def _no_writers(store, tx, own=None):
    for document in store.list("change", tx):
        if document["id"] != own and document["status"] in ACTIVE_WRITES:
            raise ToolchainError("有尚未完成或恢复的变更: " + document["id"], "fail")
    for journal in store.list("checkpoint-restore", tx):
        if journal.get("status") in {"prepared", "restoring", "recovery_required"}:
            raise ToolchainError("有尚未完成或恢复的检查点恢复", "fail")


def _postimages(project, images):
    return all(file_state(project, rel) == image["after"] for rel, image in images.items())


def apply(project, payload):
    from _toolchain_runtime import lease_conflicts
    store = Store(project, create=True)
    with store.transaction() as tx:
        key, digest, old = _request(store, "change.apply", payload, tx)
        if old is not None:
            return old
        document = _document(store, payload.get("id"), payload.get("actor"), tx)
        if document["status"] != "draft" or not document["operations"]:
            raise ToolchainError("应用需要含暂存操作的 draft 变更", "fail")
        _no_writers(store, tx, document["id"])
        existing_scope = [m for m in document["scope"] if m in {o["key"] for o in _index(project, document["architecture"])["objects"] if o["kind"] == "module"}]
        if lease_conflicts(store, existing_scope, actor=document["actor"], conn=tx, architecture=document["architecture"]):
            raise ToolchainError("其他执行者占用本次模块范围", "fail")
        _check_inputs(project, document["base"], inventory=True)
        result = _preview(project, document, store, cache=True)
        if not result["images"]:
            raise ToolchainError("暂存没有实际文件变化", "fail")
        document["journal"] = {"images": result["images"], "architecture_files": result["architecture_files"], "written": []}
        document["apply_request"] = {"key": key, "digest": digest}
        document["status"] = "prepared"
        document = _record(store, document, "change.prepared", document["journal"], tx)
    # Journal committed before the first project byte is changed.
    try:
        for rel in sorted(result["images"], key=lambda r: (r not in result["architecture_files"], r)):
            image = result["images"][rel]
            raw = store.blob(image["after"]["sha256"]) if image["after"]["exists"] else None
            replace_file(project, rel, raw, image["before"])
            with store.transaction() as tx:
                document = _document(store, document["id"], document["actor"], tx)
                document["status"] = "applying"
                document["journal"]["written"].append(rel)
                document = _record(store, document, "change.file_applied", {"file": rel, **image}, tx)
        with store.transaction() as tx:
            document = _document(store, document["id"], document["actor"], tx)
            document["status"] = "applied"
            document["applied_inputs"] = fingerprints(project, _files(project))
            document = _record(store, document, "change.applied", {"inputs": document["applied_inputs"]}, tx)
            _save_request(store, key, digest, document, tx)
        return document
    except BaseException as exc:
        with store.transaction() as tx:
            document = _document(store, document["id"], document["actor"], tx)
            document["status"] = "recovery_required"
            document["error"] = str(exc)
            _record(store, document, "change.apply_interrupted", {"error": str(exc)}, tx)
        # Process interruption leaves a journal; ordinary errors attempt guarded recovery.
        if isinstance(exc, Exception):
            try:
                recover(project, {"id": document["id"], "actor": document["actor"]})
            except Exception:
                pass
        raise


def _rollback(project, document, store):
    images = document.get("journal", {}).get("images", {})
    for rel, image in images.items():
        current = file_state(project, rel)
        if current not in (image["before"], image["after"]):
            raise ToolchainError("恢复发现第三方修改，保持现场: " + rel, "fail")
        if image["before"]["exists"]:
            store.blob(image["before"]["sha256"])
    # Validate all preconditions and blobs before first rollback write.
    for rel, image in reversed(list(images.items())):
        current = file_state(project, rel)
        if current != image["before"]:
            raw = store.blob(image["before"]["sha256"]) if image["before"]["exists"] else None
            replace_file(project, rel, raw, image["after"])


def recover(project, payload):
    store = Store(project, create=True)
    with store.transaction() as tx:
        document = _document(store, payload.get("id"), payload.get("actor"), tx)
        if document["status"] not in ACTIVE_WRITES:
            raise ToolchainError("只恢复中断的变更", "fail")
        _no_writers(store, tx, document["id"])
        _rollback(project, document, store)
        document["status"] = "rolled_back"
        return _record(store, document, "change.recovered", {"result": "guarded rollback", "error": document.get("error")}, tx)


def abort(project, payload):
    store = Store(project, create=True)
    with store.transaction() as tx:
        key, digest, old = _request(store, "change.abort", payload, tx)
        if old is not None:
            return old
        document = _document(store, payload.get("id"), payload.get("actor"), tx)
        if document["status"] not in ("draft", "applied", "verified"):
            raise ToolchainError("变更不能在当前状态撤回", "fail")
        _no_writers(store, tx, document["id"])
        if document["status"] != "draft":
            if not _postimages(project, document["journal"]["images"]):
                raise ToolchainError("应用后内容已变化，不能撤回覆盖", "fail")
            document["status"] = "prepared"
            document["rollback_intent"] = "abort"
            document = _record(store, document, "change.abort_prepared", {"journal": document["journal"]}, tx)
        else:
            document["status"] = "aborted"
            result = _record(store, document, "change.aborted", {"reason": payload.get("reason", "")}, tx)
            _save_request(store, key, digest, result, tx)
            return result
    try:
        # The rollback intent is durable before changing any project bytes.
        _rollback(project, document, store)
    except BaseException as exc:
        with store.transaction() as tx:
            document = _document(store, document["id"], document["actor"], tx)
            document["status"] = "recovery_required"
            document["error"] = str(exc)
            _record(store, document, "change.abort_interrupted", {"error": str(exc)}, tx)
        raise
    with store.transaction() as tx:
        document = _document(store, document["id"], document["actor"], tx)
        document["status"] = "aborted"
        result = _record(store, document, "change.aborted", {"reason": payload.get("reason", "")}, tx)
        _save_request(store, key, digest, result, tx)
        return result


def verify(project, payload):
    import gate_check
    store = Store(project, create=True)
    with store.transaction() as tx:
        key, digest, old = _request(store, "change.verify", payload, tx)
        if old is not None:
            return old
        document = _document(store, payload.get("id"), payload.get("actor"), tx)
        if document["status"] not in ("applied", "verified"):
            raise ToolchainError("只有已应用变更可验证", "fail")
        _no_writers(store, tx)
        if not _postimages(project, document["journal"]["images"]):
            raise ToolchainError("应用内容已被外部修改，请新建变更", "fail")
        paths = sorted(set(_files(project)) | set(document["base"]) | set(document.get("journal", {}).get("images", {})))
        inputs = store.capture(paths)
        branch = _branch(store, tx)
    passed, lines, stages = gate_check.run_gate(project, document["architecture"], quality_required=True,
                                                facts=payload.get("facts"), policy=payload.get("policy"))
    status = "pass" if passed is True else "fail" if passed is False else "unknown"
    gate = gate_check.build_envelope(status, {"pass": 0, "fail": 1, "unknown": 2}[status], lines, stages)
    from _toolchain_query import read_object
    current_index = _index(project, document["architecture"])
    bindings = {selector: read_object(current_index, selector)["locations"] for selector in document.get("targets", [])}
    with store.transaction() as tx:
        latest = _document(store, document["id"], document["actor"], tx)
        if latest["revision"] != document["revision"]:
            raise ToolchainError("验证过程中变更记录发生变化，结果不能接受", "fail")
        fresh = fingerprints(project, sorted(set(inputs) | set(_files(project)))) == inputs and _branch(store, tx) == branch
        receipt = {"id": uid("verification"), "change": document["id"], "created_at": now(),
                   "status": status if fresh else "unknown", "fresh": fresh, "inputs": inputs,
                   "branch": branch, "gate": gate, "operations_sha256": hashlib.sha256(encoded(document["operations"])).hexdigest(),
                   "object_bindings": bindings, "coverage": "适用项目门禁；对象关联不自动证明每个业务行为已验收",
                   "tool_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}}
        store.put("verification", receipt["id"], receipt, 0, tx)
        latest["verification"] = receipt
        latest["status"] = "verified"
        result = _record(store, latest, "change.verified", receipt, tx)
        _save_request(store, key, digest, result, tx)
    return result


def accept(project, payload):
    from _toolchain_runtime import lease_conflicts
    store = Store(project, create=True)
    with store.transaction() as tx:
        key, digest, old = _request(store, "change.accept", payload, tx)
        if old is not None:
            return old
        document = _document(store, payload.get("id"), payload.get("actor"), tx)
        if document["status"] != "verified":
            raise ToolchainError("接受需要已验证变更", "fail")
        _no_writers(store, tx)
        receipt = document.get("verification", {})
        if receipt.get("status") != "pass" or not receipt.get("fresh"):
            raise ToolchainError("验证未通过或证据已过期", "fail")
        _check_inputs(project, receipt["inputs"], inventory=True)
        if _branch(store, tx) != receipt["branch"]:
            raise ToolchainError("恢复后分支已变化，必须重新验证", "fail")
        tools = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
        if receipt["tool_sha256"] != tools:
            raise ToolchainError("验证工具已更新，必须重新验证", "fail")
        if document["unresolved"]:
            raise ToolchainError("变更仍有未决事项", "fail")
        if lease_conflicts(store, document["scope"], actor=document["actor"], conn=tx, architecture=document["architecture"]):
            raise ToolchainError("接受时模块范围被其他执行者占用", "fail")
        operation_sha = hashlib.sha256(encoded(document["operations"])).hexdigest()
        for module, participant in document["participants"].items():
            if (participant["status"] != "ready" or participant["operations_sha256"] != operation_sha or
                    participant["inputs"] != receipt["inputs"] or participant["branch"] != receipt["branch"]):
                raise ToolchainError("参与模块未就绪或依据过期: " + module, "fail")
        document["status"] = "accepted"
        document["accepted_at"] = now()
        result = _record(store, document, "change.accepted", {"verification": receipt["id"], "inputs": receipt["inputs"]}, tx)
        _save_request(store, key, digest, result, tx)
        return result


def change_dispatch(project: Path, architecture: str, action: str, payload: dict) -> dict:
    project = Path(project).resolve()
    if action == "change.begin":
        return begin(project, architecture, payload)
    if action in ("change.read", "change.status"):
        return _document(Store(project), payload.get("id"))
    if action == "change.list":
        values = Store(project).list("change")
        offset, limit = payload.get("offset", 0), payload.get("limit", 50)
        if type(offset) is not int or type(limit) is not int or offset < 0 or limit < 1:
            raise ToolchainError("分页需要 offset>=0、limit>=1")
        return {"items": values[offset:offset+limit], "offset": offset, "limit": limit,
                "total": len(values), "has_more": offset + limit < len(values)}
    if action == "change.preview":
        return preview(project, payload.get("id"))
    functions = {"change.stage": stage, "change.apply": apply, "change.verify": verify,
                 "change.accept": accept, "change.abort": abort, "change.recover": recover,
                 "change.coordinate": coordinate}
    if action not in functions:
        raise ToolchainError("未知变更命令: " + action)
    return functions[action](project, payload)
