"""_archlib.py 单元测试（指针解析 / 项目根推断 / IO 错误翻译 / 实现清单收集）"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import _archlib  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
