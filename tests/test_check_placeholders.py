"""check_placeholders.py 单元测试（stdlib unittest，无外部依赖）"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import check_placeholders  # noqa: E402

EXAMPLE = REPO_ROOT / "shared" / "assets" / "example-architecture.json"
TEMPLATE = REPO_ROOT / "shared" / "assets" / "architecture-template-with-placeholders.json"


def write_json(tmpdir: str, data: dict) -> Path:
    p = Path(tmpdir) / "arch.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


class TestCheckPlaceholders(unittest.TestCase):
    def test_example_passes(self):
        """完整示例应无占位符，返回 0。"""
        self.assertEqual(check_placeholders.main([str(EXAMPLE)]), 0)

    def test_template_blocked(self):
        """带占位符模板必须被拦截（F 机制有效）。"""
        self.assertEqual(check_placeholders.main([str(TEMPLATE)]), 1)

    def test_core_value_placeholder_returns_1(self):
        """core 字段 value 占位符 → critical → 返回 1。"""
        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            data["项目"]["名称"] = "__待填__"
            self.assertEqual(check_placeholders.main([str(write_json(td, data))]), 1)

    def test_missing_core_field_returns_1(self):
        """schema 标 core 的顶层字段整段缺失 → critical → 返回 1。"""
        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            del data["功能树"]
            self.assertEqual(check_placeholders.main([str(write_json(td, data))]), 1)

    def test_placeholder_key_blocked(self):
        """__示例模块名__ 等示例 key 残留 → critical（防生成假模块）。"""
        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            data["模块详情"]["__示例模块名__"] = {"职责": "x"}
            self.assertEqual(check_placeholders.main([str(write_json(td, data))]), 1)

    def test_incomplete_module_detail_blocked(self):
        """模块详情对象缺 14 项底线子字段 → critical。"""
        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            data["模块详情"]["m_user"] = {"职责": "x"}
            self.assertEqual(check_placeholders.main([str(write_json(td, data))]), 1)

    def test_strict_mode_flags_important(self):
        """普通模式忽略 important 档占位符，--strict 下返回 1。"""
        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            data["交付物"].append("__待填__")  # 交付物 = important 顶层字段
            p = write_json(td, data)
            self.assertEqual(check_placeholders.main([str(p)]), 0)
            self.assertEqual(check_placeholders.main([str(p), "--strict"]), 1)

    def test_json_output_contract(self):
        """--json 输出含 status/critical/important/optional 契约字段。"""
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as td:
            data = load_example()
            data["项目"]["名称"] = "__待填__"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = check_placeholders.main([str(write_json(td, data)), "--json"])
            self.assertEqual(rc, 1)
            result = json.loads(buf.getvalue())
            self.assertEqual(result["status"], "incomplete")
            self.assertIn("critical", result)
            self.assertIn("next_steps", result)


if __name__ == "__main__":
    unittest.main()
