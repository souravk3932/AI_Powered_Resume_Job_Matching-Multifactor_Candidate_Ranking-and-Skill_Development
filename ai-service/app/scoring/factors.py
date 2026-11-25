"""The ten factor scorers. Each one turns VERIFIED evidence into a score from 0 to 100 using fixed rules.

Nothing here calls an LLM, and nothing here uses a person's name, contact details, age, gender,
religion, college name or grades. The LLM only helped read the documents; the numbers come from here.

Every scorer returns the same shape (see _result):
  status   evaluated | not_applicable | not_provided | not_available
  score    0 to 100, or None when status is not "evaluated"
  steps    the arithmetic in words, so the student can follow it
  items    the individual pieces of evidence and the points each one earned
  used     keys of the evidence items this factor spent (the engine checks nothing is spent twice)
"""
import re
from dataclasses import dataclass, field
from datetime import date

from app.matching.catalog import get_catalog, normalise
from app.scoring.durations import parse_months, required_years

CAT = get_catalog()


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
@dataclass
class Context:
    resume: dict            # stored resume profile data (every item has a "status")
    jd: dict                # stored job description profile data
    match: dict             # the Phase 6 skill match result
    role_keywords: list[str] = field(default_factory=list)
    today: date = field(default_factory=date.today)


def supported(items) -> list[dict]:
    """Only claims whose quote was verified in the document count as evidence."""
    return [i for i in (items or []) if i.get("status") == "supported"]


def _result(fid, status, score=None, steps=None, items=None, notes=None, used=None) -> dict:
    return {"id": fid, "status": status, "score": None if score is None else round(float(score), 1),
            "steps": steps or [], "items": items or [], "notes": notes or [], "used": used or []}


def _text(*parts) -> str:
    return " ".join(str(p) for p in parts if p)


def _diminishing(points: list[float]) -> float:
    """Combine several pieces of evidence with diminishing returns: each extra one adds less.
    [60, 40] -> 100 x (1 - 0.4 x 0.6) = 76. Never exceeds 100, and one strong item is not drowned by weak ones."""
    remaining = 1.0
    for p in points:
        remaining *= 1 - max(0.0, min(100.0, p)) / 100
    return 100 * (1 - remaining)


def _skill_ids(text: str) -> set[str]:
    """Known technical skills named in a text, plus everything they imply (Django -> Python)."""
    found = set(CAT.find_in_text(text))
    for s in list(found):
        found |= CAT.implied(s)
    return found


def _jd_skill_weights(jd: dict) -> dict[str, float]:
    """Skill id -> weight, from the job's verified requirements. Required counts 1.0, preferred 0.5."""
    weights: dict[str, float] = {}
    for field_name, w in (("required_skills", 1.0), ("preferred_skills", 0.5)):
        for item in supported(jd.get(field_name)):
            key = CAT.lookup(item["name"]) or f"custom:{normalise(item['name'])}"
            weights[key] = max(weights.get(key, 0.0), w)
    return weights


def _covered(skill_ids: set[str], wanted: dict[str, float]) -> tuple[float, list[str]]:
    hit = [k for k in wanted if k in skill_ids]
    return sum(wanted[k] for k in hit), [CAT.name_of(k) for k in hit]


def _relevant(text: str, ctx: Context) -> bool:
    """Does this text connect to the job? Either a job skill is named, or a word typical for the role is."""
    wanted = _jd_skill_weights(ctx.jd)
    if _skill_ids(text) & set(wanted):
        return True
    low = text.lower()
    return any(k in low for k in ctx.role_keywords)


# ---------------------------------------------------------------------------
# 1. technical skills  (from the Phase 6 match)
# ---------------------------------------------------------------------------
SUPPORT_MULTIPLIER = {"demonstrated": 1.0, "certified": 0.95, "listed": 0.8}
PARTIAL_POINTS = {"broader": 0.5, "family": 0.5, "semantic": 0.3}
IMPORTANCE_WEIGHT = {"required": 1.0, "preferred": 0.4}


