#!/usr/bin/env python3
"""Shared helpers for task-architecture scripts.

This module centralises the boilerplate that every script in
``shared/scripts/`` used to copy-paste: UTF-8 stdout reconfiguration,
architecture-JSON loading (with pointer following), slice hydration,
project-root inference, implementation-manifest collection, and the
standard validation text output.

Design contract:

* Pure standard library (matches the "工具失败时按文本规则降级" principle).
* Read-only except for ``configure_utf8_stdout`` (which mutates ``sys``).
* Functions raise only the same exceptions the original inline code raised
  (``FileNotFoundError``, ``json.JSONDecodeError``, ``ValueError``) so each
  script's existing ``try/except`` still catches them.
* Every script keeps running as an independent subprocess; importing this
  module is the only shared dependency. Scripts add their own directory to
  ``sys.path`` before importing (see header template in usage docs).

Encoding note: we read with ``utf-8-sig`` throughout because it transparently
accepts both BOM-prefixed and plain UTF-8 files — this is a strict superset of
the behaviours previously hard-coded per script, so no caller regresses.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")


def configure_utf8_stdout() -> None:
    """Force stdout/stderr to UTF-8 so Chinese keys/labels never mojibake on Windows."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


def project_root_for_architecture(path: Path) -> Path:
    """Infer the project root from an architecture file path.

    ``architecture/index.json`` -> the directory above ``architecture/``.
    Anything else (e.g. a legacy single-file ``architecture.json``) -> its
    parent directory.
    """
    if path.name == "index.json" and path.parent.name == "architecture":
        return path.parent.parent
    return path.parent


def hydrate_slices(data: Any, architecture_path: Path) -> Any:
    """Merge enabled physical slices back into an in-memory architecture dict.

    Pass-through when ``data`` is not a dict or when slicing is disabled.
    Skips the ``切片元信息`` metadata key so it never leaks into business data.
    Missing slice files are silently skipped (callers that need strictness can
    re-check existence afterwards).
    """
    if not isinstance(data, dict):
        return data
    slice_state = data.get("架构切片", {})
    if not isinstance(slice_state, dict) or not slice_state.get("启用"):
        return data
    slice_items = slice_state.get("切片清单", [])
    if not isinstance(slice_items, list) or not slice_items:
        return data
    project_root = project_root_for_architecture(architecture_path)
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


def load_architecture_json(path: Path) -> Any:
    """Read an architecture JSON, following the ``指向`` pointer and hydrating slices.

    Equivalent to the inline ``load_json`` that used to live in five scripts.
    Supports both pointer form (``{"指向": "architecture/index.json"}``) and
    legacy inline single-file form.
    """
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and isinstance(data.get("指向"), str):
        target = path.parent / data["指向"]
        data = json.loads(target.read_text(encoding="utf-8-sig"))
        return hydrate_slices(data, target)
    return hydrate_slices(data, path)


def collect_implementation_files(data: Any) -> set[str]:
    """Return the set of forward-slash file paths declared in ``实现清单``.

    Accepts either ``文件列表`` or ``文件`` as the per-item file container.
    Empty/missing manifests return an empty set (never raise).
    """
    declared: set[str] = set()
    if not isinstance(data, dict):
        return declared
    implementation = data.get("实现清单", {})
    if not isinstance(implementation, dict):
        return declared
    for item in implementation.values():
        if not isinstance(item, dict):
            continue
        for file_item in (item.get("文件列表") or item.get("文件") or []):
            if isinstance(file_item, dict) and isinstance(file_item.get("路径"), str):
                declared.add(file_item["路径"].replace("\\", "/").rstrip("/"))
    return declared


def emit_validation_text(title: str, errors: Iterable[str], warnings: Iterable[str]) -> None:
    """Print the standard ``{title}: 错误 N 项, 警告 M 项`` summary plus ERROR/WARN lines."""
    errors_list = list(errors)
    warnings_list = list(warnings)
    print(f"{title}: 错误 {len(errors_list)} 项, 警告 {len(warnings_list)} 项")
    for item in errors_list:
        print(f"ERROR: {item}")
    for item in warnings_list:
        print(f"WARN: {item}")


def run_with_io_errors(func: Callable[[], T]) -> tuple[T | None, str | None, int]:
    """Run ``func`` and translate the two common IO/JSON errors into a friendly message.

    Returns ``(result, error_message, exit_code)``:
    * success -> ``(result, None, 0)``
    * ``FileNotFoundError`` -> ``(None, "文件不存在: <name>", 2)``
    * ``json.JSONDecodeError`` -> ``(None, "JSON 语法错误: <exc>", 2)``

    Anything else re-raises (callers that want broader catching wrap further).
    """
    try:
        return func(), None, 0
    except FileNotFoundError as exc:
        name = exc.filename or str(exc)
        return None, f"文件不存在: {name}", 2
    except json.JSONDecodeError as exc:
        return None, f"JSON 语法错误: {exc}", 2
