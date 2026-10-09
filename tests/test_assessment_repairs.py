"""Behavioral regressions from the 30-round assessment; no language parser assumed."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / 'shared/scripts'))
import _archlib
import check_quality_redlines as redlines
from check_project_quality import canonical_hash, evaluate_project
from _architecture_visual import build_visual_model
import gate_check
import manage_state
import scan_code_drift


class RedlineCompletionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.arch = self.root / 'architecture.json'
        self.data = json.loads((PACKAGE/'shared/assets/example-architecture.json').read_text(encoding='utf-8'))
        files = scan_code_drift.collect_declared_files(self.data, self.root)
        for rel in files:
            p=self.root/rel
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(b'actual fixture file')
        self.data['上下文恢复点']['当前阶段']='验证完成'
        self.data['上下文恢复点']['已触碰文件']=sorted(files)
        self.data['功能树'].append({'编号':'bulk-test','名称':'导出本地记录',
                                    '验收标准':['保持原始行'], '异常路径':['拒绝无效列'],
                                    '架构落位':{'测试':['CSV异常和原子写出验收']}})
        self.arch.write_text(json.dumps(self.data),encoding='utf-8')
        state=manage_state.create_initial_state('redline verdict regression')
        for stage in state['stages']:stage['status']='completed'
        manage_state.save_state(self.root/'architecture/_state.json',state)
        self.evidence=self.root/'review.txt'
        self.evidence.write_text('实际审查：此夹具测试持久化复核机制；非业务测试证据',encoding='utf-8')

    def write_review(self, mutate=None):
        finding=redlines.check_redlines(self.data)[0][-1]
        review={'finding':finding,'architecture_sha256':canonical_hash(self.data),
                'disposition':'covered','reviewer':'automated-test-fixture-review',
                'rationale':'仅本回归夹具的语义复核机制测试',
                'input_hashes':{'review.txt':hashlib.sha256(self.evidence.read_bytes()).hexdigest()}}
        if mutate:mutate(review)
        p=self.root/'architecture/quality/redline-reviews.json'
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps({'schema_version':1,'reviews':[review]}),encoding='utf-8')
        return p

    def cli(self, *args):
        output=io.StringIO()
        with redirect_stdout(output):code=redlines.main([str(self.arch),'--json',*args])
        return code,json.loads(output.getvalue())

    def test_known_redline_blocks_real_gate_and_matches_cli(self):
        code,result=self.cli()
        passed,_,stages=gate_check.run_gate(self.root,'architecture.json')
        self.assertEqual(code,1)
        self.assertFalse(passed)
        self.assertEqual(next(s['status'] for s in stages if s['name']=='质量红线'),result['status'])

    def test_persisted_review_passes_real_gate_and_cli(self):
        self.write_review()
        code,result=self.cli()
        self.assertEqual(code,0,result)
        self.assertTrue(result['已豁免'])
        self.assertIs(gate_check.run_gate(self.root,'architecture.json')[0],True)

    def test_render_keeps_reviewed_findings_visible_without_unresolved_error(self):
        from render_architecture import main as render
        self.write_review()
        path=self.root/'view.json'
        with redirect_stdout(io.StringIO()):
            code=render([str(self.arch),'--json','--output',str(path)])
        self.assertEqual(code,0)
        rendered=json.loads(path.read_text(encoding='utf-8'))
        text=json.dumps(rendered,ensure_ascii=False)
        self.assertIn('已记录语义复核',text)
        self.assertIn('导出本地记录',text)

    def test_render_cannot_overwrite_the_review_input(self):
        from render_architecture import main as render
        path=self.write_review()
        original=path.read_bytes()
        with redirect_stdout(io.StringIO()):
            code=render([str(self.arch),'--json','--output',str(path)])
        self.assertEqual(code,2)
        self.assertEqual(path.read_bytes(),original)

    def test_review_invalidates_when_evidence_changes(self):
        self.write_review()
        self.evidence.write_text('changed',encoding='utf-8')
        self.assertEqual(self.cli()[0],2)
        self.assertIsNone(gate_check.run_gate(self.root,'architecture.json')[0])

    def test_review_invalidates_when_architecture_changes(self):
        self.write_review()
        self.data['项目']['名称']='updated name'
        self.arch.write_text(json.dumps(self.data),encoding='utf-8')
        self.assertEqual(self.cli()[0],2)

    def test_review_needs_reason_reviewer_current_exact_finding_and_evidence(self):
        for field,value in [('rationale',''),('reviewer',''),('finding','功能树.*'),
                            ('input_hashes',{}),('disposition','ignore'),
                            ('input_hashes',{'../outside':'0'*64})]:
            with self.subTest(field=field):
                self.write_review(lambda r:r.update({field:value}))
                code,result=self.cli()
                self.assertEqual(code,2,result)
                self.assertEqual(result['已豁免'],[])

    def test_malformed_and_duplicate_review_records_do_not_partially_apply(self):
        path=self.write_review()
        document=json.loads(path.read_text())
        document['reviews'].append(document['reviews'][0])
        path.write_text(json.dumps(document),encoding='utf-8')
        self.assertEqual(self.cli()[1]['已豁免'],[])
        path.write_text('{"schema_version":1,"schema_version":1,"reviews":[]}',encoding='utf-8')
        self.assertEqual(self.cli()[0],2)
        # Two different features with the same human label cannot share a
        # single ambiguous semantic disposition.
        duplicate=copy.deepcopy(self.data['功能树'][-1]);duplicate['编号']='bulk-second'
        self.data['功能树'].append(duplicate)
        self.arch.write_text(json.dumps(self.data),encoding='utf-8')
        self.write_review()
        self.assertEqual(self.cli()[0],2)
        self.assertEqual(self.cli()[1]['已豁免'],[])

    def test_temporary_exemption_does_not_certify_completion(self):
        self.assertEqual(self.cli('--exempt','功能树.导出本地记录','--exempt-reason','review later')[0],2)

    def test_nested_operation_cannot_escape_redline_check(self):
        data={'功能树':[{'名称':'父级','子节点':[{'名称':'删除数据'}]}]}
        self.assertTrue(any('删除数据' in s for s in redlines.check_redlines(data)[0]))


class ContractObservationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.file=self.root/'引擎.未知'
        self.file.write_bytes(b'opaque project source')
        self.data={'接口契约':{'engine':{'导出':[{'名称':'calculate','签名':'(amount) -> integer',
                                       '可能异常':['InvalidAmount'],'消费者':['ui']}]}}}
        self.save()
        self.facts={'schema_version':1,'modules':['engine','ui'],
                    'sources':[{'id':'native','origin':'observed','tool':{'name':'controlled fixture exporter','version':'1'},
                    'scope':['engine'],'capabilities':['contract'],'complete':True,'errors':[],'excluded':[],
                    'input_hashes':{'引擎.未知':hashlib.sha256(self.file.read_bytes()).hexdigest()}}],
                    'contracts':[{'source':'native','module':'engine','name':'calculate','signature':'(amount) -> integer',
                                  'file':'引擎.未知','errors':['InvalidAmount'],'consumers':['ui']}]}
        self.policy={'schema_version':1,'rules':[{'id':'api','check':'contract','required':True,'source':'native','scope':['engine']}]}

    def save(self):
        (self.root/'architecture.json').write_text(json.dumps(self.data),encoding='utf-8')

    def run_check(self):return evaluate_project(self.root,self.facts,self.policy)

    def test_complete_matching_contract_passes_without_language_whitelist(self):
        self.assertEqual(self.run_check()['status'],'pass')

    def test_real_name_signature_error_and_consumer_drift_fail(self):
        original=copy.deepcopy(self.facts['contracts'])
        for field,value in [('name','operation title'),('signature','(x,y) -> integer'),
                            ('errors',[]),('consumers',[])]:
            with self.subTest(field=field):
                self.facts['contracts']=copy.deepcopy(original)
                self.facts['contracts'][0][field]=value
                self.assertEqual(self.run_check()['status'],'fail')

    def test_title_and_see_tests_cannot_replace_concrete_contract(self):
        self.data['接口契约']['engine']['导出']=[{'名称':'处理金额','说明':'见测试'}]
        self.save()
        result=self.run_check()
        self.assertEqual(result['status'],'fail')
        self.assertTrue(any(f.get('field')=='签名' for f in result['checks'][0]['findings']))

    def test_extra_observed_api_fails_even_if_declared_apis_match(self):
        extra=copy.deepcopy(self.facts['contracts'][0]);extra['name']='debug_reset'
        self.facts['contracts'].append(extra)
        self.assertEqual(self.run_check()['status'],'fail')

    def test_absent_observations_and_incomplete_scope_unknown(self):
        self.facts.pop('contracts')
        self.assertEqual(self.run_check()['status'],'unknown')
        self.facts['contracts']=[]
        self.facts['sources'][0]['complete']=False
        self.assertEqual(self.run_check()['status'],'unknown')

    def test_absent_optional_values_are_unknown_in_observations(self):
        for field in ['errors','consumers']:
            original=self.facts['contracts'][0].pop(field)
            self.assertEqual(self.run_check()['status'],'unknown')
            self.facts['contracts'][0][field]=original

    def test_stale_source_and_unhashed_api_file_unknown(self):
        self.file.write_bytes(b'changed')
        self.assertEqual(self.run_check()['status'],'unknown')
        self.file.write_bytes(b'opaque project source')
        self.facts['contracts'][0]['file']='unhashed.unit'
        self.assertEqual(self.run_check()['status'],'unknown')

    def test_duplicate_observed_api_is_unknown(self):
        self.facts['contracts'].append(copy.deepcopy(self.facts['contracts'][0]))
        self.assertEqual(self.run_check()['status'],'unknown')

    def test_unknown_consumer_is_not_accepted(self):
        self.facts['contracts'][0]['consumers']=['不存在']
        self.assertEqual(self.run_check()['status'],'unknown')

    def test_missing_declared_signature_and_consumers_fail(self):
        export=self.data['接口契约']['engine']['导出'][0]
        for field in ('签名','消费者'):
            value=export.pop(field);self.save()
            self.assertEqual(self.run_check()['status'],'fail')
            export[field]=value

    def test_declared_unknown_consumer_fails(self):
        self.data['接口契约']['engine']['导出'][0]['消费者']=['missing']
        self.save()
        self.assertEqual(self.run_check()['status'],'fail')

    def test_no_exports_does_not_vacuously_certify_api_quality(self):
        self.facts['contracts']=[]
        self.data['接口契约']['engine']['导出']=[];self.save()
        self.assertEqual(self.run_check()['status'],'unknown')


class VisualReferenceRepairTests(unittest.TestCase):
    def model(self, reference):
        data={'模块详情':{'A':{'上游依赖':[reference]},'B':{}},'模块拓扑':{'节点':[{'编号':'A'},{'编号':'B'}]}}
        before=copy.deepcopy(data)
        model=build_visual_model(data)
        self.assertEqual(data,before)
        return model

    def test_structured_module_reference_creates_dependency_with_declaration_pointer(self):
        for ref in [{'模块编号':'B','依赖内容':'读取状态'},{'编号':'B'},'B']:
            with self.subTest(ref=ref):
                model=self.model(ref)
                edges=[r for r in model['relations'] if r['kind']=='依赖']
                self.assertEqual(len(edges),1)
                self.assertIn('/模块详情/A/上游依赖/0',edges[0]['sources'])
                self.assertFalse(any(d['code'] in ('unstructured_reference','unresolved_reference') for d in model['diagnostics']))

    def test_explicit_prose_retains_fact_without_inventing_edge(self):
        model=self.model({'说明':'外部验收调用方'})
        self.assertFalse(any(r['kind']=='依赖' for r in model['relations']))
        self.assertTrue(any(d['code']=='descriptive_reference' for d in model['diagnostics']))
        self.assertFalse(any(d['code']=='unresolved_reference' for d in model['diagnostics']))

    def test_bad_module_id_remains_diagnostic_even_with_description(self):
        for ref in ['missing',{'模块编号':'missing','说明':'context'}]:
            model=self.model(ref)
            self.assertTrue(any(d['code']=='unresolved_reference' for d in model['diagnostics']))

    def test_conflicting_module_ids_never_create_an_edge(self):
        model=self.model({'模块编号':'A','编号':'B'})
        self.assertTrue(any(d['code']=='conflicting_reference' for d in model['diagnostics']))
        self.assertFalse(any(r['kind']=='依赖' for r in model['relations']))


if __name__=='__main__':unittest.main()
