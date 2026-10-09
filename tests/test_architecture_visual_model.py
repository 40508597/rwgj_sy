"""Independent contracts for a lossless project canvas and explicit relations."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import _archlib
from _architecture_core import ArchitectureView
from _architecture_visual import build_visual_model


def escape(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def values_by_pointer(value, pointer=""):
    result = {pointer: value}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(values_by_pointer(child, pointer + "/" + escape(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.update(values_by_pointer(child, pointer + "/" + str(index)))
    return result


def original_value(model, nid):
    node = model["nodes"][nid]
    if node["t"] == "object":
        return {model["nodes"][child]["k"]: original_value(model, child)
                for child in node["raw_c"]}
    if node["t"] == "array":
        return [original_value(model, child) for child in node["raw_c"]]
    return node["v"]


class VisualModelContracts(unittest.TestCase):
    def assert_fully_reachable(self, model):
        visited = set()
        stack = [0]
        while stack:
            nid = stack.pop()
            self.assertNotIn(nid, visited, "reading hierarchy must have one acyclic position per node")
            visited.add(nid)
            for child in model["nodes"][nid]["c"]:
                self.assertEqual(model["nodes"][child]["parent"], nid)
                stack.append(child)
        self.assertEqual(visited, set(range(len(model["nodes"]))))
        for node in model["nodes"]:
            self.assertIs(type(node["restore_safe"]), bool)
            if node["restore_safe"]:
                self.assertNotIn("restore_guard", node)
            else:
                self.assertIsInstance(node["restore_guard"], str)
                self.assertEqual(len(node["restore_guard"]), 64)
                self.assertFalse(set(node["restore_guard"]) - set("0123456789abcdef"))

    def assert_source_values(self, source, model):
        expected = values_by_pointer(source)
        raw_nodes = model["nodes"][:model["source_node_count"]]
        actual = {node["p"]: i for i, node in enumerate(raw_nodes)}
        self.assertEqual(set(actual), set(expected))
        self.assertEqual(len(actual), len(raw_nodes))
        for pointer, value in expected.items():
            recovered = original_value(model, actual[pointer])
            self.assertEqual(recovered, value, pointer)
            # A loader sidecar is a JSON object, not a serialized Python class.
            # Scalars and ordinary containers keep the original exact types.
            expected_type = dict if isinstance(value, ArchitectureView) else type(value)
            self.assertIs(type(recovered), expected_type, pointer)
            if isinstance(value, (dict, list)) and not value:
                self.assertTrue(raw_nodes[actual[pointer]]["empty"], pointer)
            elif not isinstance(value, (dict, list)):
                self.assertIs(type(raw_nodes[actual[pointer]]["v"]), type(value), pointer)
        leaves = sum(not isinstance(v, (dict, list)) or not v for v in expected.values())
        self.assertEqual(model["leaf_count"], leaves)
        self.assertEqual(model["top_count"], len(source))
        self.assert_fully_reachable(model)

    def test_empty_and_arbitrary_language_objects_need_no_architecture_fields(self):
        fixtures = [
            {},
            {"Rust/C++": {"enabled": False, "zero": 0, "empty": "", "nullable": None,
                          "schema~value": [], "对象": {}, "float": 1.0},
             "C#": ["程序.vendor-binary", "模块.e", "library.rs", True, None, []]},
            {"项目": "a project without a name object", "extra": [{"deep": {"more": {"still": []}}}]},
        ]
        for source in fixtures:
            with self.subTest(source=source):
                before = copy.deepcopy(source)
                model = build_visual_model(source)
                self.assert_source_values(source, model)
                self.assertEqual(source, before)
                self.assertEqual(model["relations"], [])
                self.assertEqual(model["physical_leaf_count"], 0)
                json.dumps(model, ensure_ascii=False)

    def test_deep_content_remains_exhaustive_without_a_render_depth_cutoff(self):
        source = {"leaf": "final value"}
        for _ in range(100):
            source = {"level": source}
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        self.assertEqual(model["leaf_count"], 1)

    def test_optional_and_unstructured_business_fields_remain_content(self):
        source = {"模块详情": [], "模块树": "not an enumerable tree", "功能树": ["text record", {}],
                  "接口契约": [{"提供方": None, "参数": []}], "数据拓扑": False,
                  "验证证据": [None, 0, {}, []]}
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        self.assertNotIn("0", model["entities"], "an array position is not a declared interface ID")
        self.assertEqual(model["relations"], [])

    def relation_fixture(self):
        return {
            "项目": {"名称": "通用接口架构", "语言": "Rust / C++ / C# / 中文DSL"},
            "模块详情": {
                "A": {"职责": "负责A", "非职责": [], "上游依赖": ["B", "B-name", "B*"],
                      "下游消费者": ["C"], "所属功能树节点": ["f"],
                      "未知扩展": {"空值": None}},
                "B": {"模块名": "B-name", "职责": "负责B"},
                "C": {"职责": "负责C"},
            },
            "模块树": [{"编号": "g", "名称": "明确分组", "模块": ["A", "B", "missing"]}],
            "模块拓扑": {"节点": [{"编号": "A", "名称": "模块A"}, {"编号": "B"}],
                         "依赖图": [{"从": "A", "到": "B", "说明": "正式依赖"}]},
            "功能树": [{"编号": "f", "名称": "功能F", "父节点": None,
                       "架构落位": {"模块": ["A"]}, "验收标准": ["criterion"]}],
            "接口契约": {"I": {"提供方": "B", "消费方": ["A"], "参数": []}},
            "数据拓扑": {"record": {"编号": "D", "字段": [], "读写责任模块": ["A", "B*"]}},
            "实现清单": {"A": {"文件列表": ["src/engine.rs", "模块.e"]}},
            "测试责任矩阵": [{"模块": "A", "单元测试": "需要"}],
        }

    def test_exact_relations_include_incoming_consumers_without_name_guessing(self):
        source = self.relation_fixture()
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        ids = model["entities"]
        actual = {(edge["a"], edge["b"], edge["kind"]) for edge in model["relations"]}
        self.assertIn((ids["A"], ids["B"], "依赖"), actual)
        self.assertIn((ids["C"], ids["A"], "依赖"), actual)
        self.assertIn((ids["A"], ids["f"], "实现功能"), actual)
        self.assertIn((ids["B"], ids["I"], "提供接口"), actual)
        self.assertIn((ids["I"], ids["A"], "消费方"), actual)
        self.assertIn((ids["D"], ids["A"], "读写责任（未拆方向）"), actual)
        dependency = next(e for e in model["relations"] if (e["a"], e["b"], e["kind"]) == (ids["A"], ids["B"], "依赖"))
        self.assertEqual(set(dependency["sources"]), {"/模块拓扑/依赖图/0", "/模块详情/A/上游依赖/0"})
        unresolved = {d.get("identifier") for d in model["diagnostics"] if d["code"] == "unresolved_reference"}
        self.assertTrue({"B-name", "B*", "missing"}.issubset(unresolved))
        for edge in model["relations"]:
            for pointer in edge["sources"]:
                self.assertIn(pointer, values_by_pointer(source))

    def test_module_and_function_facets_keep_all_original_specs(self):
        source = self.relation_fixture()
        model = build_visual_model(source)
        module = model["nodes"][model["entities"]["A"]]
        facet_names = {model["nodes"][nid]["label"] for nid in module["c"]}
        self.assertTrue({"职责与边界", "功能与依赖", "专项规格"}.issubset(facet_names))
        feature = model["nodes"][model["entities"]["f"]]
        self.assertIn("功能规格与验收", {model["nodes"][nid]["label"] for nid in feature["c"]})
        self.assert_source_values(source, model)

    def test_nested_module_tree_declares_containment_without_implying_dependency(self):
        source = {"模块树": [{"编号": "parent", "名称": "父模块", "子模块": [
            {"编号": "child", "名称": "子模块", "子模块": ["parent"]}]}]}
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        parent, child = model["entities"]["parent"], model["entities"]["child"]
        actual = {(edge["a"], edge["b"], edge["kind"]) for edge in model["relations"]}
        self.assertEqual(actual, {(parent, child, "模块归属"), (child, parent, "模块归属")})

    def test_duplicate_and_ambiguous_ids_are_not_resolved_by_last_writer(self):
        source = {
            "模块拓扑": {"节点": [{"编号": "A", "名称": "one"}, {"编号": "A", "名称": "two"}, {"编号": "B"}],
                         "依赖图": [{"从": "A", "到": "B"}]},
            "模块详情": {"A": {"职责": "detail cannot disambiguate the duplicate topology"}},
            "功能树": [{"编号": "f", "父节点": None}, {"编号": "f", "父节点": "f"}],
            "完整备注": "A",
        }
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        self.assertNotIn("A", model["entities"])
        self.assertNotIn("f", model["entities"])
        self.assertFalse(any(e["kind"] == "依赖" for e in model["relations"]))
        self.assertTrue(any(d["code"] == "ambiguous_id" for d in model["diagnostics"]))
        self.assertFalse(any(model["nodes"][a]["v"] == "A" for a, _ in model["references"]))

    def test_function_cycles_and_multiple_parents_keep_records_reachable(self):
        source = {"功能树": [
            {"编号": "a", "父节点": "b", "验收标准": []},
            {"编号": "b", "父节点": "a", "子节点": ["c"]},
            {"编号": "c", "父节点": "a", "异常路径": ["retain"]},
        ]}
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        codes = {d["code"] for d in model["diagnostics"]}
        self.assertIn("function_parent_cycle", codes)
        self.assertIn("multiple_function_parents", codes)
        self.assertEqual(sum(e["kind"] == "功能分解" for e in model["relations"]), 4)

    def test_explicit_root_and_child_declarations_cannot_silently_choose_a_parent(self):
        source = {"功能树": [{"编号": "a", "父节点": None, "子节点": ["b"]},
                            {"编号": "b", "父节点": None}]}
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        a, b = model["entities"]["a"], model["entities"]["b"]
        self.assertNotEqual(model["nodes"][b]["parent"], a)
        self.assertTrue(any(d["code"] == "function_parent_conflict" for d in model["diagnostics"]))
        self.assertTrue(any(e["a"] == a and e["b"] == b and e["kind"] == "功能分解" for e in model["relations"]))

    def test_cross_role_identity_collisions_do_not_generate_generic_content_links(self):
        source = {"模块详情": {"shared": {"职责": "module"}},
                  "功能树": [{"编号": "shared", "名称": "feature", "架构落位": {"模块": ["shared"]}}],
                  "普通备注": "shared"}
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        self.assertNotIn("shared", model["entities"])
        self.assertEqual(model["references"], [])
        self.assertEqual(sum(e["kind"] == "实现功能" for e in model["relations"]), 1,
                         "an explicitly typed module reference remains resolvable")
        duplicate_module = {"模块拓扑": {"节点": [{"编号": "shared"}, {"编号": "shared"}]},
                            "功能树": [{"编号": "shared"}], "普通备注": "shared"}
        duplicate_model = build_visual_model(duplicate_module)
        self.assertNotIn("shared", duplicate_model["entities"])
        self.assertEqual(duplicate_model["references"], [])

    def test_numeric_ids_are_not_boolean_or_string_aliases(self):
        source = {"模块拓扑": {"节点": [{"编号": 0}, {"编号": 7}], "依赖图": [
            {"从": 0, "到": 7}, {"从": "0", "到": 7}, {"从": False, "到": 7}]}}
        model = build_visual_model(source)
        self.assert_source_values(source, model)
        self.assertEqual(sum(e["kind"] == "依赖" for e in model["relations"]), 1)
        self.assertEqual(model["nodes"][model["entities"]["0"]]["entity"], "0")

    def test_numbered_changes_and_evidence_restore_to_the_same_record_after_reordering(self):
        source = self.relation_fixture()
        source.update({"变更记录": [{"编号": "a", "说明": "Alpha"}, {"编号": "b", "说明": "Beta"}],
                       "验证证据": [{"ID": "a", "输出": "first evidence"},
                                  {"ID": "b", "输出": "second evidence"}]})
        before = copy.deepcopy(source)
        first = build_visual_model(source)
        source["变更记录"].reverse()
        source["验证证据"].reverse()
        source["变更记录"][1]["说明"] = "Alpha revised"
        second = build_visual_model(source)
        for collection, text_field in (("变更记录", "说明"), ("验证证据", "输出")):
            with self.subTest(collection=collection):
                original = next(n for n in first["nodes"] if n["p"] == "/" + collection + "/0")
                relocated = next(n for n in second["nodes"] if n.get("reading_key") == original["reading_key"])
                self.assertEqual(relocated["p"], "/" + collection + "/1")
                self.assertEqual(original["record_key"], relocated["record_key"])
                self.assertTrue(relocated["restore_safe"])
                self.assertNotIn("restore_guard", relocated,
                                 "a stable explicit ID must not depend on unchanged record content")
                field = next(n for n in first["nodes"] if n["p"] == original["p"] + "/" + text_field)
                moved_field = next(n for n in second["nodes"] if n.get("reading_key") == field["reading_key"])
                self.assertEqual(moved_field["v"], source[collection][1][text_field],
                                 "an edited record body must not change its explicit-ID reading key")
                self.assertTrue(moved_field["restore_safe"])
                self.assertIsNone(relocated["entity"], "reading identity must not become a semantic entity")
        self.assertEqual(first["relations"], second["relations"])
        self.assertEqual(first["entities"], second["entities"])
        self.assert_source_values(before, first)
        self.assert_source_values(source, second)

    def test_nested_record_keys_follow_original_collections_and_preserve_canonical_keys(self):
        source = {"模块详情": {"A": {"职责": "boundary", "规格": [
            {"id": "outer-a", "列表": [{"ID": 7, "内容": "nested-a"}]},
            {"id": "outer-b", "列表": [{"ID": 7, "内容": "nested-b"}]},
        ]}}}
        first = build_visual_model(source)
        source["模块详情"]["A"]["规格"].reverse()
        second = build_visual_model(source)
        first_nodes = {n["p"]: n for n in first["nodes"] if n["p"] is not None}
        self.assertEqual(first_nodes["/模块详情/A"]["reading_key"], "entity:A")
        self.assertEqual(first_nodes["/模块详情/A/职责"]["reading_key"], "field:A/职责")
        self.assertNotEqual(first_nodes["/模块详情/A/规格/0/列表/0"]["record_key"],
                            first_nodes["/模块详情/A/规格/1/列表/0"]["record_key"])
        original = first_nodes["/模块详情/A/规格/0/列表/0/内容"]
        relocated = next(n for n in second["nodes"] if n.get("reading_key") == original["reading_key"])
        self.assertEqual(relocated["p"], "/模块详情/A/规格/1/列表/0/内容")
        self.assertEqual(relocated["v"], "nested-a")
        self.assertTrue(relocated["restore_safe"])
        self.assertEqual(second["relations"], [])
        self.assert_source_values(source, second)

    def test_reading_ids_are_scoped_typed_and_do_not_disambiguate_duplicate_records(self):
        source = {"one": [{"编号": 7}, {"编号": "7"}], "two": [{"编号": 7}],
                  "duplicates": [{"编号": "same", "名称": "first"},
                                 {"编号": "same", "名称": "second"}],
                  "anonymous": [{"名称": "a name is not an ID"}, {"id": False}, {"ID": ""}],
                  "fallback": [{"编号": "duplicate", "id": "a"}, {"编号": "duplicate", "id": "b"}],
                  "功能树": [{"编号": "f", "说明": "one"}, {"编号": "f", "说明": "two"}]}
        before = copy.deepcopy(source)
        model = build_visual_model(source)
        nodes = {n["p"]: n for n in model["nodes"] if n["p"] is not None}
        keys = [nodes[p]["record_key"] for p in ("/one/0", "/one/1", "/two/0")]
        self.assertEqual(len(set(keys)), 3, "collection scope and ID type both affect identity")
        for prefix in ("/duplicates/", "/anonymous/"):
            for pointer, node in nodes.items():
                if pointer.startswith(prefix):
                    self.assertFalse(node["restore_safe"], pointer)
                    self.assertNotIn("record_key", node, pointer)
        for pointer in ("/fallback/0", "/fallback/1"):
            self.assertTrue(nodes[pointer]["restore_safe"])
            self.assertIn("/@id:string:", nodes[pointer]["record_key"])
        for node in model["nodes"]:
            if node["role"] == "属性面":
                self.assertFalse(node["restore_safe"], "facets of ambiguous records cannot restore safely")
        self.assertEqual(model["entities"], {})
        self.assertEqual(model["relations"], [])
        self.assertEqual(model["references"], [])
        self.assertEqual(source, before)
        self.assert_source_values(source, model)

    def test_unidentified_nested_arrays_never_inherit_a_safe_record_identity(self):
        source = {"records": [{"编号": "safe", "步骤": ["one", {"说明": "two"}]},
                              {"名称": "unsafe", "嵌套": [{"id": "locally-unique", "说明": "three"}]}]}
        model = build_visual_model(source)
        nodes = {n["p"]: n for n in model["nodes"] if n["p"] is not None}
        self.assertTrue(nodes["/records/0"]["restore_safe"])
        self.assertTrue(nodes["/records/0/步骤"]["restore_safe"])
        for pointer, node in nodes.items():
            if pointer.startswith("/records/0/步骤/") or pointer.startswith("/records/1"):
                self.assertFalse(node["restore_safe"], pointer)
        self.assert_source_values(source, model)

    def test_function_cycles_and_multiple_parents_do_not_change_raw_reading_identifiers(self):
        source = {"功能树": [{"编号": "a", "父节点": "b", "子节点": ["c"], "说明": "a-spec"},
                             {"编号": "b", "父节点": "a", "子节点": ["c"], "说明": "b-spec"},
                             {"编号": "c", "父节点": "a", "说明": "c-spec"}]}
        first = build_visual_model(source)
        source["功能树"].reverse()
        second = build_visual_model(source)
        for identifier in ("a", "b", "c"):
            first_node = first["nodes"][first["entities"][identifier]]
            second_node = second["nodes"][second["entities"][identifier]]
            self.assertEqual(first_node["reading_key"], "entity:" + identifier)
            self.assertEqual(second_node["reading_key"], first_node["reading_key"])
            for model, node in ((first, first_node), (second, second_node)):
                field = next(n for n in model["nodes"] if n["p"] == node["p"] + "/说明")
                self.assertEqual(field["reading_key"], "field:" + identifier + "/说明")
                self.assertTrue(field["restore_safe"])
        for model in (first, second):
            self.assertTrue({"function_parent_cycle", "multiple_function_parents"}.issubset(
                {d["code"] for d in model["diagnostics"]}))
            self.assertEqual(sum(e["kind"] == "功能分解" for e in model["relations"]), 4)
        self.assert_source_values(source, second)

    def test_anonymous_record_guard_survives_unrelated_changes_but_not_record_edits_or_reordering(self):
        source = {"records": [{"说明": "Alpha", "nested": {"flag": True, "count": 1}},
                              {"说明": "Beta", "nested": {"flag": False, "count": 2}}],
                  "unrelated": "before"}
        before = copy.deepcopy(source)
        first = build_visual_model(source)
        source["unrelated"] = "after"
        source["records"][0] = {"nested": {"count": 1, "flag": True}, "说明": "Alpha"}
        unrelated = build_visual_model(source)
        source["records"][0]["说明"] = "Alpha revised"
        edited = build_visual_model(source)
        reordered_source = copy.deepcopy(before)
        reordered_source["records"].reverse()
        reordered = build_visual_model(reordered_source)
        indexes = [{n["p"]: n for n in model["nodes"] if n["p"] is not None}
                   for model in (first, unrelated, edited, reordered)]
        original, unchanged, changed, moved = indexes
        for pointer, node in original.items():
            if pointer == "/records/0" or pointer.startswith("/records/0/"):
                self.assertFalse(node["restore_safe"])
                self.assertEqual(len(node["restore_guard"]), 64)
                self.assertEqual(node["restore_guard"], original["/records/0"]["restore_guard"])
                self.assertEqual(node["restore_guard"], unchanged[pointer]["restore_guard"],
                                 "unrelated edits and object member ordering must not invalidate content")
                self.assertNotEqual(node["restore_guard"], changed[pointer]["restore_guard"])
                self.assertNotEqual(node["restore_guard"], moved[pointer]["restore_guard"])
        self.assertEqual(source["records"][1], before["records"][1])
        self.assert_source_values(before, first)
        self.assert_source_values(source, edited)
        self.assert_source_values(reordered_source, reordered)

    def test_nested_guard_includes_unstable_outer_record_even_for_locally_numbered_children(self):
        source = {"outer": [{"label": "Alpha", "items": [{"id": "same", "说明": "shared"}]},
                            {"label": "Beta", "items": [{"id": "same", "说明": "shared"}]}]}
        original = build_visual_model(source)
        changed = copy.deepcopy(source)
        changed["outer"][0]["label"] = "changed outside the selected inner record"
        edited = build_visual_model(changed)
        source["outer"].reverse()
        reordered = build_visual_model(source)
        first = {n["p"]: n for n in original["nodes"] if n["p"] is not None}
        second = {n["p"]: n for n in edited["nodes"] if n["p"] is not None}
        third = {n["p"]: n for n in reordered["nodes"] if n["p"] is not None}
        pointer = "/outer/0/items/0"
        self.assertFalse(first[pointer]["restore_safe"])
        self.assertNotEqual(first[pointer]["restore_guard"], first["/outer/1/items/0"]["restore_guard"],
                            "equal inner content does not erase different unstable outer context")
        self.assertNotEqual(first[pointer]["restore_guard"], second[pointer]["restore_guard"])
        self.assertNotEqual(first[pointer]["restore_guard"], third[pointer]["restore_guard"])
        self.assertEqual(first[pointer]["restore_guard"], first[pointer + "/说明"]["restore_guard"])
        self.assert_source_values(changed, edited)
        self.assert_source_values(source, reordered)

    def test_duplicate_ids_and_json_types_are_content_guards_without_becoming_stable_identities(self):
        source = {"duplicates": [{"编号": "same", "输出": value} for value in (1, True, 1.0, None, "1")]}
        first = build_visual_model(source)
        original = {n["p"]: n for n in first["nodes"] if n["p"] is not None}
        guards = []
        for index in range(5):
            node = original["/duplicates/" + str(index)]
            self.assertFalse(node["restore_safe"])
            self.assertNotIn("record_key", node)
            guards.append(node["restore_guard"])
        self.assertEqual(len(set(guards)), 5, "integer, boolean, float, null and string content stay distinct")
        source["duplicates"][0], source["duplicates"][1] = source["duplicates"][1], source["duplicates"][0]
        second = build_visual_model(source)
        changed = next(n for n in second["nodes"] if n["p"] == "/duplicates/0")
        self.assertNotEqual(guards[0], changed["restore_guard"])
        self.assertEqual(second["relations"], [])
        self.assertEqual(second["entities"], {})
        self.assert_source_values(source, second)
        ambiguous = build_visual_model({"功能树": [{"编号": "duplicate", "说明": "first"},
                                                {"编号": "duplicate", "说明": "second"}]})
        for node in ambiguous["nodes"]:
            if node["role"] == "属性面":
                parent = ambiguous["nodes"][node["parent"]]
                self.assertFalse(node["restore_safe"])
                self.assertEqual(node["restore_guard"], parent["restore_guard"])

    def test_physical_supplemental_record_guards_survive_path_moves_and_unrelated_content_changes(self):
        source = {"business": "unchanged"}
        physical = [{"path": "C:/old/architecture/log.json", "data": {
            "log": [{"message": "Alpha"}, {"message": "Beta"}], "unrelated": 1}}]
        before = copy.deepcopy(physical)
        first = build_visual_model(source, physical)
        physical[0]["path"] = "D:/moved/architecture/log.json"
        physical[0]["data"]["unrelated"] = 2
        unrelated = build_visual_model(source, physical)
        physical[0]["data"]["log"].reverse()
        reordered = build_visual_model(source, physical)
        pointer = "/@源文件/0/原文件补充字段/log/0"
        nodes = [next(n for n in model["nodes"] if n["p"] == pointer)
                 for model in (first, unrelated, reordered)]
        self.assertTrue(all(n["restore_safe"] is False for n in nodes))
        self.assertTrue(all("reading_key" not in n for n in nodes))
        self.assertEqual(nodes[0]["restore_guard"], nodes[1]["restore_guard"])
        self.assertNotEqual(nodes[0]["restore_guard"], nodes[2]["restore_guard"])
        self.assertEqual(first["physical_leaf_count"], unrelated["physical_leaf_count"])
        self.assertEqual(first["physical_leaf_count"], reordered["physical_leaf_count"])
        self.assertEqual(before[0]["data"]["log"][0]["message"], "Alpha")
        self.assert_source_values(source, reordered)

    def test_physical_pointer_slice_metadata_and_partial_merges_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "architecture").mkdir()
            pointer = {"指向": "architecture/index.json", "说明": "root pointer annotation"}
            index = {"项目": {"名称": "来源完整"}, "架构切片": {"启用": True, "切片清单": [
                {"路径": "architecture/a.json", "包含": ["扩展"]},
                {"路径": "architecture/b.json", "包含": ["扩展"]},
            ]}}
            a = {"切片元信息": {"编号": "slice-a", "empty": {}}, "扩展": [{"编号": "x", "a": 1}]}
            b = {"切片元信息": {"编号": "slice-b"}, "扩展": [{"编号": "y", "b": False}]}
            for relative, value in (("architecture.json", pointer), ("architecture/index.json", index),
                                    ("architecture/a.json", a), ("architecture/b.json", b)):
                (root / relative).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            paths = set()
            hydrated = _archlib.load_architecture_json(root / "architecture.json", paths)
            self.assertIsInstance(hydrated, ArchitectureView)
            self.assertEqual(json.dumps(hydrated, ensure_ascii=False, sort_keys=True),
                             json.dumps(dict(hydrated), ensure_ascii=False, sort_keys=True))
            sources = [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "data": json.loads(path.read_text(encoding="utf-8"))} for path in sorted(paths)]
            before_data, before_sources = copy.deepcopy(hydrated), copy.deepcopy(sources)
            model = build_visual_model(hydrated, sources)
            self.assert_source_values(hydrated, model)
            expected = {(record["path"], p): value for record in sources
                        for p, value in values_by_pointer(record["data"]).items()
                        if not isinstance(value, (dict, list)) or not value}
            actual = {(m["source"], m["pointer"]): m for m in model["physical_mappings"]}
            self.assertEqual(set(actual), set(expected))
            self.assertEqual(model["physical_leaf_count"], len(expected))
            for key, value in expected.items():
                mapping = actual[key]
                self.assertEqual(model["nodes"][mapping["node"]]["p"], mapping["visual_pointer"])
                recovered = original_value(model, mapping["node"])
                self.assertEqual(recovered, value)
                self.assertIs(type(recovered), type(value))
            self.assertTrue(any(m["pointer"].startswith("/切片元信息") for m in actual.values()))
            self.assertTrue(any(m["pointer"] == "/指向" for m in actual.values()))
            self.assertTrue(any(m["pointer"] == "/扩展/0/b" and m["visual_pointer"].startswith("/@源文件/") for m in actual.values()))
            self.assertEqual(hydrated, before_data)
            self.assertEqual(sources, before_sources)
            model["sources"][0]["path"] = "modified view"
            self.assertEqual(sources, before_sources)

    def test_physical_values_keep_boolean_number_types_and_empty_roots(self):
        source = {"value": True, "empty": {}, "array": []}
        physical = [{"path": "numbers.json", "sha256": "observed", "data": {"value": 1}},
                    {"path": "empty.json", "data": {}},
                    {"path": "null.json", "data": None},
                    {"path": "metadata-only.json"}]
        model = build_visual_model(source, physical)
        self.assert_source_values(source, model)
        self.assertEqual(model["physical_leaf_count"], 3)
        mapping = next(m for m in model["physical_mappings"] if m["source"] == "numbers.json")
        self.assertTrue(mapping["visual_pointer"].startswith("/@源文件/"))
        self.assertIs(type(model["nodes"][mapping["node"]]["v"]), int)
        self.assertTrue(any(d["code"] == "source_data_unavailable" for d in model["diagnostics"]))
        self.assertNotIn("value", model["field_sources"])

    def test_source_namespace_cannot_overwrite_an_actual_business_field(self):
        source = {"@源文件": [{"原文件补充字段": {"foo": "business"}}]}
        model = build_visual_model(source, [{"path": "pointer.json", "data": {"指向": "index.json"}}])
        self.assert_source_values(source, model)
        self.assertEqual(model["source_namespace"], "@源文件-1")
        self.assertTrue(model["physical_mappings"][0]["visual_pointer"].startswith("/@源文件-1/"))

    def test_invalid_non_json_values_fail_without_mutating_inputs(self):
        for source in (["not object"], {"bad": float("nan")}, {1: "not a JSON key"}):
            with self.subTest(source=source):
                with self.assertRaises(_archlib.ArchitectureInputError):
                    build_visual_model(source)
        cyclic = {}
        cyclic["cycle"] = cyclic
        with self.assertRaises(_archlib.ArchitectureInputError):
            build_visual_model(cyclic)
        self.assertIs(cyclic["cycle"], cyclic)


if __name__ == "__main__":
    unittest.main()