def technical_skills(ctx: Context) -> dict:
    reqs = [s for s in ctx.match.get("skills", []) if s["importance"] in IMPORTANCE_WEIGHT]
    if not reqs:
        return _result("technical_skills", "not_applicable", notes=["The job description named no verified technical skills."])
    if not (supported(ctx.resume.get("technical_skills")) or supported(ctx.resume.get("projects"))):
        return _result("technical_skills", "not_provided", notes=["No technical skills could be read from the resume."])

    items, total, earned = [], 0.0, 0.0
    for s in reqs:
        weight = IMPORTANCE_WEIGHT[s["importance"]]
        if s["status"] == "matched":
            points = SUPPORT_MULTIPLIER.get(s["support"], 0.8)
        elif s["status"] == "partial":
            points = PARTIAL_POINTS.get(s["method"], 0.3)
        else:
            points = 0.0
        total += weight
        earned += weight * points
        items.append({"label": s["requirement"], "points": round(100 * points), "detail": f"{s['importance']}, {s['status']}"
                      + (f" ({s['method']}, {s['support']})" if s["status"] != "missing" else "")})
    score = 100 * earned / total
    steps = [
        "Each requirement earns: matched 100% (shown in your work), 95% (certificate) or 80% (only listed); partly matched 50% "
        "(general or similar skill) or 30% (meaning-based suggestion); not found 0%.",
        "Required skills count 1.0 and preferred skills 0.4.",
        f"Score = 100 x {earned:.2f} earned / {total:.2f} possible = {score:.1f}",
    ]
    return _result("technical_skills", "evaluated", score, steps, items)


# ---------------------------------------------------------------------------
# 2. soft skills
# ---------------------------------------------------------------------------
def soft_skills(ctx: Context) -> dict:
    reqs = [s for s in ctx.match.get("skills", []) if s["importance"] == "soft"]
    if not reqs:
        return _result("soft_skills", "not_applicable", notes=["The job description named no verified soft skills."])
    has_any = supported(ctx.resume.get("soft_skills")) or any(a.get("kind") == "leadership" for a in supported(ctx.resume.get("achievements")))
    if not has_any:
        return _result("soft_skills", "not_provided", notes=["The resume lists no soft skills. Many resumes leave them out, so this is not counted against you."])
    items, earned = [], 0.0
    for s in reqs:
        points = SUPPORT_MULTIPLIER.get(s["support"], 0.8) if s["status"] == "matched" else 0.0
        earned += points
        items.append({"label": s["requirement"], "points": round(100 * points), "detail": s["status"] + (f" ({s['support']})" if s["support"] else "")})
    score = 100 * earned / len(reqs)
    return _result("soft_skills", "evaluated", score,
                   ["Each soft skill the job names earns 100% if shown in your work, 80% if only listed, 0% if not found.",
                    f"Score = 100 x {earned:.2f} / {len(reqs)} = {score:.1f}"], items)


# ---------------------------------------------------------------------------
# 3. education  (level and field only: never the college's name or the grades)
# ---------------------------------------------------------------------------
_LEVELS = [   # written in any capitalisation
    (5, r"ph\.?\s?d|doctorate|d\.?phil"),
    (4, r"m\.?\s?tech|m\.?sc|\bmca\b|\bmba\b|master|post\s?graduate"),
    (3, r"b\.?\s?tech|b\.?sc|\bbca\b|\bbba\b|b\.?com|bachelor|under\s?graduate"),
    (2, r"diploma|polytechnic"),
    (1, r"class xii|12th|higher secondary|intermediate|\bxii\b"),
]
# Two-letter abbreviations are also ordinary words ("to be", "me"), so they count only when written in CAPITALS
_LEVELS_CAPS = [(4, r"\bM\.?E\b|\bM\.?S\b|\bPG\b"), (3, r"\bB\.?E\b|\bB\.?S\b")]
LEVEL_NAMES = {5: "doctorate", 4: "master's", 3: "bachelor's", 2: "diploma", 1: "school (class XII)", 0: "unknown"}
_COMPUTING = re.compile(r"computer|software|information (?:technology|science|systems)|\bit\b|informatics|data science|artificial intelligence|\bcse\b|\bai\b|cyber|\bmca\b|\bbca\b", re.I)
_RELATED = re.compile(r"electronic|electrical|\bece\b|\beee\b|instrumentation|mechanical|civil|engineering|mathematic|statistic|physics", re.I)


