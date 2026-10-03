"""Exercise the shipped capability library through observable planning behavior."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / 'shared/scripts'))
import _capabilitylib as lib


class ProgrammingSubskills(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='programming-library-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / 'source').mkdir()
        (self.project / 'source/累计.任意规则').write_text('输入与界面无语言限制', encoding='utf-8')
        (self.project / 'source/ship').write_text('无后缀实现单元', encoding='utf-8')
        self.write(self.project / 'architecture.json', {'功能树': [{'编号': 'f_quota'}],
            '模块拓扑': {'节点': [{'编号': 'm_quota'}]}, '专业能力索引': []})
        self.catalog = PACKAGE / 'shared/assets/capability-catalog.json'
        self.context = {'stage': '模块详情', 'tier': 'full', 'module_ids': ['m_quota'],
            'read_scope': ['source/**'], 'write_scope': [], 'budget': {'max_files': 1, 'max_bytes': 8000},
            'facts': {'has_ui': True, 'web_ui': True, 'browser_tool_available': True, 'known_defect': True}}

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def plan(self, **updates):
        context = {**self.context, **updates}
        path = self.project / 'context.json'
        self.write(path, context)
        return lib.build_plan(self.project, path, self.catalog)

    def test_each_imported_capability_can_be_selected_with_one_minimal_file(self):
        identifiers = ['architecture-patterns', 'architecture-decisions', 'api-contract-design',
            'implementation-planning', 'systematic-debugging', 'behavior-test-design', 'property-testing',
            'api-misuse-review', 'defect-variant-review', 'frontend-visual-design', 'web-ui-review', 'browser-acceptance']
        for identifier in identifiers:
            with self.subTest(identifier=identifier):
                result = self.plan(required_capabilities=[identifier])
                self.assertEqual(result['status'], 'planned', result)
                self.assertEqual([x['id'] for x in result['selected']], [identifier])
                self.assertEqual(len(result['selected'][0]['read_files']), 1)
                self.assertEqual(Path(result['selected'][0]['read_files'][0]['path']).name, 'GUIDE.md')

    def test_cli_combines_architecture_interfaces_and_implementation_plan(self):
        context = {**self.context, 'professional_domains': ['架构设计', '接口设计'],
            'confirmed_capabilities': ['实现任务规划'], 'budget': {'max_files': 3, 'max_bytes': 24000}}
        self.write(self.project / 'context.json', context)
        command = [sys.executable, '-B', '-X', 'utf8', str(PACKAGE / 'shared/scripts/plan_capabilities.py'),
            '--project', str(self.project), '--context', str(self.project / 'context.json')]
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual({x['id'] for x in result['selected']},
            {'architecture-patterns', 'api-contract-design', 'implementation-planning'})

    def test_native_ui_does_not_select_web_only_capabilities(self):
        facts = {**self.context['facts'], 'web_ui': False, 'browser_tool_available': False}
        result = self.plan(confirmed_capabilities=['frontend-visual-design', 'web-ui-review', 'browser-acceptance'],
                           facts=facts)
        self.assertEqual([x['id'] for x in result['selected']], ['frontend-visual-design'])
        self.assertEqual(result['status'], 'unknown')

    def test_browser_available_fact_is_required_for_browser_acceptance(self):
        result = self.plan(required_capabilities=['browser-acceptance'],
            facts={**self.context['facts'], 'browser_tool_available': False})
        self.assertEqual(result['selected'], [])
        self.assertEqual(result['status'], 'unknown')

    def test_real_web_context_can_select_design_review_and_browser_coverage(self):
        result = self.plan(required_capabilities=['frontend-visual-design', 'web-ui-review', 'browser-acceptance'],
                          budget={'max_files': 3, 'max_bytes': 24000})
        self.assertEqual(result['status'], 'planned', result)
        self.assertEqual({x['id'] for x in result['selected']},
                         {'frontend-visual-design', 'web-ui-review', 'browser-acceptance'})
        self.assertTrue(result['planning_only'])

    def test_boolean_availability_cannot_be_forged_with_numbers_or_strings(self):
        for value in [1, 1.0, 'true', '1', None, [], {}, False]:
            with self.subTest(value=value):
                result = self.plan(required_capabilities=['frontend-visual-design'],
                    facts={**self.context['facts'], 'has_ui': value})
                self.assertEqual(result['selected'], [])
                self.assertEqual(result['status'], 'unknown')

    def test_variant_review_needs_an_existing_defect_fact(self):
        result = self.plan(required_capabilities=['defect-variant-review'],
                          facts={**self.context['facts'], 'known_defect': False})
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['selected'], [])

    def test_language_labels_and_arbitrary_suffixes_do_not_change_interface_selection(self):
        for label in ['自定义语法', '未知语言', '易语言', 'C++', '图形规则']:
            with self.subTest(language=label):
                result = self.plan(required_capabilities=['api-contract-design'], language=label)
                self.assertEqual(result['status'], 'planned', result)
                self.assertEqual([x['id'] for x in result['selected']], ['api-contract-design'])

    def test_audit_role_alone_does_not_load_the_library(self):
        result = self.plan(execution_roles=['审计员'], stage='验证')
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(result['selected'], [])

    def test_exclusion_still_blocks_an_imported_required_capability(self):
        result = self.plan(required_capabilities=['property-testing'], excluded_capabilities=['属性与不变量测试'])
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['selected'], [])

    def test_imported_capabilities_cannot_expand_business_write_authority(self):
        result = self.plan(required_capabilities=['systematic-debugging'])
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(result['selected'][0]['write_scope'], [])

    def test_budget_limits_prevent_loading_all_requested_guides(self):
        result = self.plan(required_capabilities=['architecture-patterns', 'implementation-planning'],
                          budget={'max_files': 1, 'max_bytes': 8000})
        self.assertEqual(result['status'], 'unknown')
        self.assertTrue(result['unknown'])


if __name__ == '__main__':
    unittest.main()
