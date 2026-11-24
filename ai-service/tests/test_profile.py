"""Tests for hiding personal details, schema shape, claim checking and the profile endpoint.
A fake LLM is used, so no internet or key is needed."""
import pytest
from fastapi.testclient import TestClient

import app.extraction.profile as profile_mod
from app.extraction.profile import CATEGORIES, MAX_PROFILE_CHARS, PROFILE_SCHEMA, RawProfile, extract_resume_profile
from app.extraction.redact import redact
from app.llm.client import LlmError
from app.main import app

RESUME = """Asha Rao
asha.rao@example.com | +91 98765 43210 | linkedin.com/in/asharao
EDUCATION
B.Tech in Computer Science, IIIT Raichur, 2027, CGPA 8.5
EXPERIENCE
- Software intern at Acme, built REST APIs with Node.js
PROJECTS
- Resume matcher using Python and React (github.com/asharao/matcher)
SKILLS
Python, SQL, Docker
AWARDS
- Winner of college hackathon 2025
"""


def empty_answer(**overrides):
    base = {c: [] for c in CATEGORIES}
    base.update(overrides)
    return base


# ---------- hiding personal details ----------
def test_redaction_hides_and_restores():
    hidden = redact(RESUME)
    for secret in ["asha.rao@example.com", "98765 43210", "linkedin.com/in/asharao", "github.com/asharao/matcher", "Asha Rao"]:
        assert secret not in hidden.text
    assert "[EMAIL_1]" in hidden.text and "[PHONE_1]" in hidden.text and "[NAME]" in hidden.text
    assert hidden.counts == {"email": 1, "link": 2, "phone": 1, "name": 1}
    assert hidden.restore("mail me at [EMAIL_1]") == "mail me at asha.rao@example.com"
    assert hidden.restore({"a": ["[NAME]"]}) == {"a": ["Asha Rao"]}


def test_redaction_keeps_ordinary_numbers():
    hidden = redact("Rahul Verma\nB.Tech 2021-2025, CGPA 8.52, rank 1042, score 98.5%")
    assert "2021-2025" in hidden.text and "8.52" in hidden.text and "1042" in hidden.text
    assert hidden.counts["phone"] == 0


def test_name_guess_ignores_headings_with_digits_or_long_lines():
    assert redact("EDUCATION\nB.Tech").counts["name"] == 0   # a one-word first line is never a name
    assert redact("Summary of my 3 years in software development and testing work").counts["name"] == 0
    assert redact("Asha Rao\nEDUCATION").counts["name"] == 1  # a normal name line is found


# ---------- schema must be compatible with Groq strict mode ----------
def _walk(node, path="schema"):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False, path
            assert set(node["required"]) == set(node["properties"]), path
        for key, value in node.items():
            _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _walk(value, f"{path}[{i}]")


def test_schema_is_strict_compatible():
    _walk(PROFILE_SCHEMA)
    assert set(PROFILE_SCHEMA["properties"]) == set(CATEGORIES)


def test_pydantic_accepts_a_full_valid_answer():
    RawProfile.model_validate(empty_answer(
        technical_skills=[{"name": "Python", "quote": "Python"}],
        education=[{"degree": None, "institution": "IIIT", "field_of_study": None, "year": None, "quote": "IIIT"}],
        experience=[{"title": None, "organization": "Acme", "kind": "internship", "duration": None,
                     "responsibilities": [], "quote": "Acme"}],
    ))


def test_pydantic_rejects_bad_kind():
    with pytest.raises(Exception):
        RawProfile.model_validate(empty_answer(achievements=[{"title": "x", "kind": "magic", "description": None, "quote": "x"}]))


# ---------- end to end with a fake LLM ----------
@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def fake(system, user, schema, schema_name, validate_with=None, max_output_tokens=2048):
        calls.append({"system": system, "user": user, "max": max_output_tokens})
        return fake.answer

    fake.answer = empty_answer()
    monkeypatch.setattr(profile_mod, "generate_json", fake)
    fake.calls = calls
    return fake


def test_personal_details_never_reach_the_llm(fake_llm):
    extract_resume_profile(RESUME)
    sent = fake_llm.calls[0]["user"]
    for secret in ["asha.rao@example.com", "98765", "linkedin.com", "github.com", "Asha Rao"]:
        assert secret not in sent
    assert fake_llm.calls[0]["max"] >= 4096  # room for a full profile (Groq default is 1024)


