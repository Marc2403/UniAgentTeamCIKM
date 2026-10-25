#!/usr/bin/env python3
"""Gareth's single-pass retrieval agent: prepare evidence, then review cases concurrently."""
import argparse
import contextvars
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from smolagents import OpenAIModel
from predict import build_case_evidence, build_retrieval_query, gather_case_knowledge, decide_case, input_cases, required_environment, citation_catalog, CASE_TYPE_INFO, case_type_for, duty_evidence_options
from retrieval_tools import build_retrieval_tools
from event_logging import case_context, log_to_file, model_context, log_event


def decision_response_format(case_id, evidence, knowledge, mode):
    """Constrain syntax/source identity; substantive support still needs review."""
    if mode == 'off':
        return None
    if mode not in {'llamacpp', 'openai'}:
        raise ValueError('UNIAGENT_STRUCTURED_OUTPUT must be off, llamacpp or openai')
    labels = [source['source_id'] for source in citation_catalog(evidence, knowledge)]
    schema = {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'antrag': {'type':'string', 'enum':[case_id]},
            'result': {'type':'string', 'enum':['angenommen','abgelehnt']},
            'begruendung': {'type':'string', 'minLength':24},
            'citations': {'type':'array', 'minItems':2 if knowledge else 1, 'maxItems':6,
                'items': {'type':'object', 'additionalProperties':False,
                    'properties': {'source_id': {'type':'string', 'enum':labels},
                                   'relevance': {'type':'string', 'minLength':16}},
                    'required':['source_id','relevance']}}
        }, 'required':['begruendung','citations','antrag','result']}
    order = ['begruendung','citations','antrag','result']
    if case_type_for(case_id) == 'expense_reimbursement':
        schema['properties']['duty_evidence'] = {
            'type':'string','enum':list(duty_evidence_options(evidence)) + ['']}
        order.insert(0,'duty_evidence')
    schema['required'] = order
    # llama.cpp follows schema key order: analyse evidence before committing to the label.
    schema['properties'] = {key:schema['properties'][key] for key in order}
    if mode == 'llamacpp':
        return {'type':'json_object', 'schema':schema}
    return {'type':'json_schema', 'json_schema':{'name':'case_decision', 'strict':True, 'schema':schema}}


def gather_review_knowledge(retrieval, evidence):
    """Retrieve administrative passages; deduplicate alternate crawl URLs."""
    case_type = case_type_for(evidence['case_id'])
    queries = [build_retrieval_query(evidence)]
    focused_queries = {
        'business_trip': [CASE_TYPE_INFO[case_type]['retrieval_keywords']],
        'expense_reimbursement': [
            'Kostenerstattung Originalquittung Originalbeleg Artikel Kassenbon Quittung Stichwort',
            'Bewirtungskosten Kaffee Tee Gäste externe Personen Erstattung'],
        'procurement': [
            'Beschaffung Direktvergabe 1000 Euro drei Vergleichsangebote',
            'Rahmenvertrag PCs Notebooks Monitore Beschaffung'],
    }[case_type]
    if case_type == 'expense_reimbursement' and 'online' in json.dumps(evidence.get('documents', {})).casefold():
        focused_queries = focused_queries + ['Online Konferenz Teilnahmegebühr privat verauslagt Finanzabteilung']
    queries += focused_queries
    title_terms = {
        'business_trip': ('dienstreise', 'reisekosten'),
        'expense_reimbursement': ('finanzbuchhaltung', 'auslagenerstattung', 'rechnungseingang', 'dienstreisemanagement'),
        'procurement': ('beschaffung', 'vergab', 'rahmenvertr', 'catering'),
    }[case_type]
    sources, scores, passages = {}, {}, {}
    for query_index, query in enumerate(queries):
        ranks = {}
        for hit in gather_case_knowledge(retrieval, query):
            corpus = hit['corpus']; ranks[corpus] = ranks.get(corpus, 0) + 1
            url = str(hit.get('url') or '').split('#', 1)[0].rstrip('/')
            if url.endswith('.html'):
                url = url[:-5]
            key = url or (corpus, hit['doc_id'])
            scores[key] = scores.get(key, 0) + 1 / (60 + ranks[corpus])
            sources.setdefault(key, hit)
            if query_index:
                snippet = hit.get('snippet', '')
                if snippet and snippet not in passages.setdefault(key, []):
                    passages[key].append(snippet)
    def topical(key):
        return any(term in str(sources[key].get('title', '')).casefold() for term in title_terms)
    # Irrelevant profiles/court rulings add noise when direct administrative guidance exists.
    relevant = [key for key in sources if topical(key)]
    ordered = sorted(relevant or list(sources), key=lambda key: scores[key], reverse=True)
    selected, seen = [], set()
    for key in ordered:
        hit = dict(sources[key],
                   snippet='\n\n'.join(passages.get(key, [])[:3]) or sources[key].get('snippet', ''),
                   retrieval_fusion_score=scores[key])
        identity = (str(hit.get('title', '')).casefold(), hit['snippet'])
        if identity not in seen:
            selected.append(hit)
            seen.add(identity)
        if len(selected) == 6:
            break
    return selected


