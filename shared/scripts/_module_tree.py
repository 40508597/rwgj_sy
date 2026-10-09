#!/usr/bin/env python3
"""Read-only recursive module routing, independent of programming language.

Every physical module owns its ``architecture.json`` and its directly owned
implementation files. Route paths are relative to the declaring architecture
file; implementation paths retain the existing project-root-relative contract.
Imports of _archlib are deliberately lazy: its loader calls this module.
"""

from __future__ import annotations

import copy
from _architecture_core import ArchitectureView, declared_dependencies, dependency_kind, pointer_value
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROUTE_FIELD = "模块路由"
CATALOG_FIELD = "模块目录"
FACTS_FIELD = "模块归属事实"
RESERVED_FIELDS = {CATALOG_FIELD, FACTS_FIELD}
GLOBAL_FIELDS = {
    "项目", "指向", "架构切片", "索引摘要", "上下文恢复点", "验证证据",
    "未决问题", "变更记录", "专业能力索引", "质量状态", "质量规则",
    "质量门禁", "质量策略", "质量事实", "全局质量状态", "项目身份",
    "扫描忽略目录",
    "专业能力调用", "能力调用记录",
}
# Other child fields are preserved under that module's ID, never flattened.
MERGED_FIELDS = {
    "模块详情", "实现清单", "模块拓扑", "模块树", "接口契约", "测试责任矩阵",
    "功能树", "运行形态", "页面拓扑", "数据拓扑", "交付物", "系统集成", "完整细节", "入口",
}
DEFAULT_IGNORE_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__"}


def _lib():
    import _archlib
    return _archlib


def _invalid(message: str):
    return _lib().ArchitectureInputError(message)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\x00\r\n"):
        raise _invalid(f"{label}必须是非空单行字符串")
    return value


def safe_relative_path(root: Path, value: str, label: str, *, base: Path | None = None) -> Path:
    """Reject lexical escapes, Windows drives/ADS and symlink escapes."""
    _text(value, label)
    normalized = value.replace("\\", "/")
    if ":" in normalized or normalized.startswith("/"):
        raise _invalid(f"{label}必须是项目内的相对路径: {value}")
    return _lib()._contained_path(root, normalized, label, base=base)


def _inside(path: Path, directory: Path, *, strict: bool = False) -> bool:
    try:
        relative = path.resolve().relative_to(directory.resolve())
        return not strict or bool(relative.parts)
    except ValueError:
        return False


def _resolved_inside(path: Path, directory: Path, *, strict: bool = False) -> bool:
    """Containment for paths already resolved once; avoid repeated disk IO."""
    try:
        relative = path.relative_to(directory)
        return not strict or bool(relative.parts)
    except ValueError:
        return False


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def validate_route_header(data: Any, path: Path, root: Path) -> dict[str, Any]:
    """Validate only this layer and direct route paths; do not open children."""
    if not isinstance(data, dict):
        raise _invalid(f"模块架构根节点必须是对象: {path}")
    forbidden = RESERVED_FIELDS.intersection(data)
    if forbidden:
        raise _invalid(f"{path}不得手写派生字段: {', '.join(sorted(forbidden))}")
    header = data.get(ROUTE_FIELD)
    if not isinstance(header, dict):
        raise _invalid(f"{path}缺少模块路由对象")
    if type(header.get("版本")) is not int or header["版本"] != 1:
        raise _invalid(f"模块路由.版本必须是整数 1: {path}")
    for key in ("编号", "名称", "职责"):
        _text(header.get(key), f"模块路由.{key} ({path})")
    if "扫描忽略目录" in header:
        if not isinstance(header["扫描忽略目录"], list):
            raise _invalid("模块路由.扫描忽略目录必须是数组")
        _validated_ignore_dirs(root, header["扫描忽略目录"])
    children = header.get("子模块")
    if not isinstance(children, list):
        raise _invalid(f"模块路由.子模块必须是数组: {path}")
    local_ids: set[str] = set()
    for child in children:
        if not isinstance(child, dict):
            raise _invalid(f"子模块路由必须是对象: {path}")
        child_id = _text(child.get("编号"), f"子模块.编号 ({path})")
        _text(child.get("职责"), f"子模块.职责 ({path})")
        target = safe_relative_path(root, child.get("路径"), "子模块路由", base=path.parent)
        if target.name != "architecture.json":
            raise _invalid(f"子模块必须使用实际目录中的 architecture.json: {target}")
        if not _inside(target.parent, path.parent, strict=True):
            raise _invalid(f"子模块架构必须位于父架构的实际后代目录: {target}")
        if child_id in local_ids:
            raise _invalid(f"子模块路由编号重复: {child_id}")
        local_ids.add(child_id)
    return header


