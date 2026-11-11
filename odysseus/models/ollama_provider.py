"""Local fast-model integration via an Ollama-compatible HTTP server.

This talks only to ``base_url`` (default ``http://localhost:11434``), a
local-loopback address by default. No prompt data leaves the machine
through this provider: for a loopback ``base_url`` the provider's own HTTP
session ignores proxy environment variables and does not follow HTTP
redirects, so the request goes straight to the local server and stays
there. It never raises network/parse exceptions to the
caller -- everything is translated into ``ModelProviderError`` /
``ModelUnavailableError`` so the orchestrator can fall back cleanly.
"""

from __future__ import annotations

import requests

from odysseus.exceptions import ModelProviderError, ModelUnavailableError
from odysseus.models.base import GenerationRequest, GenerationResponse, ModelProvider
from odysseus.models.loopback import is_loopback_url


_MAX_SERVER_ERROR_CHARS = 200

# 4xx statuses that a later attempt can plausibly get past (request timeout,
# rate limit). Every other 4xx means the request itself is wrong -- typically
# a model that has not been pulled -- and repeating it cannot help.
_RETRYABLE_CLIENT_STATUSES = frozenset({408, 429})


def _is_permanent_client_error(response: object) -> bool:
    """True for a 4xx response that is pointless to retry. Never raises."""
    status = getattr(response, "status_code", None)
    if not isinstance(status, int) or isinstance(status, bool):
        return False  # unknown status: keep the previous retry behaviour
    return 400 <= status < 500 and status not in _RETRYABLE_CLIENT_STATUSES


def _server_error_message(response: object) -> str | None:
    """The ``error`` text from an Ollama error body, if there is one.

    Ollama answers a failed request (e.g. a model that has not been pulled)
    with a JSON body like ``{"error": "model 'x' not found"}``. Never raises.
    """
    try:
        data = response.json()  # type: ignore[attr-defined]
    except Exception:  # no response, no body, or not JSON
        return None
    message = data.get("error") if isinstance(data, dict) else None
    if not isinstance(message, str) or not message.strip():
        return None
    return " ".join(message.split())[:_MAX_SERVER_ERROR_CHARS]


def _redirect_note(exc: Exception) -> str:
    """Describe a refused redirect, naming its target when known. Never raises."""
    target = None
    try:
        target = exc.response.headers.get("Location")  # type: ignore[attr-defined]
    except Exception:  # no response attached, or no usable headers
        pass
    where = ""
    if isinstance(target, str) and target.strip():
        where = f" to {' '.join(target.split())[:_MAX_SERVER_ERROR_CHARS]!r}"
    return f"the server answered with a redirect{where}, which was not followed"


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
        if session is None:
            session = requests.Session()
            if is_loopback_url(self.base_url):
                # requests honours HTTP_PROXY/ALL_PROXY (and ~/.netrc) by
                # default and, unless NO_PROXY lists the host, would hand a
                # loopback request -- prompt included -- to that proxy. A
                # local server is never behind a proxy: connect directly.
                # A caller-supplied session is left exactly as given.
                session.trust_env = False
                # Likewise never follow a redirect: a 307/308 from whatever
                # is listening on the loopback port would re-send the POST
                # body (the prompt) to the redirect target, which can be any
                # host. With 0 allowed, requests raises TooManyRedirects
                # before sending anything to the target.
                session.max_redirects = 0
        self._session = session

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
        server_error: str | None = None
        attempts = 0
        for _ in range(self.max_retries + 1):
            attempts += 1
            try:
                resp = self._session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise ModelProviderError(
                        f"Ollama returned a non-object JSON body: {type(data).__name__}"
                    )
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
            except requests.exceptions.HTTPError as exc:
                # Keep the server's own explanation: the bare status line
                # ("404 Client Error") does not say *why* it failed.
                last_error = exc
                response = getattr(exc, "response", None)
                server_error = _server_error_message(response)
                if _is_permanent_client_error(response):
                    break  # e.g. 404 model not found: a retry cannot fix it
                continue
            except requests.exceptions.TooManyRedirects as exc:
                # Same answer on every attempt, so a retry cannot help.
                raise ModelProviderError(
                    f"Ollama request to {self.base_url} failed: {_redirect_note(exc)}"
                ) from exc
            except requests.exceptions.RequestException as exc:
                last_error = exc
                server_error = None
                continue
            except ValueError as exc:  # JSON decode error
                last_error = exc
                continue

        if isinstance(last_error, requests.exceptions.ConnectionError):
            raise ModelUnavailableError(
                f"Could not reach Ollama at {self.base_url}: {last_error}"
            ) from last_error
        reason = f" (server said: {server_error})" if server_error else ""
        raise ModelProviderError(
            f"Ollama request failed after {attempts} attempt(s): {last_error}{reason}"
        ) from last_error

    def health_check(self, timeout_seconds: float | None = None) -> tuple[bool, str]:
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=timeout)
            resp.raise_for_status()
        except requests.exceptions.TooManyRedirects as exc:
            return False, f"No Ollama server at {self.base_url}: {_redirect_note(exc)}"
        except requests.exceptions.RequestException as exc:
            return False, f"Ollama server unreachable at {self.base_url}: {exc}"
        try:
            # ``"models": null`` is what some Ollama versions send when nothing
            # is installed: that is an empty list, not an unreadable one.
            models = resp.json().get("models") or []
            if not isinstance(models, list):
                raise ValueError("'models' is not a list")
            names = {
                m["name"] for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)
            }
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
