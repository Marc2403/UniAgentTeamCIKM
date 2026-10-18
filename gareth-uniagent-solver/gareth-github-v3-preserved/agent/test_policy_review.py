import unittest
from types import SimpleNamespace
from unittest.mock import patch
from policy_review import policy_excerpt, explicit_sum_checks
from predict import _call_model_expecting_json
from predict_fast import gather_review_knowledge

class CoverageTests(unittest.TestCase):
 def test_full_policy_preserves_rule_and_exception(self):
  text='Ordinary purchases.\nChairs require framework supplier.\nException: approved specialist laboratory chairs.'
  self.assertEqual(text,policy_excerpt(text,'chairs'))
 def test_long_page_preserves_relevant_tail_not_just_header(self):
  text=('Unrelated navigation. '*3000)+'\nSpecialist chairs require framework supplier unless an approved exception applies.\n'
  excerpt=policy_excerpt(text,'chairs framework exception',2400)
  self.assertIn('approved exception applies',excerpt)
  self.assertLessEqual(len(excerpt),2500)
 def test_expenses_can_retrieve_cross_domain_purchasing_policy(self):
  hit={'corpus':'rules-de','doc_id':'rv','title':'Rahmenverträge','url':'https://u/policy','score':1,'snippet':'header'}
  tool=SimpleNamespace(corpus_name='rules-de',documents_by_id={'rv':{'content':'Monitor purchases require framework procurement. Exceptions require approval.'}})
  with patch('predict_fast.gather_case_knowledge',return_value=[hit]):
   result=gather_review_knowledge([tool],{'case_id':'auslagenerstattung-unseen','documents':{'file.pdf':'Monitor purchase'}})
  self.assertIn('Exceptions require approval.',result[0]['snippet'])
  self.assertEqual('complete_page',result[0]['coverage'])
 def test_empty_model_response_retried_once(self):
  with patch('predict.call_model',side_effect=[ValueError('Model returned no final content'),'{"ok":true}']) as call:
   import json
   result,error=_call_model_expecting_json(None,[],'p',json.loads,'repair')
  self.assertEqual({'ok':True},result);self.assertIsNone(error);self.assertEqual(2,call.call_count)
 def test_auth_error_not_retried(self):
  with patch('predict.call_model',side_effect=RuntimeError('401')) as call:
   with self.assertRaises(RuntimeError):_call_model_expecting_json(None,[],'p',str,'repair')
  self.assertEqual(1,call.call_count)
 def test_truncation_retry_is_bounded(self):
  with patch('predict.call_model',side_effect=ValueError('Model returned no final content')) as call:
   result,error=_call_model_expecting_json(None,[],'p',str,'repair')
  self.assertIsNone(result);self.assertEqual(2,call.call_count);self.assertIsNotNone(error)
 def test_explicit_sum_currency_formats(self):
  rows=explicit_sum_checks({'invoice.pdf':'12,40 + 8,60 = 21,00 EUR; 1.000,00 + 20,00 = 1.020,00'})
  self.assertEqual([True,True],[r['matches'] for r in rows])
 def test_bad_equation_detected_without_adding_unrelated_numbers(self):
  rows=explicit_sum_checks({'file.pdf':'Invoice 2026: 10,00 + 5,00 = 18,00. Other invoice 99,00.'})
  self.assertEqual(1,len(rows));self.assertFalse(rows[0]['matches'])
 def test_no_guessing_totals_from_unrelated_amounts(self):
  self.assertEqual([],explicit_sum_checks({'file.pdf':'Offer 100,00 EUR. Invoice 200,00 EUR.'}))
