"""The scoring engine: combines the ten factor scores into one explainable result.

    Overall = sum( factor score x effective weight )

Factors with real evidence are "evaluated". A factor with nothing to judge is NOT scored as zero:
  not_provided   the job asks for it but the resume gave no information (flagged, left out of the sum)
  not_applicable the job does not ask and the resume has nothing (neutral, left out)
  not_available  needs a skill assessment the student has not taken yet (left out)
The weights of the factors that remain are scaled up so they again add to 100 ("effective weight").
Because that can flatter a resume with little information, the result also reports
  coverage     how much of the applicable weight was actually evaluated, and
  lower_bound  the score if the "not provided" factors were counted as zero.

This is a decision-support tool. The number is a measure of how well the written evidence fits the
job description. It is NOT a probability of being hired.
"""
from datetime import date

from app.scoring.factors import FACTORS, Context
from app.scoring.roles import detect_role, load_roles

ENGINE_VERSION = "score-v1"

NOT_USED = ["name", "contact details", "age, gender, religion or nationality", "photo",
            "college name or reputation", "grades (CGPA, percentages)", "the amount of any funding"]


def evaluate(resume: dict, jd: dict, match: dict, role_id: str | None = None, job_title: str = "",
             today: date | None = None) -> dict:
    roles = load_roles()
    if role_id is not None and role_id not in roles["roles"]:
        raise ValueError(f"unknown role profile: {role_id}")
    chosen = role_id or detect_role(job_title)
    role = roles["roles"][chosen]
    ctx = Context(resume=resume, jd=jd, match=match, role_keywords=role["keywords"], today=today or date.today())

    factors = []
    for spec in roles["factors"]:
        result = FACTORS[spec["id"]](ctx)
        result.update(name=spec["name"], kind=spec["kind"], weight=role["weights"][spec["id"]])
        factors.append(result)

    evaluated = [f for f in factors if f["status"] == "evaluated"]
    missing_info = [f for f in factors if f["status"] == "not_provided"]
    w_eval = sum(f["weight"] for f in evaluated)
    w_applicable = w_eval + sum(f["weight"] for f in missing_info)

    overall = lower = None
    if w_eval:
        total = sum(f["score"] * f["weight"] for f in evaluated)
        overall = total / w_eval
        lower = total / w_applicable
    coverage = (w_eval / w_applicable) if w_applicable else 0.0

    calculation = []
    for f in factors:
        if f["status"] == "evaluated":
            f["effective_weight"] = round(100 * f["weight"] / w_eval, 1)
            f["contribution"] = round(f["score"] * f["weight"] / w_eval, 1)
            calculation.append(f"{f['name']}: {f['score']:.1f} x {f['effective_weight']:.1f}% = {f['contribution']:.1f}")
        else:
            f["effective_weight"] = f["contribution"] = None

    # Each piece of evidence may be spent by only ONE factor (leadership roles, grants and awards each have one home)
    seen: dict[str, str] = {}
    warnings = []
    for f in factors:
        for key in f["used"]:
            if key in seen and seen[key] != f["id"]:
                warnings.append(f"'{key}' was used by both {seen[key]} and {f['id']}.")
            seen[key] = f["id"]

    level = "high" if coverage >= 0.85 else "medium" if coverage >= 0.6 else "low"
    return {
        "engine_version": ENGINE_VERSION,
        "roles_version": roles["version"],
        "role_profile": {"id": chosen, "name": role["name"], "weights": role["weights"],
                         "auto_detected": role_id is None},
        "factors": factors,
        "overall": None if overall is None else round(overall, 1),
        "lower_bound": None if lower is None else round(lower, 1),
        "coverage": round(coverage, 2),
        "evidence_level": level,
        "formula": "Overall = sum of (factor score x effective weight). Effective weights add up to 100% over the factors that were evaluated.",
        "calculation": calculation,
        "not_provided": [f["name"] for f in missing_info],
        "not_used": NOT_USED,
        "warnings": warnings,
        "disclaimer": "This measures how well the written evidence fits this job description. It is not a prediction of being hired.",
    }
