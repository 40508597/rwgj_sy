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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def load_json(path: Path) -> Any:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and isinstance(data.get("指向"), str):
        target = path.parent / data["指向"]
        data = json.loads(target.read_text(encoding="utf-8-sig"))
        return hydrate_slices(data, target)
    return hydrate_slices(data, path)


def _project_root_for_architecture(path: Path) -> Path:
    if path.name == "index.json" and path.parent.name == "architecture":
        return path.parent.parent
    return path.parent


def hydrate_slices(data: Any, architecture_path: Path) -> Any:
    if not isinstance(data, dict):
        return data
    slice_state = data.get("架构切片", {})
    if not isinstance(slice_state, dict) or not slice_state.get("启用"):
        return data
    slice_items = slice_state.get("切片清单", [])
    if not isinstance(slice_items, list) or not slice_items:
        return data
    project_root = _project_root_for_architecture(architecture_path)
    hydrated = dict(data)
    for item in slice_items:
        if not isinstance(item, dict) or not isinstance(item.get("路径"), str):
            continue
        slice_path = project_root / item["路径"]
        if not slice_path.exists():
            continue
        slice_data = json.loads(slice_path.read_text(encoding="utf-8-sig"))
        if not isinstance(slice_data, dict):
            continue
        for key, value in slice_data.items():
            if key != "切片元信息":
                hydrated[key] = value
    return hydrated


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
    data = load_json(args.architecture)
    if args.path:
        emit({"路径": args.path, "结果": get_path(data, args.path)})
        return 0
    if args.module:
        details = data.get("模块详情", {}) if isinstance(data, dict) else {}
        emit({"模块": args.module, "结果": details.get(args.module)})
        return 0
    emit({"错误": "需要 --path 或 --module"})
    return 2


def iter_declared_files(data: dict[str, Any]) -> set[str]:
    declared: set[str] = set()
    implementation = data.get("实现清单", {})
    if not isinstance(implementation, dict):
        return declared
    for item in implementation.values():
        if not isinstance(item, dict):
            continue
        for file_item in (item.get("文件列表") or item.get("文件") or []):
            if isinstance(file_item, dict) and isinstance(file_item.get("路径"), str):
                declared.add(file_item["路径"].replace("\\", "/"))
    return declared


def cmd_gate_file(args: argparse.Namespace) -> int:
    data = load_json(args.architecture)
    declared = iter_declared_files(data)
    target = args.file.replace("\\", "/")
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
