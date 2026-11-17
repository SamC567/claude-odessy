"""docs/INTEGRATION.md must name every public method of the interfaces it
documents, so an integrator reading it sees the whole surface to adapt."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from odysseus.core.orchestrator import Orchestrator
from odysseus.memory.store import MemoryStore
from odysseus.models.base import ModelProvider

INTEGRATION_DOC = Path(__file__).resolve().parent.parent / "docs" / "INTEGRATION.md"


def _public_methods(cls: type) -> list[str]:
    return sorted(
        name
        for name, member in inspect.getmembers(cls)
        if not name.startswith("_") and callable(member)
    )


def _documented_names(text: str) -> set[str]:
    # Names written as code: `name` or `name(...)`.
    return set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)\(?", text))


@pytest.mark.parametrize("cls", [MemoryStore, ModelProvider, Orchestrator])
def test_integration_doc_names_every_public_method(cls: type) -> None:
    documented = _documented_names(INTEGRATION_DOC.read_text(encoding="utf-8"))
    missing = [name for name in _public_methods(cls) if name not in documented]
    assert not missing, f"docs/INTEGRATION.md does not name {cls.__name__}: {missing}"


def test_integration_doc_memory_table_lists_only_real_methods() -> None:
    text = INTEGRATION_DOC.read_text(encoding="utf-8")
    section = text.split("### `MemoryStore` methods", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([a-z_]+)\(", section, flags=re.MULTILINE)
    assert rows, "MemoryStore methods table not found"
    assert sorted(rows) == _public_methods(MemoryStore)


def test_integration_doc_states_no_test_count() -> None:
    # A hard-coded count went stale (it said 41 tests); the log records it.
    text = INTEGRATION_DOC.read_text(encoding="utf-8")
    assert not re.search(r"\b\d+ tests\b", text)
