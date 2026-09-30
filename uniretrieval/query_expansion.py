"""LLM query expansion: one call per query for related terms and a short
hypothetical answer passage (query2doc), used as an extra lexical ranking."""

import json
import re

from uniretrieval.data import Query
from uniretrieval.llm import ChatModel, Completion

PROMPTS = {
    "de": """Du hilfst einer Suchmaschine für die Verwaltung einer deutschen Universität und das hessische Landesrecht.
Suchanfrage: {query}
Beschreibung: {description}
Hinweis: {narrative}

Antworte nur mit einem JSON-Objekt:
{{"terms": [bis zu 15 Fachbegriffe, Synonyme, Abkürzungen und Namen einschlägiger Vorschriften auf Deutsch],
 "passage": "ein Absatz von höchstens 80 Wörtern, wie er in einem passenden Dokument stehen könnte"}}""",
    "en": """You help a search engine for the administration of a German university.
Query: {query}
Description: {description}
Note: {narrative}

Answer only with a JSON object:
{{"terms": [up to 15 technical terms, synonyms, abbreviations and names of relevant regulations in English],
 "passage": "one paragraph of at most 80 words as it could appear in a matching document"}}""",
}


def parse_expansion(response: str) -> dict:
    """{'terms': [...], 'passage': str}; tolerant of fences and chatter around the JSON."""
    match = re.search(r"\{.*\}", response, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in response")
    parsed = json.loads(match.group(0))
    terms = [str(term) for term in parsed.get("terms", []) if isinstance(term, (str, int, float))]
    passage = parsed.get("passage", "")
    return {"terms": terms, "passage": passage if isinstance(passage, str) else ""}


def expansion_prompt(query: Query, language: str) -> str:
    return PROMPTS.get(language, PROMPTS["en"]).format(
        query=query.query, description=query.description or "-", narrative=query.narrative or "-"
    )


def expand(model: ChatModel, query: Query, language: str, max_tokens: int) -> tuple[str, Completion, dict]:
    """Returns (expanded query text, completion, parsed expansion)."""
    prompt = expansion_prompt(query, language)
    completion = model.complete(prompt, max_tokens)
    expansion = parse_expansion(completion.text)
    text = " ".join([query.query, query.description, *expansion["terms"], expansion["passage"]])
    return text, completion, expansion
