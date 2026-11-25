"""Tests for the scoring engine. No LLM and no model are involved: scoring is pure, deterministic rules."""
import copy
from datetime import date

import numpy as np
import pytest

from app.matching.matcher import match_skills
from app.scoring import engine, factors
from app.scoring.durations import parse_months, required_years
from app.scoring.engine import evaluate
from app.scoring.factors import Context, degree_level
from app.scoring.roles import detect_role, list_roles, load_roles

TODAY = date(2026, 11, 24)


def item(status="supported", **fields):
    return {"status": status, "note": "", **fields}


def skill(name, status="supported"):
    return item(status, name=name, quote=name)


def resume(**parts):
    base = {k: [] for k in ["technical_skills", "soft_skills", "education", "experience", "projects", "certifications", "achievements", "funding"]}
    base.update(parts)
    return base


def jd(**parts):
    base = {k: [] for k in ["required_skills", "preferred_skills", "soft_skills", "competencies", "education_requirements",
                            "experience_requirements", "responsibilities", "certifications"]}
    base.update(parts)
    return base


def ctx(r=None, j=None, match=None, keywords=(), today=TODAY):
    return Context(resume=r or resume(), jd=j or jd(), match=match or {"skills": []}, role_keywords=list(keywords), today=today)


def no_embed(texts):
    return np.zeros((len(texts), 4), dtype=np.float32)


def project(title, tech=(), desc="", outcome=None, links=(), role=None, quote=None):
    return item(title=title, description=desc, technologies=list(tech), role=role, outcome=outcome, links=list(links), quote=quote or title)


# ---------------------------------------------------------------------------
# role profiles
# ---------------------------------------------------------------------------
def test_every_role_profile_adds_up_to_100():
    roles = load_roles()
    assert len(roles["roles"]) >= 6
    for rid, role in roles["roles"].items():
        assert sum(role["weights"].values()) == 100, rid
        assert set(role["weights"]) == {f["id"] for f in roles["factors"]}


@pytest.mark.parametrize("title, expected", [
    ("Backend Engineer (Python) - Fintech Platform", "software_developer"), ("Full Stack Developer", "software_developer"),
    ("Data Analyst", "data_analyst"), ("Senior Project Manager", "project_manager"), ("Product Manager", "project_manager"),
    ("Business Development Executive", "business_development"), ("Startup Founder in Residence", "entrepreneurial_innovation"),
    ("Receptionist", "default"), ("", "default"),
])
def test_role_is_detected_from_the_title(title, expected):
    assert detect_role(title) == expected


def test_roles_can_be_listed_for_the_screen():
    assert {r["id"] for r in list_roles()} >= {"default", "software_developer", "project_manager"}


# ---------------------------------------------------------------------------
# durations
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text, months", [
    ("May 2025 - Jul 2025", 3), ("Jan 2023 – Dec 2023", 12), ("June 2024 to August 2024", 3), ("Data Intern (May 2025 - Jul 2025): cleaned data", 3),
    ("6 months", 6), ("2 years", 24), ("1.5 years", 18), ("2022 - 2026", 48), ("Mar 2026 - Present", 9), ("no dates here", None), ("", None), (None, None),
    ("Decision 2023 - 2024 made", 12),   # 'Decision' is not December; falls back to the plain year range
])
def test_parse_months(text, months):
    assert parse_months(text, TODAY) == months


def test_required_years():
    assert required_years("3+ years of professional experience") == 3
    assert required_years("at least 2 yrs") == 2
    assert required_years("strong experience") is None


# ---------------------------------------------------------------------------
# 1 and 2: technical and soft skills (from the Phase 6 match)
# ---------------------------------------------------------------------------
def m(importance, status, method="exact", support="listed", name="X"):
    return {"requirement": name, "importance": importance, "status": status, "method": method, "support": support}


def test_technical_skills_arithmetic():
    match = {"skills": [m("required", "matched", support="demonstrated", name="A"), m("required", "matched", support="listed", name="B"),
                        m("required", "partial", "broader", "listed", "C"), m("required", "missing", "none", None, "D"),
                        m("preferred", "matched", support="listed", name="E")]}
    r = factors.technical_skills(ctx(resume(technical_skills=[skill("A")]), match=match))
    # earned = 1 + 0.8 + 0.5 + 0 + 0.4 x 0.8 = 2.62 ; possible = 4 + 0.4 = 4.4 ; 100 x 2.62 / 4.4 = 59.5
    assert r["status"] == "evaluated" and r["score"] == 59.5 and len(r["items"]) == 5


