"""Shapes of the data going in and out. Pydantic checks them automatically."""
from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["resume", "jd"]


class Section(BaseModel):
    name: str      # our standard name, e.g. "education"
    heading: str   # the heading exactly as written in the document
    text: str


class ExtractionResult(BaseModel):
    text: str                          # cleaned full text
    sections: list[Section]
    expected_not_found: list[str]      # common sections we did not find (NOT a judgement)
    headings_recognised: bool
    page_count: int = 0
    pages_read: int = 0
    char_count: int
    warnings: list[str]
    scanned_suspected: bool = False
    extractor_version: str


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=60000)
    doc_type: DocType
