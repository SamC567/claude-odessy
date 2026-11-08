"""The central Jarvis identity.

This is deliberately small: it holds *who the system is* (name, persona,
permission policy) rather than any behaviour. Behaviour that uses this
identity to actually do things lives in ``Orchestrator``. Keeping them
separate is what lets the orchestrator be tested with a trivial identity
and lets the identity be reused by future entry points (API, voice,
chat) without dragging orchestration logic along.
"""

from __future__ import annotations

from dataclasses import dataclass

from odysseus.config import IdentityConfig


@dataclass(frozen=True)
class JarvisIdentity:
    """Immutable description of who is answering, and under what policy."""

    name: str
    persona: str
    allow_external_providers: bool

    @classmethod
    def from_config(cls, config: IdentityConfig) -> "JarvisIdentity":
        return cls(
            name=config.name,
            persona=config.persona,
            allow_external_providers=config.allow_external_providers,
        )

    def greeting(self) -> str:
        return f"{self.name} online. {self.persona}"
