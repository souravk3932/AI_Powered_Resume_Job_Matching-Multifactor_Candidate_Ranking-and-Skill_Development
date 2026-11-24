"""Internal endpoint: match a resume profile against a job description profile (skills only)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.matching.matcher import match_skills
from app.security import require_service_key

router = APIRouter(prefix="/internal/match", dependencies=[Depends(require_service_key)])


class MatchRequest(BaseModel):
    resume: dict   # the stored resume profile data (skills, projects, experience... with statuses)
    jd: dict       # the stored job description profile data (required skills, preferred skills...)


# A normal (sync) function: runs in a worker thread, so loading the model does not freeze the service.
@router.post("/skills")
def match(body: MatchRequest):
    return match_skills(body.resume, body.jd)
