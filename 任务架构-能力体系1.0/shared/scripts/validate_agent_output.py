#!/usr/bin/env python3
"""Validate standardized task-architecture agent output.

This tool is intentionally lightweight. It checks only the structure needed for
portable module-agent proposals, gate results, and reports. Full engineering
judgment remains in SKILL.md and references/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


VALID_TYPES = {"模块提案", "接口提案", "风险报告", "验证报告", "阻塞报告", "门禁结果"}
VALID_RESULTS = {"通过", "不通过", "需要确认", "阻塞", "降级执行"}
ARRAY_FIELDS = ["变更提案", "接口影响", "风险", "必须同步", "验证责任", "证据", "下一步"]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_agent_output(data: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ["根节点必须是对象"], warnings

    output_type = data.get("输出类型")
    result = data.get("结论")
    if output_type not in VALID_TYPES:
        errors.append("输出类型 必须是标准枚举")
    if result not in VALID_RESULTS:
        errors.append("结论 必须是标准枚举")

    scope = data.get("负责范围")
    if scope is not None and not isinstance(scope, dict):
        errors.append("负责范围 必须是对象")

    family = data.get("功能族展开")
    if family is not None and not isinstance(family, dict):
        errors.append("功能族展开 必须是对象")

    for field in ARRAY_FIELDS:
        if field in data and not isinstance(data[field], list):
            errors.append(f"{field} 必须是数组")

    if result in {"需要确认", "阻塞", "降级执行"} and not data.get("下一步"):
        warnings.append("需要确认/阻塞/降级执行 应提供 下一步")
    if output_type == "验证报告" and not data.get("证据"):
        warnings.append("验证报告 应提供 证据 或明确未验证项")
    if output_type == "门禁结果" and not data.get("证据"):
        warnings.append("门禁结果 建议提供 证据")

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate standardized agent output.")
    parser.add_argument("output", type=Path, help="Agent output JSON file")
    parser.add_argument("--schema", type=Path, help="Optional schema path; parsed for availability only")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable result")
    args = parser.parse_args(argv)

    try:
        data = load_json(args.output)
        if args.schema:
            load_json(args.schema)
    except FileNotFoundError as exc:
        print(f"ERROR: 文件不存在: {exc.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: JSON 语法错误: {exc}", file=sys.stderr)
        return 2

    errors, warnings = validate_agent_output(data)
    if args.json:
        print(json.dumps({"错误": errors, "警告": warnings}, ensure_ascii=False, indent=2))
    else:
        print(f"智能体输出校验: 错误 {len(errors)} 项, 警告 {len(warnings)} 项")
        for item in errors:
            print(f"ERROR: {item}")
        for item in warnings:
            print(f"WARN: {item}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