def test_technical_skills_neutral_and_not_provided_cases():
    assert factors.technical_skills(ctx(match={"skills": []}))["status"] == "not_applicable"
    only_missing = {"skills": [m("required", "missing", "none", None)]}
    assert factors.technical_skills(ctx(resume(), match=only_missing))["status"] == "not_provided"   # an empty resume is not "zero skill"
    assert factors.technical_skills(ctx(resume(technical_skills=[skill("Go")]), match=only_missing))["score"] == 0.0


def test_soft_skills_missing_information_is_not_zero():
    match = {"skills": [m("soft", "missing", "none", None, "Communication")]}
    assert factors.soft_skills(ctx(resume(), match=match))["status"] == "not_provided"
    out = factors.soft_skills(ctx(resume(soft_skills=[skill("teamwork")]), match=match))
    assert out["status"] == "evaluated" and out["score"] == 0.0


# ---------------------------------------------------------------------------
# 3: education
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text, level", [("B.Tech", 3), ("B.E.", 3), ("BE Computer Science", 3), ("Bachelor of Science", 3), ("M.Tech", 4), ("MBA", 4),
                                         ("Master's", 4), ("M.S. in AI", 4), ("PhD", 5), ("Diploma in Engineering", 2), ("Class XII", 1),
                                         ("to be decided", 0), ("tell me more", 0), ("", 0)])
def test_degree_level(text, level):
    assert degree_level(text) == level


def edu(degree, field=None, institution="Some University", year="2022 - 2026"):
    return item(degree=degree, field_of_study=field, institution=institution, year=year, quote=f"{degree} {field} {institution}")


def need(text):
    return item(text=text, quote=text)


def test_education_level_and_related_field():
    r = factors.education(ctx(resume(education=[edu("B.Tech", "Electronics and Communication")]),
                              jd(education_requirements=[need("B.E./B.Tech in Computer Science or a related field")])))
    assert r["status"] == "evaluated" and r["score"] == 84.0     # 0.6 x 100 (level) + 0.4 x 60 (related field)


def test_education_exact_field_and_no_related_allowed():
    j = jd(education_requirements=[need("Bachelor's degree in Computer Science")])
    assert factors.education(ctx(resume(education=[edu("B.Tech", "Computer Science and Engineering")]), j))["score"] == 100.0
    assert factors.education(ctx(resume(education=[edu("B.Tech", "Electronics")]), j))["score"] == 60.0      # related not allowed: field 0


def test_education_one_level_below_and_far_below():
    j = jd(education_requirements=[need("Master's degree in Computer Science")])
    assert factors.education(ctx(resume(education=[edu("B.Tech", "Computer Science")]), j))["score"] == 0.6 * 50 + 0.4 * 100
    j2 = jd(education_requirements=[need("PhD in Computer Science")])
    assert factors.education(ctx(resume(education=[edu("B.Tech", "Computer Science")]), j2))["score"] == 0.6 * 0 + 0.4 * 100


def test_education_ignores_the_college_name_and_grades():
    j = jd(education_requirements=[need("B.Tech in Computer Science")])
    a = factors.education(ctx(resume(education=[edu("B.Tech", "Computer Science", institution="IIT Bombay")]), j))
    b = factors.education(ctx(resume(education=[edu("B.Tech", "Computer Science", institution="Unknown Village College")]), j))
    assert a["score"] == b["score"] == 100.0
    # an institute's name must not change the field: "Information Technology" in a name does not make an ECE degree computing
    c = factors.education(ctx(resume(education=[edu("B.Tech", "Electronics", institution="Institute of Information Technology")]), j))
    assert c["score"] == 60.0


def test_education_statuses_and_in_progress_note():
    assert factors.education(ctx(resume(education=[edu("B.Tech")]), jd()))["status"] == "not_applicable"
    assert factors.education(ctx(resume(), jd(education_requirements=[need("B.Tech")])))["status"] == "not_provided"
    r = factors.education(ctx(resume(education=[edu("B.Tech", "Computer Science", year="2022 - 2026")]), jd(education_requirements=[need("B.Tech in Computer Science")])))
    assert any("in progress" in n for n in r["notes"])


