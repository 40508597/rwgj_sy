"""resolve_tool.py 单元测试（stdlib unittest，无外部依赖）

回归重点：`--list` 在「非受管目录」（自 cwd 向上找不到 architecture.json 或
architecture/ 锚点）下不得崩溃——历史 bug 是项目级脚本目录返回 None 时直接调用
`None.is_dir()`，抛 AttributeError。未受管目录属常态，不是错误。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import resolve_tool  # noqa: E402


@contextlib.contextmanager
def chdir(path: Path):
    """临时切换工作目录（main() 以 Path.cwd() 作为解析起点）。"""
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run_main(argv: list[str]) -> tuple[int, str]:
    """调用 main() 并合并捕获 stdout/stderr，返回 (退出码, 文本)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = resolve_tool.main(argv)
    return code, buf.getvalue()


class TestResolveTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        # 非受管目录：无 architecture.json / architecture/
        self.unmanaged = root / "unmanaged"
        self.unmanaged.mkdir()
        # 受管目录：有 architecture/ 锚点 + 项目级脚本
        self.managed = root / "managed"
        self.managed_scripts = self.managed / "shared" / "scripts"
        self.managed_scripts.mkdir(parents=True)
        (self.managed / "architecture").mkdir()
        (self.managed_scripts / "project_only_tool.py").write_text(
            "# 项目级工具\n", encoding="utf-8")

    def test_list_outside_project_anchor_does_not_crash(self):
        """非受管目录下 --list 退出码 0，只列安装级工具（历史崩溃点）。"""
        with chdir(self.unmanaged):
            if resolve_tool.find_project_root(Path.cwd()) is not None:
                self.skipTest("临时目录存在受管锚点祖先，无法构造非受管场景")
            code, out = run_main(["--list"])
        self.assertEqual(code, 0)
        self.assertIn("[install]", out)
        self.assertIn("validate_architecture.py", out)
        self.assertNotIn("[project]", out)

    def test_list_json_outside_project_anchor(self):
        """--json 形态同样不崩溃，且每行 path 指向真实文件。"""
        with chdir(self.unmanaged):
            code, out = run_main(["--list", "--json"])
        self.assertEqual(code, 0)
        rows = json.loads(out)["tools"]
        self.assertTrue(rows)
        self.assertEqual({r["source"] for r in rows}, {"install"})
        for row in rows:
            self.assertTrue(Path(row["path"]).is_file(), row["path"])

    def test_list_includes_project_tools_when_anchored(self):
        """受管目录下 --list 同时列出项目级与安装级工具。"""
        with chdir(self.managed):
            code, out = run_main(["--list"])
        self.assertEqual(code, 0)
        self.assertIn("[project]", out)
        self.assertIn("project_only_tool.py", out)
        self.assertIn("[install]", out)

    def test_resolve_prefers_project_over_install(self):
        """同名工具存在时，项目级优先于安装级。"""
        project_copy = self.managed_scripts / "validate_architecture.py"
        project_copy.write_text("# 项目级覆盖\n", encoding="utf-8")
        with chdir(self.managed):
            code, out = run_main(["--json", "validate_architecture"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["found"])
        self.assertEqual(data["source"], "project")
        self.assertEqual(Path(data["path"]), project_copy.resolve())

    def test_resolve_falls_back_to_install(self):
        """项目级缺失时回退安装目录，.py 后缀可省略。"""
        with chdir(self.unmanaged):
            code, out = run_main(["--json", "validate_architecture"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["source"], "install")
        self.assertEqual(Path(data["path"]).name, "validate_architecture.py")
        self.assertTrue(Path(data["path"]).is_file())

    def test_resolve_missing_tool_returns_1(self):
        """两处都不存在时退出码 1，并给出降级提示。"""
        with chdir(self.unmanaged):
            code, out = run_main(["no_such_tool_xyz"])
        self.assertEqual(code, 1)
        self.assertIn("未找到", out)

    def test_directory_named_like_script_does_not_shadow_install(self):
        (self.managed_scripts / "validate_architecture.py").mkdir()
        with chdir(self.managed):
            code, out = run_main(["--json", "validate_architecture"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["source"], "install")

    def test_list_excludes_directories_named_like_scripts(self):
        (self.managed_scripts / "not_a_tool.py").mkdir()
        with chdir(self.managed):
            code, out = run_main(["--list", "--json"])
        self.assertEqual(code, 0)
        self.assertNotIn("not_a_tool.py", {row["name"] for row in json.loads(out)["tools"]})

    def test_nested_working_directory_finds_project_override(self):
        nested = self.managed / "src" / "feature"
        nested.mkdir(parents=True)
        with chdir(nested):
            code, out = run_main(["--json", "project_only_tool"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["source"], "project")

    def test_rejects_path_traversal(self):
        """含路径分隔符或 .. 的入参一律拒绝（退出码 2）。"""
        with chdir(self.unmanaged):
            for bad in ("../evil.py", "sub/dir.py", "..\\evil.py"):
                with self.subTest(arg=bad):
                    code, _ = run_main([bad])
                    self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
