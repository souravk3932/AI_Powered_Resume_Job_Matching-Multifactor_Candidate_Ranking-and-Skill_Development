"""Tests for the skill catalogue and the matching engine. A fake embedder is used for the engine tests,
so they need no model. One test at the bottom uses the real Sentence Transformers model."""
import numpy as np
import pytest

from app.matching.catalog import get_catalog, normalise
from app.matching.matcher import match_skills

cat = get_catalog()


# ---------- catalogue ----------
@pytest.mark.parametrize("written, expected", [
    ("JS", "javascript"), ("Java Script", "javascript"), ("ECMAScript", "javascript"), ("Postgres", "postgresql"),
    ("Node.js", "nodejs"), ("nodejs", "nodejs"), ("C++", "cpp"), ("c#", "csharp"), ("K8s", "kubernetes"),
    ("Strong Python skills", "python"), ("experience with Docker", "docker"), ("REST", "rest"), ("RESTful APIs", "rest"),
    ("ML", "machine-learning"), ("excellent communication", "communication"), ("Team player", "teamwork"),
])
def test_lookup_understands_many_spellings(written, expected):
    assert cat.lookup(written) == expected


def test_unknown_skill_is_none():
    assert cat.lookup("Rasa") is None and cat.lookup("banana bread") is None


def test_implied_and_specific_relations():
    assert {"python"} <= cat.implied("django") and {"sql"} <= cat.implied("postgresql")
    assert cat.implied("keras") >= {"tensorflow", "python", "deep-learning", "machine-learning"}   # follows the chain
    assert {"postgresql", "mysql"} <= cat.specifics("sql")
    assert "sql" not in cat.implied("sql")


def test_families():
    assert cat.shared_family("kafka", "rabbitmq") == "Message queues"
    assert cat.shared_family("kafka", "react") is None


def test_text_scanning_finds_skills_but_not_ordinary_words():
    found = cat.find_in_text("Built REST APIs with Node.js and PostgreSQL, deployed on Docker. We go the extra mile and express interest.")
    assert {"rest", "nodejs", "postgresql", "docker"} <= found
    assert "go" not in found and "express" not in found and "c" not in found


def test_text_scan_prefers_the_longest_name():
    found = cat.find_in_text("Wrote Java Script and some Java")
    assert "javascript" in found and "java" in found


def test_rest_the_word_is_not_the_skill():
    assert "rest" not in cat.find_in_text("Did the rest of the work")


def test_catalogue_is_consistent():
    # loading it already checks duplicate ids/aliases and unknown references; this just proves it loads
    assert cat.version == "skills-v1" and cat.name_of("javascript") == "JavaScript"


# ---------- helpers to build profiles ----------
def item(status="supported", **fields):
    return {"status": status, "note": "", **fields}


def skill(name, quote=None, status="supported"):
    return item(status, name=name, quote=quote or name)


def resume(**parts):
    base = {k: [] for k in ["technical_skills", "soft_skills", "education", "experience", "projects", "certifications", "achievements", "funding"]}
    base.update(parts)
    return base


def jd(**parts):
    base = {k: [] for k in ["required_skills", "preferred_skills", "soft_skills", "competencies"]}
    base.update(parts)
    return base


def by_name(result):
    return {r["requirement"]: r for r in result["skills"]}


def no_embed(texts):  # a fake that finds nothing similar
    return np.zeros((len(texts), 4), dtype=np.float32)


# ---------- the matching rules ----------
def test_exact_and_alias():
    out = match_skills(resume(technical_skills=[skill("JS"), skill("Python")]),
                       jd(required_skills=[skill("JavaScript"), skill("Python")]), embed_fn=no_embed)
    r = by_name(out)
    assert r["JavaScript"]["status"] == "matched" and r["JavaScript"]["method"] == "alias"
    assert r["Python"]["status"] == "matched" and r["Python"]["method"] == "exact" and r["Python"]["support"] == "listed"


