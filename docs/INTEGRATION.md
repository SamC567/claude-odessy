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

No network access and no external services required (the default config
uses the dependency-free `EchoProvider`). The test count is recorded per
change in `docs/MILESTONE_A_LOG.md` rather than here, so it cannot go stale.

## Module interfaces to integrate against

| Interface | File | Contract |
|---|---|---|
| `ModelProvider` | `odysseus/models/base.py` | `generate(GenerationRequest) -> GenerationResponse`, `health_check() -> (bool, str)`. Implement this for any new backend (the original repo's existing model client, a cloud model, etc.) instead of changing the orchestrator. |
| `MemoryStore` | `odysseus/memory/store.py` | Backed by SQLite here; the API is intentionally storage-agnostic if the original repo already has a memory backend to adapt to. Full method list and which caller needs each one: see "`MemoryStore` methods" below. |
| `Orchestrator` | `odysseus/core/orchestrator.py` | `respond(prompt) -> InteractionResult`, `remember(content, source, confidence, tags)`. This is the integration seam for a future chat/voice/API front-end. |
| `OdysseusConfig` | `odysseus/config.py` | pydantic model; `load_config(path, overrides)`. |

### `MemoryStore` methods

Every public method of `MemoryStore` is listed here; `tests/test_integration_docs.py`
fails if one is added without being listed. "Required" means the caller uses it
unconditionally, so an adapter must provide it for that caller to work.
"Optional" means the caller looks it up with `getattr` and skips the feature
when it is missing.

| Method | Purpose | Used by |
|---|---|---|
| `submit_candidate(entry)` | Store a new candidate as pending (or auto-approve above the configured threshold). | `Orchestrator.remember` (required) |
| `query(text, limit)` | Approved entries matching a text, best first. | `Orchestrator.respond` (required), `memory search` |
| `find_duplicate(content)` | Existing entry with the same normalised content. | `memory remember` (optional) |
| `get(entry_id)` | One entry by id, or `None`. | `memory show` |
| `raw_row(entry_id)` | Stored values of a row, even an unreadable one. | `memory show --raw` (optional) |
| `list_pending()` | Review inbox. | `memory list-pending` |
| `list_approved(tag=None)` | Approved entries, optionally one tag. | `memory list-approved` |
| `list_rejected()` | Rejected entries. | `memory list-rejected` |
| `search_terms(text)` | The terms `query` searches for. | `memory search --explain` |
| `matched_terms(text, entry)` | Which of those terms an entry matched. | `memory search --explain` |
| `approve(entry_id, reviewer)` | pending → approved (audited). | `memory approve` |
| `reject(entry_id, reviewer)` | pending → rejected (audited). | `memory reject` |
| `retract(entry_id, reviewer)` | approved → rejected (audited). | `memory forget` |
| `quarantine(entry_id, reviewer)` | Move an unreadable row aside (audited). | `memory quarantine` |
| `restore_quarantined(entry_id, reviewer)` | Undo a quarantine (audited). | `memory restore-quarantined` |
| `list_quarantined()` | Quarantined rows as stored. | `memory list-quarantined` |
| `count_quarantined()` | Number of quarantined rows. | `health` (optional) |
| `count_by_status()` | Row counts per status. | `health` (required) |
| `unreadable_entry_ids()` | Ids of rows that cannot be decoded. | `health` (optional) |
| `integrity_check()` | `(ok, detail)` from SQLite's integrity check. | `health` (required) |

`health` also reads the store's `db_path` attribute to report the file and
free disk space.

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
  `db_path`-equivalent, or write an adapter backed by that store and have
  `Orchestrator` take the adapter instead. `Orchestrator` alone needs only
  `submit_candidate` and `query`; the CLI and `health` need the methods
  marked for them in "`MemoryStore` methods" above.
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
