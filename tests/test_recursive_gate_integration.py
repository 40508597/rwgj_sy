"""Exercise recursive module sources through real validation and gate tools."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _archlib
import gate_check
import manage_state
import scan_code_drift
import validate_architecture


class RecursiveGateIntegration(unittest.TestCase):
    """The fixture has two branches and a grandchild with opaque source files."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix=".tmp-recursive-gate-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.architecture = self.root / "architecture.json"
        self.sources = {
            "root": "主入口.工程",
            "alpha": "模块甲/控制器.未知",
            "leaf": "模块甲/深层引擎/执行入口",
            "beta": "模块乙/资源.vendor-binary",
        }
        self.documents = {
            "root": "architecture.json",
            "alpha": "模块甲/architecture.json",
            "leaf": "模块甲/深层引擎/architecture.json",
            "beta": "模块乙/architecture.json",
        }
        self.names = {"root": "系统", "alpha": "控制模块", "leaf": "执行引擎", "beta": "资源模块"}
        self.duties = {key: f"负责{value}的明确边界" for key, value in self.names.items()}
        for module_id, relative in self.sources.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"fixture implementation {module_id}".encode("utf-8"))
        for module_id in self.sources:
            self.write(self.documents[module_id], self.module_document(module_id))
        root_data = self.read(self.documents["root"])
        # Keep the ordinary root architecture/completion contract in full.
        example = json.loads((PACKAGE / "shared/assets/example-architecture.json").read_text(encoding="utf-8"))
        example.update(root_data)
        example["专业能力索引"] = []
        example["功能树"] = [{"编号": "feature", "名称": "完整递归夹具", "架构落位": {"模块": list(self.sources)}}]
        example["模块树"] = [{"编号": "root", "名称": self.names["root"], "父模块": None, "子模块": []}]
        example["模块拓扑"] = {"节点": [{"编号": "root", "名称": self.names["root"]}],
                              "依赖图": [{"从": "leaf", "到": "beta", "说明": "跨枝读取资源"}]}
        example["测试责任矩阵"] = [{"模块": "root", "责任": "由本测试执行全部真实检查入口"}]
        example["架构切片"] = {"启用": False, "切片清单": []}
        example["验证证据"] = {name: [] for name in ("自动化测试", "架构校验", "浏览器验收", "截图", "手动检查", "未验证项")}
        example["验证证据"]["手动检查"] = ["测试夹具已在磁盘创建四个登记实现文件及模块架构"]
        example["上下文恢复点"] = {
            "当前任务": "递归模块验证", "当前阶段": "收尾验证", "继续位置": "各模块实际目录",
            "下一步": "执行真实检查入口", "已触碰文件": list(self.sources.values()),
            "用户明确约束": [], "剩余风险": [],
        }
        self.write("architecture.json", example)
        self.state = manage_state.create_initial_state("recursive fixture")
        for stage in self.state["stages"]:
            stage["status"] = "completed"
        self.save_state()

    def module_document(self, module_id):
        children = []
        if module_id == "root":
            children = [{"编号": child, "路径": self.documents[child], "职责": self.duties[child]}
                        for child in ("alpha", "beta")]
        elif module_id == "alpha":
            children = [{"编号": "leaf", "路径": "深层引擎/architecture.json", "职责": self.duties["leaf"]}]
        detail = {field: "本模块按职责边界记录" for field in validate_architecture.FALLBACK_MODULE_DETAIL_SUBFIELDS}
        detail.update({"上游依赖": [], "下游消费者": [], "模块号": module_id, "模块名": self.names[module_id], "职责": [self.duties[module_id]]})
        return {
            "模块路由": {"版本": 1, "编号": module_id, "名称": self.names[module_id],
                         "职责": self.duties[module_id], "子模块": children},
            "模块详情": {module_id: detail},
            "实现清单": {module_id: {"文件列表": [self.sources[module_id]], "依赖模块": ["beta"] if module_id == "leaf" else []}},
            "本地进度": {"当前阶段": "文件已创建", "恢复位置": self.sources[module_id]},
        }

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def read(self, relative):
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def change(self, module_id, mutate):
        data = self.read(self.documents[module_id])
        mutate(data)
        self.write(self.documents[module_id], data)

    def save_state(self):
        manage_state.save_state(self.root / "architecture/_state.json", self.state)

    def cli(self, script, *arguments):
        process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / script),
                                  *map(str, arguments), "--json"],
                                 capture_output=True, encoding="utf-8", timeout=30)
        try:
            result = json.loads(process.stdout)
        except ValueError:
            result = None
        return process.returncode, result, process.stderr

    def module_check(self):
        return self.cli("module_architecture.py", "check", "--architecture", self.architecture)

    def test_real_recursive_entrypoints_pass_and_inventory_excludes_all_module_sources(self):
        loaded_sources = set()
        data = _archlib.load_architecture_json(self.architecture, loaded_sources, project_root=self.root)
        self.assertEqual({record["编号"] for record in data["模块目录"]}, set(self.sources))
        self.assertEqual({path.relative_to(self.root).as_posix() for path in loaded_sources}, set(self.documents.values()))
        self.assertEqual(data["模块归属事实"]["leaf"]["本地进度"]["恢复位置"], self.sources["leaf"])
        drift = scan_code_drift.scan_code_drift(self.root, self.architecture,
                                              scan_code_drift.DEFAULT_EXTENSIONS, all_files=True)
        self.assertEqual(drift["声明但不存在"], [])
        self.assertEqual(drift["存在但未登记"], [])
        self.assertEqual(set(drift["已登记代码文件"]), set(self.sources.values()))
        self.assertEqual(self.cli("validate_architecture.py", self.architecture)[0], 0)
        code, checked, error = self.module_check()
        self.assertEqual(code, 0, (checked, error))
        self.assertEqual(checked["status"], "pass")
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json")
        self.assertIs(passed, True, stages)
        self.assertEqual(next(stage["status"] for stage in stages if stage["name"] == "模块树"), "pass")

    def test_grandchild_missing_opaque_source_fails_validator_drift_tree_and_gate(self):
        (self.root / self.sources["leaf"]).unlink()
        drift = scan_code_drift.scan_code_drift(self.root, self.architecture, {".py"}, explicit_extensions=True)
        self.assertEqual(drift["声明但不存在"], [self.sources["leaf"]])
        code, validated, _ = self.cli("validate_architecture.py", self.architecture)
        self.assertEqual(code, 1)
        self.assertTrue(any(self.sources["leaf"] in issue for issue in validated["错误"]))
        self.assertEqual(self.module_check()[0], 1)
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json")
        self.assertIs(passed, False)
        self.assertEqual({stage["name"]: stage["status"] for stage in stages}["代码漂移"], "fail")
        self.assertEqual({stage["name"]: stage["status"] for stage in stages}["模块树"], "fail")

    def test_module_entry_file_is_included_in_inventory_and_recovery_counts(self):
        def entry_only(data):
            data["实现清单"]["leaf"] = {"入口文件": self.sources["leaf"], "依赖模块": ["beta"]}
        self.change("leaf", entry_only)
        drift = scan_code_drift.scan_code_drift(self.root, self.architecture,
                                              scan_code_drift.DEFAULT_EXTENSIONS, all_files=True)
        self.assertIn(self.sources["leaf"], drift["已登记代码文件"])
        self.assertEqual(drift["存在但未登记"], [])
        self.assertEqual(gate_check._count_impl_files(self.root), 4)
        (self.root / self.sources["leaf"]).unlink()
        drift = scan_code_drift.scan_code_drift(self.root, self.architecture, {".py"})
        self.assertEqual(drift["声明但不存在"], [self.sources["leaf"]])
        self.assertIs(gate_check.run_gate(self.root, "architecture.json")[0], False)

    def test_hardlinked_architecture_cannot_be_registered_as_child_source(self):
        source = self.root / self.sources["leaf"]
        source.unlink()
        try:
            os.link(self.architecture, source)
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        self.assertTrue(os.path.samefile(self.architecture, source))
        self.assertEqual(self.module_check()[0], 1)
        self.assertNotEqual(self.cli("validate_architecture.py", self.architecture)[0], 0)
        self.assertEqual(self.cli("scan_code_drift.py", self.root, "--all-files")[0], 2)
        self.assertIsNot(gate_check.run_gate(self.root, "architecture.json")[0], True)

    def test_corrupt_grandchild_cannot_pass_completed_global_state(self):
        (self.root / self.documents["leaf"]).write_text("{broken", encoding="utf-8")
        self.assertEqual(self.cli("validate_architecture.py", self.architecture)[0], 2)
        self.assertEqual(self.cli("scan_code_drift.py", self.root, "--all-files")[0], 2)
        self.assertEqual(self.module_check()[0], 2)
        self.assertIsNone(gate_check.run_gate(self.root, "architecture.json")[0])

    def test_missing_child_route_target_never_passes(self):
        (self.root / self.documents["leaf"]).unlink()
        self.assertEqual(self.module_check()[0], 1)
        self.assertNotEqual(self.cli("validate_architecture.py", self.architecture)[0], 0)
        self.assertIsNot(gate_check.run_gate(self.root, "architecture.json")[0], True)

    def test_duplicate_route_and_wrong_child_ownership_are_blocked(self):
        original = self.read("architecture.json")
        duplicate = copy.deepcopy(original)
        duplicate["模块路由"]["子模块"].append(copy.deepcopy(duplicate["模块路由"]["子模块"][0]))
        self.write("architecture.json", duplicate)
        self.assertEqual(self.module_check()[0], 1)
        self.assertIsNot(gate_check.run_gate(self.root, "architecture.json")[0], True)
        self.write("architecture.json", original)
        self.change("alpha", lambda data: data["实现清单"]["alpha"]["文件列表"].append(self.sources["leaf"]))
        self.assertEqual(self.module_check()[0], 1)
        self.assertIsNot(gate_check.run_gate(self.root, "architecture.json")[0], True)

    def test_child_detail_baseline_is_checked_after_hydration(self):
        self.change("leaf", lambda data: data["模块详情"]["leaf"].pop("安全"))
        code, result, _ = self.cli("validate_architecture.py", self.architecture)
        self.assertEqual(code, 1)
        self.assertTrue(any("模块详情.leaf.安全" in issue for issue in result["错误"]))
        self.assertIs(gate_check.run_gate(self.root, "architecture.json")[0], False)

    def test_missing_child_manifest_is_not_hidden_by_other_modules(self):
        self.change("leaf", lambda data: data.pop("实现清单"))
        code, result, _ = self.cli("validate_architecture.py", self.architecture)
        self.assertEqual(code, 1)
        self.assertTrue(any("leaf" in issue and "实现清单" in issue for issue in result["错误"]))
        self.assertIs(gate_check.run_gate(self.root, "architecture.json")[0], False)

    def test_child_cannot_declare_another_modules_detail(self):
        self.change("leaf", lambda data: data["模块详情"].update({"beta": copy.deepcopy(data["模块详情"]["leaf"])}))
        self.assertEqual(self.module_check()[0], 1)
        self.assertIsNot(gate_check.run_gate(self.root, "architecture.json")[0], True)

    def test_topology_and_dependency_unknown_modules_are_hard_failures(self):
        for mutate in (
            lambda data: data["模块拓扑"]["节点"].append({"编号": "ghost", "名称": "未注册实体"}),
            lambda data: data["模块拓扑"]["依赖图"].append({"从": "leaf", "到": "ghost"}),
        ):
            with self.subTest(mutate=mutate):
                original = self.read("architecture.json")
                self.change("root", mutate)
                code, result, _ = self.cli("validate_architecture.py", self.architecture)
                self.assertEqual(code, 1, result)
                self.assertTrue(any("ghost" in issue for issue in result["错误"]))
                self.write("architecture.json", original)

    def test_cross_branch_dependency_is_valid_and_reverse_edge_still_forms_cycle(self):
        self.assertEqual(self.cli("validate_architecture.py", self.architecture)[0], 0)
        self.change("root", lambda data: data["模块拓扑"]["依赖图"].append({"从": "beta", "到": "leaf"}))
        code, result, _ = self.cli("validate_architecture.py", self.architecture)
        self.assertEqual(code, 1)
        self.assertTrue(any("有向环" in issue for issue in result["错误"]))
        self.assertIs(gate_check.run_gate(self.root, "architecture.json")[0], False)

    def test_manifest_dependency_cycle_blocks_real_validator_and_gate(self):
        self.change("root", lambda data: data["实现清单"]["root"].update({"依赖模块": ["leaf"]}))
        self.change("leaf", lambda data: data["实现清单"]["leaf"].update({"依赖模块": ["root"]}))
        self.assertEqual(self.module_check()[0], 1)
        code, result, _ = self.cli("validate_architecture.py", self.architecture)
        self.assertEqual(code, 1)
        self.assertTrue(any("有向环" in issue for issue in result["错误"]))
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json")
        self.assertIs(passed, False)
        self.assertEqual({stage["name"]: stage["status"] for stage in stages}["模块树"], "fail")

    def test_manifest_unknown_dependency_blocks_real_validator_and_gate(self):
        self.change("leaf", lambda data: data["实现清单"]["leaf"].update({"依赖模块": ["ghost"]}))
        self.assertEqual(self.module_check()[0], 1)
        code, result, _ = self.cli("validate_architecture.py", self.architecture)
        self.assertEqual(code, 1)
        self.assertTrue(any("ghost" in issue for issue in result["错误"]))
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json")
        self.assertIs(passed, False)
        self.assertEqual({stage["name"]: stage["status"] for stage in stages}["模块树"], "fail")

    def test_containment_does_not_invent_a_reverse_dependency(self):
        self.change("root", lambda data: data["模块拓扑"].update({"依赖图": []}))
        self.change("leaf", lambda data: data["实现清单"]["leaf"].update({"依赖模块": ["root"]}))
        self.assertEqual(self.module_check()[0], 0)
        self.assertEqual(self.cli("validate_architecture.py", self.architecture)[0], 0)
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json")
        self.assertIs(passed, True, stages)

    def test_unrouted_physical_module_is_not_treated_as_loaded(self):
        self.write("遗失模块/architecture.json", {"模块路由": {"版本": 1, "编号": "omitted", "名称": "遗漏", "职责": "遗漏事实", "子模块": []}})
        self.assertEqual(self.module_check()[0], 1)
        code, result, _ = self.cli("validate_architecture.py", self.architecture)
        self.assertEqual(code, 1)
        self.assertTrue(any("遗失模块/architecture.json" in issue for issue in result["错误"]))
        self.assertIs(gate_check.run_gate(self.root, "architecture.json")[0], False)

    def test_completed_modules_do_not_bypass_required_global_phases(self):
        self.state["stages"][0]["status"] = "pending"
        self.save_state()
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json")
        self.assertIs(passed, False)
        self.assertEqual({stage["name"]: stage["status"] for stage in stages}["进度状态"], "fail")

    def test_child_capability_declarations_cannot_hide_the_required_global_plan(self):
        declaration = [{"技能": "review", "调用状态": "已完成"}]
        for field in ("专业能力调用", "能力调用记录"):
            with self.subTest(field=field):
                self.change("leaf", lambda data: data.update({field: declaration}))
                self.assertEqual(self.module_check()[0], 1)
                self.assertIsNot(gate_check.run_gate(self.root, "architecture.json")[0], True)
                self.change("leaf", lambda data: data.pop(field))
                self.change("root", lambda data: data.update({field: declaration}))
                passed, _, stages = gate_check.run_gate(self.root, "architecture.json")
                self.assertIsNone(passed)
                self.assertEqual({stage["name"]: stage["status"] for stage in stages}["专业能力接入"], "unknown")
                self.change("root", lambda data: data.pop(field))

    def test_child_edit_invalidates_real_required_quality_receipt(self):
        from run_verification import run_verification
        command = [sys.executable, "-c", "print('recursive fixture receipt')"]
        receipt = run_verification(self.root, command, [self.sources["leaf"]], timeout=5)
        self.assertEqual(receipt["status"], "pass")
        self.write("architecture/quality/receipt.json", receipt)
        self.write("architecture/quality/facts.json", {"schema_version": 1, "modules": list(self.sources), "sources": []})
        self.write("architecture/quality/policy.json", {"schema_version": 1, "rules": [{
            "id": "recursive-test", "check": "execution", "required": True,
            "receipt": "architecture/quality/receipt.json", "inputs": [self.sources["leaf"]], "command": command,
        }]})
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json", quality_required=True)
        self.assertIs(passed, True, stages)
        (self.root / self.sources["leaf"]).write_bytes(b"modified after verification")
        passed, _, stages = gate_check.run_gate(self.root, "architecture.json", quality_required=True)
        self.assertIsNone(passed, stages)
        self.assertEqual({stage["name"]: stage["status"] for stage in stages}["通用质量"], "unknown")


if __name__ == "__main__":
    unittest.main()
