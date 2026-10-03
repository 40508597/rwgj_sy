#!/usr/bin/env python3
"""Run explicit argv and bind its result to selected project files.

This tool accepts files of any language or format.  A receipt records an
execution, not a signature, proof of whole-project coverage, or proof that the
command constitutes an effective business test.  Matching before/after hashes
cannot detect an input changed and restored while the command was running.
Timeout terminates the top-level command only, not its entire process tree.
Output is spooled to temporary files so descendants holding inherited output
handles cannot keep this tool waiting on a pipe after the top-level timeout.
``check_receipt`` only reads receipts and inputs; it never executes a receipt.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys
import tempfile
from typing import Any


TOOL_VERSION = "1.0.0"
EXIT_CODES = {"pass": 0, "fail": 1, "unknown": 2}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(project: Path | str) -> Path:
    if "\x00" in str(project):
        raise ValueError("project path contains NUL")
    root = Path(project).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project must be an existing directory")
    return root


def _inside(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError("path escapes project root") from None
    return resolved


def _relative_path(value: str, root: Path) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("input must be a nonempty relative path without NUL")
    portable = value.replace("\\", "/")
    if PurePosixPath(portable).is_absolute() or PureWindowsPath(value).drive:
        raise ValueError("input must be relative to the project")
    return _inside(root / portable, root)


def _same_file(left: Path, right: Path) -> bool:
    if os.path.normcase(str(left)) == os.path.normcase(str(right)):
        return True
    if left.exists() and right.exists():
        return os.path.samefile(left, right)
    return False


def _input_files(root: Path, inputs: list[str]) -> dict[str, Path]:
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("no selected inputs; verification cannot pass")
    files: dict[str, Path] = {}
    for value in inputs:
        path = _relative_path(value, root)
        if not path.is_file():
            raise ValueError(f"input is missing or is not a regular file: {value}")
        if any(_same_file(path, other) for other in files.values()):
            raise ValueError(f"duplicate input: {value}")
        files[path.relative_to(root).as_posix()] = path
    return dict(sorted(files.items()))


def _output_file(root: Path, value: str, files: dict[str, Path]) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("output must be a nonempty path without NUL")
    supplied = Path(value)
    path = _inside(supplied if supplied.is_absolute() else root / supplied, root)
    if path.exists() and not path.is_file():
        raise ValueError("output must not be a directory or special file")
    if any(_same_file(path, item) for item in files.values()):
        raise ValueError("output must not overwrite a selected input")
    return path


def _hash(path: Path) -> str:
    if not path.is_file():
        raise ValueError("selected input is no longer a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _capture(receipt: dict[str, Any], name: str, data: bytes | None) -> None:
    raw = data or b""
    receipt[name] = raw.decode("utf-8", errors="replace")
    receipt[name + "_base64"] = base64.b64encode(raw).decode("ascii")
    receipt[name + "_sha256"] = hashlib.sha256(raw).hexdigest()


def run_verification(project: Path | str, command: list[str], inputs: list[str],
                     timeout: float = 60.0) -> dict[str, Any]:
    """Execute only supplied argv.  All normal input/execution failures are unknown."""
    receipt: dict[str, Any] = {
        "schema_version": 1, "tool_version": TOOL_VERSION,
        "status": "unknown", "returncode": None,
        "command": command, "project": str(project),
        "input_hashes": {}, "after_hashes": {},
        "stdout": "", "stderr": "", "started_at": _now(),
        "finished_at": "", "reason": "", "timed_out": False,
    }
    _capture(receipt, "stdout", b"")
    _capture(receipt, "stderr", b"")
    files: dict[str, Path] = {}
    try:
        root = _root(project)
        receipt["project"] = str(root)
        if (not isinstance(command, list) or not command or not command[0]
                or any(not isinstance(arg, str) or "\x00" in arg
                       for arg in command)):
            raise ValueError("command must be nonempty explicit argv without NUL")
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be positive and finite")
        files = _input_files(root, inputs)
        receipt["input_hashes"] = {key: _hash(path) for key, path in files.items()}
        # Files avoid the unbounded pipe drain that can occur when an orphaned
        # descendant inherits stdout/stderr after the top-level process dies.
        # Temporary files are created inside the selected project, without
        # taking over any input path.  Timed-out output is a snapshot, not a
        # claim that all descendants finished or their future output is known.
        with tempfile.TemporaryFile(mode="w+b", dir=root) as stdout_file, \
                tempfile.TemporaryFile(mode="w+b", dir=root) as stderr_file:
            try:
                result = subprocess.run(command, cwd=root, shell=False,
                                        stdout=stdout_file, stderr=stderr_file,
                                        timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                receipt["timed_out"] = True
                receipt["reason"] = "top-level command timed out; descendants may still be running"
            except (OSError, ValueError, OverflowError) as error:
                receipt["reason"] = f"command could not start: {type(error).__name__}: {error}"
            else:
                receipt["returncode"] = result.returncode
                receipt["status"] = "pass" if result.returncode == 0 else "fail"
                receipt["reason"] = ("command succeeded for selected inputs"
                                      if result.returncode == 0 else "command returned nonzero")
            stdout_file.seek(0)
            stderr_file.seek(0)
            _capture(receipt, "stdout", stdout_file.read())
            _capture(receipt, "stderr", stderr_file.read())
        after: dict[str, str] = {}
        for key, path in files.items():
            try:
                after[key] = _hash(_inside(path, root))
            except (OSError, ValueError, RuntimeError):
                receipt["status"] = "unknown"
                receipt["reason"] = "selected input could not be read after execution"
        receipt["after_hashes"] = after
        if after != receipt["input_hashes"]:
            receipt["status"] = "unknown"
            receipt["reason"] = "selected inputs changed or became unreadable during execution"
    except (OSError, ValueError, RuntimeError, OverflowError) as error:
        receipt["status"] = "unknown"
        receipt["reason"] = f"verification could not complete: {type(error).__name__}: {error}"
    receipt["finished_at"] = _now()
    return receipt


def check_receipt(receipt: dict, project: Path,
                  required_inputs: list[str] | None = None) -> tuple[str, str]:
    """Recheck structure and current input hashes, without running any command.

    This validates local consistency of an unsigned receipt.  The caller must
    decide whether its source and its test command are suitable evidence.
    """
    try:
        root = _root(project)
        if not isinstance(receipt, dict):
            raise ValueError("receipt must be an object")
        if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1:
            raise ValueError("unsupported receipt schema")
        if not isinstance(receipt.get("tool_version"), str) or not receipt["tool_version"]:
            raise ValueError("missing tool version")
        status = receipt.get("status")
        if status not in EXIT_CODES:
            raise ValueError("invalid receipt status")
        recorded_project = receipt.get("project")
        if (not isinstance(recorded_project, str) or "\x00" in recorded_project
                or not Path(recorded_project).is_absolute()
                or _root(recorded_project) != root):
            raise ValueError("receipt project does not match")
        command = receipt.get("command")
        if (not isinstance(command, list) or not command or not command[0]
                or any(not isinstance(arg, str) or "\x00" in arg for arg in command)):
            raise ValueError("invalid command record")
        code = receipt.get("returncode")
        if code is not None and type(code) is not int:
            raise ValueError("invalid return code")
        if "timed_out" in receipt and type(receipt["timed_out"]) is not bool:
            raise ValueError("invalid timeout record")
        if status == "pass" and (code != 0 or receipt.get("timed_out") is True):
            raise ValueError("pass contradicts execution result")
        if status == "fail" and (code is None or code == 0 or receipt.get("timed_out") is True):
            raise ValueError("fail contradicts execution result")
        if not isinstance(receipt.get("reason"), str) or not receipt["reason"]:
            raise ValueError("missing result reason")
        for name in ("stdout", "stderr"):
            if not isinstance(receipt.get(name), str):
                raise ValueError(f"invalid {name} record")
            # External producers may omit raw-byte fields.  If included, all
            # three views must agree so invalid UTF-8 still retains exact bytes.
            if name + "_base64" in receipt or name + "_sha256" in receipt:
                raw = base64.b64decode(receipt[name + "_base64"], validate=True)
                if (hashlib.sha256(raw).hexdigest() != receipt[name + "_sha256"]
                        or raw.decode("utf-8", errors="replace") != receipt[name]):
                    raise ValueError(f"inconsistent {name} record")
        started = datetime.fromisoformat(receipt["started_at"])
        finished = datetime.fromisoformat(receipt["finished_at"])
        if started.tzinfo is None or finished.tzinfo is None or finished < started:
            raise ValueError("invalid execution timestamps")
        hashes = receipt.get("input_hashes")
        after = receipt.get("after_hashes")
        if not isinstance(hashes, dict) or not hashes or not isinstance(after, dict):
            raise ValueError("receipt requires nonempty selected input hashes")
        for mapping in (hashes, after):
            for key, digest in mapping.items():
                if (not isinstance(key, str) or not isinstance(digest, str)
                        or not _SHA256.fullmatch(digest)):
                    raise ValueError("invalid input hash record")
        files = _input_files(root, list(hashes))
        if set(files) != set(hashes):
            raise ValueError("input paths must be canonical project-relative paths")
        if set(after) - set(hashes):
            raise ValueError("after hashes contain unselected inputs")
        if status in ("pass", "fail") and after != hashes:
            raise ValueError("result contradicts before/after input hashes")
        if required_inputs is not None:
            if not isinstance(required_inputs, list):
                raise ValueError("required inputs must be a list")
            if required_inputs:
                required = _input_files(root, required_inputs)
                if not set(required).issubset(files):
                    raise ValueError("receipt does not cover all required inputs")
        current = {key: _hash(path) for key, path in files.items()}
        if current != hashes:
            raise ValueError("selected input hashes are stale")
        return status, receipt["reason"]
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        return "unknown", f"receipt could not be verified: {error}"


def _write_receipt(root: Path, output: str, files: dict[str, Path], receipt: dict) -> Path:
    path = _output_file(root, output, files)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _output_file(root, output, files)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".verification-", suffix=".tmp",
                                         delete=False) as stream:
            temporary = stream.name
            json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        # Recheck after command execution, including paths or links it changed.
        destination = _output_file(root, output, files)
        if destination != path:
            raise ValueError("output path changed while writing receipt")
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return path


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--output", required=True)
    parser.add_argument("--input", dest="inputs", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=60.0)
    if "--" not in arguments:
        parser.error("explicit command argv must follow --")
    separator = arguments.index("--")
    options = parser.parse_args(arguments[:separator])
    command = arguments[separator + 1:]
    try:
        root = _root(options.project)
        files = _input_files(root, options.inputs)
        _output_file(root, options.output, files)
        receipt = run_verification(root, command, options.inputs, options.timeout)
        path = _write_receipt(root, options.output, files, receipt)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"unknown: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": receipt["status"], "receipt": str(path),
                      "reason": receipt["reason"]}, ensure_ascii=False))
    return EXIT_CODES[receipt["status"]]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
