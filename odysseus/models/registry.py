"""Builds a ``ModelProvider`` from configuration.

This is the one place that knows about every concrete provider class,
so adding a new backend later means registering it here, not touching
the orchestrator or config schema's consumers.
"""

from __future__ import annotations

from odysseus.config import ModelProviderConfig
from odysseus.logging_setup import audit
from odysseus.models.base import ModelProvider
from odysseus.models.echo_provider import EchoProvider
# Re-exported: callers import ``is_loopback_url`` from this module.
from odysseus.models.loopback import is_loopback_url
from odysseus.models.ollama_provider import OllamaProvider

#: The ``model.provider`` values ``build_provider`` knows how to build. Any
#: other value is answered by the echo fallback; diagnostics (F073) uses this
#: set to say so instead of keeping its own copy of the list.
BUILTIN_PROVIDERS = frozenset({"echo", "ollama"})
_BUILTIN_PROVIDERS = BUILTIN_PROVIDERS  # earlier, private name


def build_provider(
    config: ModelProviderConfig, allow_external: bool = False
) -> ModelProvider:
    """Construct the configured provider. Never raises for an unknown name.

    An unrecognised ``provider`` value falls back to the echo provider
    rather than raising, keeping the system usable with a bad/partial
    config -- the health module is where that gets surfaced as a warning.
    """
    if config.provider == "ollama":
        if not allow_external and not is_loopback_url(config.base_url):
            # Enforces identity.allow_external_providers: never send prompts
            # to a non-loopback host unless explicitly permitted.
            audit("model_provider_blocked", provider="ollama", reason="non-loopback base_url")
            return EchoProvider(model_name="echo-fallback-external-blocked")
        return OllamaProvider(
            base_url=config.base_url,
            model_name=config.model_name,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
        )
    if config.provider == "echo":
        return EchoProvider(model_name=config.model_name or "echo-fallback")
    return EchoProvider(model_name="echo-fallback-unknown-provider")
