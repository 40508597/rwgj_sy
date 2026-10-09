#!/usr/bin/env python3
"""Run explicit byte-patch fault fixtures against a checker in isolated copies.

Language neutral: patches arbitrary bytes and consumes a checker JSON contract.
This is not a syntax mutation generator or an operating-system security sandbox.
Commands must be explicitly authorized; copying changes cwd, not process rights.
Only a passing baseline followed by the expected check's failure is detected.
Timeout stops the top-level process only; descendants may remain running. Output
is spooled to log files so inherited handles cannot prolong a pipe drain.
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


class ProbeInputError(ValueError):
    """Unsafe path or invalid suite contract, optionally with a copy preflight."""

    def __init__(self, message: str, *, copy_scope: dict | None = None):
        super().__init__(message)
        self.copy_scope = copy_scope


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path, counters: dict | None = None) -> str:
    """Hash large artifacts incrementally; do not hold an entire dependency in RAM."""
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
            if counters is not None:
                counters["bytes_hashed"] += len(chunk)
    if counters is not None:
        counters["files_hashed"] += 1
    return value.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _no_links(path: Path) -> None:
    """Reject symlinks and Windows junction/reparse points, including ancestors."""
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ProbeInputError(f"links/reparse points are not allowed: {candidate}")


def _child(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ProbeInputError("input path must be a nonempty relative path")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized or ".." in normalized.split("/"):
        raise ProbeInputError(f"absolute or escaping path is not allowed: {value!r}")
    candidate = root / normalized
    _no_links(candidate)
    resolved = candidate.resolve()
    canonical_root = root.resolve()
    if not _inside(resolved, canonical_root) or resolved == canonical_root:
        raise ProbeInputError(f"path is outside the project: {value!r}")
    return resolved


def _snapshot(root: Path, counters: dict | None = None) -> dict[str, str]:
    result: dict[str, str] = {}
    _no_links(root)
    def walk_error(exc: OSError) -> None:
        raise exc
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        for name in dirs + files:
            _no_links(Path(directory) / name)
        for name in sorted(files):
            path = Path(directory) / name
            if not path.is_file():
                raise ProbeInputError(f"special file is not supported: {path}")
            result[path.relative_to(root).as_posix()] = _file_hash(path, counters)
    return dict(sorted(result.items()))


def _snapshot_hash(snapshot: dict[str, str]) -> str:
    return _hash(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode())


def _patterns(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ProbeInputError(f"{label} must be {'a nonempty' if nonempty else 'an'} array")
    result = []
    for pattern in value:
        if not isinstance(pattern, str) or not pattern.strip() or "\x00" in pattern:
            raise ProbeInputError(f"{label} requires nonempty relative patterns")
        pattern = pattern.replace("\\", "/").rstrip("/")
        if not pattern or pattern.startswith("/") or ":" in pattern or any(part in ("", ".", "..") for part in pattern.split("/")):
            raise ProbeInputError(f"{label} pattern escapes or is not canonical: {pattern!r}")
        if pattern in result:
            raise ProbeInputError(f"{label} contains duplicate patterns")
        result.append(pattern)
    return result


def _matches(relative: str, pattern: str) -> bool:
    """Component globs; literal directories include descendants, ** any depth."""
    if not any(char in pattern for char in "*?["):
        return relative == pattern or relative.startswith(pattern + "/")
    target = relative.split("/")
    reachable = {0}
    for part in pattern.split("/"):
        if not reachable:
            return False
        if part == "**":
            reachable = set(range(min(reachable), len(target) + 1))
        else:
            reachable = {index + 1 for index in reachable
                         if index < len(target) and fnmatch.fnmatchcase(target[index], part)}
    return len(target) in reachable


def _excluded(relative: str, patterns: list[str]) -> bool:
    # An excluded directory also excludes its descendants, including when the
    # directory itself matched a wildcard rather than a literal path.
    parts = relative.split("/")
    return any(_matches("/".join(parts[:end]), pattern)
               for end in range(1, len(parts) + 1) for pattern in patterns)


def _copy_selection(project: Path, suite_path: Path, document: dict,
                    cases: list[dict], snapshot: dict[str, str]) -> tuple[dict, set[str], dict]:
    """Select explicit copy inputs; budgets reject before creating any workspace."""
    raw = document.get("copy_scope", {})
    if not isinstance(raw, dict) or set(raw) - {"include", "exclude", "max_files", "max_bytes"}:
        raise ProbeInputError("copy_scope must be an object with include/exclude/max_files/max_bytes only")
    include = _patterns(raw.get("include", ["**"]), "copy_scope.include", nonempty=True)
    exclude = _patterns(raw.get("exclude", []), "copy_scope.exclude")
    for name in ("max_files", "max_bytes"):
        if name in raw and (type(raw[name]) is not int or raw[name] <= 0):
            raise ProbeInputError(f"copy_scope.{name} must be a positive integer")
    selected = {rel: value for rel, value in snapshot.items()
                if any(_matches(rel, pattern) for pattern in include) and not _excluded(rel, exclude)}
    required = {suite_path.relative_to(project).as_posix(),
                *(_child(project, case["input"]).relative_to(project).as_posix() for case in cases)}
    if required - set(selected):
        raise ProbeInputError(f"copy_scope omits suite or mutation inputs: {sorted(required - set(selected))}")
    sizes = {rel: (project / rel).stat().st_size for rel in selected}
    total_bytes = sum(sizes.values())
    directories = set()
    for directory, dirs, _ in os.walk(project, followlinks=False):
        for name in dirs:
            rel = (Path(directory) / name).relative_to(project).as_posix()
            if any(_matches(rel, pattern) for pattern in include) and not _excluded(rel, exclude):
                directories.add(rel)
    for rel in (*selected, *directories):
        directories.update(parent.as_posix() for parent in Path(rel).parents if parent != Path('.'))
    report = {"mode": "full" if set(selected) == set(snapshot) else "explicit-subset",
              "include": include, "exclude": exclude, "files_total": len(snapshot),
              "files_selected": len(selected), "bytes_per_copy": total_bytes,
              "max_files": raw.get("max_files"), "max_bytes": raw.get("max_bytes"),
              "budget_unit": "selected files and bytes per independent project copy",
              "selected_input_hashes": selected, "selected_sha256": _snapshot_hash(selected),
              "omitted_files": sorted(set(snapshot) - set(selected)),
              "directories_selected": sorted(directories),
              "maximum_copies": 2 * len(cases), "maximum_copy_bytes": 2 * len(cases) * total_bytes,
              "complete_project_file_scope": set(selected) == set(snapshot)}
    exceeded = len(selected) > raw.get("max_files", len(selected)) or total_bytes > raw.get("max_bytes", total_bytes)
    report["budget_status"] = "exceeded" if exceeded else "pass"
    if exceeded:
        raise ProbeInputError(f"copy_scope budget exceeded: {len(selected)} files, {total_bytes} bytes per copy",
                              copy_scope=report)
    return selected, directories, report


def _copy_project(project: Path, destination: Path, snapshot: dict[str, str],
                  directories: set[str], counters: dict) -> None:
    """Create an independent writable copy; never hardlink to shared inputs."""
    def ignore(directory: str, names: list[str]) -> list[str]:
        parent = Path(directory).relative_to(project)
        return [name for name in names if (parent / name).as_posix() not in snapshot
                and (parent / name).as_posix() not in directories]
    def copy_file(source: str, target: str) -> str:
        copied = shutil.copy2(source, target)
        counters["files_copied"] += 1
        counters["bytes_copied"] += Path(copied).stat().st_size
        return copied
    counters["copy_attempts"] += 1
    shutil.copytree(project, destination, ignore=ignore, copy_function=copy_file)
    counters["copies_completed"] += 1
    if _snapshot(destination, counters) != snapshot:
        raise ProbeInputError("project changed while copying selected inputs")


def _patch_bytes(case: dict, project: Path) -> tuple[bytes, bytes]:
    before = _child(project, case["input"]).read_bytes()
    old, new = base64.b64decode(case["old_base64"]), base64.b64decode(case["new_base64"])
    if before.find(old) == -1 or before.find(old) != before.rfind(old):
        raise ProbeInputError("old bytes must occur exactly once")
    return before, before.replace(old, new, 1)


def _classify_probe(entry: dict, case: dict, baseline: Path, mutant: Path, folder: Path) -> None:
    """Keep baseline validity, mutant outcome and checker contract independent."""
    entry["baseline"] = _run(case, baseline, folder, "baseline")
    good = entry["baseline"]
    if good["checker_status"] != "pass" or good["target_status"] != "pass":
        entry.update(outcome="invalid", reason="normal baseline did not pass the expected check")
        return
    entry["mutant"] = _run(case, mutant, folder, "mutant")
    bad = entry["mutant"]
    if bad["checker_status"] == "fail" and bad["target_status"] == "fail":
        entry.update(outcome="detected", reason="expected check detected the injected fault")
    elif bad["checker_status"] == "unknown" or bad["target_status"] == "unknown":
        entry.update(outcome="unknown", reason="mutant check unavailable, inconsistent, or unsuccessful")
    else:
        entry.update(outcome="missed", reason="expected check did not detect the injected fault")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ProbeInputError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _json(text: str) -> Any:
    def invalid_constant(value: str) -> Any:
        raise ProbeInputError(f"nonfinite JSON value: {value}")
    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ProbeInputError(f"JSON number is outside the finite supported range: {value}")
        return number
    return json.loads(text, object_pairs_hook=_object, parse_constant=invalid_constant,
                      parse_float=finite_float)


def validate_suite(value: Any, project: Path) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ProbeInputError("suite schema_version must be integer 1")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ProbeInputError("suite cases must be a nonempty list")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ProbeInputError("each case must be an object")
        ident = case.get("id")
        if not isinstance(ident, str) or not ident.strip() or ident in ids:
            raise ProbeInputError("case id must be nonempty and unique")
        ids.add(ident)
        source = _child(project, case.get("input"))
        if not source.is_file():
            raise ProbeInputError(f"case {ident}: input is not a file")
        for key in ("old_base64", "new_base64"):
            encoded = case.get(key)
            if not isinstance(encoded, str):
                raise ProbeInputError(f"case {ident}: {key} must be base64 text")
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, UnicodeError) as exc:
                raise ProbeInputError(f"case {ident}: invalid {key}") from exc
            if key == "old_base64" and not decoded:
                raise ProbeInputError(f"case {ident}: old bytes must not be empty")
        if case["old_base64"] == case["new_base64"] or base64.b64decode(case["old_base64"]) == base64.b64decode(case["new_base64"]):
            raise ProbeInputError(f"case {ident}: patch must change bytes")
        if not isinstance(case.get("check_id"), str) or not case["check_id"].strip():
            raise ProbeInputError(f"case {ident}: check_id must be nonempty")
        command = case.get("command")
        if (not isinstance(command, list) or not command or not command[0]
                or any(not isinstance(a, str) or "\x00" in a for a in command)):
            raise ProbeInputError(f"case {ident}: command must be a nonempty argv list")
        timeout = case.get("timeout", 30)
        if type(timeout) not in (int, float) or not 0 < timeout <= 3600 or not math.isfinite(timeout):
            raise ProbeInputError(f"case {ident}: timeout must be in (0, 3600]")
    return cases


def _result_contract(value: Any, rc: int | None, check_id: str) -> tuple[str, str | None, str]:
    if not isinstance(value, dict):
        return "unknown", None, "checker output is not an object"
    status = value.get("status")
    code = value.get("code")
    codes = {"pass": 0, "fail": 1, "unknown": 2}
    if not isinstance(status, str) or status not in codes or type(code) is not int or code != codes[status] or rc != code:
        return "unknown", None, "checker status/code/process return code disagree"
    checks = value.get("checks")
    if not isinstance(checks, list) or not checks:
        return "unknown", None, "checker checks are missing"
    ids: set[str] = set()
    target = None
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids or not isinstance(item.get("status"), str) or item["status"] not in codes:
            return "unknown", None, "invalid or duplicate checker check"
        if "required" in item and type(item["required"]) is not bool:
            return "unknown", None, "checker required must be a boolean"
        ids.add(item["id"])
        if item["id"] == check_id:
            target = item["status"]
    if target is None:
        return "unknown", None, "expected check is missing"
    if status == "pass" and any(item.get("required", True) and item["status"] != "pass" for item in checks):
        return "unknown", None, "passing checker contains nonpassing required checks"
    return status, target, ""


def _run(case: dict[str, Any], copy: Path, logs: Path, label: str) -> dict[str, Any]:
    command = [arg.replace("{project}", str(copy)) for arg in case["command"]]
    outcome: dict[str, Any] = {"command": command, "cwd": str(copy), "timeout": case.get("timeout", 30), "returncode": None}
    stdout_path, stderr_path = logs / f"{label}.stdout.log", logs / f"{label}.stderr.log"
    with stdout_path.open("w+b") as stdout_file, stderr_path.open("w+b") as stderr_file:
        try:
            proc = subprocess.run(command, cwd=copy, shell=False, stdout=stdout_file, stderr=stderr_file, timeout=outcome["timeout"])
            outcome["returncode"] = proc.returncode
        except subprocess.TimeoutExpired:
            outcome["error"] = "timeout"
            outcome["timeout_note"] = "top-level process timed out; descendants may still be running"
        except (OSError, ValueError) as exc:
            outcome["error"] = str(exc)
        # Read only the observed byte count: descendants can retain these file
        # handles and produce later output. Timed-out logs are a snapshot.
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(os.fstat(stdout_file.fileno()).st_size)
        stderr = stderr_file.read(os.fstat(stderr_file.fileno()).st_size)
    outcome.update({"stdout": stdout.decode("utf-8", errors="replace"), "stderr": stderr.decode("utf-8", errors="replace"), "stdout_log": str(logs / f"{label}.stdout.log"), "stderr_log": str(logs / f"{label}.stderr.log")})
    try:
        value = _json(stdout.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        outcome.update({"checker_status": "unknown", "target_status": None, "contract_error": str(exc)})
    else:
        status, target, reason = _result_contract(value, outcome["returncode"], case["check_id"])
        outcome.update({"output": value, "checker_status": status, "target_status": target, "contract_error": reason})
    return outcome


def run_suite(project: Path, suite_path: Path, workspace: Path) -> dict[str, Any]:
    for path in (project, suite_path, workspace):
        _no_links(path.absolute())
    project, suite_path, workspace = project.resolve(), suite_path.resolve(), workspace.resolve()
    if not project.is_dir() or not _inside(suite_path, project) or not suite_path.is_file():
        raise ProbeInputError("project must exist and suite must be a file inside it")
    if _inside(workspace.resolve(), project) or workspace.exists() or not workspace.parent.is_dir():
        raise ProbeInputError("workspace must be new, outside project, with an existing parent")
    suite_bytes = suite_path.read_bytes()
    document = _json(suite_bytes.decode("utf-8-sig"))
    cases = validate_suite(document, project)
    work = {"copy_attempts": 0, "copies_completed": 0, "files_copied": 0, "bytes_copied": 0,
            "files_hashed": 0, "bytes_hashed": 0}
    snapshot = _snapshot(project, work)
    if snapshot.get(suite_path.relative_to(project).as_posix()) != _hash(suite_bytes):
        raise ProbeInputError("suite changed while taking the original project snapshot")
    selected, directories, scope = _copy_selection(project, suite_path, document, cases, snapshot)
    workspace.mkdir(exist_ok=False)
    report: dict[str, Any] = {"schema_version": 1, "kind": "explicit-byte-fault-probes", "project": str(project), "suite": str(suite_path), "suite_sha256": _hash(suite_bytes), "project_sha256": _snapshot_hash(snapshot), "cases_total": len(cases), "cases": [], "limitations": ["Explicit fixture byte patches, not an automatic syntax mutation generator.", "Isolated project copies, not an operating-system security sandbox.", "Checker JSON is an external observation; hashes bind artifacts but do not authenticate a checker.", "Timeout stops the top-level process only; descendants may remain running and logs are an output snapshot."]}
    report["copy_scope"] = scope
    report["work"] = work
    report["original_guard_scope"] = "complete project file tree, including omitted copy inputs"
    if not scope["complete_project_file_scope"]:
        report["limitations"].append("Explicit copy scope omits listed project files; results certify only the selected copied inputs, not omitted dependencies.")
    for index, case in enumerate(cases, 1):
        folder = workspace / f"case-{index:04d}"
        folder.mkdir()
        entry: dict[str, Any] = {"id": case["id"], "check_id": case["check_id"], "input": case["input"], "old_base64": case["old_base64"], "new_base64": case["new_base64"], "project_sha256": report["project_sha256"], "outcome": "unknown"}
        report["cases"].append(entry)
        try:
            baseline, mutant = folder / "baseline", folder / "mutant"
            if _snapshot(project, work) != snapshot:
                raise ProbeInputError("original project changed during the run")
            # Invalid patches need no writable project copies. They still remain
            # in the report and in the fixed denominator as invalid samples.
            try:
                before, after = _patch_bytes(case, project)
            except ProbeInputError as exc:
                entry.update(outcome="invalid", reason=str(exc))
                continue
            entry["before_sha256"] = _hash(before)
            entry["after_sha256"] = _hash(after)
            for destination in (baseline, mutant):
                _copy_project(project, destination, selected, directories, work)
            source = _child(mutant, case["input"])
            if source.read_bytes() != before:
                raise ProbeInputError("mutation input changed while preparing copies")
            source.write_bytes(after)
            _classify_probe(entry, case, baseline, mutant, folder)

        except (OSError, ValueError, shutil.Error) as exc:
            entry.update({"outcome": "unknown", "reason": str(exc)})
        finally:
            (folder / "result.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    counts = {name: sum(item["outcome"] == name for item in report["cases"]) for name in ("detected", "missed", "invalid", "unknown")}
    report["counts"] = counts
    report["detection_rate"] = counts["detected"] / report["cases_total"]
    try:
        report["original_unchanged"] = _snapshot(project, work) == snapshot
    except (OSError, ValueError) as exc:
        report["original_unchanged"] = False
        report["original_error"] = str(exc)
    report["status"] = "fail" if counts["missed"] else "unknown" if counts["invalid"] or counts["unknown"] or not report["original_unchanged"] else "pass"
    report["code"] = {"pass": 0, "fail": 1, "unknown": 2}[report["status"]]
    report["checks"] = [{"id": item["id"], "status": "pass" if item["outcome"] == "detected" else "fail" if item["outcome"] == "missed" else "unknown"} for item in report["cases"]]
    report["report_path"] = str(workspace / "report.json")
    (workspace / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    suite = args.suite if args.suite.is_absolute() else args.project / args.suite
    try:
        report = run_suite(args.project, suite, args.workspace)
    except (OSError, ValueError) as exc:
        report = {"schema_version": 1, "status": "unknown", "code": 2, "checks": [], "error": str(exc)}
        if isinstance(exc, ProbeInputError) and exc.copy_scope is not None:
            report["copy_scope"] = exc.copy_scope
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(f"fault probes: {report['status']}")
        if "error" in report:
            print(report["error"])
        else:
            print(f"detected {report['counts']['detected']}/{report['cases_total']}; {report['counts']}")
            print(report["report_path"])
    return report["code"]


if __name__ == "__main__":
    raise SystemExit(main())
