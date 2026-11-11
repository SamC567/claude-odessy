from __future__ import annotations

import pytest

from odysseus.config import IdentityConfig
from odysseus.core.identity import JarvisIdentity
from odysseus.core.orchestrator import Orchestrator
from odysseus.exceptions import ModelProviderError, ModelUnavailableError
from odysseus.memory.models import MemoryStatus
from odysseus.models.base import GenerationRequest, GenerationResponse, ModelProvider
from odysseus.models.echo_provider import EchoProvider


class _AlwaysFailsProvider(ModelProvider):
    name = "always-fails"

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise ModelUnavailableError("simulated outage")

    def health_check(self):
        return False, "simulated outage"


class _CannedProvider(ModelProvider):
    name = "canned"

    def __init__(self, text: str = "a canned answer"):
        self.text = text
        self.last_request: GenerationRequest | None = None

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.last_request = request
        return GenerationResponse(text=self.text, provider_name=self.name, model_name="canned-v1")

    def health_check(self):
        return True, "always healthy"


@pytest.fixture
def identity() -> JarvisIdentity:
    return JarvisIdentity.from_config(IdentityConfig())


def test_respond_uses_primary_provider(identity, memory_store):
    provider = _CannedProvider()
    orchestrator = Orchestrator(identity=identity, provider=provider, memory=memory_store)
    result = orchestrator.respond("hello")
    assert result.text == "a canned answer"
    assert result.provider_used == "canned"
    assert result.degraded is False


def test_respond_falls_back_when_primary_fails(identity, memory_store):
    orchestrator = Orchestrator(
        identity=identity,
        provider=_AlwaysFailsProvider(),
        memory=memory_store,
        fallback_provider=EchoProvider(),
    )
    result = orchestrator.respond("hello")
    assert result.degraded is True
    assert result.provider_used == "echo"
    assert result.is_live_model is False
    assert "simulated outage" in result.degraded_reason


def test_respond_includes_approved_memory_as_context(identity, memory_store):
    entry = orchestrator_remember_and_approve(identity, memory_store, "The vault code is 1234")
    provider = _CannedProvider()
    orchestrator = Orchestrator(identity=identity, provider=provider, memory=memory_store)
    result = orchestrator.respond("what is the vault code")
    assert "vault code" in " ".join(result.memory_context)
    assert result.memory_sources == ((entry.id, entry.source),)
    assert provider.last_request.system_prompt is not None
    assert "vault code" in provider.last_request.system_prompt


def test_respond_excludes_pending_memory_from_context(identity, memory_store):
    orchestrator = Orchestrator(identity=identity, provider=_CannedProvider(), memory=memory_store)
    orchestrator.remember("The secret is unreviewed", source="user", confidence=0.9)
    result = orchestrator.respond("tell me the secret")
    assert result.memory_context == ()


def test_remember_always_lands_pending(identity, memory_store):
    orchestrator = Orchestrator(identity=identity, provider=_CannedProvider(), memory=memory_store)
    entry = orchestrator.remember("a new fact", source="user", confidence=0.99)
    assert entry.status == MemoryStatus.PENDING


def test_respond_rejects_empty_prompt(identity, memory_store):
    orchestrator = Orchestrator(identity=identity, provider=_CannedProvider(), memory=memory_store)
    with pytest.raises(ValueError):
        orchestrator.respond("   ")


def orchestrator_remember_and_approve(identity, memory_store, content: str):
    orchestrator = Orchestrator(identity=identity, provider=_CannedProvider(), memory=memory_store)
    entry = orchestrator.remember(content, source="user", confidence=0.9)
    memory_store.approve(entry.id, reviewer="test")
    return entry


def test_respond_degrades_when_memory_query_fails(identity, memory_store):
    from odysseus.exceptions import MemoryError_

    def boom(*args, **kwargs):
        raise MemoryError_("disk I/O error")

    memory_store.query = boom
    result = Orchestrator(identity, _CannedProvider(), memory_store).respond("hello")
    assert result.text == "a canned answer"
    assert result.memory_context == ()
    assert result.degraded is True
    assert "memory unavailable" in result.degraded_reason


def test_used_fallback_distinguishes_provider_fallback_from_memory_degradation(
    identity, memory_store
):
    from odysseus.exceptions import MemoryError_

    fell_back = Orchestrator(identity, _AlwaysFailsProvider(), memory_store).respond("hello")
    assert fell_back.degraded is True
    assert fell_back.used_fallback is True

    healthy = Orchestrator(identity, _CannedProvider(), memory_store).respond("hello")
    assert healthy.used_fallback is False

    def boom(*args, **kwargs):
        raise MemoryError_("disk I/O error")

    memory_store.query = boom
    memory_only = Orchestrator(identity, _CannedProvider(), memory_store).respond("hello")
    assert memory_only.degraded is True
    assert memory_only.provider_used == "canned"
    assert memory_only.used_fallback is False
