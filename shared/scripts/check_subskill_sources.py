#!/usr/bin/env python3
"""Check local imported-subskill bytes and their declared catalog bindings.

This checker does not fetch repositories or execute imported code. A pass is
consistency with a local, unsigned lock, not authentication of its publisher.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
from pathlib import Path
from typing import Any

import _archlib

_archlib.configure_utf8_stdout()
LOCK = "shared/assets/github-subskills.lock.json"
CATALOG = "shared/assets/capability-catalog.json"
SUBSKILLS = "shared/subskills"
LICENSES = {"MIT", "Apache-2.0", "CC-BY-SA-4.0"}
SHA = re.compile(r"[0-9a-fA-F]{64}\Z")
COMMIT = re.compile(r"[0-9a-fA-F]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)
LIMITS = [
    "Checks local bytes against an unsigned local lock; does not authenticate a remote Git commit, author or reviewer.",
    "Does not execute imported code or prove engineering correctness, actual skill use or license rights beyond the recorded declarations.",
    "Checks the bundled catalog; project overrides and host-provided external skills require their own evidence.",
    "A coordinated replacement of the lock and files is outside this local integrity check.",
]


class Ambiguous(ValueError):
    """JSON cannot have one unambiguous interpretation."""


class Violation(ValueError):
    """A readable declaration or file violates the local contract."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise Violation(f"{label} must be a nonempty string without surrounding whitespace")
    return value


def _relative(value: Any, label: str, *, imported: bool = False) -> str:
    raw = _text(value, label)
    if "\\" in raw or "\x00" in raw or ":" in raw or raw.startswith("/"):
        raise Violation(f"{label} must be a portable package-relative path: {raw}")
    pieces = raw.split("/")
    if any(not p or p in {".", ".."} or p.endswith((".", " ")) or DEVICE.fullmatch(p) for p in pieces):
        raise Violation(f"{label} has an unsafe or ambiguous path component: {raw}")
    if imported and not raw.startswith(SUBSKILLS + "/"):
        raise Violation(f"{label} must be inside {SUBSKILLS}: {raw}")
    return raw


def _reject_link(path: Path) -> None:
    info = path.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
        raise Violation(f"symbolic link or reparse point is not allowed: {path}")


def _bound(root: Path, relative: str) -> Path:
    target = root
    for piece in relative.split("/"):
        target /= piece
        try:
            _reject_link(target)
        except FileNotFoundError as error:
            raise Violation(f"declared file is missing: {relative}") from error
    resolved = target.resolve()
    if not resolved.is_relative_to(root):
        raise Violation(f"declared path escapes package: {relative}")
    return resolved


def _exists_unlinked(root: Path, relative: str) -> bool:
    """Probe absence without silently following a linked ancestor."""
    current = root
    for piece in relative.split("/"):
        current /= piece
        try:
            _reject_link(current)
        except FileNotFoundError:
            return False
    return True


def _json(path: Path) -> Any:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise Ambiguous(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise Ambiguous("non-finite JSON number")
        return parsed

    def constant(value):
        raise Ambiguous(f"non-finite JSON number: {value}")

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_float=number, parse_constant=constant)


def _catalog_root(root: Path, catalog: Path, value: Any) -> Path:
    raw = _text(value, "catalog root")
    if "\\" in raw or "\x00" in raw or ":" in raw or raw.startswith("/"):
        raise Violation("catalog root must be a portable relative path")
    current = catalog.parent
    for piece in raw.split("/"):
        if piece == ".":
            continue
        if piece == "..":
            current = current.parent
        else:
            _relative(piece, "catalog root component")
            current /= piece
            try:
                _reject_link(current)
            except FileNotFoundError as error:
                raise Violation("catalog root is missing") from error
        if not current.is_relative_to(root):
            raise Violation("catalog root escapes package")
    return current.resolve()


def _path_key(path: Path) -> str:
    return path.as_posix().casefold().rstrip("/")


