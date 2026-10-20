import contextvars
import gzip
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from event_logging import log_to_file, model_context, case_context, log_event, reset_state
from predict_fast import review_case, write_ordered_predictions

class PredictionOrderRegressionTest(unittest.TestCase):
    def test_out_of_order_completion_keeps_labels_with_application_ids(self):
        import io
        stream = io.StringIO()
        results = [{'antrag':'case-03','result':'abgelehnt'},
                   {'antrag':'case-01','result':'angenommen'},
                   {'antrag':'case-02','result':'abgelehnt'}]
        write_ordered_predictions(stream, results[:1])
        write_ordered_predictions(stream, results)
        rows = list(map(json.loads, stream.getvalue().splitlines()))
        self.assertEqual(['case-01','case-02','case-03'], [row['antrag'] for row in rows])
        self.assertEqual(['angenommen','abgelehnt','abgelehnt'], [row['result'] for row in rows])

class ConcurrentReviewTest(unittest.TestCase):
    def test_concurrent_reviews_keep_valid_gzip_and_separate_case_chains(self):
        reset_state()
        class FakeModel:
            def __init__(self, **kwargs): pass
            def generate(self, messages):
                evidence, _ = json.JSONDecoder().raw_decode(messages[-1]['content'].split('EVIDENCE_JSON:\n')[-1])
                return SimpleNamespace(content=json.dumps({'antrag': evidence['case_id'], 'result':'angenommen','begruendung':'Belegt', 'citations':[{'kind':'case','filename':'receipt.pdf','relevance':'Paid receipt'}], 'duty_evidence':{'source_id':'C1','quote':'Paid for Universität Test'}}))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.gz'
            with patch('predict_fast.OpenAIModel', FakeModel), log_to_file(path), model_context('test-local'):
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures=[]
                    for i in range(20):
                        case=f'auslagenerstattung-{i:02}'
                        with case_context(case): log_event('input',input={'case':case})
                        futures.append(pool.submit(contextvars.copy_context().run,review_case,case,{'case_id':case,'documents':{'receipt.pdf':'Paid for Universität Test'}},[],('http://local','unused','test-local',512)))
                    results=[f.result() for f in futures]
            with gzip.open(path,'rt') as stream: events=[json.loads(line) for line in stream]
        self.assertEqual(20,len(results))
        self.assertEqual({'angenommen'}, {r['result'] for r in results})
        self.assertEqual(len(events),len({e['event_id'] for e in events}))
        by_id={e['event_id']:e for e in events}
        for e in events:
            self.assertEqual('test-local',e['model'])
            if e['parent_event_id']:
                self.assertEqual(e['case_id'],by_id[e['parent_event_id']]['case_id'])
        for case in {e['case_id'] for e in events}:
            self.assertEqual('decision',[e for e in events if e['case_id']==case][-1]['event_type'])

class StructuredOutputTest(unittest.TestCase):
    def test_schema_locks_case_and_available_source_ids(self):
        from predict_fast import decision_response_format
        schema=decision_response_format('auslagenerstattung-01', {'documents':{'receipt.pdf':'Paid for Universität Test'}}, [{'corpus':'rules','doc_id':'payment'}], 'llamacpp')['schema']
        self.assertEqual(['auslagenerstattung-01'],schema['properties']['antrag']['enum'])
        self.assertEqual(['C1','P1'],schema['properties']['citations']['items']['properties']['source_id']['enum'])
        self.assertEqual(2,schema['properties']['citations']['minItems'])
        self.assertFalse(schema['additionalProperties'])

    def test_modes_are_explicit_and_invalid_mode_fails(self):
        from predict_fast import decision_response_format
        evidence={'documents':{'receipt.pdf':'Paid for Universität Test'}}
        self.assertIsNone(decision_response_format('dienstreiseantrag-new',evidence,[],'off'))
        self.assertEqual('json_schema',decision_response_format('dienstreiseantrag-new',evidence,[],'openai')['type'])
        with self.assertRaises(ValueError):decision_response_format('dienstreiseantrag-new',evidence,[],'typo')

    def test_review_passes_format_to_client(self):
        class FakeModel:
            def __init__(inner, **kwargs):inner.kwargs=kwargs;self.options=kwargs
            def generate(inner,messages):
                return SimpleNamespace(content=json.dumps({'antrag':'auslagenerstattung-01','result':'angenommen','begruendung':'Der Zahlungsbeleg bestätigt die tatsächliche Zahlung.', 'citations':[{'source_id':'C1','relevance':'Die Rechnung ist als bezahlt markiert.'}], 'duty_evidence':{'source_id':'C1','quote':'Paid for Universität Test'}}))
        with patch.dict('os.environ',{'UNIAGENT_STRUCTURED_OUTPUT':'llamacpp','OPENAI_REASONING_EFFORT':'low'}), patch('predict_fast.OpenAIModel',FakeModel):
            result=review_case('auslagenerstattung-01',{'case_id':'auslagenerstattung-01','documents':{'receipt.pdf':'Paid for Universität Test'}},[],('http://local','unused','model',1024))
        self.assertEqual('angenommen',result['result'])
        self.assertEqual('json_object',self.options['response_format']['type'])
        self.assertEqual('low', self.options['reasoning_effort'])

