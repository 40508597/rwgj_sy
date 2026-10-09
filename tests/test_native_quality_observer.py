"""Real Node/CommonJS scenario observations, not fabricated parser facts.

The optional example measures selected runtime-load edges only. Business and
interface regressions are measured separately by an actual scenario execution
receipt; they are not advertised as native contract or CRAP observations.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

PACKAGE = Path(os.environ.get("TASKARCH_PACKAGE", str(Path(__file__).resolve().parents[1])))
OBSERVER = PACKAGE / "shared/assets/quality-observers/node-runtime-observer.cjs"
NODE = shutil.which("node")
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
SOURCE_FILES = {
    "orders.cjs": "const prices = require('./prices.cjs');\nconst tax = require('./tax.cjs');\n"
                  "exports.total = lines => tax.add(prices.sum(lines));\n",
    "prices.cjs": "exports.sum = lines => lines.reduce((sum, line) => sum + line.price * line.quantity, 0);\n",
    "tax.cjs": "exports.add = value => Math.round(value * 1.1);\n",
    "checkout-scenario.cjs": "const assert = require('node:assert/strict');\n"
                             "function run() {\n"
                             "  const { total } = require('./orders.cjs');\n"
                             "  assert.equal(total([{price: 100, quantity: 3}]), 330);\n"
                             "  console.log('checkout total=330');\n"
                             "}\nmodule.exports = run;\n"
                             "if (require.main === module) {\n"
                             "  try { run(); } catch (error) { console.error(error.stack); process.exitCode = 1; }\n"
                             "}\n",
}


@unittest.skipUnless(NODE, "Node.js is missing; real native observation tests were not executed")
class NativeQualityObserver(unittest.TestCase):
    def setUp(self):
        evidence = os.environ.get("TASKARCH_NATIVE_EVIDENCE")
        if evidence:
            self.root = Path(evidence) / "projects" / f"{self._testMethodName}-{uuid.uuid4().hex[:8]}"
            self.root.mkdir(parents=True)
        else:
            temporary = tempfile.TemporaryDirectory(prefix="taskarch-real-node-")
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        for rel, text in SOURCE_FILES.items():
            (self.root / rel).write_text(text, encoding="utf-8")
        example = OBSERVER.with_name("node-runtime-observer.config.example.json")
        self.config = json.loads(example.read_text(encoding="utf-8"))
        self.config["source_id"] = "observed"
        self.save_config()
        scope = ["orders", "prices", "tax"]
        self.boundary = {"id": "boundary", "check": "dependency", "required": True,
                         "source": "observed", "scope": scope, "kind": "runtime-load",
                         "allow": [["orders", "prices"], ["orders", "tax"]]}
        self.cycle = {"id": "cycle", "check": "acyclic", "required": True,
                      "source": "observed", "scope": scope, "kind": "runtime-load"}
        self.sequence = 0

    def save_config(self):
        (self.root / "observer.json").write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")

    def invoke(self, argv, expected=None):
        self.sequence += 1
        # Every captured record binds the exact inputs at invocation time.
        selected = {rel: hashlib.sha256((self.root / rel).read_bytes()).hexdigest()
                    for rel in [*SOURCE_FILES, "observer.json"] if (self.root / rel).is_file()}
        completed = subprocess.run(argv, cwd=self.root, env=ENV, capture_output=True,
                                   encoding="utf-8", timeout=40)
        record = {"command": list(map(str, argv)), "cwd": str(self.root), "input_hashes": selected,
                  "stdout": completed.stdout, "stderr": completed.stderr, "exit_status": completed.returncode}
        (self.root / f"command-{self.sequence:02}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertNotIn("Traceback", completed.stderr, record)
        if expected is not None:
            self.assertEqual(completed.returncode, expected, record)
        return completed

    def observe(self, expected=0):
        process = self.invoke([NODE, str(OBSERVER), str(self.root), "observer.json",
                               "architecture/quality/facts.json", "architecture/quality/node-raw.json"], expected)
        report = json.loads(process.stdout)
        self.assertEqual(report["code"], process.returncode, report)
        return report

    def check(self, rules, expected):
        quality = self.root / "architecture/quality"
        quality.mkdir(parents=True, exist_ok=True)
        (quality / "policy.json").write_text(json.dumps({"schema_version": 1, "rules": rules}), encoding="utf-8")
        completed = self.invoke([sys.executable, "-B", "-X", "utf8",
                                 str(PACKAGE / "shared/scripts/check_project_quality.py"), str(self.root), "--json"], expected)
        report = json.loads(completed.stdout)
        self.assertEqual(report["code"], expected, report)
        return report

    def target(self, report, name, expected):
        item = next(item for item in report["checks"] if item["id"] == name)
        self.assertEqual(item["status"], expected, report)
        return item

    def mutate(self, rel, before, after):
        file = self.root / rel
        text = file.read_text(encoding="utf-8")
        self.assertEqual(text.count(before), 1)
        file.write_text(text.replace(before, after), encoding="utf-8")

    def execution_rule(self):
        return {"id": "checkout-execution", "check": "execution", "required": True,
                "receipt": "architecture/quality/checkout-receipt.json", "inputs": list(SOURCE_FILES),
                "command": [NODE, "checkout-scenario.cjs"]}

    def run_business(self, expected=0):
        command = [sys.executable, "-B", "-X", "utf8", str(PACKAGE / "shared/scripts/run_verification.py"),
                   str(self.root), "--output", "architecture/quality/checkout-receipt.json"]
        for rel in SOURCE_FILES:
            command.extend(["--input", rel])
        command.extend(["--timeout", "10", "--", NODE, "checkout-scenario.cjs"])
        return self.invoke(command, expected)

    def test_real_commonjs_baseline_and_raw_snapshot(self):
        self.observe()
        report = self.check([self.boundary, self.cycle], 0)
        self.target(report, "boundary", "pass")
        self.target(report, "cycle", "pass")
        facts = json.loads((self.root / "architecture/quality/facts.json").read_text(encoding="utf-8"))
        raw = json.loads((self.root / "architecture/quality/node-raw.json").read_text(encoding="utf-8"))
        source = facts["sources"][0]
        self.assertEqual(source["origin"], "observed")
        self.assertIn("Node v", source["tool"]["version"])
        self.assertEqual(source["capabilities"], ["dependencies:runtime-load"])
        self.assertEqual(set(source["scope"]), {"orders", "prices", "tax"})
        self.assertEqual({(edge["from"], edge["to"], edge["kind"]) for edge in facts["dependencies"]},
                         {("orders", "prices", "runtime-load"), ("orders", "tax", "runtime-load")})
        self.assertEqual(raw["returncode"], 0)
        self.assertEqual(raw["stdout"], "checkout total=330\n")
        self.assertEqual(raw["stderr"], "")
        self.assertTrue(raw["complete"])
        self.assertTrue(raw["snapshot"]["observed"])
        self.assertEqual(raw["input_hashes"], raw["input_hashes_after"])
        self.assertEqual(facts["metrics"], [])  # No invented CRAP inputs.
        self.assertNotIn("contracts", facts)

    def test_forbidden_runtime_dependency_is_detected_without_crash(self):
        self.observe()
        self.target(self.check([self.boundary], 0), "boundary", "pass")
        self.mutate("prices.cjs", "exports.sum", "require('./tax.cjs');\nexports.sum")
        self.observe()
        item = self.target(self.check([self.boundary], 1), "boundary", "fail")
        self.assertIn({"from": "prices", "to": "tax", "kind": "runtime-load"}, item["findings"])

    def test_runtime_cycle_is_detected_without_scenario_failure(self):
        self.observe()
        self.target(self.check([self.cycle], 0), "cycle", "pass")
        self.mutate("tax.cjs", "exports.add", "require('./orders.cjs');\nexports.add")
        self.observe()
        item = self.target(self.check([self.cycle], 1), "cycle", "fail")
        self.assertEqual(set(item["findings"][0]["cycle"]), {"orders", "tax"})

    def test_business_error_is_detected_by_real_execution_not_observer_crash(self):
        self.observe()
        self.run_business()
        rule = self.execution_rule()
        self.target(self.check([rule], 0), rule["id"], "pass")
        self.mutate("tax.cjs", "value * 1.1", "value * 1.2")
        self.run_business(1)
        self.target(self.check([rule], 1), rule["id"], "fail")
        receipt = json.loads((self.root / rule["receipt"]).read_text(encoding="utf-8"))
        self.assertIn("AssertionError", receipt["stderr"])

    def test_export_regression_is_only_execution_evidence(self):
        self.observe()
        self.run_business()
        rule = self.execution_rule()
        self.target(self.check([rule], 0), rule["id"], "pass")
        self.mutate("orders.cjs", "exports.total", "exports.renamedTotal")
        self.run_business(1)
        self.target(self.check([rule], 1), rule["id"], "fail")
        receipt = json.loads((self.root / rule["receipt"]).read_text(encoding="utf-8"))
        self.assertIn("TypeError", receipt["stderr"])

    def test_stale_observed_input_is_unknown(self):
        self.observe()
        self.mutate("prices.cjs", "sum + line.price", "sum + 2 * line.price")
        self.target(self.check([self.boundary], 2), "boundary", "unknown")

    def test_stale_configuration_is_unknown(self):
        self.observe()
        self.config["timeout_ms"] += 1
        self.save_config()
        self.target(self.check([self.boundary], 2), "boundary", "unknown")

    def test_missing_selected_file_is_unknown(self):
        self.observe()
        (self.root / "tax.cjs").unlink()
        self.observe(2)
        self.target(self.check([self.boundary], 2), "boundary", "unknown")

    def test_real_worker_timeout_is_unknown(self):
        self.config["timeout_ms"] = 100
        self.save_config()
        self.mutate("checkout-scenario.cjs", "const { total }", "while (true) {}\n  const { total }")
        self.observe(2)
        self.target(self.check([self.boundary], 2), "boundary", "unknown")
        raw = json.loads((self.root / "architecture/quality/node-raw.json").read_text(encoding="utf-8"))
        self.assertFalse(raw["complete"])
        self.assertIsNone(raw["snapshot"])

    def test_omitted_loaded_module_is_unknown(self):
        self.config["modules"] = self.config["modules"][:2]
        self.save_config()
        self.observe(2)
        # All configured observations are still incomplete, not an empty pass.
        self.boundary["scope"] = ["orders", "prices"]
        self.target(self.check([self.boundary], 2), "boundary", "unknown")

    def test_declared_unexecuted_module_is_unknown(self):
        (self.root / "unused.cjs").write_text("exports.neverCalled = 1;\n", encoding="utf-8")
        self.config["modules"].append({"id": "unused", "file": "unused.cjs"})
        self.config["inputs"].append("unused.cjs")
        self.save_config()
        self.observe(2)
        self.target(self.check([self.boundary], 2), "boundary", "unknown")

    def test_missing_runner_input_rejects_before_execution(self):
        self.config["inputs"].remove("checkout-scenario.cjs")
        self.save_config()
        report = self.observe(2)
        self.assertIn("omitted", report["errors"][0])
        self.assertFalse((self.root / "architecture/quality/facts.json").exists())

    def test_duplicate_json_key_rejects_before_execution(self):
        file = self.root / "observer.json"
        file.write_text(file.read_text(encoding="utf-8").replace('"source_id": "observed"',
                        '"source_id": "observed", "source_id": "shadowed"'), encoding="utf-8")
        self.assertIn("duplicate JSON key", self.observe(2)["errors"][0])

    def test_nested_duplicate_json_key_rejects_before_execution(self):
        file = self.root / "observer.json"
        file.write_text(file.read_text(encoding="utf-8").replace('"id": "orders"',
                        '"id": "orders", "id": "shadowed"'), encoding="utf-8")
        self.assertIn("duplicate JSON key", self.observe(2)["errors"][0])

    def test_duplicate_module_or_input_rejects_before_execution(self):
        cases = []
        duplicate_id = copy.deepcopy(self.config)
        duplicate_id["modules"][1]["id"] = "orders"
        cases.append(duplicate_id)
        duplicate_file = copy.deepcopy(self.config)
        duplicate_file["modules"][1]["file"] = "orders.cjs"
        cases.append(duplicate_file)
        duplicate_input = copy.deepcopy(self.config)
        duplicate_input["inputs"].append("orders.cjs")
        cases.append(duplicate_input)
        for config in cases:
            with self.subTest(config=config):
                self.config = config
                self.save_config()
                self.assertIn("duplicate", self.observe(2)["errors"][0])

    def test_out_of_project_path_rejects_before_execution(self):
        self.config["modules"][0]["file"] = "../outside.cjs"
        self.save_config()
        self.assertIn("project-relative path", self.observe(2)["errors"][0])

    def test_command_declaration_is_rejected_not_executed(self):
        marker = self.root / "should-not-exist"
        self.config["command"] = [NODE, "-e", f"require('node:fs').writeFileSync({json.dumps(str(marker))},'ran')"]
        self.save_config()
        self.assertIn("unsupported field command", self.observe(2)["errors"][0])
        self.assertFalse(marker.exists())

    def test_failed_scenario_is_incomplete_not_detected_quality(self):
        self.mutate("checkout-scenario.cjs", "assert.equal(total", "throw new Error('scenario failed');\n  assert.equal(total")
        self.observe(2)
        self.target(self.check([self.boundary], 2), "boundary", "unknown")
        raw = json.loads((self.root / "architecture/quality/node-raw.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["returncode"], 1)
        self.assertIn("scenario failed", raw["stderr"])

    def test_worker_exit_without_snapshot_is_unknown(self):
        self.mutate("checkout-scenario.cjs", "const { total }", "process.exit(7);\n  const { total }")
        self.observe(2)
        self.target(self.check([self.boundary], 2), "boundary", "unknown")
        raw = json.loads((self.root / "architecture/quality/node-raw.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["returncode"], 7)
        self.assertIsNone(raw["snapshot"])

    def test_output_cannot_overwrite_selected_input(self):
        before = (self.root / "orders.cjs").read_bytes()
        completed = self.invoke([NODE, str(OBSERVER), str(self.root), "observer.json", "orders.cjs", "raw.json"], 2)
        self.assertIn("must not overwrite", completed.stdout)
        self.assertEqual((self.root / "orders.cjs").read_bytes(), before)

    def test_existing_hardlinked_outputs_preserve_inputs_and_old_reports(self):
        for case in ("facts-input", "raw-input", "facts-raw"):
            with self.subTest(case=case):
                directory = self.root / case
                directory.mkdir()
                facts, raw = directory / "facts.json", directory / "raw.json"
                selected = self.root / "prices.cjs"
                if case == "facts-input":
                    os.link(selected, facts)
                    raw.write_bytes(b"prior raw report")
                elif case == "raw-input":
                    os.link(selected, raw)
                    facts.write_bytes(b"prior facts report")
                else:
                    facts.write_bytes(b"prior shared report")
                    os.link(facts, raw)
                watched = [self.root / name for name in SOURCE_FILES] + [self.root / "observer.json", facts, raw]
                before = {str(file): file.read_bytes() for file in watched}
                completed = self.invoke([NODE, str(OBSERVER), str(self.root), "observer.json",
                                         f"{case}/facts.json", f"{case}/raw.json"], 2)
                self.assertIn("multiple hard links", completed.stdout)
                self.assertEqual(before, {str(file): file.read_bytes() for file in watched})

    def test_windows_lexical_alias_outputs_are_rejected_before_write(self):
        before = {name: (self.root / name).read_bytes() for name in SOURCE_FILES}
        for alias in ("orders.cjs:stream", "orders.cjs.", "orders.cjs ",
                      "directory./facts.json", "directory /facts.json", "facts\n.json"):
            with self.subTest(alias=alias):
                completed = self.invoke([NODE, str(OBSERVER), str(self.root), "observer.json", alias, "raw.json"], 2)
                self.assertIn("project-relative path", completed.stdout)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in SOURCE_FILES})
        self.assertFalse((self.root / "raw.json").exists())

    def test_windows_lexical_alias_input_is_rejected_before_execution(self):
        self.config["modules"][0]["file"] = "orders.cjs:stream"
        self.save_config()
        self.assertIn("project-relative path", self.observe(2)["errors"][0])

    def test_runner_created_output_hardlink_is_rejected_before_report_write(self):
        self.mutate("checkout-scenario.cjs", "console.log('checkout total=330');",
                    "const fs = require('node:fs');\n"
                    "  fs.mkdirSync('architecture/quality', {recursive: true});\n"
                    "  fs.linkSync('prices.cjs', 'architecture/quality/facts.json');\n"
                    "  console.log('checkout total=330');")
        selected = self.root / "prices.cjs"
        before = selected.read_bytes()
        quality = self.root / "architecture/quality"
        quality.mkdir(parents=True)
        raw = quality / "node-raw.json"
        raw.write_bytes(b"prior raw report")
        self.assertIn("multiple hard links", self.observe(2)["errors"][0])
        self.assertEqual(selected.read_bytes(), before)
        self.assertEqual(raw.read_bytes(), b"prior raw report")
        self.assertEqual((quality / "facts.json").read_bytes(), before)

    def test_input_mutation_during_scenario_is_unknown(self):
        self.mutate("checkout-scenario.cjs", "console.log('checkout total=330');",
                    "require('node:fs').appendFileSync('prices.cjs', '// mutated input\\n');\n"
                    "  console.log('checkout total=330');")
        self.observe(2)
        self.target(self.check([self.boundary], 2), "boundary", "unknown")
        raw = json.loads((self.root / "architecture/quality/node-raw.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["returncode"], 0)
        self.assertIn("selected inputs changed", "\n".join(raw["errors"]))

    def test_exact_copy_rollback_restores_real_behavior(self):
        self.observe()
        self.target(self.check([self.boundary, self.cycle], 0), "boundary", "pass")
        baseline = (self.root / "prices.cjs").read_bytes()
        copy_root = self.root / "rollback-copy"
        shutil.copytree(self.root, copy_root)
        original_root = self.root
        self.root = copy_root
        self.mutate("prices.cjs", "exports.sum", "require('./tax.cjs');\nexports.sum")
        self.observe()
        self.target(self.check([self.boundary], 1), "boundary", "fail")
        (self.root / "prices.cjs").write_bytes(baseline)
        self.observe()
        self.run_business()
        self.target(self.check([self.boundary, self.cycle, self.execution_rule()], 0), "boundary", "pass")
        self.assertEqual(hashlib.sha256((self.root / "prices.cjs").read_bytes()).hexdigest(),
                         hashlib.sha256(baseline).hexdigest())
        self.root = original_root


if __name__ == "__main__":
    unittest.main()
