#!/usr/bin/env python3
"""Diff two task-architecture JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


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
        with slice_path.open("r", encoding="utf-8-sig") as handle:
            slice_data = json.load(handle)
        if not isinstance(slice_data, dict):
            continue
        for key, value in slice_data.items():
            if key != "切片元信息":
                hydrated[key] = value
    return hydrated


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and isinstance(data.get("指向"), str):
        target = path.parent / data["指向"]
        with target.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return hydrate_slices(data, target)
    return hydrate_slices(data, path)


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

    try:
        old_data = load_json(args.old)
        new_data = load_json(args.new)
    except FileNotFoundError as exc:
        print(f"ERROR: 文件不存在: {exc.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: JSON 语法错误: {exc}", file=sys.stderr)
        return 2

    diff = diff_architecture(old_data, new_data)
    if args.json:
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        emit_text(diff, args.max_items)
    total = len(diff["新增"]) + len(diff["删除"]) + len(diff["修改"])
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
