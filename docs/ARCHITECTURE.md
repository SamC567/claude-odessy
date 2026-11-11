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
  only touches `MemoryStore.query`. Results are ranked by the number of
  distinct query terms matched (then confidence, then recency); there is
  still no stop-word list, term weighting or stemming, and a word matches
  as a substring ("the" matches "other").
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

- `OllamaProvider.generate` (F003) appends the server's own `error` text to the `ModelProviderError` for an HTTP error response, e.g. `404 Client Error ... (server said: model 'llama3' not found, try pulling it first)`; previously only the status line reached the `chat` degraded reason and the audit log, so a model that had not been pulled was indistinguishable from any other 404. The text is whitespace-collapsed and capped at 200 characters. Tested against a simulated server only.

- `chat` CLI (F001) reports an empty or whitespace-only prompt as `error: prompt must not be empty` with exit code 2 instead of a `ValueError` traceback (same convention as `memory remember`).

- `configure_logging` (F001/F073) no longer raises when the audit log location is unusable (a file where the `data` directory should be, unwritable directory/file): audit records fall back to stderr and a WARNING says they are not persisted. Previously every CLI command, including `health` — whose `audit_log` check exists to report exactly this — died with an `OSError` traceback. Audit records are **not durable** in that state. Windows ACL behaviour untested here.

- `MemoryStore.query` (F009) orders results by how many distinct query terms an entry matches before confidence/recency; previously ordering was confidence-only, so with the orchestrator's limit of 3 a high-confidence entry sharing one common word ("the") could push the relevant entry out of the context.

- `OllamaProvider.health_check` (F003/F073) treats `"models": null` from `/api/tags` as "no models installed" (unhealthy, diagnostics WARNING) and a non-list `models` value as an unreadable list; previously either raised `TypeError` out of `health_check`, which must not raise, and diagnostics reported a crashed check (CRITICAL). Tested against a simulated server only.

- Config env overrides (F001) honour `ODYSSEUS_LOG_LEVEL` for the top-level `log_level` field (documented in `config/.env.example` but previously silently ignored, since only `SECTION__FIELD` names were applied). A single-segment section name such as `ODYSSEUS_MODEL` is still ignored.

- `InteractionResult.used_fallback` (F001) is true only when the primary provider failed and the fallback answered; the `chat` CLI no longer prints "fell back to <provider>" for a memory-only degradation (previously it claimed a provider fallback that had not happened).

- CLI `health` (F073) still produces a full report when the memory database is corrupt/unopenable: `memory_store` is CRITICAL (exit 1) instead of the command dying with only `error: ...`. `run_diagnostics` accepts `memory_store=None` plus `memory_store_error`.

