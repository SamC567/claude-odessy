"""Builds a ``ModelProvider`` from configuration.

This is the one place that knows about every concrete provider class,
so adding a new backend later means registering it here, not touching
the orchestrator or config schema's consumers.
"""

from __future__ import annotations

from odysseus.config import ModelProviderConfig
from odysseus.models.base import ModelProvider
from odysseus.models.echo_provider import EchoProvider
from odysseus.models.ollama_provider import OllamaProvider

_BUILTIN_PROVIDERS = {"echo", "ollama"}


def build_provider(config: ModelProviderConfig) -> ModelProvider:
    """Construct the configured provider. Never raises for an unknown name.

    An unrecognised ``provider`` value falls back to the echo provider
    rather than raising, keeping the system usable with a bad/partial
    config -- the health module is where that gets surfaced as a warning.
    """
    if config.provider == "ollama":
        return OllamaProvider(
            base_url=config.base_url,
            model_name=config.model_name,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
        )
    if config.provider == "echo":
        return EchoProvider(model_name=config.model_name or "echo-fallback")
    return EchoProvider(model_name="echo-fallback-unknown-provider")
