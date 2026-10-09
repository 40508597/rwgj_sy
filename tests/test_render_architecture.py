"""render_architecture.py 单元测试（纯函数渲染 + 三种格式端到端）"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import render_architecture as render  # noqa: E402

EXAMPLE = json.loads((REPO_ROOT / "shared/assets/example-architecture.json").read_text(encoding="utf-8"))


class TestDependencyFlow(unittest.TestCase):
    def test_flow_contains_nodes_and_edges(self):
        text = render.to_dependency_flow(EXAMPLE)
        self.assertIn("m_user.create", text)
        self.assertIn("m_database", text)
        self.assertIn("-->", text)  # 依赖边渲染

    def test_flow_groups_by_layer(self):
        text = render.to_dependency_flow(EXAMPLE)
        self.assertIn('subgraph "基础设施"', text)
        self.assertIn('subgraph "业务"', text)

    def test_flow_empty(self):
        self.assertIn("无模块拓扑数据", render.to_dependency_flow({}))

    def test_flow_max_nodes_pages_without_dropping_nodes(self):
        text = render.to_dependency_flow(EXAMPLE, max_nodes=2)
        self.assertIn("分图 4 / 4", text)
        for node in EXAMPLE["模块拓扑"]["节点"]:
            self.assertIn(node["编号"], text)
        self.assertIn("完整依赖关系", text)


class TestFunctionTree(unittest.TestCase):
    def test_tree_contains_root_and_leaf_marks(self):
        text = render.to_function_tree(EXAMPLE)
        self.assertIn("| f1 | f1.1 |", text)
        self.assertIn("-->", text)
        self.assertIn("✔", text)  # 叶子可验收标记

    def test_tree_empty(self):
        self.assertIn("无功能树数据", render.to_function_tree({}))


class TestProgressTable(unittest.TestCase):
    def test_table_from_state(self):
        state = {"completion": {"percentage": 50, "required_completed": 5, "required_total": 9},
                 "stages": [{"id": "需求理解", "status": "completed", "description": "d"},
                            {"id": "功能树", "status": "in_progress", "description": "d"}]}
        text = render.to_progress_table(state)
        self.assertIn("50%", text)
        self.assertIn("✅ 已完成", text)
        self.assertIn("⏳ 进行中", text)

    def test_table_without_state(self):
        self.assertIn("状态文件不存在", render.to_progress_table(None))


class TestModuleSummary(unittest.TestCase):
    def test_summary_contains_fill_rate(self):
        text = render.to_module_summary(EXAMPLE)
        self.assertIn("14/14", text)  # example 模块底线全填
        self.assertIn("职责摘要", text)


class TestMarkdownReport(unittest.TestCase):
    def test_report_sections(self):
        text = render.render_markdown_report(EXAMPLE, None, ["红线A"], ["警告B"], 60)
        for section in ("模块依赖图", "功能树", "架构进度", "模块摘要", "数据拓扑", "质量问题"):
            self.assertIn(section, text)
        self.assertIn("红线A", text)
        self.assertIn("警告B", text)
        self.assertIn("单向渲染", text)  # 铁律声明

    def test_report_clean(self):
        text = render.render_markdown_report(EXAMPLE, None, [], [], 60)
        self.assertIn("无质量红线", text)


class TestJsonOutput(unittest.TestCase):
    def test_payload_structure(self):
        payload = render._build_json_payload(EXAMPLE, None, ["e"], ["w"])
        self.assertIn("模块", payload)
        self.assertIn("依赖边", payload)
        self.assertIn("功能树", payload)
        self.assertEqual(payload["质量问题"], {"错误": ["e"], "警告": ["w"]})
        self.assertIn("单向渲染", payload["元信息"])
        self.assertIn("真相源永远在", payload["元信息"]["单向渲染"])


class TestMainEndToEnd(unittest.TestCase):
    def _write_example(self, td: str) -> Path:
        p = Path(td) / "arch.json"
        p.write_text(json.dumps(EXAMPLE, ensure_ascii=False), encoding="utf-8")
        return p

    def test_md_to_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_example(td)
            self.assertEqual(render.main([str(p)]), 0)

    def test_html_to_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_example(td)
            out = Path(td) / "arch.html"
            self.assertEqual(render.main([str(p), "--format", "html", "--output", str(out)]), 0)
            html = out.read_text(encoding="utf-8")
            self.assertIn("<html", html)
            self.assertIn('id="project-data" type="application/json"', html)
            payload = json.loads(html.split('id="project-data" type="application/json">', 1)[1].split('</script>', 1)[0])
            self.assertEqual(payload["top_count"], len(EXAMPLE))
            self.assertTrue(payload["physical_mappings"])

    def test_html_report_view_remains_available(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_example(td)
            out = Path(td) / "report.html"
            self.assertEqual(render.main([str(p), "--format", "html", "--html-view", "report", "--output", str(out)]), 0)
            self.assertIn("const DATA = ", out.read_text(encoding="utf-8"))

    def test_json_to_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_example(td)
            out = Path(td) / "arch-view.json"
            self.assertEqual(render.main([str(p), "--format", "json", "--output", str(out)]), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(data["模块"]), 7)

    def test_output_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_example(td)
            before = p.read_bytes()
            self.assertEqual(render.main([str(p), "--format", "json", "--output", str(p)]), 2)
            self.assertEqual(p.read_bytes(), before)

    def test_missing_file_returns_2(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(render.main([str(Path(td) / "nope.json")]), 2)

    def test_unreadable_snapshot_is_reported_without_creating_output(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_example(td)
            out = Path(td) / "view.json"
            with patch.object(Path, "read_bytes", side_effect=PermissionError("snapshot input denied")):
                self.assertEqual(render.main([str(p), "--format", "json", "--output", str(out)]), 2)
            self.assertFalse(out.exists())

    def test_source_created_during_render_invalidates_output(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_example(td)
            source = Path(td) / "src/user/schema.py"
            out = Path(td) / "view.json"
            original = render.render_json_output
            def render_and_create(*args, **kwargs):
                text = original(*args, **kwargs)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("# arrived during render\n", encoding="utf-8")
                return text
            with patch.object(render, "render_json_output", side_effect=render_and_create):
                self.assertEqual(render.main([str(p), "--format", "json", "--output", str(out)]), 2)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
