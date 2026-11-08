# Compatibility & Migration Guide

This repo was built with **no access** to the original Odysseus
repository. The assumptions list that must be checked once it's
available lives in `docs/INTEGRATION.md` under "Assumptions to verify
against the original Odysseus repository" — read that section first.

## Compatibility summary

- **Language/runtime**: Python 3.10+, stdlib `sqlite3` + 3 small
  dependencies (`pydantic`, `PyYAML`, `requests`). No compiled
  extensions, no Docker requirement, nothing GPU-specific.
- **Storage**: a single SQLite file (`data/odysseus_memory.sqlite3` by
  default, gitignored, created on first run). Trivial to copy or back up.
- **Network**: zero required network access. The only outbound call
  this code ever makes is to `model.base_url` (default
  `http://localhost:11434`, loopback) when `model.provider: ollama` is
  configured, and even that is optional — the system runs fully offline
  on the `echo` provider.
- **State surfaces that would need migrating**: only the
  `memory_entries` SQLite table. There is no other persisted state
  (config is files, not a database; logs are append-only files).

## Migration path once the original repo is available

1. Diff package/module names (see assumption 1 in `INTEGRATION.md`) and
   rename `odysseus/` if it collides.
2. Decide per assumption 2–3 whether `ModelProvider` / `MemoryStore`
   become the system of record or adapters over the original repo's
   existing abstractions — prefer adapters if the original repo has
   users/data depending on its current interfaces.
3. If there is existing persistent-memory data to bring forward, write
   a one-off script that reads it and calls
   `MemoryStore.submit_candidate(...)` per record **with status staying
   PENDING** (do not bulk-import directly as APPROVED) so a human
   reviews the migrated set once, the same way any other candidate
   memory is reviewed.
4. Re-run this repo's test suite (`python -m pytest`) after any adapter
   work — it is the regression net for F001/F003/F009/F073 behaviour
   during the merge.
5. Only after the merge, revisit `allow_external_providers` and decide
   if/when a cloud model provider should be added (assumption 6).
