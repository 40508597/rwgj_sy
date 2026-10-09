#!/usr/bin/env python3
"""Check registered files and scan a project inventory without reading file contents.

The legacy suffix-filtered scan remains the CLI default for compatibility.
``--all-files`` scans every regular file in the declared scope, including empty
files, extensionless files and binary engineering artifacts. Registered files
are ALWAYS checked, irrespective of the actual-file scan's suffix filter.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()

DEFAULT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".cs", ".php", ".rb", ".swift", ".kt", ".vue", ".svelte", ".md", ".json",
}
DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    "env", "dist", "build", ".next", ".turbo", ".pytest_cache", "architecture",
}
DEFAULT_IGNORE_FILE_PREFIXES = (".tmp-",)


def _safe_path(root: Path, value: str, label: str, *, relative: bool = True) -> Path:
    """Validate lexical and resolved boundaries, including symlink targets."""
    if not isinstance(value, str) or not value or any(c in value for c in ("\x00", "\n", "\r")):
        raise _archlib.ArchitectureInputError(f"{label}必须是非空路径且不得含 NUL 或换行")
    normalized = value.replace("\\", "/")
    win_path = PureWindowsPath(normalized)
    path = Path(normalized)
    if relative and (path.is_absolute() or win_path.drive or win_path.root):
        raise _archlib.ArchitectureInputError(f"{label}必须是项目内的相对路径: {value!r}")
    candidate = Path(os.path.abspath(root / path)) if not path.is_absolute() else Path(os.path.abspath(path))
    try:
        candidate.relative_to(root)
        # Both sides must resolve aliases such as Windows 8.3 directory names.
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise _archlib.ArchitectureInputError(f"{label}越出项目根目录: {value!r}") from exc
    return candidate


def _project_root(project_root: Path) -> Path:
    if "\x00" in str(project_root):
        raise _archlib.ArchitectureInputError("项目目录路径不得含 NUL")
    root = project_root.resolve()
    if not root.is_dir():
        raise _archlib.ArchitectureInputError(f"项目目录不存在或不是目录: {root}")
    return root


def _load_project_architecture(root: Path, architecture_path: Path,
                               source_paths: set[Path] | None = None) -> dict[str, Any]:
    """Validate pointer/slice bounds before reading any of their contents."""
    path = _safe_path(root, str(architecture_path), "架构文件路径", relative=False)
    data = _archlib._read_architecture_file(path)
    if not isinstance(data, dict):
        raise _archlib.ArchitectureInputError("architecture 根节点必须是对象")
    if "指向" in data:
        pointer = data["指向"]
        if not isinstance(pointer, str) or not pointer or any(c in pointer for c in ("\x00", "\n", "\r")):
            raise _archlib.ArchitectureInputError("架构指向必须是非空路径字符串且不得含 NUL 或换行")
        # A pointer is relative to its containing architecture file, not root.
        pointer_value = pointer.replace("\\", "/")
        if Path(pointer_value).is_absolute() or PureWindowsPath(pointer_value).drive or PureWindowsPath(pointer_value).root:
            raise _archlib.ArchitectureInputError("架构指向必须是项目内的相对路径")
        target = _safe_path(root, str(path.parent / pointer.replace("\\", "/")), "架构指向", relative=False)
        data = _archlib._read_architecture_file(target)
        path = target
        if not isinstance(data, dict):
            raise _archlib.ArchitectureInputError("architecture 指向的根节点必须是对象")
    slicing = data.get("架构切片", {})
    if not isinstance(slicing, dict):
        raise _archlib.ArchitectureInputError("架构切片必须是对象")
    if slicing.get("启用"):
        items = slicing.get("切片清单", [])
        if not isinstance(items, list):
            raise _archlib.ArchitectureInputError("切片清单必须是数组")
        slice_root = _archlib.project_root_for_architecture(path)
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("路径"), str):
                raise _archlib.ArchitectureInputError(f"切片清单[{index}]必须提供路径字符串")
            _safe_path(root, item["路径"], f"切片清单[{index}].路径")
            slice_path = _safe_path(root, str(slice_root / item["路径"].replace("\\", "/")), "架构切片路径", relative=False)
            if not slice_path.is_file():
                raise _archlib.ArchitectureInputError(f"启用的架构切片不存在或不是文件: {slice_path}")
    # Use the same pointer-chain/slice semantics as all other architecture
    # consumers after lexical bounds checks, with this caller's explicit root.
    return _archlib.load_architecture_json(architecture_path, source_paths, project_root=root)


def _tree_file_paths(value: Any, label: str, root: Path):
    """Read explicit file slots, not arbitrary descriptions or behavior IDs.

    Placement 文件 is a path slot. 测试 also permits responsibility labels: only
    explicit path records, path-structured strings or existing files register.
    验证责任/测试责任 and prose never register. Directory placements stay directories. Legacy
    untyped tree strings are not authoritative file registrations.
    """
    stack = [(value, label, False)]
    while stack:
        node, context, placement = stack.pop()
        if isinstance(node, list):
            stack.extend((item, f"{context}[{i}]", placement) for i, item in enumerate(node))
            continue
        if not isinstance(node, dict):
            continue
        fields = ("文件", "文件列表", "文件路径", "测试文件") + (("测试",) if placement else ())
        for field in fields:
            if field not in node:
                continue
            entries = node[field] if isinstance(node[field], list) else [node[field]]
            for index, entry in enumerate(entries):
                if placement and field == "测试" and isinstance(entry, dict) and "路径" not in entry:
                    continue  # A named acceptance/scenario record is not a file.
                raw = entry.get("路径") if isinstance(entry, dict) else entry
                if not isinstance(raw, str):
                    raise _archlib.ArchitectureInputError(f"{context}.{field}[{index}]必须是路径字符串或路径对象")
                if placement and field == "测试" and isinstance(entry, str):
                    # Test references may be human labels rather than paths.
                    # No suffix/language/word whitelist: a missing bare-label
                    # test file must use 测试文件 or an explicit 路径 record.
                    if not any(c in raw for c in ("/", "\\")) and not PureWindowsPath(raw).drive:
                        if any(c in raw for c in ("\x00", "\n", "\r")) or not raw:
                            continue
                        if not _safe_path(root, raw, f"{context}.{field}[{index}]").is_file():
                            continue
                directory_ok = placement and field in ("文件", "测试")
                if isinstance(entry, dict) and entry.get("类型") == "文件":
                    directory_ok = False
                yield raw, f"{context}.{field}[{index}]", directory_ok
        if node.get("类型") == "文件":
            yield node.get("路径"), f"{context}.路径", False
        for key, child in node.items():
            if isinstance(child, (dict, list)):
                stack.append((child, f"{context}.{key}", key in ("架构落位", "落位")))


def collect_declared_files(data: dict[str, Any], root: Path) -> set[str]:
    """Check every explicit manifest/tree registration, irrespective of suffix."""
    declared: set[str] = set()
    for value in _archlib.collect_implementation_files(data):
        candidate = _safe_path(root, value, "实现清单文件路径")
        declared.add(candidate.relative_to(root).as_posix())
    for key in ("功能树", "模块树"):
        for value, context, directory_ok in _tree_file_paths(data.get(key, []), key, root):
            candidate = _safe_path(root, value, context)
            # Validate even directory references before excluding them from file
            # completeness. A typed file/manifest record is never exempt here.
            if directory_ok and (value.endswith(("/", "\\")) or candidate.is_dir()):
                continue
            declared.add(candidate.relative_to(root).as_posix())
    return declared


def collect_actual_files(root: Path, extensions: set[str], ignore_dirs: set[str],
                         *, all_files: bool = False, skipped_links: list[str] | None = None) -> set[str]:
    """Inventory regular files only; never open or infer their contents/language."""
    actual: set[str] = set()

    def raise_walk_error(error: OSError) -> None:
        raise error

    for directory, dirs, files in os.walk(root, onerror=raise_walk_error, followlinks=False):
        retained: list[str] = []
        for name in sorted(dirs):
            if name in ignore_dirs:
                continue
            candidate = _safe_path(root, str(Path(directory) / name), "扫描目录", relative=False)
            if candidate.is_symlink():
                if skipped_links is not None:
                    skipped_links.append(candidate.relative_to(root).as_posix())
                continue
            retained.append(name)
        dirs[:] = retained
        for name in sorted(files):
            if name.startswith(DEFAULT_IGNORE_FILE_PREFIXES):
                continue
            if not all_files and Path(name).suffix.lower() not in extensions:
                continue
            candidate = _safe_path(root, str(Path(directory) / name), "扫描文件", relative=False)
            if candidate.is_file() and (all_files or candidate.stat().st_size > 0):
                actual.add(candidate.relative_to(root).as_posix())
    return actual


def scan_code_drift(project_root: Path, architecture_path: Path, extensions: set[str],
                    *, all_files: bool = False, explicit_extensions: bool = False) -> dict[str, Any]:
    root = _project_root(project_root)
    source_paths: set[Path] = set()
    data = _load_project_architecture(root, architecture_path, source_paths)
    declared = collect_declared_files(data, root)
    skipped_links: list[str] = []
    actual = collect_actual_files(root, extensions, DEFAULT_IGNORE_DIRS,
                                  all_files=all_files, skipped_links=skipped_links)
    arch_path = _safe_path(root, str(architecture_path), "架构文件路径", relative=False)
    def identity(relative: str) -> str:
        # normcase follows the host filesystem: Windows aliases such as
        # Core.PY/core.py match, while POSIX keeps distinct case-sensitive names.
        return os.path.normcase(str((root / relative).resolve()))

    metadata = {identity(arch_path.relative_to(root).as_posix()),
                *(identity(item) for item in ("architecture.json", "architecture/index.json", "architecture/_state.json"))}
    # Only successfully loaded authoritative sources are metadata. An unrelated
    # architecture.json or JSON file elsewhere is still an inventory candidate.
    metadata.update(os.path.normcase(str(path.resolve())) for path in source_paths)
    actual = {item for item in actual if identity(item) not in metadata}
    declared_identities = {identity(path) for path in declared}
    # Declaration completeness is deliberately independent of scan scope.
    missing = sorted(item for item in declared if not (root / item).is_file())
    mode = "all-files" if all_files else ("explicit-extensions" if explicit_extensions else "legacy-extensions")
    return {
        "声明但不存在": missing,
        "存在但未登记": sorted(item for item in actual if identity(item) not in declared_identities),
        "已登记代码文件": sorted(declared),
        "扫描范围": {
            "模式": mode,
            "扩展名": None if all_files else sorted(extensions),
            "忽略目录": sorted(DEFAULT_IGNORE_DIRS),
            "忽略文件前缀": list(DEFAULT_IGNORE_FILE_PREFIXES),
            "空文件": "included" if all_files else "excluded",
            "声明文件核查": "all-declared-paths",
            "声明来源": "实现清单与明确树文件槽（文件/文件列表/文件路径/测试文件、架构落位或落位的文件、测试路径对象/有路径结构或实际文件确认的测试引用、文件类型记录）；测试责任标签不作为路径，不从说明、异常、验收或验证责任文本推断",
            "未扫描符号链接目录": sorted(skipped_links),
            "检查内容": "file-inventory-only",
            "架构源文件": sorted(path.resolve().relative_to(root).as_posix() for path in source_paths),
        },
    }


def emit_text(result: dict[str, Any], max_items: int) -> None:
    missing, undocumented = result["声明但不存在"], result["存在但未登记"]
    print(f"文件漂移扫描: 模式 {result['扫描范围']['模式']}, 声明但不存在 {len(missing)} 项, 存在但未登记 {len(undocumented)} 项")
    for label, items in (("声明但不存在", missing), ("存在但未登记", undocumented)):
        print(f"{label}: {len(items)} 项")
        for item in items[:max_items]:
            print(f"  - {item}")
        if len(items) > max_items:
            print(f"  ... 已截断 {len(items) - max_items} 项")
    print("范围说明：声明路径全部核查；仅检查文件清单，不判断文件内容或代码语义。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check project file drift against architecture.json.")
    parser.add_argument("project", type=Path, help="Project root")
    parser.add_argument("--architecture", type=Path, default=Path("architecture.json"), help="Architecture JSON inside project")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all-files", action="store_true", help="Inventory every regular file in scope, without suffix filtering")
    scope.add_argument("--extensions", default=None, help="Filter actual-file inventory only; registered files always checked")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--max-items", type=int, default=80, help="Max text items per section")
    args = parser.parse_args(argv)
    try:
        root = _project_root(args.project)
        architecture_path = args.architecture
        if not architecture_path.is_absolute():
            architecture_path = root / architecture_path
        extensions = set(DEFAULT_EXTENSIONS)
        if args.extensions is not None:
            extensions = {item.strip().lower() for item in args.extensions.split(",") if item.strip()}
            extensions = {item if item.startswith(".") else f".{item}" for item in extensions}
        result = scan_code_drift(root, architecture_path, extensions,
                                 all_files=args.all_files, explicit_extensions=args.extensions is not None)
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_text(result, max(0, args.max_items))
    return 1 if result["声明但不存在"] or result["存在但未登记"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
