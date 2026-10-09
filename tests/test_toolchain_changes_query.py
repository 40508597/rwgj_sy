"""Independent real-directory checks of staged ownership and module migration."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared/scripts"))
import _toolchain_changes as changes
import _toolchain_query as query
from _toolchain_store import Store, ToolchainError


def write(root, rel, value):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def document(key, files=()):
    return {"模块路由": {"版本": 1, "编号": key, "名称": key, "职责": "负责" + key, "子模块": []},
            "模块详情": {key: {"职责": "负责" + key}},
            "实现清单": {key: {"文件列表": list(files), "依赖模块": []}}}


class ChangesQueryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        root = document("root", ["main.unknown"])
        worker = document("worker", ["work/code.opaque", "work/test.case"])
        leaf = document("leaf", ["work/leaf/code.any"])
        consumer = document("consumer", ["consumer/code.unknown"])
        root["模块路由"]["子模块"] = [
            {"编号": "worker", "路径": "work/architecture.json", "职责": "负责worker"},
            {"编号": "consumer", "路径": "consumer/architecture.json", "职责": "负责consumer"}]
        worker["模块路由"]["子模块"] = [{"编号": "leaf", "路径": "leaf/architecture.json", "职责": "负责leaf"}]
        consumer["实现清单"]["consumer"]["依赖模块"] = ["worker"]
        consumer["功能树"] = [{"编号": "call", "名称": "调用执行器", "架构落位": {
            "模块": ["worker"], "文件": ["work/code.opaque"], "测试": ["work/test.case"]}}]
        worker["测试责任矩阵"] = [{"编号": "t", "模块": "worker", "测试": "work/test.case"}]
        for rel, data in (("architecture.json", root), ("work/architecture.json", worker),
                          ("work/leaf/architecture.json", leaf), ("consumer/architecture.json", consumer)):
            write(self.project, rel, data)
        for rel in ("main.unknown", "work/code.opaque", "work/test.case", "work/leaf/code.any", "consumer/code.unknown"):
            path = self.project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("original:" + rel).encode("utf-8"))

    def payload(self, **kwargs):
        return {"actor": "independent-test", "request_id": uuid.uuid4().hex, **kwargs}

    def begin(self, scope=None):
        return changes.begin(self.project, "architecture.json", self.payload(
            scope=scope or ["worker"], goal="实际目录归属和变更回归"))

    def stage(self, change, operations):
        return changes.stage(self.project, self.payload(id=change["id"], operations=operations))

    def apply(self, change):
        return changes.apply(self.project, self.payload(id=change["id"]))

    def project_bytes(self):
        return {path.relative_to(self.project).as_posix(): path.read_bytes()
                for path in self.project.rglob("*") if path.is_file()
                and not path.relative_to(self.project).as_posix().startswith("architecture/toolchain/")}

    def test_begin_stage_preview_apply_uses_actual_owner_and_keeps_unrelated_bytes(self):
        before = self.project_bytes()
        change = self.begin()
        staged = self.stage(change, [
            {"type": "set", "file": "work/architecture.json", "pointer": "/模块详情/worker/错误约定", "value": "明确拒绝无效输入"},
            {"type": "write", "file": "work/code.opaque", "base64": "AP8BwA=="}])
        self.assertEqual(staged["status"], "draft")
        self.assertEqual(self.project_bytes(), before)
        preview = changes.preview(self.project, change["id"])
        self.assertTrue(preview["current_inputs_match"])
        self.assertEqual({item["file"] for item in preview["changes"]}, {"work/architecture.json", "work/code.opaque"})
        applied = self.apply(change)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual((self.project / "work/code.opaque").read_bytes(), b"\x00\xff\x01\xc0")
        after = self.project_bytes()
        for rel in set(before) - {"work/architecture.json", "work/code.opaque"}:
            self.assertEqual(before[rel], after[rel])
        result = query.read_object(query.build_index(self.project), "worker")
        self.assertEqual(result["value"]["模块详情"]["错误约定"], "明确拒绝无效输入")

    def test_new_source_must_be_registered_in_staged_design(self):
        change = self.begin()
        before = self.project_bytes()
        with self.assertRaises(ToolchainError):
            self.stage(change, [{"type": "write", "file": "work/new.even-unknown", "text": "new code"}])
        self.assertEqual(self.project_bytes(), before)
        self.assertEqual(Store(self.project).get("change", change["id"])["operations"], [])
        self.stage(change, [
            {"type": "set", "file": "work/architecture.json", "pointer": "/实现清单/worker/文件列表",
             "value": ["work/code.opaque", "work/test.case", "work/new.even-unknown"]},
            {"type": "write", "file": "work/new.even-unknown", "text": "new code"}])
        self.apply(change)
        self.assertEqual((self.project / "work/new.even-unknown").read_text(encoding="utf-8"), "new code")
        self.assertIn("work/new.even-unknown", {item["path"] for item in query.build_index(self.project)["files"]})

    def test_cross_module_source_reference_does_not_grant_file_ownership(self):
        # consumer refers to worker's file as context, while the actual physical
        # ownership is worker. That reference must not block worker's own edit.
        change = self.begin(["worker"])
        self.stage(change, [{"type": "write", "file": "work/code.opaque", "text": "worker edit"}])
        self.apply(change)
        self.assertEqual((self.project / "work/code.opaque").read_text(encoding="utf-8"), "worker edit")

    def test_out_of_scope_architecture_and_sources_cannot_be_staged(self):
        change = self.begin()
        before = self.project_bytes()
        for operation in (
            {"type": "write", "file": "main.unknown", "text": "escaped scope"},
            {"type": "write", "file": "consumer/code.unknown", "text": "escaped scope"},
            {"type": "set", "file": "architecture.json", "pointer": "/根约束", "value": "escaped scope"}):
            with self.assertRaises(ToolchainError):
                self.stage(change, [operation])
        self.assertEqual(self.project_bytes(), before)

    def test_stale_inputs_and_new_unread_files_reject_apply_without_overwrite(self):
        change = self.begin()
        self.stage(change, [{"type": "write", "file": "work/code.opaque", "text": "new content"}])
        (self.project / "work/code.opaque").write_bytes(b"concurrent content")
        with self.assertRaises(ToolchainError):
            self.apply(change)
        self.assertEqual((self.project / "work/code.opaque").read_bytes(), b"concurrent content")
        self.assertEqual(Store(self.project).get("change", change["id"])["status"], "draft")
        fresh = self.begin()
        self.stage(fresh, [{"type": "write", "file": "work/code.opaque", "text": "second version"}])
        (self.project / "external-new-file.unknown").write_bytes(b"not in read inventory")
        with self.assertRaises(ToolchainError):
            self.apply(fresh)
        self.assertEqual((self.project / "work/code.opaque").read_bytes(), b"concurrent content")

    def test_module_create_can_be_planned_staged_and_applied(self):
        change = self.begin(["root"])
        self.stage(change, [{"type": "module.create", "parent": "root", "directory": "new-module",
                             "module": "new", "name": "新模块", "responsibility": "负责新增能力"}])
        preview = changes.preview(self.project, change["id"])
        self.assertEqual(preview["structure"]["status"], "pass")
        self.apply(change)
        self.assertTrue((self.project / "new-module/architecture.json").is_file())
        result = query.build_index(self.project)
        self.assertEqual(query.read_object(result, "new")["value"]["模块路由"]["职责"], "负责新增能力")

    def test_create_with_registered_opaque_source_in_same_staged_change(self):
        change = self.begin(["worker"])
        self.stage(change, [
            {"type": "module.create", "parent": "worker", "directory": "new",
             "module": "new", "name": "子模块", "responsibility": "负责新增能力"},
            {"type": "set", "file": "work/new/architecture.json", "pointer": "/实现清单/new/文件列表",
             "value": ["work/new/code.未知语言"]},
            {"type": "write", "file": "work/new/code.未知语言", "base64": "AP//AQ=="}])
        self.apply(change)
        self.assertEqual((self.project / "work/new/code.未知语言").read_bytes(), b"\x00\xff\xff\x01")
        result = query.build_index(self.project)
        self.assertEqual(next(item["physical_owner"] for item in result["files"] if item["path"] == "work/new/code.未知语言"), "new")

    def test_module_create_cannot_modify_parent_outside_declared_scope(self):
        before = self.project_bytes()
        change = self.begin(["worker"])
        with self.assertRaises(ToolchainError):
            self.stage(change, [{"type": "module.create", "parent": "root", "directory": "new",
                                 "module": "new", "name": "新", "responsibility": "新职责"}])
        self.assertEqual(self.project_bytes(), before)

    def test_central_behavior_reference_does_not_expand_manifest_write_ownership(self):
        central = self.project / "central"
        write(central, "architecture.json", {
            "模块详情": {"a": {"职责": "a"}, "b": {"职责": "b"}},
            "实现清单": {"a": {"文件列表": ["src/a.unknown"]}, "b": {"文件列表": ["src/b.unknown"]}},
            "功能树": [{"编号": "fb", "所属模块": "b", "架构落位": {"模块": ["b"], "文件": ["src/a.unknown"]}}]})
        for name in ("a", "b"):
            path = central / ("src/" + name + ".unknown")
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(name.encode())
        self.project = central
        change = self.begin(["a"])
        self.stage(change, [{"type": "write", "file": "src/a.unknown", "text": "updated a"}])
        self.apply(change)
        self.assertEqual((central / "src/a.unknown").read_text(encoding="utf-8"), "updated a")
        self.assertEqual((central / "src/b.unknown").read_bytes(), b"b")

    def test_module_move_preserves_ids_bytes_children_and_cross_module_references(self):
        before_index = query.build_index(self.project)
        source_bytes = (self.project / "work/code.opaque").read_bytes()
        leaf_bytes = (self.project / "work/leaf/code.any").read_bytes()
        change = self.begin(["root", "worker", "leaf", "consumer"])
        self.stage(change, [{"type": "module.move", "module": "worker", "parent": "root", "to_directory": "renamed/worker"}])
        preview = changes.preview(self.project, change["id"])
        self.assertEqual(preview["structure"]["status"], "pass")
        self.apply(change)
        self.assertEqual((self.project / "renamed/worker/code.opaque").read_bytes(), source_bytes)
        self.assertEqual((self.project / "renamed/worker/leaf/code.any").read_bytes(), leaf_bytes)
        self.assertFalse((self.project / "work/architecture.json").exists())
        result = query.build_index(self.project)
        for key in ("root", "worker", "leaf", "consumer"):
            self.assertEqual(query.read_object(result, key)["id"], query.read_object(before_index, key)["id"])
        self.assertEqual(query.read_object(result, "worker")["value"]["实现清单"]["文件列表"],
                         ["renamed/worker/code.opaque", "renamed/worker/test.case"])
        consumer = query.read_object(result, "behavior:call")
        self.assertEqual(consumer["value"]["架构落位"]["文件"], ["renamed/worker/code.opaque"])
        self.assertFalse(any(item["code"] == "missing_file" for item in result["diagnostics"]))

    def test_move_requires_all_subtree_and_external_reference_owners(self):
        before = self.project_bytes()
        for scope in (["root", "worker"], ["root", "worker", "leaf"]):
            change = self.begin(scope)
            with self.assertRaises(ToolchainError):
                self.stage(change, [{"type": "module.move", "module": "worker", "to_directory": "moved"}])
        self.assertEqual(self.project_bytes(), before)

    def test_module_move_rewrites_native_test_selectors_to_actual_new_file(self):
        path = self.project / "work/architecture.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["测试责任矩阵"][0]["测试"] = "work/test.case::测试行为"
        write(self.project, "work/architecture.json", document)
        change = self.begin(["root", "worker", "leaf", "consumer"])
        self.stage(change, [{"type": "module.move", "module": "worker", "to_directory": "moved"}])
        self.apply(change)
        result = query.build_index(self.project)
        test = query.read_object(result, "test:t")
        self.assertEqual(test["value"]["测试"], "moved/test.case::测试行为")
        self.assertTrue(all(item["exists"] for item in result["files"] if item["role"] == "test"))

    def test_module_move_preserves_opaque_literals_and_reports_unresolved_candidates(self):
        path = self.project / "work/architecture.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["消息模板"] = {"原样输出": "work/code.opaque", "work/test.case": "业务键不推断为路径"}
        document["接口契约"] = {"worker": {"导出": [{"名称": "render_literal", "签名": "work/code.opaque", "返回常量": "work/code.opaque"}]}}
        write(self.project, "work/architecture.json", document)
        change = self.begin(["root", "worker", "leaf", "consumer"])
        self.stage(change, [{"type": "module.move", "module": "worker", "to_directory": "moved"}])
        preview = changes.preview(self.project, change["id"])
        # An opaque exact match may be an intentional literal or an undeclared
        # path. The tool must disclose it without guessing which is true.
        diagnostics = json.dumps(preview["diagnostics"], ensure_ascii=False)
        self.assertIn("work/code.opaque", diagnostics)
        self.apply(change)
        actual = json.loads((self.project / "moved/architecture.json").read_text(encoding="utf-8"))
        self.assertEqual(actual["消息模板"], document["消息模板"])
        self.assertEqual(actual["接口契约"]["worker"]["导出"], document["接口契约"]["worker"]["导出"])
        self.assertEqual(actual["实现清单"]["worker"]["文件列表"], ["moved/code.opaque", "moved/test.case"])

    def test_cross_parent_move_synchronizes_explicit_global_and_local_module_trees(self):
        root = json.loads((self.project / "architecture.json").read_text(encoding="utf-8"))
        worker = json.loads((self.project / "work/architecture.json").read_text(encoding="utf-8"))
        consumer = json.loads((self.project / "consumer/architecture.json").read_text(encoding="utf-8"))
        leaf_node = {"编号": "leaf", "父模块": "worker", "说明": "完整保留孙模块", "子模块": [],
                     "落位": {"文件": ["work/leaf/code.any"]}}
        worker_node = {"编号": "worker", "父模块": "root", "名称": "执行器", "自定义事实": {"保留": True},
                       "原样业务字符串": "work/code.opaque", "子模块": [leaf_node],
                       "落位": {"文件": ["work/code.opaque"], "测试": ["work/test.case::验收"]}}
        consumer_node = {"编号": "consumer", "父模块": "root", "说明": "新的物理父模块", "子模块": []}
        root["模块树"] = [{"编号": "root", "父模块": None, "子模块": [copy.deepcopy(worker_node), copy.deepcopy(consumer_node)]}]
        worker["模块树"] = [copy.deepcopy(worker_node)]
        consumer["模块树"] = [copy.deepcopy(consumer_node)]
        write(self.project, "architecture.json", root)
        write(self.project, "work/architecture.json", worker)
        write(self.project, "consumer/architecture.json", consumer)
        code = (self.project / "work/code.opaque").read_bytes()
        leaf_code = (self.project / "work/leaf/code.any").read_bytes()
        change = self.begin(["root", "worker", "leaf", "consumer"])
        self.stage(change, [{"type": "module.move", "module": "worker", "parent": "consumer", "to_directory": "consumer/nested-worker"}])
        self.assertEqual(changes.preview(self.project, change["id"])["structure"]["status"], "pass")
        self.apply(change)
        actual_root = json.loads((self.project / "architecture.json").read_text(encoding="utf-8"))
        root_node = actual_root["模块树"][0]
        self.assertEqual([node["编号"] for node in root_node["子模块"]], ["consumer"])
        new_parent_node = root_node["子模块"][0]
        actual_worker = new_parent_node["子模块"][0]
        self.assertEqual((actual_worker["编号"], actual_worker["父模块"]), ("worker", "consumer"))
        self.assertEqual(actual_worker["自定义事实"], {"保留": True})
        self.assertEqual(actual_worker["原样业务字符串"], "work/code.opaque")
        self.assertEqual(actual_worker["落位"], {"文件": ["consumer/nested-worker/code.opaque"], "测试": ["consumer/nested-worker/test.case::验收"]})
        self.assertEqual(actual_worker["子模块"][0]["父模块"], "worker")
        self.assertEqual(actual_worker["子模块"][0]["落位"]["文件"], ["consumer/nested-worker/leaf/code.any"])
        local = json.loads((self.project / "consumer/nested-worker/architecture.json").read_text(encoding="utf-8"))
        self.assertEqual(local["模块树"][0], actual_worker)
        consumer_local = json.loads((self.project / "consumer/architecture.json").read_text(encoding="utf-8"))
        self.assertEqual(consumer_local["模块树"][0]["子模块"], [actual_worker])
        self.assertEqual((self.project / "consumer/nested-worker/code.opaque").read_bytes(), code)
        self.assertEqual((self.project / "consumer/nested-worker/leaf/code.any").read_bytes(), leaf_code)
        index = query.build_index(self.project)
        module_edges = {(edge["source"], edge["target"]) for edge in index["relationships"] if edge["type"] == "contains"
                        and edge["source"].startswith("module:") and edge["target"].startswith("module:")}
        self.assertIn(("module:consumer", "module:worker"), module_edges)
        self.assertNotIn(("module:root", "module:worker"), module_edges)
        self.assertFalse(any(item["code"] == "missing_file" for item in index["diagnostics"]))


if __name__ == "__main__":
    unittest.main()
