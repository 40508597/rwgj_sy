"""check_quality_redlines.py 单元测试（质量红线启发式）"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import check_quality_redlines as redlines  # noqa: E402

EXAMPLE = json.loads((REPO_ROOT / "shared/assets/example-architecture.json").read_text(encoding="utf-8"))


class TestRedlines(unittest.TestCase):
    def test_example_passes(self):
        """完整示例不应触发红线（验证锚点与 verify-all 一致）。"""
        errors, warnings, _ = redlines.check_redlines(EXAMPLE)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_action_leaf_without_exception_path(self):
        """操作类叶子节点缺异常路径 → 红线。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["功能树"].append({
            "编号": "f9", "名称": "删除用户", "类型": "功能", "分类": "核心功能",
            "子节点": [], "架构落位": {"模块": ["m_user"]},
        })
        errors, _, _ = redlines.check_redlines(data)
        self.assertTrue(any("异常路径" in e for e in errors))

    def test_bulk_feature_without_safety_signals(self):
        """导出类功能缺安全与可靠性信号 → 红线。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["功能树"].append({
            "编号": "f9", "名称": "导出数据", "类型": "功能", "分类": "核心功能",
            "子节点": [], "说明": "一键导出", "异常路径": ["文件损坏"],
            "架构落位": {"模块": ["m_user"]},
        })
        errors, _, _ = redlines.check_redlines(data)
        self.assertTrue(any("安全与可靠性信号" in e for e in errors))

    def test_leaf_without_acceptance_criteria_warns(self):
        """叶子节点缺验收标准/测试落位 → 警告（不阻塞）。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["功能树"].append({
            "编号": "f9", "名称": "查询日志", "类型": "功能", "分类": "核心功能",
            "子节点": [], "异常路径": ["无日志"],
        })
        errors, warnings, _ = redlines.check_redlines(data)
        self.assertEqual(errors, [])
        self.assertTrue(any("验收标准" in w for w in warnings))
        self.assertTrue(any("架构落位.测试" in w for w in warnings))

    def test_hollow_module_warns(self):
        """模块详情填充率 < 50% → 空壳模块警告。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["模块详情"]["m_hollow"] = {"职责": "x"}
        _, warnings, _ = redlines.check_redlines(data)
        self.assertTrue(any("空壳模块" in w for w in warnings))

    def test_state_machine_conflict_warns(self):
        """状态机声明「不适用」但数据读写含状态流转信号 → 警告。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["模块详情"]["m_conflict"] = {
            "职责": "y", "状态机": "不适用",
            "数据读写责任": [{"表名": "orders", "操作": ["update"], "说明": "订单状态流转"}],
        }
        _, warnings, _ = redlines.check_redlines(data)
        self.assertTrue(any("状态流转信号" in w for w in warnings))


class TestMainExitCode(unittest.TestCase):
    def test_main_returns_1_on_redline(self):
        data = json.loads(json.dumps(EXAMPLE))
        data["功能树"].append({"编号": "f9", "名称": "删除用户", "子节点": [],
                               "架构落位": {"模块": []}})
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "arch.json"
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(redlines.main([str(p)]), 1)

    def test_main_returns_0_on_clean(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "arch.json"
            p.write_text(json.dumps(EXAMPLE, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(redlines.main([str(p)]), 0)


if __name__ == "__main__":
    unittest.main()
