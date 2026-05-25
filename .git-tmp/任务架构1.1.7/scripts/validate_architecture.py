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


REQUIRED_TOP_KEYS = [
    "项目",
    "运行形态",
    "功能树",
    "专业能力索引",
    "入口",
    "模块拓扑",
    "模块树",
    "模块详情",
    "页面拓扑",
    "数据拓扑",
    "交付物",
    "系统集成",
    "接口契约",
    "实现清单",
    "完整细节",
    "测试责任矩阵",
    "验证证据",
    "架构切片",
    "上下文恢复点",
    "未决问题",
    "变更记录",
]

ENTRY_KEYS = ["用户入口", "接口入口", "命令入口", "事件入口", "系统入口", "资源入口"]

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


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_schema(architecture_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    skill_root = Path(__file__).resolve().parents[1]
    schema_path = skill_root / "assets" / "schema" / "architecture.schema.json"
    if not schema_path.exists():
        return None, f"schema 文件不存在，已跳过轻量 schema 校验: {schema_path}"
    try:
        schema = load_json(schema_path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"schema 无法读取，已跳过轻量 schema 校验: {exc}"
    if not isinstance(schema, dict):
        return None, "schema 根节点不是对象，已跳过轻量 schema 校验"
    return schema, None


def _type_matches(value: Any, expected: str) -> bool:
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


def validate_architecture(data: dict[str, Any], root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    schema, schema_warning = load_schema(root / "architecture.json")
    if schema_warning:
        warnings.append(schema_warning)
    elif schema is not None:
        errors.extend(validate_schema_subset(data, schema))

    for key in REQUIRED_TOP_KEYS:
        if key not in data:
            errors.append(f"缺少顶层主键: {key}")

    entry = data.get("入口")
    if not isinstance(entry, dict):
        errors.append("入口 必须是对象")
    else:
        for key in ENTRY_KEYS:
            if key not in entry:
                errors.append(f"入口 缺少通用入口主键: {key}")
            elif not isinstance(entry[key], list):
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
            for file_item in item.get("文件列表", []):
                if not isinstance(file_item, dict):
                    continue
                path_value = file_item.get("路径")
                if isinstance(path_value, str) and path_value and not (root / path_value).exists():
                    warnings.append(f"实现清单文件不存在: {path_value}")
    elif implementation is not None:
        errors.append("实现清单 必须是对象")

    return errors, warnings


def emit_text(errors: list[str], warnings: list[str]) -> None:
    print(f"架构校验: 错误 {len(errors)} 项, 警告 {len(warnings)} 项")
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARN: {item}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate task architecture JSON.")
    parser.add_argument("architecture", type=Path, help="Path to architecture.json")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        data = load_json(args.architecture)
    except FileNotFoundError:
        print(f"ERROR: 文件不存在: {args.architecture}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: JSON 语法错误: {exc}", file=sys.stderr)
        return 2

    if not isinstance(data, dict):
        print("ERROR: architecture 根节点必须是对象", file=sys.stderr)
        return 2

    errors, warnings = validate_architecture(data, args.architecture.resolve().parent)
    if args.json:
        print(json.dumps({"错误": errors, "警告": warnings}, ensure_ascii=False, indent=2))
    else:
        emit_text(errors, warnings)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
