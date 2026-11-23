"""Step 3 of extraction: split the cleaned text into sections (Education, Skills...).

Different resumes call the same section by different names ("Work History",
"Professional Experience"...). We keep a table of known heading names for each
section, and we only treat a line as a heading when it is short and matches.
"""
import re

# canonical section name -> the heading texts people use for it (lowercase)
RESUME_HEADINGS = {
    "summary": ["summary", "professional summary", "profile", "objective", "career objective", "about me", "about"],
    "education": ["education", "academic background", "academics", "academic qualifications",
                  "educational qualifications", "academic details", "qualifications"],
    "experience": ["experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "internships", "internship", "internship experience"],
    "projects": ["projects", "academic projects", "personal projects", "key projects", "project work", "selected projects"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "technologies",
               "tech stack", "tools and technologies", "skills and tools", "soft skills"],
    "certifications": ["certifications", "certificates", "licenses", "licenses and certifications",
                       "courses", "training", "certifications and courses"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments",
                     "awards and achievements", "scholarships", "awards and honors"],
    "leadership": ["leadership", "positions of responsibility", "extracurricular", "extracurricular activities",
                   "extra curricular activities", "co-curricular activities", "volunteering", "volunteer experience"],
    "funding": ["grants", "funding", "grants and funding", "research grants", "funded projects"],
    "publications": ["publications", "research papers", "patents", "research"],
}

JD_HEADINGS = {
    "about": ["about us", "about the company", "company overview", "overview", "who we are", "about the role", "about"],
    "responsibilities": ["responsibilities", "key responsibilities", "roles and responsibilities", "what you will do",
                         "what you'll do", "duties", "job duties", "the role", "job description", "job summary"],
    "requirements": ["requirements", "required skills", "required qualifications", "qualifications",
                     "minimum qualifications", "what you need", "must have", "must-have skills",
                     "skills required", "skills", "basic qualifications", "who you are"],
    "preferred": ["preferred qualifications", "preferred skills", "nice to have", "good to have", "bonus",
                  "bonus points", "preferred", "plus"],
    "experience": ["experience", "experience required"],
    "education": ["education", "educational requirements"],
    "benefits": ["benefits", "perks", "what we offer", "compensation", "salary"],
}

TABLES = {"resume": RESUME_HEADINGS, "jd": JD_HEADINGS}

# Sections most resumes have. Reported as "not found" (never as "lacking") if missing.
EXPECTED = {
    "resume": ["education", "experience", "projects", "skills"],
    "jd": ["responsibilities", "requirements"],
}

MAX_HEADING_WORDS = 6
MAX_HEADING_CHARS = 50
_DECORATION = re.compile(r"^[\W_\d]+|[\W_]+$")  # leading/trailing symbols, numbers like "1."


def _normalise(line: str) -> str:
    """'  EDUCATION:  ' -> 'education'. '**Skills &  Tools**' -> 'skills and tools'."""
    text = line.strip().replace("&", " and ")
    text = _DECORATION.sub("", text)
    return re.sub(r"\s+", " ", text).lower()


def _lookup(table: dict) -> dict:
    return {alias: name for name, aliases in table.items() for alias in aliases}


def _heading_name(line: str, alias_to_name: dict):
    """Return the canonical section name if this line is a heading, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_HEADING_CHARS or stripped.startswith("- "):
        return None
    if stripped.endswith("."):  # headings do not end like sentences
        return None
    norm = _normalise(stripped)
    if not norm or len(norm.split()) > MAX_HEADING_WORDS:
        return None
    if norm in alias_to_name:
        return alias_to_name[norm]
    # Combined headings like "Education and Certifications": every part must be known
    parts = [p.strip() for p in re.split(r"\band\b|/|,", norm) if p.strip()]
    if len(parts) > 1 and all(p in alias_to_name for p in parts):
        return alias_to_name[parts[0]]
    return None


def find_sections(text: str, doc_type: str) -> dict:
    table = TABLES[doc_type]
    alias_to_name = _lookup(table)

    sections: list[dict] = []
    current = {"name": "preamble", "heading": "", "lines": []}
    for line in text.split("\n"):
        name = _heading_name(line, alias_to_name)
        if name:
            sections.append(current)
            current = {"name": name, "heading": line.strip(), "lines": []}
        else:
            current["lines"].append(line)
    sections.append(current)

    result = []
    for sec in sections:
        body = "\n".join(sec["lines"]).strip()
        if sec["name"] == "preamble" and not body:
            continue
        if sec["name"] != "preamble" and not body:
            continue  # a heading with nothing under it carries no information
        result.append({"name": sec["name"], "heading": sec["heading"], "text": body})

    found = {s["name"] for s in result}
    return {
        "sections": result,
        "expected_not_found": [n for n in EXPECTED[doc_type] if n not in found],
        "headings_recognised": any(s["name"] != "preamble" for s in result),
    }
