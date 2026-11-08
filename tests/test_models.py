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
