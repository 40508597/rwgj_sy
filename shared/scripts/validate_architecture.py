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


def validate_schema_subset(data: Any, schema: dict[str, Any], path: str = "根节点") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _type_matches(data, expected_type):
        errors.append(f"{path} 类型应为 {expected_type}")
        return errors

    if not isinstance(data, dict):
        return errors

    for key in schema.get("required", []):
        if isinstance(key, str) and key not in data:
            errors.append(f"{path} 缺少 schema 必需键: {key}")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return errors

    for key, child_schema in properties.items():
        if key not in data or not isinstance(child_schema, dict):
            continue
        errors.extend(validate_schema_subset(data[key], child_schema, f"{path}.{key}"))

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

    返回 (errors, warnings)：类型错误归 warning（结构问题但非阻塞），
    全空归 error（与门禁语义一致，必须至少记录 未验证项）。
    """
    errors: list[str] = []
    warnings: list[str] = []
    ve = data.get("验证证据")
    if not isinstance(ve, dict) or not ve:
        return errors, warnings  # 缺失由顶层 required/占位符检测覆盖
    required_classes = ["自动化测试", "架构校验", "浏览器验收", "截图", "手动检查", "未验证项"]
    for k in required_classes:
        if k in ve and not isinstance(ve[k], list):
            warnings.append(f"验证证据.{k} 必须是数组")
    has_any = any(isinstance(ve.get(k), list) and len(ve.get(k)) > 0 for k in required_classes)
    if not has_any:
        errors.append("验证证据 六类全空，至少记录 未验证项 或一项已执行证据")
    return errors, warnings


def _check_recovery_point(data: dict[str, Any], core_subfields: list[str]) -> list[str]:
    """校验14：上下文恢复点完整。schema 标 core 的 7 项子字段必须存在。
    存在性校验；值占位符或空白由 check_placeholders 覆盖，不重复验。
    """
    issues: list[str] = []
    recovery = data.get("上下文恢复点")
    if not isinstance(recovery, dict) or not recovery:
        return issues
    for sub in core_subfields:
        if sub not in recovery:
            issues.append(f"上下文恢复点.{sub} 缺失（核心子字段）")
    return issues


def _check_module_detail_fields(data: dict[str, Any], required_subs: list[str]) -> list[str]:
    """校验19：每个模块详情对象必须含 14 项底线子字段。"""
    issues: list[str] = []
    details = data.get("模块详情")
    if not isinstance(details, dict) or not details:
        return issues
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


def _check_slice_sync(data: dict[str, Any], root: Path) -> list[str]:
    """校验21：架构切片清单与磁盘 architecture/ 目录双向对账。

    - 切片清单中列出但磁盘上不存在的 → 未生成切片（warning）
    - 磁盘 architecture/ 下实际切片文件但未登记到 切片清单 的 → 未登记切片（warning）
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
        actual = {str(p.relative_to(root)).replace("\\", "/")
                  for p in arch_dir.rglob("*.json") if p.name != "index.json"}
        actual_lower = {p for p in actual}
        undeclared = actual_lower - declared_paths - {"architecture/index.json"}
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
        errors.extend(validate_schema_subset(data, schema))

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
        for edge in topology.get("依赖图", []):
            if not isinstance(edge, dict):
                continue
            src = edge.get("从")
            dst = edge.get("到")
            if isinstance(src, str) and src not in topology_ids:
                warnings.append(f"依赖图来源模块未登记: {src}")
            if isinstance(dst, str) and dst not in topology_ids:
                warnings.append(f"依赖图目标模块未登记: {dst}")

    implementation = data.get("实现清单", {})
    if isinstance(implementation, dict):
        for module_id, item in implementation.items():
            if module_id not in topology_ids:
                warnings.append(f"实现清单模块未登记到模块拓扑.节点: {module_id}")
            if not isinstance(item, dict):
                continue
            for file_item in (item.get("文件列表") or item.get("文件") or []):
                if not isinstance(file_item, dict):
                    continue
                path_value = file_item.get("路径")
                if isinstance(path_value, str) and path_value and not (root / path_value).exists():
                    warnings.append(f"实现清单文件不存在: {path_value}")
    elif implementation is not None:
        errors.append("实现清单 必须是对象")

    # 校验13 验证证据完整（全空为 error，类型问题为 warning）
    ev_errors, ev_warnings = _check_verification_evidence(data)
    errors.extend(ev_errors)
    warnings.extend(ev_warnings)
    # 校验14 上下文恢复点完整
    warnings.extend(_check_recovery_point(data, derive_recovery_core_subfields(schema)))
    # 校验19 模块详情字段完整性
    warnings.extend(_check_module_detail_fields(data, derive_module_detail_subfields(schema)))
    # 校验21 架构切片同步
    warnings.extend(_check_slice_sync(data, root))

    return errors, warnings




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
        print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit

    if not isinstance(data, dict):
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
