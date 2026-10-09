"""One full native long-task run, plus inexpensive benchmark contract checks."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/benchmark_long_task.py"
spec = importlib.util.spec_from_file_location("benchmark_long_task", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)
ENV = dict(os.environ, **benchmark.ENVIRONMENT)


class LongTaskBenchmarkIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="long-task-benchmark-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        cls.output = cls.work / "result.json"
        cls.process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPT),
            "--skill-root", str(ROOT), "--output", str(cls.output), "--keep-project", str(cls.work / "kept")],
            capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=120)
        cls.result = json.loads(cls.output.read_text(encoding="utf-8"))

    def test_fixed_scenarios_real_business_and_current_gate(self):
        self.assertEqual(self.process.returncode, 0, (self.process.stderr, self.result["scenarios"]))
        self.assertEqual(json.loads(self.process.stdout)["counts"], {"success": 12, "failure": 0, "unknown": 0})
        self.assertEqual(self.result["scenario_ids"], list(benchmark.SCENARIOS))
        self.assertEqual(self.result["scenario_denominator"], 12)
        self.assertEqual([item["id"] for item in self.result["scenarios"]], list(benchmark.SCENARIOS))
        self.assertEqual(self.result["baseline_gate"]["verdict"], "pass")
        self.assertEqual(self.result["modified_gate"]["verdict"], "pass")
        for gate in (self.result["baseline_gate"], self.result["modified_gate"]):
            self.assertTrue(all(stage["status"] == "pass" for stage in gate["stages"]), gate)
            self.assertIn("通用质量", {stage["name"] for stage in gate["stages"]})
        modified = next(step for step in self.result["steps"] if step["label"] == "modified-cli")
        self.assertEqual(json.loads(modified["stdout"])["total_cents"], 324)
        failed = next(step for step in self.result["steps"] if step["label"] == "native-business-receipt" and step["exit_status"] == 1)
        self.assertIn("FAIL", failed["execution_receipt"]["stderr"])
        self.assertEqual(failed["execution_receipt"]["returncode"], 1)

    def test_subprocess_evidence_negative_acceptance_and_explicit_byte_measurement(self):
        steps = self.result["steps"]
        self.assertGreaterEqual(len(steps), 50)
        self.assertEqual([step["sequence"] for step in steps], list(range(1, len(steps) + 1)))
        for step in steps:
            self.assertEqual(step["argv"][1:4], ["-B", "-X", "utf8"])
            self.assertEqual(step["environment"], benchmark.ENVIRONMENT)
            self.assertEqual(step["exit_status"], step["expected_exit_status"], step["label"])
            self.assertIn("before_hashes", step)
            self.assertIn("after_hashes", step)
            self.assertIsInstance(step["stderr"], str)
            self.assertGreater(step["pid"], 0)
        rejects = [step for step in steps if step["label"] == "change.accept" and step["exit_status"] != 0]
        self.assertEqual(len(rejects), 3)
        self.assertEqual(self.result["metrics"]["false_acceptances"], 0)
        self.assertEqual(self.result["metrics"]["recoordination_count"], 1)
        self.assertEqual(self.result["metrics"]["context_bytes_read"], sum(item["bytes"] for item in self.result["context_reads"]))
        self.assertGreater(self.result["metrics"]["context_bytes_read"], 0)
        self.assertNotIn("tokens_saved", self.result["metrics"])
        exports = next(step for step in steps if step["label"] == "handoff.export")
        resumes = next(step for step in steps if step["label"] == "handoff.resume")
        self.assertNotEqual(exports["pid"], resumes["pid"])
        preview = next(step for step in steps if step["label"] == "change.preview")
        self.assertEqual(preview["before_hashes"], preview["after_hashes"])
        stale = next(step for step in steps if step["scenario"] == "stale_execution_receipt_rejected" and step["label"] == "change.verify")
        self.assertEqual(json.loads(stale["stdout"])["status"], "unknown")

    def test_original_hash_recovery_and_independent_editor_bytes_persist(self):
        conflict = self.result["independent_editor_preservation"]
        path = Path(conflict["file"])
        self.assertTrue(conflict["preserved_on_rejection"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), conflict["sha256"])
        self.assertIn(b"independent editor", path.read_bytes())
        restored = self.result["recovery_result"]
        self.assertEqual(restored["status"], "restored")
        self.assertTrue(restored["registered_original_hashes_restored"])
        self.assertTrue(restored["unregistered_editor_bytes_preserved"])
        root = Path(restored["project"])
        self.assertEqual((root / "independent.txt").read_bytes(), b"independent unregistered bytes\n")
        self.assertEqual((root / "catalog/prices.py").read_text(encoding="utf-8"), benchmark.business_sources(True)["catalog/prices.py"])
        self.assertEqual((Path(self.result["project"]) / "catalog/prices.py").read_bytes(), (root / "catalog/prices.py").read_bytes())
        self.assertGreater(self.result["metrics"]["recovery_seconds"], 0)


class LongTaskBenchmarkContract(unittest.TestCase):
    def test_same_untuned_fixture_can_target_two_skill_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            left, right = base / "left", base / "right"
            self.assertEqual(benchmark.fixture(left), benchmark.fixture(right))
            self.assertEqual(benchmark.snapshot(left), benchmark.snapshot(right))
            self.assertNotIn("architecture/toolchain", benchmark.snapshot(left))
            original = benchmark.business_sources()
            changed = benchmark.business_sources(True)
            self.assertEqual(set(original), set(changed))
            self.assertEqual(original["orders/service.py"], changed["orders/service.py"])
            self.assertEqual(original["cli.py"], changed["cli.py"])

    def test_keep_project_rejects_existing_directory_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sentinel = root / "sentinel.txt"
            sentinel.write_bytes(b"independent existing data")
            process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPT),
                "--report", str(root / "result.json"), "--keep-project", str(root)],
                capture_output=True, text=True, encoding="utf-8", env=ENV, timeout=10)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(sentinel.read_bytes(), b"independent existing data")
            self.assertFalse((root / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
