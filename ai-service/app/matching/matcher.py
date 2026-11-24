"""Phase 6: match a resume's skills against a job description's skill requirements.

Result for every requirement: matched, partial or missing, with the evidence and a plain-English reason.
This file makes NO final score. Scoring is a separate, deterministic engine (Phase 7).

How a requirement is judged (first rule that applies wins):
  1. exact / alias   resume has the same skill (JS = JavaScript)             -> matched
  2. implied         resume has a more specific skill that includes it
                     (PostgreSQL includes SQL, Django includes Python)       -> matched
  3. broader         job wants the specific one, resume has only the general
                     (job wants PostgreSQL, resume has SQL)                  -> partial
  4. family          resume has a similar skill (Kafka vs RabbitMQ)          -> partial
  5. semantic        a sentence in the resume means something similar,
                     found with Sentence Transformers                        -> partial (low confidence)
  6. otherwise                                                               -> missing
Embeddings never create "matched" on their own: "Python" and "Java" look alike to them.

Only claims whose quote was verified ("supported") count as evidence. "Missing" only means
"not found in the text we could read", never "the student lacks this skill".
"""
import os
from typing import Callable

import numpy as np

from app.matching.catalog import SkillCatalog, get_catalog, normalise

ENGINE_VERSION = "match-v1"
DEFAULT_PARTIAL_THRESHOLD = 0.5   # cosine similarity needed to suggest a partial match


def _supported(items) -> list[dict]:
    return [i for i in (items or []) if i.get("status") == "supported"]


def _needs_review(items) -> list[str]:
    return [i.get("name") or i.get("title") or i.get("text", "")[:40] for i in (items or []) if i.get("status") != "supported"]


class _Candidate:
    """Everything the resume (verified items only) tells us, organised by skill."""

    def __init__(self, resume: dict, catalog: SkillCatalog):
        self.catalog = catalog
        self.have: dict[str, list[dict]] = {}    # skill key -> evidence
        self.display: dict[str, str] = {}        # skill key -> name as it should be shown
        self.spelled: dict[str, str] = {}        # skill key -> how the resume itself wrote it ("JS")
        self.snippets: list[tuple[str, str]] = []  # (source label, sentence) for the semantic step
        self._build(resume)

    def key_for(self, name: str) -> str:
        skill_id = self.catalog.lookup(name)
        return skill_id or f"custom:{normalise(name)}"

    def _add(self, key: str, shown: str, source: str, strength: str, text: str):
        self.display.setdefault(key, self.catalog.name_of(key) if not key.startswith("custom:") else shown)
        self.spelled.setdefault(key, shown)
        entry = {"source": source, "text": text[:160], "strength": strength}
        if entry not in self.have.setdefault(key, []):
            self.have[key].append(entry)

    def _scan(self, text: str, source: str, strength: str = "demonstrated"):
        for skill_id in self.catalog.find_in_text(text):
            self._add(skill_id, self.catalog.name_of(skill_id), source, strength, text)

    def _build(self, r: dict):
        for item in _supported(r.get("technical_skills")):
            self._add(self.key_for(item["name"]), item["name"], "skills list", "listed", item["quote"])
        for item in _supported(r.get("soft_skills")):
            self._add(self.key_for(item["name"]), item["name"], "skills list", "listed", item["quote"])

        for p in _supported(r.get("projects")):
            source = f"project: {p['title']}"
            for tech in p.get("technologies", []):
                self._add(self.key_for(tech), tech, source, "demonstrated", p["quote"])
            self._scan(" ".join(filter(None, [p["title"], p.get("description"), p.get("outcome"), p["quote"]])), source)
            self.snippets.append((source, " ".join(filter(None, [p["title"], p.get("description"), ", ".join(p.get("technologies", []))]))))

        for e in _supported(r.get("experience")):
            source = f"{e.get('kind', 'experience')}: {' at '.join(filter(None, [e.get('title'), e.get('organization')])) or 'experience'}"
            text = " ".join([*e.get("responsibilities", []), e["quote"]])
            self._scan(text, source)
            self.snippets.append((source, text))

        for c in _supported(r.get("certifications")):
            source = f"certification: {c['name']}"
            self._scan(c["name"], source, "certified")
            self.snippets.append((source, c["name"]))

        for a in _supported(r.get("achievements")):
            source = f"achievement: {a['title']}"
            self._scan(" ".join(filter(None, [a["title"], a.get("description")])), source)
            if a.get("kind") == "leadership":
                self._add("leadership", "Leadership", source, "demonstrated", a["quote"])
            self.snippets.append((source, " ".join(filter(None, [a["title"], a.get("description")]))))


def _best_support(evidence: list[dict]) -> str:
    strengths = {e["strength"] for e in evidence}
    return "demonstrated" if "demonstrated" in strengths else "certified" if "certified" in strengths else "listed"


def _cite(evidence: list[dict]) -> str:
    best = max(evidence, key=lambda e: {"demonstrated": 3, "certified": 2, "listed": 1}[e["strength"]])
    return "in your skills list" if best["source"] == "skills list" else f"in your {best['source']}"


