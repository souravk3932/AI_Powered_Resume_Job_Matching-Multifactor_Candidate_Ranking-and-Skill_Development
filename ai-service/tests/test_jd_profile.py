"""Tests for job description extraction. A fake LLM is used (no internet or key)."""
import pytest
from fastapi.testclient import TestClient

import app.extraction.jd_profile as jd_mod
from app.extraction.jd_profile import JD_CATEGORIES, JD_SCHEMA, RawJdProfile, extract_jd_profile
from app.extraction.redact import redact
from app.llm.client import LlmError
from app.main import app

JD = """Full Stack Developer
Contact hr@acme.com or +91 99999 88888 to apply.
Responsibilities:
- Build and maintain REST APIs in Node.js
Required Qualifications
- Strong React and SQL skills
- B.Tech in Computer Science
- 2+ years of experience in web development
Nice to have
- Docker and AWS knowledge
Good communication skills are important."""


def answer(**overrides):
    base = {c: [] for c in JD_CATEGORIES}
    base["job_title"] = None
    base.update(overrides)
    return base


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def fake(system, user, schema, schema_name, validate_with=None, max_output_tokens=2048, reasoning_effort=None):
        calls.append(user)
        return fake.answer

    fake.answer = answer()
    fake.calls = calls
    monkeypatch.setattr(jd_mod, "generate_json", fake)
    return fake


@pytest.fixture
def no_rule(monkeypatch):
    """Switch the completeness check off, for tests that are only about checking the AI's own answer."""
    monkeypatch.setattr(jd_mod, "completeness_check", lambda *a, **k: 0)


