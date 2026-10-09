"""Regression contracts for complete, readable architecture-derived views."""
from __future__ import annotations

import copy
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
import render_architecture as render  # noqa: E402
from _architecture_core import ArchitectureView, declared_dependencies  # noqa: E402

EXAMPLE_PATH = REPO_ROOT / "shared/assets/example-architecture.json"
EXAMPLE = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
SAFE_ALIAS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MERMAID = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
DECLARATION = re.compile(r'^\s*(\S+)\s*\[\s*"([^"\n]*)"\s*\]', re.MULTILINE)


def html_payload(document: str) -> dict:
    assignment = re.search(r"\b(?:const|let|var)\s+DATA\s*=\s*", document)
    if assignment is None:
        raise AssertionError("standalone HTML must embed its JSON data")
    payload, _ = json.JSONDecoder().raw_decode(document[assignment.end():])
    return payload


class StaticText(HTMLParser):
    """Ignore script/style text so payload keys cannot impersonate a heading."""

    def __init__(self):
        super().__init__()
        self.suppressed = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.suppressed += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.suppressed = max(0, self.suppressed - 1)

    def handle_data(self, value):
        if not self.suppressed:
            self.parts.append(value)


class HumanViewContracts(unittest.TestCase):
    def assert_declarations(self, text, names, *, page_limit):
        blocks = MERMAID.findall(text)
        self.assertTrue(blocks, "a human graph view must contain diagrams")
        labels = []
        for block in blocks:
            declarations = DECLARATION.findall(block)
            self.assertLessEqual(len(declarations), page_limit)
            for alias, label in declarations:
                self.assertRegex(alias, SAFE_ALIAS)
                labels.append(html.unescape(label))
        for name in names:
            self.assertEqual(sum(name in label for label in labels), 1,
                             f"{name!r} must have one explicit node declaration")

    def module_fixture(self):
        nodes = [{"编号": f"module-{i}", "名称": f"模块名称{i}", "层级": "业务"}
                 for i in range(5)]
        edges = [
            {"从": "module-0", "到": "module-4", "说明": "跨页读取配置"},
            {"从": "module-3", "到": "module-1", "说明": "跨页调用校验"},
            {"从": "module-1", "到": "module-0", "说明": "页内记录审计"},
        ]
        return {"项目": {"名称": "完整阅读回归"},
                "模块拓扑": {"节点": nodes, "依赖图": edges}}

    def new_e_fixture(self):
        """Minimal real-project shapes, without loading a developer's checkout."""
        canvas_ids = [
            "m_ide_canvas_analysis", "m_ide_canvas_core", "m_ide_canvas_declaration_flags",
            "m_ide_canvas_flow", "m_ide_canvas_fold_persistence", "m_ide_canvas_input",
            "m_ide_canvas_view",
        ]
        topology_ids = ["m_frontend_lexer", "m_frontend_parser"]
        return {
            "项目": {"名称": "新E格式最小夹具", "类型": "桌面IDE+编译器",
                     "语言": "Python / TypeScript / JavaScript / 中文DSL"},
            "模块拓扑": {
                "节点": [
                    {"编号": "m_frontend_lexer", "名称": "词法模块", "层": "前端",
                     "文件": ["前端/词法.py"]},
                    {"编号": "m_frontend_parser", "名称": "语法模块", "层": "前端",
                     "文件": ["前端/语法.py"]},
                ],
                "依赖图": [{"从": "m_frontend_parser", "到": "m_frontend_lexer",
                            "原声明": "m_frontend_parser → m_frontend_lexer"}],
            },
            "模块树": [
                {"编号": "group_frontend", "名称": "前端（语言核心）", "层": "前端",
                 "模块": topology_ids},
                {"编号": "group_canvas", "名称": "IDE Canvas", "层": "IDE新前端",
                 "模块": canvas_ids},
            ],
            # Real details are keyed by module ID and lack a 模块编号 field.
            "模块详情": {identifier: {"职责": ["保留该模块真实职责"],
                                       "非职责": ["不扩大编译器范围"],
                                       "数据读写责任": ["按实体约定保持源码数据"],
                                       "测试责任": ["对应生产入口回归"]}
                         for identifier in topology_ids + canvas_ids},
            "接口契约": {"词法模块.切分": {
                "提供方": "m_frontend_lexer", "消费方": ["m_frontend_parser"],
                "参数": [{"名": "源码", "类型": "文本型", "必填": True}],
                "返回": "记号序列", "可能异常": ["编码解码失败"], "幂等": True,
            }},
            "实现清单": {identifier: {"文件列表": [f"IDE/{identifier}.ts"], "状态": "计划中"}
                         for identifier in canvas_ids},
            "测试责任矩阵": [{"模块": "m_frontend_lexer", "单元测试": "需要",
                              "集成测试": "需要", "E2E测试": "不需要", "性能测试": "需要",
                              "安全测试": "不需要", "测试覆盖率目标": "关键分支 100%"}],
            "数据拓扑": [{
                "编号": "data_source", "名称": "源码文本", "存储介质": "文件（工程目录内）",
                "说明": "保留原始源码字节约定", "路径约定": ["工程目录/代码/*.e.txt"],
                "生命周期": ["从磁盘加载", "内存编辑", "原子写回"],
                "字段契约": ["行分隔符按原文件保留（CRLF 或 LF）", "文件末尾换行状态按原文件保留"],
                "索引": ["无（按路径访问）"], "迁移": ["编码检测失败时在诊断中提示"],
                "归属关系": "属于某个工程文档",
                "读写责任模块": ["m_ide_canvas_core", "m_frontend_lexer", "m_frontend_*"],
            }],
            "入口": {"用户入口": ["打开工程"], "接口入口": ["词法模块.切分"],
                     "命令入口": [], "事件入口": [], "系统入口": [], "资源入口": []},
            "FE-扩展契约": {"字段": ["新格式的自由契约也必须保留"], "状态": "未验证"},
        }

    def test_payload_preserves_existing_keys_and_deep_copies_complete_source(self):
        source = copy.deepcopy(EXAMPLE)
        source["未来扩展段"] = {"任意语言": ["易语言", "Rust", {"标记": ["完整保留"]}]}
        before = copy.deepcopy(source)
        payload = render._build_json_payload(source, None, [], [])
        existing = {"项目", "元信息", "模块", "依赖边", "功能树", "数据拓扑",
                    "模块详情", "进度", "数据实体", "质量问题"}
        self.assertTrue(existing.issubset(payload))
        self.assertEqual(payload["完整架构"], source)
        self.assertIsNot(payload["完整架构"], source)
        payload["完整架构"]["未来扩展段"]["任意语言"][2]["标记"].append("仅修改视图")
        self.assertEqual(source, before, "view consumers must not mutate the source")
        self.assertGreater(payload["视图设置"]["每图节点上限"], 0)

    def test_json_and_html_keep_all_modules_when_the_graph_page_limit_is_small(self):
        for fmt in ("json", "html"):
            with self.subTest(format=fmt):
                if fmt == "json":
                    payload = json.loads(render.render_json_output(EXAMPLE, None, [], [], 2))
                else:
                    payload = html_payload(render.render_html_report(EXAMPLE, None, [], [], 2))
                self.assertEqual(payload["模块"], EXAMPLE["模块拓扑"]["节点"])
                self.assertEqual(payload["完整架构"], EXAMPLE)
                self.assertEqual(payload["视图设置"]["每图节点上限"], 2)

    def test_new_e_group_references_expand_catalog_without_changing_topology(self):
        source = self.new_e_fixture()
        expected_ids = set(source["模块详情"])
        topology_ids = {node["编号"] for node in source["模块拓扑"]["节点"]}
        for fmt in ("json", "html"):
            with self.subTest(format=fmt):
                if fmt == "json":
                    payload = json.loads(render.render_json_output(source, None, [], [], 1))
                else:
                    payload = html_payload(render.render_html_report(source, None, [], [], 1))
                self.assertEqual(payload["模块"], source["模块拓扑"]["节点"])
                self.assertEqual(payload["依赖边"], source["模块拓扑"]["依赖图"])
                catalog = payload["模块目录"]
                actual_ids = [node["编号"] for node in catalog]
                self.assertEqual(set(actual_ids), expected_ids)
                self.assertEqual(len(actual_ids), len(expected_ids), "group references must not duplicate modules")
                self.assertEqual(len(expected_ids - topology_ids), 7)
                self.assertNotIn("group_frontend", actual_ids)
                self.assertNotIn("group_canvas", actual_ids)

    def test_new_e_outer_detail_keys_and_field_contract_entities_remain_complete(self):
        source = self.new_e_fixture()
        before = copy.deepcopy(source)
        for fmt in ("json", "html"):
            with self.subTest(format=fmt):
                if fmt == "json":
                    payload = json.loads(render.render_json_output(source, None, [], [], 1))
                else:
                    payload = html_payload(render.render_html_report(source, None, [], [], 1))
                self.assertEqual(payload["完整架构"], source)
                self.assertEqual(payload["模块详情"], source["模块详情"])
                self.assertEqual(payload["数据实体"], source["数据拓扑"])
                entity = payload["数据实体"][0]
                self.assertNotIn("字段", entity)
                self.assertEqual(entity["字段契约"], source["数据拓扑"][0]["字段契约"])
                self.assertEqual(entity["读写责任模块"], source["数据拓扑"][0]["读写责任模块"])
        self.assertEqual(source, before)

    def test_new_e_layer_and_original_declaration_are_readable_in_markdown(self):
        source = self.new_e_fixture()
        text = render.to_dependency_flow(source, max_nodes=2)
        self.assert_declarations(text, ["词法模块", "语法模块"], page_limit=2)
        self.assertIn('subgraph "前端"', text)
        rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]
        edge = source["模块拓扑"]["依赖图"][0]
        self.assertTrue(any(all(value in row for value in
                                (edge["从"], edge["到"], edge["原声明"])) for row in rows))

    def test_markdown_pages_declare_every_module_once(self):
        source = self.module_fixture()
        text = render.to_dependency_flow(source, max_nodes=2)
        self.assert_declarations(text, [n["名称"] for n in source["模块拓扑"]["节点"]],
                                 page_limit=2)
        self.assertGreaterEqual(len(MERMAID.findall(text)), 3)

    def test_markdown_keeps_every_dependency_in_a_complete_relationship_table(self):
        source = self.module_fixture()
        text = render.render_markdown_report(source, None, [], [], 2)
        rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]
        for edge in source["模块拓扑"]["依赖图"]:
            with self.subTest(edge=edge):
                self.assertTrue(any(all(value in row for value in
                                        (edge["从"], edge["到"], edge["说明"])) for row in rows),
                                "pagination must not erase a relationship or its explanation")

    def test_numeric_and_special_module_ids_use_safe_graph_aliases(self):
        hostile_id = 'bad"]\nINJECTED_NODE --> injected\n%%'
        hostile_name = '</script><script>globalThis.pwned = true</script>'
        names = ["零号模块", "七号模块", "特殊模块"]
        source = {"模块拓扑": {"节点": [
            {"编号": 0, "名称": names[0]},
            {"编号": 7, "名称": names[1]},
            {"编号": hostile_id, "名称": names[2], "说明": hostile_name},
        ], "依赖图": [
            {"从": 0, "到": 7, "说明": "数字端点依赖"},
            {"从": 7, "到": hostile_id, "说明": "特殊端点依赖"},
        ]}}
        text = render.to_dependency_flow(source, max_nodes=10)
        self.assert_declarations(text, names, page_limit=10)
        graph = "\n".join(MERMAID.findall(text))
        self.assertNotIn("INJECTED_NODE --> injected", graph)
        self.assertNotIn("<script>", graph)
        self.assertEqual(len(re.findall(r"^\s*[A-Za-z_]\w*\s*-->", graph, re.MULTILINE)), 2)

    def test_pure_function_cycle_is_not_lost(self):
        source = {"功能树": [
            {"编号": "cycle.a", "名称": "环内功能甲", "子节点": ["cycle.b"]},
            {"编号": "cycle.b", "名称": "环内功能乙", "子节点": ["cycle.a"]},
        ]}
        text = render.to_function_tree(source, max_nodes=1)
        self.assert_declarations(text, ["环内功能甲", "环内功能乙"], page_limit=1)

    def test_reachable_function_cycle_and_isolated_component_are_not_lost(self):
        source = {"功能树": [
            {"编号": "root", "名称": "根功能", "子节点": ["a"]},
            {"编号": "a", "名称": "可达功能甲", "子节点": ["b"]},
            {"编号": "b", "名称": "可达功能乙", "子节点": ["a"]},
            {"编号": "isolated", "名称": "独立功能", "子节点": []},
        ]}
        text = render.to_function_tree(source, max_nodes=2)
        self.assert_declarations(text, [n["名称"] for n in source["功能树"]], page_limit=2)

    def test_child_before_parent_still_appears_on_paginated_function_graph(self):
        source = {"功能树": [
            {"编号": 7, "名称": "先列出的子功能", "父节点": 0, "子节点": []},
            {"编号": 0, "名称": "后列出的父功能", "子节点": [7]},
        ]}
        self.assert_declarations(render.to_function_tree(source, max_nodes=1),
                                 ["先列出的子功能", "后列出的父功能"], page_limit=1)

    def test_html_preserves_hostile_text_as_data_without_script_injection(self):
        source = self.module_fixture()
        hostile = '</script><script>globalThis.pwned = true</script><img src=x onerror=alert(1)>'
        source["模块拓扑"]["节点"][0]["编号"] = hostile
        source["模块拓扑"]["节点"][0]["名称"] = hostile
        source["特殊扩展"] = {"原始文本": hostile,
                              "占位符": "@TITLE@ @DATA@ @TIME@ @DEPENDENCY_STATUS@ @DEPENDENCY_CLASS@"}
        document = render.render_html_report(source, None, [], [], 1)
        self.assertEqual(html_payload(document)["完整架构"], source)
        self.assertNotIn(hostile, document)
        self.assertNotIn("<img src=x", document)

    def test_empty_acceptance_and_structural_errors_have_reader_diagnostics(self):
        source = {"模块拓扑": {"节点": [{"编号": "known", "名称": "已知模块"}],
                                "依赖图": [{"从": "known", "到": "missing-module"}]},
                  "功能树": [{"编号": "empty-leaf", "名称": "缺验收叶子", "子节点": [],
                              "验收标准": [], "架构落位": {"测试": []}}]}
        document = render.render_html_report(source, None, [], [], 2)
        prompts = html_payload(document)["渲染提示"]
        self.assertIsInstance(prompts, list)
        diagnostics = json.dumps(prompts, ensure_ascii=False)
        self.assertIn("验收", diagnostics)
        self.assertIn("missing-module", diagnostics)
        visible = StaticText()
        visible.feed(document)
        self.assertRegex(" ".join(visible.parts), r"(?:渲染|阅读|结构).{0,8}(?:提示|诊断)")

    def conflicting_dependency_fixture(self):
        return {"模块拓扑": {"节点": [{"编号": key} for key in ("a", "b", "c")],
                                "依赖图": [{"从": "b", "到": "c"}]},
                "模块详情": {"a": {"上游依赖": [{"模块编号": "b", "编号": "c"}]},
                               "b": {}, "c": {}}}

    def test_conflicting_dependencies_are_incomplete_in_every_report_format(self):
        source = self.conflicting_dependency_fixture()
        before = copy.deepcopy(source)
        markdown = render.render_markdown_report(source, None, [], [], 2)
        self.assertIn("conflicting_reference", markdown)
        self.assertIn("/模块详情/a/上游依赖/0", markdown)
        self.assertIn("关系图不完整", markdown)
        visible = StaticText()
        report_html = render.render_html_report(source, None, [], [], 2)
        visible.feed(report_html)
        self.assertIn('id="dependency-extraction"', report_html)
        self.assertIn("依赖声明解析：incomplete", " ".join(visible.parts))
        self.assertIn("阻断诊断 1 项", " ".join(visible.parts))
        for payload in (json.loads(render.render_json_output(source, None, [], [], 2)),
                        html_payload(render.render_html_report(source, None, [], [], 2))):
            with self.subTest(payload=payload["元信息"]):
                self.assertEqual(payload["依赖提取"]["status"], "incomplete")
                self.assertEqual(payload["依赖提取"]["parsed_edge_count"], 1)
                self.assertEqual(payload["依赖提取"]["blocking_diagnostic_count"], 1)
                self.assertEqual(payload["依赖诊断"], declared_dependencies(source)["diagnostics"])
                self.assertEqual(payload["完整架构"], source)
                self.assertEqual(payload["依赖边"], [{"从": "b", "到": "c"}])
                self.assertEqual(payload["质量问题"], {"错误": [], "警告": []})
                self.assertIn("关系图不完整", " ".join(payload["渲染提示"]))
        self.assertEqual(source, before)

    def test_invalid_only_dependency_graph_is_not_reported_as_no_dependencies(self):
        source = self.conflicting_dependency_fixture()
        source["模块拓扑"]["依赖图"] = []
        flow = render.to_dependency_flow(source)
        self.assertIn("0 条依赖", flow)
        self.assertIn("关系图不完整", flow)
        self.assertIn("不代表项目没有依赖", flow)

    def test_descriptive_reference_is_visible_without_claiming_a_blocked_parse(self):
        source = {"模块详情": {"a": {"上游依赖": [{"说明": "外部进程，仅作说明"}]}}}
        payload = json.loads(render.render_json_output(source, None, [], [], 2))
        self.assertEqual(payload["依赖提取"]["status"], "complete")
        self.assertEqual(payload["依赖提取"]["blocking_diagnostic_count"], 0)
        self.assertEqual(payload["依赖提取"]["explanatory_diagnostic_count"], 1)
        self.assertEqual(payload["依赖边"], [])
        self.assertEqual(payload["依赖诊断"][0]["code"], "descriptive_reference")
        self.assertIn("descriptive_reference", " ".join(payload["渲染提示"]))
        self.assertIn("不代表实现或测试通过", payload["依赖提取"]["reason"])
        visible = StaticText()
        visible.feed(render.render_html_report(source, None, [], [], 2))
        self.assertIn("依赖声明解析：complete", " ".join(visible.parts))
        self.assertIn("说明性记录 1 项", " ".join(visible.parts))

    def test_dependency_diagnostics_keep_all_physical_sources_and_escape_readable_text(self):
        source = self.conflicting_dependency_fixture()
        result = declared_dependencies(source)
        original = result["diagnostics"][0]
        hostile = '</script><img src=x onerror=alert(1)>|危险来源'
        result["diagnostics"] = [dict(original, file=hostile, sha256="a" * 64),
                                 dict(original, file="architecture/detail-two.json", sha256="b" * 64)]
        view = ArchitectureView(source, result)
        for document in (render.render_json_output(view, None, [], [], 2),
                         render.render_html_report(view, None, [], [], 2)):
            payload = html_payload(document) if document.startswith("<!") else json.loads(document)
            self.assertEqual(payload["依赖诊断"], result["diagnostics"])
            self.assertEqual(payload["依赖提取"]["blocking_diagnostic_count"], 2)
        html_document = render.render_html_report(view, None, [], [], 2)
        self.assertNotIn(hostile, html_document)
        self.assertNotIn("<img src=x", html_document)
        markdown = render.render_markdown_report(view, None, [], [], 2)
        self.assertIn(render._cell(hostile), markdown)
        self.assertIn("architecture/detail-two.json#/模块详情/a/上游依赖/0", markdown)
        self.assertIn("a" * 64, markdown)
        self.assertIn("b" * 64, markdown)
        payload = render._build_json_payload(view, None, [], [])
        payload["依赖诊断"].clear()
        self.assertEqual(view.dependency_sources, result, "view consumers must not alter origin facts")

    def test_real_cli_sliced_reports_preserve_physical_diagnostic_pointer_and_hash(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "architecture").mkdir()
            source = self.conflicting_dependency_fixture()
            details = source.pop("模块详情")
            source["架构切片"] = {"启用": True, "切片清单": [
                {"路径": "architecture/details.json", "包含": ["模块详情"]}]}
            arch_path, slice_path = root / "architecture.json", root / "architecture/details.json"
            arch_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            slice_path.write_text(json.dumps({"模块详情": details}, ensure_ascii=False), encoding="utf-8")
            before = {path: path.read_bytes() for path in (arch_path, slice_path)}
            digest = hashlib.sha256(before[slice_path]).hexdigest()
            for fmt in ("md", "json", "html"):
                with self.subTest(format=fmt):
                    output = root / ("report." + fmt)
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        code = render.main([str(arch_path), "--format", fmt, "--html-view", "report",
                                            "--output", str(output)])
                    self.assertEqual(code, 0)
                    document = output.read_text(encoding="utf-8")
                    if fmt == "md":
                        self.assertIn("architecture/details.json#/模块详情/a/上游依赖/0", document)
                        self.assertIn(digest, document)
                    else:
                        payload = html_payload(document) if fmt == "html" else json.loads(document)
                        diagnostic = payload["依赖诊断"][0]
                        self.assertEqual(diagnostic["code"], "conflicting_reference")
                        self.assertEqual(diagnostic["file"], "architecture/details.json")
                        self.assertEqual(diagnostic["pointer"], "/模块详情/a/上游依赖/0")
                        self.assertEqual(diagnostic["sha256"], digest)
                        self.assertEqual(payload["依赖提取"]["status"], "incomplete")
                        self.assertEqual(payload["完整架构"]["模块详情"], details)
            self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_real_cli_plain_and_recursive_reports_keep_diagnostic_physical_owners(self):
        for layout in ("plain", "recursive"):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                arch_path = root / "architecture.json"
                if layout == "plain":
                    documents = {arch_path: self.conflicting_dependency_fixture()}
                    diagnostic_path, pointer = arch_path, "/模块详情/a/上游依赖/0"
                else:
                    def module(key):
                        return {"模块路由": {"版本": 1, "编号": key, "名称": key,
                                            "职责": "负责" + key, "子模块": []},
                                "模块详情": {key: {}},
                                "实现清单": {key: {"文件列表": [], "依赖模块": []}}}
                    root_doc, child_doc = module("root"), module("a")
                    root_doc["模块路由"]["子模块"] = [
                        {"编号": "a", "路径": "a/architecture.json", "职责": "负责a"}]
                    child_doc["模块详情"]["a"]["上游依赖"] = [{"模块编号": "b", "编号": "c"}]
                    diagnostic_path, pointer = root / "a/architecture.json", "/模块详情/a/上游依赖/0"
                    documents = {arch_path: root_doc, diagnostic_path: child_doc}
                for path, document in documents.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
                before = {path: path.read_bytes() for path in documents}
                digest = hashlib.sha256(before[diagnostic_path]).hexdigest()
                physical_file = diagnostic_path.relative_to(root).as_posix()
                for fmt in ("md", "json", "html"):
                    with self.subTest(format=fmt):
                        output = root / ("report." + fmt)
                        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                            code = render.main([str(arch_path), "--format", fmt, "--html-view", "report",
                                                "--output", str(output)])
                        self.assertEqual(code, 0)
                        document = output.read_text(encoding="utf-8")
                        if fmt == "md":
                            self.assertIn(physical_file + "#" + pointer, document)
                            self.assertIn(digest, document)
                        else:
                            payload = html_payload(document) if fmt == "html" else json.loads(document)
                            diagnostic = payload["依赖诊断"][0]
                            self.assertEqual((diagnostic["file"], diagnostic["pointer"], diagnostic["sha256"]),
                                             (physical_file, pointer, digest))
                            self.assertEqual(payload["依赖提取"]["status"], "incomplete")
                self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_real_cli_reports_keep_diagnostics_from_multiple_physical_slices(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            arch_path = root / "architecture.json"
            source = {"模块拓扑": {"节点": [{"编号": key} for key in ("a", "b", "c", "d")],
                                    "依赖图": [{"从": "b", "到": "c"}]},
                      "架构切片": {"启用": True, "切片清单": [
                          {"路径": "architecture/details-one.json", "包含": ["模块详情"]},
                          {"路径": "architecture/details-two.json", "包含": ["模块详情"]}]}}
            documents = {arch_path: source,
                         root / "architecture/details-one.json": {
                             "模块详情": {"a": {"上游依赖": [{"模块编号": "b", "编号": "c"}]}}},
                         root / "architecture/details-two.json": {
                             "模块详情": {"d": {"上游依赖": [{"模块编号": "a", "编号": "b"}]}}}}
            for path, document in documents.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            before = {path: path.read_bytes() for path in documents}
            expected = {(path.relative_to(root).as_posix(), hashlib.sha256(raw).hexdigest())
                        for path, raw in before.items() if path != arch_path}
            for fmt in ("md", "json", "html"):
                output = root / ("report." + fmt)
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = render.main([str(arch_path), "--format", fmt, "--html-view", "report",
                                        "--output", str(output)])
                self.assertEqual(code, 0)
                document = output.read_text(encoding="utf-8")
                if fmt == "md":
                    for path, digest in expected:
                        self.assertIn(path + "#/模块详情/", document)
                        self.assertIn(digest, document)
                else:
                    payload = html_payload(document) if fmt == "html" else json.loads(document)
                    self.assertEqual({(item["file"], item["sha256"]) for item in payload["依赖诊断"]}, expected)
                    self.assertEqual(payload["依赖提取"]["blocking_diagnostic_count"], 2)
                    self.assertEqual(payload["依赖提取"]["parsed_edge_count"], 1)
            self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_html_retains_function_cycle_and_reports_its_structure(self):
        source = {"功能树": [
            {"编号": "cycle.a", "名称": "循环甲", "子节点": ["cycle.b"]},
            {"编号": "cycle.b", "名称": "循环乙", "子节点": ["cycle.a"]},
        ]}
        payload = html_payload(render.render_html_report(source, None, [], [], 1))
        self.assertEqual(payload["功能树"], source["功能树"])
        self.assertRegex(json.dumps(payload["渲染提示"], ensure_ascii=False), r"环|循环")

    def test_cli_rejects_nonpositive_page_limits_without_writing_output(self):
        # No temporary artifacts are required: block both output mutations.
        output = EXAMPLE_PATH.with_name("__invalid_max_nodes_must_not_be_written__.html")
        for limit in (0, -1):
            with self.subTest(limit=limit), mock.patch.object(Path, "write_text") as write, \
                    mock.patch.object(Path, "mkdir") as mkdir, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                try:
                    code = render.main([str(EXAMPLE_PATH), "--format", "html", "--output",
                                        str(output), "--max-nodes", str(limit)])
                except SystemExit as exc:
                    code = exc.code
                self.assertEqual(code, 2)
                write.assert_not_called()
                mkdir.assert_not_called()

    def test_cli_reports_unknown_quality_when_only_the_quality_checker_is_unavailable(self):
        original_import = __import__

        def without_quality_checker(name, *args, **kwargs):
            if name == "check_quality_redlines":
                raise ImportError("simulated unavailable quality checker")
            return original_import(name, *args, **kwargs)

        for fmt in ("md", "html", "json"):
            with self.subTest(format=fmt):
                output = io.StringIO()
                with mock.patch("builtins.__import__", side_effect=without_quality_checker), \
                        mock.patch.object(render._archlib, "load_architecture_json", return_value={}), \
                        mock.patch.object(render, "_resolve_state_path", return_value=None), \
                        redirect_stdout(output), redirect_stderr(io.StringIO()):
                    code = render.main([str(EXAMPLE_PATH), "--format", fmt, "--html-view", "report"])
                self.assertEqual(code, 0, "a report can render while identifying unavailable checks")
                document = output.getvalue()
                if fmt == "md":
                    diagnostics = document
                    self.assertNotIn("无质量红线，无警告", document)
                else:
                    payload = html_payload(document) if fmt == "html" else json.loads(document)
                    self.assertTrue(payload["质量问题"]["警告"])
                    diagnostics = json.dumps(payload["质量问题"]["警告"], ensure_ascii=False)
                self.assertRegex(diagnostics, r"未知|不可用")


class ViewFreshnessContracts(unittest.TestCase):
    """Saved views are byte-bound snapshots, not current-source certificates."""

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def fixture(self, root):
        entry = root / "architecture.json"
        index = root / "architecture/index.json"
        part = root / "architecture/part.json"
        self.write_json(entry, {"指向": "architecture/index.json"})
        self.write_json(index, {"项目": {"名称": "新鲜度回归"}, "架构切片": {
            "启用": True, "切片清单": [{"路径": "architecture/part.json", "包含": ["记录"]}]}})
        self.write_json(part, {"记录": [{"编号": "record-A", "正文": "完整原字段"}]})
        return entry, index, part

    def generate(self, entry, view, fmt="html", mode="project", *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = render.main([str(entry), "--format", fmt, "--html-view", mode,
                                "--output", str(view), *map(str, extra)])
        self.assertEqual(code, 0, stderr.getvalue())
        return view.read_text(encoding="utf-8")

    def assert_freshness(self, entry, view, expected, state=None):
        before = view.read_bytes()
        result = render.check_view(entry, view, state)
        self.assertEqual(result["freshness"], expected, result)
        self.assertEqual((result["status"], result["code"]), {
            "fresh": ("pass", 0), "stale": ("fail", 1), "unknown": ("unknown", 2)}[expected])
        self.assertEqual(view.read_bytes(), before, "checking is read-only")
        return result

    def replace_manifest(self, view, mutate):
        document = view.read_text(encoding="utf-8")
        manifest, _, _ = render._read_view_manifest(view)
        mutate(manifest)
        view.write_text(render._MANIFEST_HTML.sub(lambda match:
            '<script id="architecture-view-manifest" type="application/json">' +
            render._manifest_json(manifest) + '</script>\n', document), encoding="utf-8")

    def test_all_cli_formats_bind_complete_input_sets_and_both_html_modes(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, index, part = self.fixture(root)
            before = {p: p.read_bytes() for p in (entry, index, part)}
            for fmt, mode in (("html", "project"), ("html", "report"), ("md", "project"), ("json", "project")):
                with self.subTest(format=fmt, mode=mode):
                    view = root / (mode + "." + fmt)
                    document = self.generate(entry, view, fmt, mode)
                    result = self.assert_freshness(entry, view, "fresh")
                    records = result["generated_basis"]["inputs"]
                    paths = {item["path"]: item for item in records}
                    self.assertTrue({str(p.resolve()) for p in (entry, index, part)} <= set(paths))
                    state_path = str((root / "architecture/_state.json").resolve())
                    self.assertEqual((paths[state_path]["exists"], paths[state_path]["sha256"]), (False, None))
                    self.assertTrue(any(item["kind"] == "schema" for item in records))
                    self.assertTrue(any(item["path"].endswith("architecture-project.html") for item in records))
                    self.assertTrue(any(item["path"].endswith("architecture-view.html") for item in records))
                    if fmt in ("html", "md"):
                        self.assertIn("生成快照、尚未核验当前输入", document)
                    self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_changed_slice_is_stale_and_regeneration_is_fresh(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, part = self.fixture(root)
            view = root / "project.html"
            self.generate(entry, view)
            self.write_json(part, {"记录": [{"编号": "record-A", "正文": "已修改"}]})
            result = self.assert_freshness(entry, view, "stale")
            self.assertTrue(any(item.get("path") == str(part.resolve()) for item in result["changes"]))
            self.generate(entry, view)
            self.assert_freshness(entry, view, "fresh")

    def test_deleted_required_slice_and_omitted_slice_declaration_never_pass(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, index, part = self.fixture(root)
            view = root / "project.html"
            self.generate(entry, view)
            original = part.read_bytes()
            part.unlink()
            self.assert_freshness(entry, view, "stale")
            part.write_bytes(original)
            self.write_json(index, {"项目": {"名称": "新鲜度回归"}})
            result = self.assert_freshness(entry, view, "stale")
            self.assertTrue(any(item.get("path") == str(part.resolve()) and item["current"] is None
                                for item in result["changes"]))

    def test_optional_state_creation_modification_and_deletion_are_stale(self):
        import manage_state
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, _ = self.fixture(root)
            view, state_path = root / "project.html", root / "architecture/_state.json"
            self.generate(entry, view)
            state = manage_state.create_initial_state("独立项目进度")
            self.write_json(state_path, state)
            self.assert_freshness(entry, view, "stale")
            self.generate(entry, view)
            state["_meta"]["revision"] = 1
            self.write_json(state_path, state)
            self.assert_freshness(entry, view, "stale")
            self.generate(entry, view)
            state_path.unlink()
            self.assert_freshness(entry, view, "stale")

    def test_entry_identity_and_explicit_state_identity_must_match(self):
        import manage_state
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, index, _ = self.fixture(root)
            view, state_path = root / "project.html", root / "custom-state.json"
            self.write_json(state_path, manage_state.create_initial_state("显式状态"))
            self.generate(entry, view, "html", "project", "--state-path", state_path)
            self.assert_freshness(entry, view, "fresh", state_path)
            self.assert_freshness(index, view, "stale", state_path)
            self.assert_freshness(entry, view, "stale")

    def test_renderer_and_schema_dependencies_are_hashed_and_protected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, _ = self.fixture(root)
            schema, dependency, view = root / "schema.json", root / "template.html", root / "project.html"
            schema.write_text("{}", encoding="utf-8")
            dependency.write_text("template-v1", encoding="utf-8")
            paths = render._renderer_inputs()
            paths.update({schema: "schema", dependency: "renderer"})
            with mock.patch.object(render, "_renderer_inputs", return_value=paths):
                self.generate(entry, view)
                self.assert_freshness(entry, view, "fresh")
                dependency.write_text("template-v2", encoding="utf-8")
                self.assert_freshness(entry, view, "stale")
                self.generate(entry, view)
                schema.write_text('{"changed":true}', encoding="utf-8")
                self.assert_freshness(entry, view, "stale")
                for protected in (schema, dependency, *render._renderer_inputs().keys()):
                    before = protected.read_bytes() if protected.exists() else None
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        code = render.main([str(entry), "--format", "html", "--output", str(protected)])
                    self.assertEqual(code, 2)
                    self.assertEqual(protected.read_bytes() if protected.exists() else None, before)

    def test_manifest_omission_is_stale_but_malformed_sha_duplicate_and_legacy_are_unknown(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, part = self.fixture(root)
            view = root / "project.html"
            self.generate(entry, view)
            original = view.read_bytes()
            self.replace_manifest(view, lambda m: m["inputs"].__setitem__(slice(None),
                [item for item in m["inputs"] if item["path"] != str(part.resolve())]))
            self.assert_freshness(entry, view, "stale")
            for mutate in (lambda m: m["inputs"][0].update(sha256="NOT-A-SHA"),
                           lambda m: m["inputs"].append(copy.deepcopy(m["inputs"][0])),
                           lambda m: m.update(schema_version=True),
                           lambda m: m.update(inputs=[])):
                view.write_bytes(original)
                self.replace_manifest(view, mutate)
                self.assert_freshness(entry, view, "unknown")
            view.write_text(render._MANIFEST_HTML.sub("", original.decode("utf-8")), encoding="utf-8")
            self.assert_freshness(entry, view, "unknown")
            view.write_bytes(original)
            match = render._MANIFEST_HTML.search(view.read_text(encoding="utf-8"))
            encoded = match.group(1).replace('"schema_version":1', '"schema_version":1,"schema_version":1')
            view.write_text(view.read_text(encoding="utf-8").replace(match.group(1), encoded), encoding="utf-8")
            self.assert_freshness(entry, view, "unknown")

    def test_view_content_tampering_is_stale_and_saved_content_is_never_executed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, _ = self.fixture(root)
            view, marker = root / "project.html", root / "executed.txt"
            document = self.generate(entry, view)
            view.write_text(document.replace("</body>", '<script>require("fs").writeFileSync(' +
                json.dumps(str(marker)) + ',"executed")</script></body>'), encoding="utf-8")
            with mock.patch.object(subprocess, "run", side_effect=AssertionError("no commands from a view")):
                self.assert_freshness(entry, view, "stale")
            self.assertFalse(marker.exists())

    def test_saved_external_paths_are_lexical_data_not_filesystem_probes(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, _ = self.fixture(root)
            view = root / "project.html"
            self.generate(entry, view)
            external = str(Path(root.anchor) / "__UNTRUSTED_SAVED__" / "never.json")
            self.replace_manifest(view, lambda m: (m.update(entry=external),
                                                  m["inputs"][0].update(path=external)))
            original_resolve = Path.resolve
            original_exists = Path.exists
            original_stat = Path.stat

            def guarded(method):
                def call(path, *args, **kwargs):
                    if "__UNTRUSTED_SAVED__" in str(path):
                        raise AssertionError("saved external paths must not access the filesystem")
                    return method(path, *args, **kwargs)
                return call

            with mock.patch.object(Path, "resolve", guarded(original_resolve)), \
                    mock.patch.object(Path, "exists", guarded(original_exists)), \
                    mock.patch.object(Path, "stat", guarded(original_stat)):
                self.assert_freshness(entry, view, "stale")

    def test_html_and_markdown_newline_byte_tampering_is_stale(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, _ = self.fixture(root)
            for fmt in ("html", "md"):
                view = root / ("newline." + fmt)
                self.generate(entry, view, fmt)
                raw = view.read_bytes()
                self.assertIn(b"\n", raw)
                changed = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                self.assertNotEqual(changed, raw)
                view.write_bytes(changed)
                self.assert_freshness(entry, view, "stale")

    def test_failed_generation_and_failed_atomic_replace_keep_old_view_and_sources(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, index, part = self.fixture(root)
            view = root / "project.html"
            self.generate(entry, view)
            before = {p: p.read_bytes() for p in (entry, index, part, view)}
            with mock.patch.object(render.os, "replace", side_effect=OSError("simulated replace failure")), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = render.main([str(entry), "--format", "html", "--output", str(view)])
            self.assertEqual(code, 2)
            self.assertEqual({p: p.read_bytes() for p in before}, before)
            self.assertEqual(list(root.glob(".architecture-view-*.tmp")), [])
            part.write_text("{broken", encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = render.main([str(entry), "--format", "html", "--output", str(view)])
            self.assertEqual(code, 2)
            self.assertEqual(view.read_bytes(), before[view])
            self.assertEqual(part.read_text(encoding="utf-8"), "{broken")

    def test_check_output_option_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, _ = self.fixture(root)
            view = root / "project.html"
            self.generate(entry, view)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = render.main([str(entry), "--check-view", str(view), "--output", str(entry)])
            self.assertEqual(code, 2)
            self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_real_cli_check_exit_codes_and_stdout_generated_view(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            entry, _, part = self.fixture(root)
            script = REPO_ROOT / "shared/scripts/render_architecture.py"
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            base = [sys.executable, "-B", "-X", "utf8", str(script), str(entry)]
            generated = subprocess.run(base + ["--format", "html"], cwd=root, env=env,
                                       capture_output=True, timeout=30)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            view = root / "stdout.html"
            view.write_bytes(generated.stdout)
            for expected in ("fresh", "stale", "unknown"):
                if expected == "stale":
                    self.write_json(part, {"记录": [{"编号": "record-A", "正文": "新值"}]})
                elif expected == "unknown":
                    view.write_text("<!doctype html><html><body>旧图无清单</body></html>", encoding="utf-8")
                result = subprocess.run(base + ["--check-view", str(view)], cwd=root, env=env,
                                        capture_output=True, text=True, encoding="utf-8", timeout=30)
                parsed = json.loads(result.stdout)
                self.assertEqual(parsed["freshness"], expected)
                self.assertEqual(result.returncode, {"fresh": 0, "stale": 1, "unknown": 2}[expected])


if __name__ == "__main__":
    unittest.main()
