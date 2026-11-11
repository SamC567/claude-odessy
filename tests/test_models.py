from __future__ import annotations

import pytest
import requests

from odysseus.config import ModelProviderConfig
from odysseus.exceptions import ModelProviderError, ModelUnavailableError
from odysseus.models.base import GenerationRequest
from odysseus.models.echo_provider import EchoProvider
from odysseus.models.ollama_provider import OllamaProvider
from odysseus.models.registry import build_provider


def test_echo_provider_never_fails_and_is_labelled():
    provider = EchoProvider()
    response = provider.generate(GenerationRequest(prompt="hello there"))
    assert response.is_live_model is False
    assert "echo-fallback" in response.text
    assert "hello there" in response.text
    healthy, _ = provider.health_check()
    assert healthy is True


def test_echo_provider_truncates_long_prompts():
    provider = EchoProvider()
    response = provider.generate(GenerationRequest(prompt="x" * 500))
    assert "…" in response.text


class _FakeSession:
    """Minimal stand-in for requests.Session used in provider tests."""

    def __init__(self, post_result=None, post_exc=None, get_result=None, get_exc=None):
        self._post_result = post_result
        self._post_exc = post_exc
        self._get_result = get_result
        self._get_exc = get_exc
        self.posted_payloads = []

    def post(self, url, json=None, timeout=None):
        self.posted_payloads.append(json)
        if self._post_exc:
            raise self._post_exc
        return self._post_result

    def get(self, url, timeout=None):
        if self._get_exc:
            raise self._get_exc
        return self._get_result


class _FakeResponse:
    def __init__(self, json_data, status_ok=True):
        self._json_data = json_data
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.exceptions.HTTPError("bad status")

    def json(self):
        return self._json_data


def test_ollama_provider_success():
    session = _FakeSession(post_result=_FakeResponse({"response": "hi there"}))
    provider = OllamaProvider(session=session)
    response = provider.generate(GenerationRequest(prompt="hello"))
    assert response.text == "hi there"
    assert response.is_live_model is True
    assert session.posted_payloads[0]["prompt"] == "hello"


def test_ollama_provider_connection_refused_raises_unavailable():
    session = _FakeSession(post_exc=requests.exceptions.ConnectionError("refused"))
    provider = OllamaProvider(session=session, max_retries=2)
    with pytest.raises(ModelUnavailableError):
        provider.generate(GenerationRequest(prompt="hello"))


def test_ollama_provider_retries_then_raises_generic_error():
    session = _FakeSession(post_exc=requests.exceptions.Timeout("slow"))
    provider = OllamaProvider(session=session, max_retries=2)
    with pytest.raises(ModelProviderError):
        provider.generate(GenerationRequest(prompt="hello"))
    assert len(session.posted_payloads) == 3  # 1 initial + 2 retries


def test_ollama_provider_empty_response_raises():
    session = _FakeSession(post_result=_FakeResponse({"response": ""}))
    provider = OllamaProvider(session=session, max_retries=0)
    with pytest.raises(ModelProviderError):
        provider.generate(GenerationRequest(prompt="hello"))


def test_ollama_provider_non_object_json_raises_provider_error():
    session = _FakeSession(post_result=_FakeResponse(["not", "an", "object"]))
    provider = OllamaProvider(session=session, max_retries=0)
    with pytest.raises(ModelProviderError):
        provider.generate(GenerationRequest(prompt="hello"))


class _HttpErrorResponse:
    """A response whose status is an error, with an Ollama-style JSON body."""

    def __init__(self, body, status_line="404 Client Error: Not Found", status_code=404):
        self._body = body
        self._status_line = status_line
        self.status_code = status_code

    def raise_for_status(self):
        raise requests.exceptions.HTTPError(self._status_line, response=self)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def test_ollama_provider_error_includes_server_explanation():
    # A model that has not been pulled: the status line alone does not say why.
    session = _FakeSession(
        post_result=_HttpErrorResponse({"error": "model 'llama3' not found, try pulling it first"})
    )
    provider = OllamaProvider(session=session, max_retries=0)
    with pytest.raises(ModelProviderError) as excinfo:
        provider.generate(GenerationRequest(prompt="hello"))
    message = str(excinfo.value)
    assert "404 Client Error" in message
    assert "server said: model 'llama3' not found, try pulling it first" in message


@pytest.mark.parametrize(
    "body", [ValueError("not json"), ["error"], {"error": None}, {"error": "   "}, {}]
)
def test_ollama_provider_error_tolerates_unusable_error_body(body):
    session = _FakeSession(post_result=_HttpErrorResponse(body))
    provider = OllamaProvider(session=session, max_retries=0)
    with pytest.raises(ModelProviderError) as excinfo:
        provider.generate(GenerationRequest(prompt="hello"))
    assert "404 Client Error" in str(excinfo.value)
    assert "server said" not in str(excinfo.value)


