"""Internal endpoints used by the Node backend (never by browsers)."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.llm import STATUS_FOR
from app.extraction.cleaning import clean_text
from app.extraction.pdf_reader import PdfReadError, extract_pdf_text
from app.extraction.profile import extract_resume_profile
from app.extraction.sections import find_sections
from app.llm.client import LlmError
from app.schemas import DocType, ExtractionResult, ProfileRequest, TextRequest
from app.security import require_service_key

EXTRACTOR_VERSION = "text-v1"
MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 60000

router = APIRouter(prefix="/internal", dependencies=[Depends(require_service_key)])


def _build_result(raw_text: str, doc_type: str, meta: dict) -> ExtractionResult:
    """Shared by both endpoints: clean the text, find sections, assemble the reply."""
    warnings = list(meta.get("warnings", []))
    text = clean_text(raw_text)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        warnings.append(f"The text was longer than {MAX_TEXT_CHARS} characters and was cut.")

    found = find_sections(text, doc_type)
    if text and not found["headings_recognised"]:
        warnings.append("No standard section headings were recognised, so the text is kept as one block.")

    return ExtractionResult(
        text=text,
        sections=found["sections"],
        expected_not_found=found["expected_not_found"],
        headings_recognised=found["headings_recognised"],
        page_count=meta.get("page_count", 0),
        pages_read=meta.get("pages_read", 0),
        char_count=len(text),
        warnings=warnings,
        scanned_suspected=meta.get("scanned_suspected", False),
        extractor_version=EXTRACTOR_VERSION,
    )


# A normal (sync) function: FastAPI runs it in a worker thread, so reading a PDF
# does not freeze the whole service.
@router.post("/extract/document", response_model=ExtractionResult)
def extract_document(doc_type: DocType = Form(...), file: UploadFile = File(...)):
    data = file.file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (max 5 MB)")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Only real PDF files are allowed")
    try:
        meta = extract_pdf_text(data)
    except PdfReadError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return _build_result(meta["text"], doc_type, meta)


@router.post("/extract/profile")
def extract_profile(body: ProfileRequest):
    """Resume text -> structured profile (skills, education, experience...) using the LLM.
    Every claim is checked against the text; nothing here is a score."""
    try:
        return extract_resume_profile(body.text)
    except LlmError as err:
        raise HTTPException(status_code=STATUS_FOR.get(err.kind, 502), detail=err.user_message) from err


@router.post("/analyze/text", response_model=ExtractionResult)
def analyze_text(body: TextRequest):
    """For pasted text (job descriptions typed in by the student)."""
    return _build_result(body.text, body.doc_type, {})
