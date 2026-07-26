"""OpenRouter implementation of the language-model port.

OpenRouter speaks the OpenAI chat-completions shape, which is one POST, so this
uses the standard library rather than adding an HTTP dependency. The transport
is injected, so tests never touch the network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Protocol

from lab_domain.errors import LanguageModelError
from lab_domain.language import Completion, Message
from lab_llm.config import API_KEY_VARIABLE, LanguageModelSettings, api_key

COMPLETIONS_PATH = "/chat/completions"
PROVIDER = "openrouter"
# OpenRouter asks callers to identify themselves; these are attribution
# headers, not credentials.
REFERER = "https://github.com/lab-platform"
TITLE = "lab-platform"


class Transport(Protocol):
    def __call__(
        self, url: str, *, headers: dict[str, str], body: bytes, timeout: int
    ) -> tuple[int, bytes]: ...


def urllib_transport(
    url: str, *, headers: dict[str, str], body: bytes, timeout: int
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()
    except urllib.error.URLError as exc:
        raise LanguageModelError(
            f"Cannot reach the model provider: {exc.reason}."
        ) from exc
    except TimeoutError as exc:
        raise LanguageModelError(
            f"The model provider did not answer within {timeout}s."
        ) from exc


class OpenRouterModel:
    """``LanguageModel`` calling OpenRouter's chat-completions endpoint."""

    provider = PROVIDER

    def __init__(
        self,
        settings: LanguageModelSettings,
        transport: Transport | None = None,
    ) -> None:
        self._settings = settings
        # Resolved here rather than as a default argument, so the module-level
        # transport can be replaced: a default binds at import time and would
        # leave tests talking to the real provider.
        self._transport = transport if transport is not None else urllib_transport

    @property
    def model(self) -> str:
        return self._settings.model or "unset"

    def available(self) -> bool:
        return self._settings.configured

    def complete(self, messages: Sequence[Message]) -> Completion:
        settings = self._settings
        key = api_key()
        if not key:
            raise LanguageModelError(
                f"No model credential: set {API_KEY_VARIABLE} in the environment."
            )
        if not settings.model:
            raise LanguageModelError(
                "No model chosen. Set LAB_LLM_MODEL, or `model` in "
                "$LAB_HOME/llm.json, to a model your provider offers."
            )

        payload = {
            "model": settings.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in messages
            ],
            "max_tokens": settings.max_tokens,
            "temperature": settings.temperature,
        }
        status, body = self._transport(
            settings.base_url.rstrip("/") + COMPLETIONS_PATH,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": REFERER,
                "X-Title": TITLE,
            },
            body=json.dumps(payload).encode("utf-8"),
            timeout=settings.timeout_seconds,
        )
        return _read_completion(status, body, settings.model)


def _read_completion(status: int, body: bytes, model: str) -> Completion:
    try:
        document = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise LanguageModelError(
            f"The model provider answered with {status} and an unreadable body."
        ) from exc

    if status != 200:
        detail = document.get("error", {})
        message = detail.get("message") if isinstance(detail, dict) else None
        raise LanguageModelError(
            f"The model provider refused the request ({status}): "
            f"{message or 'no reason given'}."
        )

    choices = document.get("choices") or []
    if not choices:
        raise LanguageModelError("The model returned no choices.")
    first = choices[0]
    text = (first.get("message") or {}).get("content") or ""
    if not text.strip():
        raise LanguageModelError("The model returned an empty completion.")

    usage = document.get("usage") or {}
    return Completion(
        text=text.strip(),
        provider=PROVIDER,
        # The provider reports which model actually served the request, which
        # can differ from the one asked for when routing.
        model=str(document.get("model") or model),
        finish_reason=first.get("finish_reason"),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )
