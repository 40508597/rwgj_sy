"""Observable regressions for audited numeric, probe and completion failures."""
from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "shared/scripts"))
import _archlib
import check_project_quality as quality
import gate_check
import run_quality_probes as probes
import run_verification as verification
import scan_code_drift as drift


class QualityRepairRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix=".tmp-quality-repairs-", dir=PACKAGE.parent)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        (self.root / "unit.bin").write_bytes(b"GOOD")
        self.facts = {
            "schema_version": 1, "modules": ["A", "B"],
            "sources": [{"id": "observed", "origin": "observed",
                         "tool": {"name": "controlled-repair-fixture", "version": "1"},
                         "capabilities": ["metric", "dependencies:call", "decision"],
                         "scope": ["A", "B", "u", "d"], "complete": True,
                         "errors": [], "excluded": [],
                         "input_hashes": {"unit.bin": hashlib.sha256(b"GOOD").hexdigest()}}],
            "dependencies": [],
            "metrics": [{"source": "observed", "name": "count", "method": "exact-integer",
                         "unit": "u", "value": 1}],
            "decisions": [{"id": "d", "source": "observed", "drivers": ["existing contract"],
                           "constraints": ["platform requires protocol P"],
                           "negative_consequences": ["platform dependency remains"],
                           "validation": ["run compatibility checks"],
                           "revisit": ["when platform contract changes"],
                           "options": [{"id": "retain", "benefits": ["compatible"], "costs": ["dependency"]}],
                           "selected": "retain", "reason": "only this option meets the contract"}],
        }
        self.metric = {"id": "a-required", "check": "metric", "required": True,
                       "source": "observed", "scope": ["u"], "metric": "count",
                       "method": "exact-integer", "max": 5}
        self.decision_rule = {"id": "decision", "check": "decision", "required": True,
                              "source": "observed", "scope": ["d"]}

    def evaluate(self, *rules):
        result = quality.evaluate_project(self.root, self.facts, {"schema_version": 1, "rules": list(rules)})
        self.assertEqual(result["code"], {"pass": 0, "fail": 1, "unknown": 2}[result["status"]])
        return result

    def exception(self, status="approved"):
        self.facts["decisions"][0]["single_option_exception"] = {
            "reason": "the external contract permits only protocol P",
            "review": {"status": status, "reviewer": "synthetic-review-fixture",
                       "evidence": ["controlled review reference; no actual approval claimed"]},
        }

    def test_equal_integer_maximum_is_not_rounded_down(self):
        self.metric["max"] = self.facts["metrics"][0]["value"] = 2 ** 53 + 1
        self.assertEqual(self.evaluate(self.metric)["status"], "pass")

    def test_integer_below_minimum_does_not_round_into_pass(self):
        self.metric.pop("max")
        self.metric["min"] = 2 ** 53 + 1
        self.facts["metrics"][0]["value"] = 2 ** 53
        self.assertEqual(self.evaluate(self.metric)["status"], "fail")

    def test_optional_bad_kind_preserves_required_failure_and_all_rows(self):
        self.facts["metrics"][0]["value"] = 6
        optional = {"id": "z-optional", "check": "dependency", "required": False,
                    "source": "observed", "scope": ["A"], "kind": [], "allow": []}
        report = self.evaluate(self.metric, optional)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["counts"], {"pass": 0, "fail": 1, "unknown": 1})
        self.assertEqual([row["status"] for row in report["checks"]], ["fail", "unknown"])

    def test_optional_unhashable_source_does_not_drop_failure(self):
        self.facts["metrics"][0]["value"] = 6
        optional = {"id": "z-optional", "check": "dependency", "required": False,
                    "source": [], "scope": ["A"], "kind": "call", "allow": []}
        report = self.evaluate(self.metric, optional)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(len(report["checks"]), 2)
        self.assertEqual(report["checks"][1]["status"], "unknown")

    def test_single_option_without_review_exception_still_fails(self):
        self.assertEqual(self.evaluate(self.decision_rule)["status"], "fail")

    def test_single_option_approved_exception_passes_structure(self):
        self.exception()
        self.assertEqual(self.evaluate(self.decision_rule)["status"], "pass")

    def test_single_option_pending_review_is_unknown(self):
        self.exception("pending")
        self.assertEqual(self.evaluate(self.decision_rule)["status"], "unknown")

    def test_single_option_rejected_review_fails(self):
        self.exception("rejected")
        self.assertEqual(self.evaluate(self.decision_rule)["status"], "fail")

    def test_single_option_review_missing_evidence_is_unknown(self):
        self.exception()
        self.facts["decisions"][0]["single_option_exception"]["review"]["evidence"] = []
        self.assertEqual(self.evaluate(self.decision_rule)["status"], "unknown")

    def test_exception_cannot_approve_zero_options(self):
        self.exception()
        self.facts["decisions"][0]["options"] = []
        self.assertEqual(self.evaluate(self.decision_rule)["status"], "fail")

    def test_known_incomplete_decision_wins_over_pending_review(self):
        self.exception("pending")
        self.facts["decisions"][0]["drivers"] = []
        self.assertEqual(self.evaluate(self.decision_rule)["status"], "fail")

    def test_unhashable_selected_option_is_diagnostic_failure(self):
        self.exception()
        self.facts["decisions"][0]["selected"] = []
        self.assertEqual(self.evaluate(self.decision_rule)["status"], "fail")

    def test_numeric_json_overflow_is_rejected_at_every_depth(self):
        for loader in (quality.strict_json, probes._json):
            with self.subTest(loader=loader.__module__), self.assertRaises(ValueError):
                loader('{"extra": {"metric": 1e309}}')

    def test_huge_verification_timeout_returns_unknown_receipt(self):
        with patch.object(verification.subprocess, "run", side_effect=AssertionError("must not execute")):
            receipt = verification.run_verification(self.root, [sys.executable, "-c", "pass"], ["unit.bin"], 10 ** 1000)
        self.assertEqual(receipt["status"], "unknown")
        self.assertTrue(receipt["finished_at"])
        self.assertIn("OverflowError", receipt["reason"])

    def suite(self, *, bad_extra=False, timeout=10):
        checker = self.base / "checker.py"
        checker.write_text(
            "import json,sys\nfrom pathlib import Path\n"
            "good = Path('unit.bin').read_bytes() == b'GOOD' and sys.argv[1] == ''\n"
            "state = 'pass' if good else 'fail'\n"
            "result = {'status':state,'code':0 if good else 1,'checks':[{'id':'target','status':state}]}\n"
            + ("print(json.dumps(result)[:-1] + ',\\\"extra\\\":1e309}')\n" if bad_extra else "print(json.dumps(result))\n")
            + "raise SystemExit(0 if good else 1)\n", encoding="utf-8")
        suite = {"schema_version": 1, "cases": [{"id": "fault", "input": "unit.bin",
                 "old_base64": base64.b64encode(b"GOOD").decode(),
                 "new_base64": base64.b64encode(b"BAD").decode(), "check_id": "target",
                 "command": [sys.executable, str(checker), ""], "timeout": timeout}]}
        suite_file = self.root / "suite.json"
        suite_file.write_text(json.dumps(suite), encoding="utf-8")
        return suite_file

    def test_empty_argv_parameter_reaches_actual_checker(self):
        suite = self.suite()
        report = probes.run_suite(self.root, suite, self.base / "probe-workspace")
        self.assertEqual(report["status"], "pass", report)
        self.assertEqual(report["counts"]["detected"], 1)
        self.assertTrue(report["original_unchanged"])
        self.assertEqual(report["cases"][0]["baseline"]["command"][-1], "")

    def test_numeric_overflow_checker_cannot_write_nonstandard_success_report(self):
        suite = self.suite(bad_extra=True)
        report = probes.run_suite(self.root, suite, self.base / "probe-workspace")
        self.assertEqual(report["status"], "unknown")
        saved = probes._json((self.base / "probe-workspace/report.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["code"], 2)
        self.assertTrue(report["original_unchanged"])
        self.assertIn("finite supported range", report["cases"][0]["baseline"]["contract_error"])

    def test_huge_probe_timeout_cli_is_structured_unknown(self):
        suite = self.suite(timeout=10 ** 1000)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = probes.main([str(self.root), "--suite", str(suite), "--workspace", str(self.base / "probe-workspace"), "--json"])
        report = json.loads(output.getvalue())
        self.assertEqual((code, report["status"]), (2, "unknown"))
        self.assertFalse((self.base / "probe-workspace").exists())

    def test_file_identity_comparison_respects_host_case_semantics(self):
        (self.root / "Core.UNIT").write_bytes(b"opaque")
        (self.root / "unit.bin").unlink()
        arch = self.root / "architecture.json"
        arch.write_text(json.dumps({"实现清单": {"A": {"文件列表": ["core.unit"]}}}), encoding="utf-8")
        report = drift.scan_code_drift(self.root, arch, set(), all_files=True)
        if os.name == "nt":
            self.assertTrue(os.path.samefile(self.root / "Core.UNIT", self.root / "core.unit"))
            self.assertEqual((report["声明但不存在"], report["存在但未登记"]), ([], []))
        else:
            self.assertEqual(report["声明但不存在"], ["core.unit"])
            self.assertEqual(report["存在但未登记"], ["Core.UNIT"])

    def test_desync_is_identical_for_all_registered_file_formats(self):
        for suffix in (".py", ".c", ".未知", ""):
            with self.subTest(suffix=suffix):
                project = self.base / ("format-" + (suffix or "none"))
                project.mkdir()
                files = [f"implementation-{i}{suffix}" for i in range(6)]
                for name in files:
                    (project / name).write_bytes(b"")
                (project / "architecture.json").write_text(json.dumps({
                    "实现清单": {"A": {"文件列表": files}},
                    "上下文恢复点": {"当前阶段": "架构设计", "已触碰文件": []},
                }), encoding="utf-8")
                failure, reason = gate_check._check_desync(project)
                self.assertTrue(failure)
                self.assertIn("6 个已登记实现文件", reason)

    def test_selected_architecture_recovery_wins_over_unrelated_side_file(self):
        files = [f"implementation-{i}" for i in range(6)]
        for name in files:
            (self.root / name).write_bytes(b"opaque")
        selected = self.root / "selected.json"
        selected.write_text(json.dumps({"实现清单": {"A": {"文件列表": files}},
                                       "上下文恢复点": {"当前阶段": "验证完成", "已触碰文件": files}}), encoding="utf-8")
        side = self.root / "architecture/tasks/state.json"
        side.parent.mkdir(parents=True)
        side.write_text("{broken", encoding="utf-8")
        self.assertFalse(gate_check._check_desync(self.root, selected)[0])

    def test_missing_recovery_is_not_a_success(self):
        (self.root / "architecture.json").write_text('{"实现清单": {}}', encoding="utf-8")
        with self.assertRaises(_archlib.ArchitectureInputError):
            gate_check._check_desync(self.root)

    def test_multi_level_pointer_and_parent_reference_share_manifest_semantics(self):
        files = [f"implementation-{i}.opaque" for i in range(6)]
        for name in files:
            (self.root / name).write_bytes(b"opaque")
        (self.root / "architecture.json").write_text(json.dumps({
            "实现清单": {"A": {"文件列表": files}},
            "上下文恢复点": {"当前阶段": "架构设计", "已触碰文件": []},
        }), encoding="utf-8")
        metadata = self.root / "metadata"
        metadata.mkdir()
        (metadata / "second.json").write_text('{"指向": "../architecture.json"}', encoding="utf-8")
        selected = metadata / "first.json"
        selected.write_text('{"指向": "second.json"}', encoding="utf-8")
        self.assertTrue(gate_check._check_desync(self.root, selected)[0])
        report = drift.scan_code_drift(self.root, selected, set(), all_files=True)
        self.assertEqual(report["声明但不存在"], [])
        self.assertEqual(report["已登记代码文件"], files)

    def test_full_gate_checks_recovery_for_unknown_and_extensionless_units_without_mocks(self):
        # Complete structural fixture, actual selected input execution, actual
        # completion/quality/drift subprocesses. No compiler or whole-business
        # coverage claim is made for these controlled opaque input fixtures.
        import manage_state
        for suffix in (".py", ".c", ".opaque", ""):
            with self.subTest(suffix=suffix):
                project = self.base / ("full-format-" + (suffix or "none"))
                project.mkdir()
                data = json.loads((PACKAGE / "shared/assets/example-architecture.json").read_text(encoding="utf-8"))

                def replace_paths(value):
                    if isinstance(value, dict):
                        return {k: replace_paths(v) for k, v in value.items()}
                    if isinstance(value, list):
                        return [replace_paths(v) for v in value]
                    return value.replace(".py", suffix) if isinstance(value, str) else value

                data = replace_paths(data)
                files = sorted(drift.collect_declared_files(data, project))
                for name in files:
                    path = project / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"controlled opaque input")
                data["上下文恢复点"]["当前阶段"] = "架构设计"
                data["上下文恢复点"]["已触碰文件"] = []
                arch = project / "architecture.json"
                arch.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                state_path = project / "architecture/_state.json"
                state = manage_state.create_initial_state("controlled format fixture")
                for stage in state["stages"]:
                    if stage["required"]:
                        stage["status"] = "completed"
                manage_state.save_state(state_path, state)
                selected_inputs = [files[0]]
                command = [sys.executable, "-c", "from pathlib import Path; assert Path(" + repr(files[0]) + ").read_bytes() == b'controlled opaque input'"]
                receipt = verification.run_verification(project, command, selected_inputs, timeout=10)
                self.assertEqual(receipt["status"], "pass", receipt)
                directory = project / "architecture/quality"
                directory.mkdir()
                (directory / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
                (directory / "facts.json").write_text('{"schema_version": 1}', encoding="utf-8")
                policy = {"schema_version": 1, "rules": [{"id": "actual-controlled-input-check", "check": "execution", "required": True,
                          "inputs": selected_inputs, "receipt": "architecture/quality/receipt.json", "command": command}]}
                (directory / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
                code, report, raw = _archlib.run_subprocess_json([sys.executable, "-B", str(PACKAGE / "shared/scripts/gate_check.py"),
                    str(project), "--quality-required", "--json"])
                self.assertEqual(code, 1, raw)
                self.assertEqual(report["verdict"], "fail")
                by_name = {row["name"]: row["status"] for row in report["stages"]}
                self.assertEqual(by_name["架构合规"], "pass", raw)
                self.assertEqual(by_name["通用质量"], "pass", raw)
                self.assertEqual(by_name["流程脱轨"], "fail", raw)

    def test_custom_quality_paths_are_used_by_actual_completion_gate(self):
        import manage_state
        data = json.loads((PACKAGE / "shared/assets/example-architecture.json").read_text(encoding="utf-8"))
        files = sorted(drift.collect_declared_files(data, self.root))
        for name in files:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"controlled input")
        data["上下文恢复点"].update({"当前阶段": "收尾验证", "已触碰文件": files})
        (self.root / "architecture.json").write_text(json.dumps(data), encoding="utf-8")
        state = manage_state.create_initial_state("custom quality fixture")
        for stage in state["stages"]:
            if stage["required"]:
                stage["status"] = "completed"
        manage_state.save_state(self.root / "architecture/_state.json", state)
        (self.root / "custom-facts.json").write_text(json.dumps(self.facts), encoding="utf-8")
        (self.root / "custom-policy.json").write_text(json.dumps({"schema_version": 1, "rules": [self.metric]}), encoding="utf-8")
        code, report, raw = _archlib.run_subprocess_json([sys.executable, "-B", str(PACKAGE / "shared/scripts/gate_check.py"),
            str(self.root), "--facts", "custom-facts.json", "--policy", "custom-policy.json", "--quality-required", "--json"])
        self.assertEqual((code, report["verdict"]), (0, "pass"), raw)

    def test_project_protocol_does_not_require_global_skill_files_in_project(self):
        import validate_protocol_semantics
        data = {"项目": {"名称": "isolated project", "说明": "small scope"}, "实现清单": {}}
        arch = self.root / "architecture.json"
        arch.write_text(json.dumps(data), encoding="utf-8")
        errors, warnings = validate_protocol_semantics.validate_protocol(self.root, arch)
        self.assertEqual(errors, [])
        self.assertFalse(any("协议文件未登记" in message for message in warnings))
        self.assertFalse((self.root / "shared").exists())

    def test_explicit_incomplete_capability_is_detected_independently(self):
        import validate_protocol_semantics
        data = {"项目": {"名称": "isolated project", "说明": "small scope"}}
        arch = self.root / "architecture.json"
        arch.write_text(json.dumps(data), encoding="utf-8")
        incomplete = self.base / "incomplete-skill"
        incomplete.mkdir()
        errors, _ = validate_protocol_semantics.validate_protocol(self.root, arch, capability_root=incomplete)
        self.assertTrue(any("必需协议文件不存在" in message for message in errors))


if __name__ == "__main__":
    unittest.main()
