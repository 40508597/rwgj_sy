#!/usr/bin/env python3
"""Scan for drift between architecture implementation lists and code files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


DEFAULT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".kt",
    ".vue",
    ".svelte",
    ".md",
    ".json",
}

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".pytest_cache",
}

DEFAULT_IGNORE_FILE_PREFIXES = (".tmp-",)


def looks_like_file_path(value: str, root: Path) -> bool:
    normalized = value.replace("\\", "/").strip()
    if not normalized or "\n" in normalized:
        return False
    if normalized.startswith(("http://", "https://")):
        return False
    first_token = normalized.split()[0]
    if first_token in {"python", "python3", "node", "npm", "pnpm", "yarn", "uv", "pytest"}:
        return False
    path = Path(normalized)
    suffix = path.suffix.lower()
    if "/" in normalized and suffix in DEFAULT_EXTENSIONS:
        return True
    if "/" in normalized and "." in path.name:
        return True
    if normalized.startswith(".") and suffix in DEFAULT_EXTENSIONS:
        return True
    if " " not in normalized and suffix in DEFAULT_EXTENSIONS and (root / normalized).exists():
        return True
    return False


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and data.get("架构模式") == "架构文件夹" and isinstance(data.get("架构入口"), str):
        target = path.parent / data["架构入口"]
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
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
        with slice_path.open("r", encoding="utf-8-sig") as handle:
            slice_data = json.load(handle)
        if not isinstance(slice_data, dict):
            continue
        for key, value in slice_data.items():
            if key != "切片元信息":
                hydrated[key] = value
    return hydrated


def _normalize(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_values(value: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for child in value.values():
            values.extend(_iter_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_iter_values(child))
    else:
        values.append(value)
    return values


def collect_declared_files(data: dict[str, Any], root: Path) -> set[str]:
    declared: set[str] = set()
    implementation = data.get("实现清单", {})
    if isinstance(implementation, dict):
        for item in implementation.values():
            if not isinstance(item, dict):
                continue
            for file_item in item.get("文件列表", []):
                if isinstance(file_item, dict) and isinstance(file_item.get("路径"), str):
                    declared.add(file_item["路径"].replace("\\", "/").rstrip("/"))

    for key in ["功能树", "模块树"]:
        for value in _iter_values(data.get(key, [])):
            if isinstance(value, str) and looks_like_file_path(value, root):
                declared.add(value.replace("\\", "/").rstrip("/"))

    return {item for item in declared if item}


def collect_actual_files(root: Path, extensions: set[str], ignore_dirs: set[str]) -> set[str]:
    actual: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore_dirs for part in path.parts):
            continue
        if path.name.startswith(DEFAULT_IGNORE_FILE_PREFIXES):
            continue
        if path.suffix.lower() not in extensions:
            continue
        actual.add(_normalize(path, root))
    return actual


def scan_code_drift(project_root: Path, architecture_path: Path, extensions: set[str]) -> dict[str, list[str]]:
    data = load_json(architecture_path)
    if not isinstance(data, dict):
        raise ValueError("architecture 根节点必须是对象")

    declared = collect_declared_files(data, project_root)
    actual = collect_actual_files(project_root, extensions, DEFAULT_IGNORE_DIRS)
    declared_files = {item for item in declared if Path(item).suffix.lower() in extensions}

    missing_declared = sorted(item for item in declared_files if not (project_root / item).exists())
    undocumented = sorted(item for item in actual if item not in declared_files)

    return {
        "声明但不存在": missing_declared,
        "存在但未登记": undocumented,
        "已登记代码文件": sorted(declared_files),
    }


def emit_text(result: dict[str, list[str]], max_items: int) -> None:
    missing = result["声明但不存在"]
    undocumented = result["存在但未登记"]
    print(f"代码漂移扫描: 声明但不存在 {len(missing)} 项, 存在但未登记 {len(undocumented)} 项")
    for label, items in [("声明但不存在", missing), ("存在但未登记", undocumented)]:
        print(f"{label}: {len(items)} 项")
        for item in items[:max_items]:
            print(f"  - {item}")
        if len(items) > max_items:
            print(f"  ... 已截断 {len(items) - max_items} 项")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan code drift against architecture.json.")
    parser.add_argument("project", type=Path, help="Project root")
    parser.add_argument("--architecture", type=Path, default=Path("architecture.json"), help="Architecture JSON")
    parser.add_argument("--extensions", default=",".join(sorted(DEFAULT_EXTENSIONS)), help="Comma-separated extensions")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--max-items", type=int, default=80, help="Max text items per section")
    args = parser.parse_args(argv)

    project_root = args.project.resolve()
    architecture_path = args.architecture
    if not architecture_path.is_absolute():
        architecture_path = project_root / architecture_path

    if not project_root.exists():
        print(f"ERROR: 项目目录不存在: {project_root}", file=sys.stderr)
        return 2
    if not architecture_path.exists():
        print(f"ERROR: architecture 文件不存在: {architecture_path}", file=sys.stderr)
        return 2

    extensions = {item.strip().lower() for item in args.extensions.split(",") if item.strip()}
    extensions = {item if item.startswith(".") else f".{item}" for item in extensions}

    try:
        result = scan_code_drift(project_root, architecture_path, extensions)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_text(result, args.max_items)

    return 1 if result["声明但不存在"] or result["存在但未登记"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
