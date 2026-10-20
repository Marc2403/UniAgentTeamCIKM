"""Hessian-law specifics, all derived at runtime from the mounted collection:
abbreviation expansion, §-reference injection, version handling, and a
norm-vs-decision prior.

Norm titles look like ` § 8 HRKG | Landesnorm Hessen | ... | gültig ab: 01.01.2010`
(one document per paragraph and version) or `HTGV | Landesnorm Hessen | ...`
(a whole law)."""

import re
from collections import Counter, defaultdict
from datetime import date, datetime

from uniretrieval.data import Document, Query
from uniretrieval.fusion import Ranking

ABBREVIATION = r"[A-ZÄÖÜ][\wÄÖÜäöüß\-]*[A-ZÄÖÜ][\wÄÖÜäöüß\-]*"
PARAGRAPH_TITLE_RE = re.compile(rf"^\s*§+\s*(?P<number>\d+[a-z]?)\s+(?P<abbreviation>{ABBREVIATION})\s*\|")
LAW_TITLE_RE = re.compile(rf"^\s*(?P<abbreviation>{ABBREVIATION})\s*\|\s*Landesnorm")
NAMED_ABBREVIATION_RE = re.compile(rf"(?P<name>[A-ZÄÖÜ][^\n|()]{{4,150}}?)\s*\((?P<abbreviation>{ABBREVIATION})\)")
VALID_FROM_RE = re.compile(r"gültig ab:\s*(\d{2}\.\d{2}\.\d{4})")
VALID_UNTIL_RE = re.compile(r"gültig bis:\s*(\d{2}\.\d{2}\.\d{4})")
PARAGRAPH_REFERENCE_RE = re.compile(
    rf"§§?\s*(?P<number>\d+[a-z]?)"
    rf"(?:\s+(?:Abs\.|Absatz|S\.|Satz|Nr\.|Nummer)\s*\d+[a-z]?)*"
    rf"\s+(?:(?:des|der|dem)\s+)?(?P<abbreviation>{ABBREVIATION})"
)
DECISION_TYPES = {"Urteil", "Beschluss", "Gerichtsbescheid", "Teilurteil", "Vorlagebeschluss", "Entscheidung"}
DECISION_INTENT_RE = re.compile(r"\b(Urteil\w*|Beschluss\w*|Rechtsprechung|Gericht\w*|Entscheidung\w*)\b", re.IGNORECASE)
NORM_INTENT_RE = re.compile(r"(§|\b(Gesetz\w*|Verordnung\w*|Verwaltungsvorschrift\w*|Richtlinie\w*)\b)", re.IGNORECASE)
WORD_RE = re.compile(r"[\wÄÖÜäöüß\-]+")


def _parse_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        return None


def norm_key(document: Document) -> tuple[str, str] | None:
    """(abbreviation, paragraph) of a norm document; paragraph '' for a whole law."""
    match = PARAGRAPH_TITLE_RE.match(document.title)
    if match:
        return match.group("abbreviation"), match.group("number")
    match = LAW_TITLE_RE.match(document.title)
    if match:
        return match.group("abbreviation"), ""
    return None