def review_case(case_id, evidence, knowledge, config):
    base, key, model_id, max_tokens = config
    # Search snippets repeat text already present in complete case documents.
    evidence = {key: value for key, value in evidence.items()
                if key not in {"search_results", "document_completeness_check"}}
    # Separate clients avoid sharing model token counters between concurrent cases.
    with case_context(case_id):
        try:
            format_options = decision_response_format(case_id, evidence, knowledge,
                os.environ.get('UNIAGENT_STRUCTURED_OUTPUT', 'off'))
            options = {'response_format':format_options} if format_options else {}
            effort = os.environ.get('OPENAI_REASONING_EFFORT', '').strip()
            if effort:
                if effort not in {'low', 'medium', 'high'}:
                    raise ValueError('OPENAI_REASONING_EFFORT must be low, medium or high')
                options['reasoning_effort'] = effort
            model = OpenAIModel(model_id=model_id, api_base=base, api_key=key,
                                max_tokens=max_tokens, temperature=0, **options)
            return decide_case(case_id, evidence, knowledge, [], model, require_duty_quote=True)
        except Exception as error:
            result = {'antrag': case_id, 'result': 'abgelehnt',
                      'begruendung': f'Modellfehler; keine geprüfte Entscheidung: {error}'}
            log_event('error', status='error', error=str(error))
            log_event('decision', output=result, status='error', error=str(error))
            return result


def write_ordered_predictions(stream, results):
    """Keep evaluator input in application order despite concurrent completion."""
    stream.seek(0)
    stream.truncate()
    for result in sorted(results, key=lambda row: row['antrag']):
        stream.write(json.dumps(result, ensure_ascii=False) + '\n')
    stream.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--max-output-tokens', type=int, default=1024)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or args.max_output_tokens < 1:
        parser.error('workers must be 1..4 and max-output-tokens positive')
    base, key, model_id = required_environment()
    args.output.mkdir(parents=True, exist_ok=True)
    with log_to_file(args.output/'run-trace.jsonl.log.gz'), model_context(model_id):
        cases = input_cases(args.input)
        retrieval = build_retrieval_tools(args.input)
        prepared, failed = {}, {}
        for case in cases:
            with case_context(case):
                try:
                    evidence = build_case_evidence(args.input, case)
                    knowledge = gather_review_knowledge(retrieval, evidence)
                    prepared[case] = (evidence, knowledge)
                except Exception as error:
                    failed[case] = {'antrag': case, 'result': 'abgelehnt',
                                    'begruendung': f'Belegfehler; keine geprüfte Entscheidung: {error}'}
                    log_event('error', status='error', error=str(error))
                    log_event('decision', output=failed[case], status='error', error=str(error))
        (args.output/'prepared-evidence.json').write_text(json.dumps(prepared, ensure_ascii=False))
        print(f'Prepared {len(prepared)} of {len(cases)} cases; reviewing with {args.workers} worker(s).', flush=True)
        with (args.output/'predictions.jsonl').open('w') as stream:
            completed = []
            def write(result):
                completed.append(result)
                write_ordered_predictions(stream, completed)
                print(f"{result['antrag']}: {result['result']}", flush=True)
            for result in failed.values():
                write(result)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(contextvars.copy_context().run, review_case, case,
                                       evidence, knowledge, (base,key,model_id,args.max_output_tokens))
                           for case,(evidence,knowledge) in prepared.items()]
                for future in as_completed(futures):
                    write(future.result())

if __name__ == '__main__':
    main()
