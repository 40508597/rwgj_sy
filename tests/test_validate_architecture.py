"""validate_architecture.py 单元测试（stdlib unittest，无外部依赖）"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import validate_architecture  # noqa: E402

EXAMPLE = REPO_ROOT / "shared" / "assets" / "example-architecture.json"
TEMPLATE = REPO_ROOT / "shared" / "assets" / "architecture-template-with-placeholders.json"


def write_json(tmpdir: str, data: dict) -> Path:
    p = Path(tmpdir) / "arch.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


class TestValidateArchitecture(unittest.TestCase):
    def test_example_passes(self):
        self.assertEqual(validate_architecture.main([str(EXAMPLE)]), 0)

    def test_missing_core_section_fails(self):
        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            del data["功能树"]
            self.assertEqual(validate_architecture.main([str(write_json(td, data))]), 1)

    def test_json_output_contract(self):
        """--json 输出含 错误/警告 契约字段，错误时 rc=1。"""
        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            del data["功能树"]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = validate_architecture.main([str(write_json(td, data)), "--json"])
            self.assertEqual(rc, 1)
            result = json.loads(buf.getvalue())
            self.assertIn("错误", result)
            self.assertIn("警告", result)
            self.assertTrue(result["错误"])

    def test_skeleton_stage_tolerates_missing_details(self):
        """--stage skeleton 容忍 模块详情/接口契约 等细节缺失（不报 error）。"""
        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            data.pop("模块详情", None)
            data.pop("接口契约", None)
            self.assertEqual(validate_architecture.main(
                [str(write_json(td, data)), "--stage", "skeleton"]), 0)


if __name__ == "__main__":
    unittest.main()