def _validated_ignore_dirs(root: Path, values: Any) -> set[str]:
    if not isinstance(values, (list, set, tuple)):
        raise _invalid("模块路由.扫描忽略目录必须是项目内目录路径数组")
    result = set()
    for value in values:
        path = safe_relative_path(root, value, "扫描忽略目录")
        relative = path.relative_to(root).as_posix()
        if relative == ".":
            raise _invalid("孤儿架构扫描不能忽略整个项目根目录")
        if path.exists() and not path.is_dir():
            raise _invalid(f"扫描忽略目录不得是文件: {relative}")
        result.add(relative)
    return result


def _manifest_paths(data: dict[str, Any], module_id: str, root: Path) -> list[str]:
    for field_name in ("模块详情", "实现清单"):
        container = data.get(field_name, {})
        if not isinstance(container, dict):
            raise _invalid(f"{field_name}必须是模块对象: {module_id}")
        for key, value in container.items():
            if key != module_id:
                raise _invalid(f"{module_id}的{field_name}只能声明本模块，发现: {key}")
            if not isinstance(value, dict):
                raise _invalid(f"{field_name}.{key}必须是对象")
            for alias in ("模块编号", "模块号"):
                if alias in value and (not isinstance(value[alias], str) or value[alias] != module_id):
                    raise _invalid(f"{field_name}.{key}.{alias} 与模块归属不一致: {module_id}")
    files = _lib().collect_implementation_files(data)
    entry = data.get("实现清单", {}).get(module_id, {}).get("入口文件")
    if entry is not None and entry != "":
        files.add(_text(entry, f"实现清单.{module_id}.入口文件").replace("\\", "/"))
    normalized: set[str] = set()
    for value in files:
        path = safe_relative_path(root, value, f"实现清单.{module_id}")
        # Keep declared spelling/project-relative paths rather than resolving
        # source symlinks into a different declaration silently.
        normalized.add(path.relative_to(root).as_posix())
    return sorted(normalized)


@dataclass
class ModuleTree:
    project_root: Path
    architecture_path: Path
    records: list[dict[str, Any]] = field(default_factory=list)
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)
    merged: dict[str, Any] = field(default_factory=dict)

    def record(self, module_id: str) -> dict[str, Any]:
        for record in self.records:
            if record["编号"] == module_id:
                return record
        raise KeyError(module_id)

    def chain(self, module_id: str) -> list[dict[str, Any]]:
        by_id = {item["编号"]: item for item in self.records}
        chain = []
        current = by_id[module_id]
        while True:
            chain.append(copy.deepcopy(current))
            parent = current["父模块"]
            if parent is None:
                break
            current = by_id[parent]
        chain.reverse()
        return chain


