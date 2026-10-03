"""Regression cases carried forward after the independent first-use evaluation."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE=Path(os.environ.get('TASKARCH_PACKAGE', str(Path(__file__).resolve().parents[1])))
MANIFEST={'cases': [{'id': 'H01', 'group': '意图理解', 'kind': 'intent', 'title': '操作在前、禁止修改在后', 'novelty': '未使用的否定词、顺序或连接词组合', 'request': '只运行检查，别修改任何文件', 'expected': {'tier': '最小闭环', 'loop': '运行'}}, {'id': 'H03', 'group': '意图理解', 'kind': 'intent', 'title': '无需调整与跑一遍组合', 'novelty': '未使用的否定词、顺序或连接词组合', 'request': '无需调整业务代码；跑一遍单元测试', 'expected': {'tier': '最小闭环', 'loop': '运行'}}, {'id': 'H04', 'group': '意图理解', 'kind': 'intent', 'title': '不必修复与运行组合', 'novelty': '未使用的否定词、顺序或连接词组合', 'request': '不必修复任何内容，只运行回归测试', 'expected': {'tier': '最小闭环', 'loop': '运行'}}, {'id': 'H05', 'group': '意图理解', 'kind': 'intent', 'title': '先不要与再运行连接', 'novelty': '未使用的否定词、顺序或连接词组合', 'request': '先不要删除日志，再运行测试', 'expected': {'tier': '最小闭环', 'loop': '运行'}}, {'id': 'H06', 'group': '意图理解', 'kind': 'intent', 'title': '否定与而是连接', 'novelty': '未使用的否定词、顺序或连接词组合', 'request': '不要修改任何文件，而是运行既有测试', 'expected': {'tier': '最小闭环', 'loop': '运行'}}, {'id': 'H07', 'group': '意图理解', 'kind': 'intent', 'title': '查看加保持不变限制', 'novelty': '只读与保持不变的组合未使用', 'request': '只查看日志，删除逻辑保持不变', 'expected': {'tier': '完全跳过', 'loop': None}}, {'id': 'H08', 'group': '意图理解', 'kind': 'intent', 'title': '单字不的否定表达', 'novelty': '此前没有单字不否定操作的输入', 'request': '不删除文件，只运行现有测试', 'expected': {'tier': '最小闭环', 'loop': '运行'}}, {'id': 'H09', 'group': '文案与实际操作', 'kind': 'intent', 'title': '支付失败提示文案', 'novelty': '风险词、失败词与引用内标点的新组合', 'request': '把提示语改成‘支付失败，请重试’', 'expected': {'tier': '最小闭环', 'loop': '修改'}}, {'id': 'H10', 'group': '文案与实际操作', 'kind': 'intent', 'title': '名称换成权限管理', 'novelty': '换成名称与接口不变的新组合', 'request': '把名称换成“权限管理”，原有接口不变', 'expected': {'tier': '最小闭环', 'loop': '修改'}}, {'id': 'H11', 'group': '文案与实际操作', 'kind': 'intent', 'title': '无引号的删除文案', 'novelty': '此前没有无引号风险文案测试', 'request': '把按钮文字改成 删除账户，实际逻辑保持不变', 'expected': {'tier': '最小闭环', 'loop': '修改'}}, {'id': 'H12', 'group': '文案与实际操作', 'kind': 'intent', 'title': '书名号中的文案', 'novelty': '此前没有书名号引用测试', 'request': '仅把说明文字改为《删除账户》，无需调整任何逻辑', 'expected': {'tier': '最小闭环', 'loop': '修改'}}, {'id': 'H13', 'group': '文案与实际操作', 'kind': 'intent', 'title': '文案后实际迁移', 'novelty': '随后连接的真实迁移是新输入', 'request': '把标题改为“重构指南”，随后迁移生产配置', 'expected': {'tier': '完整流程', 'loop': None}}, {'id': 'H14', 'group': '文案与实际操作', 'kind': 'intent', 'title': '文案后实际权限变更', 'novelty': '并且修改权限的新复合请求', 'request': '把提示语改为“删除”，并且修改用户权限', 'expected': {'tier': '完整流程', 'loop': None}}, {'id': 'H15', 'group': '文案与实际操作', 'kind': 'intent', 'title': '禁止脚本后实际生产修改', 'novelty': '禁止脚本与生产权限修改的新组合', 'request': '不要运行删除脚本；直接修改生产权限配置', 'expected': {'tier': '完整流程', 'loop': None}}, {'id': 'H16', 'group': '文案与实际操作', 'kind': 'intent', 'title': '文案修改后只读查看', 'novelty': '风险文案后只读的新请求', 'request': '把按钮文字改成“删除账户”然后只查看最近日志', 'expected': {'tier': '最小闭环', 'loop': '修改'}}, {'id': 'H17', 'group': '状态流转', 'kind': 'state', 'title': '当前必选阶段被跳过', 'novelty': '未使用的当前阶段状态、CLI 转移或备注组合', 'mode': 'required_current_skipped', 'expected': {'mention': '需求理解', 'complete': False}}, {'id': 'H18', 'group': '状态流转', 'kind': 'state', 'title': '当前可选阶段被跳过且其他已完成', 'novelty': '未使用的当前阶段状态、CLI 转移或备注组合', 'mode': 'optional_current_skipped', 'expected': {'complete': True}}, {'id': 'H19', 'group': '状态流转', 'kind': 'state', 'title': '当前中间阶段已完成且后面只有进行中', 'novelty': '未使用的当前阶段状态、CLI 转移或备注组合', 'mode': 'later_in_progress', 'expected': {'mention': '测试责任', 'complete': False}}, {'id': 'H20', 'group': '状态流转', 'kind': 'state', 'title': '当前可选阶段跳过且早期阶段待做', 'novelty': '未使用的当前阶段状态、CLI 转移或备注组合', 'mode': 'optional_current_earlier_pending', 'expected': {'mention': '模块详情', 'complete': False}}, {'id': 'H21', 'group': '状态流转', 'kind': 'state', 'title': '非法 CLI 状态不写盘', 'novelty': '未使用的当前阶段状态、CLI 转移或备注组合', 'mode': 'invalid_cli_status', 'expected': {'rc': 2, 'unchanged': True}}, {'id': 'H22', 'group': '状态流转', 'kind': 'state', 'title': '已完成项目通过 CLI 重新打开早期阶段', 'novelty': '未使用的当前阶段状态、CLI 转移或备注组合', 'mode': 'reopen_cli', 'expected': {'mention': '功能树', 'complete': False}}, {'id': 'H23', 'group': '状态流转', 'kind': 'state', 'title': '负 revision 输入拒绝且不写盘', 'novelty': '未使用的当前阶段状态、CLI 转移或备注组合', 'mode': 'negative_revision', 'expected': {'rc': 2, 'unchanged': True}}, {'id': 'H24', 'group': '状态流转', 'kind': 'state', 'title': '含中文换行和引号的阶段备注保存', 'novelty': '未使用的当前阶段状态、CLI 转移或备注组合', 'mode': 'multiline_note', 'expected': {'note': '验收：第一行\n第二行“记录”'}}, {'id': 'H25', 'group': '架构结构', 'kind': 'structure', 'title': '节点数组内部含非对象', 'novelty': '新的嵌套字段或数组元素类型错误，未复用旧的节点集合类型样例', 'path': ['模块拓扑', '节点'], 'value': [7], 'expected': {'rc': 1, 'diagnostic': '模块拓扑.节点'}}, {'id': 'H26', 'group': '架构结构', 'kind': 'structure', 'title': '依赖数组内部含 null', 'novelty': '新的嵌套字段或数组元素类型错误，未复用旧的节点集合类型样例', 'path': ['模块拓扑', '依赖图'], 'value': [None], 'expected': {'rc': 1, 'diagnostic': '模块拓扑.依赖图'}}, {'id': 'H27', 'group': '架构结构', 'kind': 'structure', 'title': '单个模块详情为数组', 'novelty': '新的嵌套字段或数组元素类型错误，未复用旧的节点集合类型样例', 'path': ['模块详情', 'm_user'], 'value': [], 'expected': {'rc': 1, 'diagnostic': '模块详情.m_user'}}, {'id': 'H28', 'group': '架构结构', 'kind': 'structure', 'title': '模块树子模块为整数', 'novelty': '新的嵌套字段或数组元素类型错误，未复用旧的节点集合类型样例', 'path': ['模块树', 0, '子模块'], 'value': 19, 'expected': {'rc': 1, 'diagnostic': '模块树.0.子模块'}}, {'id': 'H29', 'group': '架构结构', 'kind': 'structure', 'title': '接口入口列表为字符串', 'novelty': '新的嵌套字段或数组元素类型错误，未复用旧的节点集合类型样例', 'path': ['入口', '接口入口'], 'value': 'pytest', 'expected': {'rc': 1, 'diagnostic': '入口.接口入口'}}, {'id': 'H30', 'group': '架构结构', 'kind': 'structure', 'title': '项目名称为数字', 'novelty': '新的嵌套字段或数组元素类型错误，未复用旧的节点集合类型样例', 'path': ['项目', '名称'], 'value': 17, 'expected': {'rc': 1, 'diagnostic': '项目.名称'}}, {'id': 'H31', 'group': '架构结构', 'kind': 'structure', 'title': '自动化测试证据为数字', 'novelty': '新的嵌套字段或数组元素类型错误，未复用旧的节点集合类型样例', 'path': ['验证证据', '自动化测试'], 'value': 42, 'expected': {'rc': 1, 'diagnostic': '验证证据.自动化测试'}}, {'id': 'H32', 'group': '架构结构', 'kind': 'structure', 'title': '切片启用为字符串 false', 'novelty': '新的嵌套字段或数组元素类型错误，未复用旧的节点集合类型样例', 'path': ['架构切片', '启用'], 'value': 'false', 'expected': {'rc': 1, 'diagnostic': '架构切片.启用'}}, {'id': 'H33', 'group': '文件与切片输入', 'kind': 'input', 'title': 'BOM 根指针、索引和切片完整链', 'novelty': '新的读取阶段、编码、切片根类型或禁用状态组合', 'mode': 'bom_pipeline', 'expected': {'rc': 0}}, {'id': 'H34', 'group': '文件与切片输入', 'kind': 'input', 'title': '非法 UTF-8 位于指针目标', 'novelty': '新的读取阶段、编码、切片根类型或禁用状态组合', 'mode': 'bad_target_utf8', 'expected': {'rc': 2}}, {'id': 'H35', 'group': '文件与切片输入', 'kind': 'input', 'title': '切片清单引用目录', 'novelty': '新的读取阶段、编码、切片根类型或禁用状态组合', 'mode': 'directory_slice', 'expected': {'rc': 2}}, {'id': 'H36', 'group': '文件与切片输入', 'kind': 'input', 'title': '零字节架构输入', 'novelty': '新的读取阶段、编码、切片根类型或禁用状态组合', 'mode': 'empty_root', 'expected': {'rc': 2}}, {'id': 'H37', 'group': '文件与切片输入', 'kind': 'input', 'title': '启用的权威切片根为数组', 'novelty': '新的读取阶段、编码、切片根类型或禁用状态组合', 'mode': 'array_slice', 'expected': {'rc_in': [1, 2], 'diagnostic': 'array.json'}}, {'id': 'H38', 'group': '文件与切片输入', 'kind': 'input', 'title': '禁用切片时不读取损坏内容', 'novelty': '新的读取阶段、编码、切片根类型或禁用状态组合', 'mode': 'disabled_corrupt_slice', 'expected': {'rc': 0}}, {'id': 'H39', 'group': '文件与切片输入', 'kind': 'input', 'title': '指针目标为 UTF-16 编码', 'novelty': '新的读取阶段、编码、切片根类型或禁用状态组合', 'mode': 'utf16_target', 'expected': {'rc': 2}}, {'id': 'H40', 'group': '文件与切片输入', 'kind': 'input', 'title': '指针路径含 NUL 字符', 'novelty': '新的读取阶段、编码、切片根类型或禁用状态组合', 'mode': 'nul_pointer', 'expected': {'rc': 2}}, {'id': 'H41', 'group': '意图理解', 'kind': 'intent', 'title': '只读打开接口契约说明', 'novelty': '未使用过的只读打开并解释表达，含接口契约关键词', 'request': '只读打开接口契约说明并解释其含义', 'expected': {'tier': '完全跳过', 'loop': None}}]}
sys.path.insert(0,str(PACKAGE/'shared/scripts'))
import detect_small_command
import manage_state
import _archlib
RULES=json.loads((PACKAGE/'shared/assets/small-command-rules.json').read_text(encoding='utf-8'))
EXAMPLE=json.loads((PACKAGE/'shared/assets/example-architecture.json').read_text(encoding='utf-8'))


class Holdout(unittest.TestCase):
    def test_template_structure_passes_but_placeholders_still_block(self):
        path=PACKAGE/'shared/assets/architecture-template-with-placeholders.json'
        result=self.cli('validate_architecture.py',[path,'--stage','skeleton','--json'])
        self.assertEqual(result.returncode,0,result.stderr or result.stdout)
        result=self.cli('check_placeholders.py',[path,'--json'])
        self.assertEqual(result.returncode,1,result.stderr or result.stdout)
        self.assertTrue(json.loads(result.stdout)['critical'])

    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='taskarch_holdout_')
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.observed={}

    def cli(self,name,args):
        run=subprocess.run([sys.executable,'-B','-X','utf8',str(PACKAGE/'shared/scripts'/name),*map(str,args)],
                           cwd=self.root,capture_output=True,encoding='utf-8',timeout=20)
        self.observed={'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr}
        return run

    def write(self,path,value,encoding='utf-8'):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False),encoding=encoding)

    def state_case(self,case):
        state=manage_state.create_initial_state('全新验收项目')
        for stage in state['stages']:
            stage['status']='completed'
        state['current_stage']=state['stages'][-1]['id']
        by_id={s['id']:s for s in state['stages']}
        optional=next(s for s in state['stages'] if not s['required'])
        mode=case['mode']
        if mode=='required_current_skipped':
            by_id['需求理解']['status']='skipped'
            state['current_stage']='需求理解'
        elif mode=='optional_current_skipped':
            optional['status']='skipped'
            state['current_stage']=optional['id']
        elif mode=='later_in_progress':
            state['current_stage']='模块详情'
            by_id['测试责任']['status']='in_progress'
        elif mode=='optional_current_earlier_pending':
            optional['status']='skipped'
            state['current_stage']=optional['id']
            by_id['模块详情']['status']='pending'
        if mode in ('required_current_skipped','optional_current_skipped','later_in_progress','optional_current_earlier_pending'):
            self.observed={'actions':manage_state.generate_next_actions(state)}
            return
        path=self.root/'architecture/_state.json'
        if mode=='negative_revision': state['_meta']['revision']=-1
        self.write(path,state)
        before=path.read_bytes()
        if mode=='invalid_cli_status':
            self.cli('manage_state.py',['update','功能树','done','--state-path',path])
        elif mode=='negative_revision':
            self.cli('manage_state.py',['show','--json','--state-path',path])
        elif mode=='reopen_cli':
            run=self.cli('manage_state.py',['update','功能树','pending','--state-path',path])
            self.assertEqual(run.returncode,0,run.stderr)
            self.observed['actions']=manage_state.load_state(path)['next_actions']
        elif mode=='multiline_note':
            run=self.cli('manage_state.py',['update','需求理解','in_progress','--note',case['expected']['note'],'--state-path',path])
            self.assertEqual(run.returncode,0,run.stderr)
            saved=manage_state.load_state(path)
            self.observed['note']=next(s for s in saved['stages'] if s['id']=='需求理解')['notes'][-1]['content']
        self.observed['unchanged']=path.read_bytes()==before

    def structure_case(self,case):
        data=copy.deepcopy(EXAMPLE)
        cursor=data
        for key in case['path'][:-1]: cursor=cursor[key]
        cursor[case['path'][-1]]=case['value']
        path=self.root/'architecture.json'
        self.write(path,data)
        self.cli('validate_architecture.py',[path,'--json'])

    def input_case(self,case):
        root=self.root/'architecture.json'
        arch=self.root/'architecture'
        arch.mkdir()
        index=arch/'index.json'
        data=copy.deepcopy(EXAMPLE)
        mode=case['mode']
        if mode=='empty_root':
            root.write_bytes(b'')
        elif mode=='nul_pointer':
            self.write(root,{'指向':'architecture/\x00index.json'})
        else:
            self.write(root,{'指向':'architecture/index.json'})
            if mode=='bad_target_utf8':
                index.write_bytes(b'{"field":"\xfe\xfa"}')
            elif mode=='utf16_target':
                self.write(index,data,encoding='utf-16')
            else:
                name='array.json' if mode=='array_slice' else 'slice.json'
                data['架构切片']['切片清单']=[{'路径':'architecture/'+name}]
                if mode=='directory_slice':
                    (arch/name).mkdir()
                elif mode=='array_slice':
                    self.write(arch/name,[])
                elif mode=='disabled_corrupt_slice':
                    data['架构切片']['启用']=False
                    (arch/name).write_text('{not valid',encoding='utf-8')
                elif mode=='bom_pipeline':
                    project=copy.deepcopy(data['项目'])
                    project['名称']='首次 BOM 切片项目'
                    self.write(arch/name,{'项目':project},encoding='utf-8-sig')
                    self.write(root,{'指向':'architecture/index.json'},encoding='utf-8-sig')
                self.write(index,data,encoding='utf-8-sig' if mode=='bom_pipeline' else 'utf-8')
        self.cli('validate_architecture.py',[root,'--json'])
        if mode=='bom_pipeline' and self.observed['exit_code']==0:
            self.observed['loaded_name']=_archlib.load_architecture_json(root)['项目']['名称']

    def check_expected(self,case):
        expected=case['expected']
        if case['kind']=='intent':
            self.assertEqual(self.observed['有效档位'],expected['tier'])
            self.assertEqual(self.observed['闭环类型'],expected['loop'])
            return
        if 'rc' in expected: self.assertEqual(self.observed['exit_code'],expected['rc'])
        if 'rc_in' in expected: self.assertIn(self.observed['exit_code'],expected['rc_in'])
        self.assertNotIn('Traceback',self.observed.get('stderr',''))
        if 'complete' in expected:
            self.assertEqual(any('所有阶段已完成' in item for item in self.observed['actions']),expected['complete'])
        if 'mention' in expected:
            self.assertTrue(any(expected['mention'] in item for item in self.observed['actions']),self.observed['actions'])
        if 'unchanged' in expected: self.assertEqual(self.observed['unchanged'],expected['unchanged'])
        if 'note' in expected: self.assertEqual(self.observed['note'],expected['note'])
        if 'diagnostic' in expected:
            diagnostics=self.observed.get('stdout','')+self.observed.get('stderr','')
            self.assertIn(expected['diagnostic'],diagnostics)
        if case.get('mode')=='bom_pipeline': self.assertEqual(self.observed['loaded_name'],'首次 BOM 切片项目')

    def execute(self,case):
        if case['kind']=='intent':
            (self.root/'architecture').mkdir()
            self.observed=detect_small_command.detect_small_command(case['request'],self.root,RULES)
        elif case['kind']=='state': self.state_case(case)
        elif case['kind']=='structure': self.structure_case(case)
        elif case['kind']=='input': self.input_case(case)
        self.check_expected(case)


def method(case):
    def run(self): self.execute(case)
    run.__doc__=case['title']
    return run


for case in MANIFEST['cases']:
    setattr(Holdout,'test_'+case['id'],method(case))


if __name__=='__main__': unittest.main()
