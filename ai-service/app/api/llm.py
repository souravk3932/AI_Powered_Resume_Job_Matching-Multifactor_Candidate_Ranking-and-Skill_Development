"""Internal LLM endpoints (same service-key protection as the other internal routes)."""
import time

from fastapi import APIRouter, Depends, HTTPException

from app.llm.client import LlmError, generate_json
from app.llm.config import load_settings
from app.security import require_service_key

router = APIRouter(prefix="/internal/llm", dependencies=[Depends(require_service_key)])

# Which HTTP status to answer with for each kind of LLM problem
STATUS_FOR = {
    "not_configured": 503,
    "auth": 502,
    "rate_limited": 429,
    "unreachable": 502,
    "bad_output": 502,
    "provider_error": 502,
}

PING_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


@router.get("/health")
def llm_health():
    """Send one tiny request to prove the key and model work. Costs almost nothing."""
    settings = load_settings()
    started = time.perf_counter()
    try:
        answer = generate_json(
            system="You reply only with JSON.",
            user='Set "ok" to true.',
            schema=PING_SCHEMA,
            schema_name="ping",
        )
    except LlmError as err:
        raise HTTPException(status_code=STATUS_FOR.get(err.kind, 502), detail=err.user_message) from err
    return {
        "provider": settings.provider,
        "model": settings.model,
        "ok": answer.get("ok") is True,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }
