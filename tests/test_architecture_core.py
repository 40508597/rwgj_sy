"""Shared declared relations and local-feature composition, without code claims."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "shared/scripts"))
import _architecture_core as core
import _architecture_visual as visual
import _archlib
import _module_tree as modules
import _toolchain_query as query
import check_placeholders
import check_quality_redlines
import module_architecture
import render_architecture
import validate_agent_output
import validate_architecture


def write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def doc(key):
    return {"模块路由": {"版本": 1, "编号": key, "名称": key, "职责": "负责" + key, "子模块": []},
            "模块详情": {key: {"职责": "负责" + key, "上游依赖": [], "下游消费者": []}},
            "实现清单": {key: {"文件列表": [], "依赖模块": []}}}


class SharedRulesTests(unittest.TestCase):
    def test_fields_and_meaningful_have_one_implementation(self):
        self.assertEqual(len(core.FALLBACK_MODULE_DETAIL_SUBFIELDS), 14)
        self.assertEqual(len(core.FALLBACK_REQUIRED_TOP_KEYS), 21)
        self.assertIs(validate_architecture.derive_module_detail_subfields, core.derive_module_detail_subfields)
        self.assertIs(check_placeholders.resolve_module_detail_subfields, core.derive_module_detail_subfields)
        self.assertIs(validate_agent_output.meaningful, core.meaningful)
        for value in (None, False, 3, [], {}, [" ", {"x": []}]):
            self.assertFalse(core.meaningful(value))
        self.assertTrue(core.meaningful({"未验证项": ["缺少运行环境"]}))
        schema = {"properties": {"模块详情": {"x-required-subfields": ["职责", "边界"]}}}
        self.assertEqual(core.derive_module_detail_subfields(schema), ["职责", "边界"])
        self.assertEqual(core.derive_module_detail_subfields(None), core.FALLBACK_MODULE_DETAIL_SUBFIELDS)

    def test_schema_fallback_is_explicit_and_invalid_json_never_silently_loaded(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "schema.json"
            schema, warning = core.load_schema(path)
            self.assertIsNone(schema)
            self.assertTrue(warning)
            path.write_text('{"properties":{},"properties":{}}', encoding="utf-8")
            schema, warning = core.load_schema(path)
            self.assertIsNone(schema)
            self.assertIn("重复 JSON 键", warning)
            path.write_text('{"x":1e999}', encoding="utf-8")
            schema, warning = core.load_schema(path)
            self.assertIsNone(schema)
            self.assertIn("非有限值", warning)

    def test_explicit_module_identifier_overrides_mapping_label_in_every_view(self):
        data = {"模块拓扑": {"节点": [{"编号": "a"}, {"编号": "b"}]},
                "模块详情": {"显示名称甲": {"模块编号": "a", "上游依赖": ["b"]},
                               "显示名称乙": {"模块编号": "b"}},
                "实现清单": {"显示名称甲": {"模块编号": "a", "依赖模块": ["b"]}}}
        self.assertEqual([(e["从"], e["到"]) for e in core.declared_dependencies(data)["edges"]], [("a", "b")])
        self.assertEqual([(e["从"], e["到"]) for e in render_architecture._edges_of(data)], [("a", "b")])
        model = visual.build_visual_model(data)
        self.assertEqual(sum(e["kind"] == "依赖" for e in model["relations"]), 1)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            write(root, "architecture.json", data)
            index = query.build_index(root)
            edges = [e for e in index["relationships"] if e["type"] == "dependency"]
            self.assertEqual([(e["source"], e["target"]) for e in edges], [("module:a", "module:b")])
            self.assertTrue(any("显示名称甲" in loc["pointer"] for loc in edges[0]["locations"]))

    def test_sources_directions_dedup_and_descriptive_references(self):
        data = {"模块拓扑": {"依赖图": [{"从": "a", "到": "b", "条件": "保留原值"}]},
                "实现清单": {"a": {"依赖模块": ["b"]}},
                "模块详情": {"a": {"上游依赖": [{"模块编号": "b"}], "下游消费者": ["c"]},
                               "b": {"上游依赖": [{"说明": "外部进程，不是登记模块"}]}}}
        original = copy.deepcopy(data)
        result = core.declared_dependencies(data, "src/a/architecture.json")
        self.assertEqual(data, original)
        self.assertEqual([(e["从"], e["到"]) for e in result["edges"]], [("a", "b"), ("c", "a")])
        self.assertEqual(len(result["edges"][0]["sources"]), 3)
        for edge in result["edges"]:
            for loc in edge["sources"]:
                value = data
                for part in loc["pointer"].split("/")[1:]:
                    part = part.replace("~1", "/").replace("~0", "~")
                    value = value[int(part)] if isinstance(value, list) else value[part]
                self.assertEqual(value, loc["value"])
                self.assertEqual(loc["file"], "src/a/architecture.json")
        self.assertEqual([d["code"] for d in result["diagnostics"]], ["descriptive_reference"])

    def test_malformed_and_conflicting_reference_not_certified(self):
        result = core.declared_dependencies({"模块详情": {"a": {"上游依赖": [
            {"模块编号": "b", "编号": "c"}, {}, False]}}})
        self.assertEqual(result["edges"], [])
        self.assertEqual(len(result["diagnostics"]), 3)
        tree = modules.ModuleTree(Path.cwd(), Path.cwd() / "architecture.json")
        tree.merged = {"实现清单": {"a": {"依赖模块": "b"}}}
        with self.assertRaises(_archlib.ArchitectureInputError):
            modules.dependency_edges(tree)


class RecursiveDeclarationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "architecture.json"

    def fixture(self):
        root, a, b = doc("root"), doc("a"), doc("b")
        root["模块路由"]["子模块"] = [{"编号": key, "路径": key + "/architecture.json", "职责": "负责" + key}
                                    for key in ("a", "b")]
        # No topology/manifest duplicate: detail alone must be visible everywhere.
        a["模块详情"]["a"]["上游依赖"] = [{"模块编号": "b", "说明": "唯一依赖声明"}]
        for file, value in (("architecture.json", root), ("a/architecture.json", a), ("b/architecture.json", b)):
            write(self.root, file, value)
        return root, a, b

    def test_impact_markdown_html_query_share_detail_only_graph_and_sources(self):
        root, _, _ = self.fixture()
        tree = modules.build_module_tree(root, self.path)
        self.assertEqual(modules.dependency_edges(tree), [("a", "b")])
        impact = module_architecture.impact(tree, module_id="b")
        self.assertEqual(impact["依赖关系"]["受影响消费者"], ["a"])
        origin = impact["依赖关系"]["边"][0]["sources"][0]
        self.assertEqual((origin["file"], origin["pointer"]), ("a/architecture.json", "/模块详情/a/上游依赖/0"))
        self.assertEqual([(e["从"], e["到"]) for e in render_architecture._edges_of(tree.merged)], [("a", "b")])
        self.assertIn("| a | b |", render_architecture.to_dependency_flow(tree.merged))
        model = visual.build_visual_model(tree.merged)
        ids = {nid: key for key, nid in model["entities"].items()}
        self.assertEqual({(ids[e["a"]], ids[e["b"]]) for e in model["relations"] if e["kind"] == "依赖"}, {("a", "b")})
        index = query.build_index(self.root)
        dependencies = [e for e in index["relationships"] if e["type"] == "dependency"]
        self.assertEqual([(e["source"], e["target"]) for e in dependencies], [("module:a", "module:b")])
        self.assertEqual(dependencies[0]["locations"][0]["file"], "a/architecture.json")
        self.assertNotIn(("root", "a"), modules.dependency_edges(tree))
        self.assertEqual(module_architecture.check(tree)["status"], "pass")

    def test_origin_sidecar_is_json_equivalent_and_survives_copy_without_index_drift(self):
        root, a, _ = self.fixture()
        root["模块拓扑"] = {"依赖图": [{"从": "root", "到": "a"}]}
        a["模块拓扑"] = {"依赖图": [{"从": "a", "到": "b", "类型": "只读校验"}]}
        write(self.root, "a/architecture.json", a)
        tree = modules.build_module_tree(root, self.path)
        view = tree.merged
        # dict(JSON) drops only the metadata attribute, never business fields.
        encoded = json.dumps(view, ensure_ascii=False, sort_keys=True)
        self.assertEqual(encoded, json.dumps(dict(view), ensure_ascii=False, sort_keys=True))
        self.assertEqual(encoded, json.dumps(copy.deepcopy(view), ensure_ascii=False, sort_keys=True))
        edge = next(e for e in core.declared_dependencies(view)["edges"] if e["从"] == "a")
        origin = next(loc for loc in edge["sources"] if loc["pointer"].startswith("/模块拓扑"))
        self.assertEqual((origin["file"], origin["pointer"], origin["view_pointer"]),
                         ("a/architecture.json", "/模块拓扑/依赖图/0", "/模块拓扑/依赖图/1"))
        self.assertNotIn("value", origin, "sidecar must not duplicate entire business records")
        self.assertEqual(len(origin["sha256"]), 64)
        modified = view.dependency_sources
        modified["edges"].clear()
        self.assertEqual(len(core.declared_dependencies(view)["edges"]), 2)
        model = visual.build_visual_model(view)
        readonly = next(e for e in model["relations"] if e["kind"] == "只读校验")
        self.assertIn("/模块拓扑/依赖图/1", readonly["sources"])
        self.assertEqual(readonly["declarations"][0]["file"], "a/architecture.json")
        self.assertEqual(readonly["declarations"][0]["pointer"], "/模块拓扑/依赖图/0")
        self.assertIn("a/architecture.json#/模块拓扑/依赖图/0", render_architecture.to_dependency_flow(view))
        edited = copy.deepcopy(view)
        edited["模块详情"]["a"]["上游依赖"] = ["new-provider"]
        self.assertIsNone(edited.dependency_sources, "stale metadata cannot be a second truth source")
        self.assertIn(("a", "new-provider"), {(e["从"], e["到"]) for e in core.declared_dependencies(edited)["edges"]})

    def test_recursive_root_slices_preserve_physical_dependency_origins(self):
        root, a, b = self.fixture()
        # The root's old graph is replaced, not mixed with authoritative slices.
        root["模块拓扑"] = {"依赖图": [{"从": "root", "到": "missing"}]}
        root["架构切片"] = {"启用": True, "切片清单": [
            {"路径": "architecture/topology-1.json", "包含": ["模块拓扑"]},
            {"路径": "architecture/topology-2.json", "包含": ["模块拓扑"]}]}
        first = {"模块拓扑": {"依赖图": [
            {"编号": "root-a", "从": "root", "到": "a"},
            {"从": "root", "到": "b", "类型": "只读校验"}]}}
        second = {"模块拓扑": {"依赖图": [
            {"编号": "root-a", "说明": "多切片补充说明"},
            {"从": "root", "到": "b", "类型": "只读校验"}]}}
        write(self.root, "architecture.json", root)
        write(self.root, "architecture/topology-1.json", first)
        write(self.root, "architecture/topology-2.json", second)
        tree, sources = module_architecture.load_tree(self.path)
        self.assertEqual(module_architecture.check(tree, sources)["status"], "pass")
        declarations = modules.dependency_declarations(tree)
        self.assertEqual({(e["从"], e["到"]) for e in declarations["edges"]},
                         {("root", "a"), ("root", "b"), ("a", "b")})
        for edge in declarations["edges"]:
            for loc in edge["sources"]:
                physical = self.root / loc["file"]
                actual = json.loads(physical.read_text(encoding="utf-8"))
                for part in loc["pointer"].split("/")[1:]:
                    key = part.replace("~1", "/").replace("~0", "~")
                    actual = actual[int(key)] if isinstance(actual, list) else actual[key]
                self.assertEqual(actual, loc["value"], "origin value must be the physical fragment, not a merged copy")
                self.assertEqual(hashlib.sha256(physical.read_bytes()).hexdigest(), loc["sha256"])
        root_a = next(e for e in declarations["edges"] if (e["从"], e["到"]) == ("root", "a"))
        self.assertEqual({loc["file"] for loc in root_a["sources"]},
                         {"architecture/topology-1.json", "architecture/topology-2.json"})
        self.assertTrue(all(loc["pointer"] == "/模块拓扑/依赖图/0" for loc in root_a["sources"]))
        loaded = _archlib.load_architecture_json(self.path)
        self.assertEqual(core.declared_dependencies(loaded), core.declared_dependencies(tree.merged))
        index = query.build_index(self.root)
        self.assertFalse(index["diagnostics"], index["diagnostics"])
        root_a_query = next(e for e in index["relationships"]
                            if e["type"] == "dependency" and e["source"] == "module:root"
                            and e["target"] == "module:a")
        self.assertEqual({loc["file"] for loc in root_a_query["locations"]},
                         {"architecture/topology-1.json", "architecture/topology-2.json"})
        self.assertEqual(json.dumps(loaded, ensure_ascii=False, sort_keys=True),
                         json.dumps(dict(loaded), ensure_ascii=False, sort_keys=True))

    def test_hydrated_origin_values_reject_changed_physical_source(self):
        root, a, b = self.fixture()
        root["架构切片"] = {"启用": True, "切片清单": [
            {"路径": "architecture/topology.json", "包含": ["模块拓扑"]}]}
        slice_data = {"模块拓扑": {"依赖图": [{"从": "root", "到": "a"}]}}
        write(self.root, "architecture.json", root)
        write(self.root, "architecture/topology.json", slice_data)
        tree, _ = module_architecture.load_tree(self.path)
        # The published in-memory view stays an immutable observed snapshot;
        # asking the collector for new physical raw fragments must not mix it
        # with different file contents under the old SHA.
        slice_data["模块拓扑"]["依赖图"][0]["到"] = "b"
        write(self.root, "architecture/topology.json", slice_data)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "来源内容已变化"):
            modules.dependency_declarations(tree)

    def test_slice_list_merge_escaped_pointers_and_diagnostics_have_real_sources(self):
        # Centralized display keys remain compatible even when identity and
        # reference fragments are independently merged from separate slices.
        name = "显示/名~甲"
        base = {"架构切片": {"启用": True, "切片清单": [
            {"路径": "architecture/one.json", "包含": ["模块详情"]},
            {"路径": "architecture/two.json", "包含": ["模块详情"]}]}}
        first = {"模块详情": {name: {"模块编号": "a", "上游依赖": ["b"]}}}
        second = {"模块详情": {name: {"上游依赖": ["c", "b", {"模块编号": "b", "编号": "c"}]}}}
        write(self.root, "architecture.json", base)
        write(self.root, "architecture/one.json", first)
        write(self.root, "architecture/two.json", second)
        view = _archlib.load_architecture_json(self.path)
        origins = core.declared_dependencies(view)
        edge = next(e for e in origins["edges"] if e["到"] == "b")
        self.assertEqual(edge["从"], "a")
        self.assertEqual({loc["file"] for loc in edge["sources"]},
                         {"architecture/one.json", "architecture/two.json"})
        escaped = "/模块详情/显示~1名~0甲/上游依赖/"
        c = next(e for e in origins["edges"] if e["到"] == "c")["sources"][0]
        self.assertEqual((c["file"], c["pointer"], c["view_pointer"]),
                         ("architecture/two.json", escaped + "0", escaped + "1"))
        diagnostic = origins["diagnostics"][0]
        self.assertEqual((diagnostic["code"], diagnostic["file"], diagnostic["pointer"]),
                         ("conflicting_reference", "architecture/two.json", escaped + "2"))
        self.assertEqual(len(diagnostic["sha256"]), 64)
        self.assertNotIn("value", diagnostic)
        edited = copy.deepcopy(view)
        edited["模块详情"][name]["上游依赖"].append("new")
        self.assertIsNone(edited.dependency_sources)
        self.assertIn("new", {e["到"] for e in core.declared_dependencies(edited)["edges"]})

    def test_detail_only_cycle_and_unknown_module_cannot_escape_check(self):
        root, a, b = self.fixture()
        b["模块详情"]["b"]["上游依赖"] = ["a"]
        write(self.root, "b/architecture.json", b)
        result = module_architecture.check(modules.build_module_tree(root, self.path))
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("有向环" in error for error in result["errors"]))
        b["模块详情"]["b"]["上游依赖"] = ["missing"]
        write(self.root, "b/architecture.json", b)
        result = module_architecture.check(modules.build_module_tree(root, self.path))
        self.assertTrue(any("missing" in error for error in result["errors"]))

    def test_route_derives_empty_tree_but_preserves_explicit_logical_group(self):
        root, _, _ = self.fixture()
        root["模块树"] = []
        tree = modules.build_module_tree(root, self.path)
        self.assertEqual([child["编号"] for child in tree.merged["模块树"][0]["子模块"]], ["a", "b"])
        logical = [{"编号": "root", "逻辑分组": "业务视图", "扩展": {"保持": True}, "子模块": []}]
        root["模块树"] = copy.deepcopy(logical)
        self.assertEqual(modules.build_module_tree(root, self.path).merged["模块树"], logical)

    def test_deep_feature_fragments_inherit_physical_owner_at_every_recursive_level(self):
        root, a, b = self.fixture()
        root["功能树"] = [{"编号": "project", "名称": "全局功能", "子节点": [
            {"编号": "domain", "名称": "公共领域导航", "子节点": []}]}]
        a["功能树"] = [{"编号": "project", "子节点": [
            {"编号": "domain", "子节点": [
                {"编号": "work", "名称": "模块行为", "子节点": [
                    {"编号": "validate", "名称": "深层校验", "子功能": [
                        {"编号": "reject", "名称": "拒绝非法输入", "子行为": [
                            {"编号": "keep", "名称": "保持旧状态", "子节点": []}]}]}]}]}]}]
        for file, value in (("architecture.json", root), ("a/architecture.json", a), ("b/architecture.json", b)):
            write(self.root, file, value)
        index = query.build_index(self.root)
        self.assertEqual(query.read_object(index, "behavior:project")["module"], "root")
        self.assertEqual(query.read_object(index, "behavior:domain")["module"], "root")
        for key in ("work", "validate", "reject", "keep"):
            feature = query.read_object(index, "behavior:" + key)
            self.assertEqual(feature["module"], "a")
            self.assertTrue(all(loc["file"] == "a/architecture.json" for loc in feature["locations"]))
            # Each locator addresses the original nested record, not a synthetic index.
            for loc in feature["locations"]:
                value = a
                for part in loc["pointer"].split("/")[1:]:
                    value = value[int(part)] if isinstance(value, list) else value[part]
                self.assertEqual(value["编号"], key)
        self.assertFalse(any(d["code"] == "multiple_owners" for d in index["diagnostics"]))
        edges = {(e["source"], e["target"]) for e in index["relationships"] if e["type"] == "contains"}
        self.assertIn(("behavior:reject", "behavior:keep"), edges)
        self.assertIn(("module:a", "behavior:keep"), edges)
        self.assertNotIn(("module:a", "behavior:domain"), edges)

    def test_example_local_descent_preserves_fields_and_provenance_and_rejects_conflict(self):
        example = PACKAGE / "shared/assets/examples/recursive-local-features"
        shutil.copytree(example, self.root, dirs_exist_ok=True)
        before = _archlib.load_architecture_json(self.path)
        self.assertEqual(validate_architecture.validate_architecture(before, self.root)[0], [])
        self.assertEqual(check_placeholders.categorize_placeholders(before, check_placeholders.load_schema())["critical"], [])
        self.assertEqual(check_quality_redlines.check_redlines(before)[0], [])
        self.assertEqual(len(before["功能树"][0]["子节点"]), 2)
        index = query.build_index(self.root)
        feature = query.read_object(index, "behavior:f_validate")
        self.assertEqual(feature["module"], "rules")
        self.assertEqual(feature["locations"][0]["file"], "modules/orders/rules/architecture.json")
        self.assertFalse(any(d["code"] == "multiple_owners" for d in index["diagnostics"]))
        self.assertIn("共 3 个功能节点", render_architecture.to_function_tree(before))
        # Consolidate then descend exactly the same branch, preserving every field.
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        child_path = self.root / "modules/orders/rules/architecture.json"
        child = json.loads(child_path.read_text(encoding="utf-8"))
        raw["功能树"] = copy.deepcopy(before["功能树"])
        child["功能树"] = []
        write(self.root, "architecture.json", raw)
        write(self.root, "modules/orders/rules/architecture.json", child)
        self.assertEqual(_archlib.load_architecture_json(self.path)["功能树"], before["功能树"])
        raw["功能树"][0]["子节点"] = [n for n in raw["功能树"][0]["子节点"] if n["编号"] != "f_validate"]
        child["功能树"] = [{"编号": "f_shop", "子节点": [copy.deepcopy(before["功能树"][0]["子节点"][1])]}]
        write(self.root, "architecture.json", raw)
        write(self.root, "modules/orders/rules/architecture.json", child)
        self.assertEqual(_archlib.load_architecture_json(self.path)["功能树"], before["功能树"])
        child["功能树"][0]["名称"] = "与根矛盾的名称"
        write(self.root, "modules/orders/rules/architecture.json", child)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "冲突"):
            _archlib.load_architecture_json(self.path)


if __name__ == "__main__":
    unittest.main()
