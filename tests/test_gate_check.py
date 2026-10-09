"""收尾门禁：只有所有校验可信且通过才允许声明完成。"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared" / "scripts"))
import gate_check
import judge_progress
import manage_state


class TestGateCheck(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "architecture.json").write_text(json.dumps({
            "实现清单": {}, "上下文恢复点": {"当前阶段": "验证完成", "已触碰文件": []}
        }), encoding="utf-8")
        self.valid = (0, {"错误": [], "警告": []}, "")
        self.clean = (0, {"声明但不存在": [], "存在但未登记": []}, "")
        for name, result in [
            ("check_placeholders", {"status": "passed"}),
            ("check_state", {"status": "ok", "required_completed": 9, "required_total": 9,
                             "percentage": 100, "blockers": []}),
        ]:
            patcher = patch.object(judge_progress, name, return_value=result)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_gate(self, validation=None, drift=None):
        validation = validation if validation is not None else self.valid
        code, data, raw = validation
        if isinstance(data, dict):
            data = {"警告": [], **data}
        with patch.object(judge_progress, "run_command", return_value=(code, json.dumps(data), raw)):
            with patch.object(gate_check, "_run_script", return_value=drift if drift is not None else self.clean):
                return gate_check.run_gate(self.root, "architecture.json")

    def test_all_pass(self):
        passed, _, stages = self.run_gate()
        self.assertIs(passed, True)
        self.assertEqual([s["status"] for s in stages], ["pass"] * 6)

    def test_validator_errors_fail(self):
        self.assertIs(self.run_gate(validation=(1, {"错误": ["缺字段"]}, ""))[0], False)

    def test_validator_nonzero_without_errors_cannot_pass(self):
        self.assertIs(self.run_gate(validation=(1, {"错误": []}, ""))[0], False)

    def test_validator_unavailable_or_invalid_output_is_unknown(self):
        for code, output in [(2, {"错误": []}), (0, None), (0, {}),
                             (0, []), (0, {"错误": ""}), (3, {"错误": []})]:
            with self.subTest(code=code, output=output):
                self.assertIsNone(self.run_gate(validation=(code, output, "diagnostic"))[0])

    def test_missing_declared_files_fail(self):
        drift = (1, {"声明但不存在": ["src/app.py"], "存在但未登记": []}, "")
        self.assertIs(self.run_gate(drift=drift)[0], False)

    def test_unregistered_files_remain_advisory(self):
        for unregistered in [["src/extra.py"], 1]:
            with self.subTest(unregistered=unregistered):
                drift = (1, {"声明但不存在": [], "存在但未登记": unregistered}, "")
                self.assertIs(self.run_gate(drift=drift)[0], True)

    def test_invalid_drift_output_is_unknown(self):
        for result in [None, {}, [], {"声明但不存在": "bad", "存在但未登记": []},
                       {"声明但不存在": -1, "存在但未登记": []},
                       {"声明但不存在": False, "存在但未登记": []}]:
            with self.subTest(result=result):
                self.assertIsNone(self.run_gate(drift=(0, result, ""))[0])

    def test_failed_drift_process_cannot_pass_with_valid_json(self):
        self.assertIsNone(self.run_gate(drift=(2, self.clean[1], "failed"))[0])

    def test_contradictory_drift_exit_code_is_unknown(self):
        self.assertIsNone(self.run_gate(drift=(1, self.clean[1], ""))[0])

    def test_known_failure_takes_priority_over_unknown(self):
        self.assertIs(self.run_gate(validation=(1, {"错误": ["bad"]}, ""),
                                    drift=(2, None, "unavailable"))[0], False)

    def test_malformed_recovery_is_unknown(self):
        state = self.root / "architecture.json"
        for content in ["{broken", "[]", '{"上下文恢复点": []}',
                        '{"上下文恢复点": {"已触碰文件": [123]}}']:
            with self.subTest(content=content):
                state.write_text(content, encoding="utf-8")
                passed, _, stages = self.run_gate()
                self.assertIsNone(passed)
                self.assertEqual(stages[-1]["status"], "unknown")

    def test_scan_error_is_unknown(self):
        with patch.object(gate_check, "_count_impl_files", side_effect=PermissionError("denied")):
            self.assertIsNone(self.run_gate()[0])

    def test_actual_desync_still_fails(self):
        files = []
        for i in range(gate_check.DRIFT_FILE_THRESHOLD + 1):
            (self.root / f"app{i}.py").write_text("pass", encoding="utf-8")
            files.append(f"app{i}.py")
        (self.root / "architecture.json").write_text(json.dumps({
            "实现清单": {"app": {"文件列表": files}},
            "上下文恢复点": {"当前阶段": "架构设计", "已触碰文件": []}
        }), encoding="utf-8")
        self.assertIs(self.run_gate()[0], False)

    def test_cli_unknown_exit_and_compatible_envelope(self):
        output = io.StringIO()
        with patch.object(gate_check, "_run_script", return_value=self.clean), patch.object(
                judge_progress, "run_command", return_value=(2, "", "offline")):
            with contextlib.redirect_stdout(output):
                code = gate_check.main([str(self.root), "--json"])
        envelope = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(envelope["verdict"], "unknown")
        self.assertEqual(envelope["结论"], "无法判定")
        self.assertEqual(envelope["evidence"]["counts"], {"pass": 5, "fail": 0, "unknown": 1})
        self.assertTrue(envelope["原因"])


class TestCompletionIntegration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        assets = Path(__file__).resolve().parents[1] / "shared/assets"
        data = json.loads((assets / "example-architecture.json").read_text(encoding="utf-8"))
        from scan_code_drift import collect_declared_files
        manifest_files = sorted(collect_declared_files(data, self.root))
        for rel in manifest_files:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("pass\n", encoding="utf-8")
        data["上下文恢复点"]["当前阶段"] = "收尾验证"
        data["上下文恢复点"]["已触碰文件"] = manifest_files
        self.arch = self.root / "architecture.json"
        self.arch.write_text(json.dumps(data), encoding="utf-8")
        self.state_path = self.root / "architecture/_state.json"
        self.state = manage_state.create_initial_state("integration")
        manage_state.save_state(self.state_path, self.state)

    def complete(self):
        for stage in self.state["stages"]:
            stage["status"] = "completed"
        manage_state.save_state(self.state_path, self.state)

    def test_pending_stages_and_blockers_block_completion(self):
        self.assertIs(gate_check.run_gate(self.root, "architecture.json")[0], False)
        self.complete()
        self.state["blockers"].append({"content": "awaiting acceptance"})
        manage_state.save_state(self.state_path, self.state)
        self.assertIs(gate_check.run_gate(self.root, "architecture.json")[0], False)

    def test_missing_or_corrupt_state_is_unknown(self):
        self.state_path.unlink()
        self.assertIsNone(gate_check.run_gate(self.root, "architecture.json")[0])
        self.state_path.write_text("[]", encoding="utf-8")
        self.assertIsNone(gate_check.run_gate(self.root, "architecture.json")[0])

    def test_real_complete_project_passes_both_entrypoints(self):
        self.complete()
        verdict = judge_progress.generate_verdict(judge_progress.check_placeholders(self.arch),
            judge_progress.check_state(self.state_path), judge_progress.check_architecture(self.arch))
        self.assertEqual(verdict["code"], 0)
        self.assertIs(gate_check.run_gate(self.root, "architecture.json")[0], True)

    def test_critical_placeholder_blocks_even_when_state_complete(self):
        self.complete()
        data = json.loads(self.arch.read_text(encoding="utf-8"))
        data["项目"]["名称"] = "__待填__"
        self.arch.write_text(json.dumps(data), encoding="utf-8")
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json")
        self.assertIs(passed, False)
        self.assertEqual(stages[0]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
