import logging
from pathlib import Path
from typing import Dict, List, Tuple

from pypdf import PdfReader

log = logging.getLogger(__name__)

# pypdf recovers from malformed PDFs but logs loudly; keep the run quiet.
logging.getLogger("pypdf").setLevel(logging.ERROR)


def list_pdfs(case_dir: Path) -> List[Path]:
    return sorted(p for p in case_dir.iterdir() if p.suffix.lower() == ".pdf")


def extract_pdf_text(pdf_path: Path) -> Tuple[str, str]:
    try:
        reader = PdfReader(str(pdf_path))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception as exc:  # noqa: BLE001
                parts.append("")
                log.warning("page extract failed %s: %s", pdf_path, exc)
        text = "\n".join(parts).strip()
        if not text:
            return "", "empty_text_layer"
        return text, "ok"
    except Exception as exc:  # noqa: BLE001
        return "", f"{type(exc).__name__}: {exc}"


def extract_case(case_dir: Path) -> Dict[str, object]:
    docs = []
    for pdf in list_pdfs(case_dir):
        text, status = extract_pdf_text(pdf)
        docs.append({"name": pdf.name, "chars": len(text), "status": status, "text": text})
    full_text = "\n\n".join(d["text"] for d in docs if d["text"])
    return {"documents": docs, "full_text": full_text}