"""CLI checks for the capability boundary, retained evidence and stage changes."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / 'shared' / 'scripts'))
import manage_state
import validate_agent_output
import check_capability_usage


class CapabilityBoundaryIntegration(unittest.TestCase):
    def setUp(self):
        # A full package contains deeply nested upstream references. Anchor the
        # disposable fixture beside the package, independent of a host's long
        # TEMP path, and keep fixture components short for legacy Win32 APIs.
        self.temp = tempfile.TemporaryDirectory(prefix='ta-', dir=PACKAGE.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def output_cli(self, value):
        path = self.root / '报告.资料'
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        proc = subprocess.run([sys.executable, '-B', '-X', 'utf8',
            str(PACKAGE / 'shared/scripts/validate_agent_output.py'), str(path), '--json'],
            capture_output=True, text=True, encoding='utf-8', timeout=15)
        return proc.returncode, json.loads(proc.stdout)

    def test_zero_findings_is_allowed_with_evidence(self):
        code, result = self.output_cli({'输出类型': '验证报告', '结论': '通过',
            '证据': ['已对当前两个输入逐项审查，未发现可复现问题'], '问题清单': []})
        self.assertEqual(code, 0, result)

    def test_empty_or_whitespace_evidence_cannot_claim_pass(self):
        for evidence in [[], [' '], [{'命令': ''}], [None]]:
            with self.subTest(evidence=evidence):
                code, result = self.output_cli({'输出类型': '验证报告', '结论': '通过', '证据': evidence})
                self.assertEqual(code, 1, result)

    def test_unknown_report_is_structurally_valid_without_a_false_pass(self):
        code, result = self.output_cli({'输出类型': '验证报告', '结论': '降级执行',
            '未验证项': ['缺少当前语言的覆盖率采集器'], '下一步': ['接入项目支持的实际采集器']})
        self.assertEqual(code, 0, result)

    def test_pass_with_unverified_items_is_rejected(self):
        code, result = self.output_cli({'输出类型': '门禁结果', '结论': '通过',
            '证据': ['结构检查运行记录'], '未验证项': ['执行未发生']})
        self.assertEqual(code, 1, result)

    def test_nested_scope_types_and_project_escape_are_rejected(self):
        for scope in [{'文件': 42}, {'模块': [None]}, {'文件': ['../outside']},
                      {'文件': [r'C:\outside\file']}, {'文件': ['/outside']}, {'接口': [' ']}]:
            with self.subTest(scope=scope):
                code, result = self.output_cli({'输出类型': '模块提案', '结论': '通过', '负责范围': scope})
                self.assertEqual(code, 1, result)

    def test_arbitrary_suffix_and_extensionless_scope_are_accepted(self):
        code, result = self.output_cli({'输出类型': '模块提案', '结论': '通过',
            '负责范围': {'文件': ['规则/计算.自定义语法', 'ship', '资料/运行 说明']}})
        self.assertEqual(code, 0, result)

    def test_malformed_enum_values_do_not_crash(self):
        for value in [[], {}, 42, None]:
            with self.subTest(value=value):
                code, result = self.output_cli({'输出类型': value, '结论': value})
                self.assertEqual(code, 1, result)

    def test_current_stage_advances_after_direct_completion_and_reopens(self):
        path = self.root / '_state.json'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(manage_state.main(['init', '--state-path', str(path)]), 0)
            self.assertEqual(manage_state.main(['update', '需求理解', 'completed', '--state-path', str(path)]), 0)
            self.assertEqual(manage_state.load_state(path)['current_stage'], '功能树')
            for stage in manage_state.STANDARD_STAGES:
                self.assertEqual(manage_state.main(['update', stage['id'], 'completed', '--state-path', str(path)]), 0)
            self.assertEqual(manage_state.load_state(path)['current_stage'], '验证证据')
            self.assertEqual(manage_state.main(['update', '模块详情', 'pending', '--state-path', str(path)]), 0)
            self.assertEqual(manage_state.load_state(path)['current_stage'], '模块详情')

    def test_explicit_active_stage_survives_other_stage_completion(self):
        path = self.root / '_state.json'
        with contextlib.redirect_stdout(io.StringIO()):
            manage_state.main(['init', '--state-path', str(path)])
            manage_state.main(['update', '模块详情', 'in_progress', '--state-path', str(path)])
            manage_state.main(['update', '功能树', 'completed', '--state-path', str(path)])
        self.assertEqual(manage_state.load_state(path)['current_stage'], '模块详情')

    def test_scope_globs_are_component_bounded_and_language_independent(self):
        matcher = check_capability_usage.in_file_scope
        self.assertTrue(matcher('bin/rulecli', ['bin/*'], self.root))
        self.assertFalse(matcher('bin/child/rulecli', ['bin/*'], self.root))
        self.assertTrue(matcher('rules/累计规则.规', ['rules/??规则.规'], self.root))
        self.assertTrue(matcher('architecture/tasks/deep/state.json', ['architecture/**'], self.root))
        self.assertTrue(matcher('state.json', ['**/state.json'], self.root))
        self.assertFalse(matcher('architecture-sibling/state.json', ['architecture/**'], self.root))
        self.assertTrue(matcher('pages/[id].tsx', ['pages/*'], self.root))
        self.assertFalse(matcher('src-sibling/file', ['src/'], self.root))
        with self.assertRaises(check_capability_usage.Invalid):
            matcher('../outside', ['**'], self.root)

    def test_receipt_cli_help_does_not_require_a_command(self):
        proc = subprocess.run([sys.executable, '-B', '-X', 'utf8',
            str(PACKAGE / 'shared/scripts/run_verification.py'), '--help'],
            capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('--input', proc.stdout)

    def test_complete_package_regression_is_independent_of_long_host_temp(self):
        long_temp = self.root / ("host-temp-" + "x" * 70)
        long_temp.mkdir()
        # The host temp is valid but would push the full upstream paths beyond
        # 260 characters with the old fixture prefix and package directory.
        longest_relative = max(len(str(path.relative_to(PACKAGE)))
                               for path in (PACKAGE / "shared/subskills").rglob("*") if path.is_file())
        old_fixture_overhead = len("taskarch-cap-boundary-") + 8 + len("/package/")
        self.assertGreater(len(str(long_temp)) + old_fixture_overhead + longest_relative, 260)
        with patch.object(tempfile, "tempdir", str(long_temp)):
            nested = type(self)("test_capability_integrity_check_detects_missing_and_broken_refs")
            try:
                nested.setUp()
                self.assertEqual(nested.root.parent, PACKAGE.parent)
                nested.test_capability_integrity_check_detects_missing_and_broken_refs()
            finally:
                nested.doCleanups()

    def test_capability_integrity_check_detects_missing_and_broken_refs(self):
        copied = self.root / 'p'
        shutil.copytree(PACKAGE, copied, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        command = [sys.executable, '-B', '-X', 'utf8', str(PACKAGE / 'scripts/validate_task_architecture_system.py'), str(copied)]
        baseline = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
        ref = copied / 'shared/references/capability-index.md'
        before = ref.read_bytes()
        ref.unlink()
        missing = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(missing.returncode, 1, missing.stdout + missing.stderr)
        ref.write_bytes(before)
        core = copied / 'skills/project-depth-core/CORE.md'
        core.write_text(core.read_text(encoding='utf-8').replace('capability-index.md', 'does-not-exist.md'), encoding='utf-8')
        broken = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(broken.returncode, 1, broken.stdout + broken.stderr)


if __name__ == '__main__':
    unittest.main()
