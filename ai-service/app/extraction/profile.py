"""Part B of extraction: turn resume text into a structured profile using the LLM.

Safety rules built into this file:
  * Personal details are hidden before the text leaves this server (redact.py).
  * The LLM only produces CLAIMS. Every claim must carry a quote copied from the resume.
  * Code then checks each quote against the resume. Found -> "supported".
    Not found -> "needs_review". Nothing the LLM says is treated as verified fact.
  * No scores here. Scoring is done later by the scoring engine, never by the LLM.
"""
import re
from typing import Literal

from pydantic import BaseModel

from app.extraction.redact import Redaction, redact
from app.llm.client import generate_json
from app.llm.config import load_settings

PROMPT_VERSION = "resume-profile-v1"
MAX_PROFILE_CHARS = 12000   # about 3,000 tokens: keeps us inside Groq's tokens-per-minute limit
MAX_ITEMS_PER_CATEGORY = 40


# ---------------------------------------------------------------------------
# 1. The shape of the answer. JSON Schema (sent to the model) + Pydantic (checks the reply).
#    Groq's strict mode needs: every property listed in "required", extra properties
#    forbidden, and "maybe missing" values written as ["string", "null"].
# ---------------------------------------------------------------------------
def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_STR = {"type": "string"}
_MAYBE = {"type": ["string", "null"]}
_STRS = {"type": "array", "items": {"type": "string"}}


def _list(item: dict) -> dict:
    return {"type": "array", "items": item}


PROFILE_SCHEMA = _obj({
    "technical_skills": _list(_obj({"name": _STR, "quote": _STR})),
    "soft_skills": _list(_obj({"name": _STR, "quote": _STR})),
    "education": _list(_obj({"degree": _MAYBE, "institution": _MAYBE, "field_of_study": _MAYBE, "year": _MAYBE, "quote": _STR})),
    "experience": _list(_obj({
        "title": _MAYBE, "organization": _MAYBE,
        "kind": {"type": "string", "enum": ["job", "internship", "other"]},
        "duration": _MAYBE, "responsibilities": _STRS, "quote": _STR})),
    "projects": _list(_obj({
        "title": _STR, "description": _MAYBE, "technologies": _STRS, "role": _MAYBE,
        "outcome": _MAYBE, "links": _STRS, "quote": _STR})),
    "certifications": _list(_obj({"name": _STR, "issuer": _MAYBE, "date": _MAYBE, "quote": _STR})),
    "achievements": _list(_obj({
        "title": _STR,
        "kind": {"type": "string", "enum": ["award", "competition", "scholarship", "leadership", "other"]},
        "description": _MAYBE, "quote": _STR})),
    "funding": _list(_obj({
        "description": _STR, "source": _MAYBE, "amount_text": _MAYBE, "purpose": _MAYBE,
        "candidate_role": _MAYBE, "outcome": _MAYBE, "quote": _STR})),
})


class _Skill(BaseModel):
    name: str
    quote: str


class _Education(BaseModel):
    degree: str | None
    institution: str | None
    field_of_study: str | None
    year: str | None
    quote: str


class _Experience(BaseModel):
    title: str | None
    organization: str | None
    kind: Literal["job", "internship", "other"]
    duration: str | None
    responsibilities: list[str]
    quote: str


class _Project(BaseModel):
    title: str
    description: str | None
    technologies: list[str]
    role: str | None
    outcome: str | None
    links: list[str]
    quote: str


class _Certification(BaseModel):
    name: str
    issuer: str | None
    date: str | None
    quote: str


class _Achievement(BaseModel):
    title: str
    kind: Literal["award", "competition", "scholarship", "leadership", "other"]
    description: str | None
    quote: str


class _Funding(BaseModel):
    description: str
    source: str | None
    amount_text: str | None
    purpose: str | None
    candidate_role: str | None
    outcome: str | None
    quote: str


class RawProfile(BaseModel):
    technical_skills: list[_Skill]
    soft_skills: list[_Skill]
    education: list[_Education]
    experience: list[_Experience]
    projects: list[_Project]
    certifications: list[_Certification]
    achievements: list[_Achievement]
    funding: list[_Funding]


CATEGORIES = list(RawProfile.model_fields)

# Which fields of each item should visibly appear in the resume text (a second, stricter check)
MUST_APPEAR = {
    "technical_skills": ["name"], "soft_skills": ["name"],
    "education": ["institution"], "experience": ["organization"],
    "projects": ["title"], "certifications": ["name"], "funding": ["source"],
    # job description categories (see jd_profile.py)
    "required_skills": ["name"], "preferred_skills": ["name"], "competencies": ["name"],
}

