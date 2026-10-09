#!/usr/bin/env python3
"""JSON CLI for physical recursive module architecture (Python 3.9+).

0 means the requested operation succeeded, 1 a known failed check/conflict,
2 invalid input or unavailable evidence. Structural success is never a claim
that module design, implementation or quality verification is complete.
"""

from __future__ import annotations

import argparse
import copy
from _architecture_core import derive_module_detail_subfields, load_schema
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402
import _module_tree as modules  # noqa: E402


class CommandInputError(ValueError):
    """A request cannot select a valid operation or module."""


class WriteConflict(ValueError):
    """Existing output or a changed input prevents a safe write."""


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CommandInputError(message)


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    data = _strict_json(raw)
    if not isinstance(data, dict):
        raise CommandInputError(f"架构文件根节点必须是对象: {path}")
    return data, hashlib.sha256(raw).hexdigest()


def _strict_json(raw: bytes) -> Any:
    """Reject ambiguous patches before they can select or overwrite a module.

    JSON Merge Patch depends on every key having one unambiguous value.  The
    standard decoder otherwise silently keeps the last duplicate key, and
    accepts NaN/Infinity even though they cannot be serialized by our writer.
    """
    try:
        return _archlib.strict_json_loads(raw.decode("utf-8-sig"))
    except ValueError as exc:
        raise CommandInputError(str(exc)) from exc


def _root_input(path: Path, root: Path | None) -> tuple[dict[str, Any], Path, Path, set[Path]]:
    path = path.absolute()
    root = root.absolute() if root is not None else _archlib.project_root_for_architecture(path)
    current = path
    visited: set[Path] = set()
    sources: set[Path] = set()
    while True:
        identity = current.resolve()
        if not modules._inside(identity, root):
            raise CommandInputError(f"架构输入路径超出项目范围: {current}")
        if identity in visited:
            raise _archlib.ArchitectureInputError(f"架构指针循环: {current}")
        visited.add(identity)
        sources.add(current)
        data, _ = _read(current)
        if isinstance(data.get("指向"), str):
            current = _archlib._contained_path(root, data["指向"], "架构指针", base=current.parent, allow_parent=True)
            continue
        data = _archlib.hydrate_slices(data, current, sources, project_root=root)
        return data, current, root, sources


def load_tree(architecture: Path, project_root: Path | None = None) -> tuple[modules.ModuleTree, set[Path]]:
    data, path, root, sources = _root_input(Path(architecture), project_root)
    if modules.ROUTE_FIELD not in data:
        raise CommandInputError("当前根架构未启用模块路由；请先显式初始化或迁移模块声明")
    tree = modules.build_module_tree(data, path, sources, project_root=root)
    return tree, sources


def _select(tree: modules.ModuleTree, module_id: str | None, file: str | None) -> tuple[str, str | None]:
    if module_id is not None:
        if module_id not in tree.documents:
            raise CommandInputError(f"模块编号不存在: {module_id}")
        return module_id, None
    if file is None:
        return tree.records[0]["编号"], None
    path = modules.safe_relative_path(tree.project_root, file, "源码定位")
    owners = [item for item in tree.records if modules._inside(path, tree.project_root / item["目录"])]
    if not owners:
        raise CommandInputError(f"源码路径没有所属模块: {file}")
    owner = max(owners, key=lambda item: len(Path(item["目录"]).parts))
    return owner["编号"], path.relative_to(tree.project_root).as_posix()


def route(tree: modules.ModuleTree, module_id: str | None = None, file: str | None = None) -> dict[str, Any]:
    selected, source = _select(tree, module_id, file)
    document = tree.documents[selected]
    result = {"status": "pass", "scope": "route", "模块": selected, "链": tree.chain(selected),
              "实现清单": copy.deepcopy(document.get("实现清单", {}).get(selected, {})),
              "说明": "按已声明目录定位；不推断模块职责是否正确"}
    if source is not None:
        result["源码路径"] = source
        result["已登记"] = source in tree.record(selected)["文件"]
    return result


