"""Behavioral and negative controls for read-only capability planning."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "shared/scripts"
sys.path.insert(0, str(SCRIPTS))
import _capabilitylib as lib


class CapabilityPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project"
        self.install = self.root / "installed"
        self.project.mkdir()
        self.install.mkdir()
        (self.install / "指南.自定义").write_text("纯文本：任意领域，不限制语言。", encoding="utf-8")
        (self.install / "最小补充").write_text("所需最小参考", encoding="utf-8")
        self.context = self.project / "context.json"
        self.catalog = self.project / "catalog.json"
        self.context_data = {"stage": "验证", "tier": "full", "professional_domains": ["量子棋局"],
                             "read_scope": ["source/**", "architecture/**"], "write_scope": ["architecture/**"]}
        self.entry = {"id": "custom-review", "能力类型": "量子棋局审查", "source": "skill", "root": str(self.install),
                      "entry": "指南.自定义", "refs": ["最小补充"], "requires": {"stages": ["验证"], "professional_domains": ["量子棋局"]},
                      "read_scope": ["**"], "write_scope": ["**"], "allowed_writeback": ["/验证证据"], "covers_risks": ["棋局破坏"]}
        self.write(self.context, self.context_data)
        self.write(self.catalog, {"version": 1, "entries": [self.entry]})

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def plan(self, context=None, entries=None, previous=None):
        if context is not None:
            self.write(self.context, context)
        if entries is not None:
            self.write(self.catalog, {"version": 1, "entries": entries})
        return lib.build_plan(self.project, self.context, self.catalog, previous)

    def cli(self, args):
        proc = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "plan_capabilities.py"),
                               "--project", str(self.project), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
        self.assertNotIn("Traceback", proc.stderr)
        return proc, json.loads(proc.stdout)

    def test_custom_domain_arbitrary_extension_and_extensionless_reference(self):
        plan = self.plan()
        self.assertEqual(plan["status"], "planned")
        selected = plan["selected"][0]
        self.assertEqual(selected["id"], "custom-review")
        self.assertEqual({Path(x["path"]).name for x in selected["read_files"]}, {"指南.自定义", "最小补充"})
        for record in selected["read_files"]:
            self.assertTrue(Path(record["path"]).is_absolute())
            self.assertEqual(record["sha256"], hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest())

    def test_identical_inputs_are_deterministic_and_bound(self):
        before = {p: p.read_bytes() for p in (self.context, self.catalog, self.install / "指南.自定义")}
        a, b = self.plan(), self.plan()
        self.assertEqual(a, b)
        expected = hashlib.sha256(json.dumps({k: v for k, v in a.items() if k != "fingerprint"}, ensure_ascii=False,
                                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(a["fingerprint"], expected)
        self.assertTrue(a["planning_only"])
        self.assertNotIn("pass", a.values())
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_stage_mismatch_does_not_load(self):
        context = {**self.context_data, "stage": "需求理解"}
        self.assertEqual(self.plan(context)["selected"], [])

    def test_domain_mismatch_does_not_load(self):
        self.assertEqual(self.plan({**self.context_data, "professional_domains": ["未知另一领域"]})["selected"], [])

    def test_full_skip_does_not_read_body_despite_matching_stage_and_domain(self):
        (self.install / "指南.自定义").write_bytes(b"\xff")
        plan = self.plan({**self.context_data, "tier": "完全跳过"})
        self.assertEqual(plan["selected"], [])
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["unknown"], [])

    def test_full_skip_keeps_unresolved_required_risk_unknown(self):
        plan = self.plan({**self.context_data, "tier": "完全跳过", "required_risks": ["棋局破坏"]})
        self.assertEqual(plan["selected"], [])
        self.assertEqual(plan["status"], "unknown")

    def test_minimal_tier_requires_explicit_current_need(self):
        self.assertEqual(self.plan({**self.context_data, "tier": "最小闭环"})["selected"], [])
        plan = self.plan({**self.context_data, "tier": "最小闭环", "confirmed_capabilities": ["量子棋局审查"]})
        self.assertEqual(len(plan["selected"]), 1)

    def test_explicit_exclusion_beats_matching_conditions_and_required_is_unknown(self):
        plan = self.plan({**self.context_data, "required_capabilities": ["量子棋局审查"], "excluded_capabilities": ["custom-review"]})
        self.assertEqual(plan["selected"], [])
        self.assertEqual(plan["status"], "unknown")
        self.assertTrue(plan["unmet"])

    def test_stage_and_module_and_risk_conditions_are_all_required(self):
        entry = {**self.entry, "requires": {"stages": ["验证"], "module_ids": ["m棋局"], "risks": ["棋局破坏"]}}
        plan = self.plan({**self.context_data, "module_ids": ["m棋局"], "risks": ["棋局破坏"]}, [entry])
        self.assertEqual(len(plan["selected"]), 1)
        plan = self.plan({**self.context_data, "module_ids": ["m其他"], "risks": ["棋局破坏"]}, [entry])
        self.assertEqual(plan["selected"], [])

    def test_detector_keywords_do_not_authorize(self):
        context = {"stage": "验证", "专业领域": ["量子棋局"], "命中依据": ["关键词命中"], "裁决边界": "仅建议"}
        plan = self.plan(context)
        self.assertEqual(plan["selected"], [])
        self.assertTrue(plan["warnings"])

    def test_explicitly_confirmed_detector_domain_can_match(self):
        context = {"stage": "验证", "专业领域": ["量子棋局"], "命中依据": ["关键词命中"], "裁决边界": "仅建议", "姿态已确认": True}
        self.assertEqual(len(self.plan(context)["selected"]), 1)

    def test_formal_wrapper_and_three_axes(self):
        context = {"姿势语境": {"当前阶段": "验证", "执行档位": "full", "专业语境": ["量子棋局"],
                               "执行模式": ["审查"], "任务场景": ["修复"], "模块关系": {"主改模块": ["m棋局"]}}}
        plan = self.plan(context)
        self.assertEqual(len(plan["selected"]), 1)
        self.assertEqual(plan["normalized_context"]["module_ids"], ["m棋局"])
        self.assertEqual(plan["normalized_context"]["execution_roles"], ["审查"])

    def test_alias_or_wrapper_conflict_rejected(self):
        with self.assertRaises(lib.CapabilityInputError):
            self.plan({"stage": "验证", "姿势语境": {"当前阶段": "实现"}})

    def test_explicit_capability_unavailable_is_unknown(self):
        plan = self.plan({**self.context_data, "confirmed_capabilities": ["未安装能力"]})
        self.assertEqual(plan["status"], "unknown")
        self.assertIn("能力需求未满足: 未安装能力", plan["unmet"])

    def test_missing_selected_entry_is_unknown(self):
        entry = {**self.entry, "entry": "不存在"}
        plan = self.plan(entries=[entry])
        self.assertEqual(plan["status"], "unknown")
        self.assertEqual(plan["selected"], [])

    def test_missing_minimum_reference_is_unknown(self):
        plan = self.plan(entries=[{**self.entry, "refs": ["不存在的最小资料"]}])
        self.assertEqual(plan["status"], "unknown")

    def test_per_file_override_and_fallback_are_explicit(self):
        (self.project / "指南.自定义").write_text("项目覆盖", encoding="utf-8")
        plan = self.plan(entries=[{**self.entry, "project_override": True}])
        records = {Path(x["path"]).name: x for x in plan["selected"][0]["read_files"]}
        self.assertEqual(records["指南.自定义"]["origin"], "project")
        self.assertEqual(records["最小补充"]["origin"], "catalog")
        self.assertEqual(Path(records["指南.自定义"]["declared_root"]), self.project)

    def test_traversal_rejected_before_read(self):
        for value in ("../逃逸", "C:/Windows/a", "..\\逃逸", "/absolute"):
            with self.subTest(value=value), self.assertRaises(lib.CapabilityInputError):
                self.plan(entries=[{**self.entry, "entry": value}])

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(lib.CapabilityInputError):
            self.plan(entries=[self.entry, self.entry])

    def test_duplicate_json_key_rejected(self):
        self.context.write_text('{"stage":"验证","stage":"需求理解"}', encoding="utf-8")
        with self.assertRaises(lib.CapabilityInputError):
            lib.build_plan(self.project, self.context, self.catalog)

    def test_nan_json_rejected(self):
        self.context.write_text('{"stage":"验证","x":NaN}', encoding="utf-8")
        with self.assertRaises(lib.CapabilityInputError):
            lib.build_plan(self.project, self.context, self.catalog)

    def test_unknown_registered_condition_rejected(self):
        with self.assertRaises(lib.CapabilityInputError):
            self.plan(entries=[{**self.entry, "requires": {"languages": ["Python"]}}])

    def test_provider_ambiguity_is_unknown_without_reading_both(self):
        other = {**self.entry, "id": "same-domain-other"}
        plan = self.plan(entries=[self.entry, other])
        self.assertEqual(plan["status"], "unknown")
        self.assertEqual(plan["selected"], [])

    def test_explicit_priority_resolves_provider(self):
        other = {**self.entry, "id": "preferred", "priority": 3}
        self.assertEqual(self.plan(entries=[self.entry, other])["selected"][0]["id"], "preferred")

    def test_selected_reasons_bind_each_actual_registered_condition(self):
        other = {**self.entry, "id": "different-domain", "能力类型": "第二能力", "requires": {"stages": ["验证"]}}
        plan = self.plan(entries=[self.entry, other])
        selected = {x["id"]: x for x in plan["selected"]}
        for entry in (self.entry, other):
            decoded = selected[entry["id"]]["reason"][-1].split("=", 1)[1]
            self.assertEqual(json.loads(decoded), entry["requires"])

    def test_budget_excess_keeps_full_plan_and_unknown(self):
        plan = self.plan({**self.context_data, "budget": {"max_files": 1, "max_bytes": 1}})
        self.assertEqual(plan["status"], "unknown")
        self.assertEqual(len(plan["selected"][0]["read_files"]), 2)
        self.assertIn("预算", "".join(plan["unknown"]))

    def test_budget_bool_and_negative_rejected(self):
        for budget in ({"max_files": True}, {"max_files": -1}, {"garbage": 1}):
            with self.subTest(budget=budget), self.assertRaises(lib.CapabilityInputError):
                self.plan({**self.context_data, "budget": budget})

    def test_changed_skill_file_changes_fingerprint(self):
        a = self.plan()
        (self.install / "指南.自定义").write_text("资料更新", encoding="utf-8")
        self.assertNotEqual(a["fingerprint"], self.plan()["fingerprint"])

    def test_retire_and_add_from_changed_context(self):
        old = self.plan()
        previous = self.project / "previous.json"
        self.write(previous, old)
        plan = self.plan({**self.context_data, "stage": "需求理解"}, previous=previous)
        self.assertEqual(plan["delta"]["retired"], ["custom-review"])
        self.assertNotEqual(old["fingerprint"], plan["fingerprint"])

    def test_previous_required_capability_is_not_silently_dropped(self):
        old = self.plan({**self.context_data, "required_capabilities": ["量子棋局审查"]})
        previous = self.project / "previous.json"
        self.write(previous, old)
        plan = self.plan({"stage": "需求理解"}, previous=previous)
        self.assertEqual(plan["status"], "unknown")
        self.assertIn("能力需求未满足: 量子棋局审查", plan["unmet"])

    def test_previous_required_risk_survives_phase_change_until_declared_resolved(self):
        old = self.plan({**self.context_data, "required_risks": ["棋局破坏"]})
        previous = self.project / "previous.json"
        self.write(previous, old)
        plan = self.plan({"stage": "需求理解"}, previous=previous)
        self.assertEqual(plan["status"], "unknown")
        self.assertIn("必需风险未覆盖: 棋局破坏", plan["unmet"])
        plan = self.plan({"stage": "需求理解", "resolved_risks": ["棋局破坏"]}, previous=previous)
        self.assertEqual(plan["status"], "planned")
        self.assertTrue(plan["warnings"])

    def test_tampered_previous_rejected(self):
        old = self.plan()
        old["selected"] = []
        previous = self.project / "previous.json"
        self.write(previous, old)
        with self.assertRaises(lib.CapabilityInputError):
            self.plan(previous=previous)

    def test_registry_and_host_scopes_intersect_without_expansion(self):
        plan = self.plan(entries=[{**self.entry, "read_scope": ["source/narrow/**"], "write_scope": []}])
        selected = plan["selected"][0]
        self.assertEqual(selected["read_scope"], ["source/narrow/**"])
        self.assertEqual(selected["write_scope"], [])

    def test_default_catalog_only_relevant_reference_in_daily_state(self):
        self.write(self.context, {"current_stage": "验证证据", "professional_domains": ["代码质量"]})
        proc, plan = self.cli(["--context", str(self.context)])
        self.assertEqual(proc.returncode, 0, plan)
        self.assertEqual([x["id"] for x in plan["selected"]], ["semantic-code-review"])
        self.assertEqual(plan["selected"][0]["source"], "reference")

    def test_default_catalog_verification_without_domain_does_not_load_all(self):
        self.write(self.context, {"stage": "验证"})
        proc, plan = self.cli(["--context", str(self.context)])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(plan["selected"], [])

    def test_project_catalog_precedence(self):
        self.write(self.project / "architecture/index.json", {"专业能力索引": []})
        project_catalog = self.project / "architecture/capabilities/catalog.json"
        self.write(project_catalog, {"version": 1, "entries": [self.entry]})
        proc, plan = self.cli(["--context", str(self.context)])
        self.assertEqual(proc.returncode, 0, plan)
        self.assertEqual(plan["inputs"]["catalog"]["path"], str(project_catalog))

    def test_existing_broken_architecture_directory_is_not_hidden(self):
        (self.project / "architecture").mkdir()
        proc, plan = self.cli(["--context", str(self.context), "--catalog", str(self.catalog)])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(plan["status"], "invalid")

    def test_output_stays_in_project_and_cannot_replace_context(self):
        original = self.context.read_bytes()
        for target in (self.context, self.install / "plan.json"):
            proc, plan = self.cli(["--context", str(self.context), "--catalog", str(self.catalog), "--output", str(target)])
            self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.context.read_bytes(), original)
        self.assertFalse((self.install / "plan.json").exists())

    def test_output_cannot_replace_selected_json_body(self):
        body = self.project / "body.json"
        body.write_text('{"reference":true}', encoding="utf-8")
        self.write(self.catalog, {"version": 1, "entries": [{**self.entry, "root": str(self.project), "entry": "body.json", "refs": []}]})
        proc, result = self.cli(["--context", str(self.context), "--catalog", str(self.catalog), "--output", str(body)])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(body.read_text()), {"reference": True})

    def test_cli_unknown_exit_two_and_valid_output_json(self):
        self.write(self.context, {"stage": "验证", "confirmed_capabilities": ["missing"]})
        proc, plan = self.cli(["--context", str(self.context), "--catalog", str(self.catalog), "--output", str(self.project / "plan.json")])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(plan, json.loads((self.project / "plan.json").read_text(encoding="utf-8")))

    def test_metadata_conversion_does_not_read_bodies(self):
        bad_body = self.install / "SKILL.md"
        bad_body.write_bytes(b"\xff\x00invalid text")
        metadata = [{"name": "custom", "entry": str(bad_body), "capability_type": "自定义领域", "requires": {"professional_domains": ["自定义领域"]}}]
        catalog = lib.catalog_from_metadata(metadata, self.project / "generated.json")
        self.assertEqual(catalog["entries"][0]["能力类型"], "自定义领域")
        self.assertEqual(catalog["entries"][0]["source"], "skill")

    def test_invalid_selected_utf8_is_unknown(self):
        (self.install / "指南.自定义").write_bytes(b"\xff")
        self.assertEqual(self.plan()["status"], "unknown")

    def test_explicit_encoding_supports_legacy_text_without_language_filter(self):
        (self.install / "指南.自定义").write_bytes("旧文本".encode("gb18030"))
        entry = {**self.entry, "encoding": "gb18030", "refs": []}
        self.assertEqual(self.plan(entries=[entry])["status"], "planned")

    def test_arbitrary_custom_context_conditions_and_missing_null_do_not_match(self):
        entry = {**self.entry, "requires": {"context_equals": {"/domain_flags/棋局": None}}}
        self.assertEqual(self.plan(entries=[entry])["selected"], [])
        self.assertEqual(len(self.plan({"domain_flags": {"棋局": None}}, [entry])["selected"]), 1)

    def test_old_example_index_remains_compatible(self):
        data = json.loads((PACKAGE / "shared/assets/example-architecture.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(lib.validate_capability_index(data)[0], [])

    def test_index_bad_fields_and_actual_node_refs_are_rejected(self):
        data = {"功能树": [{"编号": "f真实"}], "验证证据": {}, "专业能力索引": [{"能力类型": "测试", "适用节点": ["接口"],
                 "关联节点": ["f不存在"], "回写位置": ["/验证证据/不存在"], "候选技能": [{"路径": "../escape"}]}]}
        errors, _ = lib.validate_capability_index(data)
        self.assertGreaterEqual(len(errors), 3)
        self.assertTrue(any("引用不存在节点" in x for x in errors))

    def test_index_writeback_and_catalog_permission_intersection(self):
        self.write(self.project / "architecture.json", {"专业能力索引": [{"能力类型": "量子棋局审查", "回写位置": ["验证证据", "完整细节"]}],
                                                        "验证证据": {}, "完整细节": {}})
        selected = self.plan()["selected"][0]
        self.assertEqual(selected["allowed_writeback"], ["/验证证据"])

    def test_catalog_real_node_reference_is_bound_and_missing_node_unknown(self):
        self.write(self.project / "architecture.json", {"专业能力索引": [], "功能树": [{"编号": "f真实"}]})
        self.assertEqual(self.plan(entries=[{**self.entry, "node_ids": ["f不存在"]}])["status"], "unknown")
        plan = self.plan(entries=[{**self.entry, "node_ids": ["f真实"]}])
        self.assertEqual(plan["selected"][0]["node_ids"], ["f真实"])
        self.assertTrue(plan["inputs"]["architecture"])


if __name__ == "__main__":
    unittest.main()