def _check_import_inventory(package: Path, all_files: dict, add) -> None:
    """Every actual imported file must be locked, including archived upstream."""
    try:
        directory = _bound(package, SUBSKILLS)
        pending = [directory]
        actual_files = set()
        while pending:
            current = pending.pop()
            _reject_link(current)
            if current.is_dir():
                pending.extend(current.iterdir())
            elif current.is_file():
                actual_files.add(current.relative_to(package).as_posix())
            else:
                raise Violation(f"unsupported imported filesystem object: {current}")
        unexpected = sorted(actual_files - set(all_files))
        if unexpected:
            add("inventory", "fail", "Imported files are not covered by the lock", paths=unexpected)
        else:
            add("inventory", "pass", "All imported files are covered by the lock")
    except Violation as error:
        add("inventory", "fail", str(error))
    except OSError as error:
        add("inventory", "unknown", f"Cannot inspect the imported file inventory: {error}")


def _check_catalog_bindings(package: Path, declared: dict, add) -> None:
    """Each locked capability must have exactly one independently read binding."""
    try:
        catalog_path = _bound(package, CATALOG)
        catalog = _json(catalog_path)
        if not isinstance(catalog, dict) or not isinstance(catalog.get("entries"), list):
            raise Violation("catalog must be an object with an entries array")
        counts: dict[str, int] = {}
        bound_guides: dict[str, str] = {}
        for position, item in enumerate(catalog["entries"]):
            if not isinstance(item, dict):
                raise Violation(f"catalog entry {position} must be an object")
            identifier = _text(item.get("id"), "catalog id")
            counts[identifier] = counts.get(identifier, 0) + 1
            raw = _text(item.get("entry"), "catalog entry")
            raw_root = _text(item.get("root", "../.."), "catalog root")
            if "\x00" in raw or "\x00" in raw_root:
                raise Violation("catalog paths must not contain NUL")
            candidate = catalog_path.parent / raw_root / raw
            resolved = candidate.resolve()
            prefix = _path_key(package / SUBSKILLS)
            candidate_key, resolved_key = _path_key(candidate.absolute()), _path_key(resolved)
            imported_binding = (candidate_key == prefix or candidate_key.startswith(prefix + "/")
                                or resolved_key == prefix or resolved_key.startswith(prefix + "/"))
            if identifier not in declared and not imported_binding:
                continue
            if identifier not in declared:
                raise Violation(f"catalog imports an unlocked capability: {identifier}")
            source = declared[identifier]
            if (item.get("能力类型") != source.get("capability_type") or item.get("source") != "reference"
                    or raw != source.get("entry")):
                raise Violation(f"catalog binding differs from the locked declaration: {identifier}")
            relative = _relative(raw, "catalog entry", imported=True)
            base = _catalog_root(package, catalog_path, item.get("root", "../.."))
            if base != package:
                raise Violation(f"catalog root resolves to a different package base: {identifier}")
            guide = _bound(base, relative)
            if guide != _bound(package, source["entry"]):
                raise Violation(f"catalog entry resolves to a different guide: {identifier}")
            key = str(guide).casefold()
            if key in bound_guides:
                raise Violation(f"duplicate catalog guide binding: {identifier} and {bound_guides[key]}")
            bound_guides[key] = identifier
        duplicated = sorted(identifier for identifier, count in counts.items() if count != 1)
        if duplicated:
            raise Violation(f"duplicate catalog ids: {duplicated}")
        missing = sorted(set(declared) - set(counts))
        if missing:
            raise Violation(f"locked capabilities are absent from catalog: {missing}")
        add("catalog", "pass", "Every locked capability has exactly one matching bundled catalog binding")
    except Violation as error:
        add("catalog", "fail", str(error))
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
        add("catalog", "unknown", f"Cannot read an unambiguous catalog: {error}")

