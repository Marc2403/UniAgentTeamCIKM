#!/usr/bin/env python3
"""Write a robustness input directory: broken PDF, empty case, very long PDF, non-PDF file, one normal case.

Usage: make_inputs.py <spot-check inputs dir to copy one real case from> <output dir>
"""

import shutil
import sys
from pathlib import Path


def write_pdf(path: Path, pages: list[list[str]]) -> None:
    """A minimal PDF with one text page per entry of `pages`."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for lines in pages:
        escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
        content = "BT /F1 9 Tf 40 800 Td 11 TL " + " ".join(f"({line}) '" for line in escaped) + " ET"
        objects.append(f"<< /Length {len(content.encode('cp1252'))} >>\nstream\n{content}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {len(objects)} 0 R /Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    output, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n{body}\nendobj\n".encode("cp1252")
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    output += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    output += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(output)


def main() -> None:
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    shutil.copytree(source / "beschaffungsantrag-02", target / "beschaffungsantrag-02")
    broken = target / "auslagenerstattung-90"
    broken.mkdir()
    (broken / "rechnung.pdf").write_bytes(b"%PDF-1.4\nthis is not a PDF body\n%%EOF\n")
    (broken / "notiz.txt").write_text("Bitte erstatten.", encoding="utf-8")
    (target / "dienstreiseantrag-91").mkdir()
    long_case = target / "beschaffungsantrag-92"
    long_case.mkdir()
    line = "Position {0}: Laborzubehör Artikel {0} Menge 1 Einzelpreis 12,50 EUR Gesamt 12,50 EUR"
    write_pdf(long_case / "beschaffungsantrag.pdf", [[f"Beschaffungsantrag Universität Wernstadt, Seite {page}"] + [line.format(page * 60 + row) for row in range(60)] for page in range(400)])


if __name__ == "__main__":
    main()
