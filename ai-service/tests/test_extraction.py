import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.extraction.cleaning import clean_text
from app.extraction.sections import find_sections
from app.main import app

KEY = {"X-Service-Key": "test-key"}


@pytest.fixture(autouse=True)
def service_key(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_KEY", "test-key")


def make_pdf(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 18
    return doc.tobytes()


# ---------- cleaning ----------
def test_cleaning_bullets_hyphens_and_page_markers():
    raw = "• Built APIs\n● Led a team\ndevel-\nopment work\nPage 2 of 3\n\n\n\nEnd"
    out = clean_text(raw)
    assert "- Built APIs" in out and "- Led a team" in out
    assert "development work" in out          # broken word joined
    assert "Page 2 of 3" not in out           # page marker removed
    assert "\n\n\n" not in out                # blank lines collapsed


def test_cleaning_keeps_real_hyphenated_names():
    assert "Full-Stack" in clean_text("Full-Stack Developer")
    assert "React-\nNative" in clean_text("React-\nNative")  # capital letter: not joined


def test_cleaning_ligatures():
    assert clean_text("eﬃcient ﬁle") == "efficient file"


# ---------- sections ----------
def test_resume_sections_with_different_heading_styles():
    text = "Jane Doe\njane@x.com\nEDUCATION\nB.Tech CSE\nWork History:\nIntern at Acme\nSkills & Tools\nPython, SQL"
    result = find_sections(text, "resume")
    names = [s["name"] for s in result["sections"]]
    assert names == ["preamble", "education", "experience", "skills"]
    assert result["expected_not_found"] == ["projects"]
    assert result["headings_recognised"] is True


def test_sentence_lines_are_not_headings():
    text = "Skills\nI have skills in Python.\n- Education is important to me"
    result = find_sections(text, "resume")
    assert [s["name"] for s in result["sections"]] == ["skills"]


def test_combined_heading():
    result = find_sections("Education and Certifications\nB.Tech", "resume")
    assert result["sections"][0]["name"] == "education"


def test_jd_sections():
    text = "Full Stack Developer\nResponsibilities:\nBuild APIs\nRequired Qualifications\nReact\nNice to have\nDocker"
    result = find_sections(text, "jd")
    assert [s["name"] for s in result["sections"]] == ["preamble", "responsibilities", "requirements", "preferred"]


def test_no_headings_keeps_text():
    result = find_sections("Just a paragraph with no headings at all", "resume")
    assert result["headings_recognised"] is False
    assert result["sections"][0]["name"] == "preamble"


# ---------- API ----------
client = TestClient(app)


def test_api_requires_key():
    assert client.post("/internal/analyze/text", json={"text": "hi", "doc_type": "jd"}).status_code == 401


def test_api_refuses_when_key_not_configured(monkeypatch):
    monkeypatch.delenv("AI_SERVICE_KEY")
    assert client.post("/internal/analyze/text", headers=KEY, json={"text": "hi", "doc_type": "jd"}).status_code == 503


def test_api_pdf_extraction():
    pdf = make_pdf(["EDUCATION", "B.Tech in Computer Science", "SKILLS", "Python and SQL and React and Node"])
    r = client.post("/internal/extract/document", headers=KEY, data={"doc_type": "resume"},
                    files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert [s["name"] for s in body["sections"]] == ["education", "skills"]
    assert body["pages_read"] == 1 and body["char_count"] > 0


def test_api_rejects_fake_pdf_and_bad_type():
    r = client.post("/internal/extract/document", headers=KEY, data={"doc_type": "resume"},
                    files={"file": ("cv.pdf", b"not a pdf at all", "application/pdf")})
    assert r.status_code == 400
    r = client.post("/internal/extract/document", headers=KEY, data={"doc_type": "poem"},
                    files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 422


def test_api_damaged_pdf_gives_clean_error():
    r = client.post("/internal/extract/document", headers=KEY, data={"doc_type": "jd"},
                    files={"file": ("cv.pdf", b"%PDF-1.4 garbage garbage", "application/pdf")})
    assert r.status_code == 422


def test_api_scanned_pdf_warns():
    doc = pymupdf.open()
    doc.new_page()  # a page with no text, like a scanned image
    r = client.post("/internal/extract/document", headers=KEY, data={"doc_type": "resume"},
                    files={"file": ("scan.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 200 and r.json()["scanned_suspected"] is True


def test_api_pasted_text():
    r = client.post("/internal/analyze/text", headers=KEY,
                    json={"text": "Requirements:\nReact\nPreferred:\nDocker", "doc_type": "jd"})
    assert [s["name"] for s in r.json()["sections"]] == ["requirements", "preferred"]