def build_module_tree(data: dict[str, Any], architecture_path: Path,
                      source_paths: set[Path] | None = None, *, project_root: Path | None = None,
                      _overrides: dict[Path, dict[str, Any]] | None = None) -> ModuleTree:
    """Validate and hydrate a finite tree iteratively, without a depth limit.

    The private override map supports mutation preflight without creating files.
    Filesystem and malformed JSON errors remain IO/input errors to the caller.
    """
    architecture_path = Path(architecture_path).absolute()
    root = Path(project_root).absolute() if project_root is not None else _lib().project_root_for_architecture(architecture_path)
    root = root.absolute()
    if not _inside(architecture_path, root):
        raise _invalid(f"架构输入路径超出项目范围: {architecture_path}")
    overrides = {Path(key).resolve(): value for key, value in (_overrides or {}).items()}
    tree = ModuleTree(root, architecture_path)
    tree.merged = copy.deepcopy(data)
    seen_paths: set[Path] = set()
    seen_dirs: set[Path] = set()
    seen_inodes: set[tuple[int, int]] = set()
    # Stack items: document path, parent ID, parent route, already-read payload.
    pending = [(architecture_path, None, None, data)]
    while pending:
        path, parent_id, parent_route, document = pending.pop()
        identity = path.resolve()
        directory = root.resolve() if parent_id is None else identity.parent
        if identity in seen_paths or directory in seen_dirs:
            raise _invalid(f"模块架构文件或实际目录重复（循环/多父亲）: {path}")
        if path.is_file():
            stat = path.stat()
            inode = (stat.st_dev, stat.st_ino)
            if stat.st_ino and inode in seen_inodes:
                raise _invalid(f"模块架构重复引用同一真实文件: {path}")
            if stat.st_ino:
                seen_inodes.add(inode)
            tree.digests[str(identity)] = hashlib.sha256(path.read_bytes()).hexdigest()
        seen_paths.add(identity)
        seen_dirs.add(directory)
        header = validate_route_header(document, path, root)
        module_id = header["编号"]
        if module_id in tree.documents:
            raise _invalid(f"模块编号必须全局唯一: {module_id}")
        if parent_route is not None:
            if parent_route["编号"] != module_id or parent_route["职责"] != header["职责"]:
                raise _invalid(f"父路由与子模块头编号/职责不一致: {path}")
            forbidden = GLOBAL_FIELDS.intersection(document)
            if forbidden:
                raise _invalid(f"子模块不得覆盖全局字段: {', '.join(sorted(forbidden))} ({path})")
            if "扫描忽略目录" in header:
                raise _invalid(f"子模块不得重新定义全局扫描忽略目录: {path}")
        if source_paths is not None:
            source_paths.add(path)
        files = _manifest_paths(document, module_id, root)
        record = {"编号": module_id, "父模块": parent_id, "路径": _relative(path, root),
                  "目录": _relative(directory, root), "名称": header["名称"], "职责": header["职责"],
                  "子模块": [child["编号"] for child in header["子模块"]], "文件": files}
        # Preserve route extensions as owned facts too (source route is intact).
        custom = {key: copy.deepcopy(value) for key, value in document.items()
                  if key not in MERGED_FIELDS and key != ROUTE_FIELD}
        if parent_id is not None:
            for key in MERGED_FIELDS:
                if key in document:
                    tree.merged[key] = (_lib()._merge_slice_value(tree.merged[key], document[key], key)
                                        if key in tree.merged else copy.deepcopy(document[key]))
        if parent_id is not None:
            # Preserve the original direct routes, including unknown extension
            # facts on both the header and individual child route entries.
            custom[ROUTE_FIELD] = copy.deepcopy(header)
            tree.merged.setdefault(FACTS_FIELD, {})[module_id] = custom
        tree.records.append(record)
        tree.documents[module_id] = copy.deepcopy(document)
        tree.paths[module_id] = path
        for child in reversed(header["子模块"]):
            child_path = safe_relative_path(root, child["路径"], "子模块路由", base=path.parent)
            child_identity = child_path.resolve()
            if child_identity in overrides:
                child_data = overrides[child_identity]
            else:
                if not child_path.is_file():
                    raise _invalid(f"模块路由文件不存在或不是文件: {child_path}")
                child_data = _lib()._read_architecture_file(child_path)
            pending.append((child_path, module_id, child, child_data))
    # The physical containment tree must agree with the declared parent. A
    # nested directory cannot be registered as a sibling to its owner.
    resolved_dirs = {record["编号"]: (root / record["目录"]).resolve() for record in tree.records}
    for record in tree.records:
        if record["父模块"] is None:
            continue
        directory = resolved_dirs[record["编号"]]
        containers = [item for item in tree.records if item["编号"] != record["编号"]
                      and _resolved_inside(directory, resolved_dirs[item["编号"]], strict=True)]
        closest = max(containers, key=lambda item: len(Path(item["目录"]).parts))
        if closest["编号"] != record["父模块"]:
            raise _invalid(f"模块的声明父亲与实际目录归属不一致: {record['编号']}")
    # Every source belongs to the deepest physical module directory. Parent
    # modules may own source files alongside children, but not within them.
    declarations: dict[Path, str] = {}
    declared_inodes: dict[tuple[int, int], tuple[str, str]] = {}
    architecture_sources = set(tree.paths.values()) | set(source_paths or set())
    architecture_identities = {path.resolve() for path in architecture_sources}
    architecture_inodes = set(seen_inodes)
    for architecture_source in architecture_sources:
        if architecture_source.is_file():
            stat = architecture_source.stat()
            if stat.st_ino:
                architecture_inodes.add((stat.st_dev, stat.st_ino))
    for record in tree.records:
        for relative in record["文件"]:
            path = safe_relative_path(root, relative, "实现清单")
            identity = path.resolve()
            owners = [item for item in tree.records if _resolved_inside(identity, resolved_dirs[item["编号"]])]
            owner = max(owners, key=lambda item: len(Path(item["目录"]).parts)) if owners else None
            if owner is None or owner["编号"] != record["编号"]:
                raise _invalid(f"实现清单文件越出本模块或进入子模块: {record['编号']}: {relative}")
            if identity in architecture_identities:
                raise _invalid(f"模块架构文件不得冒充实现文件: {relative}")
            if identity in declarations and declarations[identity] != record["编号"]:
                raise _invalid(f"实现文件被多个模块声明: {relative}")
            declarations[identity] = record["编号"]
            if path.is_file():
                stat = path.stat()
                inode = (stat.st_dev, stat.st_ino)
                if stat.st_ino and inode in architecture_inodes:
                    raise _invalid(f"架构元数据真实文件不得通过硬链接冒充实现文件: {relative}")
                previous = declared_inodes.get(inode)
                if stat.st_ino and previous is not None and previous != (record["编号"], relative):
                    raise _invalid(f"实现清单重复声明同一真实文件: {previous[1]}, {relative}")
                if stat.st_ino:
                    declared_inodes[inode] = (record["编号"], relative)
    # Project real module IDs into the existing topology without destroying
    # unknown node attributes or resolving a contradictory name by overwrite.
    nodes = [{"编号": item["编号"], "名称": item["名称"]} for item in tree.records]
    topology = tree.merged.get("模块拓扑", {})
    if not isinstance(topology, dict):
        raise _invalid("模块拓扑必须是对象")
    existing_nodes = topology.get("节点", [])
    if not isinstance(existing_nodes, list):
        raise _invalid("模块拓扑.节点必须是数组")
    topology = copy.deepcopy(topology)
    topology["节点"] = _lib()._merge_slice_value(existing_nodes, nodes, "模块拓扑.节点")
    topology.setdefault("依赖图", [])
    tree.merged["模块拓扑"] = topology
    tree.merged[CATALOG_FIELD] = copy.deepcopy(tree.records)
    if not tree.merged.get("模块树"):
        by_id = {item["编号"]: {"编号": item["编号"], "名称": item["名称"], "子模块": []}
                 for item in tree.records}
        for item in tree.records:
            if item["父模块"] is not None:
                by_id[item["父模块"]]["子模块"].append(by_id[item["编号"]])
        tree.merged["模块树"] = [by_id[tree.records[0]["编号"]]]
    # Physical origins are an in-memory sidecar, not another persisted field or
    # business truth source. It must not alter canonical JSON / review hashes.
    declared = dependency_declarations(tree, _with_view_values=True)
    graph = tree.merged["模块拓扑"].get("依赖图", [])
    for edge in declared["edges"]:
        for origin in edge["sources"]:
            raw = origin.pop("value", None)
            logical = origin.pop("_view_value", raw)
            origin.setdefault("relation_type", dependency_kind(raw))
            origin.setdefault("view_pointer", origin["pointer"])
            if origin["view_pointer"].startswith("/模块拓扑/依赖图/") and isinstance(graph, list):
                matches = [i for i, item in enumerate(graph)
                           if type(item) is type(logical) and item == logical
                           or isinstance(logical, dict) and isinstance(item, dict)
                           and isinstance(logical.get("编号"), str) and item.get("编号") == logical["编号"]]
                origin["view_pointer"] = "/模块拓扑/依赖图/" + str(matches[0]) if matches else "/模块拓扑"
            physical = root / origin["file"] if "file" in origin else None
            if physical is not None and str(physical.resolve()) in tree.digests:
                origin["sha256"] = tree.digests[str(physical.resolve())]
    for diagnostic in declared["diagnostics"]:
        diagnostic.pop("value", None)
        if "file" in diagnostic:
            physical = root / diagnostic["file"]
            if str(physical.resolve()) in tree.digests:
                diagnostic["sha256"] = tree.digests[str(physical.resolve())]
    tree.merged = ArchitectureView(tree.merged, declared)
    return tree


