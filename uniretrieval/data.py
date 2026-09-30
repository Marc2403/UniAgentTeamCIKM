"""Dataset loading: queries and documents with all their fields.

A local dataset directory (queries.jsonl + documents.jsonl[.gz], the layout TIRA
mounts as $inputDataset) is read directly so every document field survives.
Anything else (e.g. a TIRA dataset ID) goes through tira's ir_datasets loader,
as in the organisers' baselines. Unknown or missing fields are tolerated.
"""

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class Query:
    qid: str
    query: str
    description: str = ""
    narrative: str = ""
    language: str = ""


@dataclass
class Document:
    doc_id: str
    title: str = ""
    url: str = ""
    content: str = ""
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.content}" if self.title else self.content


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _query_from_record(record: dict[str, Any]) -> Query:
    original = record.get("original_query")
    if not isinstance(original, dict):
        raise ValueError(f"Query {record.get('qid')} does not provide an original_query dictionary.")
    return Query(
        qid=str(record["qid"]),
        query=_as_text(record.get("query")),
        description=_as_text(original.get("description")),
        narrative=_as_text(original.get("narrative")),
        language=_as_text(original.get("language")),
    )


def _document_from_record(record: dict[str, Any]) -> Document:
    title = _as_text(record.get("title"))
    content = _as_text(record.get("content")) or _as_text(record.get("text"))
    known = {"doc_id", "title", "url", "content", "text"}
    return Document(
        doc_id=str(record["doc_id"]),
        title=title,
        url=_as_text(record.get("url")),
        content=content,
        fields={key: value for key, value in record.items() if key not in known},
    )


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _local_files(directory: Path) -> tuple[Path, Path] | None:
    queries = directory / "queries.jsonl"
    documents = next(
        (directory / name for name in ("documents.jsonl.gz", "documents.jsonl") if (directory / name).is_file()),
        None,
    )
    if queries.is_file() and documents is not None:
        return queries, documents
    return None


def _load_via_tira(dataset: str) -> tuple[list[Query], dict[str, Document]]:
    from tira.third_party_integrations import ir_datasets

    loaded = ir_datasets.load(dataset)
    queries = [
        _query_from_record(
            {"qid": query.query_id, "query": query.default_text(), "original_query": query.original_query}
        )
        for query in loaded.queries_iter()
    ]
    documents = {}
    for document in loaded.docs_iter():
        record = document._asdict() if hasattr(document, "_asdict") else {}
        record.setdefault("doc_id", document.doc_id)
        record.setdefault("text", document.default_text())
        documents[str(document.doc_id)] = _document_from_record(record)
    return queries, documents


def load_dataset(dataset: str) -> tuple[list[Query], dict[str, Document]]:
    files = _local_files(Path(dataset)) if Path(dataset).is_dir() else None
    if files is None:
        return _load_via_tira(dataset)
    queries_path, documents_path = files
    queries = [_query_from_record(record) for record in _read_jsonl(queries_path)]
    documents = {}
    for record in _read_jsonl(documents_path):
        document = _document_from_record(record)
        documents[document.doc_id] = document
    return queries, documents


def detect_language(queries: list[Query]) -> str:
    if not queries:
        raise ValueError("Cannot detect a language because the dataset has no queries.")
    languages = {query.language for query in queries}
    if "" in languages:
        raise ValueError("Every query must provide a valid language.")
    if len(languages) != 1:
        raise ValueError("Expected all queries to have one language, found: " + ", ".join(sorted(languages)))
    return languages.pop()


def detect_collection(documents: dict[str, Document], configured: str = "auto") -> str:
    """`law` if documents carry legal metadata (document_type), else `web`."""
    if configured in {"web", "law"}:
        return configured
    if configured != "auto":
        raise ValueError(f"Unknown collection kind: {configured}")
    has_legal_metadata = any(document.fields.get("document_type") for document in documents.values())
    return "law" if has_legal_metadata else "web"
