import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from predict import validate_citations, decide_case, call_model

class GroundingTest(unittest.TestCase):
    def setUp(self):
        self.evidence = {'case_id': 'dienstreiseantrag-01', 'documents': {'request.pdf': 'Travel request'}}
        self.knowledge = [{'corpus': 'rules-de', 'doc_id': 'deadline', 'snippet': 'Deadline rule'}]
        self.case = {'kind': 'case', 'filename': 'request.pdf', 'relevance': 'Travel dates'}
        self.policy = {'kind': 'policy', 'corpus': 'rules-de', 'doc_id': 'deadline', 'relevance': 'Application deadline'}

    def test_requires_both_sources_when_policy_was_retrieved(self):
        with self.assertRaises(ValueError):
            validate_citations({'citations': [self.case]}, self.evidence, self.knowledge)
        self.assertEqual(2, len(validate_citations({'citations': [self.case, self.policy]}, self.evidence, self.knowledge)))

    def test_rejects_invented_sources_and_malformed_ids(self):
        for bad in [dict(self.case, filename='invented.pdf'), dict(self.policy, doc_id='invented'), dict(self.policy, doc_id=[]), dict(self.policy, corpus='other')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_citations({'citations': [self.case, bad]}, self.evidence, self.knowledge)

    def test_missing_and_empty_citations_are_invalid(self):
        for citations in [None, [], 'request.pdf']:
            with self.subTest(citations=citations), self.assertRaises(ValueError):
                validate_citations({'citations': citations}, self.evidence, [])

    def test_invalid_citation_is_retried_and_repaired(self):
        good = {'antrag': 'dienstreiseantrag-01', 'result': 'angenommen', 'begruendung': 'Supported', 'citations': [self.case, self.policy]}
        bad = dict(good, citations=[self.case, dict(self.policy, doc_id='invented')])
        class Model:
            calls = 0
            def generate(inner, messages):
                inner.calls += 1
                return SimpleNamespace(content=json.dumps(bad if inner.calls == 1 else good))
        model = Model()
        with contextlib.redirect_stdout(io.StringIO()):
            decision = decide_case('dienstreiseantrag-01', self.evidence, self.knowledge, [], model)
        self.assertEqual(2, model.calls)
        self.assertEqual('angenommen', decision['result'])
        self.assertEqual({'antrag', 'result', 'begruendung'}, set(decision))

    def test_unrepaired_citation_failure_is_logged(self):
        class Model:
            def generate(inner, messages):
                return SimpleNamespace(content=json.dumps({'antrag': 'dienstreiseantrag-01', 'result': 'angenommen', 'begruendung': 'Unsupported'}))
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            decision = decide_case('dienstreiseantrag-01', self.evidence, self.knowledge, [], Model())
        self.assertEqual('abgelehnt', decision['result'])
        last = json.loads(capture.getvalue().splitlines()[-1])
        self.assertEqual('error', last['status'])

    def test_model_usage_is_logged(self):
        class Model:
            def generate(inner, messages):
                return SimpleNamespace(content='answer', token_usage=SimpleNamespace(input_tokens=20, output_tokens=7))
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            call_model(Model(), [], 'prompt')
        usage = json.loads(capture.getvalue())['output']['usage']
        self.assertEqual({'input_tokens': 20, 'output_tokens': 7}, usage)

class LocalContextBudgetTest(unittest.TestCase):
    def test_optional_excerpt_budget_preserves_source_identity(self):
        from unittest.mock import patch
        from predict import gather_case_knowledge
        class Retrieval:
            def __call__(self, **kwargs):
                return json.dumps([{'corpus': 'rules', 'doc_id': 'id1', 'score': 1.0, 'snippet': 'abcdefghij'}])
        with patch.dict('os.environ', {'UNIAGENT_SNIPPET_MAX_CHARACTERS': '4'}):
            hit = gather_case_knowledge([Retrieval()], 'query')[0]
        self.assertEqual('abcd', hit['snippet'])
        self.assertEqual('id1', hit['doc_id'])
        with patch.dict('os.environ', {'UNIAGENT_SNIPPET_MAX_CHARACTERS': '0'}):
            self.assertEqual('abcdefghij', gather_case_knowledge([Retrieval()], 'query')[0]['snippet'])

class ShortSourceLabelTest(unittest.TestCase):
    def test_labels_resolve_to_exact_real_sources(self):
        evidence={'documents': {'receipt.pdf':'Paid'}}
        knowledge=[{'corpus':'rules-de','doc_id':'long-uuid'}]
        checked=validate_citations({'citations':[{'source_id':'C1','relevance':'Paid'}, {'source_id':'P1','relevance':'Policy'}]}, evidence, knowledge)
        self.assertEqual('receipt.pdf',checked[0]['filename'])
        self.assertEqual('long-uuid',checked[1]['doc_id'])
        self.assertEqual('rules-de',checked[1]['corpus'])

    def test_invented_and_wrongly_typed_short_labels_fail(self):
        for label in ['P99', ['C1'], None]:
            with self.subTest(label=label), self.assertRaises(ValueError):
                validate_citations({'citations':[{'source_id':label,'relevance':'Claim'}]}, {'documents':{'receipt.pdf':'Paid'}}, [])

class ExplanationRegressionTest(unittest.TestCase):
    def test_copied_prompt_placeholder_is_not_a_supported_decision(self):
        from predict import parse_decision
        for reason in ['kurze belegte Begründung', '...', 'Begründung']:
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                parse_decision({'antrag':'dienstreiseantrag-01','result':'angenommen','begruendung':reason}, 'dienstreiseantrag-01')

    def test_specific_explanation_remains_valid(self):
        from predict import parse_decision
        answer={'antrag':'dienstreiseantrag-01','result':'angenommen','begruendung':'Antrag am 12.02.2026 vor Reisebeginn am 10.03.2026.'}
        self.assertEqual(answer, parse_decision(answer, answer['antrag']))

class CurrencyExtractionRegressionTest(unittest.TestCase):
    def test_international_invoice_prefix_currencies(self):
        from predict import extract_amounts
        self.assertEqual(['84.02 €','89.90 €','94.40 €'],extract_amounts('Net €84.02 Gross €89.90 Invoice total €94.40'))

    def test_german_and_large_values_remain_supported(self):
        from predict import extract_amounts
        self.assertEqual(['2.667,00 EUR','1234,56 €','1,234.56 USD'],extract_amounts('2.667,00 EUR 1234,56 € USD 1,234.56'))

    def test_decimal_identifiers_are_not_bare_monetary_values(self):
        from predict import extract_amounts
        self.assertEqual([],extract_amounts('Date 12.02.2026 room 2.107 VAT 7%'))

class EvidenceCueRegressionTest(unittest.TestCase):
    def test_receipt_purpose_is_preserved_verbatim_without_eligibility_inference(self):
        from predict import case_observation_notes
        note='für Versuchsstand Labor E 3.12'
        facts=case_observation_notes({'case_id':'auslagenerstattung-02','documents':{'receipt.pdf':'SUMME 19,86\n'+note}})
        self.assertIn(note,facts['verbatim_document_cues']['receipt.pdf'])
        self.assertNotIn('result',facts)

    def test_currency_formatting_cannot_turn_673_into_an_above_1000_amount(self):
        from predict import case_observation_notes
        facts=case_observation_notes({'case_id':'beschaffungsantrag-02','documents':{'request.pdf':'Netto 673,00 EUR'},'amounts_by_document':{'request.pdf':['673,00 EUR','2.667,00 €','1,234.56 USD']}})
        comparisons={row['numeric_comparison'] for row in facts['numeric_comparisons']}
        self.assertEqual({'673.00 < 1000','2667.00 > 1000','1234.56 > 1000'},comparisons)

class DutyQuoteEvidenceTest(unittest.TestCase):
    def test_policy_only_purpose_cannot_support_private_expense_approval(self):
        from predict import validate_duty_evidence
        evidence={'documents':{'invoice.pdf':'Private buyer. Headphones. Paid 229 EUR.'}}
        with self.assertRaises(ValueError):
            validate_duty_evidence({'result':'angenommen','duty_evidence':{'source_id':'P1','quote':'Universität Lab example'}}, evidence)
        with self.assertRaises(ValueError):
            validate_duty_evidence({'result':'angenommen','duty_evidence':{'source_id':'C1','quote':'Universität Lab example'}}, evidence)

    def test_actual_lab_note_is_accepted_despite_pdf_whitespace(self):
        from predict import validate_duty_evidence
        evidence={'documents':{'receipt.pdf':'19,86 EUR\nfür Versuchsstand  Labor\nE 3.12'}}
        proof=validate_duty_evidence({'result':'angenommen','duty_evidence':{'source_id':'C1','quote':'für Versuchsstand Labor E 3.12'}}, evidence)
        self.assertEqual('receipt.pdf',proof['filename'])

    def test_payment_alone_is_insufficient_and_rejection_needs_no_positive_quote(self):
        from predict import validate_duty_evidence
        evidence={'documents':{'receipt.pdf':'Payment received 229 EUR'}}
        with self.assertRaises(ValueError):
            validate_duty_evidence({'result':'angenommen','duty_evidence':{'source_id':'C1','quote':'Payment received 229 EUR'}}, evidence)
        self.assertIsNone(validate_duty_evidence({'result':'abgelehnt'}, evidence))
