#!/usr/bin/env python3
"""Small deterministic helpers for the split task-architecture system.

This CLI is intentionally non-cognitive. It can inspect architecture JSON,
check basic write gates, and print capability lineage. It must not expand
function clusters or make design decisions.
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


def emit(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def get_path(data: Any, dotted_path: str) -> Any:
    current = data
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def cmd_slice(args: argparse.Namespace) -> int:
    data = _archlib.load_architecture_json(args.architecture)
    if args.path:
        emit({"路径": args.path, "结果": get_path(data, args.path)})
        return 0
    if args.module:
        details = data.get("模块详情", {}) if isinstance(data, dict) else {}
        emit({"模块": args.module, "结果": details.get(args.module)})
        return 0
    emit({"错误": "需要 --path 或 --module"})
    return 2


def cmd_gate_file(args: argparse.Namespace) -> int:
    data = _archlib.load_architecture_json(args.architecture)
    declared = _archlib.collect_implementation_files(data)
    target = args.file.replace("\\", "/").rstrip("/")
    if target in declared:
        emit({"通过": True, "文件": target})
        return 0
    emit({
        "通过": False,
        "文件": target,
        "原因": "文件未登记到 实现清单",
        "修复": "先更新 architecture/index.json 的切片清单和相关架构切片中的功能树、模块详情、实现清单，再修改文件",
    })
    return 1


def cmd_lineage(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    lineage = root / "docs" / "version-lineage.md"
    capability = root / "docs" / "capability-map.md"
    emit({
        "version_lineage": str(lineage),
        "capability_map": str(capability),
        "exists": {
            "version_lineage": lineage.exists(),
            "capability_map": capability.exists(),
        },
        "执行顺序": ["project-depth-core", "architecture-json", "agent-protocol"],
    })
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task architecture deterministic CLI helpers.")
    sub = parser.add_subparsers(dest="command", required=True)

    slice_parser = sub.add_parser("slice", help="Read an architecture path or module detail.")
    slice_parser.add_argument("--architecture", type=Path, default=Path("architecture.json"))
    slice_parser.add_argument("--path")
    slice_parser.add_argument("--module")
    slice_parser.set_defaults(func=cmd_slice)

    gate_parser = sub.add_parser("gate-file", help="Check whether a file is registered.")
    gate_parser.add_argument("--architecture", type=Path, default=Path("architecture.json"))
    gate_parser.add_argument("--file", required=True)
    gate_parser.set_defaults(func=cmd_gate_file)

    lineage_parser = sub.add_parser("lineage", help="Show capability lineage files.")
    lineage_parser.add_argument("--root", type=Path, default=Path("."))
    lineage_parser.set_defaults(func=cmd_lineage)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
