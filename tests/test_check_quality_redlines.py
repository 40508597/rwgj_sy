"""check_quality_redlines.py 单元测试（质量红线启发式）"""

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import check_quality_redlines as redlines  # noqa: E402

EXAMPLE = json.loads((REPO_ROOT / "shared/assets/example-architecture.json").read_text(encoding="utf-8"))


class TestRedlines(unittest.TestCase):
    def test_example_passes(self):
        """完整示例不应触发红线（验证锚点与 verify-all 一致）。"""
        errors, warnings, _ = redlines.check_redlines(EXAMPLE)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_action_leaf_without_exception_path(self):
        """操作类叶子节点缺异常路径 → 红线。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["功能树"].append({
            "编号": "f9", "名称": "删除用户", "类型": "功能", "分类": "核心功能",
            "子节点": [], "架构落位": {"模块": ["m_user"]},
        })
        errors, _, _ = redlines.check_redlines(data)
        self.assertTrue(any("异常路径" in e for e in errors))

    def test_bulk_feature_without_safety_signals(self):
        """导出类功能缺安全与可靠性信号 → 红线。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["功能树"].append({
            "编号": "f9", "名称": "导出数据", "类型": "功能", "分类": "核心功能",
            "子节点": [], "说明": "一键导出", "异常路径": ["文件损坏"],
            "架构落位": {"模块": ["m_user"]},
        })
        errors, _, _ = redlines.check_redlines(data)
        self.assertTrue(any("安全与可靠性信号" in e for e in errors))

    def test_leaf_without_acceptance_criteria_warns(self):
        """叶子节点缺验收标准/测试落位 → 警告（不阻塞）。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["功能树"].append({
            "编号": "f9", "名称": "查询日志", "类型": "功能", "分类": "核心功能",
            "子节点": [], "异常路径": ["无日志"],
        })
        errors, warnings, _ = redlines.check_redlines(data)
        self.assertEqual(errors, [])
        self.assertTrue(any("验收标准" in w for w in warnings))
        self.assertTrue(any("架构落位.测试" in w for w in warnings))

    def test_hollow_module_warns(self):
        """模块详情填充率 < 50% → 空壳模块警告。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["模块详情"]["m_hollow"] = {"职责": "x"}
        _, warnings, _ = redlines.check_redlines(data)
        self.assertTrue(any("空壳模块" in w for w in warnings))

    def test_state_machine_conflict_warns(self):
        """状态机声明「不适用」但数据读写含状态流转信号 → 警告。"""
        data = json.loads(json.dumps(EXAMPLE))
        data["模块详情"]["m_conflict"] = {
            "职责": "y", "状态机": "不适用",
            "数据读写责任": [{"表名": "orders", "操作": ["update"], "说明": "订单状态流转"}],
        }
        _, warnings, _ = redlines.check_redlines(data)
        self.assertTrue(any("状态流转信号" in w for w in warnings))


