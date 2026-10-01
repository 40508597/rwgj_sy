"""验证宿主适配协议；不依赖已安装的 Claude Code。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("claude_stop_hook", ROOT / "optional/claude_stop_hook.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class TestStopHook(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "architecture").mkdir()
        self.event = {"hook_event_name": "Stop", "cwd": str(self.root),
                      "last_assistant_message": "【任务完成】完成变更", "stop_hook_active": False}

    def test_verified_completion_allows_stop(self):
        with patch.object(hook._archlib, "run_subprocess_json", return_value=(0, {"code": 0, "verdict": "pass"}, "")):
            self.assertEqual(hook.decide(self.event), {})

    def test_failure_unknown_and_invalid_output_block_claim(self):
        for response in [(1, {"verdict": "fail"}, ""), (2, {"verdict": "unknown"}, ""),
                         (0, None, "bad output"), (0, {"code": 2, "verdict": "unknown"}, "")]:
            with self.subTest(response=response):
                with patch.object(hook._archlib, "run_subprocess_json", return_value=response):
                    self.assertEqual(hook.decide(self.event)["decision"], "block")

    def test_failure_report_and_questions_do_not_run_gate(self):
        for message in ["【未通过验证】需要补充测试", "请提供需求", "这是概念解释"]:
            with patch.object(hook._archlib, "run_subprocess_json", side_effect=AssertionError("unneeded check")):
                self.assertEqual(hook.decide({**self.event, "last_assistant_message": message}), {})

    def test_repeated_failure_stops_retry_with_explicit_failure(self):
        with patch.object(hook._archlib, "run_subprocess_json", return_value=(2, None, "offline")):
            result = hook.decide({**self.event, "stop_hook_active": True})
        self.assertIs(result["continue"], False)
        self.assertTrue(result["stopReason"].startswith("【未通过验证】"))
