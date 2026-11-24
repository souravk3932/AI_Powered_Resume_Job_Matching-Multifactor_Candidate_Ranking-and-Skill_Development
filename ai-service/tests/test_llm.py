"""Tests for the LLM wrapper. A fake Groq is used, so no internet, key or money is needed."""
from types import SimpleNamespace

import groq
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.llm.client import LlmError, generate_json
from app.main import app

SCHEMA = {
    "type": "object",
    "properties": {"skills": {"type": "array", "items": {"type": "string"}}},
    "required": ["skills"],
    "additionalProperties": False,
}


class Answer(BaseModel):
    skills: list[str]


class FakeGroq:
    """Stands in for groq.Groq. Each call returns/raises the next item in `outputs`."""
    outputs: list = []
    calls: list = []
    init_kwargs: dict = {}

    def __init__(self, **kwargs):
        FakeGroq.init_kwargs = kwargs
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        FakeGroq.calls.append(kwargs)
        item = FakeGroq.outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))])


def api_error(cls, status):
    request = httpx.Request("POST", "https://api.groq.com/x")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    FakeGroq.outputs, FakeGroq.calls, FakeGroq.init_kwargs = [], [], {}
    monkeypatch.setattr(groq, "Groq", FakeGroq)
    monkeypatch.setenv("AI_SERVICE_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake_key_for_tests")
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "2")


def ask(**kwargs):
    return generate_json("sys", "user text", SCHEMA, "skills_answer", **kwargs)


# ---------- configuration ----------
def test_missing_key_is_reported(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(LlmError) as err:
        ask()
    assert err.value.kind == "not_configured" and "GROQ_API_KEY" in err.value.user_message
    assert FakeGroq.calls == []  # we never even tried


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mystery")
    with pytest.raises(LlmError) as err:
        ask()
    assert err.value.kind == "not_configured"


# ---------- happy path ----------
def test_strict_model_sends_json_schema():
    FakeGroq.outputs = ['{"skills": ["Python"]}']
    assert ask() == {"skills": ["Python"]}
    sent = FakeGroq.calls[0]
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["temperature"] == 0
    assert FakeGroq.init_kwargs["api_key"] == "gsk_fake_key_for_tests"


def test_other_models_use_json_object_and_describe_schema(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "some/other-model")
    FakeGroq.outputs = ['{"skills": []}']
    ask()
    sent = FakeGroq.calls[0]
    assert sent["response_format"] == {"type": "json_object"}
    assert "skills" in sent["messages"][0]["content"]  # schema is explained in the prompt


def test_key_is_never_inside_the_prompt():
    FakeGroq.outputs = ['{"skills": []}']
    ask()
    assert "gsk_fake_key_for_tests" not in str(FakeGroq.calls[0]["messages"])


# ---------- validation and retry ----------
def test_invalid_json_then_valid_retries_once():
    FakeGroq.outputs = ["this is not json", '{"skills": ["SQL"]}']
    assert ask() == {"skills": ["SQL"]}
    assert len(FakeGroq.calls) == 2


def test_invalid_twice_gives_bad_output():
    FakeGroq.outputs = ["nope", "still nope"]
    with pytest.raises(LlmError) as err:
        ask()
    assert err.value.kind == "bad_output" and len(FakeGroq.calls) == 2


def test_pydantic_validation_triggers_retry():
    FakeGroq.outputs = ['{"skills": "not a list"}', '{"skills": ["React"]}']
    assert ask(validate_with=Answer) == {"skills": ["React"]}


def test_json_array_at_top_level_is_rejected():
    FakeGroq.outputs = ["[1, 2]", "[3]"]
    with pytest.raises(LlmError):
        ask()


# ---------- provider errors are translated ----------
@pytest.mark.parametrize(
    "error, kind",
    [
        (api_error(groq.AuthenticationError, 401), "auth"),
        (api_error(groq.RateLimitError, 429), "rate_limited"),
        (api_error(groq.APIStatusError, 500), "provider_error"),
        (groq.APIConnectionError(request=httpx.Request("POST", "https://x")), "unreachable"),
    ],
)
def test_provider_errors_are_translated_and_not_retried(error, kind):
    FakeGroq.outputs = [error, '{"skills": []}']
    with pytest.raises(LlmError) as err:
        ask()
    assert err.value.kind == kind
    assert len(FakeGroq.calls) == 1  # asking again would not help


def test_schema_rejection_is_retried():
    FakeGroq.outputs = [api_error(groq.BadRequestError, 400), '{"skills": ["Go"]}']
    assert ask() == {"skills": ["Go"]}


# ---------- health endpoint ----------
client = TestClient(app)
KEY = {"X-Service-Key": "test-key"}


def test_health_requires_service_key():
    assert client.get("/internal/llm/health").status_code == 401


def test_health_ok():
    FakeGroq.outputs = ['{"ok": true}']
    body = client.get("/internal/llm/health", headers=KEY).json()
    assert body["ok"] is True and body["provider"] == "groq" and "latency_ms" in body
    assert "gsk_" not in str(body)


def test_health_reports_missing_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    r = client.get("/internal/llm/health", headers=KEY)
    assert r.status_code == 503 and "GROQ_API_KEY" in r.json()["detail"]


def test_health_reports_bad_key():
    FakeGroq.outputs = [api_error(groq.AuthenticationError, 401)]
    r = client.get("/internal/llm/health", headers=KEY)
    assert r.status_code == 502 and "rejected" in r.json()["detail"]
