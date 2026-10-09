"""Recursive physical modules: trust boundaries, local reads and safe writes."""

import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
import _archlib
import _module_tree as modules
import module_architecture as cli


def document(module_id, name=None, responsibility=None, files=None):
    return {"模块路由": {"版本": 1, "编号": module_id, "名称": name or module_id,
                         "职责": responsibility or f"负责{module_id}", "子模块": []},
            "模块详情": {module_id: {"职责": responsibility or f"负责{module_id}"}},
            "实现清单": {module_id: {"文件列表": list(files or []), "依赖模块": []}}}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def attach(parent, child, path):
    parent["模块路由"]["子模块"].append({"编号": child["模块路由"]["编号"], "路径": path,
                                         "职责": child["模块路由"]["职责"]})


class TreeCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "architecture.json"

    def base_tree(self):
        root = document("root", "总系统", "编排项目", ["main.anylanguage"])
        root["项目"] = {"名称": "任意语言项目", "扩展": {"原始事实": True}}
        root["上下文恢复点"] = {"下一步": ["保持全局恢复"]}
        child = document("worker", "执行器", "处理任务", ["业务/执行器/worker.rs", "业务/执行器/test.case"])
        attach(root, child, "业务/执行器/architecture.json")
        write(self.path, root)
        write(self.root / "业务/执行器/architecture.json", child)
        for path in ("main.anylanguage", "业务/执行器/worker.rs", "业务/执行器/test.case"):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("language independent", encoding="utf-8")
        return root, child

    def hydrate(self, data):
        return modules.hydrate_module_tree(data, self.path)

    def run_cli(self, arguments):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = cli.main(arguments)
        return code, json.loads(stdout.getvalue())

    def test_legacy_passthrough_and_no_input_mutation(self):
        old = {"项目": {"名称": "旧架构"}}
        self.assertIs(self.hydrate(old), old)
        root, child = self.base_tree()
        original = copy.deepcopy(root)
        child_bytes = (self.root / "业务/执行器/architecture.json").read_bytes()
        sources = set()
        merged = modules.hydrate_module_tree(root, self.path, sources)
        self.assertEqual(root, original)
        self.assertEqual((self.root / "业务/执行器/architecture.json").read_bytes(), child_bytes)
        self.assertEqual(merged["项目"], original["项目"])
        self.assertEqual(merged["模块路由"], original["模块路由"])
        self.assertEqual({path.relative_to(self.root).as_posix() for path in sources},
                         {"architecture.json", "业务/执行器/architecture.json"})
        self.assertEqual(set(merged["模块详情"]), {"root", "worker"})
        self.assertEqual([item["编号"] for item in merged["模块拓扑"]["节点"]], ["root", "worker"])

    def test_unicode_route_parent_source_and_all_suffixes(self):
        root, _ = self.base_tree()
        merged = self.hydrate(root)
        self.assertEqual(modules.check_hydrated_module_files(merged, self.root), [])
        tree, _ = cli.load_tree(self.path)
        result = cli.route(tree, file="业务/执行器/test.case")
        self.assertEqual([item["编号"] for item in result["链"]], ["root", "worker"])
        self.assertTrue(result["已登记"])
        self.assertEqual(cli.route(tree, file="main.anylanguage")["模块"], "root")
        self.assertEqual(cli.route(tree, file="业务/执行器/new.nonstandard")["模块"], "worker")
        self.assertFalse(cli.route(tree, file="业务/执行器/new.nonstandard")["已登记"])

    def test_iterative_tree_deeper_than_sixty_four_layers(self):
        root = document("m0")
        current = root
        directory = self.root
        depth = 72
        for index in range(1, depth + 1):
            child = document(f"m{index}")
            attach(current, child, "x/architecture.json")
            write(directory / "architecture.json", current)
            directory = directory / "x"
            current = child
        write(directory / "architecture.json", current)
        tree = modules.build_module_tree(root, self.path)
        self.assertEqual(len(tree.records), depth + 1)
        self.assertEqual(len(tree.chain(f"m{depth}")), depth + 1)
        self.assertEqual(tree.records[-1]["父模块"], f"m{depth - 1}")

    def test_unknown_child_facts_and_route_extensions_are_scoped(self):
        root, first = self.base_tree()
        second = document("other")
        first["业务事实"] = {"同名": "第一份"}
        first["模块路由"]["自定义头事实"] = {"保持": True}
        second["业务事实"] = {"同名": "第二份"}
        attach(root, second, "other/architecture.json")
        write(self.root / "业务/执行器/architecture.json", first)
        write(self.root / "other/architecture.json", second)
        merged = self.hydrate(root)
        self.assertEqual(merged["模块归属事实"]["worker"]["业务事实"], {"同名": "第一份"})
        self.assertEqual(merged["模块归属事实"]["other"]["业务事实"], {"同名": "第二份"})
        self.assertEqual(merged["模块归属事实"]["worker"]["模块路由"]["自定义头事实"], {"保持": True})
        self.assertNotIn("业务事实", merged)

    def test_existing_semantic_consumers_receive_child_design_facts(self):
        import check_placeholders
        import validate_architecture
        root, child = self.base_tree()
        root["功能树"] = [{"编号": "entry", "名称": "项目入口"}]
        child["功能树"] = [{"编号": "work", "名称": "执行业务"}]
        child["数据拓扑"] = [{"编号": "work_item", "名称": "任务实体", "写入模块": "worker"}]
        child["完整细节"] = {"执行器设计": {"重试": "__待填：重试边界__"}}
        child["运行形态"] = ["worker-service"]
        write(self.path, root)
        write(self.root / "业务/执行器/architecture.json", child)
        merged = _archlib.load_architecture_json(self.path)
        self.assertEqual([item["编号"] for item in merged["功能树"]], ["entry", "work"])
        self.assertEqual(merged["数据拓扑"], child["数据拓扑"])
        self.assertEqual(merged["运行形态"], ["worker-service"])
        placeholders = check_placeholders.find_value_placeholders(merged)
        self.assertIn(("root.完整细节.执行器设计.重试", "__待填：重试边界__"), placeholders)
        # An invalid child-only standard field reaches the old schema validator;
        # it cannot hide in an opaque extension and escape its type checks.
        child["数据拓扑"] = "invalid: not an array or object"
        write(self.root / "业务/执行器/architecture.json", child)
        invalid = _archlib.load_architecture_json(self.path)
        errors, _ = validate_architecture.validate_architecture(invalid, self.root, stage="skeleton")
        self.assertTrue(any("数据拓扑 类型应为" in error for error in errors), errors)

    def test_conflicting_shared_facts_are_rejected(self):
        root, child = self.base_tree()
        root["接口契约"] = {"boundary": {"输入": "A"}}
        child["接口契约"] = {"boundary": {"输入": "B"}}
        write(self.root / "业务/执行器/architecture.json", child)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "冲突"):
            self.hydrate(root)

    def test_duplicate_ids_mismatched_header_and_responsibility(self):
        for field, value in (("编号", "unexpected"), ("职责", "不同职责")):
            with self.subTest(field=field):
                root, child = self.base_tree()
                child["模块路由"][field] = value
                write(self.root / "业务/执行器/architecture.json", child)
                with self.assertRaisesRegex(_archlib.ArchitectureInputError, "编号/职责不一致"):
                    self.hydrate(root)
        root, child = self.base_tree()
        child["模块路由"]["编号"] = "root"
        child["模块详情"] = {"root": {}}
        child["实现清单"] = {"root": {}}
        root["模块路由"]["子模块"][0]["编号"] = "root"
        write(self.root / "业务/执行器/architecture.json", child)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "全局唯一"):
            self.hydrate(root)

    def test_version_bool_and_responsibility_list_rejected(self):
        for field, value in (("版本", True), ("职责", ["业务"]), ("名称", "")):
            with self.subTest(field=field):
                root = document("root")
                root["模块路由"][field] = value
                with self.assertRaises(_archlib.ArchitectureInputError):
                    self.hydrate(root)

    def test_global_and_derived_fields_cannot_be_child_overrides(self):
        for key in ("项目", "上下文恢复点", "验证证据", "质量状态", "架构切片", "模块目录", "模块归属事实",
                    "专业能力调用", "能力调用记录"):
            with self.subTest(key=key):
                root, child = self.base_tree()
                child[key] = {}
                write(self.root / "业务/执行器/architecture.json", child)
                with self.assertRaises(_archlib.ArchitectureInputError):
                    self.hydrate(root)
        root, _ = self.base_tree()
        root["模块目录"] = []
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "派生字段"):
            self.hydrate(root)

    def test_manifests_and_details_only_declare_their_owner(self):
        for key in ("实现清单", "模块详情"):
            with self.subTest(key=key):
                root, child = self.base_tree()
                child[key]["root"] = {}
                write(self.root / "业务/执行器/architecture.json", child)
                with self.assertRaisesRegex(_archlib.ArchitectureInputError, "只能声明本模块"):
                    self.hydrate(root)

    def test_recursive_explicit_identifiers_cannot_redirect_physical_owner(self):
        for section in ("模块详情", "实现清单"):
            for alias in ("模块编号", "模块号"):
                for value in ("root", "", None, False, 3, ["worker"]):
                    with self.subTest(section=section, alias=alias, value=value):
                        root, child = self.base_tree()
                        child[section]["worker"][alias] = value
                        write(self.root / "业务/执行器/architecture.json", child)
                        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "模块归属不一致"):
                            cli.load_tree(self.path)
        root, child = self.base_tree()
        for section in ("模块详情", "实现清单"):
            child[section]["worker"].update({"模块编号": "worker", "模块号": "worker"})
        write(self.root / "业务/执行器/architecture.json", child)
        self.assertEqual(cli.load_tree(self.path)[0].record("worker")["文件"],
                         ["业务/执行器/test.case", "业务/执行器/worker.rs"])

    def test_recursive_validator_defends_already_hydrated_identity_changes(self):
        import validate_architecture
        root, _ = self.base_tree()
        tree, sources = cli.load_tree(self.path)
        for section in ("模块详情", "实现清单"):
            for alias in ("模块编号", "模块号"):
                with self.subTest(section=section, alias=alias):
                    edited = copy.deepcopy(tree.merged)
                    edited[section]["worker"][alias] = "root"
                    errors = validate_architecture._check_module_directory(edited, self.root, "full", sources)
                    self.assertTrue(any(section + ".worker." + alias in error for error in errors), errors)
        root, _ = self.base_tree()
        root["实现清单"]["root"]["文件列表"].append("业务/执行器/worker.rs")
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "进入子模块"):
            self.hydrate(root)

    def test_child_cannot_claim_sibling_or_parent_source(self):
        for relative in ("main.anylanguage", "other/file.kt", "../outside", "C:/secret/file"):
            with self.subTest(path=relative):
                root, child = self.base_tree()
                child["实现清单"]["worker"]["文件列表"] = [relative]
                write(self.root / "业务/执行器/architecture.json", child)
                with self.assertRaises(_archlib.ArchitectureInputError):
                    self.hydrate(root)

    def test_child_route_must_be_strict_descendant_and_not_duplicate(self):
        for relative in ("../outside/architecture.json", "architecture.json", "C:/else/architecture.json",
                         "业务/执行器/not-architecture.json"):
            with self.subTest(path=relative):
                root, _ = self.base_tree()
                root["模块路由"]["子模块"][0]["路径"] = relative
                with self.assertRaises(_archlib.ArchitectureInputError):
                    self.hydrate(root)
        root, _ = self.base_tree()
        duplicate = copy.deepcopy(root["模块路由"]["子模块"][0])
        duplicate["编号"] = "alias"
        root["模块路由"]["子模块"].append(duplicate)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "重复"):
            self.hydrate(root)

    def test_nested_physical_module_cannot_be_declared_as_sibling(self):
        root = document("root")
        parent, nested = document("parent"), document("nested")
        attach(root, parent, "a/architecture.json")
        attach(root, nested, "a/nested/architecture.json")
        write(self.path, root)
        write(self.root / "a/architecture.json", parent)
        write(self.root / "a/nested/architecture.json", nested)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "实际目录归属"):
            self.hydrate(root)

    def test_symlink_escapes_and_same_real_architecture_are_rejected(self):
        def directory_link(link, target):
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                if os.name != "nt":
                    self.skipTest(f"symlink unavailable: {exc}")
                # Windows junctions exercise real path resolution without
                # requiring Developer Mode or the symlink privilege.
                completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                           capture_output=True)
                if completed.returncode:
                    self.skipTest(f"symlink/junction unavailable: {exc}")
            self.addCleanup(lambda: link.rmdir() if os.path.lexists(link) else None)
        root, child = self.base_tree()
        with tempfile.TemporaryDirectory() as outside:
            outside_path = Path(outside)
            write(outside_path / "architecture.json", child)
            directory_link(self.root / "escape", outside_path)
            tree, _ = cli.load_tree(self.path)
            self.assertEqual(modules.unregistered_architectures(tree), [])
            root["模块路由"]["子模块"][0]["路径"] = "escape/architecture.json"
            with self.assertRaisesRegex(_archlib.ArchitectureInputError, "超出项目范围"):
                self.hydrate(root)
        root, _ = self.base_tree()
        directory_link(self.root / "alias", self.root / "业务/执行器")
        extra = copy.deepcopy(root["模块路由"]["子模块"][0])
        extra.update({"编号": "alias", "路径": "alias/architecture.json"})
        root["模块路由"]["子模块"].append(extra)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "重复"):
            self.hydrate(root)

    def test_source_hardlinks_cannot_create_two_real_file_owners(self):
        root = document("root", files=["one.src"])
        child = document("child", files=["child/two.src"])
        attach(root, child, "child/architecture.json")
        write(self.path, root)
        write(self.root / "child/architecture.json", child)
        (self.root / "one.src").write_text("same inode", encoding="utf-8")
        try:
            os.link(self.root / "one.src", self.root / "child/two.src")
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "同一真实文件"):
            self.hydrate(root)

    def test_hardlinked_architecture_cannot_have_two_parents(self):
        root = document("root")
        root["模块路由"]["子模块"] = [{"编号": "child", "路径": "child/architecture.json", "职责": "子职责"}]
        write(self.path, root)
        (self.root / "child").mkdir()
        try:
            os.link(self.path, self.root / "child/architecture.json")
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "同一真实文件"):
            self.hydrate(root)

    def test_architecture_hardlink_cannot_masquerade_as_source(self):
        root, _ = self.base_tree()
        source = self.root / "业务/执行器/worker.rs"
        source.unlink()
        try:
            os.link(self.path, source)
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "架构元数据.*实现文件"):
            self.hydrate(root)

    def test_known_slice_metadata_hardlink_is_not_ordinary_source(self):
        root, _ = self.base_tree()
        metadata = self.root / "metadata/slice.json"
        write(metadata, {"功能树": []})
        source = self.root / "业务/执行器/worker.rs"
        source.unlink()
        try:
            os.link(metadata, source)
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "架构元数据.*实现文件"):
            modules.hydrate_module_tree(root, self.path, {metadata})

    def test_pointer_metadata_hardlink_is_not_source(self):
        root = document("root")
        child = document("child", files=["architecture/child/implementation.src"])
        attach(root, child, "child/architecture.json")
        write(self.path, {"指向": "architecture/index.json"})
        write(self.root / "architecture/index.json", root)
        write(self.root / "architecture/child/architecture.json", child)
        source = self.root / "architecture/child/implementation.src"
        try:
            os.link(self.path, source)
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "架构元数据.*实现文件"):
            _archlib.load_architecture_json(self.path)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "架构元数据.*实现文件"):
            _archlib.load_architecture_json(self.path, set())

    def test_missing_declared_file_is_known_failure_not_pass(self):
        root, _ = self.base_tree()
        (self.root / "业务/执行器/test.case").unlink()
        merged = self.hydrate(root)
        errors = modules.check_hydrated_module_files(merged, self.root)
        self.assertEqual(len(errors), 1)
        code, result = self.run_cli(["check", "--architecture", str(self.path)])
        self.assertEqual((code, result["status"]), (1, "fail"))
        self.assertIn("test.case", result["errors"][0])

    def test_orphan_architecture_is_a_known_failure(self):
        self.base_tree()
        write(self.root / "forgotten/architecture.json", document("orphan"))
        code, result = self.run_cli(["check", "--architecture", str(self.path)])
        self.assertEqual((code, result["status"]), (1, "fail"))
        self.assertTrue(any("forgotten/architecture.json" in item for item in result["errors"]))

    def test_orphan_inventory_explicit_scope_and_dependency_cycles(self):
        root, child = self.base_tree()
        write(self.root / "tests/fixtures/sample/architecture.json", document("fixture"))
        code, result = self.run_cli(["check", "--architecture", str(self.path), "--ignore-dir", "tests/fixtures"])
        self.assertEqual((code, result["status"]), (0, "pass"))
        self.assertIn("tests/fixtures", result["扫描忽略目录"])
        root["实现清单"]["root"]["依赖模块"] = ["worker"]
        child["实现清单"]["worker"]["依赖模块"] = ["root"]
        write(self.path, root)
        write(self.root / "业务/执行器/architecture.json", child)
        code, result = self.run_cli(["check", "--architecture", str(self.path), "--ignore-dir", "tests/fixtures"])
        self.assertEqual((code, result["status"]), (1, "fail"))
        self.assertTrue(any("有向环" in error for error in result["errors"]))

    def test_persistent_inventory_scope_is_shared_by_check_add_and_update(self):
        root, _ = self.base_tree()
        root["模块路由"]["扫描忽略目录"] = ["tests/fixtures"]
        write(self.path, root)
        write(self.root / "tests/fixtures/example/architecture.json", document("fixture"))
        code, result = self.run_cli(["check", "--architecture", str(self.path)])
        self.assertEqual((code, result["status"]), (0, "pass"))
        self.assertIn("tests/fixtures", result["扫描忽略目录"])
        cli.add(self.path, "root", "new", "new", "新增", "可正常新增")
        patch_path = self.root / "patch.json"
        write(patch_path, {"模块工作状态": {"下一步": "实际设计"}})
        target = self.root / "new/architecture.json"
        cli.update(self.path, "new", patch_path, hashlib.sha256(target.read_bytes()).hexdigest())
        tree, _ = cli.load_tree(self.path)
        self.assertEqual(modules.unregistered_architectures(tree), [])
        self.assertEqual(modules.inventory_ignore_dirs(tree), modules.DEFAULT_IGNORE_DIRS | {"tests/fixtures"})

    def test_ignore_scope_cannot_escape_or_disable_registered_file_checks(self):
        for value in (["../escape"], ["C:/escape"], ["."], "tests"):
            with self.subTest(value=value):
                root, _ = self.base_tree()
                root["模块路由"]["扫描忽略目录"] = value
                with self.assertRaises(_archlib.ArchitectureInputError):
                    self.hydrate(root)
        root, child = self.base_tree()
        child["模块路由"]["扫描忽略目录"] = ["tests"]
        write(self.root / "业务/执行器/architecture.json", child)
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "全局扫描"):
            self.hydrate(root)
        root, _ = self.base_tree()
        root["模块路由"]["扫描忽略目录"] = ["业务/执行器"]
        write(self.path, root)
        (self.root / "业务/执行器/worker.rs").unlink()
        code, result = self.run_cli(["check", "--architecture", str(self.path)])
        self.assertEqual((code, result["status"]), (1, "fail"))
        self.assertTrue(any("worker.rs" in error for error in result["errors"]))

    def test_read_is_local_even_if_child_json_is_invalid(self):
        root, _ = self.base_tree()
        (self.root / "业务/执行器/architecture.json").write_text("invalid child", encoding="utf-8")
        with patch.object(_archlib, "_read_architecture_file", side_effect=AssertionError("must not load children")):
            code, result = self.run_cli(["read", "--architecture", str(self.path)])
        self.assertEqual((code, result["scope"]), (0, "local"))
        self.assertEqual(result["直接子路由"], root["模块路由"]["子模块"])
        code, result = self.run_cli(["check", "--architecture", str(self.path)])
        self.assertEqual((code, result["status"]), (2, "unknown"))

    def test_cross_branch_dependency_impact_does_not_infer_containment(self):
        root, parent, leaf, consumer = (document(name) for name in ("root", "a", "leaf", "b"))
        attach(root, parent, "a/architecture.json")
        attach(root, consumer, "b/architecture.json")
        attach(parent, leaf, "leaf/architecture.json")
        consumer["实现清单"]["b"]["依赖模块"] = ["leaf"]
        for path, payload in ((self.path, root), (self.root / "a/architecture.json", parent),
                              (self.root / "a/leaf/architecture.json", leaf), (self.root / "b/architecture.json", consumer)):
            write(path, payload)
        tree, _ = cli.load_tree(self.path)
        result = cli.impact(tree, "leaf", direction="both")
        self.assertEqual(result["包含关系"]["祖先"], ["root", "a"])
        self.assertEqual(result["依赖关系"]["受影响消费者"], ["b"])
        self.assertEqual(result["依赖关系"]["上游依赖"], [])
        result = cli.impact(tree, "root")
        self.assertEqual(result["依赖关系"]["受影响消费者"], [])
        self.assertEqual(result["包含关系"]["后代"], ["a", "leaf", "b"])

    def test_search_returns_candidates_with_no_semantic_claim(self):
        self.base_tree()
        tree, _ = cli.load_tree(self.path)
        result = cli.search(tree, "任务")
        self.assertEqual(result["scope"], "candidates")
        self.assertEqual([item["编号"] for item in result["候选"]], ["worker"])
        self.assertEqual(cli.search(tree, "未登记功能")["候选"], [])

    def test_init_full_template_has_real_root_id_and_design_placeholders(self):
        code, result = self.run_cli(["init", "--output", str(self.root), "--id", "system",
                                     "--name", "系统", "--responsibility", "提供项目能力"])
        self.assertEqual(code, 0)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("指向", data)
        self.assertEqual(data["模块路由"]["编号"], "system")
        self.assertIn("上下文恢复点", data)
        self.assertIn("功能树", data)
        self.assertIn("__待填__", data["模块详情"]["system"].values())
        self.assertIn("module_architecture.py", data["变更记录"][-1]["原因"])
        self.assertNotIn("architecture/index.json", data["变更记录"][-1]["影响范围"])
        self.assertIn("模块路由", data["上下文恢复点"]["继续位置"])
        before = self.path.read_bytes()
        code, result = self.run_cli(["init", "--output", str(self.root), "--id", "other",
                                     "--name", "覆盖", "--responsibility", "不得覆盖"])
        self.assertEqual((code, result["status"]), (1, "fail"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_add_nested_module_and_preserve_parent_files(self):
        root, _ = self.base_tree()
        cli.add(self.path, "worker", "更深/解析器", "parser", "解析器", "解析输入")
        tree, _ = cli.load_tree(self.path)
        self.assertEqual([item["编号"] for item in tree.chain("parser")], ["root", "worker", "parser"])
        self.assertEqual(tree.record("worker")["文件"], ["业务/执行器/test.case", "业务/执行器/worker.rs"])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), root)
        child_path = self.root / "业务/执行器/更深/解析器/architecture.json"
        self.assertTrue(child_path.is_file())
        self.assertEqual(cli.check(tree)["status"], "pass")

    def test_add_preflights_existing_paths_duplicate_id_and_escapes(self):
        self.base_tree()
        (self.root / "existing").mkdir()
        (self.root / "file-target").write_text("retain", encoding="utf-8")
        before = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        for directory, module_id in (("existing", "new"), ("file-target", "new"), ("new/deep", "worker"),
                                     ("../escape", "new"), ("业务/执行器/new", "new")):
            with self.subTest(directory=directory):
                with self.assertRaises((cli.WriteConflict, _archlib.ArchitectureInputError, cli.CommandInputError)):
                    cli.add(self.path, "root", directory, module_id, "新模块", "拒绝部分写入")
        after = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)
        self.assertFalse((self.root / "new").exists())

    def test_add_rolls_back_own_files_if_parent_cas_conflicts(self):
        self.base_tree()
        before = self.path.read_bytes()
        with patch.object(cli, "_cas_write", side_effect=cli.WriteConflict("simulated conflict")):
            with self.assertRaises(cli.WriteConflict):
                cli.add(self.path, "root", "new/intermediate/leaf", "new", "新", "回滚新骨架")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / "new").exists())

    def test_explicit_adoption_preserves_existing_unicode_source_bytes(self):
        self.base_tree()
        directory = self.root / "已有模块/中文业务"
        directory.mkdir(parents=True)
        source = directory / "服务.scala"
        test = directory / "测试.any"
        source.write_bytes(b"original source\x00\xff")
        test.write_text("保留现有测试", encoding="utf-8")
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (source, test)}
        code, result = self.run_cli(["add", "--architecture", str(self.path), "--parent", "root",
                                     "--directory", "已有模块/中文业务", "--id", "existing", "--name", "已有业务",
                                     "--responsibility", "纳管现有代码", "--adopt-existing"])
        self.assertEqual((code, result["status"]), (0, "pass"))
        self.assertEqual({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (source, test)}, before)
        self.assertTrue((directory / "architecture.json").is_file())
        self.assertIn("existing", cli.load_tree(self.path)[0].documents)
        architecture_before = (directory / "architecture.json").read_bytes()
        with self.assertRaises(cli.WriteConflict):
            cli.add(self.path, "root", "已有模块/中文业务", "different", "不同ID", "不得覆盖", adopt_existing=True)
        self.assertEqual((directory / "architecture.json").read_bytes(), architecture_before)

    def test_failed_adoption_retains_existing_directory_and_source(self):
        self.base_tree()
        directory = self.root / "existing"
        directory.mkdir()
        source = directory / "source.go"
        source.write_text("retain source", encoding="utf-8")
        with patch.object(cli, "_cas_write", side_effect=cli.WriteConflict("simulated conflict")):
            with self.assertRaises(cli.WriteConflict):
                cli.add(self.path, "root", "existing", "new", "已有", "安全纳管", adopt_existing=True)
        self.assertTrue(directory.is_dir())
        self.assertEqual(source.read_text(encoding="utf-8"), "retain source")
        self.assertFalse((directory / "architecture.json").exists())

    def test_update_requires_expected_hash_and_preserves_unknown_fields(self):
        root, child = self.base_tree()
        path = self.root / "业务/执行器/architecture.json"
        patch_path = self.root / "patch.json"
        write(patch_path, {"自定义事实": {"评审": "待验证"}})
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        result = cli.update(self.path, "worker", patch_path, expected)
        self.assertEqual(result["status"], "pass")
        changed = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(changed["实现清单"], child["实现清单"])
        self.assertEqual(changed["自定义事实"], {"评审": "待验证"})
        before = path.read_bytes()
        with self.assertRaises(cli.WriteConflict):
            cli.update(self.path, "worker", patch_path, expected)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), root)

    def test_update_rejects_identity_changes_and_global_child_injection(self):
        self.base_tree()
        path = self.root / "业务/执行器/architecture.json"
        patch_path = self.root / "patch.json"
        before = path.read_bytes()
        expected = hashlib.sha256(before).hexdigest()
        for value in ({"模块路由": {"编号": "other"}}, {"模块路由": []},
                      {"上下文恢复点": {"全局": "非法"}}, {"模块目录": []}):
            write(patch_path, value)
            with self.assertRaises((cli.WriteConflict, _archlib.ArchitectureInputError)):
                cli.update(self.path, "worker", patch_path, expected)
            self.assertEqual(path.read_bytes(), before)

    def test_update_cannot_drop_a_route_and_leave_an_orphan(self):
        self.base_tree()
        before = self.path.read_bytes()
        patch_path = self.root / "patch.json"
        write(patch_path, {"模块路由": {"子模块": []}})
        with self.assertRaisesRegex(cli.WriteConflict, "未登记模块"):
            cli.update(self.path, "root", patch_path, hashlib.sha256(before).hexdigest())
        self.assertEqual(self.path.read_bytes(), before)

    def batch_patch(self, changes):
        patch_path = self.root / "batch-patch.json"
        entries = []
        tree, _ = cli.load_tree(self.path)
        for module_id, patch_value in changes:
            path = tree.paths[module_id]
            entries.append({"编号": module_id, "预期SHA256": hashlib.sha256(path.read_bytes()).hexdigest(), "补丁": patch_value})
        write(patch_path, {"更新": entries})
        return patch_path

    def test_batch_can_coordinate_parent_route_and_child_responsibility(self):
        root, _ = self.base_tree()
        children = copy.deepcopy(root["模块路由"]["子模块"])
        children[0]["职责"] = "处理任务并追踪结果"
        patch_path = self.batch_patch([
            ("root", {"模块路由": {"子模块": children}}),
            ("worker", {"模块路由": {"职责": "处理任务并追踪结果"},
                        "模块详情": {"worker": {"职责": "处理任务并追踪结果"}}}),
        ])
        code, result = self.run_cli(["update-batch", "--architecture", str(self.path), "--patch", str(patch_path)])
        self.assertEqual((code, result["status"]), (0, "pass"))
        self.assertEqual([item["编号"] for item in result["更新"]], ["root", "worker"])
        tree, _ = cli.load_tree(self.path)
        self.assertEqual(tree.record("worker")["职责"], "处理任务并追踪结果")
        self.assertEqual(tree.documents["root"]["模块路由"]["子模块"][0]["职责"], "处理任务并追踪结果")

    def test_batch_stale_hash_or_candidate_conflict_writes_nothing(self):
        self.base_tree()
        child_path = self.root / "业务/执行器/architecture.json"
        original = {self.path: self.path.read_bytes(), child_path: child_path.read_bytes()}
        patch_path = self.batch_patch([("root", {"局部事实": 1}), ("worker", {"局部事实": 2})])
        data = json.loads(patch_path.read_text(encoding="utf-8"))
        data["更新"][1]["预期SHA256"] = "0" * 64
        write(patch_path, data)
        with patch.object(cli, "_cas_write", wraps=cli._cas_write) as writer:
            with self.assertRaises(cli.WriteConflict):
                cli.update_batch(self.path, patch_path)
            writer.assert_not_called()
        self.assertEqual({path: path.read_bytes() for path in original}, original)
        patch_path = self.batch_patch([("root", {"局部事实": 1}), ("worker", {"模块路由": {"职责": "不协调的职责"}})])
        with patch.object(cli, "_cas_write", wraps=cli._cas_write) as writer:
            with self.assertRaises(_archlib.ArchitectureInputError):
                cli.update_batch(self.path, patch_path)
            writer.assert_not_called()
        self.assertEqual({path: path.read_bytes() for path in original}, original)

    def test_batch_rechecks_all_hashes_before_first_write(self):
        self.base_tree()
        patch_path = self.batch_patch([("root", {"事实": 1}), ("worker", {"事实": 2})])
        root_bytes = self.path.read_bytes()
        child_path = self.root / "业务/执行器/architecture.json"
        scanner = modules.unregistered_architectures
        def change_after_preflight(*args, **kwargs):
            result = scanner(*args, **kwargs)
            child_path.write_bytes(child_path.read_bytes() + b" ")
            return result
        with patch.object(modules, "unregistered_architectures", side_effect=change_after_preflight):
            with patch.object(cli, "_cas_write", wraps=cli._cas_write) as writer:
                with self.assertRaisesRegex(cli.WriteConflict, "写入前SHA256"):
                    cli.update_batch(self.path, patch_path)
                writer.assert_not_called()
        self.assertEqual(self.path.read_bytes(), root_bytes)

    def test_batch_failed_write_restores_exact_original_bytes(self):
        self.base_tree()
        self.path.write_bytes(b"\xef\xbb\xbf" + self.path.read_bytes())
        patch_path = self.batch_patch([("root", {"事实": 1}), ("worker", {"事实": 2})])
        child_path = self.root / "业务/执行器/architecture.json"
        original = {self.path: self.path.read_bytes(), child_path: child_path.read_bytes()}
        writer = cli._cas_write
        def fail_second(path, data, expected):
            if path == child_path:
                raise OSError("simulated unavailable child write")
            return writer(path, data, expected)
        with patch.object(cli, "_cas_write", side_effect=fail_second):
            with self.assertRaisesRegex(cli.WriteConflict, "已尽力回退: root"):
                cli.update_batch(self.path, patch_path)
        self.assertEqual({path: path.read_bytes() for path in original}, original)

    def test_batch_rollback_does_not_overwrite_another_writer(self):
        self.base_tree()
        patch_path = self.batch_patch([("root", {"事实": 1}), ("worker", {"事实": 2})])
        child_path = self.root / "业务/执行器/architecture.json"
        writer = cli._cas_write
        other_bytes = b'{"other_writer":true}'
        def concurrent_write(path, data, expected):
            if path == child_path:
                self.path.write_bytes(other_bytes)
                raise OSError("another writer changed root")
            return writer(path, data, expected)
        with patch.object(cli, "_cas_write", side_effect=concurrent_write):
            with self.assertRaisesRegex(cli.CommandInputError, "其他写者更改"):
                cli.update_batch(self.path, patch_path)
        self.assertEqual(self.path.read_bytes(), other_bytes)

    def test_cli_json_status_and_exit_codes_real_subprocess(self):
        self.base_tree()
        script = REPO_ROOT / "shared/scripts/module_architecture.py"
        environment = dict(os.environ, PYTHONUTF8="1")
        for arguments, expected_code, status in ((["check", "--architecture", str(self.path)], 0, "pass"),
                                                  (["route", "--architecture", str(self.path), "--module", "absent"], 2, "unknown"),
                                                  (["unknown-command"], 2, "unknown")):
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, str(script), *arguments], capture_output=True,
                                        text=True, encoding="utf-8", env=environment)
                self.assertEqual(result.returncode, expected_code, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], status)
                self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
