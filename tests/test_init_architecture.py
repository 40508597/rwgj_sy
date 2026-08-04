"""init_architecture.py 单元测试（占位符剥离 / 初始化 / 迁移）"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import init_architecture  # noqa: E402

TIMESTAMP = "2026-01-01T00:00:00+08:00"
SLICE_RELS = [
    "architecture/features/core.json",
    "architecture/modules/structure.json",
    "architecture/pages/delivery.json",
    "architecture/data/data.json",
    "architecture/tasks/state.json",
]


def collect_underscore_keys(node, keys=None):
    """递归收集所有以 __ 开头的 key。"""
    if keys is None:
        keys = []
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and k.startswith("__"):
                keys.append(k)
            collect_underscore_keys(v, keys)
    elif isinstance(node, list):
        for item in node:
            collect_underscore_keys(item, keys)
    return keys


class TestStripTemplateMetadata(unittest.TestCase):
    def test_removes_top_and_nested_underscore_keys(self):
        data = {
            "__注释__": "说明",
            "项目": {"名称": "demo"},
            "模块详情": {"__示例模块名__": {"职责": "x"}},
            "接口契约": {"__示例接口名__": {}},
            "实现清单": {"列表": [{"__占位符说明__": "y"}]},
        }
        init_architecture.strip_template_metadata(data)
        self.assertEqual(collect_underscore_keys(data), [])
        self.assertEqual(data["模块详情"], {})  # 示例 key 清掉后容器为空
        self.assertEqual(data["项目"]["名称"], "demo")  # 真实数据保留


class TestInitEndToEnd(unittest.TestCase):
    def test_init_creates_pointer_index_and_slices(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rc = init_architecture.main([
                "--mode", "init", "--output", str(root),
                "--name", "演示项目", "--project-type", "web",
                "--time", TIMESTAMP,
            ])
            self.assertEqual(rc, 0)
            pointer = root / "architecture.json"
            index = root / "architecture" / "index.json"
            self.assertTrue(pointer.exists())
            self.assertTrue(index.exists())
            for rel in SLICE_RELS:
                self.assertTrue((root / rel).exists(), rel)

            # 指针语义
            self.assertEqual(json.loads(pointer.read_text(encoding="utf-8"))["指向"], "architecture/index.json")
            # 索引无 __ 开头 key（占位符/示例 key 已剥离）
            index_data = json.loads(index.read_text(encoding="utf-8"))
            self.assertEqual(collect_underscore_keys(index_data), [])
            # 切片也无 __ key（模块详情示例 key 被剥离，容器为空）
            modules = json.loads((root / "architecture/modules/structure.json").read_text(encoding="utf-8"))
            self.assertEqual(modules["模块详情"], {})
            self.assertEqual(collect_underscore_keys(modules), [])

    def test_init_refuses_existing_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = ["--mode", "init", "--output", str(root), "--time", TIMESTAMP]
            self.assertEqual(init_architecture.main(args), 0)
            self.assertEqual(init_architecture.main(args), 1)
            self.assertEqual(init_architecture.main(args + ["--force"]), 0)

    def test_migrate_single_file(self):
        """旧单文件迁移：生成指针/索引/切片并归档旧文件。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "old-architecture.json"
            src.write_text((REPO_ROOT / "shared/assets/example-architecture.json").read_text(encoding="utf-8"), encoding="utf-8")
            rc = init_architecture.main([
                "--mode", "migrate", "--from", str(src), "--output", str(root),
                "--time", TIMESTAMP,
            ])
            self.assertEqual(rc, 0)
            self.assertTrue((root / "architecture.json").exists())
            self.assertTrue((root / "architecture/index.json").exists())
            for rel in SLICE_RELS:
                self.assertTrue((root / rel).exists(), rel)
            # 旧文件已归档
            archives = list((root / "architecture/archive").glob("*.json"))
            self.assertEqual(len(archives), 1)
            archived = json.loads(archives[0].read_text(encoding="utf-8"))
            self.assertEqual(archived["项目"]["名称"], "用户管理系统")

    def test_migrate_pointer_input_rejected(self):
        """已是指针的输入不应重复迁移。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "pointer.json"
            src.write_text('{"指向": "architecture/index.json"}', encoding="utf-8")
            rc = init_architecture.main([
                "--mode", "migrate", "--from", str(src), "--output", str(root),
            ])
            self.assertEqual(rc, 2)  # ValueError → 返回 2


if __name__ == "__main__":
    unittest.main()
