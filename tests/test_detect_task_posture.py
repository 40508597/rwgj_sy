"""detect_task_posture.py 单元测试（关键词匹配 / 风险分级 / 姿态判定纯函数）"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import detect_task_posture  # noqa: E402

RULES = json.loads((REPO_ROOT / "shared/assets/task-posture-rules.json").read_text(encoding="utf-8"))


class TestTextHelpers(unittest.TestCase):
    def test_collect_matches_case_insensitive(self):
        self.assertEqual(
            detect_task_posture.collect_matches("新增一个导出功能", ["新增", "导出"]),
            ["新增", "导出"])

    def test_contains_any(self):
        self.assertTrue(detect_task_posture.contains_any("删除用户", ["删除"]))
        self.assertFalse(detect_task_posture.contains_any("查询用户", ["删除"]))

    def test_unique_preserves_order(self):
        self.assertEqual(detect_task_posture.unique(["a", "b", "a"]), ["a", "b"])


class TestDetectRisk(unittest.TestCase):
    def test_high_risk_word(self):
        self.assertEqual(detect_task_posture.detect_risk("需要做支付迁移", RULES), "高")

    def test_medium_risk_word(self):
        self.assertEqual(detect_task_posture.detect_risk("批量导出数据", RULES), "中")

    def test_low_risk(self):
        self.assertEqual(detect_task_posture.detect_risk("添加一个查询功能", RULES), "低")

    def test_risk_words_single_source_loaded(self):
        """规则文件已不再内嵌风险词，检测器回退读 risk-words.json 单一真相源。"""
        self.assertIn("风险词说明", RULES)
        self.assertNotIn("风险词", RULES)
        self.assertEqual(detect_task_posture.detect_risk("删除用户", RULES), "高")

    def test_refactor_stays_medium_risk(self):
        """兼容性回归：老规则中「重构」属中风险，单源化后不得丢失。"""
        self.assertEqual(detect_task_posture.detect_risk("重构模块", RULES), "中")

    def test_rules_risk_override_takes_precedence(self):
        custom = json.loads(json.dumps(RULES))
        custom["风险词"] = {"高": ["炸"], "中": []}
        self.assertEqual(detect_task_posture.detect_risk("点个炸鸡", custom), "高")
        self.assertEqual(detect_task_posture.detect_risk("点个炸鸡", RULES), "低")


class TestDetectTaskPosture(unittest.TestCase):
    def test_managed_project_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            result = detect_task_posture.detect_task_posture("新增一个导出功能", root, RULES)
            self.assertTrue(result["受管项目"])
            self.assertIn("architecture.json", result["必须加载"])

    def test_sliced_project_pointer_points_to_index(self):
        """兼容性：仅 architecture/ 切片目录的老项目，必须加载指向 architecture/index.json。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture").mkdir()
            (root / "architecture/index.json").write_text("{}", encoding="utf-8")
            result = detect_task_posture.detect_task_posture("新增一个导出功能", root, RULES)
            self.assertTrue(result["受管项目"])
            self.assertIn("architecture/index.json", result["必须加载"])

    def test_auxiliary_directory_does_not_invent_centralized_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture/quality").mkdir(parents=True)
            result = detect_task_posture.detect_task_posture("纳管已有项目并增加库存预留", root, RULES)
            self.assertTrue(result["受管项目"])
            self.assertIn("architecture.json", result["必须加载"])
            self.assertNotIn("architecture/index.json", result["必须加载"])

    def test_unmanaged_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_task_posture.detect_task_posture("查询一下", Path(td), RULES)
            self.assertFalse(result["受管项目"])
            self.assertIn("SKILL.md", result["必须加载"])

    def test_task_type_and_domain(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_task_posture.detect_task_posture("帮我设计一个数据看板", Path(td), RULES)
            self.assertIn("模糊需求", result["任务类型"])
            self.assertIn("数据", result["专业领域"])

    def test_auditor_always_present(self):
        """结果必须包含审计员视角（交叉审计基线）。"""
        with tempfile.TemporaryDirectory() as td:
            result = detect_task_posture.detect_task_posture("新增一个功能", Path(td), RULES)
            self.assertIn("审计员", result["执行角色"])

    def test_verdict_contract(self):
        """输出契约：关键 key 必须存在。"""
        with tempfile.TemporaryDirectory() as td:
            result = detect_task_posture.detect_task_posture("做一个系统", Path(td), RULES)
            for key in ("任务类型", "受管项目", "风险等级", "置信度", "命中依据",
                        "执行角色", "必须加载", "必须校验", "禁止事项", "裁决边界"):
                self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
