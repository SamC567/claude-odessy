"""A dependency-free fallback provider.

This is not a toy: it is the provider the system falls back to when no
local model server is reachable, so that "the system must remain usable
when optional services or external models are unavailable" holds in
practice rather than just on paper. It never raises and never makes a
network call.
"""

from __future__ import annotations

from odysseus.models.base import GenerationRequest, GenerationResponse, ModelProvider


class EchoProvider(ModelProvider):
    """Deterministic, local, zero-dependency provider.

    Returns a clearly-labelled canned response that reflects the prompt
    back, so it is obviously distinguishable from a genuine model answer
    in logs, tests and any transcript a person reviews.
    """

    name = "echo"

    def __init__(self, model_name: str = "echo-fallback") -> None:
        self.model_name = model_name

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        preview = request.prompt.strip().replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "…"
        text = (
            "[echo-fallback: no live model backend was available, so this is "
            f"not a model-generated answer] You said: {preview!r}"
        )
        return GenerationResponse(
            text=text,
            provider_name=self.name,
            model_name=self.model_name,
            is_live_model=False,
            raw={"prompt_len": len(request.prompt)},
        )

    def health_check(self) -> tuple[bool, str]:
        return True, "echo provider is always available (no external dependency)"