def degree_level(text: str) -> int:
    text = text or ""
    low = text.lower()
    found = [level for level, pattern in _LEVELS if re.search(pattern, low)]
    found += [level for level, pattern in _LEVELS_CAPS if re.search(pattern, text)]
    return max(found, default=0)


def education(ctx: Context) -> dict:
    asked = supported(ctx.jd.get("education_requirements"))
    if not asked:
        return _result("education", "not_applicable", notes=["The job description names no education requirement."])
    have = supported(ctx.resume.get("education"))
    if not have:
        return _result("education", "not_provided", notes=["No education could be read from the resume."])

    need_text = " ".join(i["text"] for i in asked)
    need_level = max(degree_level(i["text"]) for i in asked)
    need_computing = bool(_COMPUTING.search(need_text))
    related_ok = "related" in need_text.lower() or "equivalent" in need_text.lower()

    best_level, best_field, shown = 0, 0.0, None
    in_progress = False
    for e in have:
        level = degree_level(_text(e.get("degree"), e.get("field_of_study")))
        field_text = _text(e.get("degree"), e.get("field_of_study"))     # NOT the institution: its name says nothing about the degree
        if _COMPUTING.search(field_text):
            f = 1.0
        elif _RELATED.search(field_text):
            f = 0.6 if related_ok else 0.0
        else:
            f = 0.0
        if level > best_level or (level == best_level and f > best_field):
            best_level, best_field, shown = level, f, e
            years = re.findall(r"(?:19|20)\d{2}", e.get("year") or "")
            in_progress = bool(years) and int(years[-1]) >= ctx.today.year

    if need_level == 0:
        level_pts = 100
        level_note = "The job does not name a degree level."
    elif best_level >= need_level:
        level_pts, level_note = 100, f"{LEVEL_NAMES[best_level]} meets the required {LEVEL_NAMES[need_level]}."
    elif best_level == need_level - 1 and best_level > 0:
        level_pts, level_note = 50, f"{LEVEL_NAMES[best_level]} is one level below the required {LEVEL_NAMES[need_level]}."
    else:
        level_pts, level_note = 0, f"{LEVEL_NAMES[best_level]} is below the required {LEVEL_NAMES[need_level]}."

    if need_computing:
        field_pts = round(100 * best_field)
        field_note = {100: "The field matches (computing).", 60: "The field is related (engineering or maths), and the job allows related fields."}.get(field_pts, "The field does not match.")
        score = 0.6 * level_pts + 0.4 * field_pts
        steps = [f"Level is worth 60% of this factor and field 40%. {level_note} {field_note}",
                 f"Score = 0.6 x {level_pts} + 0.4 x {field_pts} = {score:.1f}"]
    else:
        score, field_pts = level_pts, None
        steps = [f"The job names no particular field, so only the level counts. {level_note}", f"Score = {score:.1f}"]
    notes = ["The college's name and any grades are not used."]
    if in_progress:
        notes.append("This degree seems to be in progress; it is counted as meeting its level. Please check the graduation date.")
    items = [{"label": _text(shown.get("degree"), shown.get("field_of_study")) or "Education", "points": round(score),
              "detail": f"level {LEVEL_NAMES[best_level]}" + (f", field {field_pts}%" if field_pts is not None else "")}]
    return _result("education", "evaluated", score, steps, items, notes, used=["education:best"])


# ---------------------------------------------------------------------------
# 4. relevant experience
# ---------------------------------------------------------------------------
KIND_WEIGHT = {"job": 1.0, "internship": 0.5, "other": 0.5}
IRRELEVANT_WEIGHT = 0.4
UNKNOWN_DURATION_MONTHS = 3.0
GENERAL_EXPERIENCE_MONTHS = 6.0   # asked for "experience" with no number of years


