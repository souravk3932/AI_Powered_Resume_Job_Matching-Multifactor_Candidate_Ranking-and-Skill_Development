"""Internal endpoints for the scoring engine."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.scoring.engine import evaluate
from app.scoring.roles import list_roles
from app.security import require_service_key

router = APIRouter(prefix="/internal/score", dependencies=[Depends(require_service_key)])


class ScoreRequest(BaseModel):
    resume: dict                    # stored resume profile data
    jd: dict                        # stored job description profile data
    match: dict                     # the Phase 6 skill match result
    role_profile: str | None = None  # None = pick from the job title
    job_title: str = ""


@router.get("/roles")
def roles():
    """The role profiles and their weights, so the screen can offer a choice."""
    return {"roles": list_roles()}


@router.post("/evaluate")
def score(body: ScoreRequest):
    try:
        return evaluate(body.resume, body.jd, body.match, role_id=body.role_profile, job_title=body.job_title)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