class PolicyRetrievalRegressionTest(unittest.TestCase):
    def test_fusion_filters_profiles_when_finance_guidance_exists(self):
        from predict_fast import gather_review_knowledge
        case_hit={'corpus':'university-de','doc_id':'staff','score':100,'title':'Staff profile','snippet':'Invoice surname'}
        policy_hit={'corpus':'university-de','doc_id':'finance','score':1,'title':'Finanzbuchhaltung und Steuern','snippet':'Invoice payment rule'}
        with patch('predict_fast.gather_case_knowledge',side_effect=[[case_hit],[policy_hit,case_hit],[policy_hit]]) as search:
            result=gather_review_knowledge([],{'case_id':'auslagenerstattung-01','documents':{'invoice.pdf':'Invoice 94.40 EUR'}})
        self.assertEqual(3,search.call_count)
        self.assertEqual(['finance'],[r['doc_id'] for r in result])
        self.assertEqual(1,len(result))

class PassageSelectionRegressionTest(unittest.TestCase):
    def test_long_single_line_selects_receipt_section_instead_of_unrelated_intro(self):
        from retrieval_tools import _best_snippet
        text = ('General finance administration. ' * 80 +
                'Kostenerstattung: Originalquittung, Artikel oder Stichwort auf dem Kassenbon. ' +
                'Other administration. ' * 80)
        snippet = _best_snippet(text, ['kostenerstattung','originalquittung','artikel','stichwort','kassenbon'])
        self.assertIn('Kostenerstattung:', snippet)
        self.assertIn('Originalquittung', snippet)
        self.assertLessEqual(len(snippet), 700)

    def test_alternate_html_urls_merge_distinct_rule_passages(self):
        from predict_fast import gather_review_knowledge
        first = {'corpus':'uni-de','doc_id':'one','url':'https://uni.example/finance',
                 'title':'Finanzbuchhaltung','snippet':'Originalquittung required'}
        second = dict(first, doc_id='two', url='https://uni.example/finance.html', snippet='Coffee for external guests')
        with patch('predict_fast.gather_case_knowledge', side_effect=[[first],[first],[second]]):
            result = gather_review_knowledge([], {'case_id':'auslagenerstattung-new','documents':{}})
        self.assertEqual(1,len(result))
        self.assertIn('Originalquittung',result[0]['snippet'])
        self.assertIn('external guests',result[0]['snippet'])

    def test_threshold_exception_on_catering_page_is_retained(self):
        from predict_fast import gather_review_knowledge
        hit = {'corpus':'uni-de','doc_id':'threshold','title':'Nachhaltiges Catering',
               'url':'https://uni.example/catering','snippet':'Unter 1000 Euro ist Direktvergabe möglich.'}
        with patch('predict_fast.gather_case_knowledge', return_value=[hit]):
            result = gather_review_knowledge([], {'case_id':'beschaffungsantrag-new','documents':{}})
        self.assertEqual(['threshold'], [row['doc_id'] for row in result])

class ReasonBeforeDecisionRegressionTest(unittest.TestCase):
    def test_constrained_schema_delays_label_until_after_evidence_analysis(self):
        from predict_fast import decision_response_format
        schema = decision_response_format('auslagenerstattung-new', {'documents':{'invoice.pdf':'Private invoice'}}, [], 'llamacpp')['schema']
        self.assertLess(list(schema['properties']).index('begruendung'), list(schema['properties']).index('result'))
        self.assertEqual('result', list(schema['properties'])[-1])

class VerifiedExpenseChoiceTest(unittest.TestCase):
    def test_private_receipt_cannot_generate_an_invented_university_quote(self):
        from predict_fast import decision_response_format
        schema=decision_response_format('auslagenerstattung-new', {'documents':{'invoice.pdf':'Private buyer. Headphones. Paid 229 EUR.'}}, [], 'llamacpp')['schema']
        self.assertEqual([''],schema['properties']['duty_evidence']['enum'])

    def test_multicolumn_invoice_excerpts_are_preverified_and_source_bound(self):
        from predict import duty_evidence_options,validate_duty_evidence
        evidence={'documents':{'invoice.pdf':'Bill to\nUniversität Wernstadt         Seller Utrecht BV\nCentral invoice office          Seller bank details'}}
        choices=duty_evidence_options(evidence)
        self.assertTrue(choices)
        for key,proof in choices.items():
            self.assertEqual(proof,validate_duty_evidence({'result':'angenommen','duty_evidence':key},evidence))
            self.assertIn(proof['quote'], ' '.join(evidence['documents']['invoice.pdf'].split()))