def experience(ctx: Context) -> dict:
    asked = supported(ctx.jd.get("experience_requirements"))
    if not asked:
        return _result("experience", "not_applicable", notes=["The job description names no experience requirement."])
    have = supported(ctx.resume.get("experience"))
    if not have:
        return _result("experience", "not_provided", notes=["No jobs or internships could be read from the resume. If you have none yet, that is normal for a student, and it is not scored as zero."])

    def asked_years(i):  # "3+ years of ..." in the text, or just "3+" in the separate years field
        found = required_years(i["text"]) or required_years(f"{i.get('years') or ''} years")
        return found

    years = [y for y in (asked_years(i) for i in asked) if y]
    need_months = max(years) * 12 if years else GENERAL_EXPERIENCE_MONTHS
    items, effective, unknown = [], 0.0, 0
    for idx, e in enumerate(have):
        text = _text(e.get("title"), *e.get("responsibilities", []), e["quote"])
        months = parse_months(_text(e.get("duration"), e["quote"]), ctx.today)
        if months is None:
            months, unknown = UNKNOWN_DURATION_MONTHS, unknown + 1
        kind_w = KIND_WEIGHT.get(e.get("kind", "other"), 0.5)
        rel_w = 1.0 if _relevant(text, ctx) else IRRELEVANT_WEIGHT
        counted = months * kind_w * rel_w
        effective += counted
        items.append({"label": _text(e.get("title"), e.get("organization") and f"at {e['organization']}") or "Experience",
                      "points": round(counted, 1),
                      "detail": f"{months:g} months x {kind_w} ({e.get('kind', 'other')}) x {rel_w} ({'relevant' if rel_w == 1 else 'not clearly relevant'}) = {counted:.1f} months"})
    score = min(100.0, 100 * effective / need_months)
    steps = ["Months are counted per job: a job counts fully, an internship counts half; work that does not clearly touch the job's skills counts 40%.",
             f"Counted: {effective:.1f} months. Asked for: {need_months:g} months" + ("" if years else " (the job names no number of years, so 6 months is used)."),
             f"Score = 100 x {effective:.1f} / {need_months:g}, at most 100 = {score:.1f}"]
    notes = [f"{unknown} item(s) had no readable dates, so {UNKNOWN_DURATION_MONTHS:g} months was assumed for each."] if unknown else []
    return _result("experience", "evaluated", score, steps, items, notes, used=[f"experience:{i}" for i in range(len(have))])


# ---------------------------------------------------------------------------
# 5. projects and practical work  (what was built: relevance, depth, evidence)
# ---------------------------------------------------------------------------
FULL_RELEVANCE_WEIGHT = 3.0   # covering 3 requirement-weights = fully relevant


def projects(ctx: Context) -> dict:
    wanted = _jd_skill_weights(ctx.jd)
    if not wanted:
        return _result("projects", "not_applicable", notes=["The job description named no verified skills to judge projects against."])
    have = supported(ctx.resume.get("projects"))
    if not have:
        return _result("projects", "not_provided", notes=["No projects could be read from the resume."])

    scored = []
    for idx, p in enumerate(have):
        ids = _skill_ids(_text(p["title"], p.get("description"), p.get("outcome"), p["quote"]))
        for tech in p.get("technologies", []):
            key = CAT.lookup(tech) or f"custom:{normalise(tech)}"
            ids |= {key} | CAT.implied(key)
        covered_w, names = _covered(ids, wanted)
        relevance = min(1.0, covered_w / FULL_RELEVANCE_WEIGHT)
        desc = len(p.get("description") or "")
        depth = 1.0 if desc >= 80 else 0.6 if desc >= 30 else 0.3
        evidence = (0.5 if p.get("outcome") else 0) + (0.5 if p.get("links") else 0)
        points = 100 * (0.6 * relevance + 0.25 * depth + 0.15 * evidence)
        detail = (f"relevance {relevance:.0%} (covers: {', '.join(names) or 'none of the job skills'}), "
                  f"depth {depth:.0%}, evidence {evidence:.0%}")
        scored.append((points, {"label": p["title"], "points": round(points), "detail": detail}, f"project:{idx}"))
    scored.sort(key=lambda t: -t[0])
    top = [t[0] for t in scored[:3]]
    score = 0.6 * top[0] + 0.4 * (sum(top) / len(top))
    steps = ["Each project earns 60% for relevance to the job's skills (covering the weight of 3 requirements = full), "
             "25% for depth (a description of 80+ characters = full) and 15% for evidence (an outcome and a link, half each).",
             "Factor = 60% of the best project + 40% of the average of the best three.",
             f"Score = 0.6 x {top[0]:.0f} + 0.4 x {sum(top) / len(top):.0f} = {score:.1f}"]
    return _result("projects", "evaluated", score, steps, [t[1] for t in scored], ["A project's leadership role is counted under leadership, and any grant under funding, never here."],
                   used=[t[2] for t in scored])


