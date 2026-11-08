"""Shared exception types.

Keeping these in one module lets every layer (models, memory, health,
orchestration) fail in a way the layer above can recognise and handle
gracefully, instead of leaking provider- or storage-specific errors.
"""

from __future__ import annotations


class OdysseusError(Exception):
    """Base class for all Odysseus/Jarvis errors."""


class ConfigError(OdysseusError):
    """Raised when configuration is missing, malformed, or inconsistent."""


class ModelProviderError(OdysseusError):
    """Raised when a model provider fails to produce a response.

    Callers should treat this as recoverable: the orchestrator falls back
    to another provider (e.g. the local echo provider) rather than
    crashing the whole system.
    """


class ModelUnavailableError(ModelProviderError):
    """Raised when a provider cannot be reached at all (e.g. connection refused)."""


class MemoryError_(OdysseusError):
    """Raised for persistent-memory failures (storage, retrieval, review-inbox)."""


class ReviewInboxError(MemoryError_):
    """Raised when a review-inbox operation is invalid (e.g. unknown entry id)."""
