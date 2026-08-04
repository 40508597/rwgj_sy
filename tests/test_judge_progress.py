"""judge_progress.py 单元测试（generate_verdict 纯函数 + 返回码契约）"""

import sys
import unittest
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

    def test_no_state_warns_but_proceeds(self):
        v = judge_progress.generate_verdict(ph_ok(), state_missing(), arch_ok())
        self.assertTrue(v["can_proceed"])
        self.assertTrue(any("进度状态" in w for w in v["warnings"]))

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


if __name__ == "__main__":
    unittest.main()
