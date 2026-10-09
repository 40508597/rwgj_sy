"""Execution-evidence checks use arbitrary files, explicit argv, and real subprocesses."""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


PACKAGE = Path(os.environ.get("TASKARCH_PACKAGE", str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(PACKAGE / "shared/scripts"))
import run_verification as runner


class VerificationReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="verification-test-", dir=PACKAGE.parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.input = self.root / "任意工程.custom-format"
        self.input.write_bytes(b"original project bytes\x00\xff")
        self.inputs = [self.input.name]

    def command(self, code):
        return [sys.executable, "-B", "-c", code]

    def receipt(self, code="print('verified')", **kwargs):
        return runner.run_verification(self.root, self.command(code), self.inputs, **kwargs)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(PACKAGE / "shared/scripts/run_verification.py"),
                               str(self.root), *args], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, encoding="utf-8", timeout=15)

    def test_arbitrary_binary_input_success_and_required_input_check(self):
        result = self.receipt()
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["input_hashes"], result["after_hashes"])
        self.assertEqual(runner.check_receipt(result, self.root, self.inputs)[0], "pass")

    def test_command_runs_in_project_and_preserves_stdout_stderr(self):
        result = self.receipt("import os,sys; print(os.getcwd()); sys.stderr.write('err\\n')")
        self.assertEqual(Path(result["stdout"].strip()), self.root)
        self.assertEqual(result["stderr"], "err" + os.linesep)
        self.assertEqual(runner.check_receipt(result, self.root)[0], "pass")

    def test_invalid_utf8_output_retains_exact_bytes(self):
        result = self.receipt("import sys; sys.stdout.buffer.write(b'\\xff\\x00full'); "
                              "sys.stderr.buffer.write(b'\\xfeother')")
        self.assertEqual(base64.b64decode(result["stdout_base64"]), b"\xff\x00full")
        self.assertEqual(base64.b64decode(result["stderr_base64"]), b"\xfeother")
        self.assertEqual(runner.check_receipt(result, self.root)[0], "pass")

    def test_nonzero_exit_fails_and_can_be_rechecked(self):
        result = self.receipt("import sys; print('failed'); sys.exit(7)")
        self.assertEqual((result["status"], result["returncode"]), ("fail", 7))
        self.assertEqual(runner.check_receipt(result, self.root)[0], "fail")

    def test_timeout_is_unknown_with_partial_output(self):
        result = self.receipt("import time; print('started', flush=True); time.sleep(5)", timeout=0.3)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["returncode"])
        self.assertTrue(result["timed_out"])
        self.assertIn("started", result["stdout"])

    def test_missing_executable_is_unknown(self):
        result = runner.run_verification(self.root, [str(self.root / "missing-program")], self.inputs)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["returncode"])

    def test_changed_input_is_unknown_even_when_command_succeeds(self):
        code = f"from pathlib import Path; Path({self.input.name!r}).write_bytes(b'changed')"
        result = self.receipt(code)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["returncode"], 0)
        self.assertNotEqual(result["input_hashes"], result["after_hashes"])

    def test_deleted_input_is_unknown(self):
        result = self.receipt(f"from pathlib import Path; Path({self.input.name!r}).unlink()")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["after_hashes"], {})

    def test_empty_inputs_do_not_execute(self):
        marker = self.root / "should-not-exist"
        result = runner.run_verification(self.root,
            self.command("from pathlib import Path; Path('should-not-exist').touch()"), [])
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(marker.exists())

    def test_invalid_inputs_are_rejected_before_execution(self):
        cases = [[self.input.name, self.input.name], ["."], ["missing"],
                 ["../outside"], [str(self.input)], ["bad\x00path"], ["C:\\outside"]]
        marker_code = "from pathlib import Path; Path('should-not-exist').touch()"
        for inputs in cases:
            with self.subTest(inputs=inputs):
                result = runner.run_verification(self.root, self.command(marker_code), inputs)
                self.assertEqual(result["status"], "unknown")
                self.assertFalse((self.root / "should-not-exist").exists())

    def test_invalid_timeout_and_command_are_rejected(self):
        for timeout in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout):
                self.assertEqual(self.receipt(timeout=timeout)["status"], "unknown")
        for command in ([], ["bad\x00command"], [1]):
            with self.subTest(command=command):
                self.assertEqual(runner.run_verification(self.root, command, self.inputs)["status"], "unknown")

    def test_receipt_becomes_unknown_when_current_inputs_change(self):
        result = self.receipt()
        self.input.write_bytes(b"later changes")
        self.assertEqual(runner.check_receipt(result, self.root)[0], "unknown")

    def test_required_inputs_must_all_be_covered(self):
        other = self.root / "second.project"
        other.write_bytes(b"second")
        result = self.receipt()
        self.assertEqual(runner.check_receipt(result, self.root, [*self.inputs, other.name])[0], "unknown")

    def test_receipt_project_must_match(self):
        result = self.receipt()
        result["project"] = str(self.root.parent)
        self.assertEqual(runner.check_receipt(result, self.root)[0], "unknown")

    def test_malformed_or_contradictory_receipts_are_unknown(self):
        result = self.receipt()
        mutations = [{"schema_version": True}, {"status": "invalid"}, {"returncode": 1},
                     {"returncode": False}, {"timed_out": True}, {"timed_out": "false"}, {"input_hashes": {}},
                     {"after_hashes": {}}, {"command": []}, {"stdout": 5},
                     {"stdout_sha256": "0" * 64}, {"started_at": "invalid"},
                     {"finished_at": "2000-01-01T00:00:00+00:00"},
                     {"input_hashes": {"../escape": "a" * 64}}]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                damaged = copy.deepcopy(result)
                damaged.update(mutation)
                self.assertEqual(runner.check_receipt(damaged, self.root)[0], "unknown")

    def test_receipt_checker_never_executes_recorded_command(self):
        result = self.receipt()
        result["command"] = self.command("from pathlib import Path; Path('not-executed').touch()")
        self.assertEqual(runner.check_receipt(result, self.root)[0], "pass")
        self.assertFalse((self.root / "not-executed").exists())

    def test_cli_writes_nested_receipt_and_returns_pass(self):
        result = self.cli("--output", "evidence/run.json", "--input", self.input.name,
                          "--timeout", "5", "--", *self.command("print('ok')"))
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads((self.root / "evidence/run.json").read_text(encoding="utf-8"))
        self.assertEqual(runner.check_receipt(receipt, self.root)[0], "pass")

    def test_cli_failure_and_unknown_exit_codes(self):
        cases = (("import sys; sys.exit(8)", 1, "5", "fail", False),
                 ("import time; time.sleep(3)", 2, "0.2", "unknown", True))
        for code, expected, timeout, status, timed_out in cases:
            with self.subTest(code=code):
                result = self.cli("--output", "run.json", "--input", self.input.name,
                                  "--timeout", timeout, "--", *self.command(code))
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertTrue((self.root / "run.json").is_file())
                receipt = json.loads((self.root / "run.json").read_text(encoding="utf-8"))
                self.assertEqual(receipt["status"], status)
                self.assertEqual(receipt["timed_out"], timed_out)
                if not timed_out:
                    self.assertEqual(receipt["returncode"], 8)

    def test_output_escape_directory_and_input_overwrite_do_not_run(self):
        before = self.input.read_bytes()
        code = "from pathlib import Path; Path('should-not-exist').touch()"
        for output in ("../escaped.json", ".", self.input.name, "bad\x00path"):
            with self.subTest(output=output):
                # main accepts NUL as an in-process argument; OS argv cannot.
                exit_code = runner.main([str(self.root), "--output", output,
                                         "--input", self.input.name, "--", *self.command(code)])
                self.assertEqual(exit_code, 2)
                self.assertFalse((self.root / "should-not-exist").exists())
                self.assertEqual(self.input.read_bytes(), before)

    def test_hardlinked_output_must_not_overwrite_input(self):
        linked = self.root / "linked-receipt.json"
        try:
            os.link(self.input, linked)
        except OSError as error:
            self.skipTest(f"hardlinks unavailable: {error}")
        with self.assertRaises(ValueError):
            runner._output_file(self.root, linked.name, runner._input_files(self.root, self.inputs))

    def test_symlinked_input_cannot_escape_project(self):
        outside = self.root.parent / (self.root.name + "-outside")
        outside.write_bytes(b"outside")
        self.addCleanup(outside.unlink)
        link = self.root / "external-link"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        result = runner.run_verification(self.root, self.command("print('not-run')"), [link.name])
        self.assertEqual(result["status"], "unknown")

    def test_argv_metacharacters_are_passed_as_literal_argument(self):
        literal = "hello & echo redirected > unexpected.txt"
        command = self.command("import sys; print(sys.argv[1])") + [literal]
        result = runner.run_verification(self.root, command, self.inputs)
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["stdout"].strip(), literal)
        self.assertFalse((self.root / "unexpected.txt").exists())

    def test_empty_argument_is_preserved(self):
        command = self.command("import sys; print(repr(sys.argv[1]))") + [""]
        result = runner.run_verification(self.root, command, self.inputs)
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["stdout"].strip(), "''")
        self.assertEqual(runner.check_receipt(result, self.root)[0], "pass")

    def test_timeout_does_not_wait_for_descendants_holding_output(self):
        code = ("import subprocess,sys,time; "
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)']); "
                "print('parent-started', flush=True); time.sleep(5)")
        started = time.monotonic()
        try:
            result = self.receipt(code, timeout=0.3)
            elapsed = time.monotonic() - started
            self.assertEqual(result["status"], "unknown")
            self.assertTrue(result["timed_out"])
            self.assertLess(elapsed, 1.5, "must not drain a pipe held by an orphaned descendant")
        finally:
            # We explicitly do not claim to terminate the process tree.  Let
            # the harmless sleeping child close inherited handles before the
            # test's project directory is removed on Windows.
            time.sleep(2.2)

    def test_output_replaced_with_input_hardlink_during_command_is_rejected(self):
        code = f"import os; os.link({self.input.name!r}, 'run.json')"
        before = self.input.read_bytes()
        result = self.cli("--output", "run.json", "--input", self.input.name,
                          "--", *self.command(code))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.input.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
