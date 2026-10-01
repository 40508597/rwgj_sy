"""detect_small_command.py 单元测试（三档判定 / 优先级 / 提问句式 / 风险升档 / 运行修改分型 / 输出契约）

审计回归用例：test_classify_audit_regressions 固化独立审计发现的全部词表误判场景，
防止修复后回退。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import detect_small_command  # noqa: E402

RULES = json.loads((REPO_ROOT / "shared/assets/small-command-rules.json").read_text(encoding="utf-8"))


class TestClassify(unittest.TestCase):
    def test_start_project_minimal(self):
        tier, evidence, _ = detect_small_command.classify("启动项目", RULES)
        self.assertEqual(tier, "最小闭环")
        self.assertTrue(any("启动" in e for e in evidence))

    def test_modify_element_minimal(self):
        tier, _, _ = detect_small_command.classify("帮我修改某个元素的颜色", RULES)
        self.assertEqual(tier, "最小闭环")

    def test_run_single_command_minimal(self):
        tier, _, _ = detect_small_command.classify("运行一下测试", RULES)
        self.assertEqual(tier, "最小闭环")

    def test_view_skip(self):
        tier, _, _ = detect_small_command.classify("查看项目", RULES)
        self.assertEqual(tier, "完全跳过")

    def test_concept_question_skip(self):
        tier, _, _ = detect_small_command.classify("介绍一下三层路由", RULES)
        self.assertEqual(tier, "完全跳过")

    def test_temp_experiment_skip(self):
        tier, _, _ = detect_small_command.classify("写个临时脚本试试", RULES)
        self.assertEqual(tier, "完全跳过")

    def test_refactor_full(self):
        tier, _, _ = detect_small_command.classify("重构系统架构", RULES)
        self.assertEqual(tier, "完整流程")

    def test_new_feature_full(self):
        tier, _, _ = detect_small_command.classify("新增一个导出功能", RULES)
        self.assertEqual(tier, "完整流程")

    def test_modify_architecture_wins_over_modify(self):
        """优先级：完整流程词优先于最小闭环词（修改架构不得降级）。"""
        tier, evidence, _ = detect_small_command.classify("修改架构", RULES)
        self.assertEqual(tier, "完整流程")
        self.assertTrue(any("架构" in e for e in evidence))

    def test_view_architecture_is_read_only(self):
        tier, _, _ = detect_small_command.classify("查看架构", RULES)
        self.assertEqual(tier, "完全跳过")

    def test_unknown_defaults_to_full(self):
        """拿不准一律完整流程（保守默认）。"""
        tier, _, _ = detect_small_command.classify("帮我写一首诗", RULES)
        self.assertEqual(tier, "完整流程")

    def test_empty_defaults_to_full(self):
        tier, _, _ = detect_small_command.classify("", RULES)
        self.assertEqual(tier, "完整流程")


class TestClassifyAuditRegressions(unittest.TestCase):
    """独立审计（2026-08-13）发现的误判场景，逐条固化。"""

    def test_interpreter_not_skip(self):
        """「解释」是「解释器」子串，完整功能开发不得被跳过。"""
        tier, _, _ = detect_small_command.classify("帮我写一个解释器", RULES)
        self.assertEqual(tier, "完整流程")

    def test_extension_name_not_full(self):
        """「扩展」是「扩展名」子串，琐碎改名不得拉进完整流程。"""
        tier, _, _ = detect_small_command.classify("改一下这个文件的扩展名", RULES)
        self.assertEqual(tier, "最小闭环")

    def test_fix_bug_with_shishi_minimal(self):
        tier, _, _ = detect_small_command.classify("试试修复这个 bug", RULES)
        self.assertEqual(tier, "最小闭环")

    def test_fix_all_bugs_with_once_minimal(self):
        tier, _, _ = detect_small_command.classify("一次性修复所有 bug", RULES)
        self.assertEqual(tier, "最小闭环")

    def test_look_at_bug_minimal(self):
        tier, _, _ = detect_small_command.classify("看看这个 bug", RULES)
        self.assertEqual(tier, "最小闭环")

    def test_view_system_log_skip(self):
        tier, _, _ = detect_small_command.classify("查看系统日志", RULES)
        self.assertEqual(tier, "完全跳过")

    def test_how_to_use_system_skip(self):
        tier, _, source = detect_small_command.classify("这个系统怎么用", RULES)
        self.assertEqual(tier, "完全跳过")
        self.assertEqual(source, "提问句式")

    def test_explain_design_pattern_skip(self):
        tier, _, source = detect_small_command.classify("解释一下设计模式", RULES)
        self.assertEqual(tier, "完全跳过")
        self.assertEqual(source, "提问句式")

    def test_skill_self_reference_skip(self):
        tier, _, source = detect_small_command.classify("任务架构怎么用", RULES)
        self.assertEqual(tier, "完全跳过")
        self.assertEqual(source, "自指问答")

    def test_introduce_interface_skip(self):
        tier, _, _ = detect_small_command.classify("介绍一下这个接口", RULES)
        self.assertEqual(tier, "完全跳过")

    def test_restart_system_minimal(self):
        tier, _, _ = detect_small_command.classify("重启系统", RULES)
        self.assertEqual(tier, "最小闭环")

    def test_why_startup_failed_minimal(self):
        """提问句式 + 失败词：调试需求不得被句式判成跳过。"""
        tier, _, _ = detect_small_command.classify("为什么系统启动失败", RULES)
        self.assertEqual(tier, "最小闭环")

    def test_what_is_architecture_is_concept_question(self):
        """架构概念问答不启动修改流程。"""
        tier, _, _ = detect_small_command.classify("架构是什么", RULES)
        self.assertEqual(tier, "完全跳过")


class TestRiskUpgrade(unittest.TestCase):
    def test_delete_production_data_forced_full(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            result = detect_small_command.detect_small_command("删个生产环境的数据", root, RULES)
            self.assertEqual(result["判定档位"], "完整流程")
            self.assertEqual(result["风险等级"], "高")
            self.assertTrue(any("风险升档" in e for e in result["命中依据"]))

    def test_modify_payment_config_forced_full(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("修改一下支付配置", Path(td), RULES)
            self.assertEqual(result["判定档位"], "完整流程")
            self.assertEqual(result["风险等级"], "高")

    def test_run_payment_script_forced_full(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("跑一下支付转账脚本", Path(td), RULES)
            self.assertEqual(result["判定档位"], "完整流程")
            self.assertEqual(result["风险等级"], "高")

    def test_view_permission_config_skip_with_risk_signal(self):
        """高风险只读查看：不升档（无操作可保护），但必须带风险等级信号。"""
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("查看权限配置", Path(td), RULES)
            self.assertEqual(result["有效档位"], "完全跳过")
            self.assertEqual(result["风险等级"], "高")

    def test_medium_risk_keeps_tier_with_confirm(self):
        """中风险：保留档位但必须动作追加风险确认。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            result = detect_small_command.detect_small_command("运行一下部署脚本", root, RULES)
            self.assertEqual(result["有效档位"], "最小闭环")
            self.assertEqual(result["风险等级"], "中")
            self.assertTrue(any("风险确认" in x for x in result["必须动作"]))

    def test_risk_question_not_upgraded(self):
        """纯问答无操作可保护，风险词不升档。"""
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("删除是什么", Path(td), RULES)
            self.assertEqual(result["有效档位"], "完全跳过")
            self.assertEqual(result["风险等级"], "高")

    def test_load_risk_words_single_source(self):
        """风险词单一真相源 risk-words.json 可读且分级完整。"""
        words = detect_small_command.load_risk_words()
        self.assertTrue(words.get("高"))
        self.assertTrue(words.get("中"))
        self.assertIn("支付", words["高"])
        self.assertIn("部署", words["中"])

    def test_rules_risk_override_takes_precedence(self):
        """规则文件内「风险词」字段优先于单一真相源（临时覆盖能力）。"""
        custom = json.loads(json.dumps(RULES))
        custom["风险词"] = {"高": ["炸"], "中": []}
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("启动炸服务", Path(td), custom)
            self.assertEqual(result["风险等级"], "高")
            self.assertEqual(result["判定档位"], "完整流程")


