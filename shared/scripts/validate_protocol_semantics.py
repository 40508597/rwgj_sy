#!/usr/bin/env python3
"""Validate semantic baselines for the portable task-architecture protocol.

The checker is intentionally small and read-only. It verifies that the upgraded
protocol keeps project goals inside architecture.json, preserves the core
reference files, adapter files, and script/schema hooks. It does not replace
engineering review.
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


REQUIRED_PROTOCOL_FILES = [
    "shared/references/universal-agent-protocol.md",
    "shared/references/dynamic-posture-context.md",
    "shared/references/module-agent-protocol.md",
    "shared/references/hard-gates.md",
    "shared/references/agent-output-contract.md",
]

REQUIRED_ADAPTER_FILES = [
    "shared/adapters/codex.md",
    "shared/adapters/claude.md",
    "shared/adapters/trae.md",
    "shared/adapters/generic-cli-agent.md",
]

REQUIRED_TOOL_FILES = [
    "shared/scripts/validate_agent_output.py",
    "shared/assets/schema/agent-output.schema.json",
    "shared/assets/example-agent-output.json",
]

SKILL_REQUIRED_PHRASES = [
    "任意编程智能体",
    "动态姿势语境",
    "虚拟模块智能体",
    "adapters/",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _is_non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def validate_protocol(root: Path, architecture_path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    data = _archlib.load_architecture_json(architecture_path)
    if not isinstance(data, dict):
        return ["architecture 根节点必须是对象"], warnings

    project = data.get("项目", {})
    if not isinstance(project, dict):
        errors.append("项目 必须是对象")
    elif not _is_non_empty(project.get("说明")):
        warnings.append("项目.说明 建议填写项目目标、非目标和长期维护背景摘要")

    recovery = data.get("上下文恢复点", {})
    if isinstance(recovery, dict) and recovery.get("动态姿势语境") and not isinstance(recovery.get("动态姿势语境"), dict):
        warnings.append("上下文恢复点.动态姿势语境 如果存在，建议为对象")

    for rel in REQUIRED_PROTOCOL_FILES + REQUIRED_ADAPTER_FILES + REQUIRED_TOOL_FILES:
        if not (root / rel).exists():
            errors.append(f"必需协议文件不存在: {rel}")

    skill_files = [
        root / "SKILL.md",
        root / "AGENT-USAGE.md",
        root / "skills" / "task-architecture" / "SKILL.md",
        root / "skills" / "agent-protocol" / "SKILL.md",
    ]
    combined_skill_text = ""
    for skill_file in skill_files:
        if skill_file.exists():
            combined_skill_text += read_text(skill_file) + "\n"
    if not combined_skill_text.strip():
        errors.append("SKILL.md 和 AGENT-USAGE.md 均不存在")
    else:
        for phrase in SKILL_REQUIRED_PHRASES:
            if phrase not in combined_skill_text:
                warnings.append(f"技能入口文件中未发现关键短语: {phrase}")

    implementation = data.get("实现清单", {})
    if isinstance(implementation, dict):
        declared: set[str] = set()
        for item in implementation.values():
            if not isinstance(item, dict):
                continue
            for file_item in (item.get("文件列表") or item.get("文件") or []):
                if isinstance(file_item, dict) and isinstance(file_item.get("路径"), str):
                    declared.add(file_item["路径"].replace("\\", "/"))
        for rel in REQUIRED_PROTOCOL_FILES + REQUIRED_ADAPTER_FILES + REQUIRED_TOOL_FILES:
            if rel not in declared:
                warnings.append(f"协议文件未登记到实现清单: {rel}")

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate portable protocol semantic baselines.")
    parser.add_argument("project", type=Path, help="Project root")
    parser.add_argument("--architecture", type=Path, default=Path("architecture.json"), help="Architecture JSON")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable result")
    args = parser.parse_args(argv)

    root = args.project.resolve()
    architecture = args.architecture if args.architecture.is_absolute() else root / args.architecture

    result, io_error, io_exit = _archlib.run_with_io_errors(
        lambda: validate_protocol(root, architecture)
    )
    if io_error is not None:
        print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit
    errors, warnings = result

    if args.json:
        print(json.dumps({"错误": errors, "警告": warnings}, ensure_ascii=False, indent=2))
    else:
        _archlib.emit_validation_text("协议语义校验", errors, warnings)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
