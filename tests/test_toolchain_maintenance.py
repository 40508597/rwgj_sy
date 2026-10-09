"""Concrete old-tool maintenance regressions and non-executing dynamic inventory."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import audit_architecture
import check_regression_assertions
import check_toolchain_inventory as audit
import diff_architecture
import init_architecture
import manage_state
import module_architecture
import run_with_progress
import _capabilitylib


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def module_document(module_id="root"):
    return {"模块路由": {"版本": 1, "编号": module_id, "名称": "项目", "职责": "统筹模块", "子模块": []},
            "模块详情": {module_id: {"职责": "统筹模块"}},
            "实现清单": {module_id: {"文件列表": [], "依赖模块": []}}}


class InventoryTests(unittest.TestCase):
    def test_actual_file_set_hashes_signatures_and_policies_are_derived(self):
        result = audit.inventory()
        self.assertEqual(result["status"], "pass", result)
        rows = {item["file"]: item for item in result["data"]["tools"]}
        actual = {path.name for path in SCRIPTS.glob("*.py")}
        self.assertEqual(set(rows), actual)
        self.assertEqual(result["data"]["actual_file_count"], len(actual))
        for name, row in rows.items():
            self.assertEqual(row["sha256"], hashlib.sha256((SCRIPTS / name).read_bytes()).hexdigest())
            self.assertEqual(row["syntax"], "pass")
            self.assertTrue(row["purpose"])
            self.assertTrue(row["contract"])
            if row["role"] == "cli":
                self.assertTrue(row["entrypoint"]["main_defined"])
                self.assertTrue(row["entrypoint"]["guard_calls_main"])
        self.assertFalse(result["evidence"]["imports_scanned_modules"])
        self.assertFalse(result["evidence"]["executes_scanned_modules"])

    def test_unreviewed_script_is_unknown_and_never_executes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "EXECUTED"
            (root / "surprise.py").write_text(
                "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n",
                encoding="utf-8")
            with patch.object(audit.subprocess, "run", side_effect=AssertionError("inventory executed code")):
                result = audit.inventory(root, root / "tests")
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["data"]["actual_file_count"], 1)
            self.assertFalse(marker.exists())
            kinds = {item["kind"] for item in result["data"]["tools"][0]["diagnostics"]}
            self.assertIn("unreviewed_tool", kinds)
            self.assertIn("import_time_effect", kinds)

    def test_custom_familiar_script_cannot_opt_into_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "validate_architecture.py").write_text("raise RuntimeError('must not execute')", encoding="utf-8")
            with patch.object(audit.subprocess, "run", side_effect=AssertionError("executed")):
                with self.assertRaisesRegex(ValueError, "已审阅"):
                    audit.inventory(root, verify_help=True)

    def test_syntax_error_and_missing_main_are_known_failures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "validate_architecture.py").write_text("def broken(:\n", encoding="utf-8")
            self.assertEqual(audit.inventory(root)["status"], "fail")
            (root / "validate_architecture.py").write_text("def main(): return 0\n", encoding="utf-8")
            result = audit.inventory(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("entrypoint", {item["kind"] for item in result["data"]["tools"][0]["diagnostics"]})

    def test_actual_parser_declarations_preserve_expressions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "validate_architecture.py").write_text(
                "import argparse\ndef main():\n p=argparse.ArgumentParser()\n"
                " p.add_argument('--real-option', choices=sorted({'yes','no'}))\n"
                " p.parse_args()\nif __name__ == '__main__': main()\n", encoding="utf-8")
            result = audit.inventory(root)
            declarations = result["data"]["tools"][0]["parser_interface"]["arguments"]
            self.assertEqual(declarations[0]["names"], ["--real-option"])
            self.assertIn("expression", declarations[0]["options"]["choices"])

    def test_missing_local_core_dependency_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "_archlib.py").write_text("import _toolchain_missing\ndef public(): pass\n", encoding="utf-8")
            result = audit.inventory(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("missing_local_dependency",
                          {item["kind"] for item in result["data"]["tools"][0]["diagnostics"]})

    def test_duplicate_function_is_rejected_and_class_methods_are_inventory_interfaces(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "_archlib.py"
            path.write_text("def load_json_utf8(path): return {}\ndef load_json_utf8(path): return None\n",
                            encoding="utf-8")
            result = audit.inventory(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("duplicate_definition",
                          {item["kind"] for item in result["data"]["tools"][0]["diagnostics"]})
            path.write_text("class Store:\n def __init__(self, project, create=False): pass\n"
                            " def get(self, kind, id, conn=None): pass\n", encoding="utf-8")
            result = audit.inventory(root)
            methods = result["data"]["tools"][0]["class_api"][0]["methods"]
            self.assertEqual([method["name"] for method in methods], ["__init__", "get"])
            self.assertIn("conn=None", methods[1]["arguments"])

    def test_empty_directory_cannot_pass_and_bad_timeout_is_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            for value in [0, -1, float("nan"), float("inf")]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    audit.inventory(Path(td), timeout=value)
            with self.assertRaisesRegex(ValueError, "没有实际"):
                audit.inventory(Path(td))

    def test_inventory_cli_missing_directory_returns_json_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            output = io.StringIO()
            with redirect_stdout(output):
                code = audit.main(["--scripts-dir", str(Path(td) / "absent")])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "unknown")

    def test_inventory_invalid_arguments_return_machine_readable_unknown(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = audit.main(["--not-a-real-option"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "unknown")

    def test_inventory_import_alone_has_no_filesystem_or_process_effects(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run([sys.executable, "-B", "-c",
                                     "import sys; sys.path.insert(0, " + repr(str(SCRIPTS))
                                     + "); import check_toolchain_inventory; print('imported')"],
                                    cwd=td, text=True, capture_output=True, encoding="utf-8",
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "imported")
            self.assertEqual(list(Path(td).iterdir()), [])


class ExistingInputMaintenanceTests(unittest.TestCase):
    def test_recursive_duplicate_key_patch_is_unknown_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch = root / "architecture.json"
            write_json(arch, module_document())
            original = arch.read_bytes()
            patch_file = root / "patch.json"
            patch_file.write_text('{"模块详情":{"root":{"职责":"第一份","职责":"第二份"}}}', encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = module_architecture.main(["update", "--architecture", str(arch), "--module", "root",
                                                 "--patch", str(patch_file), "--expected-sha256",
                                                 hashlib.sha256(original).hexdigest()])
            self.assertEqual(code, 2, output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["status"], "unknown")
            self.assertEqual(arch.read_bytes(), original)

    def test_recursive_batch_duplicate_and_nonfinite_inputs_never_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch = root / "architecture.json"
            write_json(arch, module_document())
            before = arch.read_bytes()
            digest = hashlib.sha256(before).hexdigest()
            for value in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}']:
                with self.subTest(value=value):
                    patch_file = root / "batch.json"
                    patch_file.write_text('{"更新":[{"编号":"root","预期SHA256":"' + digest
                                          + '","补丁":' + value + '}]}', encoding="utf-8")
                    output = io.StringIO()
                    with redirect_stdout(output):
                        code = module_architecture.main(["update-batch", "--architecture", str(arch),
                                                         "--patch", str(patch_file)])
                    self.assertEqual(code, 2, output.getvalue())
                    self.assertEqual(arch.read_bytes(), before)

    def test_recursive_stale_hash_still_conflicts_and_valid_unicode_patch_works(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch = root / "architecture.json"
            patch_file = root / "patch.json"
            write_json(arch, module_document())
            write_json(patch_file, {"扩展事实": {"未知语言": "保留"}})
            before = arch.read_bytes()
            with self.assertRaises(module_architecture.WriteConflict):
                module_architecture.update(arch, "root", patch_file, "0" * 64)
            self.assertEqual(arch.read_bytes(), before)
            result = module_architecture.update(arch, "root", patch_file, hashlib.sha256(before).hexdigest())
            self.assertEqual(result["status"], "pass")
            self.assertEqual(json.loads(arch.read_text(encoding="utf-8"))["扩展事实"]["未知语言"], "保留")

    def test_state_template_and_capability_readers_reject_ambiguous_numbers(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "input.json"
            for text in ['{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}', '{"a":NaN}', '{"a":1e999}']:
                path.write_text(text, encoding="utf-8")
                for reader in (manage_state.load_state, init_architecture.load_template, _capabilitylib.read_json):
                    with self.subTest(text=text, reader=reader.__name__), self.assertRaises(ValueError):
                        reader(path)

    def test_migration_rejects_duplicate_before_archive_or_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "architecture.json"
            source.write_text('{"项目":{"名称":"旧","名称":"覆盖"}}', encoding="utf-8")
            before = source.read_bytes()
            with self.assertRaises(ValueError):
                init_architecture.migrate_single_file(source, root, False, "2026-10-09T00:00:00Z")
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse((root / "architecture").exists())

    def test_audit_duplicate_report_is_unknown_and_bom_report_is_supported(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            path.write_text('{"问题清单":[],"问题清单":[]}', encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(audit_architecture.main(["report", str(path)]), 2)
            report = audit_architecture.build_questionnaire("fixture")
            for question in report["问题清单"]:
                question.update({"结论": "na", "不适用原因": "明确不在本测试范围"})
            path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8-sig")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(audit_architecture.main(["report", str(path)]), 0)

    def test_missing_regression_text_is_unknown_instead_of_failed_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            output = io.StringIO()
            with redirect_stdout(output):
                code = check_regression_assertions.main(["--scenario", "export", "--file",
                                                          str(Path(td) / "missing.txt"), "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "unknown")

    def test_regression_behavior_and_diff_negative_display_limit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            text = root / "output.txt"
            text.write_text("权限 大数据 失败 审计 测试", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(check_regression_assertions.main(["--scenario", "export", "--file", str(text), "--json"]), 0)
            self.assertTrue(json.loads(output.getvalue())["通过"])
            first, second = root / "old.json", root / "new.json"
            write_json(first, {})
            write_json(second, {"a": 1, "b": 2, "c": 3})
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(diff_architecture.main([str(first), str(second), "--max-items", "-1"]), 1)
            self.assertIn("已截断 3 项", output.getvalue())
            self.assertNotIn("  - ", output.getvalue())


class ProgressWrapperMaintenanceTests(unittest.TestCase):
    def test_external_absolute_traversal_private_and_self_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            external = Path(td) / "external.py"
            external.write_text("raise RuntimeError('must never execute')", encoding="utf-8")
            for name in [str(external), "../../external.py", "..\\outside.py", "_archlib.py", "run_with_progress.py", "not-python.txt"]:
                with self.subTest(name=name), patch.object(run_with_progress.subprocess, "run",
                                                           side_effect=AssertionError("external code executed")):
                    success, message = run_with_progress.run_script_with_feedback(name, [], "test")
                    self.assertFalse(success)
                    self.assertIn("同目录", message)

    def test_public_tool_argument_order_and_child_failure_semantics_remain(self):
        completed = subprocess.CompletedProcess([], 2, "unknown", "input unavailable")
        with patch.object(run_with_progress.subprocess, "run", return_value=completed) as run, redirect_stdout(io.StringIO()):
            success, error = run_with_progress.run_script_with_feedback("validate_architecture.py", ["input.json", "--json"], "验证")
        self.assertFalse(success)
        self.assertEqual(error, "input unavailable")
        self.assertEqual(run.call_args.args[0][-2:], ["input.json", "--json"])

    def test_progress_help_and_detector_help_exit_before_project_operations(self):
        for name in ["run_with_progress.py", "detect_should_trigger.py"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                result = subprocess.run([sys.executable, "-B", str(SCRIPTS / name), "--help"], cwd=td,
                                        capture_output=True, text=True, encoding="utf-8",
                                        env=dict(os.environ, TASK_ARCH_AUTO_TRIGGER="off", PYTHONDONTWRITEBYTECODE="1"))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())
                self.assertEqual(list(Path(td).iterdir()), [])

    def test_detector_missing_project_is_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "detect_should_trigger.py"),
                                     "--project", str(Path(td) / "absent")], capture_output=True,
                                    text=True, encoding="utf-8", env=dict(os.environ, TASK_ARCH_AUTO_TRIGGER="1"))
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


class RenderOutputMaintenanceTests(unittest.TestCase):
    def run_render(self, architecture, output):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "render_architecture.py"),
                               str(architecture), "--format", "html", "--output", str(output)],
                              capture_output=True, text=True, encoding="utf-8",
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1"))

    def fixture(self, root):
        architecture = root / "architecture.json"
        source = root / "source.未知语言"
        document = module_document()
        document["实现清单"]["root"]["文件列表"] = [source.name]
        write_json(architecture, document)
        source.write_bytes(b"opaque source\xff\x00\r\n")
        return architecture, source

    def test_real_render_cli_refuses_architecture_and_registered_source_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            architecture, source = self.fixture(root)
            before = {architecture: architecture.read_bytes(), source: source.read_bytes()}
            for output in [architecture, source]:
                with self.subTest(output=output):
                    result = self.run_render(architecture, output)
                    self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertIn("不得覆盖", result.stderr)
                    for path, raw in before.items():
                        self.assertEqual(path.read_bytes(), raw)

    def test_real_render_cli_generates_html_preserving_architecture_and_opaque_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            architecture, source = self.fixture(root)
            before = {architecture: architecture.read_bytes(), source: source.read_bytes()}
            output = root / "views" / "project.html"
            result = self.run_render(architecture, output)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            html = output.read_text(encoding="utf-8")
            self.assertIn("<!doctype html", html.lower())
            self.assertIn("source.未知语言", html)
            self.assertIn("模块路由", html)
            for path, raw in before.items():
                self.assertEqual(path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
