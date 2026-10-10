"""detect_should_trigger.py 单元测试（自指豁免 + 触发判定纯函数）"""

import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import detect_should_trigger  # noqa: E402


class TestIsCapabilityPackage(unittest.TestCase):
    def test_skill_frontmatter_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "SKILL.md").write_text(
                "---\nname: xl-ai-language\ndescription: 测试\n---\n# 任务架构\n", encoding="utf-8")
            for relative in ("shared/scripts/_archlib.py", "shared/assets/schema/architecture.schema.json",
                             "skills/xl-ai-language/LAYER.md"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("结构夹具", encoding="utf-8")
            self.assertTrue(detect_should_trigger.is_capability_package_itself(root))

    def test_other_skill_not_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "SKILL.md").write_text(
                "---\nname: other-skill\ndescription: 测试\n---\n", encoding="utf-8")
            self.assertFalse(detect_should_trigger.is_capability_package_itself(root))

    def test_agent_usage_alone_not_capability(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENT-USAGE.md").write_text("通用入口", encoding="utf-8")
            self.assertFalse(detect_should_trigger.is_capability_package_itself(root))

    def test_empty_dir_not_detected(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(detect_should_trigger.is_capability_package_itself(Path(td)))


class TestShouldTriggerTaskArchitecture(unittest.TestCase):
    def test_managed_project_never_scans_code(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture").mkdir()
            with patch.object(detect_should_trigger, "iter_structure_files", side_effect=AssertionError("scanned")):
                self.assertTrue(detect_should_trigger.should_trigger_task_architecture(root)[0])

    def test_dependencies_do_not_inflate_project_size(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for directory in ("src", "lib", "node_modules"):
                (root / directory).mkdir()
            (root / "package.json").write_text("{}", encoding="utf-8")
            for i in range(30):
                (root / "node_modules" / f"vendor{i}.py").write_text("pass", encoding="utf-8")
            self.assertFalse(detect_should_trigger.should_trigger_task_architecture(root)[0])

    def test_size_probe_stops_after_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for directory in ("src", "lib"):
                (root / directory).mkdir()
            (root / "package.json").write_text("{}", encoding="utf-8")
            def files(*args):
                for i in range(11):
                    yield f"src/{i}.py"
                raise AssertionError("scan did not stop at threshold")
            with patch.object(detect_should_trigger, "iter_structure_files", side_effect=files):
                self.assertTrue(detect_should_trigger.should_trigger_task_architecture(root)[0])

    def test_managed_project_triggers(self):
        """存在 architecture.json 指针 → 触发。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text(
                '{"指向": "architecture/index.json"}', encoding="utf-8")
            should, reasons = detect_should_trigger.should_trigger_task_architecture(root)
            self.assertTrue(should)
            self.assertTrue(any("architecture.json" in r for r in reasons))

    def test_architecture_dir_triggers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture").mkdir()
            (root / "architecture" / "index.json").write_text("{}", encoding="utf-8")
            should, _ = detect_should_trigger.should_trigger_task_architecture(root)
            self.assertTrue(should)

    def test_empty_project_not_triggers(self):
        with tempfile.TemporaryDirectory() as td:
            should, _ = detect_should_trigger.should_trigger_task_architecture(Path(td))
            self.assertFalse(should)

    def test_multi_module_project_triggers(self):
        """多模块（≥2 目录）+ 项目配置 + 代码量 > 10 → 触发。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for d in ("src", "lib"):
                (root / d).mkdir()
            (root / "package.json").write_text("{}", encoding="utf-8")
            for i in range(12):
                (root / "src" / f"f{i}.py").write_text("x = 1\n", encoding="utf-8")
            should, _ = detect_should_trigger.should_trigger_task_architecture(root)
            self.assertTrue(should)


if __name__ == "__main__":
    unittest.main()
