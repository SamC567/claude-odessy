"""Orchestration: wires identity + model provider + memory together.

This is the one place that decides, on each interaction:
    1. What memory context (if any) to pull in -- only APPROVED memory.
    2. Which model provider to call, and what to do if it fails.
    3. Whether anything learned should be queued for the review inbox.

Keeping this logic in one small class (rather than spread across the
model/memory modules) is what "avoid unnecessary model-to-model handoffs
and duplicated functionality" means in practice here: there is exactly
one orchestration path, not one per feature.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from odysseus.core.identity import JarvisIdentity
from odysseus.exceptions import MemoryError_, ModelProviderError
from odysseus.logging_setup import audit
from odysseus.memory.models import MemoryEntry
from odysseus.memory.store import MemoryStore
from odysseus.models.base import GenerationRequest, GenerationResponse, ModelProvider
from odysseus.models.echo_provider import EchoProvider


def _reply_problem(response: object) -> str | None:
    """Say why ``response`` cannot be shown as an answer, or None if it can.

    Describes the reply instead of quoting it: the text ends up in the
    degraded reason and the audit log.
    """
    if not isinstance(response, GenerationResponse):
        return f"a {type(response).__name__} instead of a GenerationResponse"
    if not isinstance(response.text, str):
        return f"text of type {type(response.text).__name__}, not a string"
    if not response.text.strip():
        return "blank text"
    return None


@dataclass
class InteractionResult:
    """What came back from a single ``Orchestrator.respond`` call."""

    text: str
    provider_used: str
    is_live_model: bool
    memory_context: tuple[str, ...] = field(default_factory=tuple)
    # Provenance of each memory_context item, same order: (entry id, source).
    memory_sources: tuple[tuple[int | None, str], ...] = field(default_factory=tuple)
    degraded: bool = False
    degraded_reason: str | None = None
    # True only when the primary provider failed and the fallback answered.
    # ``degraded`` alone does not imply this (memory may be what degraded).
    used_fallback: bool = False


class Orchestrator:
    """Coordinates identity, a model provider, and persistent memory.

    ``fallback_provider`` is used automatically whenever ``provider``
    raises ``ModelProviderError`` (or, against the interface contract, any
    other ``Exception``) or returns no usable reply (not a
    ``GenerationResponse``, or blank text) -- this is the concrete mechanism
    behind "the system must remain usable when optional services or
    external models are unavailable". It defaults to the dependency-free
    ``EchoProvider`` so that guarantee holds even with no extra config.
    """

    def __init__(
        self,
        identity: JarvisIdentity,
        provider: ModelProvider,
        memory: MemoryStore,
        fallback_provider: ModelProvider | None = None,
        memory_context_limit: int = 3,
    ) -> None:
        self.identity = identity
        self.provider = provider
        self.memory = memory
        self.fallback_provider = fallback_provider or EchoProvider()
        self.memory_context_limit = memory_context_limit

    def respond(self, prompt: str) -> InteractionResult:
        """Answer ``prompt``, using approved memory as context when relevant."""
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty")

        memory_failure: str | None = None
        try:
            context_entries = self.memory.query(prompt, limit=self.memory_context_limit)
        except MemoryError_ as exc:
            # Memory being unavailable is a supported degraded state, not a crash.
            context_entries = []
            memory_failure = f"memory unavailable: {exc}"
            audit("orchestrator.memory_failed", error=str(exc))
        context_texts = tuple(e.content for e in context_entries)
        context_sources = tuple((e.id, e.source) for e in context_entries)
        if context_entries:
            audit("orchestrator.memory_used", entry_ids=[e.id for e in context_entries])

        system_prompt = self.identity.persona
        if context_texts:
            system_prompt += "\nRelevant known facts:\n" + "\n".join(
                f"- {t}" for t in context_texts
            )

        request = GenerationRequest(prompt=prompt, system_prompt=system_prompt)

        degraded = memory_failure is not None
        degraded_reason = memory_failure
        used_fallback = False
        try:
            response = self.provider.generate(request)
            # A reply that cannot be shown (wrong type, blank text) is a
            # provider failure too, not an answer: hand over to the fallback.
            problem = _reply_problem(response)
            if problem is not None:
                raise ModelProviderError(
                    f"provider {self.provider.name!r} returned no usable reply: {problem}"
                )
            audit("orchestrator.generate", provider=self.provider.name, degraded=False)
        except ModelProviderError as exc:
            degraded = True
            used_fallback = True
            degraded_reason = (
                f"{memory_failure}; {exc}" if memory_failure else str(exc)
            )
            audit(
                "orchestrator.provider_failed",
                provider=self.provider.name,
                error=str(exc),
            )
            response = self.fallback_provider.generate(request)
            audit("orchestrator.generate", provider=self.fallback_provider.name, degraded=True)
        except Exception as exc:  # noqa: BLE001 - see comment
            # The interface says a provider raises only ModelProviderError.
            # A provider that breaks that (a bug in a new or third-party
            # backend) must not take the interaction down with it: degrade
            # the same way, but say in the reason and the audit trail that
            # this was an unexpected error, not an ordinary outage.
            # KeyboardInterrupt/SystemExit are not Exception and still pass.
            degraded = True
            used_fallback = True
            failure = (
                f"provider {self.provider.name!r} raised an unexpected "
                f"{type(exc).__name__}: {exc}"
            )
            degraded_reason = f"{memory_failure}; {failure}" if memory_failure else failure
            audit(
                "orchestrator.provider_failed",
                provider=self.provider.name,
                error=str(exc),
                unexpected=type(exc).__name__,
            )
            response = self.fallback_provider.generate(request)
            audit("orchestrator.generate", provider=self.fallback_provider.name, degraded=True)

        return InteractionResult(
            text=response.text,
            provider_used=response.provider_name,
            is_live_model=response.is_live_model,
            memory_context=context_texts,
            memory_sources=context_sources,
            degraded=degraded,
            degraded_reason=degraded_reason,
            used_fallback=used_fallback,
        )

    def remember(
        self,
        content: str,
        source: str,
        confidence: float,
        tags: tuple[str, ...] = (),
    ) -> MemoryEntry:
        """Submit a candidate fact. Always goes through the review inbox first.

        This method never writes directly to approved memory -- that is
        the entire point of F009's review-inbox requirement. Promotion
        happens only via ``MemoryStore.approve``.
        """
        entry = MemoryEntry(content=content, source=source, confidence=confidence, tags=tags)
        return self.memory.submit_candidate(entry)
