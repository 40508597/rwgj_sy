"""Forward scenarios: real CLI, independent plans and semantic writeback faults."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "shared/scripts"
sys.path.insert(0, str(SCRIPTS))
import check_capability_usage as checker


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CapabilityUseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.base = self.root / "architecture/capabilities"
        self.base.mkdir(parents=True)
        self.context_path = self.base / "context.json"
        self.write(self.context_path, {"stage": "review", "tier": "minimal", "module_ids": [],
                                      "risks": [], "confirmed_capabilities": ["semantic-code-review"]})
        self.source = self.root / "references/审查说明.md"
        self.source.parent.mkdir()
        self.source.write_text("Read only. Report actual findings; zero findings is allowed.\n", encoding="utf-8")
        self.input = self.root / "src/输入.任意后缀"
        self.input.parent.mkdir()
        self.input.write_text("billing/invoice/pay\n", encoding="utf-8")
        self.before = {"项目": {"名称": "语言无关账单"}, "专业能力索引": [],
                       "功能树": [{"编号": "f_invoice"}], "验证证据": {"手动检查": []}}
        self.arch = copy.deepcopy(self.before)
        self.payload = {"findings": [], "reviewed": ["invoice"], "limitations": ["manual/model review"]}
        self.arch["验证证据"]["手动检查"].append(copy.deepcopy(self.payload))
        self.artifact = self.base / "artifacts/review.json"
        self.write(self.artifact, {"result": self.payload})
        self.plan = {
            "version": 1, "project_root": str(self.root), "planning_only": True, "status": "planned",
            "selected": [{"id": "semantic-code-review", "capability_type": "review", "source": "reference",
                "read_files": [{"path": str(self.source), "sha256": sha(self.source), "bytes": self.source.stat().st_size,
                                "origin": "project", "declared_root": str(self.root)}],
                "reason": ["explicitly requested"], "node_ids": ["f_invoice"],
                "read_scope": ["src/输入.任意后缀"], "write_scope": [], "allowed_writeback": ["/验证证据"]}],
            "unmet": [], "unknown": [], "errors": [], "warnings": [],
            "inputs": {"context": {"path": str(self.context_path), "sha256": sha(self.context_path)}, "catalog": None,
                       "architecture": [], "index_sha256": hashlib.sha256(encode([])).hexdigest()},
            "architecture_snapshot": copy.deepcopy(self.before),
            "architecture_sha256": hashlib.sha256(encode(self.before)).hexdigest(),
        }
        self.sign()
        self.call = {"id": "review-001", "capability_id": "semantic-code-review", "kind": "review", "status": "completed",
            "input_hashes": {"src/输入.任意后缀": sha(self.input)}, "read_files": ["src/输入.任意后缀"], "modified_files": [],
            "outputs": [{"id": "report", "artifact": "architecture/capabilities/artifacts/review.json",
                         "artifact_pointer": "/result", "writeback": "/验证证据/手动检查/0", "sha256": sha(self.artifact)}],
            "review": {"summary": "Reviewed invoice flow. No reproducible defects found.", "limitations": ["not an execution test"]}}
        self.usage = {"schema_version": 1, "plan_fingerprint": self.plan["fingerprint"],
                      "context_sha256": self.plan["inputs"]["context"]["sha256"], "calls": [self.call]}
        self.save()

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def sign(self):
        unsigned = {key: value for key, value in self.plan.items() if key != "fingerprint"}
        self.plan["fingerprint"] = hashlib.sha256(encode(unsigned)).hexdigest()

    def save(self):
        self.write(self.root / "architecture.json", self.arch)
        self.write(self.base / "plan.json", self.plan)
        self.write(self.base / "usage.json", self.usage)

    def run_cli(self):
        process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "check_capability_usage.py"),
                                  str(self.root), "--json"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(process.stderr, "", process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["code"], process.returncode)
        return result

    def require(self, state):
        self.save()
        result = self.run_cli()
        self.assertEqual(result["status"], state, result)
        return result

    def prepare_real_architecture_view(self, layout):
        """Keep the signed before JSON separate from the real loader sidecar."""
        original, current = copy.deepcopy(self.before), copy.deepcopy(self.arch)
        entry = self.root / "architecture.json"
        if layout == "centralized-slice":
            routing = {"启用": True, "切片清单": [
                {"路径": "architecture/evidence.json", "包含": ["验证证据"]}]}
            original["架构切片"] = copy.deepcopy(routing)
            current["架构切片"] = copy.deepcopy(routing)
            physical = copy.deepcopy(current)
            self.write(self.root / "architecture/evidence.json",
                       {"验证证据": physical.pop("验证证据")})
            self.write(entry, physical)
        elif layout == "pointer":
            self.write(self.root / "architecture/index.json", current)
            self.write(entry, {"指向": "architecture/index.json"})
        else:
            self.write(entry, current)
        self.plan["architecture_snapshot"] = original
        self.plan["architecture_sha256"] = hashlib.sha256(encode(original)).hexdigest()
        self.sign()
        self.usage["plan_fingerprint"] = self.plan["fingerprint"]
        self.write(self.base / "plan.json", self.plan)
        self.write(self.base / "usage.json", self.usage)
        plan = checker.read_json(self.base / "plan.json")
        before = plan["architecture_snapshot"]
        after = checker.snapshot_current(self.root, entry, plan)
        self.assertIs(type(before), dict)
        self.assertIsInstance(after, checker._archlib.ArchitectureView)
        self.assertIsNotNone(after.dependency_sources)
        self.assertEqual(checker.canonical(after), checker.canonical(current))
        return before, after

    def test_real_architecture_view_allowed_writeback_keeps_leaf_coverage(self):
        for layout in ("plain", "pointer", "centralized-slice"):
            with self.subTest(layout=layout):
                before, after = self.prepare_real_architecture_view(layout)
                self.assertEqual(checker.differences(before, after), ["/验证证据/手动检查/0"])
                self.assertEqual(checker.differences(after, before), ["/验证证据/手动检查/0"])
                result = self.run_cli()
                self.assertEqual(result["status"], "pass", result)
                snapshot = next(row for row in result["checks"] if row["id"] == "architecture-snapshot")
                self.assertEqual(snapshot["status"], "pass")
                self.assertFalse(any(row["id"] == "writeback-coverage" for row in result["checks"]), result)

    def test_real_architecture_view_outside_writeback_is_still_unknown(self):
        self.arch["项目"]["名称"] = "unreported identity edit"
        for layout in ("plain", "pointer", "centralized-slice"):
            with self.subTest(layout=layout):
                before, after = self.prepare_real_architecture_view(layout)
                self.assertEqual(checker.differences(before, after),
                                 ["/项目/名称", "/验证证据/手动检查/0"])
                result = self.run_cli()
                self.assertEqual(result["status"], "unknown", result)
                guarded = {row["id"]: row for row in result["checks"]
                           if row["id"] in {"architecture-snapshot", "writeback-coverage"}}
                self.assertEqual(set(guarded), {"architecture-snapshot", "writeback-coverage"})
                for row in guarded.values():
                    self.assertEqual(row["status"], "unknown")
                    self.assertEqual(row["paths"], ["/项目/名称"])

    def test_real_architecture_view_does_not_hide_stale_source_evidence(self):
        self.source.write_text("changed source after the plan was signed", encoding="utf-8")
        for layout in ("plain", "pointer", "centralized-slice"):
            with self.subTest(layout=layout):
                self.prepare_real_architecture_view(layout)
                result = self.run_cli()
                self.assertEqual(result["status"], "unknown", result)
                source = next(row for row in result["checks"] if row["id"] == "semantic-code-review:source")
                self.assertEqual(source["status"], "unknown")
                snapshot = next(row for row in result["checks"] if row["id"] == "architecture-snapshot")
                self.assertEqual(snapshot["status"], "pass")

    def test_review_zero_findings_and_nonstandard_language_input_pass(self):
        result = self.require("pass")
        row = next(v for v in result["checks"] if v["id"].endswith(":review"))
        self.assertEqual(row["evidence_kind"], "review")
        self.assertIn("does not prove", row["reason"])

    def test_old_project_without_calls_skips_instead_of_claiming_pass(self):
        for path in self.base.glob("*.json"):
            path.unlink()
        result = self.run_cli()
        self.assertEqual((result["enabled"], result["status"], result["code"]), (False, "skipped", 0))

    def test_index_only_project_uses_conventional_architecture_entry(self):
        index = self.root / "architecture/index.json"
        (self.root / "architecture.json").replace(index)
        self.assertEqual(self.run_cli()["status"], "pass")

    def test_actual_declared_call_without_plan_is_unknown(self):
        for path in self.base.glob("*.json"):
            path.unlink()
        self.arch["专业能力索引"] = [{"能力类型": "审查", "调用状态": "已完成"}]
        self.write(self.root / "architecture.json", self.arch)
        self.assertEqual(self.run_cli()["status"], "unknown")

    def test_selected_but_no_usage_is_unknown(self):
        (self.base / "usage.json").unlink()
        self.assertEqual(self.run_cli()["status"], "unknown")

    def test_changed_source_is_unknown(self):
        self.source.write_text("changed professional instructions", encoding="utf-8")
        self.require("unknown")

    def test_new_context_cannot_reuse_old_usage(self):
        self.write(self.context_path, {"stage": "deploy", "confirmed_capabilities": []})
        self.require("unknown")

    def test_replanned_context_cannot_relabel_old_usage_as_current(self):
        self.plan["inputs"]["context"]["sha256"] = "0" * 64
        self.sign()
        self.require("unknown")

    def test_changed_actual_input_cannot_reuse_review(self):
        self.input.write_text("changed bill calculation", encoding="utf-8")
        self.require("unknown")

    def test_output_missing_and_partial_are_unknown(self):
        self.call["status"] = "partial"
        self.call["outputs"] = []
        self.require("unknown")

    def test_explicit_failed_call_wins_over_missing_artifact(self):
        self.call["status"] = "failed"
        self.artifact.unlink()
        self.require("fail")

    def test_actual_writeback_semantic_field_loss_is_fail(self):
        self.arch["验证证据"]["手动检查"][0].pop("limitations")
        self.require("fail")

    def test_output_finding_id_is_not_a_new_architecture_node(self):
        self.payload["findings"] = [{"编号": "finding-1", "说明": "review finding"}]
        self.arch["验证证据"]["手动检查"][0] = copy.deepcopy(self.payload)
        self.write(self.artifact, {"result": self.payload})
        self.call["outputs"][0]["sha256"] = sha(self.artifact)
        self.require("pass")

    def test_boolean_and_integer_are_not_equivalent_artifacts(self):
        self.payload["accepted"] = True
        self.write(self.artifact, {"result": self.payload})
        self.call["outputs"][0]["sha256"] = sha(self.artifact)
        self.arch["验证证据"]["手动检查"][0]["accepted"] = 1
        self.require("fail")

    def test_missing_writeback_is_fail(self):
        self.arch["验证证据"]["手动检查"] = []
        self.require("fail")

    def test_output_whitespace_and_object_key_order_do_not_change_semantics(self):
        self.write(self.artifact, {"result": {"limitations": ["manual/model review"], "reviewed": ["invoice"], "findings": []}})
        self.call["outputs"][0]["sha256"] = sha(self.artifact)
        self.require("pass")

    def test_scope_prefix_cannot_allow_similarly_named_sibling(self):
        self.plan["selected"][0]["allowed_writeback"] = ["/验证证据/手动检查"]
        self.sign()
        self.usage["plan_fingerprint"] = self.plan["fingerprint"]
        self.call["outputs"][0]["writeback"] = "/验证证据/手动检查扩展/0"
        self.require("fail")

    def test_declared_file_write_without_write_permission_is_fail(self):
        self.call["modified_files"] = ["src/输入.任意后缀"]
        self.require("fail")

    def test_project_read_wildcard_still_cannot_escape_project(self):
        self.plan["selected"][0]["read_scope"] = ["**"]
        self.sign()
        self.usage["plan_fingerprint"] = self.plan["fingerprint"]
        self.require("pass")
        self.call["read_files"] = ["../outside.json"]
        self.require("fail")

    def test_plan_cannot_expand_context_read_permission(self):
        self.write(self.context_path, {"read_scope": ["another/input"], "write_scope": []})
        self.plan["inputs"]["context"]["sha256"] = sha(self.context_path)
        self.sign()
        self.usage.update(plan_fingerprint=self.plan["fingerprint"], context_sha256=sha(self.context_path))
        self.require("fail")

    def test_context_write_permission_does_not_make_readonly_catalog_writable(self):
        catalog = self.base / "catalog.json"
        self.write(catalog, {"version": 1, "entries": [{"id": "semantic-code-review", "write_scope": [],
                   "allowed_writeback": ["/验证证据"], "source": "reference", "root": str(self.root),
                   "entry": "references/审查说明.md"}]})
        self.write(self.context_path, {"write_scope": ["src/"]})
        self.plan["inputs"]["catalog"] = {"path": str(catalog), "sha256": sha(catalog)}
        self.plan["inputs"]["context"]["sha256"] = sha(self.context_path)
        self.plan["selected"][0]["write_scope"] = ["src/"]
        self.sign()
        self.usage.update(plan_fingerprint=self.plan["fingerprint"], context_sha256=sha(self.context_path))
        self.call["modified_files"] = ["src/输入.任意后缀"]
        self.require("fail")

    def test_project_escape_in_declared_modified_file_is_known_fail(self):
        self.call["modified_files"] = ["../outside.json"]
        self.require("fail")

    def test_external_readonly_catalog_is_hash_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "catalog.json"
            self.write(path, {"version": 1, "entries": [{"id": "semantic-code-review", "source": "reference",
                     "root": str(self.root), "entry": "references/审查说明.md", "write_scope": [],
                     "allowed_writeback": ["/验证证据"]}]})
            self.plan["inputs"]["catalog"] = {"path": str(path), "sha256": sha(path)}
            self.sign()
            self.usage["plan_fingerprint"] = self.plan["fingerprint"]
            self.require("pass")
            self.write(path, {"version": 1, "entries": [{"id": "changed"}]})
            self.require("unknown")

    def test_artifact_path_escape_is_known_fail_without_reading_it(self):
        self.call["outputs"][0]["artifact"] = "../outside.json"
        self.require("fail")

    def test_unselected_candidate_cannot_become_used(self):
        self.call["capability_id"] = "not-selected"
        self.require("fail")

    def test_duplicate_call_cannot_cover_missing_other_capability(self):
        self.usage["calls"].append(copy.deepcopy(self.call))
        self.require("fail")

    def test_two_complete_calls_with_distinct_outputs_merge(self):
        second = copy.deepcopy(self.call)
        second["id"] = "review-002"
        second["outputs"][0]["writeback"] = "/验证证据/手动检查/1"
        self.arch["验证证据"]["手动检查"].append(copy.deepcopy(self.payload))
        self.usage["calls"].append(second)
        self.require("pass")

    def test_conflicting_calls_are_not_last_writer_wins(self):
        artifact = self.base / "artifacts/conflicting.json"
        self.write(artifact, {"result": {"findings": ["different conclusion"]}})
        second = copy.deepcopy(self.call)
        second["id"] = "review-002"
        second["outputs"][0].update(artifact="architecture/capabilities/artifacts/conflicting.json", sha256=sha(artifact))
        self.usage["calls"].append(second)
        self.require("fail")

    def test_partial_call_stays_unknown_even_when_another_call_completes(self):
        second = copy.deepcopy(self.call)
        self.call["status"] = "partial"
        second["id"] = "review-002"
        self.usage["calls"].append(second)
        self.require("unknown")

    def test_recovery_after_current_call_completed_retains_plan_binding(self):
        self.call["status"] = "partial"
        self.require("unknown")
        self.call["status"] = "completed"
        self.require("pass")

    def test_json_pointer_escaped_dictionary_keys_are_read_exactly(self):
        self.arch["验证证据"]["手动检查"] = []
        self.arch["验证证据"]["a/b~c"] = self.payload
        self.call["outputs"][0]["writeback"] = "/验证证据/a~1b~0c"
        self.require("pass")

    def test_unreported_change_in_permitted_parent_needs_artifact_coverage(self):
        self.arch["验证证据"]["自动化测试"] = [{"结论": "通过", "来源": "no execution record"}]
        self.require("unknown")

    def test_empty_allow_scope_cannot_allow_root_writeback(self):
        self.call["outputs"][0]["writeback"] = ""
        self.require("fail")

    def test_capability_permission_edit_invalidates_original_plan(self):
        self.arch["专业能力索引"].append({"能力类型": "外部总控"})
        self.require("unknown")

    def test_structural_node_edit_invalidates_original_plan(self):
        self.arch["功能树"][0]["编号"] = "f_replaced"
        self.require("fail")

    def test_duplicate_json_keys_cannot_hide_failed_call(self):
        (self.base / "usage.json").write_text('{"schema_version":1,"schema_version":1,"calls":[]}', encoding="utf-8")
        self.assertEqual(self.run_cli()["status"], "unknown")

    def test_execution_requires_real_matching_current_receipt(self):
        command = [sys.executable, "-B", "-X", "utf8", "-c", "from pathlib import Path; assert Path('src/输入.任意后缀').read_text() == 'billing/invoice/pay\\n'"]
        receipt = "architecture/capabilities/receipt.json"
        process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "run_verification.py"),
            str(self.root), "--output", receipt, "--input", "src/输入.任意后缀", "--", *command], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.call["kind"] = "execution"
        self.call["execution"] = {"receipt": receipt, "command": command}
        self.require("pass")
        self.call["execution"]["command"] = ["different", "argv"]
        self.require("unknown")
        (self.root / receipt).unlink()
        self.require("unknown")

    def test_fake_review_cannot_claim_execution_evidence(self):
        self.call["kind"] = "execution"
        self.require("unknown")


class JsonDifferenceTypesTests(unittest.TestCase):
    def test_dictionary_subclasses_are_json_objects_even_when_nested(self):
        class OtherObject(dict):
            pass
        raw = {"nested": {"array": [{"value": 1}]}}
        view = checker._archlib.ArchitectureView({"nested": checker._archlib.ArchitectureView(
            {"array": [OtherObject({"value": 1})]})})
        view._dependency_sources = {"private": "not a JSON member"}
        self.assertEqual(checker.differences(raw, view), [])
        self.assertEqual(checker.differences(view, raw), [])
        view["nested"]["array"][0]["value"] = 2
        self.assertEqual(checker.differences({"nested": {"array": [{"value": 1}]}}, view),
                         ["/nested/array/0/value"])

    def test_nonobject_types_keep_strict_type_comparison(self):
        class OtherArray(list):
            pass
        for before, after in ((True, 1), (False, 0), (True, 1.0), (1, 1.0),
                              ([], ()), ([1], OtherArray([1])), (None, {}),
                              ({}, []), ("1", 1)):
            with self.subTest(before=type(before).__name__, after=type(after).__name__):
                self.assertEqual(checker.differences({"value": before}, {"value": after}), ["/value"])
                self.assertEqual(checker.differences({"value": after}, {"value": before}), ["/value"])

    def test_object_fields_array_lengths_and_escaped_paths_remain_exact(self):
        before = {"a/b~c": [{"accepted": True}], "removed": {}}
        after = checker._archlib.ArchitectureView({"a/b~c": [{"accepted": 1}, {}], "added": {}})
        self.assertEqual(checker.differences(before, after),
                         ["/a~1b~0c/0/accepted", "/a~1b~0c/1", "/added", "/removed"])


if __name__ == "__main__":
    unittest.main()