def search(tree: modules.ModuleTree, query: str) -> dict[str, Any]:
    if not query.strip():
        raise CommandInputError("--query 不得为空")
    lowered = query.casefold()
    candidates = [copy.deepcopy(item) for item in tree.records
                  if lowered in item["名称"].casefold() or lowered in item["职责"].casefold()]
    return {"status": "pass", "scope": "candidates", "查询": query, "候选": candidates,
            "说明": "仅按名称/职责文本返回候选；须读取本层事实后判断语义，空候选不代表功能不存在"}


def impact(tree: modules.ModuleTree, module_id: str | None = None, file: str | None = None,
           direction: str = "dependents") -> dict[str, Any]:
    selected, source = _select(tree, module_id, file)
    edges = modules.dependency_edges(tree)
    unknown = sorted({value for edge in edges for value in edge} - set(tree.documents))
    children = {item["编号"]: item["子模块"] for item in tree.records}
    descendants: list[str] = []
    pending = list(reversed(children[selected]))
    while pending:
        current = pending.pop()
        descendants.append(current)
        pending.extend(reversed(children[current]))
    def reachable(reverse: bool) -> list[str]:
        adjacency: dict[str, set[str]] = {}
        for left, right in edges:
            origin, target = (right, left) if reverse else (left, right)
            adjacency.setdefault(origin, set()).add(target)
        seen = {selected}
        queue = [selected]
        for current in queue:
            for target in sorted(adjacency.get(current, set())):
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        return queue[1:]
    result: dict[str, Any] = {"status": "unknown" if unknown else "pass", "scope": "declared-impact",
        "模块": selected, "包含关系": {"祖先": [item["编号"] for item in tree.chain(selected)[:-1]], "后代": descendants},
        "依赖关系": {"方向约定": "从=依赖方，到=被依赖方", "边": modules.dependency_declarations(tree)["edges"], "未登记模块": unknown},
        "说明": "包含关系不自动计为依赖；仅报告显式声明的图，不推断动态调用或完整行为影响"}
    if direction in ("dependents", "both"):
        result["依赖关系"]["受影响消费者"] = reachable(True)
    if direction in ("dependencies", "both"):
        result["依赖关系"]["上游依赖"] = reachable(False)
    if source is not None:
        result["源码路径"] = source
    return result


def check(tree: modules.ModuleTree, sources: set[Path] | None = None, *, scan_orphans: bool = True,
          ignore_dirs: set[str] | None = None) -> dict[str, Any]:
    errors = modules.check_hydrated_module_files(tree.merged, tree.project_root)
    edges = modules.dependency_edges(tree)
    unknown = sorted({value for edge in edges for value in edge} - set(tree.documents))
    if unknown:
        errors.append(f"依赖图引用未登记模块: {', '.join(unknown)}")
    import validate_architecture
    cycle = validate_architecture.dependency_cycle([{"从": left, "到": right} for left, right in edges])
    if cycle:
        errors.append(f"模块依赖图存在有向环: {' -> '.join(cycle)}")
    for record in tree.records:
        document = tree.documents[record["编号"]]
        for key in ("模块详情", "实现清单"):
            if record["编号"] not in document.get(key, {}):
                errors.append(f"模块缺少本层{key}: {record['编号']}")
    if scan_orphans:
        for path in modules.unregistered_architectures(tree, allowed_paths=sources, ignore_dirs=ignore_dirs):
            errors.append(f"存在未登记模块架构文件: {path}")
    return {"status": "fail" if errors else "pass", "scope": "module-tree", "errors": errors,
            "模块目录": copy.deepcopy(tree.records), "扫描忽略目录": sorted(modules.inventory_ignore_dirs(tree, ignore_dirs)),
            "扫描说明": "扫描项目内未登记的所有 architecture.json；不遍历符号链接目录；忽略目录名称或项目相对目录以输出范围为准",
            "说明": "仅检查结构、目录归属、显式依赖及清单文件存在性；设计/实现/质量/执行结果仍需原门禁"}


def read_layer(path: Path, project_root: Path | None = None) -> dict[str, Any]:
    """Read exactly one architecture document, without opening child JSON."""
    path = path.absolute()
    root = project_root.absolute() if project_root is not None else _archlib.project_root_for_architecture(path)
    if not modules._inside(path, root):
        raise CommandInputError(f"架构文件超出项目范围: {path}")
    data, digest = _read(path)
    if "指向" in data:
        return {"status": "pass", "scope": "local", "路径": str(path), "sha256": digest, "当前层": data,
                "说明": "当前文件为入口指针；按指向显式读取下一层，本次未加载目标或全树"}
    modules.validate_route_header(data, path, root)
    return {"status": "pass", "scope": "local", "路径": str(path), "sha256": digest,
            "当前层": data, "直接子路由": copy.deepcopy(data[modules.ROUTE_FIELD]["子模块"]),
            "说明": "只读取当前层及其直接子路由声明；未打开子架构，不能据此宣称全树检查通过"}


