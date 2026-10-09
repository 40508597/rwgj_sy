#!/usr/bin/env python3
"""Validate a task-architecture JSON file.

This tool is intentionally lightweight: it uses only the Python standard
library, reads files only, and reports concise errors/warnings for an agent to
write back into 验证证据.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402
import _capabilitylib  # noqa: E402

_archlib.configure_utf8_stdout()


# 骨架阶段允许缺失的键（逐块设计阶段才填充）
SKELETON_OPTIONAL_KEYS = [
    "模块详情",
    "接口契约",
    "实现清单",
    "完整细节",
    "测试责任矩阵",
]

# FORBIDDEN_ENTRY_KEYS 是 schema 没有覆盖的旧入口名，保留硬编码兜底.
# 入口 required/optional 改由 schema 推导（架构 schema 已声明入口.properties
# 与入口.required: 用户入口/接口入口/事件入口/系统入口）.
FORBIDDEN_ENTRY_KEYS = [
    "页面路由",
    "API路由",
    "静态资源路由",
    "CLI命令树",
    "后台任务",
    "桌面窗口",
    "桌面菜单栏",
    "托盘入口",
    "本地协议",
    "文件关联",
    "系统通知",
    "WebSocket事件",
]

TYPE_MAP = {
    "object": dict,
    "array": list,
    "boolean": bool,
    "string": str,
    "number": (int, float),
    "integer": int,
}

from _architecture_core import (
    FALLBACK_REQUIRED_TOP_KEYS,
    FALLBACK_ENTRY_REQUIRED,
    FALLBACK_ENTRY_OPTIONAL,
    FALLBACK_MODULE_DETAIL_SUBFIELDS,
    FALLBACK_RECOVERY_CORE_SUBFIELDS,
    load_schema,
    derive_required_top_keys,
    derive_entry_keys,
    derive_module_detail_subfields,
    derive_recovery_core_subfields,
    meaningful,
    declared_dependencies
)


def _type_matches(value: Any, expected: Any) -> bool:
    # 支持类型数组，如 ["array", "object"]
    if isinstance(expected, list):
        return any(_type_matches(value, t) for t in expected)
    if not isinstance(expected, str):
        return True
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    expected_type = TYPE_MAP.get(expected)
    return True if expected_type is None else isinstance(value, expected_type)


def validate_schema_subset(data: Any, schema: dict[str, Any], path: str = "根节点",
                           root_schema: dict[str, Any] | None = None,
                           stage: str = "full") -> list[str]:
    errors: list[str] = []
    root_schema = schema if root_schema is None else root_schema
    reference = schema.get("$ref")
    if isinstance(reference, str):
        target: Any = root_schema
        if not reference.startswith("#/"):
            return [f"{path} 不支持的 schema 引用: {reference}"]
        for key in reference[2:].split("/"):
            key = key.replace("~1", "/").replace("~0", "~")
            target = target.get(key) if isinstance(target, dict) else None
        if not isinstance(target, dict):
            return [f"{path} schema 引用不存在: {reference}"]
        return validate_schema_subset(data, target, path, root_schema, stage)
    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        if any(isinstance(option, dict) and not validate_schema_subset(data, option, path, root_schema, stage)
               for option in alternatives):
            return []
        return [f"{path} 不符合任一允许结构"]
    expected_type = schema.get("type")
    if isinstance(expected_type, (str, list)) and not _type_matches(data, expected_type):
        errors.append(f"{path} 类型应为 {expected_type}")
        return errors

    if isinstance(data, list):
        minimum = schema.get("x-full-min-items", 0) if stage == "full" else 0
        if len(data) < minimum:
            errors.append(f"{path} 完成模式至少需要 {minimum} 项")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(data):
                errors.extend(validate_schema_subset(item, item_schema, f"{path}.{index}", root_schema, stage))
        return errors
    string_minimum = max(schema.get("minLength", 0), schema.get("x-full-min-length", 0) if stage == "full" else 0)
    if isinstance(data, str) and string_minimum > len(data.strip()):
        errors.append(f"{path} 必须是非空字符串")
    if not isinstance(data, dict):
        return errors

    minimum = schema.get("x-full-min-properties", 0) if stage == "full" else 0
    if len(data) < minimum:
        errors.append(f"{path} 完成模式至少需要 {minimum} 项")

    required_fields = list(schema.get("required", []))
    if stage == "full":
        required_fields.extend(schema.get("x-full-required", []))
    for key in required_fields:
        if isinstance(key, str) and key not in data:
            errors.append(f"{path} 缺少 schema 必需键: {key}")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return errors

    for key, child_schema in properties.items():
        if key not in data or not isinstance(child_schema, dict):
            continue
        errors.extend(validate_schema_subset(data[key], child_schema, f"{path}.{key}", root_schema, stage))

    extra_schema = schema.get("additionalProperties")
    for key in data.keys() - properties.keys():
        if isinstance(extra_schema, dict):
            errors.extend(validate_schema_subset(data[key], extra_schema, f"{path}.{key}", root_schema, stage))
        elif extra_schema is False:
            errors.append(f"{path} 未声明的字段: {key}")

    return errors


def _module_ids_from_tree(nodes: Any) -> set[str]:
    found: set[str] = set()
    if not isinstance(nodes, list):
        return found
    pending = list(nodes)
    while pending:
        node = pending.pop()
        if not isinstance(node, dict):
            continue
        module_id = node.get("编号")
        if isinstance(module_id, str):
            found.add(module_id)
        if isinstance(node.get("子模块"), list):
            pending.extend(node["子模块"])
    return found


def _check_module_directory(data: dict[str, Any], root: Path, stage: str,
                            source_paths: set[Path] | None = None) -> list[str]:
    """Check the hydrated ownership tree independently of the dependency graph.

    The loader has already traversed every route and verified file ownership.
    This check reconciles that derived catalog with the ordinary architecture
    sections, without opening the module JSON files again.
    """
    if "模块路由" not in data:
        return []
    issues: list[str] = []
    directory = data.get("模块目录")
    if not isinstance(directory, list) or not directory:
        return ["模块路由尚未生成有效模块目录，必须递归加载全部模块架构"]
    records: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    from scan_code_drift import _safe_path
    for index, record in enumerate(directory):
        if not isinstance(record, dict) or not isinstance(record.get("编号"), str) or not record["编号"].strip():
            issues.append(f"模块目录[{index}] 必须提供非空模块编号")
            continue
        module_id = record["编号"]
        if module_id in records:
            issues.append(f"模块目录编号重复: {module_id}")
        records[module_id] = record
        try:
            source = _safe_path(root.resolve(), record.get("路径"), f"模块目录.{module_id}.路径")
            folder = _safe_path(root.resolve(), record.get("目录"), f"模块目录.{module_id}.目录")
            expected_folder = root.resolve() if record.get("父模块") is None else source.parent.resolve()
            if expected_folder != folder.resolve():
                issues.append(f"模块目录路径与目录不匹配: {module_id}")
            identity = os.path.normcase(str(source.resolve()))
            if identity in paths:
                issues.append(f"模块目录架构路径重复: {record['路径']}")
            paths.add(identity)
            if not source.is_file():
                issues.append(f"模块目录架构文件不存在或不是文件: {record['路径']}")
        except (OSError, ValueError) as exc:
            issues.append(str(exc))
    ids = set(records)
    route = data.get("模块路由")
    root_id = route.get("编号") if isinstance(route, dict) else None
    roots = [module_id for module_id, record in records.items() if record.get("父模块") is None]
    if roots != [root_id]:
        issues.append("模块目录必须有且仅有与根模块路由编号一致的根模块")
    for module_id, record in records.items():
        parent = record.get("父模块")
        if parent is not None and not isinstance(parent, str):
            issues.append(f"模块目录.{module_id}.父模块 必须是模块编号或 null")
            continue
        children = record.get("子模块")
        if not isinstance(children, list) or any(not isinstance(child, str) for child in children):
            issues.append(f"模块目录.{module_id}.子模块 必须是模块编号数组")
            continue
        if len(set(children)) != len(children):
            issues.append(f"模块目录子模块重复: {module_id}")
        for child in children:
            if child not in records or records[child].get("父模块") != module_id:
                issues.append(f"模块目录父子归属不匹配: {module_id} -> {child}")
        if parent is not None:
            parent_children = records.get(parent, {}).get("子模块")
            if not isinstance(parent_children, list) or module_id not in parent_children:
                issues.append(f"模块目录父模块未正确登记: {module_id}")
    topology = data.get("模块拓扑", {})
    nodes = topology.get("节点", []) if isinstance(topology, dict) else []
    topology_ids = [node.get("编号") for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []
    if len(topology_ids) != len(set(value for value in topology_ids if isinstance(value, str))):
        issues.append("模块拓扑.节点 编号缺失或重复")
    topology_set = {value for value in topology_ids if isinstance(value, str)}
    for module_id in sorted(ids - topology_set):
        issues.append(f"模块目录模块未登记到模块拓扑.节点: {module_id}")
    for module_id in sorted(topology_set - ids):
        issues.append(f"模块拓扑节点没有模块路由归属: {module_id}")
    for module_id in sorted(_module_ids_from_tree(data.get("模块树")) - ids):
        issues.append(f"模块树节点没有模块路由归属: {module_id}")
    for field in ("模块详情", "实现清单"):
        values = data.get(field)
        if not isinstance(values, dict):
            continue  # Existing schema/type checks report this.
        for module_id in sorted(set(values) - ids):
            issues.append(f"{field}模块没有模块路由归属: {module_id}")
        if stage == "full":
            for module_id in sorted(ids - set(values)):
                issues.append(f"模块目录模块缺少{field}: {module_id}")
        for module_id, detail in values.items():
            for alias in ("模块编号", "模块号"):
                if isinstance(detail, dict) and alias in detail and (
                        not isinstance(detail[alias], str) or detail[alias] != module_id):
                    issues.append(f"{field}.{module_id}.{alias} 与模块归属不一致")
    from _module_tree import ModuleTree, check_hydrated_module_files, dependency_edges, unregistered_architectures
    tree = ModuleTree(root, root / records[root_id]["路径"] if root_id in records else root / "architecture.json")
    tree.merged = data
    tree.paths = {module_id: root / record["路径"] for module_id, record in records.items()
                  if isinstance(record.get("路径"), str)}
    try:
        dependencies = dependency_edges(tree)
    except _archlib.ArchitectureInputError as exc:
        issues.append(str(exc))
    else:
        unknown = sorted({module_id for edge in dependencies for module_id in edge} - ids)
        if unknown:
            issues.append("依赖图引用未登记模块: " + ", ".join(unknown))
        cycle_edges = [{"从": source, "到": target} for source, target in dependencies]
        if stage == "skeleton":
            cycle_edges = [edge for edge in cycle_edges
                           if not any(edge[key].startswith(("__待", "__示例", "__注释__")) for key in ("从", "到"))]
        cycle = dependency_cycle(cycle_edges)
        if cycle:
            issues.append("模块依赖存在有向环: " + " -> ".join(cycle))
    allowed_paths = set(source_paths or ())
    allowed_paths.add(root / "architecture.json")
    for relative in unregistered_architectures(tree, allowed_paths=allowed_paths):
        issues.append(f"模块架构文件未登记到模块路由: {relative}")
    if stage == "full":
        issues.extend(check_hydrated_module_files(data, root))
    return issues


def _check_verification_evidence(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """校验13：验证证据完整。六类（自动化测试/架构校验/浏览器验收/截图/手动检查/未验证项）
    必须每项是数组；六类全空且 未验证项 也空 → error（声称完成但无证据，
    与 validation-checklist.md 验证证据门禁对齐：完成项必须有命令/截图/手检/未验证项记录）。
    缺失整段或不是对象由顶层 required 校验覆盖。

    返回 (errors, warnings)：错误类型、缺失、全空或全空记录归 error。
    """
    errors: list[str] = []
    warnings: list[str] = []
    ve = data.get("验证证据")
    if not isinstance(ve, dict) or not ve:
        return ["验证证据 缺失、不是对象或为空"], warnings
    required_classes = ["自动化测试", "架构校验", "浏览器验收", "截图", "手动检查", "未验证项"]
    for k in required_classes:
        if k in ve and not isinstance(ve[k], list):
            errors.append(f"验证证据.{k} 必须是数组")
    has_any = any(isinstance(ve.get(k), list) and any(meaningful(v) for v in ve[k])
                  for k in required_classes)
    if not has_any:
        errors.append("验证证据 六类全空，至少记录 未验证项 或一项已执行证据")
    return errors, warnings


def _check_recovery_point(data: dict[str, Any], core_subfields: list[str]) -> list[str]:
    """校验14：上下文恢复点完整。schema 标 core 的 7 项子字段必须存在。
    当前任务/阶段/继续位置/下一步须有恢复信息；约束/触碰文件/风险可合理为空数组。
    """
    issues: list[str] = []
    recovery = data.get("上下文恢复点")
    if not isinstance(recovery, dict):
        return ["上下文恢复点 必须是对象"]
    for sub in core_subfields:
        if sub not in recovery:
            issues.append(f"上下文恢复点.{sub} 缺失（核心子字段）")
        elif sub in {"当前任务", "当前阶段", "继续位置", "下一步"}:
            value = recovery[sub]
            valid = isinstance(value, str) and bool(value.strip())
            valid = valid or (isinstance(value, list) and bool(value)
                              and all(isinstance(v, str) and bool(v.strip()) for v in value))
            if not valid:
                issues.append(f"上下文恢复点.{sub} 必须有非空恢复信息")
    return issues


def _check_module_detail_fields(data: dict[str, Any], required_subs: list[str]) -> list[str]:
    """校验19：每个模块详情对象必须含 14 项底线子字段。"""
    issues: list[str] = []
    details = data.get("模块详情")
    if not isinstance(details, dict) or not details:
        return ["模块详情 缺失、不是对象或为空"]
    for module_id, detail in details.items():
        if module_id.startswith("__"):
            continue  # 示例 key 由 check_placeholders 覆盖
        if not isinstance(detail, dict):
            issues.append(f"模块详情.{module_id} 必须是对象")
            continue
        for sub in required_subs:
            if sub not in detail:
                issues.append(f"模块详情.{module_id}.{sub} 缺失（模块详情底线字段）")
    return issues


def completion_issues(data: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    """完成产物底线，供 F 与 B 门禁共用；不把无事件/无页面当作缺陷。"""
    if schema is None:
        schema, _ = load_schema()
    issues: list[str] = []
    if schema:
        core_schema = {"type": "object", "$defs": schema.get("$defs", {}),
                       "properties": {k: v for k, v in schema.get("properties", {}).items()
                                      if v.get("x-importance") == "core"}}
        issues.extend(validate_schema_subset(data, core_schema))
    else:
        for key in ("功能树", "模块树", "模块详情", "实现清单", "测试责任矩阵"):
            if not data.get(key):
                issues.append(f"{key} 完成模式不可为空")
        project = data.get("项目", {})
        for key in ("名称", "类型"):
            value = project.get(key) if isinstance(project, dict) else None
            if not isinstance(value, str) or not value.strip():
                issues.append(f"项目.{key} 必须是非空字符串")
        topology = data.get("模块拓扑", {})
        if not isinstance(topology, dict) or not topology.get("节点"):
            issues.append("模块拓扑.节点 完成模式不可为空")
    evidence_errors, _ = _check_verification_evidence(data)
    issues.extend(evidence_errors)
    issues.extend(_check_recovery_point(data, derive_recovery_core_subfields(schema)))
    issues.extend(_check_module_detail_fields(data, derive_module_detail_subfields(schema)))
    topology = data.get("模块拓扑", {})
    details = data.get("模块详情", {})
    if isinstance(topology, dict) and isinstance(details, dict):
        for node in topology.get("节点", []) if isinstance(topology.get("节点"), list) else []:
            if isinstance(node, dict) and isinstance(node.get("编号"), str) and node["编号"] not in details:
                issues.append(f"模块拓扑节点缺少模块详情: {node['编号']}")
    return list(dict.fromkeys(issues))


def dependency_cycle(edges: list[Any]) -> list[str]:
    """返回一个有向环（含起止节点），迭代遍历不受 Python 递归深度限制。"""
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src, dst = edge.get("从"), edge.get("到")
        if isinstance(src, str) and isinstance(dst, str):
            adjacency.setdefault(src, []).append(dst)
            adjacency.setdefault(dst, [])
    state: dict[str, int] = {}
    for start in adjacency:
        if state.get(start):
            continue
        active = [start]
        positions = {start: 0}
        stack = [(start, iter(adjacency[start]))]
        state[start] = 1
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                stack.pop()
                state[node] = 2
                positions.pop(node)
                active.pop()
            elif state.get(child) == 1:
                return active[positions[child]:] + [child]
            elif not state.get(child):
                positions[child] = len(active)
                active.append(child)
                state[child] = 1
                stack.append((child, iter(adjacency[child])))
    return []


def _check_slice_sync(data: dict[str, Any], root: Path) -> list[str]:
    """校验21：架构切片清单与磁盘 architecture/ 目录双向对账。

    - 切片清单中列出但磁盘上不存在的 → 未生成切片（warning）
    - 磁盘 architecture/ 下实际切片文件但未登记到 切片清单 的 → 未登记切片（warning）
    - 标准进度状态 architecture/_state.json 和独立质量目录 architecture/quality/
      是辅助产物（json-sharding.md / universal-quality.md），不属于业务架构切片。
      仅排除这些明确角色；其他目录、其他状态名或模块 index.json 仍需登记。
    若启用=false 则跳过。
    """
    issues: list[str] = []
    slicing = data.get("架构切片", {})
    if not isinstance(slicing, dict):
        return issues
    if slicing.get("启用") is False:
        return issues
    slice_list = slicing.get("切片清单", [])
    declared_paths: set[str] = set()
    if isinstance(slice_list, list):
        for item in slice_list:
            if isinstance(item, dict):
                p = item.get("路径")
                if isinstance(p, str):
                    declared_paths.add(p.replace("\\", "/").lstrip("./"))
        # 检查声明的切片在磁盘是否存在
        arch_root = root / "architecture"
        for p in declared_paths:
            if not (root / p).exists() and not (arch_root.parent / p).exists():
                issues.append(f"架构切片清单中 {p} 在磁盘不存在（未生成）")
    # 反向：磁盘 architecture/ 下实际 .json 切片但未登记
    arch_dir = root / "architecture"
    if arch_dir.is_dir():
        actual: set[str] = set()
        for path in arch_dir.rglob("*.json"):
            relative = path.relative_to(arch_dir).as_posix()
            # Match the host's documented path identity: Windows reserved paths
            # are case-insensitive; POSIX paths retain their case distinction.
            identity = relative.casefold() if sys.platform == "win32" else relative
            if identity in {"index.json", "_state.json"} or identity.startswith("quality/"):
                continue
            actual.add(path.relative_to(root).as_posix())
        undeclared = actual - declared_paths
        for p in sorted(undeclared):
            issues.append(f"磁盘切片 {p} 未登记到 架构切片.切片清单")
    return issues


def validate_architecture(data: dict[str, Any], root: Path, stage: str = "full", *,
                          source_paths: set[Path] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    schema, schema_warning = load_schema()
    if schema_warning:
        warnings.append(schema_warning)
    elif schema is not None:
        if stage == "skeleton":
            # 骨架阶段：从 schema required 中移除可选键再校验
            schema = dict(schema)
            schema["required"] = [k for k in schema.get("required", []) if k not in SKELETON_OPTIONAL_KEYS]
        errors.extend(validate_schema_subset(data, schema, stage=stage))

    required_keys = derive_required_top_keys(schema)
    if stage == "skeleton":
        required_keys = [k for k in required_keys if k not in SKELETON_OPTIONAL_KEYS]
    for key in required_keys:
        if key not in data:
            errors.append(f"缺少顶层主键: {key}")

    # 专业能力声明的结构与引用独立于质量采集规则，不能被其它成功检查掩盖。
    capability_errors, capability_warnings = _capabilitylib.validate_capability_index(data)
    errors.extend(capability_errors)
    warnings.extend(capability_warnings)
    errors.extend(_check_module_directory(data, root, stage, source_paths))

    entry_required, entry_optional = derive_entry_keys(schema)
    entry = data.get("入口")
    if not isinstance(entry, dict):
        errors.append("入口 必须是对象")
    else:
        for key in entry_required:
            if key not in entry:
                errors.append(f"入口 缺少通用入口主键: {key}")
            elif not isinstance(entry[key], list):
                errors.append(f"入口.{key} 必须是数组")
        for key in entry_optional:
            if key in entry and not isinstance(entry[key], list):
                errors.append(f"入口.{key} 必须是数组")
        for key in FORBIDDEN_ENTRY_KEYS:
            if key in entry:
                errors.append(f"入口 不得使用旧入口主键: {key}")

    topology = data.get("模块拓扑", {})
    topology_nodes = topology.get("节点", []) if isinstance(topology, dict) else []
    if not isinstance(topology_nodes, list):
        errors.append("模块拓扑.节点 必须是数组")
        topology_nodes = []
    topology_ids = {
        node.get("编号")
        for node in topology_nodes
        if isinstance(node, dict) and isinstance(node.get("编号"), str)
    }

    details = data.get("模块详情", {})
    if isinstance(details, dict):
        for module_id in topology_ids:
            if module_id not in details:
                warnings.append(f"模块拓扑节点缺少模块详情: {module_id}")
    else:
        errors.append("模块详情 必须是对象")

    tree_ids = _module_ids_from_tree(data.get("模块树", []))
    for module_id in tree_ids:
        if module_id not in topology_ids:
            warnings.append(f"模块树节点未登记到模块拓扑.节点: {module_id}")

    if isinstance(topology, dict):
        declared = declared_dependencies(data)
        errors.extend(item["message"] + ": " + item["pointer"] for item in declared["diagnostics"]
                      if item["code"] != "descriptive_reference")
        edges = declared["edges"]
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            src = edge.get("从")
            dst = edge.get("到")
            if isinstance(src, str) and src not in topology_ids:
                (errors if "模块路由" in data else warnings).append(f"依赖图来源模块未登记: {src}")
            if isinstance(dst, str) and dst not in topology_ids:
                (errors if "模块路由" in data else warnings).append(f"依赖图目标模块未登记: {dst}")
        cycle_edges = edges
        if stage == "skeleton":
            cycle_edges = [edge for edge in edges if isinstance(edge, dict)
                           and not any(isinstance(edge.get(key), str)
                                       and edge[key].startswith(("__待", "__示例", "__注释__"))
                                       for key in ("从", "到"))]
        cycle = dependency_cycle(cycle_edges)
        if cycle:
            errors.append("模块依赖存在有向环: " + " -> ".join(cycle))

    implementation = data.get("实现清单", {})
    if isinstance(implementation, dict):
        for module_id, item in implementation.items():
            if module_id not in topology_ids:
                warnings.append(f"实现清单模块未登记到模块拓扑.节点: {module_id}")
            if not isinstance(item, dict):
                continue
            files: list[Any] = []
            for field in ("文件列表", "文件"):
                entries = item.get(field, [])
                if not isinstance(entries, list):
                    errors.append(f"实现清单.{module_id}.{field} 必须是数组")
                else:
                    files.extend(entries)
            for file_item in files:
                path_value = file_item if isinstance(file_item, str) else file_item.get("路径") if isinstance(file_item, dict) else None
                if not isinstance(path_value, str) or not path_value.strip():
                    errors.append(f"实现清单.{module_id} 文件必须是非空路径字符串或含路径的对象")
                    continue
                if isinstance(path_value, str) and path_value and not (root / path_value).exists():
                    warnings.append(f"实现清单文件不存在: {path_value}")
    elif implementation is not None:
        errors.append("实现清单 必须是对象")

    # 完成阶段统一检查 schema core 字段、验证证据、恢复点与模块详情底线。
    if stage == "full":
        errors.extend(completion_issues(data, schema))
    # 校验21 架构切片同步
    warnings.extend(_check_slice_sync(data, root))

    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))




def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate task architecture JSON.")
    parser.add_argument("architecture", type=Path, help="Path to architecture.json")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--stage", choices=["full", "skeleton"], default="full",
                        help="Validation stage: 'skeleton' tolerates missing detail keys (模块详情/接口契约/实现清单/完整细节/测试责任矩阵)")
    args = parser.parse_args(argv)

    source_paths: set[Path] = set()
    data, io_error, io_exit = _archlib.run_with_io_errors(
        lambda: _archlib.load_architecture_json(args.architecture, source_paths)
    )
    if io_error is not None:
        if args.json:
            print(json.dumps({"status": "unknown", "错误": [io_error], "警告": []}, ensure_ascii=False))
        else:
            print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit

    if not isinstance(data, dict):
        if args.json:
            print(json.dumps({"status": "unknown", "错误": ["architecture 根节点必须是对象"], "警告": []}, ensure_ascii=False))
        else:
            print("ERROR: architecture 根节点必须是对象", file=sys.stderr)
        return 2

    validation, io_error, io_exit = _archlib.run_with_io_errors(lambda: validate_architecture(
        data, _archlib.project_root_for_architecture(args.architecture.resolve()), stage=args.stage,
        source_paths=source_paths,
    ))
    if io_error is not None:
        if args.json:
            print(json.dumps({"status": "unknown", "错误": [io_error], "警告": []}, ensure_ascii=False))
        else:
            print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit
    errors, warnings = validation
    if args.json:
        print(json.dumps({"错误": errors, "警告": warnings}, ensure_ascii=False, indent=2))
    else:
        _archlib.emit_validation_text("架构校验", errors, warnings)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
