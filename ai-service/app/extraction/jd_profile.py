"""Job description version of profile.py: required skills, preferred skills, responsibilities...

Same safety rules as for resumes: hide personal details first, every claim carries a
quote, code checks each quote against the text. The LLM never scores anything.
"""
import re

from pydantic import BaseModel

from app.extraction.profile import MAX_PROFILE_CHARS, _MAYBE, _STR, _list, _norm, _obj, _verify
from app.extraction.redact import redact
from app.extraction.sections import find_sections
from app.matching.catalog import get_catalog, normalise
from app.llm.client import generate_json
from app.llm.config import load_settings

PROMPT_VERSION = "jd-profile-v1"

_BOOL = {"type": "boolean"}

JD_SCHEMA = _obj({
    "job_title": _MAYBE,
    "required_skills": _list(_obj({"name": _STR, "quote": _STR})),
    "preferred_skills": _list(_obj({"name": _STR, "quote": _STR})),
    "soft_skills": _list(_obj({"name": _STR, "quote": _STR})),
    "competencies": _list(_obj({"name": _STR, "quote": _STR})),
    "education_requirements": _list(_obj({"text": _STR, "quote": _STR})),
    "experience_requirements": _list(_obj({"text": _STR, "years": _MAYBE, "quote": _STR})),
    "responsibilities": _list(_obj({"text": _STR, "quote": _STR})),
    "certifications": _list(_obj({"name": _STR, "required": _BOOL, "quote": _STR})),
})


class _Named(BaseModel):
    name: str
    quote: str


class _Text(BaseModel):
    text: str
    quote: str


class _Experience(BaseModel):
    text: str
    years: str | None
    quote: str


class _Cert(BaseModel):
    name: str
    required: bool
    quote: str


class RawJdProfile(BaseModel):
    job_title: str | None
    required_skills: list[_Named]
    preferred_skills: list[_Named]
    soft_skills: list[_Named]
    competencies: list[_Named]
    education_requirements: list[_Text]
    experience_requirements: list[_Experience]
    responsibilities: list[_Text]
    certifications: list[_Cert]


JD_CATEGORIES = [c for c in RawJdProfile.model_fields if c != "job_title"]
JD_DEDUPE = ("required_skills", "preferred_skills", "soft_skills", "competencies")

SYSTEM_PROMPT = """You extract requirements from ONE job description into JSON. Follow these rules strictly.
1. Use ONLY what is written in the job description. Never guess, infer, or add anything.
2. Every item needs a "quote": text copied EXACTLY, character for character, from the job description (less than 200 characters).
3. If a value is not written, use null (or an empty list). Never invent values.
4. Text like [EMAIL_1], [PHONE_1], [LINK_1] is a privacy placeholder. Never guess what it hides.
5. required_skills and preferred_skills: technical skills, tools, languages, frameworks only. A skill is "preferred" ONLY when the text says preferred, nice to have, plus, bonus or good to have. Otherwise it is required. List each skill once, in only one of the two lists.
6. soft_skills: only if named (for example communication, teamwork, leadership).
7. competencies: role-specific abilities that are neither a tool nor a soft skill (for example "stakeholder management", "system design"). Use the words of the text for the name; do not invent a new label.
7b. If the text says something is NOT required, NOT needed or NOT expected (for example "knowledge of X is not required"), do NOT list it anywhere.
7c. Go through the whole text, including every "nice to have" and "plus" line and every sentence about communication or teamwork. Do not stop early.
8. education_requirements: degrees or fields asked for. experience_requirements: years or kind of experience asked for; put the years exactly as written in "years".
9. responsibilities: what the person will do, one short item each.
10. certifications: "required" is true only if the text says it is required or mandatory.
11. job_title: the title written in the text, or null.
12. If a category has nothing, return an empty list."""


# A line that says something is NOT needed must never become a requirement
_NEGATION = re.compile(r"\bnot\s+(?:required|needed|necessary|expected|mandatory)\b|\bno\s+(?:need|experience)\b|\bwithout\b|\boptional\b", re.I)


def completeness_check(text: str, profile: dict, catalog=None) -> int:
    """Safety net for the AI's recall. Read the job description's own Requirements / Nice-to-have /
    Responsibilities sections and add known skills the AI did not list. Each added item quotes the real line
    and is marked origin="rule". Returns how many were added. Works only on text we can verify."""
    catalog = catalog or get_catalog()
    lists = ("required_skills", "preferred_skills", "soft_skills")
    key = lambda name: catalog.lookup(name) or normalise(name)  # noqa: E731
    # Only VERIFIED items count as "already listed". An unverified item is ignored by the matcher, so if the
    # AI listed a skill but its quote did not match, the skill would otherwise disappear from the comparison.
    listed = {key(i["name"]) for c in lists for i in profile[c] if i.get("status") == "supported"}
    added = 0
    for section in find_sections(text, "jd")["sections"]:
        if section["name"] not in ("requirements", "preferred", "responsibilities"):
            continue
        technical_target = "preferred_skills" if section["name"] == "preferred" else "required_skills"
        for line in section["text"].split("\n"):
            line = line.strip()
            if not line or _NEGATION.search(line):
                continue
            # Tools named in a job's duties are fair requirements, but a duty such as "mentor juniors" is not
            # a skill the candidate must already have, so soft skills come only from requirement sections.
            soft_ids = set() if section["name"] == "responsibilities" else catalog.find_soft_in_text(line)
            for target, ids in ((technical_target, catalog.find_in_text(line)), ("soft_skills", soft_ids)):
                for skill_id in sorted(ids - listed):
                    listed.add(skill_id)
                    for c in lists:   # replace an unverified AI item for the same skill with this verified one
                        profile[c][:] = [i for i in profile[c] if i.get("status") == "supported" or key(i["name"]) != skill_id]
                    profile[target].append({
                        "name": catalog.name_of(skill_id), "quote": line[:200], "status": "supported", "origin": "rule",
                        "note": f"Added by a completeness check: named in the text under '{section['heading'] or section['name']}'.",
                    })
                    added += 1
    return added


def extract_jd_profile(text: str) -> dict:
    warnings: list[str] = []
    if len(text) > MAX_PROFILE_CHARS:
        text = text[:MAX_PROFILE_CHARS]
        warnings.append(f"The job description is long, so only the first {MAX_PROFILE_CHARS:,} characters were analysed.")

    hidden = redact(text, hide_name=False)       # emails, phones, links hidden; the job title is NOT a name
    raw = generate_json(
        system=SYSTEM_PROMPT,
        user=f"JOB DESCRIPTION:\n{hidden.text}",
        schema=JD_SCHEMA,
        schema_name="jd_profile",
        validate_with=RawJdProfile,
        max_output_tokens=4096,
    )
    profile, verify_warnings = _verify(raw, hidden.text, JD_CATEGORIES, JD_DEDUPE)
    profile = hidden.restore(profile)
    warnings += verify_warnings

    # The AI sometimes skips a whole list (seen on real job descriptions), so code re-reads the text too
    added = completeness_check(text, profile)

    title = raw.get("job_title")
    job_title = title if title and _norm(title) in _norm(hidden.text) else None  # only a title really written in the text

    settings = load_settings()
    return {
        "profile": {"job_title": job_title, **profile},
        "counts": {c: len(profile[c]) for c in JD_CATEGORIES},
        "added_by_rule": added,
        "needs_review": sum(1 for c in JD_CATEGORIES for i in profile[c] if i["status"] != "supported"),
        "redactions": hidden.counts,
        "warnings": warnings,
        "provider": settings.provider,
        "model": settings.model,
        "prompt_version": PROMPT_VERSION,
    }
