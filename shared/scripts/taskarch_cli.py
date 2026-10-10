#!/usr/bin/env python3
"""Small deterministic helpers for the split xl-ai-language system.

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
        elif isinstance(current, list) and part.isdecimal():
            normalized = part.lstrip("0") or "0"
            if len(normalized) > len(str(len(current))):
                return None
            index = int(normalized)
            current = current[index] if index < len(current) else None
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
        emit({"模块": args.module, "结果": details.get(args.module) if isinstance(details, dict) else None})
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
        "修复": "先从项目根架构定位所属模块，更新相关模块架构中的功能、契约与实现清单，再修改文件；集中布局使用相关切片",
    })
    return 1


def cmd_lineage(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    # 版本继承与能力地图已合并进 README §二（版本演进）与 §4.1/4.2，
    # 避免能力来源与子能力说明在多份文档中重复维护。
    readme = root / "README.md"
    emit({
        "version_lineage_source": "README.md §二 版本演进",
        "capability_map_source": "README.md §4.1/4.2 子能力层",
        "readme_exists": readme.exists(),
        "执行顺序": ["project-depth-core", "architecture-json", "agent-protocol"],
    })
    return 0


def main(argv: list[str] | None = None) -> int:
    # Keep existing three helpers; unified namespaces share the maintained core.
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if forwarded and (forwarded[0] in {"query", "change", "lease", "handoff", "run", "checkpoint", "timeline", "project"}
                      or forwarded[0] in {"--project", "--architecture"}):
        from taskarch import main as toolchain_main
        return toolchain_main(forwarded)
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
    result, error, exit_code = _archlib.run_with_io_errors(lambda: args.func(args))
    if error is not None:
        emit({"status": "unknown", "错误": error})
        return exit_code
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
