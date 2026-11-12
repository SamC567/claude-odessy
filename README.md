# Odysseus / Jarvis — Milestone A Foundation

A private, local-first foundation for the Jarvis/Odysseus assistant
project. This repository is an independent development workspace,
separate from the original Odysseus repository, built so the work can
be integrated there later (see `docs/INTEGRATION.md`).

## Milestone A scope

- **F001** — Odysseus base architecture (central identity + orchestration)
- **F003** — Local model integration (replaceable model-provider interface)
- **F009** — Persistent memory (source attribution, confidence, review inbox)
- **F073** — System health and diagnostics

## Quick start

```bash
pip install -r requirements-dev.txt
python -m pytest                       # 41 tests
python -m odysseus.cli health
python -m odysseus.cli chat "hello"
```

By default the system runs entirely offline, using a dependency-free
`echo` model provider and a local SQLite memory store — nothing
external is required. To use a local Ollama server instead:

```bash
export ODYSSEUS_MODEL__PROVIDER=ollama
python -m odysseus.cli chat "hello"
```

## Persistent memory & review inbox

Every piece of information the system is asked to remember is stored
with a **source** and a **confidence** score, and starts in a
**review inbox** (`status=pending`) — it is never treated as trusted,
permanent memory until explicitly approved:

```bash
python -m odysseus.cli memory remember "fact text" --source user --confidence 0.8
python -m odysseus.cli memory list-pending
python -m odysseus.cli memory show 1
python -m odysseus.cli memory show 1 --raw   # values exactly as stored (also works for a corrupt row)
python -m odysseus.cli memory quarantine 1 --reviewer alice   # move a row that cannot be read out of memory, unchanged
python -m odysseus.cli memory list-quarantined   # quarantined rows, values exactly as stored
python -m odysseus.cli memory restore-quarantined 1 --reviewer alice   # undo a quarantine: the row goes back unchanged (not repaired)
python -m odysseus.cli memory approve 1 --reviewer alice
python -m odysseus.cli memory list-rejected
python -m odysseus.cli memory list-approved --tag food   # approved memories filed under exactly that tag
python -m odysseus.cli memory search "pizza"   # which approved memories this text retrieves
python -m odysseus.cli memory search "pizza olives" --explain   # ...and which search terms each one matched
```

## Docs

- `docs/ARCHITECTURE.md` — module map, design rationale, known limitations
- `docs/INTEGRATION.md` — install/run/test instructions, module interfaces, assumptions to verify
- `docs/MIGRATION_ASSUMPTIONS.md` — compatibility summary and migration path

## Security posture

- Local-first: no outbound network calls unless the `ollama` provider
  is explicitly configured, and even then only to `model.base_url`
  (loopback by default).
- No credentials or API keys anywhere in this repo; see
  `config/.env.example` for the (secret-free) override format.
- No unrestricted shell execution anywhere in this codebase.
- Every memory write and review decision, and every model-provider
  call/fallback, is written to an audit log (`odysseus.logging_setup.audit`).