SYSTEM_PROMPT = """You extract facts from ONE resume into JSON. Follow these rules strictly.
1. Use ONLY what is written in the resume. Never guess, infer, or add anything.
2. Every item needs a "quote": text copied EXACTLY, character for character, from the resume (one line or less than 200 characters).
3. If a value is not written in the resume, use null (or an empty list). Never invent values.
4. Text like [EMAIL_1], [PHONE_1], [LINK_1], [NAME] is a privacy placeholder. Copy it as written if needed. Never guess what it hides.
5. technical_skills: tools, languages, frameworks, technologies. soft_skills: only if the resume names them (for example communication, leadership, teamwork). List each skill once.
6. experience: jobs and internships (kind "job" or "internship"). Do not put college projects here.
7. projects: put technologies in "technologies". Put a link in "links" only if one appears for that project.
8. achievements: awards, competitions, scholarships, leadership roles. Do NOT repeat the same thing in funding.
9. funding: ONLY an explicit grant, fellowship, seed money or funded project. Copy the amount exactly as written into "amount_text" (never convert it). A prize or a scholarship is not funding unless the resume calls it funding or a grant.
10. Do not extract age, gender, religion, marital status, nationality or caste, even if present.
11. If a category has nothing, return an empty list."""


# ---------------------------------------------------------------------------
# 2. Checking the claims against the resume
# ---------------------------------------------------------------------------
def _norm(text: str) -> str:
    """Lowercase, remove bullet marks, collapse spaces: so line breaks/bullets do not break matching."""
    text = re.sub(r"(?m)^\s*[-•*]\s+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _check_item(category: str, item: dict, source_norm: str) -> tuple[str, str]:
    """Return (status, note). 'supported' only if the quote AND key fields are really in the resume."""
    quote = _norm(item.get("quote", ""))
    if len(quote) < 2 or quote not in source_norm:
        return "needs_review", "The quoted text was not found in the resume."
    for field_name in MUST_APPEAR.get(category, []):
        value = item.get(field_name)
        if value and _norm(value) not in source_norm:
            return "needs_review", f"'{value}' was not found in the resume."
    return "supported", ""


def _verify(raw: dict, source_text: str, categories: list[str] | None = None,
            dedupe: tuple = ("technical_skills", "soft_skills")) -> tuple[dict, list[str]]:
    """Check every item against the text. Shared by resumes and job descriptions."""
    source_norm = _norm(source_text)
    profile: dict[str, list] = {}
    warnings: list[str] = []
    for category in categories or CATEGORIES:
        seen: set[str] = set()
        kept = []
        for item in raw[category][:MAX_ITEMS_PER_CATEGORY]:
            if category in dedupe:
                key = item["name"].strip().lower()
                if key in seen:
                    continue  # same skill listed twice
                seen.add(key)
            status, note = _check_item(category, item, source_norm)
            kept.append({**item, "status": status, "note": note})
        if len(raw[category]) > MAX_ITEMS_PER_CATEGORY:
            warnings.append(f"Only the first {MAX_ITEMS_PER_CATEGORY} {category.replace('_', ' ')} were kept.")
        profile[category] = kept
    return profile, warnings


# ---------------------------------------------------------------------------
# 3. The one function the API calls
# ---------------------------------------------------------------------------
def extract_resume_profile(text: str) -> dict:
    warnings: list[str] = []
    if len(text) > MAX_PROFILE_CHARS:
        text = text[:MAX_PROFILE_CHARS]
        warnings.append(f"The resume is long, so only the first {MAX_PROFILE_CHARS:,} characters were analysed.")

    hidden: Redaction = redact(text)          # personal details never leave this server
    raw = generate_json(
        system=SYSTEM_PROMPT,
        user=f"RESUME:\n{hidden.text}",
        schema=PROFILE_SCHEMA,
        schema_name="resume_profile",
        validate_with=RawProfile,
        max_output_tokens=4096,
        # "low" on purpose: on real resumes, medium/high effort made the model over-think and run out of
        # tokens before writing the JSON (measured: fails even with 7,000 tokens; low needs about 1,000).
        reasoning_effort="low",
    )
    profile, verify_warnings = _verify(raw, hidden.text)   # verify against the text the model actually saw
    profile = hidden.restore(profile)                      # then put real values back, for the student only
    warnings += verify_warnings

    settings = load_settings()
    return {
        "profile": profile,
        "counts": {c: len(profile[c]) for c in CATEGORIES},
        "needs_review": sum(1 for c in CATEGORIES for i in profile[c] if i["status"] != "supported"),
        "redactions": hidden.counts,
        "warnings": warnings,
        "provider": settings.provider,
        "model": settings.model,
        "prompt_version": PROMPT_VERSION,
    }