def evaluate_sources(root: str | Path) -> dict[str, Any]:
    """Return enabled/status/code/checks. Known failures take precedence over unknowns."""
    checks: list[dict[str, Any]] = []
    result: dict[str, Any] = {"enabled": True, "status": "unknown", "code": 2,
                              "checks": checks, "limits": list(LIMITS),
                              "checked_entries": 0, "checked_files": 0}

    def add(identifier, state, reason, **details):
        checks.append({"id": identifier, "status": state, "reason": reason, **details})

    def finish():
        states = {row["status"] for row in checks}
        result["status"] = "fail" if "fail" in states else "unknown" if "unknown" in states else "pass"
        result["code"] = {"pass": 0, "fail": 1, "unknown": 2}[result["status"]]
        return result

    try:
        package = Path(root).absolute()
        _reject_link(package)
        package = package.resolve()
        if not package.is_dir():
            raise OSError("package root is not a directory")
        result["root"] = str(package)
        lock = package / LOCK
        result["lock"] = str(lock)
        if not _exists_unlinked(package, LOCK):
            imported = package / SUBSKILLS
            if _exists_unlinked(package, SUBSKILLS):
                present = not imported.is_dir() or next(imported.iterdir(), None) is not None
            else:
                present = False
            if present:
                add("activation", "unknown", "Imported resources exist but their source lock is missing")
                return finish()
            result.update(enabled=False, status="skipped", code=0)
            add("activation", "skipped", "No source lock or imported resources: checker is not enabled")
            return result
        lock = _bound(package, LOCK)
        document = _json(lock)
    except Violation as error:
        add("activation", "fail", str(error))
        return finish()
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
        add("lock", "unknown", f"Cannot read an unambiguous source lock: {error}")
        return finish()

    if not isinstance(document, dict) or type(document.get("schema_version")) is not int or document.get("schema_version") != 1:
        add("lock-schema", "fail", "Expected an object with integer schema_version=1")
        return finish()
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        add("lock-schema", "fail", "entries must be a nonempty array")
        return finish()
    declared: dict[str, dict[str, Any]] = {}
    all_files: dict[str, str] = {}
    aliases: dict[str, str] = {}
    entry_paths: dict[str, str] = {}
    source_paths: dict[str, str] = {}
    for index, item in enumerate(entries):
        label = f"entry:{index}"
        try:
            if not isinstance(item, dict):
                raise Violation("lock entry must be an object")
            identifier = _text(item.get("id"), "id")
            label = f"entry:{identifier}"
            if identifier in declared:
                raise Violation(f"duplicate lock id: {identifier}")
            declared[identifier] = item
            _text(item.get("capability_type"), "capability_type")
            repo = _text(item.get("repo"), "repo")
            if not REPO.fullmatch(repo) or any(p in {".", ".."} for p in repo.split("/")):
                raise Violation("repo must be owner/name")
            commit = _text(item.get("commit"), "commit")
            if not COMMIT.fullmatch(commit):
                raise Violation("commit must be a 40-character hexadecimal SHA")
            upstream = _relative(item.get("upstream_path"), "upstream_path")
            if "?" in upstream or "#" in upstream:
                raise Violation("upstream_path must not contain URL query or fragment components")
            expected_url = f"https://github.com/{repo}/blob/{commit}/{upstream}"
            if item.get("upstream_url") != expected_url:
                raise Violation("upstream_url does not match repo, commit and upstream_path")
            license_id = item.get("license")
            if not isinstance(license_id, str) or license_id not in LICENSES:
                raise Violation("unsupported or missing SPDX license declaration")
            if repo.lower() == "trailofbits/skills" and license_id != "CC-BY-SA-4.0":
                raise Violation("Trail of Bits source declaration cannot downgrade CC-BY-SA-4.0")
            adaptation = item.get("adaptation")
            if not isinstance(adaptation, dict) or adaptation.get("changed") is not True:
                raise Violation("adaptation.changed must be true")
            _text(adaptation.get("notice"), "adaptation.notice")
            if "license" in adaptation and adaptation["license"] != license_id:
                raise Violation("adaptation license differs from upstream license declaration")
            if license_id == "CC-BY-SA-4.0":
                if adaptation.get("license") != license_id:
                    raise Violation("CC-BY-SA adaptation requires the same structured license")
                author = _text(adaptation.get("upstream_author"), "adaptation.upstream_author")
                if repo.lower() == "trailofbits/skills" and author != "Trail of Bits":
                    raise Violation("Trail of Bits attribution must be retained")
            role_paths = {role: _relative(item.get(role), role, imported=True)
                          for role in ("entry", "source_entry", "license_file")}
            if len({path.casefold() for path in role_paths.values()}) != 3:
                raise Violation("GUIDE, archived source and license must be distinct files")
            if not role_paths["entry"].endswith("/GUIDE.md"):
                raise Violation("adapted entry must be GUIDE.md")
            archive_name = "SOURCE.md" if upstream.split("/")[-1] == "SKILL.md" else upstream.split("/")[-1]
            if role_paths["source_entry"].split("/")[-1] != archive_name:
                raise Violation(f"archived source must retain its filename, with SKILL.md renamed SOURCE.md: {archive_name}")
            physical_roles = [_bound(package, path) for path in role_paths.values()]
            if any(a.samefile(b) for offset, a in enumerate(physical_roles) for b in physical_roles[offset + 1:]):
                raise Violation("GUIDE, archived source and license must not be filesystem aliases")
            for role, bindings in (("entry", entry_paths), ("source_entry", source_paths)):
                key = role_paths[role].casefold()
                if key in bindings:
                    raise Violation(f"duplicate {role} binding: {role_paths[role]}")
                bindings[key] = identifier
            files = item.get("files")
            if not isinstance(files, dict) or not files:
                raise Violation("files must be a nonempty path-to-SHA256 object")
            if any(path not in files for path in role_paths.values()):
                raise Violation("GUIDE, SOURCE and license file must all be covered by files")
            own_aliases = set()
            for raw, expected in files.items():
                relative = _relative(raw, "files path", imported=True)
                key = relative.casefold()
                if key in own_aliases or (key in aliases and aliases[key] != relative):
                    raise Violation(f"duplicate portable path alias: {relative}")
                own_aliases.add(key)
                aliases[key] = relative
                if not isinstance(expected, str) or not SHA.fullmatch(expected):
                    raise Violation(f"invalid SHA256 for {relative}")
                if relative in all_files and all_files[relative].lower() != expected.lower():
                    raise Violation(f"conflicting shared-file hashes: {relative}")
                all_files[relative] = expected
                try:
                    path = _bound(package, relative)
                    if not path.is_file():
                        raise Violation(f"declared resource is not a file: {relative}")
                    data = path.read_bytes()
                    actual = hashlib.sha256(data).hexdigest()
                    if actual != expected.lower():
                        raise Violation(f"locked bytes changed: {relative}")
                    if relative in role_paths.values() and not data.decode("utf-8-sig").strip():
                        raise Violation(f"required source, guide or license is empty: {relative}")
                    result["checked_files"] += 1
                    add(f"file:{identifier}:{relative}", "pass", "Current bytes match the locked SHA256", path=relative)
                except Violation as error:
                    add(f"file:{identifier}:{relative}", "fail", str(error), path=relative)
                except (OSError, UnicodeError) as error:
                    add(f"file:{identifier}:{relative}", "unknown", f"Cannot read the declared resource: {error}", path=relative)
            result["checked_entries"] += 1
            add(label, "pass", "Source identity and adaptation declarations are structurally consistent")
        except Violation as error:
            add(label, "fail", str(error))
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
            add(label, "unknown", f"Cannot finish entry check: {error}")

    _check_import_inventory(package, all_files, add)
    _check_catalog_bindings(package, declared, add)
    return finish()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parents[2]), help="Skill package root")
    parser.add_argument("--json", action="store_true", help="Print the structured report")
    args = parser.parse_args()
    result = evaluate_sources(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"subskill sources: {result['status']} (code {result['code']})")
        for row in result["checks"]:
            if row["status"] in {"fail", "unknown"}:
                print(f"[{row['status']}] {row['id']}: {row['reason']}")
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
