"""Real-file navigation, provenance, unknowns and context regressions."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared/scripts"))
import _archlib
import _toolchain_query as query


def write(root, file, value):
    path = root / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def module(key, files=()):
    return {"模块路由": {"版本": 1, "编号": key, "名称": key, "职责": "负责" + key, "子模块": []},
            "模块详情": {key: {"职责": "负责" + key, "非职责": ["保留真实边界"],
                                 "上游依赖": [], "下游消费者": []}},
            "实现清单": {key: {"文件列表": list(files), "依赖模块": []}}}


class QueryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def source(self, file, content=b"opaque language independent source"):
        path = self.root / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def recursive(self):
        root = module("root", ["main.任意语言"])
        worker = module("worker", ["领域/worker/code.unknown", "领域/worker/测试.case"])
        database = module("db", ["存储/data.any"])
        leaf = module("leaf", ["领域/worker/内层/leaf.any"])
        root["项目"] = {"名称": "递归真实文件", "约束": ["语言不受限"]}
        root["质量规则"] = [{"编号": "r", "说明": "保留全局约束"}]
        root["模块路由"]["子模块"] = [
            {"编号": "worker", "路径": "领域/worker/architecture.json", "职责": worker["模块路由"]["职责"]},
            {"编号": "db", "路径": "存储/architecture.json", "职责": database["模块路由"]["职责"]}]
        worker["模块路由"]["子模块"] = [
            {"编号": "leaf", "路径": "内层/architecture.json", "职责": leaf["模块路由"]["职责"]}]
        worker["模块详情"]["worker"]["上游依赖"] = [{"模块编号": "db", "说明": "显式依赖"}]
        worker["实现清单"]["worker"]["依赖模块"] = ["db"]
        worker["自定义约束"] = {"必须": ["不可删除此原始事实"]}
        worker["功能树"] = [{"编号": "work", "名称": "执行任务", "父节点": None,
                                 "子节点": [{"编号": "work.child", "名称": "校验输入", "子节点": []}],
                                 "验收标准": ["原始输入保真"],
                                 "架构落位": {"模块": ["worker"], "接口": ["process"], "数据": ["jobs"],
                                              "文件": ["领域/worker/code.unknown"], "测试": ["领域/worker/测试.case"]}}]
        worker["接口契约"] = {"worker": {"导出": [{"名称": "process", "签名": "opaque signature", "消费者": ["root"]}]}}
        database["接口契约"] = {"db": {"导出": [{"编号": "database-read", "名称": "read", "签名": "native signature"}]}}
        worker["数据拓扑"] = [{"编号": "jobs", "名称": "任务实体", "读取模块": ["worker"], "写入模块": ["db"]}]
        worker["测试责任矩阵"] = [{"编号": "test-work", "模块": "worker", "行为": ["work"], "契约": ["process"],
                                      "测试": "领域/worker/测试.case::业务用例", "断言": ["失败不能污染状态"]}]
        worker["架构决策"] = [{"编号": "adr-1", "标题": "保持不透明源码", "选项": ["保留", "猜测"], "结论": "保留"}]
        write(self.root, "architecture.json", root)
        write(self.root, "领域/worker/architecture.json", worker)
        write(self.root, "领域/worker/内层/architecture.json", leaf)
        write(self.root, "存储/architecture.json", database)
        for file in ("main.任意语言", "领域/worker/code.unknown", "领域/worker/测试.case", "领域/worker/内层/leaf.any", "存储/data.any"):
            self.source(file)
        return root, worker, database, leaf

    def index(self):
        return query.build_index(self.root)

    def test_defensive_builder_reports_declared_and_physical_owner_conflicts(self):
        root, worker, database, leaf = self.recursive()
        valid = _archlib.load_architecture_json(self.root / "architecture.json")
        root["实现清单"]["root"]["模块编号"] = "worker"
        # The public loader must reject it first; the builder also defends its
        # own input when an already-hydrated or injected document is changed.
        write(self.root, "architecture.json", root)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "模块归属不一致"):
            self.index()
        docs = {"architecture.json": root, "领域/worker/architecture.json": worker,
                "存储/architecture.json": database, "领域/worker/内层/architecture.json": leaf}
        hashes = {file: hashlib.sha256((self.root / file).read_bytes()).hexdigest() for file in docs}
        index = query._Builder(self.root, "architecture.json", docs, hashes, dict(valid)).build()
        ownership = next(item for item in index["files"] if item["path"] == "main.任意语言")
        self.assertEqual((ownership["module"], ownership["physical_owner"], ownership["ownership"]),
                         ("worker", "root", True))
        diagnostics = {d["code"]: d for d in index["diagnostics"]}
        self.assertIn("module_identity_mismatch", diagnostics)
        self.assertIn("physical_owner_mismatch", diagnostics)
        notice = diagnostics["physical_owner_mismatch"]
        self.assertEqual((notice["declared_owner"], notice["physical_owner"]), ("worker", "root"))

    def test_stable_ids_are_injective_urlencoded_and_validate_inputs(self):
        self.assertEqual(query.object_id("module", "域/a:b%"), "module:%E5%9F%9F%2Fa%3Ab%25")
        self.assertNotEqual(query.object_id("module", "a/b"), query.object_id("module", "a%2Fb"))
        for kind, key in (("mystery", "x"), ("module", ""), ("module", None)):
            with self.assertRaises(_archlib.ArchitectureInputError):
                query.object_id(kind, key)

    def test_all_six_kinds_and_actual_language_independent_files(self):
        self.recursive()
        index = self.index()
        self.assertEqual({obj["kind"] for obj in index["objects"]}, query.KINDS)
        self.assertTrue(all(item["exists"] for item in index["files"]))
        self.assertIn("领域/worker/code.unknown", {item["path"] for item in index["files"]})
        self.assertEqual(query.read_object(index, "worker")["module"], "worker")
        self.assertEqual(query.read_object(index, "contract:worker%3A%3Aprocess")["value"]["签名"], "opaque signature")

    def test_every_provenance_pointer_addresses_actual_raw_declaration(self):
        self.recursive()
        index = self.index()
        for obj in index["objects"]:
            for declaration in obj["declarations"]:
                loc = declaration["location"]
                raw = (self.root / loc["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), loc["sha256"])
                value = json.loads(raw)
                for part in loc["pointer"].split("/")[1:]:
                    part = part.replace("~1", "/").replace("~0", "~")
                    value = value[int(part)] if isinstance(value, list) else value[part]
                expected = declaration["value"]
                if declaration["role"] == "扩展事实":
                    expected = next(iter(expected.values()))
                self.assertEqual(value, expected, (obj["id"], loc))
        self.assertEqual(query.read_object(index, "behavior:work.child")["locations"][0]["pointer"], "/功能树/0/子节点/0")

    def test_containment_never_invents_a_dependency(self):
        self.recursive()
        index = self.index()
        edges = {(edge["type"], edge["source"], edge["target"]) for edge in index["relationships"]}
        self.assertIn(("contains", "module:root", "module:worker"), edges)
        self.assertIn(("contains", "module:worker", "module:leaf"), edges)
        self.assertNotIn(("dependency", "module:root", "module:worker"), edges)
        self.assertIn(("dependency", "module:worker", "module:db"), edges)

    def test_context_preserves_constraints_contracts_tests_and_current_versions(self):
        self.recursive()
        index = self.index()
        context = query.context(index, "worker")
        self.assertEqual([obj["key"] for obj in context["ancestors"]], ["root"])
        self.assertIn("module:leaf", context["scope"])
        self.assertTrue(any(fact["field"] == "质量规则" for fact in context["global_constraints"]))
        self.assertEqual(query.read_object(index, "worker")["value"]["扩展事实"]["自定义约束"]["必须"], ["不可删除此原始事实"])
        self.assertIn("contract:database-read", {obj["id"] for obj in context["contracts"]})
        self.assertEqual({item["path"] for item in context["test_paths"]}, {"领域/worker/测试.case"})
        self.assertEqual(context["input_versions"]["领域/worker/code.unknown"], hashlib.sha256((self.root / "领域/worker/code.unknown").read_bytes()).hexdigest())
        self.assertTrue(context["complete"])
        self.assertFalse(context["truncated"])
        self.source("领域/worker/code.unknown", b"new opaque bytes")
        changed = query.context(self.index(), "worker")
        self.assertNotEqual(context["input_versions"]["领域/worker/code.unknown"], changed["input_versions"]["领域/worker/code.unknown"])

    def test_unknown_and_ambiguous_references_are_reported_never_guessed(self):
        _, worker, database, _ = self.recursive()
        worker["模块详情"]["worker"]["上游依赖"].append({"模块编号": "not-declared"})
        worker["功能树"][0]["架构落位"]["接口"] += ["unavailable"]
        database["接口契约"]["db"]["导出"].append({"名称": "process", "签名": "other provider"})
        write(self.root, "领域/worker/architecture.json", worker)
        write(self.root, "存储/architecture.json", database)
        index = self.index()
        codes = {(item["code"], item.get("reference")) for item in index["diagnostics"]}
        self.assertIn(("unknown_reference", "not-declared"), codes)
        self.assertIn(("unknown_reference", "unavailable"), codes)
        self.assertIn(("ambiguous_reference", "process"), codes)
        self.assertFalse(any(edge["target"] == "module:not-declared" for edge in index["relationships"]))

    def test_search_pagination_returns_total_and_never_silently_caps(self):
        data = {"功能树": [{"编号": "f" + str(i), "名称": "matching"} for i in range(83)]}
        write(self.root, "architecture.json", data)
        index = self.index()
        first = query.search(index, "matching", "behavior")
        self.assertEqual((len(first["items"]), first["total"], first["has_more"]), (50, 83, True))
        second = query.search(index, "matching", "behavior", 50, 50)
        self.assertEqual((len(second["items"]), second["total"], second["has_more"]), (33, 83, False))
        self.assertEqual(len(query.search(index, "", limit=1000)["items"]), 83)
        self.assertFalse(first["semantic_proof"])
        for offset, limit in ((-1, 4), (0, -1), (False, 3), (0, "3")):
            with self.assertRaises(_archlib.ArchitectureInputError):
                query.search(index, "", offset=offset, limit=limit)

    def test_expand_paginates_only_declared_containment(self):
        self.recursive()
        index = self.index()
        expanded = query.expand(index, "root", limit=1)
        self.assertEqual(expanded["total"], 2)
        self.assertEqual(len(expanded["items"]), 1)
        self.assertTrue(expanded["has_more"])
        self.assertEqual({edge["type"] for edge in expanded["relationships"]}, {"contains"})
        child = query.expand(index, "worker", limit=1000)
        self.assertIn("module:leaf", {obj["id"] for obj in child["items"]})
        self.assertNotIn("module:db", {obj["id"] for obj in child["items"]})

    def test_all_query_helpers_are_read_only_and_return_detached_values(self):
        self.recursive()
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        index = self.index()
        original = copy.deepcopy(index)
        query.search(index, "")
        query.expand(index, "worker")
        query.context(index, "worker")
        result = query.read_object(index, "worker")
        result["value"]["模块路由"]["职责"] = "external mutation"
        self.assertEqual(index, original)
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root / "architecture/toolchain").exists())

    def test_selector_does_not_use_labels_or_guess_nonmodule_keys(self):
        self.recursive()
        index = self.index()
        for selector in ("执行任务", "work", "missing", ""):
            with self.assertRaises(_archlib.ArchitectureInputError):
                query.read_object(index, selector)
        self.assertEqual(query.read_object(index, "behavior:work")["key"], "work")

    def test_pointer_derived_identity_is_explicitly_unstable(self):
        data = {"模块详情": {"m": {}}, "测试责任矩阵": [{"模块": "m", "场景": "未编号用例"}]}
        write(self.root, "architecture.json", data)
        first = self.index()
        obj = next(obj for obj in first["objects"] if obj["kind"] == "test")
        self.assertFalse(obj["identity_stable"])
        self.assertEqual(obj["identity_source"], "physical_pointer")
        self.assertIn("unstable_identity", {item["code"] for item in first["diagnostics"]})
        data["测试责任矩阵"].insert(0, {"编号": "inserted", "模块": "m"})
        write(self.root, "architecture.json", data)
        second = next(obj for obj in self.index()["objects"] if obj["kind"] == "test" and not obj["identity_stable"])
        self.assertNotEqual(obj["id"], second["id"])

    def test_explicit_and_export_identities_survive_reorder_and_module_path_move(self):
        _, worker, _, _ = self.recursive()
        first = self.index()
        worker["功能树"].reverse()
        worker["接口契约"]["worker"]["导出"].insert(0, {"名称": "new", "签名": "extra"})
        write(self.root, "领域/worker/architecture.json", worker)
        second = self.index()
        for oid in ("behavior:work", "behavior:work.child", "contract:worker%3A%3Aprocess"):
            self.assertEqual(query.read_object(first, oid)["id"], query.read_object(second, oid)["id"])
        # A centralized file relocation does not change explicit IDs either.
        data = {"功能树": [{"编号": "behavior", "名称": "同一对象"}]}
        write(self.root, "架构/records.json", data)
        write(self.root, "架构/entry.json", {"指向": "records.json"})
        relocated = query.build_index(self.root, "架构/entry.json")
        self.assertEqual(query.read_object(relocated, "behavior:behavior")["key"], "behavior")
        self.assertEqual(query.read_object(relocated, "behavior:behavior")["locations"][0]["file"], "架构/records.json")

    def test_slices_index_only_authoritative_active_declarations(self):
        index = {"功能树": [{"编号": "stale", "名称": "过期内联数据"}],
                 "架构切片": {"启用": True, "切片清单": [
                     {"路径": "architecture/features/a.json", "包含": ["功能树"]},
                     {"路径": "architecture/features/b.json", "包含": ["功能树"]}]}}
        write(self.root, "architecture.json", {"指向": "architecture/index.json"})
        write(self.root, "architecture/index.json", index)
        write(self.root, "architecture/features/a.json", {"切片元信息": {"编号": "slice"},
                                                           "功能树": [{"编号": "active", "名称": "当前", "说明": "一份"}]})
        write(self.root, "architecture/features/b.json", {"功能树": [{"编号": "active", "名称": "当前", "验收标准": ["兼容合并"]}]})
        result = self.index()
        self.assertEqual({obj["id"] for obj in result["objects"]}, {"behavior:active"})
        obj = query.read_object(result, "behavior:active")
        self.assertEqual({loc["file"] for loc in obj["locations"]}, {"architecture/features/a.json", "architecture/features/b.json"})
        self.assertEqual(obj["value"]["说明"], "一份")
        self.assertEqual(obj["value"]["验收标准"], ["兼容合并"])
        self.assertEqual(len(result["input_hashes"]), 4)

    def test_pointer_parent_reference_inside_project_is_supported(self):
        write(self.root, "architecture/entry.json", {"指向": "../facts.json"})
        write(self.root, "facts.json", {"功能树": [{"编号": "f"}]})
        result = query.build_index(self.root, "architecture/entry.json")
        self.assertEqual(result["input_hashes"].keys(), {"architecture/entry.json", "facts.json"})
        self.assertEqual(query.read_object(result, "behavior:f")["locations"][0]["file"], "facts.json")

    def test_duplicate_keys_nonfinite_and_bad_roots_rejected(self):
        for raw in ('{"功能树":[],"功能树":[]}', '{"项目":{"x":NaN}}', '{"项目":{"x":1e999}}', '[]'):
            (self.root / "architecture.json").write_text(raw, encoding="utf-8")
            with self.assertRaises(_archlib.ArchitectureInputError):
                self.index()

    def test_conflicting_explicit_objects_are_not_silently_overwritten(self):
        write(self.root, "architecture.json", {"功能树": [{"编号": "f", "名称": "first"}, {"编号": "f", "名称": "other"}]})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "冲突"):
            self.index()

    def test_invalid_paths_diagnosed_and_outside_bytes_never_collected(self):
        write(self.root, "architecture.json", {"模块详情": {"m": {}}, "实现清单": {"m": {"文件列表": ["../outside.secret"]}}})
        result = self.index()
        self.assertEqual(result["files"], [])
        self.assertIn("invalid_path", {item["code"] for item in result["diagnostics"]})
        for architecture in ("../outside.json", "C:/outside.json", "/outside.json"):
            with self.assertRaises(_archlib.ArchitectureInputError):
                query.build_index(self.root, architecture)

    def test_missing_files_and_prose_remain_explicit_unknowns(self):
        data = {"模块详情": {"m": {"测试责任": ["应该检查输入", "tests/test.any：尚未执行"]}},
                "实现清单": {"m": {"文件列表": ["missing.any"]}}}
        write(self.root, "architecture.json", data)
        result = self.index()
        self.assertEqual([item["path"] for item in result["files"]], ["missing.any"])
        self.assertEqual({item["code"] for item in result["diagnostics"]}, {"missing_file", "unstructured_path"})
        self.assertIsNone(query.context(result, "m")["input_versions"]["missing.any"])

    def test_declared_directory_preserved_without_false_file_digest(self):
        (self.root / "src").mkdir()
        write(self.root, "architecture.json", {"模块树": [{"编号": "m", "落位": {"文件": ["src/"]}, "子模块": []}]})
        result = self.index()
        self.assertTrue(result["files"][0]["is_directory"])
        self.assertNotIn("src", query.context(result, "m")["input_versions"])
        self.assertNotIn("missing_file", {item["code"] for item in result["diagnostics"]})

    def test_change_during_indexing_rejects_stale_snapshot(self):
        write(self.root, "architecture.json", {"功能树": [{"编号": "f"}]})
        original = query._Builder.build
        def changed(builder):
            result = original(builder)
            write(self.root, "architecture.json", {"功能树": [{"编号": "replacement"}]})
            return result
        with patch.object(query._Builder, "build", changed):
            with self.assertRaisesRegex(_archlib.ArchitectureInputError, "发生变化"):
                self.index()

    def test_unicode_pointer_escaping_and_bom(self):
        data = {"接口契约": {"域/接口~1": {"输入": "原始"}}}
        (self.root / "architecture.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(data, ensure_ascii=False).encode("utf-8"))
        result = self.index()
        obj = query.read_object(result, query.object_id("contract", "域/接口~1"))
        self.assertEqual(obj["locations"][0]["pointer"], "/接口契约/域~1接口~01")

    def test_topology_edges_retain_extension_facts_and_data_endpoint_relations(self):
        edge = {"从": "a", "到": "b", "说明": "不能丢失", "自定义条件": {"重试": False}}
        data = {"模块拓扑": {"节点": [{"编号": "a"}, {"编号": "b"}], "依赖图": [edge]},
                "数据拓扑": {"节点": [{"编号": "d1"}, {"编号": "d2"}],
                             "关系": [{"从": "d1", "到": "d2", "说明": "数据派生", "未知扩展": [1, 2]}]}}
        write(self.root, "architecture.json", data)
        result = self.index()
        module_edge = next(item for item in result["relationships"] if item["source"] == "module:a")
        self.assertEqual(module_edge["declarations"][0]["value"], edge)
        self.assertEqual(module_edge["locations"][0]["pointer"], "/模块拓扑/依赖图/0")
        data_edge = next(item for item in result["relationships"] if item["source"] == "data:d1")
        self.assertEqual((data_edge["type"], data_edge["target"]), ("dependency", "data:d2"))
        self.assertEqual(data_edge["declarations"][0]["value"]["未知扩展"], [1, 2])
        self.assertIn("data:d2", {item["id"] for item in query.context(result, "data:d1")["related_objects"]})

    def test_file_mutation_during_query_rejects_stale_source_versions(self):
        self.recursive()
        original = query._Builder.build
        def changed(builder):
            result = original(builder)
            self.source("领域/worker/code.unknown", b"concurrent editor")
            return result
        with patch.object(query._Builder, "build", changed):
            with self.assertRaisesRegex(_archlib.ArchitectureInputError, "声明文件内容发生变化"):
                self.index()

    def test_explicit_test_paths_allow_spaces_unicode_colons_and_no_extension(self):
        for file in ("测试/键：值 case", "tests/extensionless"):
            self.source(file)
        write(self.root, "architecture.json", {"模块详情": {"m": {}}, "测试责任矩阵": [
            {"编号": "tests", "模块": "m", "测试文件": ["测试/键：值 case", "tests/extensionless"]}]})
        result = self.index()
        self.assertEqual({item["path"] for item in result["files"]}, {"测试/键：值 case", "tests/extensionless"})
        self.assertTrue(all(item["exists"] for item in result["files"]))

    def test_cross_module_references_are_not_ownership_declarations(self):
        root, worker, _, _ = self.recursive()
        root["功能树"] = [{"编号": "global", "架构落位": {"文件": ["领域/worker/code.unknown"]}}]
        write(self.root, "architecture.json", root)
        result = self.index()
        entries = [item for item in result["files"] if item["path"] == "领域/worker/code.unknown"]
        reference = next(item for item in entries if item["declared_by"] == "root")
        authoritative = next(item for item in entries if item["declared_by"] == "worker")
        self.assertFalse(reference["ownership"])
        self.assertEqual(reference["physical_owner"], "worker")
        self.assertTrue(authoritative["ownership"])
        self.assertEqual(authoritative["physical_owner"], "worker")
        self.assertEqual(authoritative["ownership_locations"][0]["pointer"], "/实现清单/worker/文件列表/0")


if __name__ == "__main__":
    unittest.main()
