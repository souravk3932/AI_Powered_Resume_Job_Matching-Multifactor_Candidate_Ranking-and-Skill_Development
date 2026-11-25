"""Role weight profiles: how much each factor counts for each kind of role.

The numbers live in data/roles.json, so they are visible, explainable and changeable without touching code.
"""
import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "roles.json"


@lru_cache(maxsize=1)
def load_roles() -> dict:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    factor_ids = [f["id"] for f in data["factors"]]
    for role_id, role in data["roles"].items():
        weights = role["weights"]
        if set(weights) != set(factor_ids):
            raise ValueError(f"role '{role_id}' must give a weight to every factor")
        if sum(weights.values()) != 100:
            raise ValueError(f"role '{role_id}' weights add up to {sum(weights.values())}, not 100")
    return data


def detect_role(job_title: str) -> str:
    """Pick the role profile that fits a job title. The student can always choose a different one."""
    title = f" {job_title.lower()} "
    best, best_len = "default", 0
    for role_id, role in load_roles()["roles"].items():
        for hint in role["title_hints"]:
            if hint in title and len(hint) > best_len:   # the most specific hint wins ("project manager" over "manager")
                best, best_len = role_id, len(hint)
    return best


def list_roles() -> list[dict]:
    roles = load_roles()
    return [{"id": rid, "name": r["name"], "weights": r["weights"]} for rid, r in roles["roles"].items()]