def hydrate_module_tree(data: Any, architecture_path: Path,
                        source_paths: set[Path] | None = None, *, project_root: Path | None = None) -> Any:
    """Pass legacy data through; hydrate only an explicit root module route."""
    if not isinstance(data, dict) or ROUTE_FIELD not in data:
        return data
    return build_module_tree(data, architecture_path, source_paths, project_root=project_root).merged


def check_hydrated_module_files(data: Any, project_root: Path) -> list[str]:
    """Check every declared file, with no extension filter or JSON reread."""
    if not isinstance(data, dict) or CATALOG_FIELD not in data:
        return []
    errors = []
    root = Path(project_root).absolute()
    catalog = data[CATALOG_FIELD]
    if not isinstance(catalog, list):
        return ["派生模块目录必须是数组"]
    for record in catalog:
        if (not isinstance(record, dict) or not isinstance(record.get("文件"), list)
                or not isinstance(record.get("目录"), str)):
            errors.append("派生模块目录记录或文件数组无效")
            continue
        for relative in record["文件"]:
            try:
                path = safe_relative_path(root, relative, "模块实现文件")
                if not path.is_file():
                    errors.append(f"模块实现文件不存在或不是文件: {record.get('编号')}: {relative}")
                elif not _inside(path, root / record.get("目录", "")):
                    errors.append(f"模块实现文件越出模块目录: {relative}")
            except (ValueError, OSError) as exc:
                errors.append(str(exc))
    return errors