# ---------------------------------------------------------------------------
# 4: experience
# ---------------------------------------------------------------------------
def exp(title, org, kind, duration, resp, quote=None):
    return item(title=title, organization=org, kind=kind, duration=duration, responsibilities=resp, quote=quote or f"{title} {org}")


def test_experience_counts_internships_at_half_and_relevant_work_fully():
    j = jd(required_skills=[skill("Python")], experience_requirements=[item(text="3+ years of backend experience", years="3+", quote="3+ years")])
    r = factors.experience(ctx(resume(experience=[exp("Intern", "Acme", "internship", "May 2025 - Jul 2025", ["Wrote Python scripts"])]), j))
    # 3 months x 0.5 (internship) x 1.0 (Python is relevant) = 1.5 months of the 36 asked for
    assert r["status"] == "evaluated" and r["score"] == round(100 * 1.5 / 36, 1)


def test_experience_not_clearly_relevant_counts_less_and_job_counts_fully():
    j = jd(required_skills=[skill("Python")], experience_requirements=[item(text="1 year of experience", years="1", quote="1 year")])
    job = exp("Cashier", "Shop", "job", "Jan 2025 - Dec 2025", ["Handled billing"])       # 12 months x 1.0 x 0.4 = 4.8
    assert factors.experience(ctx(resume(experience=[job]), j))["score"] == round(100 * 4.8 / 12, 1)
    relevant = exp("Dev", "Firm", "job", "Jan 2025 - Dec 2025", ["Built Python APIs"])      # 12 x 1 x 1 = 12 -> 100
    assert factors.experience(ctx(resume(experience=[relevant]), j))["score"] == 100.0


def test_experience_is_capped_at_100_and_unknown_dates_are_assumed_and_disclosed():
    j = jd(required_skills=[skill("Python")], experience_requirements=[item(text="2 years of Python", years="2", quote="2 years")])
    long = exp("Dev", "Firm", "job", "Jan 2020 - Dec 2025", ["Python"])
    assert factors.experience(ctx(resume(experience=[long]), j))["score"] == 100.0
    r = factors.experience(ctx(resume(experience=[exp("Dev", "Firm", "job", None, ["Python"], quote="Dev at Firm")]), j))
    assert any("no readable dates" in n for n in r["notes"])


def test_experience_statuses_students_without_jobs_are_not_scored_zero():
    j = jd(experience_requirements=[item(text="2+ years", years="2+", quote="2+ years")])
    assert factors.experience(ctx(resume(), j))["status"] == "not_provided"
    assert factors.experience(ctx(resume(experience=[exp("Dev", "F", "job", "2 years", [])]), jd()))["status"] == "not_applicable"


# ---------------------------------------------------------------------------
# 5: projects
# ---------------------------------------------------------------------------
JD3 = jd(required_skills=[skill("Python"), skill("Docker"), skill("SQL")])
LONG = "A long description of what was built, how it works and who used it, written clearly in detail."


def test_project_scoring_arithmetic():
    full = project("Shop", ["Python", "Docker", "SQL"], LONG, outcome="1000 users", links=["https://x.test"])
    assert len(LONG) >= 80
    r = factors.projects(ctx(resume(projects=[full]), JD3))
    # relevance 100% (3 of 3), depth 100%, evidence 100% -> 100 ; factor = 0.6 x 100 + 0.4 x 100
    assert r["score"] == 100.0
    half = project("Blog", ["Python"], "short blurb of text that is about forty characters")        # relevance 1/3, depth 0.6, evidence 0
    r2 = factors.projects(ctx(resume(projects=[half]), JD3))
    assert r2["score"] == round(0.6 * (100 * (0.6 * (1 / 3) + 0.25 * 0.6)) + 0.4 * (100 * (0.6 * (1 / 3) + 0.25 * 0.6)), 1)


def test_projects_implied_skills_count_and_best_projects_dominate():
    django = project("Site", ["Django"], LONG, outcome="live", links=["x"])        # Django implies Python: covers 1 of the 3
    r = factors.projects(ctx(resume(projects=[django, project("Toy", [], "x")]), JD3))
    assert r["status"] == "evaluated" and r["items"][0]["label"] == "Site"


def test_projects_statuses():
    assert factors.projects(ctx(resume(projects=[project("A")]), jd()))["status"] == "not_applicable"
    assert factors.projects(ctx(resume(), JD3))["status"] == "not_provided"


# ---------------------------------------------------------------------------
# 6: certifications
# ---------------------------------------------------------------------------
def cert(name):
    return item(name=name, issuer=None, date=None, quote=name)


