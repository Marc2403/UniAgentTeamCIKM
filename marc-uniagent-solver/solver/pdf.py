"""PDF text extraction: pdftotext in reading order, pdfplumber as fallback."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfText:
    name: str
    pages: list[str]
    method: str
    error: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(self.pages).strip()


def _pdftotext(path: Path) -> list[str]:
    # -raw keeps the content-stream order; -layout interleaves table columns and form labels.
    result = subprocess.run(
        ["pdftotext", "-raw", "-enc", "UTF-8", str(path), "-"],
        capture_output=True,
        timeout=60,
        check=True,
    )
    pages = result.stdout.decode("utf-8", errors="replace").split("\f")
    return [page.strip() for page in pages if page.strip()]


def _pdfplumber(path: Path) -> list[str]:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return [text.strip() for text in (page.extract_text() or "" for page in pdf.pages) if text.strip()]


def read_pdf(path: Path) -> PdfText:
    errors = []
    for method, extract in (("pdftotext", _pdftotext), ("pdfplumber", _pdfplumber)):
        try:
            pages = extract(path)
        except Exception as error:  # a broken PDF must not stop the case
            errors.append(f"{method}: {error}")
            continue
        if pages:
            return PdfText(path.name, pages, method)
        errors.append(f"{method}: no text")
    return PdfText(path.name, [], "none", "; ".join(errors))
