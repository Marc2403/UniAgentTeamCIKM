"""Parsers for German/English amounts and dates, and the shared Finding type."""

import re
from dataclasses import asdict, dataclass, field
from datetime import date

PASS = "pass"
FAIL = "fail"
UNCLEAR = "unclear"
NOT_APPLICABLE = "n/a"


@dataclass
class Finding:
    rule_id: str
    status: str
    detail: str
    sources: list[str] = field(default_factory=list)
    # A failed hard check rejects the case on its own; a soft one is only a hint for the model.
    hard: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


_CURRENCY = re.compile(r"(?i)\b(?:eur|euro|usd|chf|gbp)\b|[€$£]")


def parse_amount(value) -> float | None:
    """Parse 2.667,00 € / €84.02 / USD 1,234.50 / 1.200 / -229,00 EUR into a float.

    A lone separator followed by exactly three digits is read as a thousands
    separator (German 1.200 = 1200); otherwise the last separator is decimal.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _CURRENCY.sub("", str(value)).replace("−", "-").replace(" ", "").replace(" ", "")
    text = text.rstrip(".-")
    match = re.fullmatch(r"([+-]?)([\d.,]*\d)", text)
    if not match:
        return None
    sign, number = match.groups()
    last_dot, last_comma = number.rfind("."), number.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal = "." if last_dot > last_comma else ","
        thousands = "," if decimal == "." else "."
        number = number.replace(thousands, "").replace(decimal, ".")
    elif last_dot >= 0 or last_comma >= 0:
        separator = "." if last_dot >= 0 else ","
        parts = number.split(separator)
        if len(parts) > 2 or (len(parts[-1]) == 3 and parts[0] != "0"):
            number = number.replace(separator, "")
        else:
            number = number.replace(separator, ".")
    try:
        return float(sign + number)
    except ValueError:
        return None


_MONTHS = {
    "jan": 1, "januar": 1, "january": 1, "jän": 1,
    "feb": 2, "februar": 2, "february": 2,
    "mär": 3, "mar": 3, "märz": 3, "maerz": 3, "march": 3,
    "apr": 4, "april": 4,
    "mai": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oct": 10, "oktober": 10, "october": 10,
    "nov": 11, "november": 11,
    "dez": 12, "dec": 12, "dezember": 12, "december": 12,
}

_MONTH_NAME = r"([A-Za-zÄÖÜäöü]{3,9})\.?"
_DATE_PATTERNS = (
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), ("y", "m", "d")),
    (re.compile(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})(?!\d)"), ("d", "m", "y")),
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), ("d", "m", "y")),
    (re.compile(r"(\d{1,2})\.?[\s-]+" + _MONTH_NAME + r"[\s-]+(\d{4})"), ("d", "M", "y")),
    (re.compile(_MONTH_NAME + r"\s+(\d{1,2}),?\s+(\d{4})"), ("M", "d", "y")),
)


def _build_date(parts: dict[str, str]) -> date | None:
    if "M" in parts:
        month = _MONTHS.get(parts["M"].lower())
        if month is None:
            return None
    else:
        month = int(parts["m"])
    year = int(parts["y"])
    if year < 100:
        year += 2000
    try:
        return date(year, month, int(parts["d"]))
    except ValueError:
        return None


def parse_date(value) -> date | None:
    """Parse the first date in 20.10.2026 / 2027-02-11 / 14. Oktober 2026 / 12-FEB-2027 / 13.03.27."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    found = []
    for pattern, order in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            parsed = _build_date(dict(zip(order, match.groups())))
            if parsed is not None:
                found.append((match.start(), parsed))
    return min(found)[1] if found else None


_AMOUNT_IN_TEXT = re.compile(
    r"(?<![\d.,])(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?![\d,])"  # 2.667,00 / 94,40
    r"|(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d.])"  # 1,234.50 / 84.02
)


def amounts_in_text(text: str) -> list[float]:
    """Every money-like number with two decimals in `text`."""
    return [amount for amount in (parse_amount(token) for token in _AMOUNT_IN_TEXT.findall(text)) if amount is not None]


def same_amount(first: float | None, second: float | None, relative: float = 0.01, absolute: float = 1.0) -> bool:
    """Equal within the larger of 1 € and 1 %, so rounding never counts as a mismatch."""
    if first is None or second is None:
        return False
    return abs(first - second) <= max(absolute, relative * max(abs(first), abs(second)))


def appears_in(amount: float | None, text: str) -> bool:
    return amount is not None and any(abs(amount - candidate) < 0.005 for candidate in amounts_in_text(text))


def format_amount(amount: float | None) -> str:
    if amount is None:
        return "?"
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{formatted} €"