class TestMainExitCode(unittest.TestCase):
    def test_main_returns_1_on_redline(self):
        data = json.loads(json.dumps(EXAMPLE))
        data["功能树"].append({"编号": "f9", "名称": "删除用户", "子节点": [],
                               "架构落位": {"模块": []}})
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "arch.json"
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(redlines.main([str(p)]), 1)

    def test_main_returns_0_on_clean(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "arch.json"
            p.write_text(json.dumps(EXAMPLE, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(redlines.main([str(p)]), 0)


def make_redline_fixture() -> dict:
    """example + 「导出数据」偷工减料节点（触发 2 红线 + 2 警告）。"""
    data = json.loads(json.dumps(EXAMPLE))
    data["功能树"].append({
        "编号": "f9", "名称": "导出数据", "类型": "功能", "分类": "核心功能",
        "子节点": [], "说明": "一键导出", "架构落位": {"模块": ["m_user"]},
    })
    return data


class TestApplyExemptions(unittest.TestCase):
    def test_exempt_filters_matching_items(self):
        data = make_redline_fixture()
        errors, warnings, _ = redlines.check_redlines(data)
        self.assertTrue(errors)  # 前提：确实有红线
        errors2, warnings2, exempted = redlines.apply_exemptions(errors, warnings, ["功能树.导出数据"])
        self.assertEqual(errors2, [])
        self.assertEqual(len(exempted), len(errors) + len(warnings))

    def test_exempt_must_match_exact_path(self):
        data = make_redline_fixture()
        errors, warnings, _ = redlines.check_redlines(data)
        errors2, _, exempted = redlines.apply_exemptions(errors, warnings, ["功能树.导出"])
        self.assertEqual(errors2, errors)  # 不匹配，红线保留
        self.assertEqual(exempted, [])

    def test_ad_hoc_exemption_is_unknown_even_with_reason(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "arch.json"
            p.write_text(json.dumps(make_redline_fixture(), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(redlines.main([str(p)]), 1)
            self.assertEqual(redlines.main(
                [str(p), "--exempt", "功能树.导出数据", "--exempt-reason", "内部工具"]), 2)

    def test_ad_hoc_exemption_without_reason_is_unknown(self):
        """临时豁免不能替代持久化语义复核证据。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "arch.json"
            p.write_text(json.dumps(make_redline_fixture(), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(redlines.main([str(p), "--exempt", "功能树.导出数据"]), 2)



class TestFeatureScope(unittest.TestCase):
    def node(self, **updates):
        return {"编号": "f_future", "名称": "批量导出", "子节点": [],
                "状态": "延期", "取舍理由": "当前批次只交付查询，导出等待下一批次数据契约", **updates}

    def evaluate(self, nodes, **fields):
        with tempfile.TemporaryDirectory() as td:
            return redlines.evaluate_redlines({"功能树": nodes, **fields}, Path(td))

    def test_all_explicit_candidate_dispositions_preserve_panorama_without_implementation_errors(self):
        for status in sorted(redlines.CANDIDATE_STATUSES):
            with self.subTest(status=status):
                data = {"功能树": [self.node(状态=status)]}
                before = copy.deepcopy(data)
                with tempfile.TemporaryDirectory() as td:
                    result = redlines.evaluate_redlines(data, Path(td))
                self.assertEqual((result["status"], result["code"]), ("pass", 0))
                self.assertEqual(result["错误"], [])
                self.assertEqual(result["警告"], [])
                self.assertTrue(any("非纳入 1" in item for item in result["提示"]))
                self.assertTrue(any("1 个节点" in item for item in result["提示"]))
                self.assertEqual(data, before)

    def test_bare_status_is_not_an_exemption(self):
        for status in redlines.CANDIDATE_STATUSES:
            node = self.node(状态=status)
            node.pop("取舍理由")
            result = self.evaluate([node])
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("取舍理由" in item for item in result["错误"]))
            self.assertTrue(any("异常路径" in item for item in result["错误"]))

    def test_optional_scope_can_defer_confirmed_design_without_hiding_it(self):
        result = self.evaluate([self.node(状态="已确认", 本轮范围={
            "结论": "不纳入", "理由": "当前只交付查询，已确认导出排在下个实施批次"})])
        self.assertEqual((result["status"], result["code"]), ("pass", 0))

    def test_missing_or_unrecognized_status_stays_strict(self):
        for status in (None, "custom-progress", [], 7):
            node = self.node(状态=status)
            if status is None:
                node.pop("状态")
            result = self.evaluate([node])
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("异常路径" in item for item in result["错误"]))

    def test_invalid_scope_or_status_cannot_bypass(self):
        scopes = [None, [], {"结论": False, "理由": "推迟交付"},
                  {"结论": "跳过", "理由": "推迟交付"},
                  {"结论": "不纳入", "理由": ""},
                  {"结论": "不纳入", "理由": ["推迟交付"]},
                  {"结论": "不纳入", "理由": "延期"},
                  {"结论": "不纳入", "理由": "__待填__"},
                  {"结论": "不纳入", "理由": "推迟交付", "随意": True}]
        for scope in scopes:
            with self.subTest(scope=scope):
                result = self.evaluate([self.node(本轮范围=scope)])
                self.assertEqual(result["status"], "fail")
                self.assertTrue(any("本轮范围" in item for item in result["错误"]))
                self.assertTrue(any("异常路径" in item for item in result["错误"]))
        result = self.evaluate([self.node(状态=[], 本轮范围={"结论": "纳入", "理由": "当前必须交付"})])
        self.assertEqual(result["status"], "fail")

    def test_candidate_status_and_explicit_inclusion_conflict(self):
        result = self.evaluate([self.node(本轮范围={"结论": "纳入", "理由": "当前必须交付"})])
        self.assertTrue(any("矛盾" in item for item in result["错误"]))
        self.assertTrue(any("异常路径" in item for item in result["错误"]))

    def test_implemented_states_cannot_be_deferred_by_scope_only(self):
        for status in redlines.IMPLEMENTED_STATUSES:
            result = self.evaluate([self.node(状态=status, 本轮范围={
                "结论": "不纳入", "理由": "后续批次再整理本功能"})])
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("已有实施证据" in item for item in result["错误"]))
            self.assertTrue(any("安全与可靠性信号" in item for item in result["错误"]))

    def test_actual_landing_cannot_hide_behind_candidate_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            node = self.node(架构落位={"模块": ["m_export"], "文件": ["export.custom-source"]})
            data = {"功能树": [node]}
            self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "pass")
            (root / "export.custom-source").write_text("actual implementation", encoding="utf-8")
            result = redlines.evaluate_redlines(data, root)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("已有实施证据" in item for item in result["错误"]))
        # Without a filesystem context, nonempty landing files stay conservative.
        self.assertTrue(redlines.check_redlines(data)[0])

    def test_manifest_link_and_actual_or_realized_files_keep_strict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = {"功能树": [self.node()], "模块详情": {
                "m_export": {"所属功能树节点": ["f_future"]}}, "实现清单": {
                "m_export": {"文件列表": [{"路径": "export.source", "状态": "计划中"}]}}}
            self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "pass")
            (root / "export.source").write_text("actual implementation", encoding="utf-8")
            self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "fail")
            (root / "export.source").unlink()
            data["实现清单"]["m_export"]["文件列表"][0]["状态"] = "已完成"
            self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "fail")

    def test_single_string_references_and_display_keys_preserve_realized_ownership(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "export.any-language").write_text("actual implementation", encoding="utf-8")
            for references in ("f_future", ["f_future"]):
                data = {"功能树": [self.node()], "模块详情": {
                    "导出显示名": {"模块编号": "m_export", "所属功能树节点": references}},
                    "实现清单": {"实现显示名": {"模块编号": "m_export", "文件列表": "export.any-language"}}}
                self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "fail")
            data = {"功能树": [self.node()], "实现清单": {
                "m_export": {"所属功能树节点": "f_future", "文件列表": "export.any-language"}}}
            self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "fail")
            data = {"功能树": [self.node(架构落位={"文件": "export.any-language"})]}
            self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "fail")

    def test_both_manifest_file_aliases_check_actual_and_realized_candidate_files(self):
        for field in ("文件列表", "文件"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                path = root / "export.any-language"
                record = {"路径": path.name, "状态": "计划中"}
                data = {"功能树": [self.node()], "模块详情": {
                    "m_export": {"所属功能树节点": ["f_future"]}}, "实现清单": {
                    "m_export": {field: [record]}}}
                self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "pass")
                path.mkdir()
                self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "pass")
                path.rmdir()
                path.write_text("actual implementation", encoding="utf-8")
                result = redlines.evaluate_redlines(data, root)
                self.assertEqual(result["status"], "fail")
                self.assertTrue(any("已有实施证据" in item for item in result["错误"]))
                self.assertTrue(any("异常路径" in item for item in result["错误"]))
                path.unlink()
                record["状态"] = "已实现"
                self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "fail")

    def test_recursive_entry_file_without_repeated_file_list_keeps_candidate_strict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "entry-without-suffix"
            data = {"功能树": [self.node()], "模块详情": {
                "m_export": {"所属功能树节点": ["f_future"]}}, "实现清单": {
                "m_export": {"文件列表": [], "入口文件": path.name}}}
            data["模块路由"] = {"版本": 1, "编号": "m_export", "名称": "导出",
                              "职责": "承担导出行为", "子模块": []}
            architecture = root / "architecture.json"
            architecture.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            def evaluate():
                loaded = redlines._archlib.load_architecture_json(architecture, project_root=root)
                self.assertEqual(loaded["模块目录"][0]["文件"], [path.name])
                return redlines.evaluate_redlines(loaded, root)

            self.assertEqual(evaluate()["status"], "pass")
            path.mkdir()
            self.assertEqual(evaluate()["status"], "pass")
            path.rmdir()
            path.write_text("actual entry implementation", encoding="utf-8")
            result = evaluate()
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("已有实施证据" in item for item in result["错误"]))
            self.assertTrue(any("安全与可靠性信号" in item for item in result["错误"]))
            path.unlink()
            self.assertEqual(evaluate()["status"], "pass")

    def test_file_alias_with_confirmed_deferred_scope_and_display_identity_keeps_strict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "implemented-source"
            data = {"功能树": [self.node(状态="已确认", 本轮范围={
                "结论": "不纳入", "理由": "当前批次先治理查询，导出留到下一批次"})],
                "模块详情": {"显示名": {"模块编号": "m_export", "所属功能树节点": "f_future"}},
                "实现清单": {"清单显示名": {"模块编号": "m_export", "文件": [path.name]}}}
            self.assertEqual(redlines.evaluate_redlines(data, root)["status"], "pass")
            path.write_text("actual implementation", encoding="utf-8")
            result = redlines.evaluate_redlines(data, root)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("已有实施证据" in item for item in result["错误"]))

    def test_malformed_landing_is_not_a_candidate_escape(self):
        for landing in (False, "module", {"文件": False}, {"文件": [""]}):
            result = self.evaluate([self.node(架构落位=landing)])
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("证据检查失败" in item for item in result["错误"]))

    def test_explicit_implementation_evidence_keeps_strict(self):
        result = self.evaluate([self.node(实施证据="tests/export.log 显示当前导出命令已运行")])
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("已有实施证据" in item for item in result["错误"]))

    def test_nested_inheritance_and_explicit_child_inclusion(self):
        child = {"编号": "f_child", "名称": "批量导出", "子节点": []}
        parent = self.node(编号="f_parent", 名称="报表候选", 子节点=[child])
        result = self.evaluate([parent])
        self.assertEqual(result["status"], "pass")
        self.assertTrue(any("非纳入 2" in item for item in result["提示"]))
        child["本轮范围"] = {"结论": "纳入", "理由": "当前批次仅实现这个子能力"}
        result = self.evaluate([parent])
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("异常路径" in item for item in result["错误"]))
        child.pop("本轮范围")
        child["状态"] = "已确认"
        self.assertEqual(self.evaluate([parent])["status"], "fail")

    def test_flat_references_and_parent_links_inherit_independent_of_order(self):
        child = {"编号": "f_child", "名称": "批量导出", "子节点": [], "父节点": "f_parent"}
        parent = self.node(编号="f_parent", 名称="报表候选", 子节点=["f_child"])
        self.assertEqual(self.evaluate([child, parent])["status"], "pass")
        child["状态"] = "已确认"
        self.assertEqual(self.evaluate([child, parent])["status"], "fail")

    def test_duplicate_ids_and_bad_links_fail_without_scope_escape(self):
        fixtures = [
            [self.node(), self.node()],
            [self.node(父节点="missing")],
            [self.node(子节点=["missing"])],
            [self.node(编号=[])],
            [self.node(子节点={})],
            [self.node(子节点=[False])],
        ]
        for nodes in fixtures:
            with self.subTest(nodes=nodes):
                result = self.evaluate(nodes)
                self.assertEqual(result["status"], "fail")
                self.assertTrue(result["错误"])

    def test_parent_cycles_and_conflicts_stay_strict(self):
        a = self.node(编号="a", 父节点="b")
        b = self.node(编号="b", 父节点="a")
        self.assertEqual(self.evaluate([a, b])["status"], "fail")
        a = self.node(编号="a", 子节点=["c"])
        b = self.node(编号="b", 子节点=["c"])
        c = self.node(编号="c")
        result = self.evaluate([a, b, c])
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("多个父节点" in item for item in result["错误"]))

    def test_inherited_scope_does_not_hide_implemented_child(self):
        child = {"编号": "f_child", "名称": "批量导出", "子节点": [],
                 "实施证据": "当前版本导出实际运行记录"}
        parent = self.node(编号="f_parent", 名称="报表候选", 子节点=[child])
        result = self.evaluate([parent])
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("已有实施证据" in item for item in result["错误"]))

    def test_file_alias_actual_candidate_fails_both_cli_and_gate(self):
        import gate_check
        import manage_state
        from scan_code_drift import collect_declared_files
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = copy.deepcopy(EXAMPLE)
            record = data["实现清单"]["m_user"]
            record["文件"] = record.pop("文件列表")
            data["模块详情"]["m_user"]["所属功能树节点"].append("f_future")
            data["功能树"].append(self.node())
            files = sorted(collect_declared_files(data, root))
            for rel in files:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("pass\n", encoding="utf-8")
            data["上下文恢复点"]["当前阶段"] = "收尾验证"
            data["上下文恢复点"]["已触碰文件"] = files
            arch = root / "architecture.json"
            arch.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            state = manage_state.create_initial_state("file-alias-scope-integration")
            for stage in state["stages"]:
                stage["status"] = "completed"
            (root / "architecture").mkdir()
            (root / "architecture/_state.json").write_text(json.dumps(state), encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                cli_code = redlines.main([str(arch), "--json"])
            cli = json.loads(stream.getvalue())
            verdict, _, stages = gate_check.run_gate(root, "architecture.json")
            redline_stage = next(item for item in stages if item["name"] == "质量红线")
            self.assertEqual((cli_code, cli["status"]), (1, "fail"))
            self.assertTrue(any("已有实施证据" in item for item in cli["错误"]))
            self.assertEqual(redline_stage["status"], "fail")
            self.assertFalse(verdict)

    def test_actual_cli_and_gate_share_current_scope_verdict(self):
        import gate_check
        import manage_state
        from scan_code_drift import collect_declared_files
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = copy.deepcopy(EXAMPLE)
            files = sorted(collect_declared_files(data, root))
            for rel in files:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("pass\n", encoding="utf-8")
            data["上下文恢复点"]["当前阶段"] = "收尾验证"
            data["上下文恢复点"]["已触碰文件"] = files
            node = self.node(本轮范围={"结论": "不纳入", "理由": "用户安排导出在下一交付批次"})
            data["功能树"].append(node)
            arch = root / "architecture.json"
            state = manage_state.create_initial_state("scope-integration")
            for stage in state["stages"]:
                stage["status"] = "completed"
            manage_state.save_state(root / "architecture/_state.json", state)
            for expected, expected_code in (("pass", 0), ("fail", 1)):
                arch.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    cli_code = redlines.main([str(arch), "--json"])
                cli = json.loads(stream.getvalue())
                verdict, _, stages = gate_check.run_gate(root, "architecture.json")
                redline_stage = next(item for item in stages if item["name"] == "质量红线")
                self.assertEqual((cli_code, cli["status"]), (expected_code, expected))
                self.assertEqual(redline_stage["status"], expected)
                self.assertEqual(verdict, expected == "pass")
                node["状态"] = "已确认"
                node["本轮范围"] = {"结论": "纳入", "理由": "用户已将导出纳入当前批次"}


if __name__ == "__main__":
    unittest.main()
