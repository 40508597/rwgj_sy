#!/usr/bin/env python3
"""Validate standardized task-architecture agent output.

This tool is intentionally lightweight. It checks only the structure needed for
portable module-agent proposals, gate results, and reports. Full engineering
judgment remains in SKILL.md and references/.

真相源：shared/assets/schema/agent-output.schema.json 的 enum / required / properties。
--schema 可选；省略时使用与本脚本同源的默认 schema 路径。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()


# 默认 schema 路径：与本脚本同源（shared/assets/schema/agent-output.schema.json）。
# 仅作缺省回退；--schema 参数可覆盖。
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "assets" / "schema" / "agent-output.schema.json"


def load_json(path: Path) -> Any:
    return _archlib.load_architecture_json(path)


def derive_rules_from_schema(schema: dict[str, Any]) -> tuple[set[str], set[str], set[str], list[str]]:
    """从 schema 推出 (valid_types, valid_results, array_fields, required_fields)。

    schema 是真相源——以下硬编码常量全部由 schema 派生：
    - 输出类型 enum → valid_types
    - 结论 enum → valid_results
    - properties 中 type=array 的字段 → array_fields
    - required → required_fields
    schema 缺失/异常时回退到 FALLBACK_* 常量，保证 0 依赖环境仍能落地校验。
    """
    # 兜底常量：与 schema enum 字段一一对应，schema 不可用时启用。
    FALLBACK_TYPES = {"模块提案", "接口提案", "风险报告", "验证报告", "阻塞报告", "门禁结果"}
    FALLBACK_RESULTS = {"通过", "不通过", "需要确认", "阻塞", "降级执行"}
    FALLBACK_ARRAY_FIELDS = {"变更提案", "接口影响", "风险", "必须同步", "验证责任", "证据", "下一步"}
    FALLBACK_REQUIRED = ["输出类型", "结论"]

    if not isinstance(schema, dict) or "properties" not in schema:
        return FALLBACK_TYPES, FALLBACK_RESULTS, FALLBACK_ARRAY_FIELDS, list(FALLBACK_REQUIRED)

    props = schema["properties"]
    if not isinstance(props, dict):
        raise ValueError("schema.properties 必须是对象")
    valid_types: set[str] = set()
    valid_results: set[str] = set()
    array_fields: set[str] = set()

    type_spec = props.get("输出类型", {})
    if isinstance(type_spec, dict) and isinstance(type_spec.get("enum"), list):
        valid_types = {str(t) for t in type_spec["enum"]}
    if not valid_types:
        valid_types = FALLBACK_TYPES

    result_spec = props.get("结论", {})
    if isinstance(result_spec, dict) and isinstance(result_spec.get("enum"), list):
        valid_results = {str(r) for r in result_spec["enum"]}
    if not valid_results:
        valid_results = FALLBACK_RESULTS

    for field, spec in props.items():
        if isinstance(spec, dict):
            t = spec.get("type")
            # type 可以是 "array" 或 ["array", ...] 联合类型
            if t == "array" or (isinstance(t, list) and "array" in t):
                array_fields.add(field)

    if not array_fields:
        array_fields = FALLBACK_ARRAY_FIELDS

    required = schema.get("required", FALLBACK_REQUIRED)
    if not isinstance(required, list) or any(not isinstance(v, str) for v in required):
        raise ValueError("schema.required 必须是字符串数组")
    return valid_types, valid_results, array_fields, list(required)


def validate_agent_output(
    data: Any,
    valid_types: set[str],
    valid_results: set[str],
    array_fields: set[str],
    required_fields: list[str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ["根节点必须是对象"], warnings

    # 必填字段缺失（schema required）
    for field in required_fields:
        if field not in data:
            errors.append(f"{field} 必填（schema required）")

    output_type = data.get("输出类型")
    result = data.get("结论")
    if "输出类型" in data and (not isinstance(output_type, str) or output_type not in valid_types):
        errors.append(f"输出类型 必须是标准枚举之一：{', '.join(sorted(valid_types))}")
    if "结论" in data and (not isinstance(result, str) or result not in valid_results):
        errors.append(f"结论 必须是标准枚举之一：{', '.join(sorted(valid_results))}")

    scope = data.get("负责范围")
    if scope is not None and not isinstance(scope, dict):
        errors.append("负责范围 必须是对象")
    elif isinstance(scope, dict):
        for field in ("模块", "功能树节点", "接口", "文件"):
            if field not in scope:
                continue
            values = scope[field]
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                errors.append(f"负责范围.{field} 必须是非空字符串组成的数组")
                continue
            if field == "文件":
                for value in values:
                    normalized = value.replace("\\", "/")
                    if ("\x00" in value or normalized.startswith("/") or
                            re.match(r"^[A-Za-z]:", normalized) or ".." in normalized.split("/")):
                        errors.append(f"负责范围.文件 必须是项目内相对路径: {value}")

    family = data.get("功能族展开")
    if family is not None and not isinstance(family, dict):
        errors.append("功能族展开 必须是对象")

    for field in array_fields:
        if field in data and not isinstance(data[field], list):
            errors.append(f"{field} 必须是数组")

    # 语义警告（与 schema 无关，属于工具内置业务规则，保留）
    if isinstance(result, str) and result in {"需要确认", "阻塞", "降级执行"} and not data.get("下一步"):
        warnings.append("需要确认/阻塞/降级执行 应提供 下一步")
    if isinstance(output_type, str) and output_type in {"验证报告", "门禁结果"}:
        evidence = data.get("证据", [])
        unknown = data.get("未验证项", [])
        if not isinstance(unknown, list):
            errors.append("未验证项 必须是数组")
        def meaningful(value: Any) -> bool:
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, dict):
                return any(meaningful(v) for v in value.values())
            if isinstance(value, list):
                return any(meaningful(v) for v in value)
            return False
        has_evidence = isinstance(evidence, list) and any(meaningful(v) for v in evidence)
        has_unknown = isinstance(unknown, list) and any(meaningful(v) for v in unknown)
        if not has_evidence and not has_unknown:
            errors.append(f"{output_type} 必须提供证据或明确未验证项")
        if result == "通过" and (not has_evidence or has_unknown):
            errors.append("通过结论不得缺少证据或同时存在未验证项；报告结构通过不代表证据已实测")

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate standardized agent output.")
    parser.add_argument("output", type=Path, help="Agent output JSON file")
    parser.add_argument(
        "--schema",
        type=Path,
        help="可选 schema 路径；省略时使用同源默认 schema。校验规则由 schema 的 enum/required/properties 实际派生。",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable result")
    args = parser.parse_args(argv)

    # 加载 schema（真相源）
    schema_path = args.schema or DEFAULT_SCHEMA_PATH
    schema: Any = None
    try:
        data = load_json(args.output)
        if schema_path.exists():
            schema = load_json(schema_path)
        valid_types, valid_results, array_fields, required_fields = derive_rules_from_schema(schema)
    except (OSError, UnicodeError, ValueError) as exc:
        if args.json:
            print(json.dumps({"错误": [f"无法读取输入: {exc}"], "警告": [], "status": "unknown"}, ensure_ascii=False))
        else:
            print(f"ERROR: 无法读取输入: {exc}", file=sys.stderr)
        return 2

    errors, warnings = validate_agent_output(data, valid_types, valid_results, array_fields, required_fields)

    if args.json:
        print(json.dumps({
            "错误": errors,
            "警告": warnings,
            "schema_source": str(schema_path) if schema_path.exists() else "fallback",
        }, ensure_ascii=False, indent=2))
    else:
        _archlib.emit_validation_text("智能体输出校验", errors, warnings)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