# ---------------------------------------------------------------------------
# 6. certifications
# ---------------------------------------------------------------------------
def certifications(ctx: Context) -> dict:
    have = supported(ctx.resume.get("certifications"))
    asked = supported(ctx.jd.get("certifications"))
    wanted = _jd_skill_weights(ctx.jd)
    if not asked and not have:
        return _result("certifications", "not_applicable", notes=["The job asks for no certification and none is listed."])
    if not asked:
        items, pts = [], []
        for idx, c in enumerate(have):
            related = bool(_skill_ids(c["name"]) & set(wanted))
            p = 50 if related else 10
            pts.append(p)
            items.append({"label": c["name"], "points": p, "detail": "related to the job's skills" if related else "not clearly related"})
        score = _diminishing(pts)
        return _result("certifications", "evaluated", score,
                       ["The job asks for no certification, so listed ones are a bonus: 50 points if related to the job's skills, 10 if not, combined with diminishing returns.",
                        f"Score = {score:.1f}"], items, used=[f"certification:{i}" for i in range(len(have))])

    if not have:
        return _result("certifications", "not_provided",
                       notes=["The job asks for a certification and none is listed in the resume. Add one if you have it; this is not scored as zero."])
    items, earned, total = [], 0.0, 0.0
    for a in asked:
        weight = 1.0 if a.get("required") else 0.5
        a_ids = _skill_ids(a["name"])
        strip = lambda name: normalise(re.sub(r"certified|certification|certificate|professional", "", name, flags=re.I))  # noqa: E731
        a_key = strip(a["name"])
        best = 0.0
        for c in have:
            c_low = strip(c["name"])        # same clean-up on both sides, so "AWS Certified Developer" equals itself
            if a_key and a_key in c_low:
                best = max(best, 1.0)                       # the same certification
            elif a_ids and (_skill_ids(c["name"]) & a_ids):
                best = max(best, 0.5)                       # a certification on the same skill
        total += weight
        earned += weight * best
        items.append({"label": a["name"], "points": round(100 * best),
                      "detail": ("required" if a.get("required") else "optional") + (", same certification" if best == 1 else ", related certification" if best else ", not found")})
    score = 100 * earned / total
    return _result("certifications", "evaluated", score,
                   ["Each certification the job names: found 100%, a different one on the same skill 50%, not found 0%. Required count 1.0, optional 0.5.",
                    f"Score = 100 x {earned:.2f} / {total:.2f} = {score:.1f}"], items, used=[f"certification:{i}" for i in range(len(have))])


# ---------------------------------------------------------------------------
# 7. achievements  (awards, competitions, scholarships; leadership roles are counted elsewhere)
# ---------------------------------------------------------------------------
_BASE = {"competition": 50, "award": 50, "scholarship": 40, "other": 30}
_LEVEL_BOOSTS = [(r"international|global|worldwide", 30), (r"national|all[- ]india", 25), (r"state|regional|zonal|university|inter[- ]college", 12)]
_WINNER = r"winner|first|1st|gold|champion|topper|rank 1|runner"
MAX_ITEM_POINTS = 80


