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
    """Unsafe path or invalid suite contract."""


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _snapshot(root: Path) -> dict[str, str]:
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
            result[path.relative_to(root).as_posix()] = _hash(path.read_bytes())
    return dict(sorted(result.items()))


def _snapshot_hash(snapshot: dict[str, str]) -> str:
    return _hash(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode())


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
    cases = validate_suite(_json(suite_bytes.decode("utf-8-sig")), project)
    snapshot = _snapshot(project)
    workspace.mkdir(exist_ok=False)
    report: dict[str, Any] = {"schema_version": 1, "kind": "explicit-byte-fault-probes", "project": str(project), "suite": str(suite_path), "suite_sha256": _hash(suite_bytes), "project_sha256": _snapshot_hash(snapshot), "cases_total": len(cases), "cases": [], "limitations": ["Explicit fixture byte patches, not an automatic syntax mutation generator.", "Isolated project copies, not an operating-system security sandbox.", "Checker JSON is an external observation; hashes bind artifacts but do not authenticate a checker.", "Timeout stops the top-level process only; descendants may remain running and logs are an output snapshot."]}
    for index, case in enumerate(cases, 1):
        folder = workspace / f"case-{index:04d}"
        folder.mkdir()
        entry: dict[str, Any] = {"id": case["id"], "check_id": case["check_id"], "input": case["input"], "old_base64": case["old_base64"], "new_base64": case["new_base64"], "project_sha256": report["project_sha256"], "outcome": "unknown"}
        report["cases"].append(entry)
        try:
            baseline, mutant = folder / "baseline", folder / "mutant"
            if _snapshot(project) != snapshot:
                raise ProbeInputError("original project changed during the run")
            shutil.copytree(project, baseline)
            shutil.copytree(project, mutant)
            if _snapshot(baseline) != snapshot or _snapshot(mutant) != snapshot:
                raise ProbeInputError("project changed while copying")
            source = _child(mutant, case["input"])
            before = source.read_bytes()
            old, new = base64.b64decode(case["old_base64"]), base64.b64decode(case["new_base64"])
            entry["before_sha256"] = _hash(before)
            if before.find(old) == -1 or before.find(old) != before.rfind(old):
                entry.update({"outcome": "invalid", "reason": "old bytes must occur exactly once"})
                continue
            after = before.replace(old, new, 1)
            source.write_bytes(after)
            entry["after_sha256"] = _hash(source.read_bytes())
            if entry["before_sha256"] == entry["after_sha256"]:
                entry.update({"outcome": "invalid", "reason": "patch did not change input hash"})
                continue
            entry["baseline"] = _run(case, baseline, folder, "baseline")
            good = entry["baseline"]
            if good["checker_status"] != "pass" or good["target_status"] != "pass":
                entry.update({"outcome": "invalid", "reason": "normal baseline did not pass the expected check"})
                continue
            entry["mutant"] = _run(case, mutant, folder, "mutant")
            bad = entry["mutant"]
            if bad["checker_status"] == "fail" and bad["target_status"] == "fail":
                entry.update({"outcome": "detected", "reason": "expected check detected the injected fault"})
            elif bad["checker_status"] == "unknown" or bad["target_status"] == "unknown":
                entry.update({"outcome": "unknown", "reason": "mutant check unavailable, inconsistent, or unsuccessful"})
            else:
                entry.update({"outcome": "missed", "reason": "expected check did not detect the injected fault"})
        except (OSError, ValueError, shutil.Error) as exc:
            entry.update({"outcome": "unknown", "reason": str(exc)})
        finally:
            (folder / "result.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    counts = {name: sum(item["outcome"] == name for item in report["cases"]) for name in ("detected", "missed", "invalid", "unknown")}
    report["counts"] = counts
    report["detection_rate"] = counts["detected"] / report["cases_total"]
    try:
        report["original_unchanged"] = _snapshot(project) == snapshot
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