- `MemoryStore` read paths (`query`, `get`, `list_*`, `count_by_status`) (F009) raise `MemoryError_` on a corrupt/unreadable database (previously raw `sqlite3` errors that bypassed the orchestrator's graceful degradation).

- `MemoryStore.submit_candidate` (F009) raises a clear `TypeError` for a non-`MemoryEntry` argument (previously obscure `AttributeError`).

- `HealthReport.overall_status` (F073) is WARNING for a report with no checks (previously OK, claiming health without evidence).

- Config (F003/F001) rejects `model.base_url` with embedded credentials (`user:pass@host`), which would otherwise leak into diagnostics/audit output and the config file.

- Config (F003/F001) rejects a blank `model.model_name` when `provider: ollama` (previously only failed at request time); the echo provider still tolerates it.

- `MemoryEntry` (F009) rejects non-string `content`/`source` with `ValueError` (previously an obscure `AttributeError` from `.strip()`).

- Review decisions (F009) reject a non-string reviewer with `ReviewInboxError` (previously an obscure `AttributeError`).

- `MemoryStore.query` (F009) raises a clear `TypeError` for non-string text or a non-int limit (previously obscure `AttributeError`/comparison errors).

- `MemoryEntry` (F009) rejects a non-numeric or bool `confidence` with `ValueError` (previously a raw `TypeError` for strings/None, and `True` was accepted as 1.0).

- `MemoryStore(auto_approve_threshold=)` (F009) validates the value (number in 0..1, not bool) at construction; previously only the config path did, so a direct caller passing e.g. -1 would silently auto-approve every candidate and bypass the review inbox.

- `load_config(path)` (F001) raises `ConfigError` for an explicitly given config path that does not exist (previously silently used defaults); the default path remains optional.

- CLI `health` (F073) no longer passes the working directory as `disk_path`, so disk space is measured on the memory DB's volume (the `run_diagnostics` default) instead of silently overriding it.

- `MemoryStore.query` (F009) caps the keyword terms used per query (first 50 distinct words plus the whole text); previously a very long query raised a raw `sqlite3.OperationalError` (expression tree too large). Words beyond the cap are not searched.

- `check_audit_log` (F073) also WARNs when a regular file sits where the log directory should be, or a directory where the log file should be (previously reported OK because `os.access` said writable).

- `MemoryEntry` (F009) rejects tags given as a bare string (previously split into single characters) or containing blank/non-string items, and normalises a tag list to a tuple.

- `check_audit_log` (F073/F001): `run_diagnostics(..., audit_log_path=)` adds an `audit_log` check that WARNs when the audit log (or its nearest existing parent directory) is not writable; the `health` CLI passes `data/audit.log`. Windows ACL behaviour untested here.

- `model.base_url` (F003/F001) must be an http(s) URL with a host; malformed values (no scheme, ftp://, empty) are a `ConfigError` at load time and surrounding whitespace is trimmed.

- `log_level` config (F001) is validated at load time (DEBUG/INFO/WARNING/ERROR/CRITICAL, case-insensitive, normalised to upper case); an unknown value is a `ConfigError` instead of a raw `ValueError` traceback from the CLI.

- `MemoryStore` review decisions (F009) record the reviewer name trimmed of surrounding whitespace.

- `memory remember` CLI (F009) reports invalid input (confidence outside 0..1, empty content/source) as `error: ...` with exit code 2 instead of a traceback.

- `check_dependencies` (F073) warns when an installed dependency's major version is outside the supported range (pydantic 2, PyYAML 6, requests 2, mirroring requirements.txt); previously any installed version reported OK.

- `check_memory_store` (F073) warns when the memory database file is not writable (previously reported OK). Windows behaviour untested here.

- `run_diagnostics` (F073) names a crashed model-provider check `model_provider:<name>` (same as the healthy path) instead of bare `model_provider`, so consumers keying on the name see a consistent identifier.

- `MemoryStore` row decoding (F009) raises `MemoryError_` for a corrupt row (bad tags JSON,
  unknown status, bad timestamp) instead of a raw `ValueError`, so the orchestrator's
  memory-failure degradation covers it.

- `OllamaProvider.generate` (F003) raises `ModelProviderError` when the server returns a
  non-object JSON body (previously an `AttributeError` escaped, bypassing the orchestrator's
  echo fallback). Tested against a simulated server only.

- `InteractionResult.memory_sources` (F009) exposes `(entry id, source)` for each memory
  used as context, and the orchestrator audits `orchestrator.memory_used`, so answers are
  traceable to their memory provenance.

- `MemoryStore.query` (F009) strips surrounding punctuation from query words, so
  "pizza?" matches "pizza" (previously the trailing `?` defeated the match).

- `health.pending_review_warn_count` (F073/F009, default 100) makes the memory-store
  pending-review WARNING threshold configurable (was hardcoded).

- `MemoryStore.query` (F009) matches case-insensitively for non-ASCII text too
  (casefold on both sides; SQLite's LIKE only folded ASCII).

- `check_config` (F073/F003) now WARNs when `provider=ollama` has a non-loopback
  `base_url` and `allow_external_providers` is false (the registry silently
  substitutes the echo fallback; previously the config check reported OK).

- `ModelProvider.health_check(timeout_seconds=None)` (F073/F003): diagnostics now
  apply `health.model_check_timeout_seconds` (previously configured but unused);
  providers without the parameter are still supported.

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
- GPU free-VRAM warning threshold (F073) is now configurable via
  `health.gpu_vram_warn_free_percent` (default 5, unchanged behaviour).
- `run_diagnostics` (F073) now measures disk space at the memory DB's directory
  when no `disk_path` is given (previously the process working directory, which
  may be a different volume from the data). Falls back to `.` if that directory
  does not exist yet.
- `MemoryStore._review` (F009) now guards the status transition inside the
  `UPDATE` itself (`WHERE id = ? AND status = ?`), so two reviewers racing on one
  entry can no longer overwrite each other's decision; the loser gets a
  `ReviewInboxError`.

- `Orchestrator.respond` (F001/F009) now degrades when `MemoryStore.query` raises
  `MemoryError_`: it answers with no memory context, sets `degraded=True` with a
  "memory unavailable" reason, and audits `orchestrator.memory_failed`
  (previously the error crashed the interaction).

- `MemoryStore.approve/reject/retract` (F009) reject a blank reviewer with `ReviewInboxError`, so every review decision is attributable.