@pytest.fixture(autouse=True)
def service_key(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_KEY", "test-key")


def _strict(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False and set(node["required"]) == set(node["properties"])
        for v in node.values():
            _strict(v)
    elif isinstance(node, list):
        for v in node:
            _strict(v)


def test_schema_is_strict_compatible():
    _strict(JD_SCHEMA)
    assert set(JD_SCHEMA["properties"]) == set(JD_CATEGORIES) | {"job_title"}


def test_pydantic_accepts_valid_answer():
    RawJdProfile.model_validate(answer(
        required_skills=[{"name": "React", "quote": "React"}],
        certifications=[{"name": "AWS", "required": False, "quote": "AWS"}],
        experience_requirements=[{"text": "2+ years", "years": "2+", "quote": "2+ years"}]))


def test_job_title_line_is_not_hidden_as_a_name():
    assert "Full Stack Developer" in redact(JD, hide_name=False).text
    assert "[NAME]" in redact(JD, hide_name=True).text        # for contrast: resumes hide the first line


def test_contacts_are_hidden_but_title_is_kept(fake_llm):
    extract_jd_profile(JD)
    sent = fake_llm.calls[0]
    assert "hr@acme.com" not in sent and "99999" not in sent
    assert "Full Stack Developer" in sent


def test_supported_vs_invented_requirements(fake_llm, no_rule):
    fake_llm.answer = answer(
        job_title="Full Stack Developer",
        required_skills=[{"name": "React", "quote": "Strong React and SQL skills"},
                         {"name": "Kubernetes", "quote": "Kubernetes experience required"}],   # not in the text
        preferred_skills=[{"name": "Docker", "quote": "Docker and AWS knowledge"}],
        experience_requirements=[{"text": "2+ years in web development", "years": "2+",
                                  "quote": "2+ years of experience in web development"}],
        certifications=[{"name": "PMP", "required": True, "quote": "PMP certification"}],     # invented
    )
    out = extract_jd_profile(JD)
    p = out["profile"]
    assert {s["name"]: s["status"] for s in p["required_skills"]} == {"React": "supported", "Kubernetes": "needs_review"}
    assert p["preferred_skills"][0]["status"] == "supported"
    assert p["experience_requirements"][0]["status"] == "supported"
    assert p["certifications"][0]["status"] == "needs_review"
    assert out["needs_review"] == 2 and p["job_title"] == "Full Stack Developer"


def test_made_up_job_title_is_dropped(fake_llm):
    fake_llm.answer = answer(job_title="Chief Wizard")
    assert extract_jd_profile(JD)["profile"]["job_title"] is None


def test_same_skill_in_required_list_twice_is_listed_once(fake_llm, no_rule):
    fake_llm.answer = answer(required_skills=[{"name": "SQL", "quote": "SQL"}, {"name": "sql", "quote": "SQL"}])
    assert len(extract_jd_profile(JD)["profile"]["required_skills"]) == 1


# ---------- endpoint ----------
client = TestClient(app)
KEY = {"X-Service-Key": "test-key"}


def test_endpoint_requires_key_and_valid_body():
    assert client.post("/internal/extract/jd-profile", json={"text": "x" * 50}).status_code == 401
    assert client.post("/internal/extract/jd-profile", headers=KEY, json={"text": "hi"}).status_code == 422


def test_endpoint_success(fake_llm):
    fake_llm.answer = answer(responsibilities=[{"text": "Build REST APIs", "quote": "Build and maintain REST APIs in Node.js"}])
    r = client.post("/internal/extract/jd-profile", headers=KEY, json={"text": JD})
    assert r.status_code == 200 and r.json()["counts"]["responsibilities"] == 1
    assert r.json()["prompt_version"] == "jd-profile-v1"


@pytest.mark.parametrize("kind, status", [("rate_limited", 429), ("not_configured", 503), ("auth", 502)])
def test_endpoint_maps_llm_errors(monkeypatch, kind, status):
    def boom(*a, **k):
        raise LlmError(kind, "problem text")
    monkeypatch.setattr(jd_mod, "generate_json", boom)
    r = client.post("/internal/extract/jd-profile", headers=KEY, json={"text": JD})
    assert r.status_code == status and r.json()["detail"] == "problem text"


# ---------- the completeness check (a safety net for the AI's recall) ----------
ZEN = """Backend Engineer (Python)
About us
We use Kafka and Kubernetes internally. Write to careers@zenpay.in.
What you will do
- Design REST APIs and microservices in Python
Requirements
- Strong Python, SQL and PostgreSQL skills; experience with Docker
- Excellent communication and an ownership mindset
Nice to have
- Experience with AWS, Kafka or Redis
Prior knowledge of GraphQL is not required.
"""


def empty_profile():
    return {c: [] for c in JD_CATEGORIES}


def names(profile, key):
    return sorted(i["name"] for i in profile[key])


def test_completeness_adds_what_the_ai_missed():
    from app.extraction.jd_profile import completeness_check
    p = empty_profile()
    added = completeness_check(ZEN, p)
    assert names(p, "preferred_skills") == ["AWS", "Kafka", "Redis"]
    assert {"Python", "SQL", "PostgreSQL", "Docker"} <= set(names(p, "required_skills"))
    assert {"Communication", "Ownership"} <= set(names(p, "soft_skills"))
    assert added == sum(len(v) for v in p.values())
    item = p["preferred_skills"][0]
    assert item["origin"] == "rule" and item["status"] == "supported" and item["quote"] in ZEN   # a real line of the text


def test_completeness_never_adds_a_skill_the_text_says_is_not_required():
    from app.extraction.jd_profile import completeness_check
    p = empty_profile()
    completeness_check(ZEN, p)
    assert "GraphQL" not in names(p, "required_skills") + names(p, "preferred_skills")


def test_completeness_only_reads_the_requirement_sections():
    from app.extraction.jd_profile import completeness_check
    p = empty_profile()
    completeness_check(ZEN, p)
    # Kubernetes is only named under "About us", so it must not become a requirement of any kind
    assert "Kubernetes" not in names(p, "required_skills") + names(p, "preferred_skills")
    # Kafka is named under "About us" AND "Nice to have": only the second counts, and only as preferred
    assert "Kafka" not in names(p, "required_skills")


def test_completeness_does_not_repeat_what_the_ai_already_found():
    from app.extraction.jd_profile import completeness_check
    p = empty_profile()
    p["required_skills"].append({"name": "node js", "quote": "x", "status": "supported"})
    p["preferred_skills"].append({"name": "Amazon Web Services", "quote": "AWS", "status": "supported"})   # same skill as AWS
    completeness_check(ZEN, p)
    assert sum(1 for i in p["preferred_skills"] if i["name"] in ("Amazon Web Services", "AWS")) == 1
    assert names(p, "preferred_skills") == ["Amazon Web Services", "Kafka", "Redis"]   # only the genuinely missing ones added


def test_extract_reports_how_many_were_added_by_rule(fake_llm):
    fake_llm.answer = answer(required_skills=[{"name": "Python", "quote": "Strong Python, SQL and PostgreSQL skills"}])
    out = extract_jd_profile(ZEN)
    assert out["added_by_rule"] > 0
    assert {s["name"] for s in out["profile"]["preferred_skills"]} == {"AWS", "Kafka", "Redis"}
    assert out["needs_review"] == 0     # rule-added items quote real lines, so they are verified


def test_completeness_does_not_turn_a_duty_into_a_required_soft_skill():
    from app.extraction.jd_profile import completeness_check
    p = empty_profile()
    completeness_check("What you will do\n- Review code and mentor junior engineers\n- Lead team meetings\nRequirements\n- Strong communication skills\n", p)
    assert names(p, "soft_skills") == ["Communication"]        # "mentor" and "lead" are duties here, not required skills
