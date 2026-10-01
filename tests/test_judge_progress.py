"""judge_progress.py 单元测试（generate_verdict 纯函数 + 返回码契约）"""

from __future__ import annotations

import sys
import unittest
import json
import tempfile
from unittest.mock import patch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import judge_progress  # noqa: E402


def ph_ok() -> dict:
    return {"status": "passed", "message": "无占位符"}


def ph_failed(critical: int = 1) -> dict:
    return {"status": "failed", "critical_count": critical,
            "important_count": 0, "next_steps": ["填写核心字段"]}


def state_missing() -> dict:
    return {"status": "no_state", "message": "状态文件不存在，建议创建"}


def state_ok(required_done: int = 9, required_total: int = 9,
             percentage: int = 100, blockers: list | None = None) -> dict:
    return {"status": "ok", "project_name": "测试", "current_stage": "验证证据",
            "percentage": percentage, "required_completed": required_done,
            "required_total": required_total, "blockers": blockers or [],
            "stages": [], "next_actions": []}


def arch_ok() -> dict:
    return {"status": "passed", "message": "架构验证通过"}


def arch_failed(errors: int = 1) -> dict:
    return {"status": "failed", "errors": [f"错误{i}" for i in range(errors)],
            "warnings": []}


class TestGenerateVerdict(unittest.TestCase):
    def test_all_pass_proceeds(self):
        v = judge_progress.generate_verdict(ph_ok(), state_ok(), arch_ok())
        self.assertTrue(v["can_proceed"])
        self.assertEqual(v["blocking_issues"], [])

    def test_placeholder_blocks(self):
        v = judge_progress.generate_verdict(ph_failed(3), state_ok(), arch_ok())
        self.assertFalse(v["can_proceed"])
        self.assertTrue(any("核心占位符" in i for i in v["blocking_issues"]))

    def test_no_state_is_unknown_and_cannot_proceed(self):
        v = judge_progress.generate_verdict(ph_ok(), state_missing(), arch_ok())
        self.assertFalse(v["can_proceed"])
        self.assertEqual(v["code"], 2)

    def test_required_stages_incomplete_blocks(self):
        v = judge_progress.generate_verdict(
            ph_ok(), state_ok(required_done=5, required_total=9, percentage=50), arch_ok())
        self.assertFalse(v["can_proceed"])
        self.assertTrue(any("必需阶段未全部完成" in i for i in v["blocking_issues"]))

    def test_blockers_block(self):
        v = judge_progress.generate_verdict(
            ph_ok(), state_ok(blockers=[{"content": "等待用户确认"}]), arch_ok())
        self.assertFalse(v["can_proceed"])
        self.assertTrue(any("阻塞项" in i for i in v["blocking_issues"]))

    def test_architecture_errors_block(self):
        v = judge_progress.generate_verdict(ph_ok(), state_ok(), arch_failed(2))
        self.assertFalse(v["can_proceed"])
        self.assertTrue(any("架构验证失败" in i for i in v["blocking_issues"]))

    def test_blocked_verdict_forbids_declaring_done(self):
        """阻塞时 next_actions 必须以「禁止声明完成」开头。"""
        v = judge_progress.generate_verdict(ph_failed(1), state_ok(), arch_ok())
        self.assertFalse(v["can_proceed"])
        self.assertTrue(any("禁止声明完成" in a for a in v["next_actions"]))

    def test_errors_and_skipped_checks_never_pass(self):
        for status in ("error", "skipped", "unexpected"):
            for index in range(3):
                with self.subTest(status=status, index=index):
                    results = [ph_ok(), state_ok(), arch_ok()]
                    results[index] = {"status": status, "message": "unavailable"}
                    v = judge_progress.generate_verdict(*results)
                    self.assertFalse(v["can_proceed"])
                    self.assertEqual(v["code"], 2)

    def test_failure_wins_over_unknown(self):
        v = judge_progress.generate_verdict(ph_failed(), {"status": "error"}, arch_ok())
        self.assertEqual(v["code"], 1)

    def test_invalid_success_output_is_unknown(self):
        for fn in (judge_progress.check_placeholders, judge_progress.check_architecture):
            for output in ("", "not json", "[]", "{}"):
                with self.subTest(fn=fn.__name__, output=output):
                    with patch.object(judge_progress, "run_command", return_value=(0, output, "")):
                        self.assertEqual(fn(Path("example.json"))["status"], "error")

    def test_missing_architecture_cli_returns_unknown(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(io.StringIO()) as buf:
            code = judge_progress.main([str(Path(td) / "missing.json"), "--json"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(buf.getvalue())["verdict"]["can_proceed"])


if __name__ == "__main__":
    unittest.main()
