"""The OpenRouter client, exercised without ever reaching the network."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from lab_llm.config import LanguageModelSettings, load_settings
from lab_llm.openrouter import OpenRouterModel

from lab_domain.errors import LanguageModelError, StateStoreError
from lab_domain.language import LanguageModel, Message, Role

MESSAGES = [
    Message(role=Role.SYSTEM, content="You summarise experiments."),
    Message(role=Role.USER, content="RUN-000001 completed."),
]

ANSWER = {
    "model": "vendor/model-served",
    "choices": [
        {"message": {"content": "  The run completed.  "}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 120, "completion_tokens": 42},
}


@dataclass
class FakeTransport:
    status: int = 200
    payload: dict = field(default_factory=lambda: ANSWER)
    calls: list[dict] = field(default_factory=list)

    def __call__(
        self, url: str, *, headers: dict[str, str], body: bytes, timeout: int
    ) -> tuple[int, bytes]:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "body": json.loads(body),
                "timeout": timeout,
            }
        )
        return self.status, json.dumps(self.payload).encode("utf-8")


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> LanguageModelSettings:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
    return LanguageModelSettings(model="vendor/model", max_tokens=500, temperature=0.0)


def test_satisfies_the_language_model_port(
    configured: LanguageModelSettings,
) -> None:
    model: LanguageModel = OpenRouterModel(configured, transport=FakeTransport())
    assert model.provider == "openrouter"
    assert model.model == "vendor/model"
    assert model.available() is True


def test_unavailable_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    model = OpenRouterModel(LanguageModelSettings(model="vendor/model"))
    assert model.available() is False


def test_unavailable_without_a_model(configured: LanguageModelSettings) -> None:
    model = OpenRouterModel(configured.model_copy(update={"model": None}))
    assert model.available() is False


def test_the_request_carries_the_key_and_the_settings(
    configured: LanguageModelSettings,
) -> None:
    transport = FakeTransport()
    OpenRouterModel(configured, transport=transport).complete(MESSAGES)

    call = transport.calls[0]
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-test-key"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["timeout"] == configured.timeout_seconds
    assert call["body"]["model"] == "vendor/model"
    assert call["body"]["max_tokens"] == 500
    assert call["body"]["temperature"] == 0.0
    assert call["body"]["messages"] == [
        {"role": "system", "content": MESSAGES[0].content},
        {"role": "user", "content": MESSAGES[1].content},
    ]


def test_the_completion_records_what_answered(
    configured: LanguageModelSettings,
) -> None:
    completion = OpenRouterModel(configured, transport=FakeTransport()).complete(
        MESSAGES
    )
    assert completion.text == "The run completed."
    assert completion.provider == "openrouter"
    # The model that served the request, which routing may change.
    assert completion.model == "vendor/model-served"
    assert completion.finish_reason == "stop"
    assert completion.prompt_tokens == 120
    assert completion.completion_tokens == 42


def test_a_custom_base_url_is_honoured(configured: LanguageModelSettings) -> None:
    transport = FakeTransport()
    settings = configured.model_copy(update={"base_url": "https://proxy.lab/v1/"})
    OpenRouterModel(settings, transport=transport).complete(MESSAGES)
    assert transport.calls[0]["url"] == "https://proxy.lab/v1/chat/completions"


def test_a_missing_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    model = OpenRouterModel(
        LanguageModelSettings(model="vendor/model"), transport=FakeTransport()
    )
    with pytest.raises(LanguageModelError, match="OPENROUTER_API_KEY"):
        model.complete(MESSAGES)


def test_a_missing_model_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
    model = OpenRouterModel(LanguageModelSettings(), transport=FakeTransport())
    with pytest.raises(LanguageModelError, match="No model chosen"):
        model.complete(MESSAGES)


def test_a_refusal_is_reported_with_the_providers_reason(
    configured: LanguageModelSettings,
) -> None:
    transport = FakeTransport(
        status=401, payload={"error": {"message": "No auth credentials found"}}
    )
    with pytest.raises(LanguageModelError, match="No auth credentials found"):
        OpenRouterModel(configured, transport=transport).complete(MESSAGES)


@pytest.mark.parametrize(
    "payload", [{"choices": []}, {"choices": [{"message": {"content": "  "}}]}]
)
def test_an_empty_answer_is_reported(
    configured: LanguageModelSettings, payload: dict
) -> None:
    transport = FakeTransport(payload=payload)
    with pytest.raises(LanguageModelError, match="returned"):
        OpenRouterModel(configured, transport=transport).complete(MESSAGES)


def test_an_unreadable_answer_is_reported(configured: LanguageModelSettings) -> None:
    def broken(
        url: str, *, headers: dict, body: bytes, timeout: int
    ) -> tuple[int, bytes]:
        return 200, b"<html>gateway error</html>"

    with pytest.raises(LanguageModelError, match="unreadable body"):
        OpenRouterModel(configured, transport=broken).complete(MESSAGES)


def test_settings_default_to_no_model(tmp_path: Path) -> None:
    """A laboratory chooses its model; the platform never guesses one."""
    settings = load_settings(tmp_path)
    assert settings.model is None
    assert settings.provider == "openrouter"
    assert settings.temperature == 0.0


def test_settings_are_read_from_lab_home(tmp_path: Path) -> None:
    (tmp_path / "llm.json").write_text(
        json.dumps({"model": "vendor/from-file", "max_tokens": 1200})
    )
    settings = load_settings(tmp_path)
    assert settings.model == "vendor/from-file"
    assert settings.max_tokens == 1200


def test_the_environment_overrides_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "llm.json").write_text(json.dumps({"model": "vendor/from-file"}))
    monkeypatch.setenv("LAB_LLM_MODEL", "vendor/from-env")
    assert load_settings(tmp_path).model == "vendor/from-env"


def test_unusable_settings_are_reported(tmp_path: Path) -> None:
    (tmp_path / "llm.json").write_text("{not json")
    with pytest.raises(StateStoreError, match="unusable"):
        load_settings(tmp_path)


def test_an_unknown_setting_is_refused(tmp_path: Path) -> None:
    (tmp_path / "llm.json").write_text(json.dumps({"modell": "typo"}))
    with pytest.raises(StateStoreError, match="unusable"):
        load_settings(tmp_path)


def test_the_key_is_never_read_from_the_settings_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Credentials come from the environment only (AGENTS.md section 15.1)."""
    (tmp_path / "llm.json").write_text(json.dumps({"api_key": "sk-leaked"}))
    with pytest.raises(StateStoreError):
        load_settings(tmp_path)
