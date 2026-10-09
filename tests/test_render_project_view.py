"""Project HTML interface and real CLI contracts, independent of any checkout."""
from __future__ import annotations

import builtins
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "shared" / "scripts" / "render_architecture.py"
sys.path.insert(0, str(SCRIPT.parent))

import _archlib
import manage_state
import render_architecture as render


class ProjectDocument(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.payloads = []
        self.script_count = 0
        self.tags = []
        self.capture = None
        self.feed(document)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "script":
            self.script_count += 1
            if dict(attrs).get("id") == "project-data":
                self.capture = []

    def handle_data(self, data):
        if self.capture is not None:
            self.capture.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.capture is not None:
            self.payloads.append(json.loads("".join(self.capture)))
            self.capture = None


def payload(document):
    parsed = ProjectDocument(document)
    if len(parsed.payloads) != 1:
        raise AssertionError("the standalone project document must have exactly one complete data block")
    return parsed.payloads[0]


def original_value(model, nid):
    node = model["nodes"][nid]
    if node["t"] == "object":
        return {model["nodes"][child]["k"]: original_value(model, child) for child in node["raw_c"]}
    if node["t"] == "array":
        return [original_value(model, child) for child in node["raw_c"]]
    return node["v"]


def leaf_values(value, pointer=""):
    if isinstance(value, dict) and value:
        result = {}
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            result.update(leaf_values(child, pointer + "/" + escaped))
        return result
    if isinstance(value, list) and value:
        result = {}
        for index, child in enumerate(value):
            result.update(leaf_values(child, pointer + "/" + str(index)))
        return result
    return {pointer: value}


class ProjectRenderingContracts(unittest.TestCase):
    def cli(self, root, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                              cwd=root, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)

    def write_fixture(self, root):
        architecture = root / "architecture"
        architecture.mkdir()
        pointer = {"指向": "architecture/index.json", "说明": "the pointer is also a physical source"}
        index = {"项目": {"名称": "通用来源夹具", "语言": "Rust / C++ / C#"},
                 "current_stage": "业务声明阶段", "completion": {"percentage": 13},
                 "架构切片": {"启用": True, "切片清单": [{
                     "路径": "architecture/part.json", "包含": ["扩展"]}]}}
        part = {"切片元信息": {"编号": "physical-slice", "空容器": {}},
                "扩展": [{"路径/键~值": [None, False, 0, "", [], {}]}]}
        state = manage_state.create_initial_state("independent progress")
        state["completion"]["percentage"] = 100  # deliberately stale; loader derives the current view
        values = {root / "architecture.json": pointer, architecture / "index.json": index,
                  architecture / "part.json": part, architecture / "_state.json": state}
        for path, value in values.items():
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return values

    def test_minimal_language_independent_api_preserves_types_and_exact_number_text(self):
        huge = 9007199254740993
        fixtures = [{}, {"Rust/C++": [False, 0, None, "", [], {}],
                          "超大整数": huge, "负整数": -huge, "负零": -0.0,
                          "未知业务": {"nested": "retained"}}]
        for source in fixtures:
            with self.subTest(source=source):
                model = payload(render.render_project_view(source, None, [], []))
                self.assertEqual(original_value(model, 0), source)
                self.assertEqual(model["top_count"], len(source))
                self.assertEqual(model["leaf_count"], len(leaf_values(source)))
                self.assertEqual(model["relations"], [])
                self.assertIsNone(model["progress"])
                for node in model["nodes"][:model["source_node_count"]]:
                    if node["t"] == "number":
                        self.assertEqual(node["number_literal"], json.dumps(node["v"]))

    def test_api_does_not_modify_data_state_quality_or_source_records(self):
        data = {"项目": {"名称": "immutable inputs"}, "模块详情": {"m": {"职责": ["original"], "非职责": []}}}
        state = manage_state.create_initial_state("separate state")
        errors, warnings = ["existing failure"], ["unverified item"]
        sources = [{"path": "source.json", "sha256": "caller-observed", "data": data,
                    "metadata": {"tags": ["original"]}}]
        originals = copy.deepcopy((data, state, errors, warnings, sources))
        model = payload(render.render_project_view(data, state, errors, warnings, sources))
        self.assertEqual((data, state, errors, warnings, sources), originals)
        self.assertEqual(model["quality"], {"errors": errors, "warnings": warnings})
        model["progress"]["stages"][0]["status"] = "completed"
        model["sources"][0]["metadata"]["tags"].append("only decoded output")
        self.assertEqual((data, state, errors, warnings, sources), originals)

    def test_hostile_script_closing_and_template_markers_stay_literal_data(self):
        hostile = '</script><script id="evil">globalThis.injected=true</script><img onerror="attack()">'
        marker = "__PROJECT_DATA__ @TITLE@ @DATA@ & < > \u2028 \u2029"
        source = {"项目": {"名称": hostile}, "text": marker, "嵌套": [hostile, marker]}
        state = {"notes": [hostile, marker]}
        sources = [{"path": hostile + marker, "sha256": marker, "data": {"注释": hostile}}]
        document = render.render_project_view(source, state, [hostile], [marker], sources)
        parsed, baseline = ProjectDocument(document), ProjectDocument(render.render_project_view({}, None, [], []))
        self.assertEqual(len(parsed.payloads), 1)
        self.assertEqual(parsed.script_count, baseline.script_count)
        self.assertFalse(any(attrs.get("id") == "evil" or "onerror" in attrs for _, attrs in parsed.tags))
        model = parsed.payloads[0]
        self.assertEqual(original_value(model, 0), source)
        self.assertEqual(model["progress"], state)
        self.assertEqual(model["quality"], {"errors": [hostile], "warnings": [marker]})
        self.assertEqual(model["sources"][0]["path"], sources[0]["path"])

    def test_progress_is_a_separate_view_and_business_status_declarations_remain_original(self):
        data = {"current_stage": "business-stage", "completion": {"percentage": 13},
                "stages": [{"status": "planned-business-value"}]}
        state = {"current_stage": "execution-stage", "completion": {"percentage": 100},
                 "stages": [{"status": "completed"}]}
        sources = [{"path": "business.json", "data": data}, {"path": "_state.json", "data": state}]
        model = payload(render.render_project_view(data, state, [], [], sources))
        self.assertEqual(original_value(model, 0), data)
        self.assertEqual(model["progress"], state)
        self.assertEqual(model["top_count"], len(data))
        mapping = next(m for m in model["physical_mappings"]
                       if m["source"] == "_state.json" and m["pointer"] == "/completion/percentage")
        self.assertEqual(model["nodes"][mapping["node"]]["v"], 100)
        self.assertTrue(mapping["visual_pointer"].startswith("/@源文件/"))
        self.assertEqual([s["path"] for s in model["field_sources"]["completion"]], ["business.json"])

    def test_real_cli_defaults_to_project_html_and_report_mode_remains_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {"unfamiliar-language": {"compiler.vendor": [], "source.e": None}}
            input_path = root / "input.json"
            input_path.write_text(json.dumps(source), encoding="utf-8")
            before = input_path.read_bytes()
            output = root / "project.html"
            result = self.cli(root, input_path, "--format", "html", "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(original_value(payload(output.read_text(encoding="utf-8")), 0), source)
            report = root / "report.html"
            result = self.cli(root, input_path, "--format", "html", "--html-view", "report", "--output", report)
            self.assertEqual(result.returncode, 0, result.stderr)
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("const DATA = ", report_text)
            self.assertIn("模块依赖图", report_text)
            self.assertEqual(ProjectDocument(report_text).payloads, [])
            self.assertEqual(input_path.read_bytes(), before)

    def test_real_cli_maps_every_physical_leaf_and_keeps_pointer_metadata_and_state_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physical = self.write_fixture(root)
            before = {str(path.resolve()): path.read_bytes() for path in physical}
            output = root / "nested-output" / "project.html"
            result = self.cli(root, root / "architecture.json", "--format", "html", "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            model = payload(output.read_text(encoding="utf-8"))
            hydrated = _archlib.load_architecture_json(root / "architecture.json")
            self.assertEqual(original_value(model, 0), hydrated)
            expected = {(str(path.resolve()), p): value for path, value in physical.items()
                        for p, value in leaf_values(value).items()}
            actual = {(m["source"], m["pointer"]): m for m in model["physical_mappings"]}
            self.assertEqual(set(actual), set(expected))
            self.assertEqual(model["physical_leaf_count"], len(expected))
            for key, value in expected.items():
                recovered = original_value(model, actual[key]["node"])
                self.assertEqual(recovered, value, key)
                self.assertIs(type(recovered), type(value), key)
            self.assertTrue(any(p == "/指向" for _, p in actual))
            self.assertTrue(any(p.startswith("/切片元信息") for _, p in actual))
            for record in model["sources"]:
                self.assertEqual(record["sha256"], hashlib.sha256(before[record["path"]]).hexdigest())
                self.assertNotIn("data", record)
            self.assertEqual(len(model["sources"]), len(physical))
            self.assertEqual(model["progress"]["completion"]["percentage"], 0)
            self.assertEqual(original_value(model, 0)["completion"]["percentage"], 13)
            self.assertEqual({str(path.resolve()): path.read_bytes() for path in physical}, before)

    def test_relative_cli_deduplicates_state_loaded_as_slice_and_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physical = self.write_fixture(root)
            index_path = root / "architecture" / "index.json"
            physical[index_path].pop("current_stage")
            physical[index_path].pop("completion")
            physical[index_path]["架构切片"]["切片清单"].append({
                "路径": "architecture/_state.json",
                "包含": list(physical[root / "architecture" / "_state.json"])})
            index_path.write_text(json.dumps(physical[index_path], ensure_ascii=False), encoding="utf-8")
            before = {path: path.read_bytes() for path in physical}
            for relative in ("architecture.json", "architecture/index.json"):
                with self.subTest(relative=relative):
                    output = root / ("pointer.html" if relative == "architecture.json" else "index.html")
                    result = self.cli(root, relative, "--format", "html", "--output", output)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    model = payload(output.read_text(encoding="utf-8"))
                    expected_sources = {str(path.resolve()) for path in physical
                                        if relative == "architecture.json" or path != root / "architecture.json"}
                    self.assertEqual(len(model["sources"]), len(expected_sources))
                    self.assertEqual({source["path"] for source in model["sources"]}, expected_sources)
                    expected_leaves = {(str(path.resolve()), pointer) for path, value in physical.items()
                                       if str(path.resolve()) in expected_sources
                                       for pointer in leaf_values(value)}
                    self.assertEqual(len(model["physical_mappings"]), len(expected_leaves))
                    self.assertEqual(model["physical_leaf_count"], len(expected_leaves))
                    self.assertEqual({path: path.read_bytes() for path in physical}, before)
                    self.assertFalse((root / "architecture" / "_state.json.lock").exists())

    def test_real_cli_refuses_all_authoritative_outputs_including_same_file_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physical = self.write_fixture(root)
            before = {path: path.read_bytes() for path in physical}
            targets = list(physical)
            alias = root / "source-alias.html"
            try:
                os.link(root / "architecture.json", alias)
            except OSError:
                pass  # path identity protection remains mandatory without hard-link support
            else:
                targets.append(alias)
            for target in targets:
                with self.subTest(target=target.name):
                    result = self.cli(root, root / "architecture.json", "--format", "html", "--output", target)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("不得覆盖", result.stderr)
                    self.assertEqual({path: path.read_bytes() for path in physical}, before)

    def test_missing_quality_checker_remains_unknown_in_cli_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, output = root / "input.json", root / "output.html"
            input_path.write_text('{"任意语言":[]}', encoding="utf-8")
            actual_import = builtins.__import__

            def without_quality(name, *args, **kwargs):
                if name == "check_quality_redlines":
                    raise ImportError("quality checker deliberately unavailable")
                return actual_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=without_quality), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = render.main([str(input_path), "--format", "html", "--output", str(output)])
            self.assertEqual(code, 0, "successful rendering is not a successful quality gate")
            document = output.read_text(encoding="utf-8")
            quality = payload(document)["quality"]
            self.assertEqual(quality["errors"], [])
            self.assertTrue(any("不可用" in warning and "未知" in warning for warning in quality["warnings"]))
            self.assertNotIn("status", quality)
            self.assertIn("架构声明不等同源码或测试已通过", document)
            self.assertNotIn("全项目验证通过", document)


if __name__ == "__main__":
    unittest.main()
