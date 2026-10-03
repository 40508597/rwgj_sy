"""Exercise actual quality/drift CLI calls through the completion gate."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "shared" / "scripts"))
import gate_check
import _archlib
import detect_small_command

_hook_spec = importlib.util.spec_from_file_location("quality_completion_hook", PACKAGE / "optional" / "claude_stop_hook.py")
quality_hook = importlib.util.module_from_spec(_hook_spec)
_hook_spec.loader.exec_module(quality_hook)


class QualityGateIntegration(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=PACKAGE.parent, prefix=".tmp-gate-quality-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.artifact = self.root / "工程.未知"
        self.artifact.write_bytes(b"opaque-unit")
        self.write("architecture.json", {"实现清单": {"A": {"文件列表": ["工程.未知"]}}})
        self.facts = {"schema_version": 1, "modules": ["A", "B"],
                      "sources": [{"id": "export", "origin": "observed",
                                   "tool": {"name": "fixture", "version": "1"},
                                   "capabilities": ["dependencies:call"], "scope": ["A", "B"],
                                   "complete": True, "errors": [], "excluded": [],
                                   "input_hashes": {"工程.未知": hashlib.sha256(b"opaque-unit").hexdigest()}}],
                      "dependencies": [{"from": "A", "to": "B", "kind": "call", "source": "export"}]}
        self.policy = {"schema_version": 1, "rules": [{"id": "boundary", "check": "dependency",
                        "required": True, "source": "export", "scope": ["A", "B"],
                        "kind": "call", "allow": [["A", "B"]]}]}

    def write(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def configure(self):
        self.write("architecture/quality/policy.json", self.policy)
        self.write("architecture/quality/facts.json", self.facts)

    def run_gate(self, required=False):
        completion = {"stages": [{"name": "legacy", "status": "pass", "detail": "fixture"}], "warnings": []}
        with patch.object(gate_check.judge_progress, "check_placeholders", return_value={}), \
             patch.object(gate_check.judge_progress, "check_state", return_value={}), \
             patch.object(gate_check.judge_progress, "check_architecture", return_value={}), \
             patch.object(gate_check.judge_progress, "generate_verdict", return_value=completion), \
             patch.object(gate_check, "_check_desync", return_value=(False, "fixture")):
            return gate_check.run_gate(self.root, "architecture.json", quality_required=required)

    def test_configured_quality_is_automatically_called(self):
        self.configure()
        passed, _, stages = self.run_gate()
        self.assertIs(passed, True)
        self.assertEqual(stages[-1]["name"], "通用质量")
        self.assertEqual(stages[-1]["status"], "pass")

    def test_forbidden_dependency_blocks_completion(self):
        self.facts["dependencies"].append({"from": "B", "to": "A", "kind": "call", "source": "export"})
        self.configure()
        self.assertIs(self.run_gate()[0], False)

    def test_missing_policy_is_unknown(self):
        self.write("architecture/quality/facts.json", self.facts)
        self.assertIsNone(self.run_gate()[0])

    def test_missing_facts_is_unknown(self):
        self.write("architecture/quality/policy.json", self.policy)
        self.assertIsNone(self.run_gate()[0])

    def test_required_quality_without_configuration_is_unknown(self):
        self.assertIsNone(self.run_gate(required=True)[0])

    def test_legacy_gate_reports_its_limited_scope(self):
        passed, lines, _ = self.run_gate()
        self.assertIs(passed, True)
        self.assertTrue(any("仅覆盖旧架构门禁" in line for line in lines))

    def test_stale_observation_blocks_completion_as_unknown(self):
        self.configure()
        self.artifact.write_bytes(b"changed-unit")
        self.assertIsNone(self.run_gate()[0])

    def test_missing_unknown_extension_file_is_known_failure(self):
        self.configure()
        self.artifact.unlink()
        self.assertIs(self.run_gate()[0], False)

    def test_legacy_failure_wins_over_unknown_quality(self):
        self.artifact.unlink()
        self.assertIs(self.run_gate(required=True)[0], False)

    def test_declared_observation_cannot_complete(self):
        self.facts["sources"][0]["origin"] = "declared"
        self.configure()
        self.assertIsNone(self.run_gate()[0])

    def test_malformed_receipt_root_is_unknown_without_crash(self):
        from check_project_quality import evaluate_project
        for value in [None, []]:
            with self.subTest(value=value):
                self.write("receipt.json", value)
                policy = {"schema_version": 1, "rules": [{"id": "test", "check": "execution",
                    "required": True, "receipt": "receipt.json", "inputs": ["工程.未知"], "command": ["test-command"]}]}
                self.assertEqual(evaluate_project(self.root, self.facts, policy)["status"], "unknown")

    def test_nul_enabled_slice_is_input_error(self):
        self.write("architecture.json", {"架构切片": {"启用": True, "切片清单": [{"路径": "bad\u0000slice"}]}})
        with self.assertRaises(_archlib.ArchitectureInputError):
            _archlib.load_architecture_json(self.root / "architecture.json")

    def test_negated_edit_and_readonly_run_document_remain_readonly(self):
        rules = json.loads((PACKAGE / "shared" / "assets" / "small-command-rules.json").read_text(encoding="utf-8"))
        for request in ["不是要修改代码，只查看运行说明", "并非要删除数据，仅阅读部署文档"]:
            with self.subTest(request=request):
                self.assertEqual(detect_small_command.classify(request, rules)[0], "完全跳过")

    def test_following_actual_operation_is_not_hidden_by_document(self):
        rules = json.loads((PACKAGE / "shared" / "assets" / "small-command-rules.json").read_text(encoding="utf-8"))
        self.assertEqual(detect_small_command.classify("查看运行说明然后删除生产数据库", rules)[0], "完整流程")

    def test_unknown_source_edge_cannot_disappear_and_pass(self):
        from check_project_quality import evaluate_project
        self.facts["dependencies"][0]["source"] = "missing-exporter"
        self.assertEqual(evaluate_project(self.root, self.facts, self.policy)["status"], "unknown")

    def test_unknown_endpoint_edge_cannot_disappear_and_pass(self):
        from check_project_quality import evaluate_project
        self.facts["dependencies"][0]["to"] = "missing-module"
        self.assertEqual(evaluate_project(self.root, self.facts, self.policy)["status"], "unknown")

    def test_oversized_metric_is_unknown_without_crash(self):
        from check_project_quality import evaluate_project
        self.facts["metrics"] = [{"unit": "A", "source": "export", "name": "complexity", "method": "cyclomatic", "value": 10 ** 1000}]
        self.assertEqual(evaluate_project(self.root, self.facts, self.policy)["status"], "unknown")

    def test_long_cycle_uses_iterative_graph_traversal(self):
        from check_project_quality import find_cycle
        nodes = [f"module-{i}" for i in range(2000)]
        edges = list(zip(nodes, nodes[1:])) + [(nodes[-1], nodes[0])]
        cycle = find_cycle(edges, nodes)
        self.assertEqual(len(cycle), len(nodes) + 1)
        self.assertEqual(cycle[0], cycle[-1])

    def test_completion_hook_actual_argv_requires_quality(self):
        event = {"hook_event_name": "Stop", "cwd": str(self.root), "last_assistant_message": "【任务完成】完整交付", "stop_hook_active": False}
        with patch.object(quality_hook.resolve_tool, "candidates_for", return_value=[("fixture", PACKAGE / "shared" / "scripts" / "gate_check.py")]), \
             patch.object(quality_hook._archlib, "run_subprocess_json", return_value=(0, {"code": 0, "verdict": "pass"}, "")) as run:
            self.assertEqual(quality_hook.decide(event), {})
        argv = run.call_args.args[0]
        self.assertIn("--quality-required", argv)
        self.assertIn("--json", argv)
        self.assertIn(str(self.root), argv)

    def test_completion_hook_unknown_required_quality_blocks(self):
        event = {"hook_event_name": "Stop", "cwd": str(self.root), "last_assistant_message": "【任务完成】完整交付", "stop_hook_active": False}
        with patch.object(quality_hook.resolve_tool, "candidates_for", return_value=[("fixture", PACKAGE / "shared" / "scripts" / "gate_check.py")]), \
             patch.object(quality_hook._archlib, "run_subprocess_json", return_value=(2, {"code": 2, "verdict": "unknown", "原因": ["缺少质量事实与规则"]}, "")) as run:
            result = quality_hook.decide(event)
        self.assertEqual(result["decision"], "block")
        self.assertIn("--quality-required", run.call_args.args[0])
        self.assertIn("缺少质量事实与规则", result["reason"])

    def test_completion_hook_local_messages_keep_scope_degradation(self):
        event = {"hook_event_name": "Stop", "cwd": str(self.root), "stop_hook_active": False}
        for message in ["查看完成：这是运行说明", "局部测试已执行", "【未通过验证】尚缺工程导出", "这是架构概念说明"]:
            with self.subTest(message=message):
                with patch.object(quality_hook._archlib, "run_subprocess_json", side_effect=AssertionError("local result must not run project completion gate")):
                    self.assertEqual(quality_hook.decide({**event, "last_assistant_message": message}), {})

    def assert_quality_cli_and_gate_unknown(self):
        code, result, _ = _archlib.run_subprocess_json([
            sys.executable, str(PACKAGE / "shared" / "scripts" / "check_project_quality.py"),
            str(self.root), "--json"])
        passed, _, stages = self.run_gate(required=True)
        self.assertIsNone(passed)
        self.assertEqual(stages[-1]["status"], "unknown")
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "unknown")

    def test_duplicate_fact_origin_cannot_turn_declaration_into_observation(self):
        self.configure()
        path = self.root / "architecture" / "quality" / "facts.json"
        raw = path.read_text(encoding="utf-8")
        self.assertIn('"origin": "observed"', raw)
        path.write_text(raw.replace('"origin": "observed"', '"origin": "declared", "origin": "observed"', 1), encoding="utf-8")
        self.assert_quality_cli_and_gate_unknown()

    def test_duplicate_policy_required_cannot_downgrade_missing_execution(self):
        self.configure()
        required_test = {"id": "required-test", "check": "execution", "required": True,
                         "receipt": "missing-receipt.json", "inputs": ["工程.未知"], "command": ["fixture-test"]}
        raw_test = json.dumps(required_test, ensure_ascii=False)
        raw_test = raw_test.replace('"required": true', '"required": true, "required": false', 1)
        raw = '{"schema_version": 1, "rules": [' + json.dumps(self.policy["rules"][0], ensure_ascii=False) + ',' + raw_test + ']}'
        (self.root / "architecture" / "quality" / "policy.json").write_text(raw, encoding="utf-8")
        self.assert_quality_cli_and_gate_unknown()

    def test_duplicate_receipt_returncode_cannot_override_execution_evidence(self):
        from run_verification import run_verification
        command = [sys.executable, "-c", "print('self-contained fixture')"]
        receipt = run_verification(self.root, command, ["工程.未知"], timeout=5)
        self.assertEqual(receipt["status"], "pass")
        self.policy["rules"].append({"id": "required-test", "check": "execution", "required": True,
            "receipt": "receipt.json", "inputs": ["工程.未知"], "command": command})
        self.configure()
        raw = json.dumps(receipt, ensure_ascii=False)
        self.assertIn('"returncode": 0', raw)
        (self.root / "receipt.json").write_text(raw.replace('"returncode": 0', '"returncode": 1, "returncode": 0', 1), encoding="utf-8")
        self.assert_quality_cli_and_gate_unknown()


if __name__ == "__main__":
    unittest.main()