def achievements(ctx: Context) -> dict:
    have = [(i, a) for i, a in enumerate(supported(ctx.resume.get("achievements"))) if a.get("kind") != "leadership"]
    if not have:
        return _result("achievements", "not_applicable", notes=["No awards, competitions or scholarships were found in the resume (leadership roles are counted under leadership)."])
    items, pts = [], []
    for idx, a in have:
        text = _text(a["title"], a.get("description"), a["quote"]).lower()
        base = _BASE.get(a.get("kind", "other"), 30)
        boost = next((b for pattern, b in _LEVEL_BOOSTS if re.search(pattern, text)), 0)
        boost += 10 if re.search(_WINNER, text) else 0
        relevant = _relevant(text, ctx)
        points = min(MAX_ITEM_POINTS, (base + boost) * (1.0 if relevant else 0.6))
        pts.append(points)
        items.append({"label": a["title"], "points": round(points),
                      "detail": f"base {base} + level/winner {boost}, x{1.0 if relevant else 0.6} ({'related to the job or role' if relevant else 'not clearly related'})"})
    score = _diminishing(sorted(pts, reverse=True)[:5])
    return _result("achievements", "evaluated", score,
                   ["Base points by kind (competition or award 50, scholarship 40, other 30), +25 national or +30 international level (+12 state or university), +10 for a win.",
                    "Items clearly related to the job or role count fully; others count 60%. Each item is capped at 80.",
                    f"The best five are combined with diminishing returns. Score = {score:.1f}"], items,
                   ["The amount of any prize money is not used."], used=[f"achievement:{i}" for i, _ in have])


# ---------------------------------------------------------------------------
# 8. leadership and entrepreneurship  (the ROLE someone played, not the work itself)
# ---------------------------------------------------------------------------
_LEAD_WORDS = r"lead|led|leader|head|captain|president|secretary|founder|co-founder|coordinator|organis|organiz|manager|chair|convener|owner"
_ENTREPRENEUR = r"founder|co-founder|startup|start-up|e-cell|entrepreneur|incubat"


def _lead_points(text: str, base: float) -> tuple[float, list[str]]:
    low, notes, points = text.lower(), [], base
    m = re.search(r"team of (\d+)", low)
    if m and int(m.group(1)) >= 3:
        points += 10
        notes.append(f"team of {m.group(1)}")
    m = re.search(r"(\d{2,})\+?\s*(?:participants|attendees|members|students|people)", low)
    if m and int(m.group(1)) >= 100:
        points += 15
        notes.append(f"{m.group(1)}+ people")
    if re.search(_ENTREPRENEUR, low):
        points += 15
        notes.append("entrepreneurship")
    return min(85, points), notes


def leadership(ctx: Context) -> dict:
    items, pts, used = [], [], []
    for i, a in enumerate(supported(ctx.resume.get("achievements"))):
        if a.get("kind") == "leadership":
            p, n = _lead_points(_text(a["title"], a.get("description"), a["quote"]), 55)
            pts.append(p); used.append(f"achievement:{i}")
            items.append({"label": a["title"], "points": round(p), "detail": "leadership role" + (f" ({', '.join(n)})" if n else "")})
    for i, pr in enumerate(supported(ctx.resume.get("projects"))):
        if pr.get("role") and re.search(_LEAD_WORDS, pr["role"], re.I):
            p, n = _lead_points(_text(pr["title"], pr.get("description"), pr["quote"], pr["role"]), 45)
            pts.append(p); used.append(f"project:{i}:role")
            items.append({"label": f"{pr['title']} ({pr['role']})", "points": round(p), "detail": "led a project" + (f" ({', '.join(n)})" if n else "")})
    for i, e in enumerate(supported(ctx.resume.get("experience"))):
        if e.get("title") and re.search(_LEAD_WORDS, e["title"], re.I):
            p, n = _lead_points(_text(e["title"], e["quote"]), 40)
            pts.append(p); used.append(f"experience:{i}:role")
            items.append({"label": e["title"], "points": round(p), "detail": "leading role at work" + (f" ({', '.join(n)})" if n else "")})
    if not items:
        return _result("leadership", "not_applicable", notes=["No leadership or entrepreneurship roles were found in the resume."])
    score = _diminishing(sorted(pts, reverse=True)[:4])
    return _result("leadership", "evaluated", score,
                   ["Leadership roles: 55 points (listed leadership), 45 (led a project), 40 (leading job title). +10 for a team of 3 or more, +15 for 100+ people reached, +15 for entrepreneurship. Each item is capped at 85.",
                    f"The best four are combined with diminishing returns. Score = {score:.1f}"], items,
                   ["This factor credits the ROLE only. The project's content is scored under projects, so nothing is counted twice."], used=used)


