"""Regression tests for real architecture data-loss and rendering counterexamples."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "shared" / "scripts"))
import _archlib
import diff_architecture as diff
import init_architecture as init
import manage_state
import render_architecture as render


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class Isolated(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def sliced(self, declarations, payloads, inline=None):
        data = dict(inline or {})
        data["架构切片"] = {"启用": True, "切片清单": declarations}
        write(self.root / "architecture.json", {"指向": "architecture/index.json"})
        write(self.root / "architecture/index.json", data)
        for rel, payload in payloads.items():
            write(self.root / rel, payload)
        return self.root / "architecture.json"

    def cli(self, argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return render.main(argv)


class SliceAuthority(Isolated):
    def test_disjoint_module_dictionaries_and_numbered_arrays_all_survive(self):
        contains = ["模块详情", "实现清单", "功能树"]
        path = self.sliced([
            {"路径": "architecture/a.json", "包含": contains},
            {"路径": "architecture/b.json", "包含": contains}], {
            "architecture/a.json": {"模块详情": {"a": {"职责": "A"}},
                                     "实现清单": {"a": {"文件列表": ["A"]}}, "功能树": [{"编号": "f_a"}]},
            "architecture/b.json": {"模块详情": {"b": {"职责": "B"}},
                                     "实现清单": {"b": {"文件列表": ["B"]}}, "功能树": [{"编号": "f_b"}]}},
            {"模块详情": {"stale": {"职责": "obsolete cache"}}})
        data = _archlib.load_architecture_json(path)
        self.assertEqual(set(data["模块详情"]), {"a", "b"})
        self.assertEqual(_archlib.collect_implementation_files(data), {"A", "B"})
        self.assertEqual([node["编号"] for node in data["功能树"]], ["f_a", "f_b"])

    def test_nested_disjoint_dictionary_fields_merge(self):
        path = self.sliced([{"路径": "architecture/a.json"}, {"路径": "architecture/b.json"}], {
            "architecture/a.json": {"模块拓扑": {"节点": [{"编号": "a"}], "依赖图": []}},
            "architecture/b.json": {"模块拓扑": {"节点": [{"编号": "b"}], "依赖图": [{"从": "b", "到": "a"}]}}})
        topology = _archlib.load_architecture_json(path)["模块拓扑"]
        self.assertEqual([node["编号"] for node in topology["节点"]], ["a", "b"])
        self.assertEqual(topology["依赖图"], [{"从": "b", "到": "a"}])

    def test_conflicting_numbered_entity_has_field_diagnostic(self):
        path = self.sliced([{"路径": "architecture/a.json"}, {"路径": "architecture/b.json"}], {
            "architecture/a.json": {"功能树": [{"编号": "same", "名称": "first"}]},
            "architecture/b.json": {"功能树": [{"编号": "same", "名称": "second"}]}})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, r"功能树\[same\].名称"):
            _archlib.load_architecture_json(path)

    def test_conflicting_module_scalar_is_not_silently_last_wins(self):
        path = self.sliced([{"路径": "architecture/a.json"}, {"路径": "architecture/b.json"}], {
            "architecture/a.json": {"模块详情": {"a": {"职责": "first"}}},
            "architecture/b.json": {"模块详情": {"a": {"职责": "second"}}}})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "模块详情.a.职责"):
            _archlib.load_architecture_json(path)

    def test_missing_authoritative_slice_rejects_inline_cache(self):
        path = self.sliced([{"路径": "architecture/missing.json"}], {}, {"模块详情": {"cached": {}}})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "权威架构切片文件不存在"):
            _archlib.load_architecture_json(path)

    def test_external_slice_path_rejected_before_read(self):
        path = self.sliced([{"路径": "../external.json", "包含": ["项目"]}], {})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "项目内的相对路径"):
            _archlib.load_architecture_json(path)

    def test_in_project_slice_outside_architecture_folder_rejected(self):
        path = self.sliced([{"路径": "data/unowned.json"}], {"data/unowned.json": {"项目": {}}})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "必须位于项目 architecture/"):
            _archlib.load_architecture_json(path)

    def test_contains_is_enforced_for_business_fields(self):
        path = self.sliced([{"路径": "architecture/a.json", "包含": ["项目"]}], {
            "architecture/a.json": {"项目": {}, "功能树": [{"编号": "unowned"}]}})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "越出包含范围.*功能树"):
            _archlib.load_architecture_json(path)

    def test_explicit_null_contains_is_not_treated_as_legacy_absent_scope(self):
        path = self.sliced([{"路径": "architecture/a.json", "包含": None}], {
            "architecture/a.json": {"项目": {}}})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "包含必须是字段名称数组"):
            _archlib.load_architecture_json(path)

    def test_slice_cannot_rewrite_routing_metadata(self):
        path = self.sliced([{"路径": "architecture/a.json", "包含": ["架构切片"]}], {
            "architecture/a.json": {"架构切片": {"启用": False}}})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "不得覆盖入口或切片配置"):
            _archlib.load_architecture_json(path)

    def test_contains_declared_but_absent_rejects_cached_fallback(self):
        path = self.sliced([{"路径": "architecture/a.json", "包含": ["功能树"]}], {
            "architecture/a.json": {"切片元信息": {}}}, {"功能树": [{"编号": "stale"}]})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "缺少声明包含字段"):
            _archlib.load_architecture_json(path)

    def test_pointer_loop_is_an_input_error(self):
        write(self.root / "architecture.json", {"指向": "architecture.json"})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "指针循环"):
            _archlib.load_architecture_json(self.root / "architecture.json")

    def test_explicit_project_root_allows_in_root_parent_pointer_but_rejects_escape(self):
        write(self.root / "architecture.json", {"实现清单": {"m": {"文件列表": ["Core"]}}})
        pointer = self.root / "metadata/pointer.json"
        write(pointer, {"指向": "../architecture.json"})
        data = _archlib.load_architecture_json(pointer, project_root=self.root)
        self.assertEqual(_archlib.collect_implementation_files(data), {"Core"})
        write(pointer, {"指向": "../../outside.json"})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "超出项目范围"):
            _archlib.load_architecture_json(pointer, project_root=self.root)

    def test_disabled_slices_do_not_load_corrupt_files(self):
        write(self.root / "architecture.json", {"架构切片": {"启用": False, "切片清单": [{"路径": "missing"}]}})
        self.assertFalse(_archlib.load_architecture_json(self.root / "architecture.json")["架构切片"]["启用"])


class ManifestContract(unittest.TestCase):
    def test_two_fields_merge_string_and_object_paths_without_suffix_assumptions(self):
        data = {"实现清单": {"a": {"文件列表": ["Core", {"路径": "src/a.any"}],
                                    "文件": [{"路径": "src\\b.C"}, "Core"]}}}
        self.assertEqual(_archlib.collect_implementation_files(data), {"Core", "src/a.any", "src/b.C"})

    def test_malformed_explicit_manifest_is_unknown_input_not_empty_manifest(self):
        for data in [{"实现清单": []}, {"实现清单": {"a": []}},
                     {"实现清单": {"a": {"文件列表": "Core"}}},
                     {"实现清单": {"a": {"文件列表": [{"路径": None}]}}}]:
            with self.subTest(data=data), self.assertRaises(_archlib.ArchitectureInputError):
                _archlib.collect_implementation_files(data)


class RenderProtection(Isolated):
    def test_pointer_target_and_slice_destinations_preserve_bytes(self):
        path = self.sliced([{"路径": "architecture/a.json", "包含": ["模块详情"]}], {
            "architecture/a.json": {"模块详情": {"a": {"职责": "A"}}}})
        for destination in [path, self.root / "architecture/index.json", self.root / "architecture/a.json"]:
            with self.subTest(destination=destination):
                before = destination.read_bytes()
                self.assertEqual(self.cli([str(path), "--output", str(destination)]), 2)
                self.assertEqual(destination.read_bytes(), before)

    def test_hardlink_to_slice_cannot_overwrite_original(self):
        path = self.sliced([{"路径": "architecture/a.json"}], {"architecture/a.json": {"模块详情": {}}})
        destination = self.root / "render.md"
        source = self.root / "architecture/a.json"
        os.link(source, destination)
        before = source.read_bytes()
        self.assertEqual(self.cli([str(path), "--output", str(destination)]), 2)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(destination.read_bytes(), before)

    def test_explicit_state_file_cannot_be_overwritten(self):
        write(self.root / "architecture.json", {})
        state = self.root / "state.json"
        write(state, manage_state.create_initial_state("project"))
        before = state.read_bytes()
        self.assertEqual(self.cli([str(self.root / "architecture.json"), "--state-path", str(state), "--output", str(state)]), 2)
        self.assertEqual(state.read_bytes(), before)

    def test_missing_state_location_cannot_be_created_as_view(self):
        write(self.root / "architecture.json", {})
        state = self.root / "state.json"
        self.assertEqual(self.cli([str(self.root / "architecture.json"), "--state-path", str(state), "--output", str(state)]), 2)
        self.assertFalse(state.exists())

    def test_stale_completion_is_recomputed_from_stages_in_all_views(self):
        state = manage_state.create_initial_state("project")
        state["completion"] = {"percentage": 100, "required_completed": 9, "required_total": 9}
        before = json.dumps(state)
        table = render.to_progress_table(state)
        self.assertIn("完成度 0%", table)
        self.assertIn("0/9", table)
        self.assertEqual(render._build_json_payload({}, state, [], [])["进度"]["completion"]["required_completed"], 0)
        self.assertEqual(json.dumps(state), before)

    def test_untrusted_title_and_identifiers_never_become_event_code(self):
        identifier = "m');globalThis.AUDIT=1;//"
        data = {"项目": {"名称": "</title><img src=x onerror=evil()>@DATA@"},
                "模块拓扑": {"节点": [{"编号": identifier, "名称": identifier}], "依赖图": []},
                "功能树": [{"编号": identifier, "名称": identifier}]}
        report = render.render_html_report(data, None, [], [], 60)
        self.assertNotIn("</title><img", report)
        self.assertIn("&lt;/title&gt;&lt;img", report)
        self.assertNotIn("onclick=", report)
        self.assertIn("getAttribute(\"data-module\")", report)
        # Data script preserves values while escaping all HTML opening tags.
        embedded = report.split("const DATA = ", 1)[1].split(";\nfunction esc", 1)[0]
        self.assertEqual(json.loads(embedded)["模块"][0]["编号"], identifier)
        self.assertNotIn("<img", embedded)

    def test_object_data_topology_is_present_in_markdown_and_html_payload(self):
        data = {"数据拓扑": {"用户": {"表名": "users", "字段": [{"名称": "id", "类型": "integer"}]}}}
        table = render.to_data_tables(data)
        self.assertIn("users", table)
        self.assertIn("id integer", table)
        payload = render._build_json_payload(data, None, [], [])
        self.assertEqual(payload["数据实体"][0]["表名"], "users")
        self.assertEqual(payload["数据拓扑"], data["数据拓扑"])


class MigrationPreservation(Isolated):
    def test_migration_archives_exact_bytes_and_preserves_extension_fields(self):
        path = self.root / "architecture.json"
        data = {"项目": {"名称": "legacy", "更新时间": "original"}, "功能树": [],
                "vendor.extension": {"a": [1, 2]}, "__private_extension__": "preserve",
                "架构切片": {"启用": False, "自定义同步元信息": "keep"}}
        before = b"\xef\xbb\xbf" + json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8") + b"\r\n"
        path.write_bytes(before)
        _, _, archive = init.migrate_single_file(path, self.root, False, "2026-10-04T00:00:00+08:00")
        self.assertEqual(archive.read_bytes(), before)
        loaded = _archlib.load_architecture_json(path)
        self.assertEqual(loaded["vendor.extension"], {"a": [1, 2]})
        self.assertEqual(loaded["__private_extension__"], "preserve")
        self.assertEqual(loaded["架构切片"]["自定义同步元信息"], "keep")

    def test_repeated_timestamp_migration_does_not_overwrite_original_archive(self):
        source = self.root / "legacy.json"
        source.write_bytes('{"项目":{"名称":"first"}}\n'.encode("utf-8"))
        _, _, first = init.migrate_single_file(source, self.root, False, "same-time")
        source.write_bytes('{"项目":{"名称":"second"}}\n'.encode("utf-8"))
        _, _, second = init.migrate_single_file(source, self.root, True, "same-time")
        self.assertNotEqual(first, second)
        self.assertEqual(json.loads(first.read_bytes())["项目"]["名称"], "first")
        self.assertEqual(json.loads(second.read_bytes())["项目"]["名称"], "second")


class DiffCompleteness(unittest.TestCase):
    def test_empty_objects_are_visible_when_added_or_removed(self):
        self.assertEqual(diff.diff_architecture({}, {"added": {}})["新增"], ["added"])
        self.assertEqual(diff.diff_architecture({"gone": {}}, {})["删除"], ["gone"])

    def test_punctuation_keys_do_not_collide_with_nested_paths(self):
        old = {"a.b": 1, "a": {"b": 2}, "z[0]": "literal", "z": ["list"]}
        new = {"a.b": 3, "a": {"b": 2}, "z[0]": "new", "z": ["list"]}
        changes = diff.diff_architecture(old, new)["修改"]
        self.assertEqual({entry["路径"] for entry in changes}, {'["a.b"]', '["z[0]"]'})
        self.assertEqual(len(diff.flatten(old)), 4)

    def test_boolean_and_number_have_distinct_json_meaning(self):
        self.assertEqual(len(diff.diff_architecture({"value": True}, {"value": 1})["修改"]), 1)


class CapabilityIdentity(Isolated):
    def test_single_usage_file_is_not_package_and_project_anchor_takes_priority(self):
        (self.root / "AGENT-USAGE.md").write_text("anything", encoding="utf-8")
        self.assertFalse(_archlib.is_capability_package(self.root))
        (self.root / "SKILL.md").write_text("---\nname: xl-ai-language\n---\n", encoding="utf-8")
        for rel in ["shared/scripts/_archlib.py", "shared/assets/schema/architecture.schema.json", "skills/xl-ai-language/LAYER.md"]:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("placeholder", encoding="utf-8")
        self.assertTrue(_archlib.is_capability_package(self.root))
        (self.root / "SKILL.md").write_text("---\nname: xl-ai-language\n---\n", encoding="utf-8")
        self.assertTrue(_archlib.is_capability_package(self.root))
        write(self.root / "architecture.json", {})
        self.assertFalse(_archlib.is_capability_package(self.root))


if __name__ == "__main__":
    unittest.main()
