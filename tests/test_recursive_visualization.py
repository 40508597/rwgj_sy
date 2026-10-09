"""Recursive module containment and lossless visual reading contracts."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared" / "scripts"))
from _architecture_visual import build_visual_model
from render_architecture import _edges_of, to_dependency_flow


def fixture():
    records = [
        {"编号": "project", "父模块": None, "名称": "总体", "目录": ".",
         "路径": "architecture.json", "职责": "系统约束与入口", "子模块": ["orders", "payments"]},
        {"编号": "orders", "父模块": "project", "名称": "订单", "目录": "订单",
         "路径": "订单/architecture.json", "职责": "订单生命周期", "子模块": ["pricing"]},
        {"编号": "pricing", "父模块": "orders", "名称": "定价", "目录": "订单/定价",
         "路径": "订单/定价/architecture.json", "职责": "计算金额", "子模块": []},
        {"编号": "payments", "父模块": "project", "名称": "支付", "目录": "支付",
         "路径": "支付/architecture.json", "职责": "支付结果", "子模块": []},
    ]
    return {"项目": {"名称": "递归项目"}, "模块目录": records,
            "模块详情": {r["编号"]: {"职责": r["职责"], "状态机": "以实现为准"} for r in records},
            "模块拓扑": {"节点": [{"编号": r["编号"], "名称": r["名称"]} for r in records],
                         "依赖图": [{"从": "payments", "到": "pricing", "说明": "消费金额契约"}]},
            "模块归属事实": {"pricing": {"任意业务字段": {"单位": "分", "边界": [0, 100000]}}}}


class RecursiveVisualContracts(unittest.TestCase):
    def assert_reachable(self, model):
        seen = set()
        pending = [0]
        while pending:
            nid = pending.pop()
            self.assertNotIn(nid, seen)
            seen.add(nid)
            pending.extend(model["nodes"][nid]["c"])
        self.assertEqual(seen, set(range(len(model["nodes"]))))

    def module_nodes(self, model):
        return {n["entity"]: i for i, n in enumerate(model["nodes"])
                if (n.get("p") or "").startswith("/模块详情/") and n.get("entity")}

    def test_recursive_modules_form_reading_tree_and_dependency_stays_separate(self):
        data = fixture()
        before = copy.deepcopy(data)
        model = build_visual_model(data)
        nodes = self.module_nodes(model)
        self.assertEqual(model["nodes"][nodes["orders"]]["parent"], nodes["project"])
        self.assertEqual(model["nodes"][nodes["pricing"]]["parent"], nodes["orders"])
        self.assertEqual(model["nodes"][nodes["payments"]]["parent"], nodes["project"])
        relations = {(r["a"], r["b"], r["kind"]) for r in model["relations"]}
        self.assertIn((nodes["orders"], nodes["pricing"], "模块包含"), relations)
        self.assertTrue(any(a == nodes["payments"] and b == nodes["pricing"] and k != "模块包含"
                            for a, b, k in relations))
        self.assertFalse(any(n.get("code") == "ambiguous_id" for n in model["diagnostics"]))
        self.assertEqual(data, before)
        self.assert_reachable(model)

    def test_custom_module_values_remain_present(self):
        model = build_visual_model(fixture())
        raw = {n["p"]: n for n in model["nodes"][:model["source_node_count"]]}
        self.assertEqual(raw["/模块归属事实/pricing/任意业务字段/单位"]["v"], "分")
        self.assertEqual(raw["/模块目录/2/路径"]["v"], "订单/定价/architecture.json")
        self.assert_reachable(model)

    def test_route_only_modules_remain_visible_without_inventing_details(self):
        data = fixture()
        del data["模块详情"]
        del data["模块拓扑"]
        model = build_visual_model(data)
        self.assertEqual(len([n for n in model["nodes"] if n.get("role") == "模块"]), 4)
        self.assertEqual(len([r for r in model["relations"] if r["kind"] == "模块包含"]), 3)
        self.assert_reachable(model)

    def test_invalid_containment_cycle_is_visible_without_losing_nodes(self):
        data = fixture()
        data["模块目录"][0]["父模块"] = "pricing"
        model = build_visual_model(data)
        self.assertTrue(any(n.get("code") == "module_parent_cycle" for n in model["diagnostics"]))
        self.assert_reachable(model)

    def test_manifest_dependency_is_visible_and_keeps_declaration_source(self):
        data = fixture()
        data["模块拓扑"]["依赖图"] = []
        data["实现清单"] = {"payments": {"依赖模块": ["pricing"]}}
        model = build_visual_model(data)
        nodes = self.module_nodes(model)
        relation = next(r for r in model["relations"] if r["kind"] == "依赖")
        self.assertEqual((relation["a"], relation["b"]), (nodes["payments"], nodes["pricing"]))
        self.assertIn("/实现清单/payments/依赖模块/0", relation["sources"])
        self.assertEqual([(e["从"], e["到"]) for e in _edges_of(data)], [("payments", "pricing")])
        self.assertIn("1 条依赖", to_dependency_flow(data))
        self.assert_reachable(model)

    def test_duplicate_manifest_dependency_merges_sources_without_extra_edge(self):
        data = fixture()
        data["实现清单"] = {"payments": {"依赖模块": ["pricing"]}}
        model = build_visual_model(data)
        dependencies = [r for r in model["relations"] if r["kind"] == "依赖"]
        self.assertEqual(len(dependencies), 1)
        self.assertEqual(set(dependencies[0]["sources"]), {
            "/模块拓扑/依赖图/0", "/实现清单/payments/依赖模块/0"})
        self.assertEqual(len(_edges_of(data)), 1)


if __name__ == "__main__":
    unittest.main()
