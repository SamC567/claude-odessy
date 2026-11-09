"""The model-provider interface.

Every model backend (local fast model, a future external/cloud model,
a test double) implements this same small interface. The orchestrator
depends only on ``ModelProvider``, never on a concrete backend, so a
provider can be swapped — or the whole model layer mocked out in tests —
without touching orchestration code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GenerationRequest:
    """A single request to generate text from a model provider."""

    prompt: str
    system_prompt: str | None = None
    max_tokens: int | None = None
    temperature: float = 0.2
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResponse:
    """The result of a successful generation call."""

    text: str
    provider_name: str
    model_name: str
    # True if this came from a genuine model backend; False if it came
    # from a fallback/mock path. Callers (and audit logs) use this to be
    # honest about what actually produced the text.
    is_live_model: bool = True
    raw: dict[str, object] = field(default_factory=dict)


class ModelProvider(ABC):
    """Abstract interface every model backend must implement."""

    #: Short, stable name used in logs, audit trails and config.
    name: str = "base"

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Produce a response for ``request``.

        Implementations must raise ``odysseus.exceptions.ModelProviderError``
        (or the more specific ``ModelUnavailableError``) on failure rather
        than letting backend-specific exceptions escape, so callers have a
        single error type to handle.
        """

    @abstractmethod
    def health_check(self, timeout_seconds: float | None = None) -> tuple[bool, str]:
        """Return ``(is_healthy, detail)`` without raising.

        ``timeout_seconds`` optionally overrides the provider's own request
        timeout so diagnostics can use a short probe timeout
        (``health.model_check_timeout_seconds``).

        Used by the health/diagnostics module (F073) and by the
        orchestrator to decide whether to attempt this provider at all.
        """