def inventory_ignore_dirs(tree: ModuleTree, extra: set[str] | None = None) -> set[str]:
    """One inventory scope shared by check, add/update and existing validators."""
    header = tree.merged.get(ROUTE_FIELD, {})
    values = header.get("扫描忽略目录", []) if isinstance(header, dict) else []
    ignored = set(DEFAULT_IGNORE_DIRS)
    ignored.update(_validated_ignore_dirs(tree.project_root, values))
    if extra is not None:
        ignored.update(_validated_ignore_dirs(tree.project_root, extra))
    return ignored


def unregistered_architectures(tree: ModuleTree, *, ignore_dirs: set[str] | None = None,
                               allowed_paths: set[Path] | None = None) -> list[str]:
    """Find architecture.json files omitted by the routes in explicit scope."""
    ignored = inventory_ignore_dirs(tree, ignore_dirs)
    known = {path.resolve() for path in tree.paths.values()}
    known.update(path.resolve() for path in (allowed_paths or set()))
    result = []
    def raise_error(error: OSError) -> None:
        raise error
    def linked_directory(path: Path) -> bool:
        # Windows junctions are reparse points but were not classified as
        # symlinks by older Python releases. Never descend them during inventory.
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    for directory, dirs, files in os.walk(tree.project_root, followlinks=False, onerror=raise_error):
        dirs[:] = [name for name in dirs if name not in ignored
                   and (Path(directory) / name).relative_to(tree.project_root).as_posix() not in ignored
                   and not linked_directory(Path(directory) / name)]
        if "architecture.json" in files:
            path = Path(directory) / "architecture.json"
            if path.resolve() not in known:
                result.append(path.relative_to(tree.project_root).as_posix())
    return sorted(result)


