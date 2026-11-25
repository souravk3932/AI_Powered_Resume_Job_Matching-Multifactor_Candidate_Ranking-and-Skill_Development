"""Turn the dates people write ("May 2025 - Jul 2025", "2 years", "2023 - Present") into a number of months."""
import re
from datetime import date

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_NOW = r"present|current|now|ongoing|till date|to date"

_MONTH_RANGE = re.compile(
    rf"(?P<m1>[A-Za-z]{{3,9}})\.?\s*,?\s*(?P<y1>(?:19|20)\d{{2}})\s*(?:-|–|—|to|until)\s*"
    rf"(?:(?P<m2>[A-Za-z]{{3,9}})\.?\s*,?\s*(?P<y2>(?:19|20)\d{{2}})|(?P<now>{_NOW}))", re.I)
_YEAR_RANGE = re.compile(rf"(?P<y1>(?:19|20)\d{{2}})\s*(?:-|–|—|to)\s*(?:(?P<y2>(?:19|20)\d{{2}})|(?P<now>{_NOW}))", re.I)
_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(years?|yrs?|months?|mos?)\b", re.I)


_FULL = {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"}
_REAL_NAMES = _FULL | set(_MONTHS) | {"sept"}


def _month(name: str) -> int | None:
    """Only real month names or their usual short forms count ('Decision' is not December)."""
    key = name.lower()
    return _MONTHS.get(key[:3]) if key in _REAL_NAMES else None


def parse_months(text: str | None, today: date | None = None) -> float | None:
    """Months covered by a duration written in words or dates. Both ends of a date range are counted
    (May 2025 to Jul 2025 = 3 months). Returns None when nothing readable is found."""
    if not text:
        return None
    today = today or date.today()

    m = _MONTH_RANGE.search(text)
    if m and _month(m["m1"]):
        start = int(m["y1"]) * 12 + _month(m["m1"])
        if m["now"]:
            end = today.year * 12 + today.month
        elif _month(m["m2"] or ""):
            end = int(m["y2"]) * 12 + _month(m["m2"])
        else:
            end = None
        if end is not None and end >= start:
            return float(end - start + 1)

    m = _AMOUNT.search(text)
    if m:
        value = float(m.group(1))
        return value * 12 if m.group(2).lower().startswith(("y")) else value

    m = _YEAR_RANGE.search(text)
    if m:
        end_year = today.year if m["now"] else int(m["y2"])
        if end_year >= int(m["y1"]):
            return float((end_year - int(m["y1"])) * 12)
    return None


def required_years(text: str | None) -> float | None:
    """'3+ years of experience' -> 3.0. Only counts amounts written in years."""
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", text, re.I)
    return float(m.group(1)) if m else None