# ---------------------------------------------------------------------------
# 9. funding and grants  (NEVER by amount)
# ---------------------------------------------------------------------------
UNVERIFIED_CAP = 70   # a funding claim that nobody has checked can earn at most this much per item


def funding(ctx: Context) -> dict:
    have = supported(ctx.resume.get("funding"))
    if not have:
        return _result("funding", "not_applicable", notes=["No grant or funding was found in the resume. Most students have none, so this is neutral."])
    wanted = _jd_skill_weights(ctx.jd)
    proj_skills = {p["title"].lower(): _skill_ids(_text(p["title"], p.get("description"), " ".join(p.get("technologies", [])))) for p in supported(ctx.resume.get("projects"))}
    items, pts = [], []
    for idx, f in enumerate(have):
        text = _text(f["description"], f.get("purpose"), f.get("outcome"), f["quote"])
        ids = _skill_ids(text)
        for title, skills in proj_skills.items():
            if title and title in text.lower():
                ids |= skills                            # the grant funded this project, so its skills count as context
        covered, _names = _covered(ids, wanted)
        role_hit = any(k in text.lower() for k in ctx.role_keywords)
        relevance = max(min(1.0, covered / 2.0), 0.6 if role_hit else 0.0)
        who = (f.get("candidate_role") or "").lower()
        contribution = 1.0 if re.search(r"lead|founder|principal|investigator|\bpi\b|owner|co-founder", who) else 0.6 if who else 0.5
        outcome = 1.0 if f.get("outcome") else 0.5
        evidence = 1.0 if f.get("source") else 0.5
        raw = 100 * (0.4 * relevance + 0.3 * contribution + 0.2 * outcome + 0.1 * evidence)
        points = min(UNVERIFIED_CAP, raw)
        pts.append(points)
        items.append({"label": f["description"][:80], "points": round(points),
                      "detail": f"relevance {relevance:.0%}, your role {contribution:.0%}, outcome {outcome:.0%}, named source {evidence:.0%}; "
                                f"amount shown but NOT scored: {f.get('amount_text') or 'not stated'}; unverified claim, capped at {UNVERIFIED_CAP}"})
    score = _diminishing(sorted(pts, reverse=True)[:3])
    return _result("funding", "evaluated", score,
                   ["Funding is judged on relevance to the job (40%), your own contribution (30%), the outcome (20%) and whether the funding source is named (10%).",
                    "The AMOUNT is never used: a larger grant does not score higher than a smaller one.",
                    f"Nobody has verified these claims, so each item is capped at {UNVERIFIED_CAP}. Score = {score:.1f}"], items,
                   ["Shown as an unverified claim until a document or an official record supports it."], used=[f"funding:{i}" for i in range(len(have))])


# ---------------------------------------------------------------------------
# 10. verified assessment  (arrives with Phase 10)
# ---------------------------------------------------------------------------
def assessment(ctx: Context) -> dict:
    return _result("assessment", "not_available", notes=["No skill assessment has been taken yet. Taking one later can add verified evidence here."])


FACTORS = {
    "technical_skills": technical_skills, "soft_skills": soft_skills, "education": education, "experience": experience,
    "projects": projects, "certifications": certifications, "achievements": achievements, "leadership": leadership,
    "funding": funding, "assessment": assessment,
}
