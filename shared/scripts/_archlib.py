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
import copy
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")


class ArchitectureInputError(ValueError):
    """Malformed architecture input, distinct from an internal programming error."""


def _read_architecture_file(path: Path) -> Any:
    if "\x00" in str(path):
        raise ArchitectureInputError("架构文件路径不得包含 NUL 字符")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def configure_utf8_stdout() -> None:
    """Force stdout/stderr to UTF-8 so Chinese keys/labels never mojibake on Windows."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


def aggregate_status(statuses: Iterable[str]) -> str:
    """统一门禁聚合：明确失败优先，其次未知，全部通过才通过。"""
    values = list(statuses)
    if "fail" in values:
        return "fail"
    if not values or any(value != "pass" for value in values):
        return "unknown"
    return "pass"


def project_root_for_architecture(path: Path) -> Path:
    """Infer the project root from an architecture file path.

    ``architecture/index.json`` -> the directory above ``architecture/``.
    Anything else (e.g. a legacy single-file ``architecture.json``) -> its
    parent directory.
    """
    if path.name == "index.json" and path.parent.name == "architecture":
        return path.parent.parent
    return path.parent


def _contained_path(root: Path, relative: str, label: str, *,
                    base: Path | None = None, allow_parent: bool = False) -> Path:
    """Resolve a project-relative input and reject lexical or link escapes."""
    normalized = relative.replace("\\", "/")
    if not normalized or "\x00" in normalized:
        raise ArchitectureInputError(f"{label}路径不得为空或包含 NUL 字符")
    rel = Path(normalized)
    if rel.is_absolute() or rel.drive or re.match(r"^[A-Za-z]:", normalized) or (".." in rel.parts and not allow_parent):
        raise ArchitectureInputError(f"{label}必须是项目内的相对路径: {relative}")
    target = (base if base is not None else root) / rel
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ArchitectureInputError(f"{label}路径超出项目范围: {relative}") from exc
    return target


def _merge_slice_value(left: Any, right: Any, field: str) -> Any:
    """Combine independent declarations without last-writer data loss."""
    if isinstance(left, dict) and isinstance(right, dict):
        merged = copy.deepcopy(left)
        for key, value in right.items():
            merged[key] = (_merge_slice_value(merged[key], value, f"{field}.{key}")
                           if key in merged else copy.deepcopy(value))
        return merged
    if isinstance(left, list) and isinstance(right, list):
        merged = copy.deepcopy(left)
        for value in right:
            if isinstance(value, dict) and isinstance(value.get("编号"), str):
                matches = [i for i, old in enumerate(merged)
                           if isinstance(old, dict) and old.get("编号") == value["编号"]]
                if len(matches) > 1:
                    raise ArchitectureInputError(f"架构切片编号重复: {field}[{value['编号']}]")
                if matches:
                    index = matches[0]
                    merged[index] = _merge_slice_value(merged[index], value, f"{field}[{value['编号']}]")
                    continue
            if not any(type(old) is type(value) and old == value for old in merged):
                merged.append(copy.deepcopy(value))
        return merged
    if type(left) is type(right) and left == right:
        return copy.deepcopy(left)
    raise ArchitectureInputError(f"架构切片声明冲突: {field}；请在切片中统一该字段的值")


def hydrate_slices(data: Any, architecture_path: Path,
                   source_paths: set[Path] | None = None, *, project_root: Path | None = None) -> Any:
    """Merge enabled physical slices back into an in-memory architecture dict.

    Pass-through when ``data`` is not a dict or when slicing is disabled.
    Skips the ``切片元信息`` metadata key so it never leaks into business data.
    A physical slice is authoritative for its declared fields. Missing files,
    ownership violations and conflicting declarations are input errors.
    """
    if not isinstance(data, dict):
        return data
    slice_state = data.get("架构切片", {})
    if not isinstance(slice_state, dict) or slice_state.get("启用") is not True:
        return data
    slice_items = slice_state.get("切片清单", [])
    if not isinstance(slice_items, list) or not slice_items:
        return data
    project_root = project_root if project_root is not None else project_root_for_architecture(architecture_path)
    hydrated = dict(data)
    owned_fields: set[str] = set()
    for item in slice_items:
        if not isinstance(item, dict) or not isinstance(item.get("路径"), str):
            continue  # 模板占位项留给 F 检查，不改变其 incomplete/退出码 1 契约。
        slice_path = _contained_path(project_root, item["路径"], "架构切片")
        try:
            slice_path.resolve().relative_to((project_root / "architecture").resolve())
        except ValueError as exc:
            raise ArchitectureInputError(f"权威架构切片必须位于项目 architecture/ 内: {slice_path}") from exc
        if not slice_path.exists():
            raise ArchitectureInputError(f"权威架构切片文件不存在: {slice_path}")
        if source_paths is not None:
            source_paths.add(slice_path)
        slice_data = _read_architecture_file(slice_path)
        if not isinstance(slice_data, dict):
            raise ArchitectureInputError(f"架构切片 {slice_path} 根节点必须是对象")
        payload = {key: value for key, value in slice_data.items() if key != "切片元信息"}
        if any(key in payload for key in ("指向", "架构切片")):
            raise ArchitectureInputError(f"架构切片不得覆盖入口或切片配置: {slice_path}")
        contains = item.get("包含")
        if "包含" in item:
            if not isinstance(contains, list) or any(not isinstance(key, str) or not key for key in contains):
                raise ArchitectureInputError(f"架构切片包含必须是字段名称数组: {slice_path}")
            extra = sorted(set(payload) - set(contains))
            if extra:
                raise ArchitectureInputError(f"架构切片越出包含范围: {slice_path}: {', '.join(extra)}")
            absent = sorted(set(contains) - set(payload))
            if absent:
                raise ArchitectureInputError(f"架构切片缺少声明包含字段: {slice_path}: {', '.join(absent)}")
        for key, value in payload.items():
            hydrated[key] = (_merge_slice_value(hydrated[key], value, key)
                             if key in owned_fields else copy.deepcopy(value))
            owned_fields.add(key)
    return hydrated


def load_architecture_json(path: Path, source_paths: set[Path] | None = None, *,
                           project_root: Path | None = None) -> Any:
    """Read an architecture JSON, following the ``指向`` pointer and hydrating slices.

    Equivalent to the inline ``load_json`` that used to live in five scripts.
    Supports both pointer form (``{"指向": "architecture/index.json"}``) and
    legacy inline single-file form.
    """
    explicit_root = project_root is not None
    project_root = project_root if explicit_root else project_root_for_architecture(path)
    seen: set[Path] = set()
    current = path
    while True:
        identity = current.resolve()
        try:
            identity.relative_to(project_root.resolve())
        except ValueError as exc:
            raise ArchitectureInputError(f"架构输入路径超出项目范围: {current}") from exc
        if identity in seen:
            raise ArchitectureInputError(f"架构指针循环: {current}")
        seen.add(identity)
        if source_paths is not None:
            source_paths.add(current)
        data = _read_architecture_file(current)
        if isinstance(data, dict) and isinstance(data.get("指向"), str):
            target = _contained_path(project_root, data["指向"], "架构指针", base=current.parent,
                                     allow_parent=True)
            current = target
            continue
        return hydrate_slices(data, current, source_paths, project_root=project_root)


def collect_implementation_files(data: Any) -> set[str]:
    """Return the set of forward-slash file paths declared in ``实现清单``.

    Combines ``文件列表`` and ``文件`` as per-item file containers.
    Empty/missing manifests return an empty set (never raise).
    """
    declared: set[str] = set()
    if not isinstance(data, dict):
        return declared
    implementation = data.get("实现清单", {})
    if not isinstance(implementation, dict):
        raise ArchitectureInputError("实现清单必须是模块对象")
    for module, item in implementation.items():
        if not isinstance(item, dict):
            raise ArchitectureInputError(f"实现清单.{module}必须是对象")
        for field in ("文件列表", "文件"):
            files = item.get(field, [])
            if not isinstance(files, list):
                raise ArchitectureInputError(f"实现清单.{module}.{field}必须是数组")
            for file_item in files:
                if isinstance(file_item, dict) and isinstance(file_item.get("路径"), str):
                    path = file_item["路径"]
                elif isinstance(file_item, str):
                    path = file_item
                else:
                    raise ArchitectureInputError(f"实现清单.{module}.{field}路径必须为字符串或路径对象")
                if not path.strip() or any(char in path for char in ("\x00", "\n", "\r")):
                    raise ArchitectureInputError(f"实现清单.{module}.{field}必须是非空路径且不得含 NUL 或换行")
                declared.add(path.replace("\\", "/").rstrip("/"))
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
    """Run ``func`` and translate IO/encoding/JSON errors into a friendly message.

    Returns ``(result, error_message, exit_code)``:
    * success -> ``(result, None, 0)``
    * ``FileNotFoundError`` -> ``(None, "文件不存在: <name>", 2)``
    * ``json.JSONDecodeError`` -> ``(None, "JSON 语法错误: <exc>", 2)``
    * ``UnicodeError`` / other ``OSError`` -> a readable input error, exit 2

    Anything else re-raises (callers that want broader catching wrap further).
    """
    try:
        return func(), None, 0
    except ArchitectureInputError as exc:
        return None, f"架构输入错误: {exc}", 2
    except FileNotFoundError as exc:
        name = exc.filename or str(exc)
        return None, f"文件不存在: {name}", 2
    except json.JSONDecodeError as exc:
        return None, f"JSON 语法错误: {exc}", 2
    except UnicodeError as exc:
        return None, f"文件编码错误（需要 UTF-8）: {exc}", 2
    except OSError as exc:
        return None, f"文件读取失败: {exc}", 2


def collect_actual_files(root: Path, extensions: set[str], ignore_dirs: set[str],
                         ignore_file_prefixes: tuple[str, ...] = (".tmp-",)) -> set[str]:
    return set(iter_actual_files(root, extensions, ignore_dirs, ignore_file_prefixes))


def iter_actual_files(root: Path, extensions: set[str], ignore_dirs: set[str],
                      ignore_file_prefixes: tuple[str, ...] = (".tmp-",)) -> Iterable[str]:
    """Collect real files under ``root`` whose suffix is in ``extensions``.

    Forward-slash relative paths. Skips directories in ``ignore_dirs``, files whose
    name starts with any ``ignore_file_prefixes``, files with a suffix outside
    ``extensions`` (case-insensitive), and empty files. Mirrors the logic that
    ``scan_code_drift.collect_actual_files`` and ``gate_check._count_impl_files``
    used to keep in two places.
    """
    # Prune before descending: dependency trees can contain far more files than
    # the project. Ignore names apply below root, not to its ancestor directories.
    resolved_root = root.resolve()

    def raise_walk_error(error: OSError) -> None:
        raise error  # An incomplete scan must not masquerade as a clean project.

    for directory, dirs, files in os.walk(root, onerror=raise_walk_error):
        dirs[:] = [name for name in dirs if name not in ignore_dirs]
        for name in files:
            if name.startswith(ignore_file_prefixes) or Path(name).suffix.lower() not in extensions:
                continue
            path = Path(directory) / name
            if not path.is_file() or path.stat().st_size == 0:
                continue
            try:
                relative = path.resolve().relative_to(resolved_root).as_posix()
            except ValueError:
                relative = path.as_posix()
            yield relative


def run_subprocess_json(cmd: list[str]) -> tuple[int, Any, str]:
    """Run a subprocess that is expected to emit a JSON document on stdout.

    Returns ``(returncode, parsed_json_or_None, stderr_or_error_text)``:
    * success + valid JSON -> ``(0, obj, "")``
    * subprocess returns non-zero but stdout is valid JSON -> ``(code, obj, stderr)``
      (caller decides whether code is an error; some tools use non-zero as
      advisory signal while still emitting JSON, e.g. detect_should_trigger)
    * stdout not JSON -> ``(code, None, stderr or stdout)``

    Replaces the three bespoke subprocess wrappers that used to live in
    judge_progress.run_command / gate_check._run_script / run_with_progress.
    UTF-8 + errors=replace keeps Chinese output legible on any host.
    """
    import subprocess
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return 1, None, str(exc)
    parsed: Any = None
    try:
        parsed = json.loads(result.stdout) if result.stdout else None
    except json.JSONDecodeError:
        parsed = None
    err_text = (result.stderr or result.stdout) if parsed is None else result.stderr
    return result.returncode, parsed, err_text


def load_json_utf8(path: Path) -> dict[str, Any]:
    """Read a JSON file (utf-8-sig, BOM-safe) and require an object root.

    Shared by the advisory detectors (detect_task_posture / detect_small_command)
    so rule files with or without BOM load identically. Raises ``ValueError``
    when the root node is not an object.
    """
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("规则文件根节点必须是对象")
    return data


def collect_matches(text: str, words: Any) -> list[str]:
    """Case-insensitive substring matches of ``words`` in ``text``.

    Non-list ``words`` (e.g. a rule author's typo of a bare string) yields no
    matches instead of silently iterating per character.
    """
    if not isinstance(words, (list, tuple)):
        return []
    lowered = text.lower()
    matches: list[str] = []
    for word in words:
        if not isinstance(word, str) or not word:
            continue
        if word.lower() in lowered:
            matches.append(word)
    return matches


def contains_any(text: str, words: Any) -> bool:
    return bool(collect_matches(text, words))


def unique(items: list[str]) -> list[str]:
    """Deduplicate preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def is_managed(project_root: Path) -> bool:
    """受管项目：根存在 architecture.json 或 architecture/ 目录（LAYER.md 口径）。

    单点定义，供 detect_task_posture / detect_small_command 等 advisory 工具
    共用，避免切片项目（仅 architecture/）在两个工具中给出矛盾信号。
    """
    return (project_root / "architecture.json").exists() or (project_root / "architecture").is_dir()


def is_capability_package(project_root: Path) -> bool:
    """Identify this complete capability package; project anchors take priority."""
    if is_managed(project_root):
        return False
    required = ("SKILL.md", "shared/scripts/_archlib.py",
                "shared/assets/schema/architecture.schema.json", "skills/task-architecture/LAYER.md")
    if not all((project_root / relative).is_file() for relative in required):
        return False
    try:
        text = (project_root / "SKILL.md").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return False
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        return False
    return re.search(r"^name[ \t]*:[ \t]*(?:任务架构|task-architecture|'任务架构'|'task-architecture'|\"任务架构\"|\"task-architecture\")[ \t]*(?:#.*)?$",
                     parts[1], re.MULTILINE) is not None
