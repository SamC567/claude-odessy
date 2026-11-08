"""Replaceable model-provider interface and implementations (F003)."""

from odysseus.models.base import GenerationRequest, GenerationResponse, ModelProvider
from odysseus.models.echo_provider import EchoProvider
from odysseus.models.ollama_provider import OllamaProvider
from odysseus.models.registry import build_provider

__all__ = [
    "GenerationRequest",
    "GenerationResponse",
    "ModelProvider",
    "EchoProvider",
    "OllamaProvider",
    "build_provider",
]
