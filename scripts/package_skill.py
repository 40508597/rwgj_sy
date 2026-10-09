#!/usr/bin/env python3
"""Build a byte-preserving runtime/development distribution, or verify its manifest.

The builder never overwrites an existing directory. Runtime keeps all shared tools,
references, assets, adapted guides and locked sources; development keeps the test
and maintainer material too. Generated caches and historical reports are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

MANIFEST = "skill-distribution.json"
GENERATED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
RUNTIME_ROOTS = {"SKILL.md", "LICENSE", "THIRD-PARTY-NOTICES.md", "verify-all.sh"}
RUNTIME_DIRS = ("skills/", "agents/", "shared/scripts/", "shared/references/",
                "shared/assets/", "shared/subskills/")
LINK = re.compile(r"\]\(([^)\n]+)\)")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PackageError(ValueError):
    """The selected package or output cannot be safely interpreted."""


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _no_link(path: Path) -> None:
    info = path.lstat()
    if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
        raise PackageError(f"links/reparse points are not package inputs: {path}")


def _files(root: Path, *, source: bool) -> dict[str, Path]:
    _no_link(root)
    result: dict[str, Path] = {}
    aliases: set[str] = set()
    def walk_error(error: OSError) -> None:
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = sorted(name for name in dirs if name not in GENERATED_DIRS)
        for name in dirs:
            _no_link(Path(directory) / name)
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if name.endswith((".pyc", ".pyo")):
                continue
            if source and (name == MANIFEST or relative == ".source.json"
                           or (name.startswith("verification-report-") and name.endswith(".md"))):
                continue
            _no_link(path)
            if not path.is_file():
                raise PackageError(f"not a regular package file: {path}")
            alias = relative.casefold()
            if alias in aliases:
                raise PackageError(f"duplicate portable path: {relative}")
            aliases.add(alias)
            result[relative] = path
    return result


def _runtime_selection(source: Path, available: dict[str, Path]) -> set[str]:
    selected = {name for name in available
                if name in RUNTIME_ROOTS or name.startswith(RUNTIME_DIRS)}
    # Follow actual maintained Markdown file links. Archived third-party examples
    # use their original repository conventions and are covered by the source lock.
    pending = sorted(selected)
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        if not name.endswith(".md") or name.startswith("shared/subskills/upstream/"):
            continue
        path = available[name]
        for match in LINK.finditer(path.read_text(encoding="utf-8-sig")):
            raw = match[1].strip()
            if raw.startswith("<") and ">" in raw:
                raw = raw[1:raw.index(">")]
            else:
                raw = raw.split(' "', 1)[0]
            if not raw or raw.startswith(("#", "/")) or ":" in raw or "<" in raw:
                continue
            raw = raw.split("#", 1)[0].split("?", 1)[0]
            target = (path.parent / raw).resolve()
            if not _inside(target, source) or not target.suffix:
                continue
            relative = target.relative_to(source).as_posix()
            if relative not in available:
                raise PackageError(f"unavailable runtime reference: {name} -> {raw}")
            if relative not in selected:
                selected.add(relative)
                pending.append(relative)
    return selected


def _payload_hash(files: dict[str, str]) -> str:
    return _hash(json.dumps(files, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8"))


def build(source: Path, output: Path, profile: str = "runtime") -> dict:
    source, output = source.resolve(), output.absolute()
    if profile not in {"runtime", "development"}:
        raise PackageError("profile must be runtime or development")
    if output.exists() or output.is_symlink():
        raise PackageError("output already exists; build into a new directory")
    if _inside(output.resolve(), source) or _inside(source, output.resolve()):
        raise PackageError("output and source must not contain each other")
    if not output.parent.is_dir():
        raise PackageError("output parent must already exist")
    _no_link(output.parent)
    available = _files(source, source=True)
    if not RUNTIME_ROOTS.difference({"verify-all.sh"}) <= set(available):
        raise PackageError("source must contain SKILL.md, LICENSE and THIRD-PARTY-NOTICES.md")
    selected = set(available) if profile == "development" else _runtime_selection(source, available)
    snapshot = {name: available[name].read_bytes() for name in sorted(selected)}
    hashes = {name: _hash(data) for name, data in snapshot.items()}
    output.mkdir(exist_ok=False)
    for name, data in snapshot.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        destination.chmod(stat.S_IMODE(available[name].stat().st_mode))
    if any(_hash(available[name].read_bytes()) != digest for name, digest in hashes.items()):
        raise PackageError("source changed during build; incomplete output has no valid manifest")
    manifest = {"schema_version": 1, "profile": profile, "files": hashes,
                "payload_sha256": _payload_hash(hashes),
                "limits": ["Hashes bind bytes; they do not authenticate an author or prove behavior.",
                           "Generated caches are outside the distribution payload."]}
    (output / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    return {"status": "pass", "code": 0, "operation": "package-build", "profile": profile,
            "output": str(output), "files": len(hashes),
            "payload_bytes": sum(map(len, snapshot.values())),
            "payload_sha256": manifest["payload_sha256"],
            "manifest": str(output / MANIFEST)}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def verify(root: Path) -> dict:
    root = root.resolve()
    actual = _files(root, source=False)
    if MANIFEST not in actual:
        raise PackageError("distribution manifest is missing")
    manifest = json.loads(actual.pop(MANIFEST).read_text(encoding="utf-8-sig"),
                          object_pairs_hook=_unique_object)
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1 or not isinstance(manifest.get("profile"), str)
            or manifest["profile"] not in {"runtime", "development"}):
        raise PackageError("unsupported distribution manifest")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected or "SKILL.md" not in expected:
        raise PackageError("manifest files must be nonempty and include SKILL.md")
    aliases: set[str] = set()
    for name, digest in expected.items():
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name or "\x00" in name
                or name.startswith("/") or any(p in {".", ".."} for p in name.split("/"))
                or PurePosixPath(name).as_posix() != name or name.casefold() in aliases
                or name == MANIFEST or not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            raise PackageError(f"invalid manifest entry: {name!r}")
        aliases.add(name.casefold())
    if manifest.get("payload_sha256") != _payload_hash(expected):
        raise PackageError("manifest payload digest is inconsistent")
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual)
                     if _hash(actual[name].read_bytes()) != expected[name])
    status = "fail" if missing or extra or changed else "pass"
    return {"status": status, "code": 1 if status == "fail" else 0,
            "operation": "package-verify", "root": str(root), "profile": manifest["profile"],
            "files": len(expected), "missing": missing, "extra": extra, "changed": changed,
            "payload_sha256": manifest["payload_sha256"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path, help="new output directory, outside the source")
    action.add_argument("--verify", type=Path, help="verify an existing distribution")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--profile", choices=("runtime", "development"), default="runtime")
    args = parser.parse_args(argv)
    try:
        result = verify(args.verify) if args.verify is not None else build(args.source, args.output, args.profile)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        result = {"status": "unknown", "code": 2, "reason": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result["code"]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