def test_certifications_same_related_and_missing():
    j = jd(certifications=[item(name="AWS Certified Developer", required=True, quote="x")])
    assert factors.certifications(ctx(resume(certifications=[cert("AWS Certified Developer")]), j))["score"] == 100.0
    assert factors.certifications(ctx(resume(certifications=[cert("AWS Certified Cloud Practitioner")]), j))["score"] == 50.0
    assert factors.certifications(ctx(resume(certifications=[cert("Google Data Analytics")]), j))["score"] == 0.0
    assert factors.certifications(ctx(resume(), j))["status"] == "not_provided"       # none listed: not scored as zero


def test_certifications_are_a_bonus_when_not_asked_for():
    assert factors.certifications(ctx(resume(), jd()))["status"] == "not_applicable"
    r = factors.certifications(ctx(resume(certifications=[cert("AWS Certified Cloud Practitioner")]), jd(required_skills=[skill("AWS")])))
    assert r["status"] == "evaluated" and r["score"] == 50.0


# ---------------------------------------------------------------------------
# 7: achievements
# ---------------------------------------------------------------------------
def ach(title, kind, description=None):
    return item(title=title, kind=kind, description=description, quote=title)


def test_achievement_points_and_relevance():
    win = ach("Smart India Hackathon 2024 - Winner (national level)", "competition")
    r = factors.achievements(ctx(resume(achievements=[win]), keywords=["hackathon"]))
    assert r["items"][0]["points"] == 80       # (50 + 25 national + 10 winner) x 1.0, capped at 80
    r2 = factors.achievements(ctx(resume(achievements=[win]), keywords=[]))
    assert r2["items"][0]["points"] == 51      # 85 x 0.6 (not clearly related) = 51


def test_achievements_combine_with_diminishing_returns_and_never_reach_100():
    two = [ach("Hackathon winner national", "competition"), ach("State level quiz winner", "award")]
    r = factors.achievements(ctx(resume(achievements=two), keywords=["hackathon", "quiz"]))
    assert 80 < r["score"] < 100


def test_leadership_roles_are_not_counted_as_achievements():
    only_lead = [ach("Secretary of the coding club", "leadership")]
    assert factors.achievements(ctx(resume(achievements=only_lead)))["status"] == "not_applicable"


def test_prize_money_is_not_used():
    a = factors.achievements(ctx(resume(achievements=[ach("Hackathon winner - prize Rs. 5,00,000", "competition")]), keywords=["hackathon"]))
    b = factors.achievements(ctx(resume(achievements=[ach("Hackathon winner - prize Rs. 500", "competition")]), keywords=["hackathon"]))
    assert a["score"] == b["score"]


# ---------------------------------------------------------------------------
# 8: leadership
# ---------------------------------------------------------------------------
def test_leadership_from_achievements_projects_and_entrepreneurship_bonus():
    lead = ach("Secretary, Entrepreneurship Cell: organised 6 events with 800+ participants", "leadership")
    r = factors.leadership(ctx(resume(achievements=[lead])))
    assert r["items"][0]["points"] == 85      # 55 + 15 (800+ people) + 15 (entrepreneurship) = 85, at the cap
    led = project("AgriSense", ["ESP32"], "Led a team of 4 to build it", role="team lead")
    r2 = factors.leadership(ctx(resume(projects=[led])))
    assert r2["items"][0]["points"] == 55     # 45 + 10 (team of 4)


def test_leadership_not_applicable_when_nothing_found():
    assert factors.leadership(ctx(resume(projects=[project("A", role="member")])))["status"] == "not_applicable"


# ---------------------------------------------------------------------------
# 9: funding  (never by amount)
# ---------------------------------------------------------------------------
def fund(amount, source="Startup India Seed Fund", role="team lead", outcome="piloted on 12 farms"):
    return item(description=f"Received {amount} seed grant for AgriSense", source=source, amount_text=amount, purpose="soil sensors",
                candidate_role=role, outcome=outcome, quote=f"Received {amount} seed grant for AgriSense")


def test_funding_amount_never_changes_the_score():
    j = jd(required_skills=[skill("Python")])
    scores = {amt: factors.funding(ctx(resume(funding=[fund(amt)]), j, keywords=["seed"]))["score"] for amt in ("Rs. 2 crore", "Rs. 2 lakh", "Rs. 2,000", None)}
    assert len(set(scores.values())) == 1


