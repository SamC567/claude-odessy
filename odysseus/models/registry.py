"""Builds a ``ModelProvider`` from configuration.

This is the one place that knows about every concrete provider class,
so adding a new backend later means registering it here, not touching
the orchestrator or config schema's consumers.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from odysseus.config import ModelProviderConfig
from odysseus.logging_setup import audit
from odysseus.models.base import ModelProvider
from odysseus.models.echo_provider import EchoProvider
from odysseus.models.ollama_provider import OllamaProvider

_BUILTIN_PROVIDERS = {"echo", "ollama"}


def is_loopback_url(url: str) -> bool:
    """True if ``url`` points at this machine (localhost or a loopback IP)."""
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
