# Milestone A Log

Append-only log of scheduled-run changes.

## 2026-11-08 — F009 query wildcard escaping
- Gap: `MemoryStore.query` interpolated user text into `LIKE` patterns
  unescaped, so `%`/`_` acted as wildcards.
- Fix: `_escape_like` + `ESCAPE '\'` in `odysseus/memory/store.py`.
- Test: `test_query_treats_like_wildcards_literally` (fails without fix, verified via stash).
- Suite: full pytest passes.

## 2026-11-08 — F073 dependency diagnostics
- Gap: F073 requires dependency diagnostics; `run_diagnostics` had none
  (only python version, disk, config, memory store, model provider).
- Fix: `check_dependencies` in `odysseus/health/diagnostics.py`, wired
  into `run_diagnostics` (metadata-only, no imports, no network).
- Tests: `test_dependencies_check_ok_and_reports_missing`,
  `test_run_diagnostics_includes_dependencies` (both fail without the fix, verified via stash).
- Suite: 44 passed (baseline 42). Note: ran with python3.13; `python` on PATH is 3.11 without pytest.
- Remaining F073 gap: hardware (CPU/RAM/GPU) checks.

## 2026-11-08 — F073 hardware diagnostics
- Gap: no hardware (CPU/RAM) check in `run_diagnostics`.
- Fix: `check_hardware` in `odysseus/health/diagnostics.py` (stdlib only, injectable memory reader), wired into `run_diagnostics`.
- Tests: `test_hardware_check_thresholds_and_unknown`, `test_run_diagnostics_includes_hardware` (new; fail without the change as `check_hardware` doesn't exist).
- Suite: 46 passed (baseline 44, python3.13).
- Remaining F073 gap: GPU/VRAM, per-service checks, thresholds in config.

## 2026-11-08 — F009 retract approved memory
- Gap: an approved memory could never be withdrawn (no reversibility; only PENDING could be reviewed).
- Fix: `MemoryStore.retract` (approved -> rejected, row kept, audited) + `memory forget` CLI command; `_review` takes an `expected` status.
- Test: `test_retract_removes_approved_entry_from_query` (fails without the change, verified via stash).
- Suite: 47 passed (baseline 46, python3.12 venv).

### Decisions
- Hardware thresholds kept as function defaults rather than adding config schema fields (reversible, no config contract change).
- Windows RAM path (ctypes) written but not run in this Linux cloud run.
- Retracted entries reuse the REJECTED status rather than adding a new enum value (no schema change, reversible to change later); re-approval deliberately unsupported.

## 2026-11-08 — F003 enforce loopback-only model endpoint
- Gap: `identity.allow_external_providers=false` was not enforced; an `ollama` provider with a non-loopback `base_url` would send prompts off-machine (violates local-first principle).
- Fix: `build_provider(config, allow_external=False)` in `odysseus/models/registry.py` falls back to echo (audited as `model_provider_blocked`) for non-loopback hosts; CLI passes the identity flag.
- Test: `test_non_loopback_base_url_blocked_unless_external_allowed` (fails without the change: no such parameter/behaviour).
- Suite: 48 passed (baseline 47, python3.12 venv).

## 2026-11-08 — F073 configurable RAM thresholds
- Gap: hardware check thresholds were hardcoded function defaults, not configurable.
- Fix: `health.ram_warn_available_percent` / `ram_critical_available_percent` in `HealthConfig` + `config/default.yaml`; `run_diagnostics` passes them to `check_hardware`.
- Test: `test_run_diagnostics_uses_configured_ram_thresholds` (fails without the change: fields don't exist / defaults ignored).
- Suite: 49 passed (baseline 48, python3.12 venv).
- Remaining F073 gap: GPU/VRAM, per-service checks.
- Decision: supersedes the earlier "thresholds as function defaults" decision; defaults unchanged so behaviour is identical unless configured (reversible).

## 2026-11-08 — F073/F003 Ollama health check verifies configured model
- Gap: `OllamaProvider.health_check` reported healthy whenever the server answered `/api/tags`, even if the configured `model_name` was not installed (generate would then fail).
- Fix: health check now parses `/api/tags` and reports unhealthy (WARNING via diagnostics, echo fallback still available) when the model is absent; bare names match `:latest`; an unparseable list is treated as reachable.
- Test: `test_ollama_health_check_detects_missing_model` (fails without the change, verified via stash).
- Suite: 50 passed (baseline 49, python3.13; python3.12 venv unavailable this run).
- Remaining F073 gap: GPU/VRAM, per-service checks.

## 2026-11-08 — F009 de-duplicate review-inbox candidates
- Gap: submitting the same fact repeatedly created duplicate PENDING/APPROVED rows (inbox flooding, noted as a risk for future auto-extraction).
- Fix: `MemoryStore.submit_candidate` returns the existing PENDING/APPROVED entry when content matches (case/whitespace-insensitive), audited as `memory.duplicate_candidate`. REJECTED/retracted entries don't count, so they can be re-proposed.
- Test: `test_duplicate_candidate_is_not_stored_twice` (fails without the change, verified via stash).
- Suite: 51 passed (baseline 50, python3.12 venv).
- Decision: a duplicate submission keeps the original entry's source/confidence (no merge of provenance) — reversible; provenance merging can be added later.
