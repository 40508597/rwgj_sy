"""manage_state.py 单元测试（stdlib unittest，无外部依赖）"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import manage_state  # noqa: E402

REQUIRED_STAGE_COUNT = 9  # 9 个必需 + 1 个可选（接口契约）


class TestManageState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = Path(self.tmp.name) / "_state.json"

    def test_standard_stages_truth(self):
        """STANDARD_STAGES 真相源：9 个必需 + 1 个可选。"""
        required = sum(1 for s in manage_state.STANDARD_STAGES if s["required"])
        self.assertEqual(required, REQUIRED_STAGE_COUNT)
        self.assertEqual(len(manage_state.STANDARD_STAGES), REQUIRED_STAGE_COUNT + 1)

    def test_init_creates_state_file(self):
        self.assertEqual(manage_state.main(
            ["init", "--project-name", "测试项目", "--state-path", str(self.state_path)]), 0)
        self.assertTrue(self.state_path.exists())

    def test_init_refuses_existing_without_force(self):
        manage_state.main(["init", "--project-name", "测试项目", "--state-path", str(self.state_path)])
        self.assertEqual(manage_state.main(
            ["init", "--project-name", "测试项目", "--state-path", str(self.state_path)]), 1)
        self.assertEqual(manage_state.main(
            ["init", "--force", "--project-name", "测试项目", "--state-path", str(self.state_path)]), 0)

    def test_show_missing_returns_1(self):
        self.assertEqual(manage_state.main(["show", "--state-path", str(self.state_path)]), 1)

    def test_show_json_contract(self):
        """show --json 输出字段契约（judge_progress 依赖这些 key）。"""
        manage_state.main(["init", "--project-name", "测试项目", "--state-path", str(self.state_path)])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = manage_state.main(["show", "--state-path", str(self.state_path), "--json"])
        self.assertEqual(rc, 0)
        result = json.loads(buf.getvalue())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["project_name"], "测试项目")
        self.assertEqual(result["required_total"], REQUIRED_STAGE_COUNT)
        self.assertEqual(result["required_completed"], 0)

    def test_update_and_completion(self):
        manage_state.main(["init", "--project-name", "测试项目", "--state-path", str(self.state_path)])
        self.assertEqual(manage_state.main(
            ["update", "功能树", "completed", "--state-path", str(self.state_path)]), 0)
        state = manage_state.load_state(self.state_path)
        stage = next(s for s in state["stages"] if s["id"] == "功能树")
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(state["completion"]["required_completed"], 1)

    def test_update_unknown_stage_returns_1(self):
        manage_state.main(["init", "--project-name", "测试项目", "--state-path", str(self.state_path)])
        self.assertEqual(manage_state.main(
            ["update", "不存在的阶段", "completed", "--state-path", str(self.state_path)]), 1)

    def test_add_blocker(self):
        manage_state.main(["init", "--project-name", "测试项目", "--state-path", str(self.state_path)])
        self.assertEqual(manage_state.main(
            ["add-blocker", "等待用户确认需求", "--state-path", str(self.state_path)]), 0)
        state = manage_state.load_state(self.state_path)
        self.assertEqual(len(state["blockers"]), 1)


if __name__ == "__main__":
    unittest.main()
