# Milestone A Architecture

Scope: **F001** (base architecture), **F003** (local model integration),
**F009** (persistent memory), **F073** (health & diagnostics) only.
This is an independent development workspace, built without access to
the original Odysseus repository — see `MIGRATION_ASSUMPTIONS.md` for
what to verify against it later.

## Module map

```
odysseus/
  config.py          Config schema + loader (YAML + env). No app logic, no secrets.
  logging_setup.py   Logging + the audit trail (`audit()`), used by every autonomous action.
  exceptions.py       Shared error types so each layer fails in a way the layer above can handle.

  models/            F003 — replaceable model-provider interface
    base.py            ModelProvider ABC, GenerationRequest/Response.
    echo_provider.py   Dependency-free fallback. Always available, clearly labelled, no network.
    ollama_provider.py Local model integration (Ollama-compatible HTTP API, loopback by default).
    registry.py        build_provider(config) -> ModelProvider. The only place that knows every backend.

  memory/            F009 — persistent memory + review inbox
    models.py          MemoryEntry (content, source, confidence, status, tags).
    store.py            SQLite-backed MemoryStore: submit_candidate / approve / reject / query.

  health/            F073 — system health & diagnostics
    diagnostics.py      Independent, failure-isolated checks -> HealthReport.

  core/              F001 — central identity + orchestration
    identity.py         JarvisIdentity: who is answering, under what permission policy.
    orchestrator.py     Orchestrator: the one place that wires identity + model + memory together.

  cli.py             Entry point: `python -m odysseus.cli {chat,health,memory,config}`
```

## Why it's split this way

- **One orchestration path.** `Orchestrator` is the only class that calls
  a model provider *and* touches memory in the same operation. Nothing
  else duplicates that wiring, which is what "avoid unnecessary
  model-to-model handoffs and duplicated functionality" means here.
- **Config has no behaviour.** `config.py` only parses and validates;
  every other module receives already-validated config objects. This
  keeps "configuration separated from application logic" real rather
  than nominal.
- **Every module degrades, not crashes.**
  - `models/`: `ModelProvider.generate()` raises a typed
    `ModelProviderError`; `Orchestrator` catches it and falls back to
    `EchoProvider` automatically. No external/local model being up is
    a *supported* state, not a failure mode.
  - `health/`: `_safe_check()` turns any exception from an individual
    check into a `CRITICAL` result for that check alone — one bad
    check never blanks out the rest of the report.
  - `memory/`: all SQLite errors are wrapped as `MemoryError_` /
    `ReviewInboxError`; callers never see a raw `sqlite3.Error`.
- **Review Inbox is structural, not a convention.** `MemoryStore` has
  no API that writes directly to `APPROVED`. The *only* way an entry
  becomes approved is `MemoryStore.approve(id, reviewer)` (or the
  explicit, audited `auto_approve_threshold` config). `MemoryStore.query()`
  only ever reads `APPROVED` rows.
- **Auditability.** `logging_setup.audit()` is called at every
  autonomous decision point currently implemented: memory submission,
  review decisions, and model-provider selection/fallback. New
  autonomous actions should call it too.

## Data flow for `orchestrator.respond(prompt)`

1. `MemoryStore.query(prompt)` — approved-only, keyword-matched context.
2. Build a system prompt from `JarvisIdentity.persona` + that context.
3. Call the configured `ModelProvider.generate(...)`.
4. On `ModelProviderError`, log it via `audit()` and retry with the
   fallback provider (`EchoProvider` by default) — this is what keeps
   the system usable with no local model server running.
5. Return an `InteractionResult` that *honestly* reports whether the
   answer came from a live model (`is_live_model`) and whether the
   primary provider was skipped (`degraded`).

## Known Milestone A limitations (intentional, not placeholders)

- **Retrieval is keyword/substring matching**, not embeddings or FTS5.
  It is real and tested, just simple — SQLite FTS5 is available in this
  environment (verified) and is the natural next step; swapping it in
  only touches `MemoryStore.query`.
- **No automatic fact-extraction from conversation.** `remember()` is
  invoked explicitly (CLI or future caller); nothing in Milestone A
  parses model output into candidate memories on its own. Doing that
  safely (without flooding the review inbox) is future work.
- **`OllamaProvider` was built and unit-tested against a simulated
  server** (this sandbox's network proxy could not reach
  `ollama.com`/`registry.ollama.ai`/GitHub releases to install a real
  Ollama binary). It talks to the standard `/api/generate` and
  `/api/tags` endpoints and has not been exercised against a live
  Ollama process. Verify this first against a real local install.

## Recent fixes

- `MemoryStore.query` (F009) returns nothing for a blank query or a
  non-positive `limit` (previously a blank query matched every approved
  entry and a negative limit disabled the cap).
- CLI `memory list-approved` (F009) lists approved memories with id, source,
  confidence and reviewer, so the id needed by `memory forget` is discoverable.

- `MemoryStore.query` now escapes SQL `LIKE` wildcards (`%`, `_`, `\`) in
  user text, so e.g. `100%` or `snake_case` match literally instead of
  acting as wildcards. Keyword/substring retrieval limitation above is
  otherwise unchanged.
- `health.diagnostics` gained `check_dependencies` (F073): reports
  installed versions of pydantic/PyYAML/requests via package metadata,
  CRITICAL if any are missing. Still not covered: GPU/VRAM
  and per-service checks beyond the model provider.
- `health.diagnostics` gained `check_hardware` (F073): CPU count and RAM
  headroom (stdlib only: /proc/meminfo on Linux, GlobalMemoryStatusEx on
  Windows; the Windows path is untested here). Thresholds are now
  configurable via `health.ram_warn_available_percent` (default 15) and
  `health.ram_critical_available_percent` (default 5).
  Unknown RAM is a WARNING.
- `MemoryStore.retract(id, reviewer)` (F009): withdraws an APPROVED entry
  (status -> REJECTED, row and provenance kept, audited with
  `previous=approved`); CLI: `memory forget <id>`. Closes the "no way to
  undo an approval" reversibility gap. Re-approving a retracted entry is
  not supported (submit a new candidate instead).
- `build_provider(config, allow_external=False)` (F003) now enforces
  `identity.allow_external_providers`: an `ollama` provider whose `base_url`
  is not loopback (localhost / 127.0.0.0/8 / ::1) is replaced by the echo
  fallback and audited as `model_provider_blocked`. Hostnames other than
  `localhost` are treated as non-loopback (no DNS resolution).
- `OllamaProvider.health_check` (F073/F003) now also verifies the configured
  `model_name` appears in `/api/tags` (bare names match `:latest`); a reachable
  server missing the model reports unhealthy (diagnostics WARNING). Tested
  against a simulated server only.
- `MemoryStore.submit_candidate` (F009) now de-duplicates: identical content
  (case/whitespace-insensitive) already PENDING or APPROVED returns the existing
  entry instead of inserting another (audited `memory.duplicate_candidate`).
  Rejected/retracted entries can be re-proposed. Source/confidence of the
  duplicate submission are not merged.
- `HealthConfig` (F073/F001) now rejects inverted thresholds at load time
  (`disk_warn_percent > disk_critical_percent`, or
  `ram_warn_available_percent < ram_critical_available_percent`) with a
  `ConfigError`, instead of silently making the WARNING band unreachable.