def test_funding_depends_on_relevance_role_outcome_and_source():
    j = jd(required_skills=[skill("Python")])
    strong = factors.funding(ctx(resume(funding=[fund("Rs. 1 lakh")]), j, keywords=["seed"]))["score"]
    weak = factors.funding(ctx(resume(funding=[fund("Rs. 1 lakh", source=None, role=None, outcome=None)]), j, keywords=["seed"]))["score"]
    unrelated = factors.funding(ctx(resume(funding=[fund("Rs. 1 lakh")]), j, keywords=[]))["score"]
    assert strong > weak and strong > unrelated


def test_unverified_funding_is_capped_per_item():
    r = factors.funding(ctx(resume(funding=[fund("Rs. 9 crore")]), jd(required_skills=[skill("Python")]), keywords=["seed"]))
    assert r["items"][0]["points"] <= factors.UNVERIFIED_CAP and "NOT scored" in r["items"][0]["detail"]


def test_funding_not_applicable_when_none():
    assert factors.funding(ctx(resume(), JD3))["status"] == "not_applicable"


# ---------------------------------------------------------------------------
# 10 and the engine
# ---------------------------------------------------------------------------
def test_assessment_is_not_available_yet():
    assert factors.assessment(ctx())["status"] == "not_available"


def stub_factors(monkeypatch, spec):
    """spec: factor id -> (status, score). Replaces the real scorers so the engine's arithmetic can be checked by hand."""
    def make(fid, status, score):
        return lambda c: {"id": fid, "status": status, "score": score, "steps": [], "items": [], "notes": [], "used": []}
    patched = {fid: make(fid, *spec.get(fid, ("not_applicable", None))) for fid in factors.FACTORS}
    monkeypatch.setattr(engine, "FACTORS", patched)


def test_engine_arithmetic_with_missing_information(monkeypatch):
    stub_factors(monkeypatch, {"technical_skills": ("evaluated", 80.0), "soft_skills": ("not_provided", None), "education": ("evaluated", 60.0),
                               "experience": ("not_provided", None), "projects": ("evaluated", 70.0), "achievements": ("evaluated", 50.0),
                               "assessment": ("not_available", None)})
    out = evaluate(resume(), jd(), {"skills": []}, role_id="default", today=TODAY)
    # default weights: tech 25, edu 10, projects 15, achievements 5 are evaluated: W = 55
    # total = 80x25 + 60x10 + 70x15 + 50x5 = 3900 ; overall = 3900 / 55 = 70.9
    assert out["overall"] == 70.9
    # applicable weight = 55 + soft 10 + experience 15 = 80 ; lower bound = 3900 / 80 = 48.75
    assert out["lower_bound"] in (48.7, 48.8) and out["coverage"] == 0.69 and out["evidence_level"] == "medium"
    assert out["not_provided"] == ["Soft skills", "Relevant experience"]
    eff = {f["id"]: f["effective_weight"] for f in out["factors"]}
    assert eff["technical_skills"] == 45.5 and eff["soft_skills"] is None
    assert abs(sum(f["contribution"] for f in out["factors"] if f["contribution"] is not None) - out["overall"]) < 0.3


def test_engine_with_everything_evaluated_uses_the_nominal_weights(monkeypatch):
    spec = {fid: ("evaluated", 100.0) for fid in factors.FACTORS}
    spec["assessment"] = ("evaluated", 100.0)
    stub_factors(monkeypatch, spec)
    out = evaluate(resume(), jd(), {"skills": []}, role_id="software_developer", today=TODAY)
    assert out["overall"] == out["lower_bound"] == 100.0 and out["coverage"] == 1.0 and out["evidence_level"] == "high"
    assert all(f["effective_weight"] == f["weight"] for f in out["factors"])


def test_engine_nothing_to_evaluate(monkeypatch):
    stub_factors(monkeypatch, {})
    out = evaluate(resume(), jd(), {"skills": []}, today=TODAY)
    assert out["overall"] is None and out["lower_bound"] is None and out["coverage"] == 0.0


def test_unknown_role_is_refused():
    with pytest.raises(ValueError):
        evaluate(resume(), jd(), {"skills": []}, role_id="wizard")


