"""diff_architecture.py 单元测试（展平 / 差异检测 / CLI 返回码）"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import diff_architecture  # noqa: E402


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestFlatten(unittest.TestCase):
    def test_nested_dict_and_list(self):
        flat = diff_architecture.flatten({"a": {"b": 1}, "c": [1, 2]})
        self.assertEqual(flat, {"a.b": 1, "c[0]": 1, "c[1]": 2})

    def test_empty_list_keeps_key(self):
        flat = diff_architecture.flatten({"a": []})
        self.assertEqual(flat, {"a": []})


class TestDiffArchitecture(unittest.TestCase):
    def test_added_removed_changed(self):
        old = {"功能树": [{"名称": "导出"}], "项目": {"名称": "A"}, "模块树": []}
        new = {"功能树": [{"名称": "导入"}], "项目": {"名称": "B"}, "数据拓扑": []}
        diff = diff_architecture.diff_architecture(old, new)
        self.assertEqual(diff["新增"], ["数据拓扑"])
        self.assertEqual(diff["删除"], ["模块树"])
        self.assertEqual(len(diff["修改"]), 2)  # 功能树[0].名称 + 项目.名称

    def test_identical_returns_empty(self):
        data = {"项目": {"名称": "A"}}
        diff = diff_architecture.diff_architecture(data, data)
        self.assertEqual(diff, {"新增": [], "删除": [], "修改": []})


class TestMain(unittest.TestCase):
    def test_diff_returns_1_identical_returns_0(self):
        with tempfile.TemporaryDirectory() as td:
            old = Path(td) / "old.json"
            new = Path(td) / "new.json"
            write_json(old, {"项目": {"名称": "A"}})
            write_json(new, {"项目": {"名称": "B"}})
            self.assertEqual(diff_architecture.main([str(old), str(new)]), 1)
            self.assertEqual(diff_architecture.main([str(old), str(old)]), 0)

    def test_json_output_contract(self):
        with tempfile.TemporaryDirectory() as td:
            old = Path(td) / "old.json"
            new = Path(td) / "new.json"
            write_json(old, {"项目": {"名称": "A"}})
            write_json(new, {"项目": {"名称": "B"}})
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = diff_architecture.main([str(old), str(new), "--json"])
            self.assertEqual(rc, 1)
            result = json.loads(buf.getvalue())
            self.assertIn("新增", result)
            self.assertIn("删除", result)
            self.assertIn("修改", result)


if __name__ == "__main__":
    unittest.main()