def test_specific_skill_satisfies_general_requirement():
    out = match_skills(resume(technical_skills=[skill("PostgreSQL"), skill("Django")]),
                       jd(required_skills=[skill("SQL"), skill("Python")]), embed_fn=no_embed)
    r = by_name(out)
    assert r["SQL"]["status"] == "matched" and r["SQL"]["method"] == "implied" and r["SQL"]["matched_with"] == "PostgreSQL"
    assert r["Python"]["status"] == "matched" and r["Python"]["matched_with"] == "Django"


def test_general_skill_is_only_partial_for_specific_requirement():
    out = match_skills(resume(technical_skills=[skill("SQL")]), jd(required_skills=[skill("PostgreSQL")]), embed_fn=no_embed)
    r = by_name(out)["PostgreSQL"]
    assert r["status"] == "partial" and r["method"] == "broader"


def test_similar_skill_is_partial():
    out = match_skills(resume(technical_skills=[skill("RabbitMQ")]), jd(preferred_skills=[skill("Kafka")]), embed_fn=no_embed)
    r = by_name(out)["Kafka"]
    assert r["status"] == "partial" and r["method"] == "family" and "Message queues" in r["reason"]


def test_different_languages_are_not_a_match():
    out = match_skills(resume(technical_skills=[skill("Java")]), jd(required_skills=[skill("Python")]), embed_fn=no_embed)
    assert by_name(out)["Python"]["status"] == "missing"


def test_missing_wording_is_fair():
    out = match_skills(resume(), jd(required_skills=[skill("Docker")]), embed_fn=no_embed)
    reason = by_name(out)["Docker"]["reason"]
    assert by_name(out)["Docker"]["status"] == "missing" and "does not mean you lack" in reason


def test_unverified_resume_claims_do_not_count():
    out = match_skills(resume(technical_skills=[skill("Docker", status="needs_review")]),
                       jd(required_skills=[skill("Docker")]), embed_fn=no_embed)
    assert by_name(out)["Docker"]["status"] == "missing"
    assert out["not_used"]["resume_items_needing_review"] == ["Docker"]


def test_unverified_job_requirements_are_not_demanded():
    out = match_skills(resume(), jd(required_skills=[skill("Kubernetes", status="needs_review")]), embed_fn=no_embed)
    assert out["skills"] == [] and out["not_used"]["job_items_needing_review"] == ["Kubernetes"]


def test_required_wins_over_preferred_and_counts_once():
    out = match_skills(resume(), jd(required_skills=[skill("AWS")], preferred_skills=[skill("Amazon Web Services")]), embed_fn=no_embed)
    assert len(out["skills"]) == 1 and out["skills"][0]["importance"] == "required"


def test_demonstrated_beats_listed():
    proj = item(title="Chat app", description="Built with Docker containers", technologies=["Node.js"], role=None,
                outcome=None, links=[], quote="Chat app built with Docker containers")
    out = match_skills(resume(technical_skills=[skill("Docker")], projects=[proj]), jd(required_skills=[skill("Docker")]), embed_fn=no_embed)
    r = by_name(out)["Docker"]
    assert r["support"] == "demonstrated" and any(e["source"] == "project: Chat app" for e in r["evidence"])


def test_skill_found_inside_experience_text():
    exp = item(title="Intern", organization="Acme", kind="internship", duration=None,
               responsibilities=["Wrote Python scripts for data cleaning"], quote="Wrote Python scripts for data cleaning")
    out = match_skills(resume(experience=[exp]), jd(required_skills=[skill("Python")]), embed_fn=no_embed)
    assert by_name(out)["Python"]["status"] == "matched" and by_name(out)["Python"]["support"] == "demonstrated"