def _module_skeleton(module_id: str, name: str, responsibility: str) -> dict[str, Any]:
    details = {key: "__待填__" for key in derive_module_detail_subfields(load_schema()[0])}
    details["职责"] = responsibility
    details["上游依赖"] = []
    details["下游消费者"] = []
    return {modules.ROUTE_FIELD: {"版本": 1, "编号": module_id, "名称": name, "职责": responsibility, "子模块": []},
            "功能树": ["__待填：在本模块记录所属功能子树；公共父节点只保留编号，完整事实不复制到根__"],
            "模块详情": {module_id: details},
            "实现清单": {module_id: {"文件列表": [], "入口文件": "", "依赖模块": [], "已完成": [],
                                      "未完成": ["__待填：模块设计、实现与验证尚未完成__"], "技术债": []}},
            "模块工作状态": {"阶段": "待设计", "下一步": ["先在本层功能树展开行为、异常与验收，再关联所属功能树节点", "完善本层模块详情、契约、实现清单与测试责任", "依赖在一个所属位置用模块编号声明；其他位置可留空，不重复复制", "建立真实验证收据索引"],
                             "问题": [], "验证收据索引": [], "验证状态": "未验证"},
            "接口契约": {}, "测试责任矩阵": [{"模块": module_id, "单元测试": "__待填__",
                                                   "集成测试": "__待填__", "测试覆盖率目标": "__待填__"}]}


