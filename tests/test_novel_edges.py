"""Independent edge cases; never writes to the original or optimized skill package.

TASKARCH_PACKAGE may point to either complete package. Failures intentionally
remain ordinary failures so they can be reproduced before a fix is proposed.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(os.environ.get('TASKARCH_PACKAGE', str(Path(__file__).resolve().parents[1])))
SCRIPTS = PACKAGE / 'shared/scripts'
sys.path.insert(0, str(SCRIPTS))
import _archlib
import resolve_tool
import detect_small_command
import manage_state

RULES = json.loads((PACKAGE/'shared/assets/small-command-rules.json').read_text(encoding='utf-8'))


@contextlib.contextmanager
def cwd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class NovelEdges(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='taskarch_novel_')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def managed(self, rel):
        root = self.root/rel
        (root/'architecture').mkdir(parents=True,exist_ok=True)
        return root

    def tool(self, root, name='validate_architecture.py'):
        target = root/'shared/scripts'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('# isolated fixture\n',encoding='utf-8')
        return target

    def resolve(self, root, name):
        with cwd(root), contextlib.redirect_stdout(io.StringIO()) as output:
            code = resolve_tool.main([name,'--json'])
        return code,json.loads(output.getvalue())

    def run_script(self, name, args):
        return subprocess.run([sys.executable,'-B','-X','utf8',str(SCRIPTS/name),*map(str,args)],
                              cwd=self.root,capture_output=True,encoding='utf-8',timeout=15)

    def classify(self, text):
        return detect_small_command.detect_small_command(text,self.managed('project'),RULES)

    def write_state(self, value):
        path=self.root/'state.json'
        path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return path

    def test_N01_nested_managed_root_prefers_child_override(self):
        parent=self.managed('repo')
        child=self.managed('repo/packages/app')
        self.tool(parent)
        own=self.tool(child)
        work=child/'src/components'
        work.mkdir(parents=True)
        code,data=self.resolve(work,'validate_architecture')
        self.assertEqual(code,0)
        self.assertEqual(Path(data['path']),own.resolve())

    def test_N02_child_missing_tool_does_not_inherit_other_project_override(self):
        parent=self.managed('repo')
        child=self.managed('repo/apps/child')
        self.tool(parent)
        code,data=self.resolve(child,'validate_architecture')
        self.assertEqual(code,0)
        self.assertEqual(data['source'],'install')
        self.assertEqual(Path(data['path']), (SCRIPTS/'validate_architecture.py').resolve())

    def test_N03_unicode_space_parentheses_path_roundtrips_in_cli(self):
        project=self.managed('客户 A（试用）/项目 甲')
        expected=self.tool(project)
        run=subprocess.run([sys.executable,'-B','-X','utf8',str(SCRIPTS/'resolve_tool.py'),
                            'validate_architecture','--json'],cwd=project,capture_output=True,
                           encoding='utf-8',timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(Path(json.loads(run.stdout)['path']),expected.resolve())

    def test_N04_negated_edit_then_run_uses_running_loop(self):
        result=self.classify('不要修改代码，只运行现有测试')
        self.assertEqual(result['有效档位'],'最小闭环')
        self.assertEqual(result['闭环类型'],'运行')
        self.assertNotIn('三重校验',result['必须动作'])

    def test_N05_negated_deletion_then_read_keeps_readonly(self):
        result=self.classify('不要删除任何东西，只查看项目日志')
        self.assertEqual(result['有效档位'],'完全跳过')

    def test_N06_quoted_delete_button_label_is_not_delete_operation(self):
        result=self.classify('把按钮文字改为“删除账户”，实际删除逻辑保持原样')
        self.assertEqual(result['有效档位'],'最小闭环')
        self.assertEqual(result['闭环类型'],'修改')

    def test_N07_documented_dangerous_example_is_not_executed(self):
        result=self.classify('只把 README 标题改为“删除生产数据示例”，不要执行任何操作')
        self.assertEqual(result['有效档位'],'最小闭环')

    def test_N08_duplicate_state_stage_is_rejected(self):
        state=manage_state.create_initial_state()
        state['stages'].append(copy.deepcopy(state['stages'][0]))
        with self.assertRaises(ValueError):
            manage_state.load_state(self.write_state(state))

    def test_N09_boolean_revision_is_not_integer_revision(self):
        state=manage_state.create_initial_state()
        state['_meta']['revision']=True
        with self.assertRaises(ValueError):
            manage_state.load_state(self.write_state(state))

    def test_N10_last_stage_complete_does_not_hide_earlier_pending(self):
        state=manage_state.create_initial_state()
        state['stages'][-1]['status']='completed'
        state['current_stage']=state['stages'][-1]['id']
        actions=manage_state.generate_next_actions(state)
        self.assertFalse(any('所有阶段已完成' in str(action) for action in actions),actions)

    def test_N11_malformed_derived_completion_cache_is_rebuilt(self):
        state=manage_state.create_initial_state()
        state['completion']=['stale cache']
        saved=manage_state.load_state(self.write_state(state))
        self.assertEqual(saved['completion']['required_completed'],0)
        self.assertEqual(saved['completion']['required_total'],9)

    def test_N12_identical_project_names_have_independent_states(self):
        a=self.root/'customer-a/app/architecture/_state.json'
        b=self.root/'customer-b/app/architecture/_state.json'
        first=manage_state.create_initial_state('app')
        second=manage_state.create_initial_state('app')
        manage_state.save_state(a,first)
        manage_state.save_state(b,second)
        before=b.read_bytes()
        first['stages'][0]['status']='completed'
        manage_state.save_state(a,first)
        self.assertEqual(b.read_bytes(),before)
        self.assertEqual(manage_state.load_state(b)['completion']['required_completed'],0)

    def test_N13_explicit_force_reset_recovers_malformed_json(self):
        path=self.root/'architecture/_state.json'
        path.parent.mkdir()
        path.write_text('{broken',encoding='utf-8')
        run=self.run_script('manage_state.py',['init','--force','--project-name','repair','--state-path',path])
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(manage_state.load_state(path)['_meta']['project_name'],'repair')

    def assert_clean_input_error(self, content, filename='architecture.json'):
        path=self.root/filename
        if isinstance(content,bytes):
            path.write_bytes(content)
        else:
            path.write_text(content,encoding='utf-8')
        run=self.run_script('validate_architecture.py',[path,'--json'])
        self.assertEqual(run.returncode,2,run.stderr)
        self.assertNotIn('Traceback',run.stderr)

    def test_N14_array_architecture_root_is_clean_input_error(self):
        self.assert_clean_input_error('[]')

    def test_N15_null_architecture_root_is_clean_input_error(self):
        self.assert_clean_input_error('null')

    def test_N16_pointer_to_directory_is_clean_input_error(self):
        (self.root/'architecture').mkdir()
        self.assert_clean_input_error(json.dumps({'指向':'architecture'}))

    def test_N17_invalid_utf8_is_clean_input_error(self):
        self.assert_clean_input_error(b'{"name":"\xff"}')

    def test_N18_corrupt_referenced_slice_is_clean_input_error(self):
        arch=self.root/'architecture'
        arch.mkdir()
        (arch/'broken.json').write_text('{broken',encoding='utf-8')
        (arch/'index.json').write_text(json.dumps({'架构切片':{'启用':True,'切片清单':[
            {'路径':'architecture/broken.json'}]}}),encoding='utf-8')
        self.assert_clean_input_error(json.dumps({'指向':'architecture/index.json'}))

    def test_N19_wrong_topology_nodes_type_does_not_crash_validator(self):
        value=json.loads((PACKAGE/'shared/assets/example-architecture.json').read_text(encoding='utf-8'))
        value['模块拓扑']['节点']=123
        path=self.root/'architecture.json'
        path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        run=self.run_script('validate_architecture.py',[path,'--json'])
        self.assertIn(run.returncode,{1,2})
        self.assertNotIn('Traceback',run.stderr,run.stderr)

    def test_N20_slice_metadata_does_not_leak_into_business_data(self):
        arch=self.root/'architecture'
        arch.mkdir()
        (arch/'one.json').write_text(json.dumps({'项目':{'名称':'hydrated'},
            '切片元信息':{'origin':'fixture'}}),encoding='utf-8')
        index=arch/'index.json'
        index.write_text(json.dumps({'项目':{'名称':'stale'},'架构切片':{'启用':True,
            '切片清单':[{'路径':'architecture/one.json'}]}}),encoding='utf-8')
        value=_archlib.load_architecture_json(index)
        self.assertEqual(value['项目']['名称'],'hydrated')
        self.assertNotIn('切片元信息',value)

    def test_G01_quoted_real_delete_targets_still_require_full_flow(self):
        for text in ('删除“生产数据库”', '运行“删除生产数据”的脚本',
                     '把标题改为“删除”，然后删除“生产数据库”',
                     '把按钮文字改为“删除”并删除“生产数据库”'):
            with self.subTest(text=text):
                result=self.classify(text)
                self.assertEqual(result['有效档位'],'完整流程')
                self.assertEqual(result['风险等级'],'高')

    def test_G02_negation_cannot_hide_positive_continuations(self):
        for text in ('不要修改代码，但是删除生产数据库',
                     '不要修改代码，但直接删除生产数据库',
                     '不要删除生产数据以外的文件',
                     '不要只查看日志，请删除生产数据库',
                     '不要删除旧数据 运行生产迁移脚本',
                     '不要删除代码运行生产迁移脚本',
                     '不要修改代码优化项目'):
            with self.subTest(text=text):
                self.assertEqual(self.classify(text)['有效档位'],'完整流程')

    def test_G03_literal_text_variants_and_punctuation_remain_small_edits(self):
        for text in ('把标题改为“删除生产数据，确认后执行”',
                     '把文案改成"删除生产数据"',
                     "把提示语改为'删除账户'",
                     '把按钮文字改为「删除账户」',
                     '把标签改为『删除账户』'):
            with self.subTest(text=text):
                result=self.classify(text)
                self.assertEqual(result['有效档位'],'最小闭环')
                self.assertEqual(result['闭环类型'],'修改')

    def test_G04_constraints_are_retained_and_risk_overrides_still_apply(self):
        result=self.classify('不要修改代码，只运行现有测试')
        self.assertTrue(any('不要修改代码' in item for item in result['禁止事项']))
        self.assertTrue(any('不要修改代码' in item for item in result['命中依据']))
        rules=copy.deepcopy(RULES)
        rules['风险词']={'高':['现有测试'],'中':[]}
        result=detect_small_command.detect_small_command('不要修改代码，只运行现有测试',self.root,rules)
        self.assertEqual(result['有效档位'],'完整流程')

    def test_G05_only_restrictions_skip_but_unknown_empty_request_does_not(self):
        self.assertEqual(self.classify('不要删除生产数据')['有效档位'],'完全跳过')
        self.assertEqual(self.classify('')['有效档位'],'完整流程')

    def test_G06_prior_in_progress_or_required_skipped_blocks_completion_hint(self):
        for status in ('in_progress','skipped'):
            with self.subTest(status=status):
                state=manage_state.create_initial_state()
                for stage in state['stages']:
                    stage['status']='completed'
                stage=next(s for s in state['stages'] if s['required'])
                stage['status']=status
                state['current_stage']=state['stages'][-1]['id']
                actions=manage_state.generate_next_actions(state)
                self.assertFalse(any('所有阶段已完成' in item for item in actions))
                self.assertTrue(any(stage['id'] in item for item in actions))

    def test_G07_optional_skip_allows_completed_hint_without_mutating_state(self):
        state=manage_state.create_initial_state()
        for stage in state['stages']:
            stage['status']='completed' if stage['required'] else 'skipped'
        state['current_stage']=state['stages'][-1]['id']
        before=copy.deepcopy(state)
        self.assertTrue(any('所有阶段已完成' in item for item in manage_state.generate_next_actions(state)))
        self.assertEqual(state,before)

    def test_G08_wrong_topology_collection_types_report_input_error(self):
        for field in ('节点','依赖图'):
            for bad in (None,123,True,'bad',{}):
                with self.subTest(field=field,bad=bad):
                    value=json.loads((PACKAGE/'shared/assets/example-architecture.json').read_text(encoding='utf-8'))
                    value['模块拓扑'][field]=bad
                    path=self.root/'architecture.json'
                    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
                    run=self.run_script('validate_architecture.py',[path,'--json'])
                    self.assertEqual(run.returncode,1,run.stderr)
                    self.assertNotIn('Traceback',run.stderr)
                    self.assertTrue(any('模块拓扑.'+field in e for e in json.loads(run.stdout)['错误']))

    def test_G09_wrong_implementation_file_list_types_report_input_error(self):
        for field in ('文件列表','文件'):
            for bad in (None,123,True,'bad',{}):
                with self.subTest(field=field,bad=bad):
                    value=json.loads((PACKAGE/'shared/assets/example-architecture.json').read_text(encoding='utf-8'))
                    value['实现清单']={'M1':{field:bad}}
                    path=self.root/'architecture.json'
                    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
                    run=self.run_script('validate_architecture.py',[path,'--json'])
                    self.assertEqual(run.returncode,1,run.stderr)
                    self.assertNotIn('Traceback',run.stderr)
                    self.assertTrue(any('实现清单.M1.' in e for e in json.loads(run.stdout)['错误']))

    def test_G10_io_errors_are_readable_but_programming_errors_still_raise(self):
        def fail(error):
            def run():
                raise error
            return run
        for error in (PermissionError('denied'),IsADirectoryError('directory'),
                      UnicodeDecodeError('utf-8',b'\xff',0,1,'bad byte')):
            with self.subTest(error=type(error).__name__):
                value,message,code=_archlib.run_with_io_errors(fail(error))
                self.assertIsNone(value)
                self.assertTrue(message)
                self.assertEqual(code,2)
        with self.assertRaises(TypeError):
            _archlib.run_with_io_errors(fail(TypeError('programming error')))


if __name__=='__main__':
    unittest.main()
