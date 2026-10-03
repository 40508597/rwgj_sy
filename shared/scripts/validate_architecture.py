#!/usr/bin/env python3
"""Validate a task-architecture JSON file.

This tool is intentionally lightweight: it uses only the Python standard
library, reads files only, and reports concise errors/warnings for an agent to
write back into 验证证据.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

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
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
}


def load_schema() -> tuple[dict[str, Any] | None, str | None]:
    skill_root = Path(__file__).resolve().parents[1]
    schema_path = skill_root / "assets" / "schema" / "architecture.schema.json"
    if not schema_path.exists():
        return None, f"schema 文件不存在，已跳过轻量 schema 校验: {schema_path}"
    try:
        schema = _archlib.load_architecture_json(schema_path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"schema 无法读取，已跳过轻量 schema 校验: {exc}"
    if not isinstance(schema, dict):
        return None, "schema 根节点不是对象，已跳过轻量 schema 校验"
    return schema, None


# 当 schema 不可用时的兜底常量（与 schema 保持同名同义，schema 改了这里也要同步）.
# 与 check_placeholders 的 FALLBACK_* 思路一致：0 依赖环境仍能落地校验。
FALLBACK_REQUIRED_TOP_KEYS = [
    "项目", "运行形态", "功能树", "专业能力索引", "入口", "模块拓扑", "模块树",
    "模块详情", "页面拓扑", "数据拓扑", "交付物", "系统集成", "接口契约", "实现清单",
    "完整细节", "测试责任矩阵", "验证证据", "架构切片", "上下文恢复点", "未决问题", "变更记录",
]
FALLBACK_ENTRY_REQUIRED = ["用户入口", "接口入口", "事件入口", "系统入口"]
FALLBACK_ENTRY_OPTIONAL = ["命令入口", "资源入口"]
# 模块详情 14 项底线子字段 / 上下文恢复点 7 项 core 子字段（与 check_placeholders 同源兜底）
FALLBACK_MODULE_DETAIL_SUBFIELDS = [
    "职责", "非职责", "所属功能树节点", "上游依赖", "下游消费者", "内部结构",
    "状态机", "数据读写责任", "错误边界", "配置", "安全", "日志审计", "性能", "测试责任",
]
FALLBACK_RECOVERY_CORE_SUBFIELDS = [
    "当前任务", "当前阶段", "继续位置", "下一步", "已触碰文件", "用户明确约束", "剩余风险",
]


def derive_required_top_keys(schema: dict[str, Any] | None) -> list[str]:
    """顶层 required 优先 schema.required，回退兜底常量。"""
    if schema and isinstance(schema.get("required"), list):
        return [str(k) for k in schema["required"]]
    return list(FALLBACK_REQUIRED_TOP_KEYS)


def derive_entry_keys(schema: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """从 schema 入口子对象推出 (required_entry_keys, optional_entry_keys)。"""
    if schema:
        entry_spec = schema.get("properties", {}).get("入口", {})
        if isinstance(entry_spec, dict):
            required = [str(k) for k in entry_spec.get("required", [])]
            props = entry_spec.get("properties", {})
            optional = [k for k in props if k not in required] if isinstance(props, dict) else []
            if required:
                return required, optional
    return list(FALLBACK_ENTRY_REQUIRED), list(FALLBACK_ENTRY_OPTIONAL)


def derive_module_detail_subfields(schema: dict[str, Any] | None) -> list[str]:
    """模块详情 14 项底线子字段：优先 schema x-required-subfields，回退兜底。"""
    if schema:
        md_spec = schema.get("properties", {}).get("模块详情", {})
        if isinstance(md_spec, dict):
            sub = md_spec.get("x-required-subfields")
            if isinstance(sub, list) and sub:
                return [str(s) for s in sub]
    return list(FALLBACK_MODULE_DETAIL_SUBFIELDS)


def derive_recovery_core_subfields(schema: dict[str, Any] | None) -> list[str]:
    """上下文恢复点 core 子字段：优先 schema properties 标 x-importance=core，回退兜底。"""
    if schema:
        rec_spec = schema.get("properties", {}).get("上下文恢复点", {})
        if isinstance(rec_spec, dict):
            props = rec_spec.get("properties", {})
            if isinstance(props, dict):
                core = [k for k, v in props.items()
                        if isinstance(v, dict) and v.get("x-importance") == "core"]
                if core:
                    return core
    return list(FALLBACK_RECOVERY_CORE_SUBFIELDS)


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
    for node in nodes:
        if not isinstance(node, dict):
            continue
        module_id = node.get("编号")
        if isinstance(module_id, str):
            found.add(module_id)
        found.update(_module_ids_from_tree(node.get("子模块", [])))
    return found


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
    def meaningful(value: Any) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, dict):
            return any(meaningful(v) for v in value.values())
        if isinstance(value, list):
            return any(meaningful(v) for v in value)
        return False
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


def validate_architecture(data: dict[str, Any], root: Path, stage: str = "full") -> tuple[list[str], list[str]]:
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
        edges = topology.get("依赖图", [])
        if not isinstance(edges, list):
            errors.append("模块拓扑.依赖图 必须是数组")
            edges = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            src = edge.get("从")
            dst = edge.get("到")
            if isinstance(src, str) and src not in topology_ids:
                warnings.append(f"依赖图来源模块未登记: {src}")
            if isinstance(dst, str) and dst not in topology_ids:
                warnings.append(f"依赖图目标模块未登记: {dst}")
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

    data, io_error, io_exit = _archlib.run_with_io_errors(
        lambda: _archlib.load_architecture_json(args.architecture)
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

    errors, warnings = validate_architecture(
        data, _archlib.project_root_for_architecture(args.architecture.resolve()), stage=args.stage
    )
    if args.json:
        print(json.dumps({"错误": errors, "警告": warnings}, ensure_ascii=False, indent=2))
    else:
        _archlib.emit_validation_text("架构校验", errors, warnings)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