# ----- a realistic whole-resume run -----
def realistic():
    r = resume(
        technical_skills=[skill("Python"), skill("SQL"), skill("Docker")],
        soft_skills=[skill("communication")],
        education=[edu("B.Tech", "Electronics and Communication", institution="NIT Warangal")],
        experience=[exp("Data Science Intern", "FinServe Labs", "internship", "May 2025 - Jul 2025", ["Built a churn model with Python and scikit-learn"])],
        projects=[project("AgriSense", ["ESP32", "Flask", "Python"], "Led a team of 4 to build a soil moisture system using Flask and MQTT; piloted on farms", outcome="12 farms", links=["https://github.com/x/agrisense"], role="team lead")],
        certifications=[cert("AWS Certified Cloud Practitioner")],
        achievements=[ach("Smart India Hackathon 2024 - Winner (national level)", "competition"), ach("Secretary, Entrepreneurship Cell", "leadership")],
        funding=[fund("Rs. 12 lakh")],
    )
    j = jd(required_skills=[skill("Python"), skill("SQL"), skill("PostgreSQL"), skill("Docker")], preferred_skills=[skill("AWS"), skill("Kafka")],
           soft_skills=[skill("Communication")], education_requirements=[need("B.E./B.Tech in Computer Science or a related field")],
           experience_requirements=[item(text="3+ years of backend experience", years="3+", quote="3+ years")])
    return r, j, match_skills(r, j, embed_fn=no_embed)


def test_full_run_has_all_ten_factors_and_no_evidence_spent_twice():
    r, j, match = realistic()
    out = evaluate(r, j, match, job_title="Backend Engineer", today=TODAY)
    assert [f["id"] for f in out["factors"]] == [f["id"] for f in load_roles()["factors"]] and len(out["factors"]) == 10
    assert out["role_profile"]["id"] == "software_developer" and out["role_profile"]["auto_detected"] is True
    assert out["warnings"] == [] and 0 < out["overall"] <= 100 and out["lower_bound"] <= out["overall"]
    achievement_labels = [i["label"] for f in out["factors"] if f["id"] == "achievements" for i in f["items"]]
    leadership_labels = [i["label"] for f in out["factors"] if f["id"] == "leadership" for i in f["items"]]
    assert not any("Secretary" in lbl for lbl in achievement_labels) and any("Secretary" in lbl for lbl in leadership_labels)
    used = [k for f in out["factors"] for k in f["used"]]
    assert len(used) == len(set(used))            # every piece of evidence is spent exactly once
    assert "college name or reputation" in out["not_used"] and "not a prediction" in out["disclaimer"]


def test_different_roles_weight_the_same_evidence_differently():
    r, j, match = realistic()
    dev = evaluate(r, j, match, role_id="software_developer", today=TODAY)
    pm = evaluate(r, j, match, role_id="project_manager", today=TODAY)
    assert dev["role_profile"]["weights"] != pm["role_profile"]["weights"]
    independent = ("technical_skills", "soft_skills", "education", "experience", "projects", "certifications")
    scores = lambda out: {f["id"]: f["score"] for f in out["factors"] if f["id"] in independent}   # noqa: E731
    assert scores(dev) == scores(pm)                       # these do not look at the role: same evidence, same score
    assert dev["overall"] != pm["overall"]                 # so the overall differs because of the weights (and the next point)
    # Achievements and funding ARE role-aware: a hackathon win is related for a developer role, not for a project manager
    ach = lambda out: next(f["score"] for f in out["factors"] if f["id"] == "achievements")   # noqa: E731
    assert ach(dev) > ach(pm)


def test_scores_do_not_depend_on_name_or_college():
    r, j, match = realistic()
    other = copy.deepcopy(r)
    other["education"][0]["institution"] = "A Completely Different College"
    other["education"][0]["quote"] = "B.Tech Electronics and Communication A Completely Different College"
    assert evaluate(r, j, match, role_id="default", today=TODAY)["overall"] == evaluate(other, j, match, role_id="default", today=TODAY)["overall"]


def test_unverified_items_never_earn_points():
    r, j, match = realistic()
    weakened = copy.deepcopy(r)
    for category in ("projects", "funding", "achievements", "certifications"):
        for it in weakened[category]:
            it["status"] = "needs_review"
    out = evaluate(weakened, j, match_skills(weakened, j, embed_fn=no_embed), role_id="default", today=TODAY)
    statuses = {f["id"]: f["status"] for f in out["factors"]}
    assert statuses["funding"] == "not_applicable" and statuses["achievements"] == "not_applicable" and statuses["projects"] == "not_provided"
