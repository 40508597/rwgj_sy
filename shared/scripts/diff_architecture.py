#!/usr/bin/env python3
"""Diff two task-architecture JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()



def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.update(flatten(child, child_prefix))
        return result
    if isinstance(value, list):
        result = {}
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            result.update(flatten(child, child_prefix))
        if not value:
            result[prefix] = []
        return result
    return {prefix: value}


def diff_architecture(old: Any, new: Any) -> dict[str, list[dict[str, Any]] | list[str]]:
    old_flat = flatten(old)
    new_flat = flatten(new)
    old_keys = set(old_flat)
    new_keys = set(new_flat)

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed = [
        {"路径": key, "旧值": old_flat[key], "新值": new_flat[key]}
        for key in sorted(old_keys & new_keys)
        if old_flat[key] != new_flat[key]
    ]
    return {"新增": added, "删除": removed, "修改": changed}


def emit_text(diff: dict[str, Any], max_items: int) -> None:
    total = len(diff["新增"]) + len(diff["删除"]) + len(diff["修改"])
    print(f"架构差异: {total} 项")
    for section in ["新增", "删除"]:
        items = diff[section][:max_items]
        print(f"{section}: {len(diff[section])} 项")
        for item in items:
            print(f"  - {item}")
        if len(diff[section]) > max_items:
            print(f"  ... 已截断 {len(diff[section]) - max_items} 项")
    changed = diff["修改"][:max_items]
    print(f"修改: {len(diff['修改'])} 项")
    for item in changed:
        print(f"  - {item['路径']}: {item['旧值']!r} -> {item['新值']!r}")
    if len(diff["修改"]) > max_items:
        print(f"  ... 已截断 {len(diff['修改']) - max_items} 项")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diff two architecture JSON files.")
    parser.add_argument("old", type=Path, help="Old architecture JSON")
    parser.add_argument("new", type=Path, help="New architecture JSON")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--max-items", type=int, default=80, help="Max text items per section")
    args = parser.parse_args(argv)

    def _load_both() -> tuple[Any, Any]:
        return (
            _archlib.load_architecture_json(args.old),
            _archlib.load_architecture_json(args.new),
        )

    pair, io_error, io_exit = _archlib.run_with_io_errors(_load_both)
    if io_error is not None:
        print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit
    old_data, new_data = pair

    diff = diff_architecture(old_data, new_data)
    if args.json:
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        emit_text(diff, args.max_items)
    total = len(diff["新增"]) + len(diff["删除"]) + len(diff["修改"])
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
