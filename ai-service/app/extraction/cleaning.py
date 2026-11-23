"""Step 2 of extraction: tidy the raw text so later steps see consistent input.

Only formatting is changed here. No words are added, removed or guessed.
"""
import re
import unicodedata

# Characters PDFs use as bullets. We turn them all into "- ".
BULLET_CHARS = "•●▪■◦‣∙▸►➢➤✓✔"

# soft hyphen, zero-width space/non-joiner/joiner, byte-order mark (written as codes, not as invisible characters)
_HIDDEN = dict.fromkeys([0x00AD, 0x200B, 0x200C, 0x200D, 0xFEFF], None)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BULLET_START = re.compile(rf"^[ \t]*[{BULLET_CHARS}][ \t]*", re.MULTILINE)
_BROKEN_WORD = re.compile(r"(?<=[a-z])-\n(?=[a-z])")  # "devel-\nopment" -> "development"
_SPACES = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")
# Lines that are only a page marker, like "Page 2 of 3" or "2 / 3"
_PAGE_MARKER = re.compile(r"^[ \t]*(?:page[ \t]*)?\d{1,3}[ \t]*(?:/|of)[ \t]*\d{1,3}[ \t]*$", re.MULTILINE | re.IGNORECASE)


def clean_text(raw: str) -> str:
    # NFKC turns look-alike characters into plain ones (ligature "ﬁ" -> "fi")
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n").translate(_HIDDEN)
    text = _CONTROL.sub("", text)
    text = _BULLET_START.sub("- ", text)
    text = _BROKEN_WORD.sub("", text)
    text = _PAGE_MARKER.sub("", text)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()