class TestClosedLoopType(unittest.TestCase):
    def test_run_type_no_triple_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            result = detect_small_command.detect_small_command("启动项目", root, RULES)
            self.assertEqual(result["有效档位"], "最小闭环")
            self.assertEqual(result["闭环类型"], "运行")
            self.assertNotIn("三重校验", result["必须动作"])
            self.assertIn("记录验证证据", result["必须动作"])

    def test_modify_type_has_triple_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            result = detect_small_command.detect_small_command("修改某个元素", root, RULES)
            self.assertEqual(result["有效档位"], "最小闭环")
            self.assertEqual(result["闭环类型"], "修改")
            self.assertIn("三重校验", result["必须动作"])
            self.assertIn("功能簇最小定位", result["必须动作"])


class TestDetectSmallCommand(unittest.TestCase):
    def test_minimal_in_managed_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            result = detect_small_command.detect_small_command("启动项目", root, RULES)
            self.assertEqual(result["有效档位"], "最小闭环")
            self.assertTrue(result["降级"])
            self.assertTrue(result["受管项目"])

    def test_minimal_downgrades_to_skip_in_unmanaged_project(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("启动项目", Path(td), RULES)
            self.assertEqual(result["判定档位"], "最小闭环")
            self.assertEqual(result["有效档位"], "完全跳过")
            self.assertFalse(result["受管项目"])
            self.assertTrue(any("非受管" in note for note in result["降级说明"]))

    def test_skip_tier_notes_specific_reason(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("查看项目", Path(td), RULES)
            self.assertEqual(result["有效档位"], "完全跳过")
            self.assertTrue(any("纯只读查看" in note for note in result["降级说明"]))

    def test_full_tier(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("设计一个系统", Path(td), RULES)
            self.assertEqual(result["有效档位"], "完整流程")
            self.assertFalse(result["降级"])

    def test_feature_cluster_rule_only_for_minimal(self):
        """审计修复：功能簇要求仅最小闭环输出，完全跳过时为空（不得自相矛盾）。"""
        with tempfile.TemporaryDirectory() as td:
            skipped = detect_small_command.detect_small_command("查看项目", Path(td), RULES)
            self.assertEqual(skipped["功能簇要求"], "")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            minimal = detect_small_command.detect_small_command("修改某个元素", root, RULES)
            self.assertTrue(minimal["功能簇要求"])
            self.assertIn("最小定位", minimal["功能簇要求"])

    def test_receipt_minimal_matches_layer_template(self):
        """回执与 LAYER.md 模板一致：入口链路/触发原因/降级档位/要求/功能簇定位。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            result = detect_small_command.detect_small_command("修改某个元素", root, RULES)
            for line in ("入口链路：SKILL.md → skills/task-architecture/LAYER.md",
                         "触发原因：detect_small_command.py 自动判定为小命令",
                         "降级档位：最小闭环（修改类）",
                         "功能簇最小定位",
                         "三重校验",
                         "功能簇定位：["):
                self.assertIn(line, result["回执"])

    def test_receipt_skip_matches_layer_template(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("查看项目", Path(td), RULES)
            for line in ("✅ 已检查任务架构技能（小命令降级）",
                         "降级档位：完全跳过",
                         "原因：",
                         "后续：使用普通编程智能体能力处理"):
                self.assertIn(line, result["回执"])

    def test_receipt_full_matches_layer_startup_template(self):
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("重构架构", Path(td), RULES)
            for line in ("入口链路：SKILL.md → skills/task-architecture/LAYER.md",
                         "本次初判：完整流程",
                         "受管状态：",
                         "下一步："):
                self.assertIn(line, result["回执"])

    def test_verdict_contract(self):
        """输出契约：关键 key 必须存在。"""
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("重构架构", Path(td), RULES)
            for key in ("判定档位", "有效档位", "闭环类型", "降级", "受管项目", "风险等级",
                        "命中依据", "必须动作", "禁止事项", "功能簇要求", "降级说明", "回执", "裁决边界"):
                self.assertIn(key, result)


class TestCompoundIntents(unittest.TestCase):
    def test_question_or_reading_cannot_hide_action(self):
        requests = ["先解释这个技能怎么用，然后重构支付模块",
                    "看看日志，然后删除生产数据库", "查看并修改权限",
                    "查看日志，删除生产数据", "查看日志 删除生产数据",
                    "介绍一下这个技能；请重构支付模块", "这个技能怎么用？请直接修改支付配置"]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture").mkdir()
            for request in requests:
                with self.subTest(request=request):
                    result = detect_small_command.detect_small_command(request, root, RULES)
                    self.assertEqual(result["有效档位"], "完整流程")

    def test_pure_reading_and_risk_questions_stay_light(self):
        for request in ["查看架构", "查看权限配置", "如何删除数据库", "删除是什么", "请解释如何删除数据库",
                        "先解释这个技能怎么用，然后介绍支付流程"]:
            with self.subTest(request=request):
                self.assertEqual(detect_small_command.classify(request, RULES)[0], "完全跳过")

    def test_small_visual_change_variants(self):
        for request in ["把按钮改成蓝色", "将标题改为中文", "把图标换成圆形"]:
            with self.subTest(request=request):
                self.assertEqual(detect_small_command.classify(request, RULES)[0], "最小闭环")

    def test_mixed_running_and_modifying_uses_modify_loop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture").mkdir()
            result = detect_small_command.detect_small_command("运行项目，然后把按钮改成蓝色", root, RULES)
            self.assertEqual(result["闭环类型"], "修改")
            self.assertIn("三重校验", result["必须动作"])


class TestMalformedRules(unittest.TestCase):
    def test_missing_risk_rules_does_not_claim_low_risk(self):
        from unittest.mock import patch
        with patch.object(detect_small_command, "RISK_WORDS_PATH", Path("/missing-risk-rules.json")):
            with self.assertRaises(OSError):
                detect_small_command.detect_small_command("运行支付脚本", Path("."), RULES)

    def _rules_with(self, mutate):
        data = json.loads(json.dumps(RULES))
        mutate(data)
        return data

    def test_trigger_words_as_string_no_char_match(self):
        """触发词写成字符串（笔误）时不得按单字符匹配。"""
        def mutate(data):
            data["档位"]["完全跳过"]["触发词"] = "看看"
        bad = self._rules_with(mutate)
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("帮我看看", Path(td), bad)
            self.assertEqual(result["判定档位"], "完整流程")  # 非列表→无命中→默认

    def test_missing_trigger_words_no_crash(self):
        def mutate(data):
            del data["档位"]["最小闭环"]["触发词"]
        bad = self._rules_with(mutate)
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("启动项目", Path(td), bad)
            self.assertEqual(result["判定档位"], "完整流程")

    def test_missing_说明_receipt_fallback(self):
        def mutate(data):
            del data["档位"]["完全跳过"]["说明"]
        bad = self._rules_with(mutate)
        with tempfile.TemporaryDirectory() as td:
            result = detect_small_command.detect_small_command("查看项目", Path(td), bad)
            self.assertIn("原因：", result["回执"])


class TestMain(unittest.TestCase):
    def test_main_prints_json_and_returns_zero(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = detect_small_command.main(["--request", "启动项目", "--project-root", str(REPO_ROOT)])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("判定档位", data)

    def test_main_bad_rules_returns_two(self):
        import contextlib
        import io
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text("{ not json", encoding="utf-8")
            with contextlib.redirect_stdout(buf):
                rc = detect_small_command.main(["--request", "查看", "--rules", str(bad)])
        self.assertEqual(rc, 2)

    def test_main_bom_rules_accepted(self):
        """BOM 前缀规则文件必须可读（utf-8-sig 底座）。"""
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as td:
            rules_path = Path(td) / "rules.json"
            rules_path.write_bytes(b"\xef\xbb\xbf" + json.dumps(RULES, ensure_ascii=False).encode("utf-8"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = detect_small_command.main(["--request", "查看项目", "--rules", str(rules_path)])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["有效档位"], "完全跳过")


if __name__ == "__main__":
    unittest.main()
