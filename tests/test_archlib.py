"""_archlib.py 单元测试（指针解析 / 项目根推断 / IO 错误翻译 / 实现清单收集）"""

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import _archlib  # noqa: E402
import _architecture_core as core


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestLoadArchitectureJson(unittest.TestCase):
    def test_pointer_following(self):
        """architecture.json 指针 → 指向 architecture/index.json。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture").mkdir()
            write_json(root / "architecture.json", {"指向": "architecture/index.json"})
            write_json(root / "architecture" / "index.json", {"项目": {"名称": "x"}})
            data = _archlib.load_architecture_json(root / "architecture.json")
            self.assertEqual(data["项目"]["名称"], "x")

    def test_inline_single_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "arch.json"
            write_json(p, {"项目": {"名称": "x"}})
            self.assertEqual(_archlib.load_architecture_json(p)["项目"]["名称"], "x")

    def test_pointer_single_file_dependency_diagnostics_have_original_sha(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture").mkdir()
            write_json(root / "architecture.json", {"指向": "architecture/index.json"})
            path = root / "architecture/index.json"
            value = {"模块详情": {"a": {"上游依赖": [{"模块编号": "b", "编号": "c"}]}}}
            write_json(path, value)
            view = _archlib.load_architecture_json(root / "architecture.json")
            self.assertEqual(view, value)
            self.assertEqual(json.dumps(view, sort_keys=True), json.dumps(value, sort_keys=True))
            diagnostic = core.declared_dependencies(view)["diagnostics"][0]
            self.assertEqual((diagnostic["file"], diagnostic["pointer"], diagnostic["sha256"]),
                             ("architecture/index.json", "/模块详情/a/上游依赖/0",
                              hashlib.sha256(path.read_bytes()).hexdigest()))
            self.assertNotIn("value", diagnostic)

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                _archlib.load_architecture_json(Path(td) / "nope.json")

    def test_bad_json_raises(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("{bad json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                _archlib.load_architecture_json(p)

    def test_bom_tolerated(self):
        """utf-8-sig 读取：带 BOM 的文件应正常解析。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bom.json"
            p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"项目": {"名称": "x"}}, ensure_ascii=False).encode("utf-8"))
            self.assertEqual(_archlib.load_architecture_json(p)["项目"]["名称"], "x")


class TestProjectRootForArchitecture(unittest.TestCase):
    def test_index_in_architecture_dir(self):
        self.assertEqual(
            _archlib.project_root_for_architecture(Path("proj/architecture/index.json")),
            Path("proj"))

    def test_single_file(self):
        self.assertEqual(
            _archlib.project_root_for_architecture(Path("proj/architecture.json")),
            Path("proj"))


class TestRunWithIoErrors(unittest.TestCase):
    def test_success(self):
        result, err, code = _archlib.run_with_io_errors(lambda: 42)
        self.assertEqual((result, err, code), (42, None, 0))

    def test_missing_file_translated(self):
        def boom():
            raise FileNotFoundError("x.json")
        result, err, code = _archlib.run_with_io_errors(boom)
        self.assertIsNone(result)
        self.assertEqual(code, 2)
        self.assertIn("文件不存在", err)

    def test_bad_json_translated(self):
        def boom():
            raise json.JSONDecodeError("bad", "doc", 0)
        result, err, code = _archlib.run_with_io_errors(boom)
        self.assertEqual(code, 2)
        self.assertIn("JSON 语法错误", err)

    def test_other_errors_reraised(self):
        def boom():
            raise ValueError("其它错误不应被吞掉")
        with self.assertRaises(ValueError):
            _archlib.run_with_io_errors(boom)


class TestCollectImplementationFiles(unittest.TestCase):
    def test_collects_forward_and_backslash_paths(self):
        data = {"实现清单": {"m": {"文件列表": [{"路径": "src/a.py"}, {"路径": "src\\b.py"}]}}}
        self.assertEqual(
            _archlib.collect_implementation_files(data), {"src/a.py", "src/b.py"})

    def test_accepts_files_alias(self):
        data = {"实现清单": {"m": {"文件": [{"路径": "src/a.py"}]}}}
        self.assertEqual(_archlib.collect_implementation_files(data), {"src/a.py"})

    def test_empty_manifest(self):
        self.assertEqual(_archlib.collect_implementation_files({"实现清单": {}}), set())
        self.assertEqual(_archlib.collect_implementation_files({}), set())