def dependency_declarations(tree: ModuleTree, *, _with_view_values: bool = False) -> dict[str, list[dict]]:
    """Collect the same declared graph as render/query, with physical sources."""
    combined = {}
    diagnostics = []
    physical_values = {}
    def original_value(loc):
        file = loc["file"]
        if file not in physical_values:
            path = safe_relative_path(tree.project_root, file, "依赖声明来源")
            raw = path.read_bytes()
            physical_values[file] = (_lib().strict_json_loads(raw), hashlib.sha256(raw).hexdigest())
        physical, digest = physical_values[file]
        if loc.get("sha256") is not None and loc["sha256"] != digest:
            raise _invalid(f"依赖声明来源内容已变化，请重新读取: {file}")
        return copy.deepcopy(pointer_value(physical, loc["pointer"]))
    documents = tree.documents or {"": tree.merged}
    for module_id, document in documents.items():
        source = (_relative(tree.paths[module_id], tree.project_root)
                  if module_id in tree.paths else None)
        result = (declared_dependencies(document) if isinstance(document, ArchitectureView)
                  and document.dependency_sources is not None else declared_dependencies(document, source))
        for loc in result["diagnostics"] + [loc for edge in result["edges"] for loc in edge["sources"]]:
            if "file" in loc:
                identity = str((tree.project_root / loc["file"]).resolve())
                if identity in tree.digests:
                    loc["sha256"] = tree.digests[identity]
            if "value" not in loc and "file" in loc:
                loc["value"] = original_value(loc)
        diagnostics.extend(result["diagnostics"])
        for edge in result["edges"]:
            entry = combined.setdefault((edge["从"], edge["到"]), {"从": edge["从"], "到": edge["到"], "sources": []})
            for field in ("说明", "原声明"):
                if field in edge and field not in entry:
                    entry[field] = copy.deepcopy(edge[field])
            for loc in edge["sources"]:
                # Index rebasing uses the hydrated logical declaration, while
                # public value remains exactly the original physical fragment.
                # This temporary field never survives sidecar publication.
                if _with_view_values:
                    loc["_view_value"] = copy.deepcopy(pointer_value(document, loc.get("view_pointer", loc["pointer"])))
                if loc not in entry["sources"]:
                    entry["sources"].append(loc)
    return {"edges": [combined[key] for key in sorted(combined, key=lambda pair: tuple((type(v).__name__, str(v)) for v in pair))],
            "diagnostics": diagnostics}


def dependency_edges(tree: ModuleTree) -> list[tuple[str, str]]:
    """Strict explicit dependencies; containment never implies a dependency."""
    result = dependency_declarations(tree)
    invalid = [item for item in result["diagnostics"] if item["code"] != "descriptive_reference"]
    if invalid:
        raise _invalid("; ".join(item["message"] + ": " + item["pointer"] for item in invalid))
    if any(not isinstance(edge[key], str) for edge in result["edges"] for key in ("从", "到")):
        raise _invalid("递归模块依赖编号必须是非空字符串")
    return [(edge["从"], edge["到"]) for edge in result["edges"]]