def test_supported_vs_invented_claims(fake_llm):
    fake_llm.answer = empty_answer(
        technical_skills=[
            {"name": "Python", "quote": "Python, SQL, Docker"},
            {"name": "Kubernetes", "quote": "Kubernetes, Helm"},          # never written in the resume
            {"name": "python", "quote": "Python, SQL, Docker"},          # duplicate of the first
        ],
        education=[{"degree": "B.Tech in Computer Science", "institution": "IIIT Raichur", "field_of_study": None,
                    "year": "2027", "quote": "B.Tech in Computer Science, IIIT Raichur, 2027"}],
        funding=[{"description": "Government grant of ₹2 crore", "source": "DST", "amount_text": "₹2 crore",
                  "purpose": None, "candidate_role": None, "outcome": None, "quote": "Received ₹2 crore DST grant"}],
    )
    out = extract_resume_profile(RESUME)
    skills = {s["name"]: s["status"] for s in out["profile"]["technical_skills"]}
    assert skills == {"Python": "supported", "Kubernetes": "needs_review"}      # duplicate dropped, invented flagged
    assert out["profile"]["education"][0]["status"] == "supported"
    assert out["profile"]["funding"][0]["status"] == "needs_review"               # invented funding is NOT trusted
    assert out["needs_review"] == 2 and out["counts"]["technical_skills"] == 2


def test_quote_with_right_words_but_wrong_field_is_flagged(fake_llm):
    fake_llm.answer = empty_answer(education=[{
        "degree": "B.Tech", "institution": "Stanford University", "field_of_study": None, "year": None,
        "quote": "B.Tech in Computer Science, IIIT Raichur, 2027"}])
    item = extract_resume_profile(RESUME)["profile"]["education"][0]
    assert item["status"] == "needs_review" and "Stanford" in item["note"]


def test_real_values_come_back_for_the_student(fake_llm):
    fake_llm.answer = empty_answer(projects=[{
        "title": "Resume matcher", "description": None, "technologies": ["Python", "React"], "role": None,
        "outcome": None, "links": ["[LINK_2]"],
        "quote": "Resume matcher using Python and React ([LINK_2])"}])
    item = extract_resume_profile(RESUME)["profile"]["projects"][0]
    assert item["links"] == ["github.com/asharao/matcher"]       # placeholder restored
    assert item["status"] == "supported"                          # verified against the placeholder text
    assert "[LINK_2]" not in item["quote"]


def test_bullets_and_line_breaks_do_not_break_quote_matching(fake_llm):
    fake_llm.answer = empty_answer(experience=[{
        "title": None, "organization": "Acme", "kind": "internship", "duration": None, "responsibilities": [],
        "quote": "Software intern at Acme, built REST APIs with Node.js"}])
    assert extract_resume_profile(RESUME)["profile"]["experience"][0]["status"] == "supported"


def test_long_resume_is_cut_and_disclosed(fake_llm):
    out = extract_resume_profile("Asha Rao\n" + "word " * 6000)
    assert any("only the first" in w for w in out["warnings"])
    assert len(fake_llm.calls[0]["user"]) < MAX_PROFILE_CHARS + 100


# ---------- endpoint ----------
client = TestClient(app)
KEY = {"X-Service-Key": "test-key"}


@pytest.fixture(autouse=True)
def service_key(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_KEY", "test-key")


def test_endpoint_needs_service_key():
    assert client.post("/internal/extract/profile", json={"text": "x" * 50}).status_code == 401


def test_endpoint_rejects_tiny_text():
    assert client.post("/internal/extract/profile", headers=KEY, json={"text": "hi"}).status_code == 422


def test_endpoint_success(fake_llm):
    fake_llm.answer = empty_answer(technical_skills=[{"name": "SQL", "quote": "SQL"}])
    r = client.post("/internal/extract/profile", headers=KEY, json={"text": RESUME})
    body = r.json()
    assert r.status_code == 200 and body["counts"]["technical_skills"] == 1 and body["prompt_version"] == "resume-profile-v1"
    assert "asha.rao@example.com" not in str(fake_llm.calls)


@pytest.mark.parametrize("kind, status", [("not_configured", 503), ("rate_limited", 429), ("auth", 502), ("too_long", 502)])
def test_endpoint_maps_llm_errors(monkeypatch, kind, status):
    def boom(*a, **k):
        raise LlmError(kind, "problem text")
    monkeypatch.setattr(profile_mod, "generate_json", boom)
    r = client.post("/internal/extract/profile", headers=KEY, json={"text": RESUME})
    assert r.status_code == status and r.json()["detail"] == "problem text"
