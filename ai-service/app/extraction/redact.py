"""Hide personal details before text is sent to an outside LLM, and put them back afterwards.

Emails, phone numbers, links and the person's name are swapped for placeholders like
[EMAIL_1]. The real values stay in memory on our side only. Afterwards restore() writes
them back into the results the student sees.

This is best-effort. It cannot find every kind of personal detail (for example a home
address written in a sentence), so we also never ask the model for such things.
"""
import re
from dataclasses import dataclass, field

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# web links, plus well-known profile sites written without https://
_URL = re.compile(
    r"(?:https?://|www\.)[^\s)>\]]+|"
    r"\b(?:linkedin|github|gitlab|leetcode|codeforces|kaggle|medium)\.com/[^\s)>\]]+",
    re.IGNORECASE,
)
# 10 to 14 digits, with optional spaces, dashes, dots, brackets and a leading +
_PHONE = re.compile(r"(?<![\w.])\+?\d(?:[\s().-]?\d){9,13}(?![\w])")
_NAME_LINE = re.compile(r"^[A-Za-z][A-Za-z.'-]*(?: [A-Za-z][A-Za-z.'-]*){1,3}$")


@dataclass
class Redaction:
    text: str                                   # the safe text to send
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> real value (never leaves this server)
    counts: dict[str, int] = field(default_factory=dict)

    def restore(self, value):
        """Put real values back into a string, list or dict (used for what the student sees)."""
        if isinstance(value, str):
            for placeholder, real in self.mapping.items():
                value = value.replace(placeholder, real)
            return value
        if isinstance(value, list):
            return [self.restore(v) for v in value]
        if isinstance(value, dict):
            return {k: self.restore(v) for k, v in value.items()}
        return value


def _guess_name(text: str) -> str | None:
    """The first line of a resume is usually the name: 2 to 4 words, letters only."""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        return line if len(line) <= 40 and _NAME_LINE.match(line) else None
    return None


def redact(text: str) -> Redaction:
    result = Redaction(text=text)

    def swap(pattern, label):
        count = 0

        def repl(match):
            nonlocal count
            count += 1
            placeholder = f"[{label}_{count}]"
            result.mapping[placeholder] = match.group(0)
            return placeholder

        result.text = pattern.sub(repl, result.text)
        result.counts[label.lower()] = count

    swap(_EMAIL, "EMAIL")   # emails first, so a link inside an email is not split
    swap(_URL, "LINK")
    swap(_PHONE, "PHONE")

    name = _guess_name(result.text)
    if name:
        result.mapping["[NAME]"] = name
        result.text = re.sub(re.escape(name), "[NAME]", result.text, flags=re.IGNORECASE)
    result.counts["name"] = 1 if name else 0
    return result
