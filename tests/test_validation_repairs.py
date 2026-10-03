"""Independent regression counterexamples for the full audit validation repairs."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "scripts"))
import audit_architecture
import check_doc_counts
import check_placeholders
import demo_project
import detect_should_trigger
import detect_task_posture
import taskarch_cli
import validate_agent_output
import validate_architecture


def example():
    return json.loads((ROOT / "shared/assets/example-architecture.json").read_text(encoding="utf-8"))


def report(conclusion="yes"):
    result = audit_architecture.build_questionnaire("fixture.json")
    for item in result["问题清单"]:
        item.update({"结论": conclusion, "证据": "实测输入、命令与输出记录"})
    return result


class CompletionRepairTests(unittest.TestCase):
    def assert_blocked(self, data):
        errors, _ = validate_architecture.validate_architecture(data, Path("."))
        self.assertTrue(errors)
        self.assertTrue(check_placeholders.categorize_placeholders(data, check_placeholders.load_schema())["critical"])

    def test_blank_project_name_blocked(self):
        data = example()
        data["项目"]["名称"] = " \n "
        self.assert_blocked(data)

    def test_blank_project_type_blocked(self):
        data = example()
        data["项目"]["类型"] = ""
        self.assert_blocked(data)

    def test_empty_module_details_blocked(self):
        data = example()
        data["模块详情"] = {}
        self.assert_blocked(data)

    def test_topology_module_without_detail_blocked(self):
        data = example()
        data["模块详情"].pop(next(iter(data["模块详情"])))
        self.assert_blocked(data)

    def test_empty_evidence_object_blocked(self):
        data = example()
        data["验证证据"] = {}
        self.assert_blocked(data)

    def test_empty_evidence_classes_blocked(self):
        data = example()
        data["验证证据"] = {name: [] for name in data["验证证据"]}
        self.assert_blocked(data)

    def test_empty_evidence_records_do_not_count(self):
        data = example()
        data["验证证据"] = {"自动化测试": [None, " ", {}, {"命令": ""}]}
        self.assert_blocked(data)

    def test_missing_recovery_core_blocked(self):
        for field in validate_architecture.FALLBACK_RECOVERY_CORE_SUBFIELDS:
            with self.subTest(field=field):
                data = example()
                data["上下文恢复点"].pop(field)
                self.assert_blocked(data)

    def test_empty_recovery_context_blocked(self):
        data = example()
        data["上下文恢复点"]["当前阶段"] = " "
        self.assert_blocked(data)

    def test_optional_event_and_ui_absence_allowed(self):
        data = example()
        data["入口"] = {key: [] for key in data["入口"]}
        data["页面拓扑"] = []
        errors, _ = validate_architecture.validate_architecture(data, Path("."))
        self.assertEqual(errors, [])

    def test_skeleton_allows_unfinished_completion_artifacts(self):
        data = example()
        for field in ("功能树", "模块树", "测试责任矩阵"):
            data[field] = []
        data["模块详情"] = {}
        data["实现清单"] = {}
        data["验证证据"] = {}
        data["上下文恢复点"] = {}
        data["项目"]["名称"] = ""
        errors, _ = validate_architecture.validate_architecture(data, Path("."), "skeleton")
        self.assertEqual(errors, [])

    def test_manifest_accepts_strings_and_merges_both_fields(self):
        data = example()
        data["实现清单"]["m_user"] = {"文件列表": ["unit.blob"], "文件": [{"路径": "extensionless-unit"}]}
        errors, warnings = validate_architecture.validate_architecture(data, Path("."))
        self.assertEqual(errors, [])
        self.assertTrue(any("unit.blob" in value for value in warnings))
        self.assertTrue(any("extensionless-unit" in value for value in warnings))

    def test_self_cycle_rejected_with_path(self):
        data = example()
        data["模块拓扑"]["依赖图"] = [{"从": "m_user", "到": "m_user"}]
        errors, _ = validate_architecture.validate_architecture(data, Path("."))
        self.assertTrue(any("m_user -> m_user" in error for error in errors))

    def test_multi_module_cycle_rejected_with_path(self):
        edges = [{"从": "alpha", "到": "beta"}, {"从": "beta", "到": "gamma"}, {"从": "gamma", "到": "alpha"}]
        self.assertEqual(validate_architecture.dependency_cycle(edges), ["alpha", "beta", "gamma", "alpha"])

    def test_large_dag_does_not_use_python_recursion(self):
        edges = [{"从": str(i), "到": str(i + 1)} for i in range(3000)]
        self.assertEqual(validate_architecture.dependency_cycle(edges), [])

    def test_documented_auxiliary_json_not_unregistered_slices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("architecture/index.json", "architecture/_state.json",
                             "architecture/quality/facts.json", "architecture/quality/policy.json",
                             "architecture/quality/test-receipt.json"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            data = example()
            data["架构切片"] = {"启用": True, "切片清单": []}
            _, warnings = validate_architecture.validate_architecture(data, root)
            self.assertFalse(any("未登记到 架构切片.切片清单" in warning for warning in warnings), warnings)

    def test_unknown_module_json_still_requires_slice_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("architecture/_state.json", "architecture/quality/policy.json",
                             "architecture/modules/undeclared.json", "architecture/modules/index.json",
                             "architecture/tasks/unregistered-state.json"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            data = example()
            data["架构切片"] = {"启用": True, "切片清单": []}
            _, warnings = validate_architecture.validate_architecture(data, root)
            undeclared = [warning for warning in warnings if "未登记到 架构切片.切片清单" in warning]
            self.assertEqual(len(undeclared), 3, undeclared)
            for relative in ("architecture/modules/undeclared.json", "architecture/modules/index.json",
                             "architecture/tasks/unregistered-state.json"):
                self.assertTrue(any(relative in warning for warning in undeclared), undeclared)


def empty_core_method(field):
    def method(self):
        data = example()
        data[field] = [] if isinstance(data[field], list) else {}
        self.assert_blocked(data)
    return method


for field in ("功能树", "模块树", "实现清单", "测试责任矩阵", "上下文恢复点"):
    setattr(CompletionRepairTests, "test_empty_" + field + "_blocked", empty_core_method(field))


class AuditRepairTests(unittest.TestCase):
    def test_empty_questionnaire_not_complete(self):
        self.assertTrue(audit_architecture.validate_report({"问题清单": []})[1])

    def test_duplicate_question_cannot_replace_other_questions(self):
        value = report()
        value["问题清单"] = [copy.deepcopy(value["问题清单"][0]) for _ in range(10)]
        passed, errors, _ = audit_architecture.validate_report(value)
        self.assertEqual(passed, 1)
        self.assertTrue(any("重复" in error for error in errors))
        self.assertTrue(any("q10" in error for error in errors))

    def test_unknown_question_rejected(self):
        value = report()
        value["问题清单"][0]["编号"] = "q11"
        self.assertTrue(audit_architecture.validate_report(value)[1])

    def test_null_evidence_not_valid(self):
        value = report()
        value["问题清单"][0]["证据"] = None
        self.assertTrue(audit_architecture.validate_report(value)[1])

    def test_nonstring_evidence_not_valid(self):
        value = report()
        value["问题清单"][0]["证据"] = {"unknown": "a path"}
        self.assertTrue(audit_architecture.validate_report(value)[1])

    def test_na_needs_reason(self):
        value = report("na")
        value["问题清单"][0]["证据"] = ""
        self.assertTrue(audit_architecture.validate_report(value)[1])
        value["问题清单"][0]["不适用原因"] = "该项目没有用户交互；范围已核对"
        self.assertEqual(audit_architecture.validate_report(value)[1], [])

    def test_unhashable_conclusion_is_clean_error(self):
        value = report()
        value["问题清单"][0]["结论"] = []
        self.assertTrue(audit_architecture.validate_report(value)[1])

    def test_valid_negative_report_does_not_claim_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            path.write_text(json.dumps(report("no"), ensure_ascii=False), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit_architecture.main(["report", str(path)]), 1)

    def test_generated_questionnaire_is_pending(self):
        value = audit_architecture.build_questionnaire("fixture.json")
        self.assertEqual(value["状态"], "待审")
        self.assertTrue(audit_architecture.validate_report(value)[1])


class InputAndScopeRepairTests(unittest.TestCase):
    def test_invalid_agent_enums_are_errors_instead_of_crashes(self):
        rules = validate_agent_output.derive_rules_from_schema(None)
        for value in (None, [], {}, 4, True):
            with self.subTest(value=value):
                errors, _ = validate_agent_output.validate_agent_output({"输出类型": value, "结论": value}, *rules)
                self.assertEqual(len(errors), 2)

    def test_bad_utf8_agent_output_returns_structured_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_bytes(b'{"broken":"\xff"}')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(validate_agent_output.main([str(path), "--json"]), 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "unknown")

    def test_bad_utf8_task_cli_returns_structured_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_bytes(b'\xff')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(taskarch_cli.main(["slice", "--architecture", str(path), "--path", "功能树"]), 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "unknown")

    def test_out_of_range_list_index_returns_null(self):
        self.assertIsNone(taskarch_cli.get_path({"items": ["a"]}, "items.99"))
        self.assertIsNone(taskarch_cli.get_path({"items": ["a"]}, "items." + "9" * 5000))
        self.assertEqual(taskarch_cli.get_path({"items": ["a"]}, "items.0000"), "a")

    def test_entry_names_cannot_exempt_managed_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            (root / "AGENT-USAGE.md").write_text("arbitrary unrelated guide", encoding="utf-8")
            (root / "SKILL.md").write_text("---\nname: 任务架构\n---\n", encoding="utf-8")
            self.assertTrue(detect_should_trigger.should_trigger_task_architecture(root)[0])

    def test_unmanaged_complexity_hint_is_language_independent(self):
        results = []
        for suffix in (".py", ".sql", ".opaque", ""):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "first-area").mkdir()
                (root / "second-area").mkdir()
                for i in range(12):
                    parent = "first-area" if i % 2 else "second-area"
                    (root / parent / (str(i) + suffix)).write_bytes(b"\x00\xffopaque-content")
                result, reasons = detect_should_trigger.should_trigger_task_architecture(root)
                results.append(result)
                self.assertTrue(any("不强制完整流程" in reason for reason in reasons))
        self.assertEqual(results, [True] * 4)

    def test_small_arbitrary_directories_do_not_trigger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("first-area", "second-area"):
                (root / name).mkdir()
                (root / name / "unit").write_bytes(b"\xff")
            self.assertFalse(detect_should_trigger.should_trigger_task_architecture(root)[0])

    def test_nonempty_demo_target_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "architecture.json"
            original.write_bytes(b"original-user-content")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(demo_project.main(["--keep", str(root)]), 2)
            self.assertEqual(original.read_bytes(), b"original-user-content")
            self.assertEqual(list(root.iterdir()), [original])

    def test_demo_setup_api_also_refuses_existing_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "service.py"
            sentinel.write_text("KEEP", encoding="utf-8")
            with self.assertRaises(ValueError):
                demo_project.setup_project(root)
            self.assertEqual(sentinel.read_text(), "KEEP")

    def test_deleted_doc_metric_rows_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            path.write_text("### 4.5 技术指标\n\n| 指标 | 数值 |\n| --- | --- |\n\n### 4.6 next\n", encoding="utf-8")
            with patch.object(check_doc_counts, "README", path):
                with self.assertRaisesRegex(ValueError, "指标缺失"):
                    check_doc_counts.read_claims()

    def test_bad_risk_word_file_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "risk-words.json"
            path.write_text("{broken", encoding="utf-8")
            with patch.object(detect_task_posture, "RISK_WORDS_PATH", path):
                self.assertEqual(detect_task_posture.detect_risk("删除生产数据库", {}), "未知")

    def test_malformed_override_cannot_be_low_risk(self):
        for value in ({}, {"高": "删除", "中": []}, {"高": [None], "中": []}):
            with self.subTest(value=value):
                self.assertEqual(detect_task_posture.detect_risk("删除生产数据库", {"风险词": value}), "未知")


if __name__ == "__main__":
    unittest.main()