def match_skills(resume: dict, jd: dict, embed_fn: Callable | None = None, catalog: SkillCatalog | None = None,
                 threshold: float | None = None) -> dict:
    """resume and jd are the 'data' parts of the stored AI profiles."""
    catalog = catalog or get_catalog()
    threshold = threshold if threshold is not None else float(os.getenv("MATCH_PARTIAL_THRESHOLD", DEFAULT_PARTIAL_THRESHOLD))
    cand = _Candidate(resume, catalog)
    warnings: list[str] = []

    # --- the requirements (only verified ones; unverified ones are reported, not used) ---
    reqs: list[dict] = []
    seen: set[str] = set()
    for importance, field in (("required", "required_skills"), ("preferred", "preferred_skills"), ("soft", "soft_skills")):
        for item in _supported(jd.get(field)):
            key = cand.key_for(item["name"])
            if key in seen:
                continue  # a skill listed as both required and preferred counts once, as the stronger one
            seen.add(key)
            reqs.append({"key": key, "name": catalog.name_of(key) if not key.startswith("custom:") else item["name"],
                         "importance": importance, "quote": item["quote"], "raw": item["name"]})

    results = []
    pending = []  # requirements the catalogue could not settle: candidates for the semantic step
    for q in reqs:
        res = {"requirement": q["name"], "importance": q["importance"], "jd_quote": q["quote"],
               "status": "missing", "method": "none", "confidence": "high", "support": None,
               "matched_with": None, "evidence": [], "reason": ""}
        key = q["key"]

        if key in cand.have:                                                       # 1. exact or alias
            ev = cand.have[key]
            shown = cand.spelled[key]   # exactly how the resume wrote it
            same = normalise(shown) in {normalise(q["raw"]), normalise(q["name"])}
            res.update(status="matched", method="exact" if same else "alias", confidence="high", evidence=ev,
                       support=_best_support(ev), matched_with=shown,
                       reason=(f"Found {_cite(ev)}." if same else f"Your resume says '{shown}', which is the same skill as {q['name']}. Found {_cite(ev)}."))
        else:
            specific = [s for s in cand.have if key in catalog.implied(s)] if not key.startswith("custom:") else []
            general = [s for s in catalog.implied(key) if s in cand.have] if not key.startswith("custom:") else []
            related = [(s, catalog.shared_family(key, s)) for s in cand.have
                       if not key.startswith("custom:") and not s.startswith("custom:") and catalog.shared_family(key, s)]
            if specific:                                                           # 2. implied
                s = specific[0]
                res.update(status="matched", method="implied", confidence="medium", evidence=cand.have[s],
                           support=_best_support(cand.have[s]), matched_with=cand.display[s],
                           reason=f"You know {cand.display[s]}, which includes {q['name']} ({_cite(cand.have[s])}).")
            elif general:                                                          # 3. broader
                s = general[0]
                res.update(status="partial", method="broader", confidence="medium", evidence=cand.have[s],
                           support=_best_support(cand.have[s]), matched_with=cand.display[s],
                           reason=f"The job asks for {q['name']}. You have the broader skill {cand.display[s]}, but {q['name']} itself is not mentioned.")
            elif related:                                                          # 4. family
                s, family = related[0]
                res.update(status="partial", method="family", confidence="medium", evidence=cand.have[s],
                           support=_best_support(cand.have[s]), matched_with=cand.display[s],
                           reason=f"The job asks for {q['name']}. You have {cand.display[s]}, a similar skill ({family}), but not {q['name']}.")
            elif q["importance"] != "soft":
                pending.append((res, q))
        results.append(res)

    # --- semantic step: only for what the catalogue could not settle, and only to SUGGEST a partial match ---
    used_model = None
    if pending and cand.snippets:
        try:
            embed = embed_fn
            if embed is None:
                from app.matching import embedder
                embed, used_model = embedder.embed, embedder.model_name()
            phrases = [f"Experience with {q['name']}" for _, q in pending]
            vectors = embed(phrases + [text for _, text in cand.snippets])
            sims = np.asarray(vectors[:len(phrases)]) @ np.asarray(vectors[len(phrases):]).T
            for (res, q), row in zip(pending, sims):
                best = int(np.argmax(row))
                if row[best] >= threshold:
                    source, text = cand.snippets[best]
                    res.update(status="partial", method="semantic", confidence="low", similarity=round(float(row[best]), 2),
                               evidence=[{"source": source, "text": text[:160], "strength": "demonstrated"}], support="demonstrated",
                               reason=f"Something in your {source} looks related to {q['name']}, but it is not named. Please check it.")
        except Exception as exc:
            from app.matching.embedder import EmbedderUnavailable
            if not isinstance(exc, EmbedderUnavailable):
                raise
            warnings.append("Meaning-based matching is not available right now, so only exact, alias and related-skill matching was used.")

    for res in results:
        if res["status"] == "missing":
            res["reason"] = (f"{res['requirement']} was not found in the parts of your resume we could read. "
                             "This does not mean you lack it. Add it to your resume if you have it.")

    def count(importance):
        part = [r for r in results if r["importance"] == importance]
        return {"total": len(part), **{s: sum(1 for r in part if r["status"] == s) for s in ("matched", "partial", "missing")}}

    return {
        "engine_version": ENGINE_VERSION, "catalog_version": catalog.version,
        "embedding_model": used_model, "partial_threshold": threshold,
        "skills": results,
        "summary": {"required": count("required"), "preferred": count("preferred"), "soft": count("soft")},
        "not_used": {
            "resume_items_needing_review": _needs_review(resume.get("technical_skills")) + _needs_review(resume.get("soft_skills")),
            "job_items_needing_review": _needs_review(jd.get("required_skills")) + _needs_review(jd.get("preferred_skills")) + _needs_review(jd.get("soft_skills")),
        },
        "warnings": warnings,
    }
