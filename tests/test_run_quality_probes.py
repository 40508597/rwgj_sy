"""Real isolated fault fixtures: arbitrary bytes, checker failures, and paths."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared" / "scripts"))
import run_quality_probes as probes


FIXTURE = '''import json, sys, time
from pathlib import Path
root = Path.cwd()
bad = b"BAD" in (root / "input.易工程").read_bytes()
mode = (root / "mode.txt").read_text()
status = "fail" if bad else "pass"
code = 1 if bad else 0
target = status
checks = [{"id": "boundary", "status": target}]
if mode == "optional-unknown": checks.append({"id": "optional", "status": "unknown", "required": False})
if mode == "baseline-fail":
    status, code = "fail", 1
    checks[0]["status"] = "fail"
if bad:
    if mode == "miss": status, code, checks = "pass", 0, [{"id": "boundary", "status": "pass"}]
    if mode == "unrelated": checks = [{"id": "boundary", "status": "pass"}, {"id": "other", "status": "fail"}]
    if mode == "unknown": status, code, checks = "unknown", 2, [{"id": "boundary", "status": "unknown"}]
    if mode == "crash": raise RuntimeError("fixture crash")
    if mode == "timeout": time.sleep(3)
    if mode == "malformed": print("not json"); sys.exit(1)
    if mode == "mismatch": code = 3
    if mode == "missing": checks = [{"id": "other", "status": "fail"}]
    if mode == "duplicate": checks.append(checks[0].copy())
print(json.dumps({"status": status, "code": code, "checks": checks}))
sys.exit(code)
'''


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


class TestRealProbes(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.project = self.base / "工程 with spaces"
        self.project.mkdir()
        (self.project / "input.易工程").write_bytes(b"\x00prefix OK! suffix\xff")
        (self.project / "mode.txt").write_text("detect", encoding="utf-8")
        (self.project / "checker.py").write_text(FIXTURE, encoding="utf-8")
        self.case = {"id": "case-1", "input": "input.易工程", "old_base64": b64(b"OK!"), "new_base64": b64(b"BAD"), "check_id": "boundary", "command": [sys.executable, "{project}/checker.py"]}
        self.suite = self.project / "suite.json"
        self.workspace = self.base / "new-results"

    def write_suite(self, cases=None, **extra):
        value = {"schema_version": 1, "cases": [self.case] if cases is None else cases}
        value.update(extra)
        self.suite.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def run_mode(self, mode="detect", **case_values):
        (self.project / "mode.txt").write_text(mode, encoding="utf-8")
        self.case.update(case_values)
        self.write_suite()
        return probes.run_suite(self.project, self.suite, self.workspace)

    def test_binary_arbitrary_extension_detected_and_original_unchanged(self):
        before = (self.project / "input.易工程").read_bytes()
        result = self.run_mode()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["counts"], {"detected": 1, "missed": 0, "invalid": 0, "unknown": 0})
        case = result["cases"][0]
        self.assertNotEqual(case["before_sha256"], case["after_sha256"])
        self.assertEqual(case["baseline"]["returncode"], 0)
        self.assertEqual(case["mutant"]["returncode"], 1)
        self.assertTrue(Path(case["mutant"]["stdout_log"]).is_file())
        self.assertTrue((self.workspace / "report.json").is_file())
        self.assertEqual((self.project / "input.易工程").read_bytes(), before)
        self.assertTrue(result["original_unchanged"])

    def test_missed_is_failure(self):
        result = self.run_mode("miss")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["cases"][0]["outcome"], "missed")

    def test_optional_unknown_does_not_invalidate_passing_baseline(self):
        result = self.run_mode("optional-unknown")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["cases"][0]["outcome"], "detected")

    def test_contract_allows_optional_nonpass_and_defaults_missing_required_to_true(self):
        for optional_status in ("fail", "unknown"):
            with self.subTest(optional_status=optional_status):
                checks = [{"id": "boundary", "status": "pass"}, {"id": "optional", "status": optional_status, "required": False}]
                value = {"status": "pass", "code": 0, "checks": checks}
                self.assertEqual(probes._result_contract(value, 0, "boundary")[:2], ("pass", "pass"))
                del checks[1]["required"]
                self.assertEqual(probes._result_contract(value, 0, "boundary")[0], "unknown")
                checks[1]["required"] = True
                self.assertEqual(probes._result_contract(value, 0, "boundary")[0], "unknown")

    def test_contract_rejects_nonboolean_required_even_when_check_passes(self):
        for required in (None, 0, 1, "false", []):
            with self.subTest(required=required):
                value = {"status": "pass", "code": 0, "checks": [{"id": "boundary", "status": "pass", "required": required}]}
                self.assertEqual(probes._result_contract(value, 0, "boundary")[0], "unknown")

    def test_timeout_output_is_spooled_to_files_without_pipe_drain(self):
        def simulate_timeout(command, **kwargs):
            self.assertNotIn("capture_output", kwargs)
            self.assertFalse(kwargs["shell"])
            self.assertNotEqual(kwargs["stdout"], subprocess.PIPE)
            kwargs["stdout"].write(b"partial fixture output")
            kwargs["stdout"].flush()
            kwargs["stderr"].write(b"fixture diagnostic")
            kwargs["stderr"].flush()
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        with patch.object(probes.subprocess, "run", side_effect=simulate_timeout):
            result = probes._run(self.case, self.project, self.base, "spool")
        self.assertEqual(result["error"], "timeout")
        self.assertEqual(result["stdout"], "partial fixture output")
        self.assertEqual(result["stderr"], "fixture diagnostic")
        self.assertIn("descendants", result["timeout_note"])
        self.assertEqual(result["checker_status"], "unknown")

    def test_unrelated_failure_is_not_detection(self):
        result = self.run_mode("unrelated")
        self.assertEqual(result["cases"][0]["outcome"], "missed")
        self.assertEqual(result["detection_rate"], 0)

    def test_nonpassing_baseline_is_invalid_and_mutant_not_run(self):
        result = self.run_mode("baseline-fail")
        self.assertEqual(result["cases"][0]["outcome"], "invalid")
        self.assertNotIn("mutant", result["cases"][0])
        self.assertEqual(result["code"], 2)

    def test_crash_unknown_bad_json_missing_duplicate_and_mismatch_never_detected(self):
        for mode in ("crash", "unknown", "malformed", "missing", "duplicate", "mismatch"):
            with self.subTest(mode=mode):
                self.workspace = self.base / f"results-{mode}"
                result = self.run_mode(mode)
                self.assertEqual(result["cases"][0]["outcome"], "unknown")
                self.assertEqual(result["counts"]["detected"], 0)

    def test_timeout_never_detected(self):
        result = self.run_mode("timeout", timeout=1)
        self.assertEqual(result["cases"][0]["outcome"], "unknown")
        self.assertEqual(result["cases"][0]["mutant"]["error"], "timeout")

    def test_patch_absent_repeated_and_overlapping_invalid(self):
        for index, payload in enumerate((b"not present", b"OK!OK!", b"aaa")):
            with self.subTest(payload=payload):
                (self.project / "input.易工程").write_bytes(payload)
                self.workspace = self.base / f"patch-{index}"
                self.case["old_base64"] = b64(b"aa" if payload == b"aaa" else b"OK!")
                result = self.run_mode()
                self.assertEqual(result["cases"][0]["outcome"], "invalid")
                self.assertNotIn("baseline", result["cases"][0])

    def test_fixed_denominator_includes_invalid_case(self):
        second = {**self.case, "id": "case-2", "old_base64": b64(b"absent")}
        self.write_suite([self.case, second])
        result = probes.run_suite(self.project, self.suite, self.workspace)
        self.assertEqual(result["cases_total"], 2)
        self.assertEqual(len(result["cases"]), 2)
        self.assertEqual(result["detection_rate"], 0.5)
        self.assertEqual(result["code"], 2)

    def test_rejects_existing_and_inside_workspace(self):
        self.write_suite()
        for workspace in (self.project / "results", self.project, self.base):
            with self.subTest(workspace=workspace):
                with self.assertRaises(probes.ProbeInputError):
                    probes.run_suite(self.project, self.suite, workspace)

    def test_rejects_suite_outside_project(self):
        outside = self.base / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        with self.assertRaises(probes.ProbeInputError):
            probes.run_suite(self.project, outside, self.workspace)

    def test_rejects_path_escapes_and_absolute_paths(self):
        for path in ("../outside", "..\\outside", "/tmp/file", "C:/file", "input\x00bad"):
            with self.subTest(path=path):
                self.case["input"] = path
                self.write_suite()
                with self.assertRaises(probes.ProbeInputError):
                    probes.run_suite(self.project, self.suite, self.workspace)

    def test_rejects_duplicate_ids_and_invalid_schema(self):
        for value in ({"schema_version": 1, "cases": [self.case, self.case]}, {"schema_version": True, "cases": [self.case]}, {"schema_version": 1, "cases": []}):
            with self.subTest(value=value):
                with self.assertRaises(probes.ProbeInputError):
                    probes.validate_suite(value, self.project)

    def test_rejects_bad_base64_same_patch_empty_old_command_and_timeout(self):
        for updates in ({"old_base64": "%%%"}, {"old_base64": ""}, {"new_base64": self.case["old_base64"]}, {"command": "python checker.py"}, {"command": []}, {"timeout": True}, {"timeout": float("nan")}, {"timeout": 0}):
            with self.subTest(updates=updates):
                with self.assertRaises(probes.ProbeInputError):
                    probes.validate_suite({"schema_version": 1, "cases": [{**self.case, **updates}]}, self.project)

    def test_rejects_symlinks_in_project_and_output(self):
        link = self.project / "linked"
        try:
            link.symlink_to(self.project / "input.易工程")
        except (OSError, NotImplementedError):
            self.skipTest("symlink privilege unavailable; reparse guard covered separately")
        self.write_suite()
        with self.assertRaises(probes.ProbeInputError):
            probes.run_suite(self.project, self.suite, self.workspace)
        link.unlink()
        alias = self.base / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(probes.ProbeInputError):
            probes.run_suite(self.project, self.suite, alias / "results")

    def test_reparse_point_guard_rejects_windows_junction_attribute(self):
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=0, st_file_attributes=0x400)):
            with self.assertRaises(probes.ProbeInputError):
                probes._no_links(self.project)

    def test_workspace_cannot_be_reused_after_success(self):
        self.run_mode()
        with self.assertRaises(probes.ProbeInputError):
            probes.run_suite(self.project, self.suite, self.workspace)

    def test_missing_executable_baseline_is_invalid_and_saved(self):
        result = self.run_mode(command=[str(self.base / "nonexistent-executable")])
        self.assertEqual(result["cases"][0]["outcome"], "invalid")
        self.assertIn("error", result["cases"][0]["baseline"])
        self.assertTrue((self.workspace / "report.json").is_file())

    def test_contract_rejects_unhashable_status_bool_code_duplicate_and_missing_checks(self):
        invalid = ({"status": [], "code": 0, "checks": []}, {"status": "pass", "code": False, "checks": [{"id": "boundary", "status": "pass"}]}, {"status": "pass", "code": 0, "checks": [{"id": "boundary", "status": []}]}, {"status": "pass", "code": 0, "checks": [{"id": "boundary", "status": "fail"}]})
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(probes._result_contract(value, 0, "boundary")[0], "unknown")

    def test_json_duplicate_keys_and_nonfinite_rejected(self):
        for value in ('{"status":"pass", "status":"fail"}', '{"n":NaN}'):
            with self.assertRaises(probes.ProbeInputError):
                probes._json(value)

    def test_cli_json_returns_real_status(self):
        self.write_suite()
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            rc = probes.main([str(self.project), "--suite", "suite.json", "--workspace", str(self.workspace), "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(stream.getvalue())["status"], "pass")


if __name__ == "__main__":
    unittest.main()
