"""manage_state.py 单元测试（stdlib unittest，无外部依赖）"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
import subprocess
from unittest.mock import patch
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

    def launch_writers(self, count=6, expected=None):
        processes = []
        for i in range(count):
            cmd = [sys.executable, str(REPO_ROOT / "shared/scripts/manage_state.py"),
                   "add-blocker", f"writer-{i}", "--state-path", str(self.state_path)]
            if expected is not None:
                cmd += ["--expect-rev", str(expected)]
            processes.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               text=True, encoding="utf-8"))
        for process in processes:
            process.communicate(timeout=20)
        return [p.returncode for p in processes]

    def test_concurrent_updates_preserve_every_writer(self):
        manage_state.save_state(self.state_path, manage_state.create_initial_state())
        self.assertEqual(self.launch_writers(), [0] * 6)
        saved = manage_state.load_state(self.state_path)
        self.assertEqual({b["content"] for b in saved["blockers"]}, {f"writer-{i}" for i in range(6)})
        self.assertEqual(manage_state.state_revision(saved), 7)

    def test_concurrent_expected_revision_has_one_winner(self):
        manage_state.save_state(self.state_path, manage_state.create_initial_state())
        codes = self.launch_writers(expected=1)
        self.assertEqual(codes.count(0), 1)
        self.assertEqual(codes.count(3), 5)
        saved = manage_state.load_state(self.state_path)
        self.assertEqual(len(saved["blockers"]), 1)
        self.assertEqual(manage_state.state_revision(saved), 2)

    def test_stale_library_snapshot_is_rejected(self):
        manage_state.save_state(self.state_path, manage_state.create_initial_state())
        first = manage_state.load_state(self.state_path)
        second = manage_state.load_state(self.state_path)
        first["blockers"].append({"content": "first"})
        manage_state.save_state(self.state_path, first)
        with self.assertRaises(manage_state.RevisionConflict):
            manage_state.save_state(self.state_path, second)
        self.assertEqual(manage_state.load_state(self.state_path)["blockers"], first["blockers"])

    def test_replace_failure_preserves_original_and_cleans_temp(self):
        state = manage_state.create_initial_state()
        manage_state.save_state(self.state_path, state)
        old = self.state_path.read_bytes()
        with patch.object(manage_state.os, "replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                manage_state.save_state(self.state_path, state)
        self.assertEqual(self.state_path.read_bytes(), old)
        self.assertEqual(manage_state.state_revision(state), 1)
        self.assertEqual(list(self.state_path.parent.glob(".tmp-state-*")), [])

    def test_derived_completion_is_recomputed(self):
        state = manage_state.create_initial_state()
        state["completion"]["required_completed"] = 9
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(manage_state.load_state(self.state_path)["completion"]["required_completed"], 0)

    def test_missing_required_stage_and_corrupt_state_are_errors(self):
        state = manage_state.create_initial_state()
        state["stages"].pop(0)
        for content in (json.dumps(state), "[]", "{broken"):
            self.state_path.write_text(content, encoding="utf-8")
            self.assertEqual(manage_state.main(["show", "--json", "--state-path", str(self.state_path)]), 2)

    def test_os_releases_lock_when_writer_exits(self):
        code = ("import sys,os; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                "import manage_state; lock=manage_state.state_lock(Path(sys.argv[2])); "
                "lock.__enter__(); os._exit(0)")
        proc = subprocess.run([sys.executable, "-c", code, str(REPO_ROOT / "shared/scripts"),
                               str(self.state_path)], capture_output=True, timeout=10)
        self.assertEqual(proc.returncode, 0)
        with manage_state.state_lock(self.state_path, timeout=0.2):
            pass


if __name__ == "__main__":
    unittest.main()
