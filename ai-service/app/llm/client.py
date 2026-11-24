"""One provider-neutral entry point for the LLM: generate_json().

The rest of the project calls generate_json() and never imports Groq directly.
To add another provider (Ollama, Gemini...), write one more small function like
_call_groq and register it in PROVIDERS.

The LLM only produces *claims* as JSON. It never decides a score.
"""
import json
import logging
from typing import Callable

import groq
from pydantic import BaseModel, ValidationError

from app.llm.config import LlmSettings, load_settings

log = logging.getLogger("llm")

# Groq models that can force the answer to match our schema ("strict" mode)
GROQ_STRICT_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "meta-models/muse-spark-open",
}


class LlmError(Exception):
    """An LLM problem with a message that is safe to show. `kind` says what happened."""

    def __init__(self, kind: str, user_message: str):
        super().__init__(user_message)
        self.kind = kind  # not_configured | auth | rate_limited | unreachable | bad_output | too_long | provider_error
        self.user_message = user_message


# ---------- provider adapter: Groq ----------
def _call_groq(settings: LlmSettings, system: str, user: str, schema_name: str, schema: dict,
               max_output_tokens: int) -> str:
    """Ask Groq and return the raw text. Translates Groq errors into LlmError."""
    client = groq.Groq(api_key=settings.api_key, timeout=settings.timeout_seconds, max_retries=2)

    if settings.model in GROQ_STRICT_MODELS:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
        system_text = system
    else:
        # Other models only guarantee valid JSON syntax, so we describe the shape in words
        response_format = {"type": "json_object"}
        system_text = f"{system}\n\nReturn ONLY JSON that matches this schema:\n{json.dumps(schema)}"

    extra: dict = {}
    if settings.model.startswith("openai/gpt-oss"):
        # These models "think" before answering. Low effort saves tokens, and we do not need the thoughts.
        extra = {"reasoning_effort": "low", "include_reasoning": False}

    try:
        reply = client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "system", "content": system_text}, {"role": "user", "content": user}],
            response_format=response_format,
            temperature=0,  # same input -> as-similar-as-possible output
            max_completion_tokens=max_output_tokens,  # Groq's default is only 1024: too small for a resume profile
            **extra,
        )
    except groq.AuthenticationError as exc:
        raise LlmError("auth", "Groq rejected the API key. Check GROQ_API_KEY in ai-service/.env.") from exc
    except groq.RateLimitError as exc:
        raise LlmError("rate_limited", "Groq says we are sending too many requests. Wait a minute and try again.") from exc
    except (groq.APIConnectionError, groq.APITimeoutError) as exc:
        raise LlmError("unreachable", "Could not reach Groq. Check your internet connection.") from exc
    except groq.BadRequestError as exc:
        # In best-effort mode Groq can reject output that does not match the schema; the caller may retry
        raise LlmError("bad_output", "The model's answer did not match the expected format.") from exc
    except groq.APIStatusError as exc:
        log.warning("groq error status=%s", exc.status_code)  # status only: never log keys or prompts
        raise LlmError("provider_error", f"Groq returned an error (status {exc.status_code}).") from exc

    choice = reply.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        # The model ran out of room: the JSON is cut off, and asking again with the same limit will not help
        raise LlmError("too_long", "The answer was cut off because the document is too long or detailed.")
    return choice.message.content or ""


PROVIDERS: dict[str, Callable[..., str]] = {"groq": _call_groq}


# ---------- public function ----------
def generate_json(
    system: str,
    user: str,
    schema: dict,
    schema_name: str,
    validate_with: type[BaseModel] | None = None,
    max_output_tokens: int = 2048,
) -> dict:
    """Ask the LLM for JSON and return it as a Python dict.

    schema       JSON Schema of the answer. For strict mode every property must be
                 in "required" and every object needs "additionalProperties": false.
    validate_with  optional Pydantic model; the answer must pass it, or we ask again.
    Raises LlmError when the LLM cannot give a valid answer.
    """
    settings = load_settings()
    if settings.provider not in PROVIDERS:
        raise LlmError("not_configured", f"LLM_PROVIDER '{settings.provider}' is not supported. Use: {', '.join(PROVIDERS)}.")
    if not settings.api_key:
        raise LlmError("not_configured", f"{settings.provider.upper()}_API_KEY is not set in ai-service/.env.")

    call = PROVIDERS[settings.provider]
    last_problem = "The model did not return valid JSON."

    for attempt in range(1, settings.max_attempts + 1):
        try:
            text = call(settings, system, user, schema_name, schema, max_output_tokens)
        except LlmError as err:
            if err.kind == "bad_output" and attempt < settings.max_attempts:
                last_problem = err.user_message
                continue  # worth asking again
            raise  # auth, rate limit, network... asking again will not help

        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("top level must be a JSON object")
            if validate_with is not None:
                validate_with.model_validate(data)  # checks types and required fields
            return data
        except (ValueError, ValidationError) as exc:
            last_problem = f"The model's answer was not valid: {type(exc).__name__}."
            log.info("llm attempt %d/%d gave invalid output", attempt, settings.max_attempts)

    raise LlmError("bad_output", last_problem)
