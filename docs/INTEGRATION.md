# Integration Guide (for merging into the original Odysseus repository)

## Installation

```bash
pip install -r requirements.txt       # runtime deps: pydantic, PyYAML, requests
pip install -r requirements-dev.txt    # + pytest, for running the test suite
```

Python 3.10+ required (uses `X | Y` union type syntax throughout).

## Running

```bash
python -m odysseus.cli health
python -m odysseus.cli chat "hello"
python -m odysseus.cli memory remember "fact text" --source user --confidence 0.8
python -m odysseus.cli memory list-pending
python -m odysseus.cli memory approve 1 --reviewer alice
python -m odysseus.cli config show
```

## Running tests

```bash
python -m pytest
```

41 tests, no network access required, no external services required
(the default config uses the dependency-free `EchoProvider`).

## Module interfaces to integrate against

| Interface | File | Contract |
|---|---|---|
| `ModelProvider` | `odysseus/models/base.py` | `generate(GenerationRequest) -> GenerationResponse`, `health_check() -> (bool, str)`. Implement this for any new backend (the original repo's existing model client, a cloud model, etc.) instead of changing the orchestrator. |
| `MemoryStore` | `odysseus/memory/store.py` | `submit_candidate`, `find_duplicate`, `approve`, `reject`, `query`, `list_pending`, `get`. Backed by SQLite here; the API is intentionally storage-agnostic if the original repo already has a memory backend to adapt to. |
| `Orchestrator` | `odysseus/core/orchestrator.py` | `respond(prompt) -> InteractionResult`, `remember(content, source, confidence, tags)`. This is the integration seam for a future chat/voice/API front-end. |
| `OdysseusConfig` | `odysseus/config.py` | pydantic model; `load_config(path, overrides)`. |

## Configuration

- Defaults: `config/default.yaml` (no secrets).
- Environment overrides: `ODYSSEUS_<SECTION>__<FIELD>=value`; the top-level
  `log_level` is `ODYSSEUS_LOG_LEVEL` (see `config/.env.example`).
- Programmatic overrides: `load_config(path, overrides={"model": {"provider": "ollama"}})`.

## Suggested integration adapters (not yet built — build only if the
original repo's interfaces differ from the ones above)

- **Model adapter**: if Odysseus already has its own model-calling
  abstraction, write one `ModelProvider` subclass that wraps it, rather
  than changing `Orchestrator`.
- **Memory adapter**: if Odysseus already has persistent storage (e.g.
  a different DB), either point `MemoryStore` at that DB via a new
  `db_path`-equivalent, or write an adapter implementing the same five
  methods (`submit_candidate`/`approve`/`reject`/`query`/`list_pending`)
  backed by that store, and have `Orchestrator` take the adapter instead.
- **Identity adapter**: if Odysseus has an existing persona/identity
  concept, `JarvisIdentity.from_config` is the single place to change to
  source it from there instead of `config/default.yaml`.

## Assumptions to verify against the original Odysseus repository

These were made without access to that repo and should be checked once
it's available:

1. **No naming collisions.** `odysseus` is used here as the top-level
   Python package name; confirm the original repo doesn't already use
   that name for something else (rename this package if so).
2. **No existing model-provider abstraction to reconcile with.** If one
   exists, `ModelProvider` here should probably become an adapter over
   it, not a replacement.
3. **No existing persistent-memory schema.** If the original project
   already stores memories/facts somewhere, decide whether to migrate
   that data into this `memory_entries` schema or adapt `MemoryStore`
   to the existing schema instead.
4. **Review-inbox policy.** This implementation assumes *all* candidate
   memories require manual review unless an explicit
   `auto_approve_threshold` is set. Confirm this matches the original
   project's intended trust model before enabling auto-approval anywhere.
5. **Local model choice.** `OllamaProvider` assumes an Ollama-compatible
   HTTP API on `localhost:11434`. If the original repo already runs a
   different local-model server, write an additional `ModelProvider`
   for it rather than changing `OllamaProvider`.
6. **Permission gate `allow_external_providers`.** Currently this flag
   exists but Milestone A ships no external/cloud provider for it to
   gate (only `echo` and `ollama`, both local). Any later cloud-model
   provider must check this flag before being used.