def test_ollama_provider_error_truncates_long_server_explanation():
    session = _FakeSession(post_result=_HttpErrorResponse({"error": "x" * 5000}))
    provider = OllamaProvider(session=session, max_retries=0)
    with pytest.raises(ModelProviderError) as excinfo:
        provider.generate(GenerationRequest(prompt="hello"))
    assert len(str(excinfo.value)) < 400


def test_ollama_provider_does_not_retry_a_permanent_client_error():
    # A missing model answers 404 every time: retrying only delays the fallback.
    session = _FakeSession(post_result=_HttpErrorResponse({"error": "model 'llama3' not found"}))
    provider = OllamaProvider(session=session, max_retries=3)
    with pytest.raises(ModelProviderError) as excinfo:
        provider.generate(GenerationRequest(prompt="hello"))
    assert len(session.posted_payloads) == 1
    assert "after 1 attempt(s)" in str(excinfo.value)
    assert "server said: model 'llama3' not found" in str(excinfo.value)


@pytest.mark.parametrize(
    "status_line, status_code",
    [
        ("500 Server Error: Internal Server Error", 500),
        ("503 Server Error: Service Unavailable", 503),
        ("429 Client Error: Too Many Requests", 429),
        ("408 Client Error: Request Timeout", 408),
        ("bad status", None),  # status unknown: keep retrying as before
    ],
)
def test_ollama_provider_still_retries_transient_http_errors(status_line, status_code):
    session = _FakeSession(
        post_result=_HttpErrorResponse({}, status_line=status_line, status_code=status_code)
    )
    provider = OllamaProvider(session=session, max_retries=2)
    with pytest.raises(ModelProviderError) as excinfo:
        provider.generate(GenerationRequest(prompt="hello"))
    assert len(session.posted_payloads) == 3  # 1 initial + 2 retries
    assert "after 3 attempt(s)" in str(excinfo.value)


def test_ollama_health_check_reports_unreachable():
    session = _FakeSession(get_exc=requests.exceptions.ConnectionError("refused"))
    provider = OllamaProvider(session=session)
    healthy, detail = provider.health_check()
    assert healthy is False
    assert "unreachable" in detail


def test_registry_builds_echo_by_default():
    provider = build_provider(ModelProviderConfig())
    assert isinstance(provider, EchoProvider)


def test_registry_builds_ollama():
    provider = build_provider(ModelProviderConfig(provider="ollama"))
    assert isinstance(provider, OllamaProvider)


def test_registry_falls_back_to_echo_for_unknown_provider():
    provider = build_provider(ModelProviderConfig(provider="some-future-cloud-model"))
    assert isinstance(provider, EchoProvider)


def test_non_loopback_base_url_blocked_unless_external_allowed():
    cfg = ModelProviderConfig(provider="ollama", base_url="http://models.example.com:11434")
    assert build_provider(cfg).name == "echo"
    assert build_provider(cfg, allow_external=True).name == "ollama"
    for local in ("http://localhost:1", "http://127.0.0.1:1", "http://[::1]:1"):
        assert build_provider(ModelProviderConfig(provider="ollama", base_url=local)).name == "ollama"


def test_ollama_health_check_detects_missing_model():
    tags = _FakeResponse({"models": [{"name": "mistral:latest"}]})
    provider = OllamaProvider(model_name="llama3", session=_FakeSession(get_result=tags))
    healthy, detail = provider.health_check()
    assert healthy is False
    assert "llama3" in detail and "not installed" in detail and "mistral:latest" in detail

    ok = _FakeResponse({"models": [{"name": "llama3:latest"}]})
    assert OllamaProvider(model_name="llama3", session=_FakeSession(get_result=ok)).health_check()[0]
    exact = _FakeResponse({"models": [{"name": "llama3:8b"}]})
    assert OllamaProvider(model_name="llama3:8b", session=_FakeSession(get_result=exact)).health_check()[0]


def test_ollama_health_check_timeout_override():
    seen = []

    class _Spy(_FakeSession):
        def get(self, url, timeout=None):
            seen.append(timeout)
            return super().get(url, timeout=timeout)

    tags = _FakeResponse({"models": [{"name": "llama3:latest"}]})
    provider = OllamaProvider(model_name="llama3", timeout_seconds=10.0, session=_Spy(get_result=tags))
    provider.health_check()
    provider.health_check(timeout_seconds=1.5)
    assert seen == [10.0, 1.5]


def test_ollama_health_check_handles_null_or_malformed_model_list():
    # A server with nothing installed may answer {"models": null}; that must be
    # "model not installed", not an exception escaping health_check.
    empty = _FakeResponse({"models": None})
    healthy, detail = OllamaProvider(
        model_name="llama3", session=_FakeSession(get_result=empty)
    ).health_check()
    assert not healthy
    assert "not installed" in detail and "installed: none" in detail

    # A models value that is not a list is unreadable, never a crash.
    for bad in (7, "llama3", {"name": "llama3"}):
        healthy, detail = OllamaProvider(
            model_name="llama3", session=_FakeSession(get_result=_FakeResponse({"models": bad}))
        ).health_check()
        assert healthy and "model list unreadable" in detail

    # Entries with a non-string name are skipped rather than crashing.
    odd = _FakeResponse({"models": [{"name": None}, {"name": ["x"]}, {"name": "llama3:latest"}]})
    assert OllamaProvider(model_name="llama3", session=_FakeSession(get_result=odd)).health_check()[0]


