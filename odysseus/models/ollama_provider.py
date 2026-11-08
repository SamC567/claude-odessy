"""Local fast-model integration via an Ollama-compatible HTTP server.

This talks only to ``base_url`` (default ``http://localhost:11434``), a
local-loopback address by default. No prompt data leaves the machine
through this provider. It never raises network/parse exceptions to the
caller -- everything is translated into ``ModelProviderError`` /
``ModelUnavailableError`` so the orchestrator can fall back cleanly.
"""

from __future__ import annotations

import requests

from odysseus.exceptions import ModelProviderError, ModelUnavailableError
from odysseus.models.base import GenerationRequest, GenerationResponse, ModelProvider


class OllamaProvider(ModelProvider):
    """Provider for a local Ollama (or Ollama-API-compatible) server."""

    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "llama3",
        timeout_seconds: float = 10.0,
        max_retries: int = 1,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self._session = session or requests.Session()

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        payload: dict[str, object] = {
            "model": self.model_name,
            "prompt": request.prompt,
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                resp.raise_for_status()
                data = resp.json()
                text = data.get("response", "")
                if not isinstance(text, str) or not text:
                    raise ModelProviderError(
                        f"Ollama returned no usable 'response' field: {data!r}"
                    )
                return GenerationResponse(
                    text=text,
                    provider_name=self.name,
                    model_name=self.model_name,
                    is_live_model=True,
                    raw=data,
                )
            except requests.exceptions.ConnectionError as exc:
                last_error = exc
                break  # connection refused is not worth retrying
            except requests.exceptions.RequestException as exc:
                last_error = exc
                continue
            except ValueError as exc:  # JSON decode error
                last_error = exc
                continue

        if isinstance(last_error, requests.exceptions.ConnectionError):
            raise ModelUnavailableError(
                f"Could not reach Ollama at {self.base_url}: {last_error}"
            ) from last_error
        raise ModelProviderError(
            f"Ollama request failed after {self.max_retries + 1} attempt(s): {last_error}"
        ) from last_error

    def health_check(self) -> tuple[bool, str]:
        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=self.timeout_seconds)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            return False, f"Ollama server unreachable at {self.base_url}: {exc}"
        try:
            models = resp.json().get("models", [])
            names = {m.get("name", "") for m in models if isinstance(m, dict)}
        except (ValueError, AttributeError):
            # Reachable but unparseable /api/tags: don't claim the model is missing.
            return True, f"Ollama server reachable at {self.base_url} (model list unreadable)"
        wanted = self.model_name
        if wanted in names or (":" not in wanted and f"{wanted}:latest" in names):
            return True, f"Ollama server reachable at {self.base_url}; model {wanted!r} installed"
        return False, (
            f"Ollama server reachable at {self.base_url} but model {wanted!r} is not installed "
            f"(installed: {', '.join(sorted(n for n in names if n)) or 'none'})"
        )
