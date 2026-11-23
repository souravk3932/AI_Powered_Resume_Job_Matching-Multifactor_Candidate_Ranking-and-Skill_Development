"""Step 1 of extraction: read the raw text out of a PDF using PyMuPDF."""
import pymupdf

MAX_PAGES = 15            # resumes and job descriptions are short; ignore the rest
MIN_CHARS_PER_PAGE = 40   # fewer than this per page usually means a scanned image


class PdfReadError(Exception):
    """Raised when the PDF cannot be opened or read. The message is safe to show."""


def extract_pdf_text(data: bytes) -> dict:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several different error types
        raise PdfReadError("Could not open this PDF. The file may be damaged.") from exc

    warnings: list[str] = []
    with doc:
        if doc.needs_pass:
            raise PdfReadError("This PDF is password-protected. Remove the password and upload it again.")

        page_count = doc.page_count
        pages: list[str] = []
        for index, page in enumerate(doc):
            if index >= MAX_PAGES:
                warnings.append(f"Only the first {MAX_PAGES} pages were read.")
                break
            pages.append(page.get_text("text"))

    text = "\n\n".join(pages)
    pages_read = len(pages)

    # A PDF made of scanned pictures has almost no real text
    scanned = pages_read > 0 and len(text.strip()) < MIN_CHARS_PER_PAGE * pages_read
    if scanned:
        warnings.append(
            "This PDF looks like scanned images, so little or no text could be read. "
            "Reading scanned documents (OCR) is not supported yet."
        )

    return {
        "text": text,
        "page_count": page_count,
        "pages_read": pages_read,
        "warnings": warnings,
        "scanned_suspected": scanned,
    }