class TestActualFiles(unittest.TestCase):
    def test_filters_and_prunes_dependency_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, content in {"src/app.PY": "pass", "src/empty.py": "",
                                 "src/.tmp-part.py": "pass", "src/readme.txt": "text",
                                 "node_modules/deep/vendor.py": "pass",
                                 "src/build/output.py": "pass"}.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            visited = []
            walk = os.walk

            def tracking_walk(*args, **kwargs):
                for item in walk(*args, **kwargs):
                    visited.append(Path(item[0]).relative_to(root).as_posix())
                    yield item

            with patch.object(_archlib.os, "walk", side_effect=tracking_walk):
                actual = _archlib.collect_actual_files(root, {".py"}, {"node_modules", "build"})
            self.assertEqual(actual, {"src/app.PY"})
            self.assertEqual(set(visited), {".", "src"})

    def test_ignore_names_do_not_hide_project_under_build_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "build" / "project"
            root.mkdir(parents=True)
            (root / "app.py").write_text("pass", encoding="utf-8")
            self.assertEqual(_archlib.collect_actual_files(root, {".py"}, {"build"}), {"app.py"})

    def test_directory_read_error_is_not_a_clean_scan(self):
        def inaccessible(root, *, onerror):
            onerror(PermissionError("denied"))
            return iter(())

        with patch.object(_archlib.os, "walk", side_effect=inaccessible):
            with self.assertRaises(PermissionError):
                _archlib.collect_actual_files(Path("."), {".py"}, set())


class TestSubprocessJson(unittest.TestCase):
    def test_non_json_stdout_keeps_diagnostic(self):
        result = subprocess.CompletedProcess([], 2, "tool failed before JSON", "")
        with patch("subprocess.run", return_value=result):
            self.assertEqual(_archlib.run_subprocess_json(["tool"]),
                             (2, None, "tool failed before JSON"))

    def test_advisory_exit_code_and_json_are_preserved(self):
        result = subprocess.CompletedProcess([], 1, '{"signal": true}', "warning")
        with patch("subprocess.run", return_value=result):
            self.assertEqual(_archlib.run_subprocess_json(["tool"]),
                             (1, {"signal": True}, "warning"))


class TestAdvisoryHelpers(unittest.TestCase):
    """共享底座新增的 advisory 辅助函数（detect_task_posture / detect_small_command 共用）。"""

    def test_load_json_utf8_bom_safe(self):
        with tempfile.TemporaryDirectory() as td:
            plain = Path(td) / "plain.json"
            plain.write_text('{"a": 1}', encoding="utf-8")
            bom = Path(td) / "bom.json"
            bom.write_bytes(b"\xef\xbb\xbf" + '{"a": 1}'.encode("utf-8"))
            self.assertEqual(_archlib.load_json_utf8(plain), {"a": 1})
            self.assertEqual(_archlib.load_json_utf8(bom), {"a": 1})

    def test_load_json_utf8_non_dict_raises(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "list.json"
            p.write_text("[1, 2]", encoding="utf-8")
            with self.assertRaises(ValueError):
                _archlib.load_json_utf8(p)

    def test_collect_matches_case_insensitive(self):
        self.assertEqual(_archlib.collect_matches("启动项目", ["启动", "跑一下"]), ["启动"])

    def test_collect_matches_non_list_returns_empty(self):
        """触发词写成字符串（规则作者笔误）时不得按单字符匹配。"""
        self.assertEqual(_archlib.collect_matches("帮我看看", "看看"), [])
        self.assertEqual(_archlib.collect_matches("帮我看看", None), [])

    def test_collect_matches_skips_non_str_items(self):
        self.assertEqual(_archlib.collect_matches("abc", ["a", 1, "", None]), ["a"])

    def test_contains_any(self):
        self.assertTrue(_archlib.contains_any("删除用户", ["删除"]))
        self.assertFalse(_archlib.contains_any("查询用户", ["删除"]))

    def test_unique_preserves_order(self):
        self.assertEqual(_archlib.unique(["a", "b", "a"]), ["a", "b"])

    def test_is_managed_both_forms(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertFalse(_archlib.is_managed(root))
            (root / "architecture.json").write_text("{}", encoding="utf-8")
            self.assertTrue(_archlib.is_managed(root))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture").mkdir()
            self.assertTrue(_archlib.is_managed(root))


if __name__ == "__main__":
    unittest.main()
