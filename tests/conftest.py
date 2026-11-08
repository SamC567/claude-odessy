from __future__ import annotations

import pytest

from odysseus.config import OdysseusConfig
from odysseus.memory.store import MemoryStore


@pytest.fixture
def memory_store(tmp_path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory.sqlite3")


@pytest.fixture
def config() -> OdysseusConfig:
    return OdysseusConfig()