def test_soft_skills_alias_and_leadership_evidence():
    ach = item(title="Secretary, E-Cell", kind="leadership", description=None, quote="Secretary, E-Cell")
    out = match_skills(resume(soft_skills=[skill("team work")], achievements=[ach]),
                       jd(soft_skills=[skill("collaboration"), skill("leadership"), skill("public speaking")]), embed_fn=no_embed)
    r = by_name(out)
    assert r["Teamwork"]["status"] == "matched" and r["Leadership"]["status"] == "matched" and r["Public Speaking"]["status"] == "missing"


def test_custom_skills_outside_the_catalogue_match_by_name():
    out = match_skills(resume(technical_skills=[skill("Rasa")]), jd(required_skills=[skill("rasa"), skill("Zebra Framework")]), embed_fn=no_embed)
    r = by_name(out)
    assert r["rasa"]["status"] == "matched" and r["Zebra Framework"]["status"] == "missing"


def test_summary_counts():
    out = match_skills(resume(technical_skills=[skill("Python"), skill("RabbitMQ")]),
                       jd(required_skills=[skill("Python"), skill("Docker")], preferred_skills=[skill("Kafka")]), embed_fn=no_embed)
    assert out["summary"]["required"] == {"total": 2, "matched": 1, "partial": 0, "missing": 1}
    assert out["summary"]["preferred"] == {"total": 1, "matched": 0, "partial": 1, "missing": 0}
    assert "score" not in out   # this engine makes no score


# ---------- the meaning-based step ----------
def similar_to_first(texts):
    """Fake embedder: the requirement phrases and the first snippet point the same way."""
    vecs = np.zeros((len(texts), 2), dtype=np.float32)
    for i, t in enumerate(texts):
        vecs[i] = [1, 0] if (t.startswith("Experience with") or "web services" in t) else [0, 1]
    return vecs


def test_semantic_match_is_only_a_low_confidence_partial():
    proj = item(title="Backend", description="Designed web services", technologies=[], role=None, outcome=None, links=[], quote="Designed web services")
    out = match_skills(resume(projects=[proj]), jd(required_skills=[skill("Zebra Framework")]), embed_fn=similar_to_first, threshold=0.5)
    r = by_name(out)["Zebra Framework"]
    assert r["status"] == "partial" and r["method"] == "semantic" and r["confidence"] == "low" and r["similarity"] == 1.0
    assert r["status"] != "matched"


def test_semantic_below_threshold_stays_missing():
    proj = item(title="Backend", description="Cooking club", technologies=[], role=None, outcome=None, links=[], quote="Cooking club")
    out = match_skills(resume(projects=[proj]), jd(required_skills=[skill("Zebra Framework")]), embed_fn=no_embed, threshold=0.5)
    assert by_name(out)["Zebra Framework"]["status"] == "missing"


def test_embedder_trouble_is_reported_not_fatal():
    from app.matching.embedder import EmbedderUnavailable

    def broken(texts):
        raise EmbedderUnavailable("blocked")
    proj = item(title="Backend", description="x", technologies=[], role=None, outcome=None, links=[], quote="x")
    out = match_skills(resume(projects=[proj]), jd(required_skills=[skill("Zebra Framework")]), embed_fn=broken)
    assert by_name(out)["Zebra Framework"]["status"] == "missing" and out["warnings"]


# ---------- the real model (skipped if Sentence Transformers cannot load) ----------
def test_real_model_separates_related_from_unrelated():
    from app.matching import embedder
    try:
        vecs = embedder.embed(["Experience with REST APIs", "Designed web services using Django", "Led the college cultural club"])
    except embedder.EmbedderUnavailable as exc:
        pytest.skip(f"model not available: {exc}")
    related, unrelated = float(vecs[0] @ vecs[1]), float(vecs[0] @ vecs[2])
    assert vecs.shape == (3, 384) and related > 0.4 and unrelated < 0.2 and related > unrelated + 0.3
    assert abs(float(np.linalg.norm(vecs[0])) - 1.0) < 1e-4    # unit length, so a dot product is the cosine
