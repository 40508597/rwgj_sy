"""Language-neutral inventory regression cases; never execute project artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(os.environ.get("TASKARCH_PACKAGE", str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(PACKAGE / "shared/scripts"))
import scan_code_drift as scanner
import _archlib


class UniversalInventory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".tmp-inventory-", dir=PACKAGE.parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.arch = self.root / "architecture.json"

    def write_arch(self, entries=None, *, data=None):
        if data is None:
            data = {"实现清单": {"module": {"文件列表": entries or []}}}
        self.arch.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def artifact(self, name, content=b"\x00\xff\x80binary-artifact"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def scan(self, **kwargs):
        return scanner.scan_code_drift(self.root, self.arch, scanner.DEFAULT_EXTENSIONS, **kwargs)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(PACKAGE / "shared/scripts/scan_code_drift.py"),
             str(self.root), "--json", *map(str, args)],
            capture_output=True, encoding="utf-8", timeout=20,
        )

    def test_missing_e_language_string_is_found_in_legacy_mode(self):
        self.write_arch(["易语言/订单工程.e"])
        result = self.scan()
        self.assertEqual(result["声明但不存在"], ["易语言/订单工程.e"])
        self.assertEqual(result["扫描范围"]["模式"], "legacy-extensions")

    def test_missing_extensionless_object_is_found(self):
        self.write_arch([{"路径": "组件/启动入口"}])
        self.assertEqual(self.scan()["声明但不存在"], ["组件/启动入口"])

    def test_arbitrary_binary_engineering_artifacts_are_registered(self):
        names = ["工程/可视化项目.vendor-binary", "易语言/主程序.e", "构建入口"]
        for name in names:
            self.artifact(name)
        self.write_arch([names[0], {"路径": names[1]}, names[2]])
        result = self.scan(all_files=True)
        self.assertEqual(result["声明但不存在"], [])
        self.assertEqual(result["存在但未登记"], [])
        self.assertEqual(result["已登记代码文件"], sorted(names))

    def test_all_files_detects_unregistered_unknown_suffix_and_no_suffix(self):
        names = ["中文目录/未登记.e", "无后缀入口", "source.surprising"]
        for name in names:
            self.artifact(name)
        self.write_arch()
        result = self.scan(all_files=True)
        self.assertEqual(result["存在但未登记"], sorted(names))
        self.assertIsNone(result["扫描范围"]["扩展名"])
        self.assertEqual(result["扫描范围"]["检查内容"], "file-inventory-only")

    def test_empty_file_is_included_by_all_files(self):
        self.artifact("空工程.e", b"")
        self.write_arch()
        self.assertEqual(self.scan(all_files=True)["存在但未登记"], ["空工程.e"])

    def test_empty_file_retains_legacy_exclusion(self):
        self.artifact("empty.py", b"")
        self.write_arch()
        self.assertEqual(self.scan()["存在但未登记"], [])

    def test_declared_empty_file_exists_in_both_modes(self):
        self.artifact("empty-project.e", b"")
        self.write_arch(["empty-project.e"])
        self.assertEqual(self.scan()["声明但不存在"], [])
        self.assertEqual(self.scan(all_files=True)["声明但不存在"], [])

    def test_explicit_filter_never_suppresses_missing_registered_file(self):
        self.write_arch(["missing.e", "无后缀"])
        self.artifact("exists.py")
        self.artifact("untracked.e")
        result = scanner.scan_code_drift(self.root, self.arch, {".py"}, explicit_extensions=True)
        self.assertEqual(result["声明但不存在"], ["missing.e", "无后缀"])
        self.assertEqual(result["存在但未登记"], ["exists.py"])
        self.assertEqual(result["扫描范围"]["模式"], "explicit-extensions")

    def test_legacy_extensions_do_not_include_unregistered_e_file(self):
        self.artifact("project.e")
        self.write_arch()
        self.assertEqual(self.scan()["存在但未登记"], [])
        self.assertIn(".py", self.scan()["扫描范围"]["扩展名"])

    def test_alternative_file_key_supports_strings_and_objects(self):
        self.write_arch(data={"实现清单": {"m": {"文件": ["a.e", {"路径": "b"}]}}})
        self.assertEqual(self.scan()["声明但不存在"], ["a.e", "b"])

    def test_both_file_fields_are_checked(self):
        self.write_arch(data={"实现清单": {"m": {"文件列表": ["a.e"], "文件": ["b"]}}})
        self.assertEqual(self.scan()["声明但不存在"], ["a.e", "b"])

    def test_backslash_paths_are_normalized(self):
        self.artifact("模块/项目.e")
        self.write_arch([{"路径": "模块\\项目.e"}])
        result = self.scan(all_files=True)
        self.assertEqual(result["已登记代码文件"], ["模块/项目.e"])
        self.assertEqual(result["存在但未登记"], [])

    def test_declared_files_accept_same_directory_path_alias(self):
        alias = self.base / "SHORT~1"
        canonical = self.base / "canonical-directory"
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            if path == alias or alias in path.parents:
                return canonical / path.relative_to(alias)
            return original_resolve(path, *args, **kwargs)

        data = {"实现清单": {"module": {"文件列表": ["bin/入口.custom"]}}}
        with mock.patch.object(Path, "resolve", resolve):
            self.assertEqual(scanner.collect_declared_files(data, alias), {"bin/入口.custom"})

    def test_directory_alias_does_not_allow_resolved_external_target(self):
        alias = self.base / "SHORT~1"
        canonical = self.base / "canonical-directory"
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            if path == alias:
                return canonical
            if alias in path.parents:
                return self.base / "outside" / path.relative_to(alias)
            return original_resolve(path, *args, **kwargs)

        data = {"实现清单": {"module": {"文件列表": ["bin/入口.custom"]}}}
        with mock.patch.object(Path, "resolve", resolve):
            with self.assertRaises(_archlib.ArchitectureInputError):
                scanner.collect_declared_files(data, alias)

    def test_registered_directory_is_not_accepted_as_a_file(self):
        (self.root / "工程.e").mkdir()
        self.write_arch(["工程.e"])
        self.assertEqual(self.scan()["声明但不存在"], ["工程.e"])

    def test_declared_relative_escape_is_rejected(self):
        (self.base / "outside.e").write_bytes(b"outside")
        self.write_arch(["../outside.e"])
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "越出"):
            self.scan(all_files=True)

    def test_absolute_and_drive_relative_manifest_paths_are_rejected(self):
        for value in (str(self.root / "absolute.e"), "C:project.e", "\\\\server\\share\\project.e"):
            with self.subTest(value=value):
                self.write_arch([value])
                with self.assertRaisesRegex(_archlib.ArchitectureInputError, "相对路径"):
                    self.scan()

    def test_bad_manifest_types_return_explainable_exit_two(self):
        malformed = [
            [], {"实现清单": []}, {"实现清单": {"m": []}},
            {"实现清单": {"m": {"文件列表": "a.e"}}},
            {"实现清单": {"m": {"文件列表": [None]}}},
            {"实现清单": {"m": {"文件列表": [17]}}},
            {"实现清单": {"m": {"文件列表": [{}]}}},
            {"实现清单": {"m": {"文件列表": [{"路径": []}]}}},
        ]
        for data in malformed:
            with self.subTest(data=data):
                self.write_arch(data=data)
                result = self.cli("--all-files")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("ERROR:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_nul_and_newline_declarations_are_rejected(self):
        for value in ("bad\x00.e", "a\nb.e", "a\rb.e", ""):
            with self.subTest(value=value):
                self.write_arch([value])
                with self.assertRaisesRegex(_archlib.ArchitectureInputError, "非空路径"):
                    self.scan()

    def test_pointer_escape_is_rejected_before_loading_target(self):
        (self.base / "outside.json").write_text("not json", encoding="utf-8")
        self.write_arch(data={"指向": "../outside.json"})
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "越出"):
            self.scan()

    def test_pointer_parent_reference_inside_project_is_allowed(self):
        self.write_arch(["missing.e"])
        pointer = self.root / "metadata/pointer.json"
        pointer.parent.mkdir()
        pointer.write_text(json.dumps({"指向": "../architecture.json"}), encoding="utf-8")
        result = scanner.scan_code_drift(self.root, pointer, scanner.DEFAULT_EXTENSIONS)
        self.assertEqual(result["声明但不存在"], ["missing.e"])

    def test_enabled_slice_escape_and_nul_are_rejected(self):
        for value in ("../outside.json", "architecture/\x00slice.json"):
            with self.subTest(value=value):
                self.write_arch(data={"架构切片": {"启用": True, "切片清单": [{"路径": value}]}})
                with self.assertRaises(_archlib.ArchitectureInputError):
                    self.scan()

    def test_missing_enabled_slice_is_unknown_input(self):
        self.write_arch(data={"架构切片": {"启用": True, "切片清单": [{"路径": "architecture/missing.json"}]}})
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("切片不存在", result.stderr)

    def test_pointer_index_slice_declares_arbitrary_file(self):
        index = self.root / "architecture/index.json"
        index.parent.mkdir()
        index.write_text(json.dumps({"架构切片": {"启用": True, "切片清单": [{"路径": "architecture/module.json"}]}}), encoding="utf-8")
        (index.parent / "module.json").write_text(json.dumps({"实现清单": {"m": {"文件列表": ["工程.e"]}}}), encoding="utf-8")
        self.write_arch(data={"指向": "architecture/index.json"})
        self.assertEqual(self.scan(all_files=True)["声明但不存在"], ["工程.e"])

    def test_external_architecture_file_is_rejected(self):
        outside = self.base / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(_archlib.ArchitectureInputError, "越出"):
            scanner.scan_code_drift(self.root, outside, scanner.DEFAULT_EXTENSIONS)

    def test_all_files_scope_exclusions_are_reported(self):
        for name in ("architecture/private.e", ".git/internal", "build/output.e", ".tmp-work.e"):
            self.artifact(name)
        self.write_arch()
        result = self.scan(all_files=True)
        self.assertEqual(result["存在但未登记"], [])
        self.assertIn("architecture", result["扫描范围"]["忽略目录"])
        self.assertIn(".tmp-", result["扫描范围"]["忽略文件前缀"])

    def test_registered_files_inside_excluded_directory_still_checked(self):
        self.write_arch(["build/missing.e"])
        self.assertEqual(self.scan(all_files=True)["声明但不存在"], ["build/missing.e"])

    def test_cli_flags_and_exit_codes(self):
        self.write_arch()
        self.assertEqual(self.cli("--all-files").returncode, 0)
        self.artifact("new.e")
        result = self.cli("--all-files")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["扫描范围"]["模式"], "all-files")
        result = self.cli("--extensions", ".py")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["扫描范围"]["模式"], "explicit-extensions")
        self.assertEqual(self.cli("--all-files", "--extensions", ".py").returncode, 2)

    def test_repeat_scan_is_deterministic_and_never_reads_artifact_content(self):
        self.artifact("工程.e", b"\xff\x00\xfe" * 100)
        self.artifact("无后缀", b"\x80")
        self.write_arch(["工程.e"])
        first = self.scan(all_files=True)
        self.assertEqual(first, self.scan(all_files=True))
        self.assertEqual(first["存在但未登记"], ["无后缀"])


if __name__ == "__main__":
    unittest.main()