class LawCollection:
    def __init__(self, documents: dict[str, Document], today: date | None = None) -> None:
        self.documents = documents
        self.today = today or date.today()
        self.versions: dict[tuple[str, str], list[str]] = defaultdict(list)
        names: dict[str, Counter] = defaultdict(Counter)
        for doc_id, document in documents.items():
            key = norm_key(document)
            if key is None:
                continue
            self.versions[key].append(doc_id)
            head = f"{document.title}\n{document.content[:300]}"
            for match in NAMED_ABBREVIATION_RE.finditer(head):
                if match.group("abbreviation") == key[0]:
                    names[key[0]][" ".join(match.group("name").split())] += 1
        self.abbreviations = {abbreviation: counter.most_common(1)[0][0] for abbreviation, counter in names.items()}
        self._abbreviations_by_head_word: dict[str, list[str]] = defaultdict(list)
        for abbreviation, name in self.abbreviations.items():
            words = [word.lower() for word in WORD_RE.findall(name) if len(word) >= 8]
            if words:
                self._abbreviations_by_head_word[max(words, key=len)].append(abbreviation)

    # -- query side -------------------------------------------------------

    def expand_abbreviations(self, text: str) -> str:
        """Long names for abbreviations in `text`, and abbreviations for law names
        whose most specific word ("Reisekostengesetz") appears in `text`."""
        words = WORD_RE.findall(text)
        extra = [self.abbreviations[word] for word in dict.fromkeys(words) if word in self.abbreviations]
        lowered = {word.lower() for word in words}
        for head_word, abbreviations in self._abbreviations_by_head_word.items():
            if head_word in lowered and len(abbreviations) <= 3:
                extra.extend(abbreviation for abbreviation in abbreviations if abbreviation not in words)
        return " ".join(extra)

    def referenced_abbreviations(self, query: Query) -> list[str]:
        text = " ".join([query.query, query.description, query.narrative])
        return [word for word in dict.fromkeys(WORD_RE.findall(text)) if word in self.abbreviations or (word, "") in self.versions]

    def referenced_paragraphs(self, query: Query) -> list[str]:
        """Current versions of the norms cited as `§ n ABK` anywhere in the query."""
        text = " ".join([query.query, query.description, query.narrative])
        found = []
        for match in PARAGRAPH_REFERENCE_RE.finditer(text):
            key = (match.group("abbreviation"), match.group("number"))
            if key in self.versions:
                found.append(self.current_version(self.versions[key]))
        return list(dict.fromkeys(found))

    def intent(self, query: Query) -> str | None:
        """'decision' or 'norm' if the query clearly asks for one of them."""
        text = " ".join([query.query, query.description, query.narrative])
        wants_decision = bool(DECISION_INTENT_RE.search(text))
        wants_norm = bool(NORM_INTENT_RE.search(text))
        if wants_decision == wants_norm:
            return None
        return "decision" if wants_decision else "norm"

    # -- document side ----------------------------------------------------

    def _validity(self, doc_id: str) -> tuple[date | None, date | None]:
        title = self.documents[doc_id].title
        valid_from = VALID_FROM_RE.search(title)
        valid_until = VALID_UNTIL_RE.search(title)
        return (
            _parse_date(valid_from.group(1) if valid_from else None),
            _parse_date(valid_until.group(1) if valid_until else None),
        )

    def current_version(self, doc_ids: list[str]) -> str:
        """The version in force today with the latest start date; if none is in
        force, the one that expired last."""

        def in_force(doc_id: str) -> bool:
            valid_from, valid_until = self._validity(doc_id)
            return (valid_from is None or valid_from <= self.today) and (valid_until is None or valid_until >= self.today)

        candidates = [doc_id for doc_id in doc_ids if in_force(doc_id)] or doc_ids
        return max(
            candidates,
            key=lambda doc_id: (
                self._validity(doc_id)[1] or date.max,
                self._validity(doc_id)[0] or date.min,
                doc_id,
            ),
        )

    def collapse_versions(self, ranking: Ranking) -> tuple[Ranking, list[str]]:
        """Show each norm once, as its current version, at the rank of its best
        version; the other versions move to the end of the ranking."""
        current_of: dict[str, str] = {}
        for doc_id, _ in ranking:
            key = norm_key(self.documents[doc_id]) if doc_id in self.documents else None
            if key is not None and len(self.versions[key]) > 1:
                current_of[doc_id] = self.current_version(self.versions[key])
        head, demoted, seen = [], [], set()
        for doc_id, score in ranking:
            representative = current_of.get(doc_id, doc_id)
            if representative not in seen:
                seen.add(representative)
                head.append((representative, score))
            if doc_id != representative:
                demoted.append((doc_id, score))
        return head + demoted, [doc_id for doc_id, _ in demoted]

    def is_decision(self, doc_id: str) -> bool:
        return self.documents[doc_id].fields.get("document_type") in DECISION_TYPES

    def abbreviation_ranking(self, ranking: Ranking, abbreviations: list[str]) -> Ranking:
        """Documents of the referenced laws, in their current order."""
        wanted = set(abbreviations)
        return [
            (doc_id, score)
            for doc_id, score in ranking
            if (key := norm_key(self.documents[doc_id])) is not None and key[0] in wanted
        ]