def _serialized(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _cas_replace_bytes(path: Path, raw: bytes, expected: str) -> None:
    """Optimistic SHA precheck + atomic replace, not a multi-writer transaction.

    Editors that ignore this protocol can write between the comparison and the
    replacement; callers must not describe this as a strong compare-and-swap.
    """
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-module-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise WriteConflict(f"架构已变化，SHA256 不匹配；请重新读取再修改: {path}")
        if path.is_symlink():
            raise WriteConflict(f"拒绝替换符号链接架构文件: {path}")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _cas_write(path: Path, data: dict[str, Any], expected: str) -> None:
    _cas_replace_bytes(path, _serialized(data), expected)


def initialize(output: Path, module_id: str, name: str, responsibility: str,
               template: Path | None = None) -> dict[str, Any]:
    import init_architecture
    output = output.absolute()
    path = output if output.name == "architecture.json" else output / "architecture.json"
    if os.path.lexists(path):
        raise WriteConflict(f"输出文件已存在，禁止覆盖: {path}")
    if path.parent.exists() and not path.parent.is_dir():
        raise WriteConflict(f"输出目录已存在且不是目录: {path.parent}")
    template_data = init_architecture.load_template(template or init_architecture.DEFAULT_TEMPLATE)
    args = argparse.Namespace(time=None, name=name, project_type=None, language=None, framework=None, directory_convention=None)
    data = init_architecture.build_architecture(template_data, args)
    creation = {"时间": data.get("项目", {}).get("更新时间", init_architecture.now_iso()),
                "操作类型": "创建架构", "原因": "通过 module_architecture.py 初始化完整根 architecture.json 与递归模块路由",
                "影响范围": "architecture.json | 模块设计与质量验证待运行", "验证结果": "已生成根模板，设计与质量验证尚未完成",
                "剩余风险": "仅生成根模板；仍需逐层填写模块设计、实现清单、测试责任并运行质量门禁"}
    change_log = data.setdefault("变更记录", [])
    if not isinstance(change_log, list):
        raise CommandInputError("根模板的变更记录必须是数组")
    if (change_log and isinstance(change_log[-1], dict)
            and change_log[-1].get("原因") == "通过 init_architecture.py 初始化 architecture/ 架构文件夹"):
        change_log[-1].update(creation)
    else:
        change_log.append(creation)
    if isinstance(data.get("上下文恢复点"), dict):
        data["上下文恢复点"]["继续位置"] = "填写根全局设计；按模块路由在实际目录逐层填写模块架构、实现清单和测试责任"
    # The complete root retains global design and recovery placeholders.
    data.pop("架构切片", None)
    skeleton = _module_skeleton(module_id, name, responsibility)
    data.update(skeleton)
    data["模块拓扑"] = {"节点": [{"编号": module_id, "名称": name}], "依赖图": []}
    data["模块树"] = []  # Loader derives physical containment; explicit logical groups remain supported.
    data["架构切片"] = {"启用": False, "架构模式": "递归模块目录", "说明": "根维护全局信息；按模块路由逐层读取实际模块目录中的 architecture.json"}
    modules.build_module_tree(data, path, project_root=path.parent)
    encoded = _serialized(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(encoded)
    return {"status": "pass", "scope": "init", "路径": str(path), "模块": module_id,
            "说明": "已创建完整根模板和路由，保留深度占位符；模块设计、实现和验证尚未完成"}


def add(architecture: Path, parent: str, directory: str, module_id: str, name: str,
        responsibility: str, project_root: Path | None = None, *, adopt_existing: bool = False) -> dict[str, Any]:
    tree, sources = load_tree(architecture, project_root)
    if parent not in tree.documents:
        raise CommandInputError(f"父模块不存在: {parent}")
    if module_id in tree.documents:
        raise WriteConflict(f"模块编号已存在: {module_id}")
    parent_path = tree.paths[parent]
    parent_data, expected = _read(parent_path)
    if "架构切片" in parent_data and parent_data["架构切片"].get("启用") is True:
        raise CommandInputError("新增模块前请将路由声明放入完整根 architecture.json；禁止修改合成切片视图")
    target_dir = modules.safe_relative_path(tree.project_root, directory, "新模块目录", base=parent_path.parent)
    target = target_dir / "architecture.json"
    if not modules._inside(target_dir, parent_path.parent, strict=True):
        raise CommandInputError("新模块目录必须是父模块目录的实际后代")
    if os.path.lexists(target):
        raise WriteConflict(f"模块架构文件已存在，禁止覆盖: {target}")
    if os.path.lexists(target_dir):
        if not adopt_existing:
            raise WriteConflict(f"模块目录已存在；显式纳管请添加 --adopt-existing: {target_dir}")
        if not target_dir.is_dir() or target_dir.is_symlink():
            raise WriteConflict(f"只能显式纳管实际目录，拒绝文件或符号链接: {target_dir}")
    # Do not create a sibling inside an already routed descendant.
    for item in tree.records:
        if item["编号"] != parent and modules._inside(target_dir, tree.project_root / item["目录"]):
            if item["编号"] not in [node["编号"] for node in tree.chain(parent)]:
                raise WriteConflict(f"新目录属于已登记模块 {item['编号']}；请以该模块为父亲")
    child = _module_skeleton(module_id, name, responsibility)
    updated = copy.deepcopy(parent_data)
    route_path = target.relative_to(parent_path.parent).as_posix()
    updated[modules.ROUTE_FIELD]["子模块"].append({"编号": module_id, "路径": route_path, "职责": responsibility})
    overrides = {target.resolve(): child, parent_path.resolve(): updated}
    root_data = updated if parent == tree.records[0]["编号"] else tree.documents[tree.records[0]["编号"]]
    candidate = modules.build_module_tree(root_data, tree.architecture_path, project_root=tree.project_root, _overrides=overrides)
    orphans = modules.unregistered_architectures(candidate, allowed_paths=sources)
    if orphans:
        raise WriteConflict(f"新增前存在未登记模块架构文件，请先登记或显式配置扫描范围: {', '.join(orphans)}")
    _serialized(updated)
    encoded_child = _serialized(child)
    # Recheck reviewed parent bytes before creating any directory.
    if hashlib.sha256(parent_path.read_bytes()).hexdigest() != expected:
        raise WriteConflict("父架构已变化；请重新读取后新增模块")
    created: list[Path] = []
    current = target_dir
    while not current.exists():
        created.append(current)
        current = current.parent
    child_written = False
    child_inode = None
    try:
        for path in reversed(created):
            path.mkdir()
        with target.open("xb") as handle:
            child_written = True
            child_inode = (os.fstat(handle.fileno()).st_dev, os.fstat(handle.fileno()).st_ino)
            handle.write(encoded_child)
        _cas_write(parent_path, updated, expected)
    except Exception:
        # Roll back only the exact file/directories this invocation created.
        if child_written and target.is_file():
            stat = target.stat()
            if (stat.st_dev, stat.st_ino) == child_inode:
                target.unlink()
        for path in created:
            if path.exists():
                try:
                    path.rmdir()
                except OSError:
                    pass  # Concurrently created user files must remain intact.
        raise
    return {"status": "pass", "scope": "add", "模块": module_id, "父模块": parent,
            "路径": str(target), "父架构SHA256": hashlib.sha256(parent_path.read_bytes()).hexdigest(),
            "显式纳管": adopt_existing,
            "说明": "已登记模块骨架；设计、实现及验证占位符仍需填写"}


def _merge_patch(document: Any, patch: Any) -> Any:
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = copy.deepcopy(document) if isinstance(document, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = _merge_patch(result.get(key), value)
    return result


def update(architecture: Path, module_id: str, patch_path: Path, expected: str,
           project_root: Path | None = None) -> dict[str, Any]:
    if len(expected) != 64 or any(char not in "0123456789abcdefABCDEF" for char in expected):
        raise CommandInputError("--expected-sha256 必须是64位十六进制摘要")
    tree, sources = load_tree(architecture, project_root)
    if module_id not in tree.documents:
        raise CommandInputError(f"模块编号不存在: {module_id}")
    path = tree.paths[module_id]
    current, actual = _read(path)
    if isinstance(current.get("架构切片"), dict) and current["架构切片"].get("启用") is True:
        raise CommandInputError("局部更新不得覆盖切片合成根；请显式编辑其物理声明文件")
    if actual != expected.lower():
        raise WriteConflict("架构已变化，SHA256 不匹配；未写入任何文件")
    patch_data, _ = _read(patch_path)
    modified = _merge_patch(current, patch_data)
    modified_route = modified.get(modules.ROUTE_FIELD)
    if not isinstance(modified_route, dict) or modified_route.get("编号") != module_id:
        raise WriteConflict("局部更新不得更改稳定模块编号")
    root_id = tree.records[0]["编号"]
    root_data = modified if module_id == root_id else tree.documents[root_id]
    candidate = modules.build_module_tree(root_data, tree.architecture_path, project_root=tree.project_root,
                                          _overrides={path.resolve(): modified})
    previous_module_paths = {item.resolve() for item in tree.paths.values()}
    auxiliary_sources = {item for item in sources if item.resolve() not in previous_module_paths}
    orphans = modules.unregistered_architectures(candidate, allowed_paths=auxiliary_sources)
    if orphans:
        raise WriteConflict(f"局部更新会留下或保留未登记模块架构文件: {', '.join(orphans)}")
    _cas_write(path, modified, actual)
    return {"status": "pass", "scope": "update", "模块": module_id, "路径": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "说明": "已按 JSON Merge Patch 局部更新并预检结构；SHA256为乐观并发预检，原子替换不构成多写者强事务；未宣称设计或质量验证完成"}


def update_batch(architecture: Path, patch_path: Path, project_root: Path | None = None) -> dict[str, Any]:
    """Coordinate local Merge Patches after validating the complete candidate.

    All reviewed hashes are checked again before the first write. Sequential
    atomic replacements and guarded best-effort rollback are optimistic: they
    do not provide a strong transaction across concurrent external writers.
    """
    tree, sources = load_tree(architecture, project_root)
    patch_data, _ = _read(patch_path)
    changes = patch_data.get("更新")
    if not isinstance(changes, list) or not changes:
        raise CommandInputError("批量补丁必须包含非空 更新 数组")
    reviewed = []
    overrides: dict[Path, dict[str, Any]] = {}
    ids: set[str] = set()
    for item in changes:
        if not isinstance(item, dict):
            raise CommandInputError("每项批量更新必须是对象")
        module_id = item.get("编号")
        expected = item.get("预期SHA256")
        patch_value = item.get("补丁")
        if not isinstance(module_id, str) or module_id not in tree.documents:
            raise CommandInputError(f"批量更新模块编号不存在: {module_id}")
        if module_id in ids:
            raise CommandInputError(f"批量更新模块编号重复: {module_id}")
        ids.add(module_id)
        if (not isinstance(expected, str) or len(expected) != 64
                or any(char not in "0123456789abcdefABCDEF" for char in expected)):
            raise CommandInputError(f"预期SHA256 必须是64位十六进制摘要: {module_id}")
        if not isinstance(patch_value, dict):
            raise CommandInputError(f"批量补丁必须是 JSON Merge Patch 对象: {module_id}")
        path = tree.paths[module_id]
        original_bytes = path.read_bytes()
        actual = hashlib.sha256(original_bytes).hexdigest()
        if actual != expected.lower():
            raise WriteConflict(f"批量预检SHA256不匹配，未写入任何文件: {module_id}")
        if path.is_symlink():
            raise WriteConflict(f"批量更新拒绝符号链接架构文件: {path}")
        current = _strict_json(original_bytes)
        if not isinstance(current, dict):
            raise CommandInputError(f"批量更新目标根节点必须是对象: {module_id}")
        if isinstance(current.get("架构切片"), dict) and current["架构切片"].get("启用") is True:
            raise CommandInputError("批量更新不得覆盖切片合成根；请显式编辑其物理声明文件")
        modified = _merge_patch(current, patch_value)
        header = modified.get(modules.ROUTE_FIELD)
        if not isinstance(header, dict) or header.get("编号") != module_id:
            raise WriteConflict(f"批量更新不得更改稳定模块编号: {module_id}")
        encoded = _serialized(modified)
        overrides[path.resolve()] = modified
        reviewed.append({"编号": module_id, "路径": path, "原始字节": original_bytes,
                         "原始摘要": actual, "候选": modified, "候选字节": encoded})
    root_id = tree.records[0]["编号"]
    root_data = overrides.get(tree.architecture_path.resolve(), tree.documents[root_id])
    candidate = modules.build_module_tree(root_data, tree.architecture_path, project_root=tree.project_root,
                                          _overrides=overrides)
    previous_paths = {path.resolve() for path in tree.paths.values()}
    auxiliary = {path for path in sources if path.resolve() not in previous_paths}
    orphans = modules.unregistered_architectures(candidate, allowed_paths=auxiliary)
    if orphans:
        raise WriteConflict(f"批量候选存在未登记模块架构文件，未写入任何文件: {', '.join(orphans)}")
    # Complete every second hash check before beginning any replacement.
    for item in reviewed:
        if hashlib.sha256(item["路径"].read_bytes()).hexdigest() != item["原始摘要"]:
            raise WriteConflict(f"批量写入前SHA256已变化，未写入任何文件: {item['编号']}")
    written = []
    try:
        for item in reviewed:
            _cas_write(item["路径"], item["候选"], item["原始摘要"])
            written.append(item)
    except Exception as exc:
        recovered, unresolved = [], []
        for item in reversed(written):
            path = item["路径"]
            try:
                candidate_hash = hashlib.sha256(item["候选字节"]).hexdigest()
                if hashlib.sha256(path.read_bytes()).hexdigest() != candidate_hash:
                    unresolved.append(f"{item['编号']}:文件已被其他写者更改，未回退")
                    continue
                _cas_replace_bytes(path, item["原始字节"], candidate_hash)
                recovered.append(item["编号"])
            except (OSError, WriteConflict) as rollback_error:
                unresolved.append(f"{item['编号']}:{rollback_error}")
        message = f"批量写入失败: {exc}；已尽力回退: {', '.join(recovered) or '无'}"
        if unresolved:
            raise CommandInputError(message + "；需复核: " + "; ".join(unresolved)) from exc
        raise WriteConflict(message) from exc
    return {"status": "pass", "scope": "update-batch", "更新": [
        {"编号": item["编号"], "路径": str(item["路径"]), "sha256": hashlib.sha256(item["候选字节"]).hexdigest()}
        for item in reviewed], "扫描忽略目录": sorted(modules.inventory_ignore_dirs(candidate)),
        "说明": "已协调预检全部候选并逐个原子替换；SHA检查与失败回退为乐观尽力机制，不承诺多进程强事务；未宣称设计或质量验证完成"}


def _parser() -> argparse.ArgumentParser:
    parser = JSONArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=JSONArgumentParser)
    for command in ("read", "route", "search", "check", "impact", "add", "update", "update-batch"):
        child = sub.add_parser(command)
        child.add_argument("--architecture", type=Path, default=Path("architecture.json"))
        child.add_argument("--project-root", type=Path)
        child.add_argument("--json", action="store_true", help="兼容标志；所有结果始终为JSON")
        if command in {"route", "impact"}:
            selectors = child.add_mutually_exclusive_group()
            selectors.add_argument("--module")
            selectors.add_argument("--file")
        if command == "search":
            child.add_argument("--query", required=True)
        if command == "check":
            child.add_argument("--ignore-dir", action="append", default=[], help="仅孤儿架构扫描忽略的目录名称或项目相对目录，可重复；输出会列明范围")
        if command == "impact":
            child.add_argument("--direction", choices=("dependents", "dependencies", "both"), default="dependents")
        if command == "add":
            child.add_argument("--parent", required=True)
            child.add_argument("--directory", required=True, help="相对父架构目录的新模块目录，不得已存在")
            child.add_argument("--id", required=True)
            child.add_argument("--name", required=True)
            child.add_argument("--responsibility", required=True)
            child.add_argument("--adopt-existing", action="store_true", help="显式纳管已有目录；只创建缺失的architecture.json，原源码不写入")
        if command == "update":
            child.add_argument("--module", required=True)
            child.add_argument("--patch", type=Path, required=True, help="JSON Merge Patch 对象文件；null删除键")
            child.add_argument("--expected-sha256", required=True)
        if command == "update-batch":
            child.add_argument("--patch", type=Path, required=True, help="对象: 更新:[{编号,预期SHA256,补丁(JSON Merge Patch)}]")
    init = sub.add_parser("init")
    init.add_argument("--output", type=Path, default=Path("."))
    init.add_argument("--id", required=True)
    init.add_argument("--name", required=True)
    init.add_argument("--responsibility", required=True)
    init.add_argument("--template", type=Path)
    init.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    _archlib.configure_utf8_stdout()
    command = None
    try:
        args = _parser().parse_args(argv)
        command = args.command
        if command == "init":
            result = initialize(args.output, args.id, args.name, args.responsibility, args.template)
        elif command == "add":
            result = add(args.architecture, args.parent, args.directory, args.id, args.name, args.responsibility,
                         args.project_root, adopt_existing=args.adopt_existing)
        elif command == "update":
            result = update(args.architecture, args.module, args.patch, args.expected_sha256, args.project_root)
        elif command == "update-batch":
            result = update_batch(args.architecture, args.patch, args.project_root)
        elif command == "read":
            result = read_layer(args.architecture, args.project_root)
        else:
            tree, sources = load_tree(args.architecture, args.project_root)
            if command == "check":
                ignored = set()
                for value in args.ignore_dir:
                    try:
                        path = modules.safe_relative_path(tree.project_root, value, "忽略目录")
                    except _archlib.ArchitectureInputError as exc:
                        raise CommandInputError(str(exc)) from exc
                    relative = path.relative_to(tree.project_root).as_posix()
                    if relative == ".":
                        raise CommandInputError("孤儿架构扫描不能忽略整个项目根目录")
                    ignored.add(relative)
                result = check(tree, sources, ignore_dirs=ignored)
            elif command == "route":
                result = route(tree, args.module, args.file)
            elif command == "search":
                result = search(tree, args.query)
            elif command == "impact":
                result = impact(tree, args.module, args.file, args.direction)
        code = {"pass": 0, "fail": 1, "unknown": 2}[result["status"]]
    except (WriteConflict, FileExistsError) as exc:
        result, code = {"status": "fail", "scope": command or "input", "errors": [str(exc)]}, 1
    except _archlib.ArchitectureInputError as exc:
        # A structurally contradictory architecture is a known failed check;
        # for other requests it is invalid input, not completed work.
        code = 1 if command == "check" else 2
        result = {"status": "fail" if code == 1 else "unknown", "scope": command or "input", "errors": [str(exc)]}
    except (CommandInputError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        result, code = {"status": "unknown", "scope": command or "input", "errors": [str(exc)]}, 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
