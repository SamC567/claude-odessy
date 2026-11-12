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


class _BrokenContractProvider(ModelProvider):
    """Raises something other than ModelProviderError, against the interface."""

    name = "broken-contract"

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise KeyError("choices")

    def health_check(self, timeout_seconds=None):
        return True, "claims to be fine"


def test_respond_falls_back_when_provider_raises_an_unexpected_exception(
    identity, memory_store, caplog
):
    import logging

    from odysseus.logging_setup import AUDIT_LOGGER_NAME

    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER_NAME):
            result = Orchestrator(identity, _BrokenContractProvider(), memory_store).respond("hello")
    finally:
        audit_logger.removeHandler(caplog.handler)

    assert result.degraded is True
    assert result.used_fallback is True
    assert result.provider_used == "echo"
    assert result.is_live_model is False
    # The reason names the provider and the exception type, so it cannot be
    # mistaken for an ordinary outage.
    assert "broken-contract" in result.degraded_reason
    assert "unexpected KeyError" in result.degraded_reason
    failed = [r.getMessage() for r in caplog.records if "orchestrator.provider_failed" in r.getMessage()]
    assert len(failed) == 1
    assert "unexpected='KeyError'" in failed[0]


def test_unexpected_provider_exception_keeps_the_memory_failure_in_the_reason(
    identity, memory_store
):
    from odysseus.exceptions import MemoryError_

    def boom(*args, **kwargs):
        raise MemoryError_("disk I/O error")

    memory_store.query = boom
    result = Orchestrator(identity, _BrokenContractProvider(), memory_store).respond("hello")
    assert result.used_fallback is True
    assert "memory unavailable" in result.degraded_reason
    assert "unexpected KeyError" in result.degraded_reason


def test_keyboard_interrupt_from_a_provider_is_not_swallowed(identity, memory_store):
    class _Interrupted(_BrokenContractProvider):
        def generate(self, request):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Orchestrator(identity, _Interrupted(), memory_store).respond("hello")


class _ReturnsProvider(ModelProvider):
    """Returns whatever it was given, even something the interface forbids."""

    name = "returns"

    def __init__(self, reply):
        self.reply = reply

    def generate(self, request: GenerationRequest):
        return self.reply

    def health_check(self, timeout_seconds=None):
        return True, "always healthy"


def _blank_response(text):
    return GenerationResponse(text=text, provider_name="returns", model_name="m")


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (None, "a NoneType instead of a GenerationResponse"),
        ({"text": "hi"}, "a dict instead of a GenerationResponse"),
        (_blank_response(""), "blank text"),
        (_blank_response(" \n\t"), "blank text"),
        (_blank_response(None), "text of type NoneType, not a string"),
    ],
)
def test_respond_falls_back_when_provider_returns_no_usable_reply(
    identity, memory_store, reply, expected
):
    result = Orchestrator(identity, _ReturnsProvider(reply), memory_store).respond("hello")

    assert result.degraded is True
    assert result.used_fallback is True
    assert result.provider_used == "echo"
    assert result.is_live_model is False
    assert result.text.strip()
    assert result.degraded_reason == f"provider 'returns' returned no usable reply: {expected}"


def test_unusable_reply_is_audited_as_a_provider_failure_not_a_generation(
    identity, memory_store, caplog
):
    import logging

    from odysseus.logging_setup import AUDIT_LOGGER_NAME

    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER_NAME):
            Orchestrator(identity, _ReturnsProvider(_blank_response("")), memory_store).respond("hello")
    finally:
        audit_logger.removeHandler(caplog.handler)

    messages = [r.getMessage() for r in caplog.records]
    assert len([m for m in messages if "orchestrator.provider_failed" in m]) == 1
    generated = [m for m in messages if "orchestrator.generate" in m]
    assert len(generated) == 1
    assert "echo" in generated[0]
    assert "returns" not in generated[0]


def test_usable_reply_with_surrounding_whitespace_is_returned_unchanged(identity, memory_store):
    result = Orchestrator(identity, _ReturnsProvider(_blank_response("  hi\n")), memory_store).respond("hello")
    assert result.text == "  hi\n"
    assert result.degraded is False
    assert result.used_fallback is False


class _RaisesProvider(ModelProvider):
    """Raises whatever it was given from ``generate``."""

    name = "spare"

    def __init__(self, exc: Exception):
        self.exc = exc

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise self.exc

    def health_check(self, timeout_seconds=None):
        return False, "broken"


class _SpareReturnsProvider(_ReturnsProvider):
    name = "spare"


@pytest.mark.parametrize(
    ("fallback", "expected"),
    [
        (_RaisesProvider(ModelUnavailableError("spare is down")), "failed: spare is down"),
        (_RaisesProvider(KeyError("choices")), "raised an unexpected KeyError: 'choices'"),
        (_SpareReturnsProvider(None), "returned no usable reply: a NoneType instead of a GenerationResponse"),
        (_SpareReturnsProvider(_blank_response(" \n")), "returned no usable reply: blank text"),
    ],
)
def test_failing_fallback_ends_with_one_typed_error_naming_both_failures(
    identity, memory_store, fallback, expected
):
    orchestrator = Orchestrator(
        identity, _AlwaysFailsProvider(), memory_store, fallback_provider=fallback
    )

    with pytest.raises(ModelProviderError) as excinfo:
        orchestrator.respond("hello")

    assert str(excinfo.value) == (
        f"no provider could answer: simulated outage; fallback provider 'spare' {expected}"
    )


def test_failing_fallback_is_audited_and_never_recorded_as_a_generation(
    identity, memory_store, caplog
):
    import logging

    from odysseus.logging_setup import AUDIT_LOGGER_NAME

    orchestrator = Orchestrator(
        identity,
        _AlwaysFailsProvider(),
        memory_store,
        fallback_provider=_RaisesProvider(KeyError("choices")),
    )
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER_NAME):
            with pytest.raises(ModelProviderError):
                orchestrator.respond("hello")
    finally:
        audit_logger.removeHandler(caplog.handler)

    messages = [r.getMessage() for r in caplog.records]
    failed = [m for m in messages if "orchestrator.fallback_failed" in m]
    assert len(failed) == 1
    assert "spare" in failed[0]
    assert "KeyError" in failed[0]
    assert not [m for m in messages if "orchestrator.generate" in m]


def test_keyboard_interrupt_from_a_fallback_is_not_swallowed(identity, memory_store):
    class _Interrupted(_RaisesProvider):
        def generate(self, request):
            raise KeyboardInterrupt

    orchestrator = Orchestrator(
        identity,
        _AlwaysFailsProvider(),
        memory_store,
        fallback_provider=_Interrupted(RuntimeError("unused")),
    )
    with pytest.raises(KeyboardInterrupt):
        orchestrator.respond("hello")