def _serve(handler_cls):
    """Start a loopback-only HTTP server on a free port; returns (server, url)."""
    import threading
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_ollama_loopback_requests_bypass_environment_proxy(monkeypatch):
    """A proxy set in the environment must never receive a loopback prompt."""
    import json
    from http.server import BaseHTTPRequestHandler

    proxied: list[str] = []

    class _Proxy(BaseHTTPRequestHandler):
        def _record(self):
            length = int(self.headers.get("Content-Length") or 0)
            proxied.append(self.path + " " + self.rfile.read(length).decode("utf-8", "replace"))
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = _record

        def log_message(self, *args):
            pass

    class _Ollama(BaseHTTPRequestHandler):
        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self._send({"response": "direct answer"})

        def do_GET(self):
            self._send({"models": [{"name": "llama3:latest"}]})

        def log_message(self, *args):
            pass

    proxy, proxy_url = _serve(_Proxy)
    ollama, ollama_url = _serve(_Ollama)
    try:
        for var in ("NO_PROXY", "no_proxy", "HTTPS_PROXY", "https_proxy"):
            monkeypatch.delenv(var, raising=False)
        for var in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(var, proxy_url)

        provider = OllamaProvider(base_url=ollama_url, max_retries=0, timeout_seconds=5)
        response = provider.generate(GenerationRequest(prompt="private prompt"))
        healthy, _ = provider.health_check()
    finally:
        proxy.shutdown()
        proxy.server_close()
        ollama.shutdown()
        ollama.server_close()

    assert response.text == "direct answer"
    assert healthy is True
    assert proxied == []


def test_ollama_non_loopback_session_keeps_environment_proxy_settings():
    # An explicitly allowed remote server may legitimately sit behind a proxy.
    assert OllamaProvider(base_url="http://localhost:11434")._session.trust_env is False
    assert OllamaProvider(base_url="http://[::1]:11434")._session.trust_env is False
    assert OllamaProvider(base_url="http://models.example:11434")._session.trust_env is True


def test_ollama_leaves_a_caller_supplied_session_untouched():
    session = requests.Session()
    OllamaProvider(base_url="http://localhost:11434", session=session)
    assert session.trust_env is True


def test_ollama_loopback_requests_do_not_follow_redirects():
    # A 307 re-sends the POST body: whatever answers on the loopback port
    # must not be able to forward the prompt to another host.
    import json
    from http.server import BaseHTTPRequestHandler

    received = []

    class _Target(BaseHTTPRequestHandler):
        def _record(self):
            length = int(self.headers.get("Content-Length") or 0)
            received.append(self.path + " " + self.rfile.read(length).decode("utf-8", "replace"))
            data = json.dumps({"response": "answer from elsewhere",
                               "models": [{"name": "llama3:latest"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = _record

        def log_message(self, *args):
            pass

    target, target_url = _serve(_Target)
    asked = []

    class _Redirector(BaseHTTPRequestHandler):
        def _redirect(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            asked.append(self.path)
            self.send_response(307)
            self.send_header("Location", target_url + self.path)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = _redirect

        def log_message(self, *args):
            pass

    redirector, redirector_url = _serve(_Redirector)
    try:
        provider = OllamaProvider(base_url=redirector_url, max_retries=2, timeout_seconds=5)
        with pytest.raises(ModelProviderError) as excinfo:
            provider.generate(GenerationRequest(prompt="private prompt"))
        healthy, detail = provider.health_check()
    finally:
        redirector.shutdown()
        redirector.server_close()
        target.shutdown()
        target.server_close()

    assert received == []  # nothing, prompt included, reached the redirect target
    assert "redirect" in str(excinfo.value) and target_url in str(excinfo.value)
    assert not isinstance(excinfo.value, ModelUnavailableError)
    assert asked == ["/api/generate", "/api/tags"]  # one attempt each: not retried
    assert healthy is False
    assert "redirect" in detail and target_url in detail


def test_ollama_redirect_policy_applies_only_to_its_own_loopback_session():
    default_limit = requests.Session().max_redirects
    assert OllamaProvider(base_url="http://127.0.0.1:11434")._session.max_redirects == 0
    # An explicitly allowed remote server keeps the requests default...
    assert OllamaProvider(base_url="http://models.example:11434")._session.max_redirects == default_limit
    # ...and a caller-supplied session is left exactly as given.
    session = requests.Session()
    OllamaProvider(base_url="http://localhost:11434", session=session)
    assert session.max_redirects == default_limit
