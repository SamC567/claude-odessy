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

## 2026-11-08 — F073/F001 validate health threshold ordering
- Gap: config accepted inverted warn/critical thresholds (e.g. disk warn 95 / critical 85), silently producing misleading health statuses.
- Fix: `model_validator` on `HealthConfig` in `odysseus/config.py`; load_config surfaces it as `ConfigError`.
- Test: `test_inverted_health_thresholds_are_rejected` (fails without the change, verified via stash).
- Suite: 52 passed (baseline 51, python3.13).
- Remaining F073 gap: GPU/VRAM, per-service checks.
- Decision: stricter validation could reject a user's existing odd config; defaults unaffected; reversible by removing the validator.

## 2026-11-08 — F009 CLI list-approved
- Gap: no way to see approved memories from the CLI, so `memory forget <id>` required knowing the id out-of-band.
- Fix: `memory list-approved` command in `odysseus/cli.py` (shows id, confidence, source, reviewer).
- Test: `test_cli_memory_list_approved_and_forget` (fails without the change: unknown subcommand).
- Suite: 53 passed (baseline 52, python3.13).

## 2026-11-08 — F009 blank query / non-positive limit
- Gap: `MemoryStore.query("")` matched every approved memory (`LIKE '%%'`) and a negative `limit` meant unlimited in SQLite.
- Fix: `query` returns `[]` for blank text or `limit <= 0`.
- Test: `test_blank_query_or_nonpositive_limit_returns_nothing` (fails without the change, verified via stash).
- Suite: 54 passed (baseline 53, python3.13).

## 2026-11-08 — F073 GPU/VRAM diagnostics
- Gap: no GPU/VRAM visibility in diagnostics (listed remaining F073 gap).
- Fix: `check_gpu` in `odysseus/health/diagnostics.py` (nvidia-smi local subprocess, injectable reader), wired into `run_diagnostics`.
- Test: `test_gpu_check_states_and_in_report` (fails without the change: no `check_gpu`).
- Suite: 55 passed (baseline 54, python3.11; no real GPU available in cloud run).
- Remaining F073 gap: per-service checks, configurable VRAM threshold.
- Decision: no GPU reported as OK (optional hardware); 5% free-VRAM warn threshold hardcoded, reversible.

## 2026-11-08 — F073 configurable VRAM threshold
- Gap: GPU free-VRAM warn threshold was hardcoded at 5%.
- Fix: `health.gpu_vram_warn_free_percent` in `HealthConfig` + `config/default.yaml`; `check_gpu(warn_free_percent=...)`, wired in `run_diagnostics`.
- Test: `test_gpu_vram_threshold_is_configurable` (fails without the change: no field/parameter).
- Suite: 56 passed (baseline 55, python3.11; 3.12 not the default interpreter here).
- Remaining F073 gap: per-service checks.
- Decision: supersedes the hardcoded-5% decision; default unchanged, reversible.

## 2026-11-09 — F073/F003 honour health.model_check_timeout_seconds
- Gap: `health.model_check_timeout_seconds` (default 3s) was configured but never used; diagnostics blocked for the provider's 10s generation timeout when Ollama was down.
- Fix: `ModelProvider.health_check(timeout_seconds=None)` (optional override; Echo/Ollama updated); `check_model_provider` / `run_diagnostics` pass the configured value. Providers whose `health_check(self)` lacks the parameter are still called the old way (compatibility).
- Tests: `test_ollama_health_check_timeout_override`, `test_run_diagnostics_passes_configured_model_check_timeout` (both fail without the change, verified via stash).
- Suite: 58 passed (baseline 56, python3.12 venv).
- Remaining F073 gap: per-service checks beyond the model provider.
- Decision: signature inspection used for backward compatibility instead of breaking the interface; reversible.

## 2026-11-09 — F073/F009 memory DB integrity in health check
- Gap: `memory_store` health check only counted rows; a corrupt SQLite file was not reported as such.
- Fix: `MemoryStore.integrity_check()` (PRAGMA quick_check, never raises) used by `check_memory_store` -> CRITICAL on failure.
- Test: `test_memory_store_check_detects_corrupt_database` (fails without the change, verified via stash).
- Suite: 59 passed (baseline 58, python3.13).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F073 disk check targets the memory DB volume
- Gap: `run_diagnostics` defaulted disk-space checking to the working directory, not the volume holding the memory DB.
- Fix: default path is `memory_store.db_path.parent` (fallback `.` if missing); explicit `disk_path` unchanged.
- Test: `test_disk_check_defaults_to_memory_db_volume` (fails without the change, verified via stash).
- Suite: 60 passed (baseline 59, python3.13).
- Remaining F073 gap: per-service checks beyond model provider and memory store.
- Decision: only the memory DB volume is checked by default (single path); multi-volume checks parked.

## 2026-11-09 — F009 atomic review transitions
- Gap: `_review` checked status then updated unconditionally (check-then-act race); a concurrent reviewer's decision could be overwritten.
- Fix: `UPDATE ... WHERE id = ? AND status = ?` plus rowcount check -> `ReviewInboxError` on loss.
- Test: `test_review_does_not_overwrite_concurrent_decision` (fails without the change, verified via stash).
- Suite: 61 passed (baseline 60, python3.12 venv).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F073/F003 config check surfaces blocked external Ollama
- Gap: a non-loopback `model.base_url` with external providers disallowed was silently swapped for the echo fallback; the `config` health check still said OK.
- Fix: `check_config` returns WARNING in that case (reuses `is_loopback_url`).
- Test: `test_config_check_warns_when_external_ollama_is_blocked` (fails without the change, verified via stash).
- Suite: 62 passed (baseline 61, python3.12 venv).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F009 Unicode case-insensitive retrieval
- Gap: `MemoryStore.query` used SQLite LIKE, which only folds ASCII, so "ärger" did not match "Ärger" (the duplicate check already used casefold).
- Fix: register a `fold` SQL function (`str.casefold`) and compare casefolded content/patterns.
- Test: `test_query_is_case_insensitive_for_non_ascii` (fails without the change, verified via stash).
- Suite: 63 passed (baseline 62, python3.11 venv).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F073 configurable pending-review warn threshold
- Gap: memory_store check warned at a hardcoded >100 pending review items.
- Fix: `health.pending_review_warn_count` (default 100) in `HealthConfig` + `config/default.yaml`; `check_memory_store(store, pending_warn_count)` wired in `run_diagnostics`.
- Test: `test_pending_review_warn_threshold_is_configurable` (fails without the change, verified via stash).
- Suite: 64 passed (baseline 63, python3.13).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F009 retrieval ignores punctuation around query words
- Gap: `MemoryStore.query` split on whitespace only, so a query word like `pizza?` never matched stored `pizza`.
- Fix: strip surrounding punctuation from query words before matching.
- Test: `test_query_ignores_punctuation_around_words` (fails without the change, verified via stash).
- Suite: 65 passed (baseline 64, python3.11).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F009 source tracking on answers
- Gap: `InteractionResult` returned memory context text only; callers/audit could not tell which entries (or sources) informed an answer.
- Fix: `InteractionResult.memory_sources` (id, source) per context item + audit event `orchestrator.memory_used`.
- Test: assertion added to `test_respond_includes_approved_memory_as_context` (fails without the change, verified via stash).
- Suite: 65 passed (baseline 65, python3.11 venv).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F003 non-object JSON from Ollama no longer escapes fallback
- Gap: `OllamaProvider.generate` called `data.get` on the decoded body; a JSON list/string raised `AttributeError`, which the orchestrator does not catch, so no echo fallback.
- Fix: non-dict body raises `ModelProviderError` (retry loop unchanged).
- Test: `test_ollama_provider_non_object_json_raises_provider_error` (fails without the change, verified via stash).
- Suite: 66 passed (baseline 65, python3.12 system interpreter).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F001/F009 orchestrator survives memory-store failure
- Gap: a `MemoryError_` from `MemoryStore.query` propagated out of `Orchestrator.respond`, contradicting the "every module degrades, not crashes" principle.
- Fix: `respond` catches it, answers without memory context, marks the result degraded ("memory unavailable: ...", combined with any provider failure reason) and audits `orchestrator.memory_failed`.
- Test: `test_respond_degrades_when_memory_query_fails` (fails without the change, verified via stash).
- Suite: 67 passed (baseline 66, python3.11).
- Remaining F073 gap: per-service checks beyond model provider and memory store.
- Decision: only `MemoryError_` is caught (not arbitrary exceptions), so programming errors still surface; reversible.

## 2026-11-09 — F009 corrupt memory row raises typed error
- Gap: a corrupt row (bad tags JSON/status/timestamp) raised a raw `ValueError` from `_row_to_entry`, bypassing the orchestrator's `MemoryError_` degradation.
- Fix: `_row_to_entry` wraps decoding errors in `MemoryError_`.
- Test: `test_corrupt_row_raises_typed_memory_error` (fails without the change, verified via stash).
- Suite: 68 passed (baseline 67, python3.13).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F073 crashed provider check keeps its stable name
- Gap: if a provider's `health_check` raised, the CRITICAL result was named `model_provider`, while the healthy/unhealthy paths use `model_provider:<name>`.
- Fix: `run_diagnostics` passes `model_provider:<name>` to `_safe_check`.
- Test: name assertion added to `test_a_failing_check_does_not_crash_the_whole_report` (fails without the change, verified via stash).
- Suite: 68 passed (baseline 68, python3.13).
- Remaining F073 gap: per-service checks beyond model provider and memory store.
- Decision: a raising `health_check` stays CRITICAL (existing tested behaviour); not changed.

## 2026-11-09 — F073 memory store check detects a read-only database
- Gap: `check_memory_store` passed on a read-only DB file (integrity check only reads), so diagnostics said OK while saving memories would fail.
- Fix: WARNING "memory database is not writable" when `os.access(db_path, W_OK)` is false.
- Test: `test_memory_store_check_warns_when_db_not_writable` (fails without the change, verified via stash).
- Suite: 69 passed (baseline 68, python3.11).
- Remaining F073 gap: per-service checks beyond model provider and memory store.
- Decision: WARNING not CRITICAL (system still answers read-only); reversible. Windows ACL-based read-only is only approximated by `os.access` (untested here).

## 2026-11-09 — F073 dependency check flags unsupported major versions
- Gap: `check_dependencies` reported OK for any installed version, e.g. pydantic 1.x which the code cannot run on.
- Fix: `SUPPORTED_MAJOR_VERSIONS` (mirrors requirements.txt); mismatched major -> WARNING (missing stays CRITICAL).
- Test: `test_dependencies_check_warns_on_unsupported_major_version` (fails without the change, verified via stash).
- Suite: 70 passed (baseline 69, python3.13).
- Remaining F073 gap: per-service checks beyond model provider and memory store.
- Decision: WARNING not CRITICAL, only major version checked (no full specifier parsing, stdlib only); reversible.

## 2026-11-09 — F009 CLI `memory remember` rejects invalid input cleanly
- Gap: `memory remember --confidence 2` (or empty content/source) escaped as a raw `ValueError` traceback.
- Fix: `cmd_memory_remember` catches `ValueError`, prints `error: ...` to stderr, returns exit code 2.
- Test: `test_cli_memory_remember_rejects_invalid_input_cleanly` (fails without the change, verified via stash).
- Suite: 71 passed (baseline 70, python3.12).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F009 review decisions require a named reviewer
- Gap: `approve`/`reject`/`retract` accepted a blank reviewer, so the review audit trail could record no accountable reviewer.
- Fix: `MemoryStore._review` raises `ReviewInboxError` for an empty/whitespace reviewer before touching the entry.
- Test: `test_review_requires_non_blank_reviewer` (fails without the change, verified via stash).
- Suite: 72 passed (baseline 71, python3.12).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F009 reviewer name is stored trimmed
- Gap: `approve`/`reject`/`retract` stored the reviewer verbatim, so "  sam " and "sam" were different identities in the audit trail.
- Fix: `MemoryStore._review` strips the reviewer after the blank check.
- Test: `test_review_records_trimmed_reviewer` (fails without the change, verified via stash).
- Suite: 73 passed (baseline 72, python3.11).
- Remaining F073 gap: per-service checks beyond model provider and memory store.

## 2026-11-09 — F001 config rejects unknown log_level
- Gap: `log_level: LOUD` passed config validation and then crashed CLI start-up with a raw `ValueError` from `logging.setLevel`.
- Fix: `OdysseusConfig.log_level` validator accepts DEBUG/INFO/WARNING/ERROR/CRITICAL (case-insensitive, normalised to upper case); otherwise `ConfigError`.
- Test: `test_unknown_log_level_is_rejected_and_known_is_normalised` (fails without the change, verified via stash).
- Suite: 74 passed (baseline 73, python3.12 venv).
- Remaining F073 gap: per-service checks beyond model provider and memory store.
- Decision: numeric/custom logging levels are not accepted (stdlib names only); reversible.

## 2026-11-09 — F003/F001 config rejects malformed model.base_url
- Gap: `model.base_url` accepted any string (`localhost:11434`, `ftp://x`, empty), failing only at request time inside the provider.
- Fix: `ModelProviderConfig.base_url` validator requires http(s) scheme and a host; value is trimmed.
- Test: `test_malformed_model_base_url_is_rejected` (fails without the change, verified via stash).
- Suite: 78 passed (baseline 74, python3.11).
- Remaining F073 gap: per-service checks beyond model provider and memory store.
- Decision: only http/https accepted (Ollama is HTTP); reversible.

## 2026-11-09 — F073 audit log writability check
- Gap: the audit trail (a governing principle) was never diagnosed; an unwritable log dir would silently drop audit records while `health` reported OK.
- Fix: `check_audit_log` + optional `audit_log_path` arg on `run_diagnostics`; CLI `health` passes `data/audit.log`. Missing log dir -> nearest existing parent is checked.
- Test: `test_audit_log_check_warns_when_not_writable_and_ok_otherwise` (fails without the change, verified via stash).
- Suite: 79 passed (baseline 78, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: WARNING not CRITICAL (the assistant still answers); optional arg keeps existing callers compatible; reversible.

## 2026-11-09 — F009 MemoryEntry validates tags
- Gap: `tags="food"` was silently stored as `["f","o","o","d"]`; blank/non-string tags were accepted.
- Fix: `MemoryEntry.__post_init__` rejects a bare string and blank/non-string items; lists are normalised to tuples.
- Test: `test_memory_entry_rejects_bad_tags` (fails without the change, verified via stash).
- Suite: 80 passed (baseline 79, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: strict rejection (ValueError, same as other fields) rather than coercion; reversible.

## 2026-11-09 — F073 audit log check detects wrong entry type
- Gap: `check_audit_log` reported OK when a regular file sat where the log directory should be, or a directory where the log file should be.
- Fix: OK requires the log path to be a file (if it exists) or its nearest existing ancestor to be a directory, as well as writable.
- Test: `test_audit_log_check_warns_when_path_is_wrong_kind_of_entry` (fails without the change, verified via stash).
- Suite: 81 passed (baseline 80, python3.11).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: WARNING (consistent with the existing audit_log check); reversible.

## 2026-11-10 — F009 query bounded for very long input
- Gap: `MemoryStore.query` with thousands of words raised a raw `sqlite3.OperationalError` (expression tree too large).
- Fix: terms capped at the first 50 distinct words plus the whole text (`_MAX_QUERY_TERMS`).
- Test: `test_query_with_very_long_text_does_not_crash` (fails without the change, verified via stash).
- Suite: 82 passed (baseline 81, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: cap of 50 terms is arbitrary; reversible constant.

## 2026-11-10 — F073 CLI health measures disk at the memory DB volume
- Gap: `cmd_health` passed `Path(".")` as `disk_path`, defeating the earlier fix that defaults disk checks to the memory DB's directory.
- Fix: CLI no longer passes `disk_path`.
- Test: `test_cli_health_measures_disk_at_memory_db_directory` (fails without the change, verified via stash).
- Suite: 83 passed (baseline 82, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: none beyond the above; reversible.

## 2026-11-10 — F001 explicit missing config path is an error
- Gap: `--config typo.yaml` silently fell back to defaults, so a mistyped path ran with the wrong model/memory settings.
- Fix: `load_config(path)` raises `ConfigError` when an explicitly given path is not a file; the default path stays optional. CLI reports it as `error: ...`, exit 2.
- Test: `test_explicit_missing_config_path_is_an_error` (fails without the change, verified via stash). `test_defaults_without_file` encoded the old behaviour and was changed to use an empty file (`test_defaults_with_empty_file`).
- Suite: 84 passed (baseline 83, python3.11).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: strict error for explicit paths only (changes prior documented "never raises" behaviour); reversible.

## 2026-11-10 — F009 store validates auto_approve_threshold
- Gap: only the config loader range-checked `auto_approve_threshold`; constructing `MemoryStore` directly with a negative value auto-approved every candidate, bypassing the review inbox.
- Fix: `MemoryStore.__init__` raises `ValueError` unless the threshold is None or a number (not bool) in 0..1.
- Test: `test_store_rejects_out_of_range_auto_approve_threshold` (fails without the change, verified via stash).
- Suite: 85 passed (baseline 84, python3.11).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: ValueError (same as MemoryEntry validation); reversible.

## 2026-11-10 — F009 MemoryEntry validates confidence type
- Gap: `confidence="0.5"`/`None` raised a raw `TypeError`; `True` was accepted as 1.0.
- Fix: `MemoryEntry.__post_init__` raises `ValueError` unless confidence is an int/float (not bool) in 0..1.
- Test: `test_memory_entry_rejects_non_numeric_confidence` (fails without the change, verified via stash).
- Suite: 86 passed (baseline 85, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: ValueError, consistent with other fields; reversible.

## 2026-11-10 — F009 query validates argument types
- Gap: `MemoryStore.query(None)` raised an obscure `AttributeError`, and a non-int `limit` a `TypeError` from a comparison deep inside.
- Fix: `query` raises a clear `TypeError` for non-str text or a non-int/bool limit.
- Test: `test_query_rejects_wrong_argument_types` (fails without the change, verified via stash).
- Suite: 87 passed (baseline 86, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: TypeError (programmer error, not data error); reversible.

## 2026-11-10 — F009 review decisions validate reviewer type
- Gap: `approve/reject/retract` with a non-string reviewer (e.g. an int) raised an obscure `AttributeError` from `.strip()`.
- Fix: `_review` raises `ReviewInboxError` unless reviewer is a non-blank `str`.
- Test: `test_review_rejects_non_string_reviewer` (fails without the change, verified via stash).
- Suite: 88 passed (baseline 87, python3.12/3.13 env).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: ReviewInboxError (same as blank reviewer); reversible.

## 2026-11-10 — F009 MemoryEntry validates content/source type
- Gap: `MemoryEntry(content=None|5, ...)` or non-string source raised an obscure `AttributeError` from `.strip()`.
- Fix: `__post_init__` raises `ValueError` unless both are `str`.
- Test: `test_memory_entry_rejects_non_string_content_and_source` (fails without the change, verified via stash).
- Suite: 89 passed (baseline 88, python3.12).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: ValueError, consistent with other field checks; reversible.

## 2026-11-10 — F003 ollama config rejects blank model_name
- Gap: `provider: ollama` with a blank `model_name` loaded fine and only failed at request time.
- Fix: `ModelProviderConfig` model validator raises (-> `ConfigError`) for blank model_name when provider is ollama; echo unaffected.
- Test: `test_ollama_provider_rejects_blank_model_name` (fails without the change, verified via stash).
- Suite: 90 passed (baseline 89, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: considered making a raising provider health_check a WARNING, but an existing test deliberately asserts CRITICAL; left unchanged.

## 2026-11-10 — F003 base_url rejects embedded credentials
- Gap: `model.base_url: http://user:pass@host` loaded fine; the URL is echoed in diagnostics/audit output, so credentials would leak and live in the config file.
- Fix: `ModelProviderConfig` base_url validator raises (-> `ConfigError`) when the URL has a username or password.
- Test: `test_model_base_url_rejects_embedded_credentials` (fails without the change, verified via stash).
- Suite: 91 passed (baseline 90, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: reject rather than strip/redact (never silently alter credentials); reversible.

## 2026-11-10 — F073 crashed-check detail names the exception type
- Gap: a check that raised (e.g. `KeyError('x')`) was reported as `check raised: 'x'`, with no hint of the error type.
- Fix: `_safe_check` detail is now `check raised <ExceptionType>: <message>`.
- Test: `test_safe_check_failure_detail_names_exception_type` (fails without the change, verified via stash).
- Suite: 92 passed (baseline 91, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: wording change only; existing tests assert on message substrings and still pass; reversible.

## 2026-11-10 — F073 empty health report is not "OK"
- Gap: `HealthReport` with zero checks reported `overall_status` OK, claiming health with no evidence.
- Fix: empty report -> WARNING.
- Test: `test_empty_report_is_not_reported_healthy` (fails without the change, verified via stash).
- Suite: 93 passed (baseline 92, python3.13; note `python` lacked deps, used `python3.13 -m pytest`).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: WARNING rather than CRITICAL (no check failed, just no evidence); reversible.

## 2026-11-10 — F009 submit_candidate validates argument type
- Gap: `submit_candidate(None)` / a non-MemoryEntry raised an obscure `AttributeError` on `.content`.
- Fix: raises a clear `TypeError` up front.
- Test: `test_submit_candidate_rejects_non_memory_entry` (fails without the change, verified via stash).
- Suite: 94 passed (baseline 93, python3.11 after `pip install -r requirements-dev.txt`).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: TypeError (programmer error), consistent with `query`; reversible.

## 2026-11-10 — F009 read paths raise typed MemoryError_
- Gap: `query/get/list_*/count_by_status` let raw `sqlite3.DatabaseError` escape on a corrupt DB, bypassing the orchestrator's `except MemoryError_` degradation (writes were already wrapped).
- Fix: shared `MemoryStore._read` helper converts `sqlite3.Error` to `MemoryError_`; used by all read methods.
- Test: `test_read_paths_raise_typed_error_on_corrupt_database` (fails without the change, verified via stash).
- Suite: 95 passed (baseline 94, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: no behaviour change on healthy DBs; reversible.

## 2026-11-10 — F073 health CLI survives a corrupt memory DB
- Gap: `odysseus.cli health` built the MemoryStore up front, so a corrupt DB aborted with `error: ...` and no report — diagnostics failed exactly when needed.
- Fix: `cmd_health` catches `MemoryError_`, still builds config/provider, and `run_diagnostics(memory_store=None, memory_store_error=...)` emits a CRITICAL `memory_store` check alongside all other checks (exit 1).
- Test: `test_cli_health_reports_corrupt_memory_db_instead_of_erroring` (fails without the change, verified via stash).
- Suite: 96 passed (baseline 95, python3.13).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: exit code 1 (CRITICAL) retained; signature change is backwards compatible (new optional kwarg); reversible.

## 2026-11-11 — F001 chat CLI no longer misreports a memory-only degradation as a provider fallback
- Gap: `InteractionResult.degraded` covers both memory failure and provider fallback, and `chat` printed `(degraded: fell back to <provider_used>; ...)` for either — so with memory unavailable but the primary model answering, it claimed a fallback that never happened.
- Fix: `InteractionResult.used_fallback` (additive, default False) set only on the provider-fallback path; the CLI prints "fell back to ..." only when it is true.
- Test: `test_used_fallback_distinguishes_provider_fallback_from_memory_degradation`, `test_cli_chat_memory_only_degradation_does_not_claim_provider_fallback` (both fail without the change, verified via stash).
- Suite: 98 passed (baseline 96, python3.12 venv — system pip is PEP 668-managed, so deps were installed into a throwaway venv outside the repo).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: added a new field rather than changing the meaning of `degraded` (keeps existing consumers working); reversible.

## 2026-11-11 — F001 `ODYSSEUS_LOG_LEVEL` env override is honoured
- Gap: `config/.env.example` documents `ODYSSEUS_LOG_LEVEL=DEBUG`, but `_apply_env_overrides` only applied `SECTION__FIELD` names, so the top-level `log_level` could not be set from the environment and the variable was silently ignored.
- Fix: single-segment env names are applied for top-level scalar fields (`_TOP_LEVEL_SCALAR_FIELDS`, currently just `log_level`); the value goes through the existing `log_level` validation. Single-segment section names (`ODYSSEUS_MODEL`) and unknown names are still ignored.
- Test: `test_env_override_top_level_log_level` (fails without the change, verified via stash), `test_env_single_segment_section_name_is_ignored` (guard; passes before and after).
- Suite: 100 passed (baseline 98, python3.12 venv outside the repo).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: explicit allow-list of top-level scalars rather than accepting any single-segment name (a stray `ODYSSEUS_MODEL=x` must not replace a whole section); an invalid value is a `ConfigError`, same as in YAML; reversible.

## 2026-11-11 — F003/F073 Ollama health check survives a null/malformed model list
- Gap: `OllamaProvider.health_check` iterated `resp.json().get("models", [])` directly, so `{"models": null}` (a server with nothing installed) or a non-list value raised `TypeError` out of a method whose contract is "without raising"; diagnostics then showed a crashed check (CRITICAL) instead of the real state.
- Fix: null is treated as an empty list ("model not installed", unhealthy); a non-list `models` is "model list unreadable" (reachable, same as unparseable JSON); entries whose `name` is not a string are skipped.
- Test: `test_ollama_health_check_handles_null_or_malformed_model_list` (fails without the change, verified via stash).
- Suite: 101 passed (baseline 100, python3.12 venv outside the repo).
- Not verified: whether a given real Ollama version actually sends `"models": null`; simulated server only, as for the rest of `OllamaProvider`.
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: a non-list `models` reports reachable/"unreadable" rather than "model missing", matching the existing policy for an unparseable body (do not claim a model is missing without evidence); reversible.

## 2026-11-11 — F009 retrieval ranks by matched terms before confidence
- Gap: `MemoryStore.query` matched any entry containing any query word of 3+ letters and ordered purely by confidence; with the orchestrator's context limit of 3, high-confidence entries sharing only a common word ("the", "what") crowded the relevant entry out of the model's context.
- Fix: `ORDER BY` now starts with the count of distinct query patterns matched (same LIKE terms as the filter), then confidence, then recency. Which entries match is unchanged; only their order (and therefore which survive `limit`) changes. No API or schema change.
- Test: `test_query_ranks_entries_matching_more_terms_first` (fails without the change, verified via stash).
- Suite: 102 passed (baseline 101, python3.12 venv outside the repo).
- Not done: stop-words, term weighting, stemming, FTS5 — the keyword/substring limitation in ARCHITECTURE.md is narrowed, not closed.
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: every pattern (including the whole-text one) counts 1, no extra weight for a whole-text match — the simplest rule that is easy to reason about and to replace with FTS5 later; reversible.

## 2026-11-11 — F001/F073 unusable audit log location no longer crashes every command
- Gap: `configure_logging` let `OSError` escape when `data/audit.log` could not be created or opened (reproduced: a regular file named `data` in the working directory -> `FileExistsError` traceback from `python -m odysseus.cli health`). Every CLI command failed, including `health`, whose `audit_log` check is meant to report this condition as a WARNING.
- Fix: `configure_logging` catches `OSError` from creating the directory / opening the file, attaches a stderr handler to the audit logger instead, and logs a WARNING on the `odysseus` logger that audit records are not persisted. No signature change.
- Test: `test_cli_survives_unusable_audit_log_location` (fails without the change, verified via stash).
- Suite: 103 passed (baseline 102, python3.12 venv outside the repo).
- Not verified: Windows permission/ACL failures (only the file-in-place-of-directory case is exercised; other `OSError`s take the same code path).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.

### Decisions
- Degrade to stderr (fail open) rather than refuse to run without a durable audit trail (fail closed). Reason: `check_audit_log` already classifies this state as WARNING, not CRITICAL, and the architecture rule is "every module degrades, not crashes"; diagnostics must be runnable to show the problem. Cost: in this state autonomous actions (memory writes, review decisions) proceed with audit records on stderr only. If you would rather block state-changing commands (`memory remember/approve/reject/forget`) when the audit log is not durable, say so — that is a small follow-up and this change is easily reverted.

## 2026-11-11 — F001 `chat` CLI rejects a blank prompt cleanly
- Gap: `python -m odysseus.cli chat "   "` (or `""`) ended in a `ValueError: prompt must not be empty` traceback: `Orchestrator.respond` raises `ValueError` for a blank prompt, and `main` only translates `OdysseusError`. `memory remember` already handled its own invalid input; `chat` did not.
- Fix: `cmd_chat` catches `ValueError` from `respond`, prints `error: ...` to stderr and returns exit code 2. No change to `Orchestrator` or to any interface.
- Test: `test_cli_chat_rejects_blank_prompt_cleanly` (fails without the change, verified via stash).
- Suite: 104 passed (baseline 103, python3.12 venv outside the repo).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: handled in the CLI rather than making `respond` raise an `OdysseusError` subclass — changing the exception type would be an interface change for existing callers; reversible.

## 2026-11-11 — F003 Ollama errors carry the server's explanation
- Gap: on an HTTP error from `/api/generate`, `OllamaProvider.generate` reported only the status line (`404 Client Error: Not Found for url ...`). Ollama puts the actual reason in a JSON body (`{"error": "model 'x' not found, try pulling it first"}`), which was discarded, so the `chat` degraded reason and the `orchestrator.provider_failed` audit record did not say why the local model was skipped.
- Fix: `_server_error_message` reads the `error` string from the error response (never raises; ignores a missing/non-JSON/non-object body and a blank or non-string value), collapses whitespace, caps it at 200 characters, and `generate` appends it as `(server said: ...)`. Still a `ModelProviderError`; no interface change; retry behaviour unchanged.
- Test: `test_ollama_provider_error_includes_server_explanation` (fails without the change, verified via stash), `test_ollama_provider_error_tolerates_unusable_error_body` (5 cases) and `test_ollama_provider_error_truncates_long_server_explanation` (guards).
- Suite: 111 passed (baseline 104, python3.12 venv outside the repo).
- Not verified: the error body shape against a live Ollama process — simulated server only, as for the rest of `OllamaProvider`.
- Not done: HTTP 4xx responses are still retried `max_retries` times like any other request failure, although a retry cannot fix a missing model.
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.

### Decisions
- The server's text is included in the error (and therefore in the audit log and the `chat` stderr line) rather than only logged at DEBUG. Reason: it comes from the configured model server (loopback unless `allow_external_providers` is set), it is the only place the cause is stated, and it is length-capped. If you would rather keep third-party text out of the audit log, revert this one commit.

## 2026-11-11 — F003 Ollama does not retry a permanent 4xx
- Gap: recorded as "Not done" in the previous entry — `OllamaProvider.generate` retried every HTTP error `max_retries` times, including a 404 for a model that has not been pulled. The retries could not succeed, delayed the fallback to the echo provider by one full request per retry, and the message claimed `max_retries + 1` attempts whatever happened.
- Fix: `_is_permanent_client_error` (never raises) classifies a response with an integer `status_code` in 400–499, other than 408 and 429, as not worth retrying; `generate` stops after that attempt. 5xx, 408, 429, timeouts, unparseable bodies and an error with no readable status keep the previous retry behaviour. The `ModelProviderError` text now carries the number of attempts actually made. Exception types, signature and config keys unchanged.
- Test: `test_ollama_provider_does_not_retry_a_permanent_client_error` (fails without the change, verified via stash) and `test_ollama_provider_still_retries_transient_http_errors` (5 cases, guards the unchanged retry paths).
- Suite: 117 passed (baseline 111, python3.12 venv outside the repo).
- Not verified: status codes a live Ollama process actually returns — simulated server only, as for the rest of `OllamaProvider`.
- Not done: no backoff/delay between retries (there was none before either); `Retry-After` on 429 is ignored.
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: 408 and 429 stay retryable and an unknown status is treated as transient — the conservative choice that changes behaviour only where a retry is known to be futile; reversible.

## 2026-11-11 — F009/F073 uncreatable memory DB directory raises the typed error
- Gap: `MemoryStore.__init__` called `db_path.parent.mkdir(...)` unguarded. With a regular file where the data directory should be (or an unwritable parent) a raw `FileExistsError`/`NotADirectoryError`/`PermissionError` escaped; `main` only translates `OdysseusError`, so every command — including `health`, which already has a CRITICAL `memory_store` path for an unopenable store — died with a traceback. The store's own docstring promises all failures are `MemoryError_`.
- Fix: the `mkdir` is wrapped; `OSError` becomes `MemoryError_("Could not create memory database directory ...")` naming the original exception type. No signature, schema or config change.
- Test: `test_store_raises_typed_error_when_db_directory_cannot_be_created` and `test_cli_reports_uncreatable_memory_db_directory` (both fail without the change, verified via stash).
- Suite: 119 passed (baseline 117, python3.12 venv outside the repo).
- Not verified: Windows permission/ACL failures (only the file-in-place-of-directory case is exercised; other `OSError`s take the same code path).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: the exception type for this failure changes from `OSError` to `MemoryError_`. Nothing in this repo caught `OSError` from the constructor and the documented contract was already `MemoryError_`, so this is treated as a bug fix rather than an interface change; reversible by reverting this commit.

## 2026-11-11 — F009 `chat` CLI shows which memories informed the answer
- Gap: source tracking stopped at the API. `Orchestrator.respond` returns `memory_sources` (entry id + source) and audits `orchestrator.memory_used`, but `cmd_chat` printed only the answer, so from the CLI there was no sign that approved memory had been injected into the prompt, and no way to find the id to `memory forget` when an answer was shaped by a wrong fact (short of reading `data/audit.log`).
- Fix: `cmd_chat` prints `(memory used: [id] source=...; ...)` to stderr when `result.memory_sources` is non-empty. CLI only; no change to `Orchestrator`, `MemoryStore`, config or any interface.
- Test: `test_cli_chat_reports_which_memories_informed_the_answer` (fails without the change, verified via stash) and `test_cli_chat_cites_no_memory_when_none_was_used` (guard: silent when no memory was used).
- Suite: 121 passed (baseline 119, python3.12 venv outside the repo).
- Not done: the cited line shows id and source only, not confidence or content; `source` is printed as stored (no escaping of control characters, same as `memory list-pending`).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.

### Decisions
- The line is always printed (no `--sources` flag) and goes to stderr. Reason: stdout — the answer — stays byte-for-byte unchanged for anything that parses it, and showing by default is the transparent choice for a privacy-first assistant. If you would rather have it opt-in or on stdout, say so; reversible by reverting this one commit.

## 2026-11-11 — F009 rejected/retracted memories can be listed
- Gap: the review workflow had no read path for its negative decisions. `reject` and `retract` keep the row (with `reviewer` and `reviewed_at`) precisely so the decision stays inspectable, but `MemoryStore` only exposed `list_pending` / `list_approved` and the CLI only `list-pending` / `list-approved`. After `memory forget 3` there was no command that showed entry 3 again, who withdrew it, or when.
- Fix: `MemoryStore.list_rejected()` (same `_list_by_status` path as the other two) and CLI `memory list-rejected`, printing id, confidence, source, reviewer, review time and content. Additive and read-only; no schema, config or existing-interface change. README command list updated.
- Test: `test_list_rejected_shows_rejected_and_retracted_with_reviewer` and `test_cli_memory_list_rejected_shows_decision_trail` (both fail without the change, verified via stash).
- Suite: 123 passed (baseline 121, python3.12 venv outside the repo).
- Not done: the listing cannot tell a rejection from a retraction (both are REJECTED; see the 2026-11-08 decision not to add an enum value) — the audit log's `previous=` field still can. No paging/limit for a large rejected set. `source`/`content` are printed as stored (no control-character escaping, same as the other list commands).
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.

## 2026-11-11 — F009 `memory show <id>` displays an entry's full record
- Gap: part of what F009 stores was write-only from the CLI. `memory remember --tags ...` persists tags and every entry has a `created_at`, but none of `list-pending` / `list-approved` / `list-rejected` prints either, and there was no single-entry view, so checking an entry's tags or when it was proposed meant opening SQLite. `MemoryStore.get` existed but had no CLI caller.
- Fix: CLI `memory show <id>` prints content, status, source, confidence, tags, created, reviewer and reviewed (UTC ISO timestamps, `-` when unset). Read-only, calls the existing `MemoryStore.get`; an unknown id prints `error: No memory entry with id=N` to stderr and exits 2 (same convention as other invalid input). No store, schema, config or existing-interface change. README command list and the `cli.py` usage docstring updated (the docstring also gains the previously missing `memory forget`).
- Test: `test_cli_memory_show_displays_full_record_including_tags` and `test_cli_memory_show_unknown_id_is_a_clean_error` (both fail without the change, verified via stash).
- Suite: 125 passed (baseline 123, python3.12 venv outside the repo).
- Not done: tags are still not searched by `MemoryStore.query` (content only) — that would change which memories are injected into prompts, so it is left as a separate, deliberate change. `content`/`source`/tags are printed as stored (no control-character escaping, same as the list commands). No `--json` output for `show`.
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.
- Decision: no audit record for `show` — it is a read, and the existing list commands are not audited either; reversible.

## 2026-11-11 — F001/F073 audit log location is configurable

- Gap: the audit log path was the hardcoded literal `"data/audit.log"` in three places in `cli.py` (two `configure_logging` calls and the `health` check), relative to the working directory. It could not be moved (e.g. to another drive or next to a relocated `memory.db_path`), contradicting "configuration separated from application logic" (F001), and `health` could only ever check that one location (F073).
- Fix: new top-level config field `audit_log_path` (default `data/audit.log`, so behaviour is unchanged), overridable with `ODYSSEUS_AUDIT_LOG_PATH`; the CLI passes it to `configure_logging` and to `run_diagnostics`. Blank values are rejected with `ConfigError`. `config/default.yaml` and `config/.env.example` updated. No interface of `configure_logging`, `run_diagnostics` or `check_audit_log` changed.
- Test: `test_cli_audit_log_path_is_configurable` (trail written to the configured file, nothing at the old location, `health` reports the configured path) and `test_audit_log_path_default_file_env_and_blank` (both fail without the change, verified via stash).
- Suite: 127 passed (baseline 125, python3.12 venv outside the repo, cloud sandbox).
- Not done: relative `audit_log_path` / `memory.db_path` are still resolved against the working directory, not the project root, although the `memory.db_path` description says "project root" (recorded in ARCHITECTURE.md). Windows path handling of the new field is untested here.
- Remaining F073 gap: per-service checks beyond model provider, memory store and audit log.

### Decisions

- Left working-directory-relative resolution as is rather than anchoring relative paths to the project root: anchoring would make an existing install started from another directory switch to a different (apparently empty) memory database and audit log. That needs the user's choice; veto/decide: (a) anchor to project root, (b) keep CWD and fix the field description.
- Placed `audit_log_path` at the top level next to `log_level` (no new config section); reversible.

## 2026-11-11 — F073/F003 `health` checks the fallback provider too

- Gap: diagnostics covered only the primary model provider. `Orchestrator` always holds a second provider (`fallback_provider`, the built-in `EchoProvider` by default) that answers when the primary fails, but `run_diagnostics` took one provider and `health` never looked at the other. A report with `model_provider:ollama: warning` therefore said nothing about whether `chat` would still get an answer.
- Fix: `run_diagnostics(..., fallback_provider=None)` adds a `fallback_provider:<name>` check (new `check_fallback_provider`, reusing `check_model_provider` and the configured `health.model_check_timeout_seconds`); `cmd_health` passes `orchestrator.fallback_provider` (and a default `EchoProvider()` on the corrupt-memory path, the same default the orchestrator uses). Unhealthy fallback = WARNING while the primary is OK, CRITICAL when the primary is not OK either. Additive: the parameter is optional and keyword-compatible, no existing check name, status or config changed; the check is skipped when the fallback is the same object as the primary.
- Test: `test_fallback_provider_gets_its_own_check`, `test_unhealthy_fallback_is_warning_alone_and_critical_with_unhealthy_primary` (tests/test_health.py) and `test_cli_health_reports_the_fallback_provider` (tests/test_cli.py: text, `--json` and corrupt-DB paths). All three fail without the change (verified via stash: 3 failed, 127 passed).
- Suite: 130 passed (baseline 127, python3.12 venv outside the repo, cloud sandbox).
- Not done: the fallback is not configurable (it is always the built-in echo provider from the CLI), so in a default install the new check is always OK and the WARNING/CRITICAL branches are exercised only by test doubles. `health` output gains one line / one JSON entry — anything that asserted an exact check count would notice (nothing in this repo does).
- Remaining F073 gap: no checks for services other than model providers, memory store and audit log — Milestone A defines no other services, so this may simply be complete for now; the user's call.

### Decisions

- Both-unhealthy is CRITICAL (so `health` exits 1). Reason: with neither provider able to answer, `chat` cannot work at all, which is a different state from "optional model down, fallback fine" (WARNING). Unreachable with the built-in echo fallback; reversible by reverting this commit.
- Separate name prefix `fallback_provider:` rather than a second `model_provider:` entry: in the default config both are `echo`, and two checks with the same name would be ambiguous for anything keying on names; reversible.
- Still awaiting the user's choice from the previous entry: relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-11 — F009 retrieval ignores stop words as search terms

- Gap: listed limitation "no stop-word list". `MemoryStore.query` used every word of three or more letters as a substring term, so a question such as "What is the capital of France?" matched every approved entry containing "the" or "what". Ranking (earlier run) put the relevant entry first, but whenever fewer relevant entries existed than the orchestrator's limit of 3, the remaining slots were filled with unrelated memories, which were then injected into the model prompt and reported as `memory used`.
- Fix: a small built-in English stop-word list (`_STOP_WORDS`, `odysseus/memory/store.py`); those words are dropped from the per-word terms (case-insensitive). The whole query text is still matched as a substring, so `query("the")` and phrases containing a stop word are unchanged. No interface, schema or config change.
- Test: `test_query_ignores_stop_words_as_search_terms` (fails without the change, verified via stash: 1 failed, 130 passed). The fixture of the existing `test_query_ranks_entries_matching_more_terms_first` was changed: its three high-confidence distractors shared only the word "the" with the query and are, by design, no longer returned, so they now share the non-stop word "capital" instead. Its assertions are unchanged and it passes both with and without this change.
- Suite: 131 passed (baseline 130, python3.12 venv outside the repo, cloud sandbox).
- Not done: the list is English-only and not configurable; a query consisting only of stop words and words under three letters ("What is this about?") now returns nothing unless the whole text matches. Substring matching ("cat" matches "category"), term weighting and stemming are unchanged. Tags are still not searched.
- Remaining F073 gap: unchanged from the previous entry (no services beyond model providers, memory store and audit log are defined in Milestone A).

### Decisions

- Behaviour change to which memories reach the prompt, made without asking: fewer (unrelated) entries are injected, none that matched a topical word are lost. Reason: injecting unrelated personal facts into prompts is the less safe default. Reversible by reverting this commit; veto if the old behaviour is wanted.
- Left "will", "can", "may" and similar out of the list (also names/nouns), and kept the list hardcoded rather than adding a config key; reversible.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-11 — F009 retrieval searches tags as well as content

- Gap: noted as "not done" in three earlier entries ("Tags are still not searched"). `memory remember --tags` stored tags and `memory show` displayed them, but `MemoryStore.query` matched content only, so tagging an entry had no effect on retrieval: an entry "Peanuts must be avoided" tagged `allergy` was not found by "any allergy?" and never reached the model prompt.
- Fix: `query` matches each term against the content plus the decoded tags (new module helper `_searchable_text`, registered as the SQL function `searchable(content, tags)`, replacing the internal `fold`). Same rules as for content: case-insensitive including non-ASCII, substring, stop words ignored, approved-only. A term present in both content and a tag counts once, so ranking by distinct matched terms is unchanged. A unit-separator between the fields stops a phrase matching across the content/tag boundary. No change to the `MemoryStore` interface, schema, config or CLI.
- Test: `test_query_matches_tags_as_well_as_content` and `test_query_survives_unreadable_tags_on_a_non_matching_row` (tests/test_memory.py). Both fail without the change (verified via stash: 2 failed, 131 passed). Also run once by hand through the CLI in a scratch directory (remember with `--tags allergy`, approve, `chat "any allergy?"` printed `(memory used: [1] source=user-note)`), echo fallback only — no live model.
- Suite: 133 passed (baseline 131, python3.12 venv outside the repo, cloud sandbox).
- Not done: tag matches are not weighted above content matches; no tag-only filter ("list everything tagged X") in the store or CLI; substring matching applies to tags too ("cat" matches the tag "category"). Nothing was run against an existing real database or on Windows.
- Remaining gaps: F073 unchanged (no services beyond model providers, memory store and audit log are defined in Milestone A). F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Behaviour change to which memories reach the prompt, made without asking: approved entries are now also retrieved by their tags, so more entries can be injected than before (the opposite direction from the stop-word change). Reason: tags are entered by the user precisely to file an entry under a word, only approved entries are affected, and the orchestrator's limit of 3 still applies. Reversible by reverting this commit; veto if tags should stay display-only.
- An unreadable (non-JSON) tags value on a row is ignored for matching rather than failing every query; the row still raises `MemoryError_` when it is returned (existing behaviour). Reversible.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-11 — F009 memory listings show control characters instead of obeying them

- Gap: noted as "not done" in three earlier entries (`source`/`content` "printed as stored, no control-character escaping"). The review inbox is where a human decides what becomes permanent memory, but `memory list-pending` printed stored text raw: a candidate whose content contained a newline produced a second line that looked like another entry (`[99] (0.99, user) ...`), and terminal escape sequences (`ESC[2K`, carriage return) or a right-to-left override could erase or reorder what the reviewer saw. The same applied to `list-approved`, `list-rejected`, `show` and the `(memory used: ...)` line of `chat`.
- Fix: new `cli._printable` renders control characters (Unicode category Cc), line/paragraph separators and bidirectional-text controls as backslash escapes (`\n`, `\x1b`, `\u202e`); the five outputs above pass content, source, tags and reviewer through it. Display only — nothing in `MemoryStore`, retrieval or the model prompt changed. Standard library only (`unicodedata`).
- Test: `test_cli_memory_listings_cannot_be_spoofed_by_control_characters` (fails without the change — verified via stash: 1 failed, 134 passed) and `test_cli_memory_listings_leave_ordinary_text_untouched` (accents, CJK, emoji with modifier, Windows-style backslash path print byte-for-byte as before; this one passes with or without the change — it guards against over-escaping). Both in tests/test_cli.py.
- Suite: 135 passed (baseline 133, python3.12 venv outside the repo, cloud sandbox).
- Not done: the model's reply printed by `chat`, `health` check details and error messages are not escaped. A literal backslash is not doubled, so typed `\n` (two characters) and an escaped newline look identical. Zero-width and other format characters (ZWSP, ZWJ, ...) are left alone. Not checked on a real terminal or on Windows — only captured output was asserted.
- Remaining gaps: F073 unchanged (no services beyond model providers, memory store and audit log are defined in Milestone A). F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Escaping is applied at the CLI only, not in `MemoryStore` or `MemoryEntry` (no rejection or stripping of control characters at submission). Reason: rejecting or altering stored content is a behaviour change to what can be remembered and to existing rows; changing only the display is the reversible option. Veto if control characters should instead be refused when a candidate is submitted.
- Zero-width format characters are deliberately not escaped (they are part of ordinary Persian/Indic text and emoji sequences); only bidi controls are. Reversible by extending `_BIDI_CONTROLS`.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-11 — F001/F009 memory context limit is configurable

- Gap: how many approved memories reach the model prompt was the literal `3` in `Orchestrator.__init__`'s default; `cli._build_orchestrator` never passed anything else, so no config file or environment variable could change it ("the orchestrator's limit of 3" in several earlier entries). A user with a larger local model could not let more facts in, and there was no way to run `chat` with memory kept out of the prompt short of retracting every entry.
- Fix: `MemoryConfig.context_limit` (default 3, 0-50; a bool, a fractional number or an out-of-range value is a `ConfigError`), passed by the CLI to the existing `Orchestrator(memory_context_limit=...)` parameter. `0` means no approved memory is added to the prompt (`MemoryStore.query` already returns nothing for a limit of 0); memory stays stored and reviewable. Documented in `config/default.yaml` and `config/.env.example`. No interface or schema change; default behaviour unchanged.
- Test: `test_memory_context_limit_defaults_to_three_and_is_overridable`, `test_memory_context_limit_rejects_unusable_values` (6 cases) in tests/test_config.py; `test_cli_chat_obeys_configured_memory_context_limit`, `test_cli_chat_memory_context_limit_zero_keeps_memory_out_of_the_prompt` in tests/test_cli.py. All fail without the change (verified by stashing `odysseus/` and `config/`: 9 failed, 135 passed).
- Suite: 144 passed (baseline 135, python3.12 venv outside the repo, cloud sandbox).
- Not done: the limit counts entries, not characters/tokens. `Orchestrator` does not validate a `memory_context_limit` passed directly in code. Not run on Windows.
- Remaining gaps: F073 unchanged (no services beyond model providers, memory store and audit log are defined in Milestone A). F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Upper bound of 50 and allowing 0 ("memory off for prompts") were chosen without asking. Reason: 0 is the privacy-conservative end and the default stays 3, so nothing changes unless the value is set; 50 is an arbitrary guard against a typo flooding the prompt. Reversible by editing the `Field` bounds; veto either.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-11 — F003 loopback Ollama requests bypass environment proxies

- Gap: `OllamaProvider` used a default `requests.Session`, which applies `HTTP_PROXY` / `ALL_PROXY` from the environment to every request unless `NO_PROXY` lists the host. With a proxy variable set (common on corporate or VPN setups) and `localhost` not in `NO_PROXY`, the request to the local model server, prompt and approved-memory context included, was sent to the proxy. That contradicts the module's own "no prompt data leaves the machine through this provider" statement and CLAUDE.md's local-first rule, and it also made a running local model look unreachable. Reproduced before the fix with a recording loopback "proxy": it received the `/api/generate` POST.
- Fix: when `OllamaProvider` creates its own session and `base_url` is loopback, it sets `session.trust_env = False` (direct connection, no environment proxies). `is_loopback_url` moved from `registry.py` to the new `odysseus/models/loopback.py` to avoid a circular import; `registry.py` re-exports it, so `odysseus.health.diagnostics` and any other importer are unaffected. No interface, config or schema change.
- Test: `test_ollama_loopback_requests_bypass_environment_proxy` (two in-process loopback HTTP servers, one acting as the proxy; asserts the proxy receives nothing and `generate` / `health_check` succeed), `test_ollama_non_loopback_session_keeps_environment_proxy_settings`, `test_ollama_leaves_a_caller_supplied_session_untouched` in tests/test_models.py. The first two fail without the change (verified by stashing `odysseus/`: 2 failed, 145 passed); the third is a guard that passes either way.
- Suite: 147 passed (baseline 144, python3.12 venv outside the repo, cloud sandbox).
- Not done: a caller-supplied session is not altered. A non-loopback `base_url` keeps honouring proxy variables. Not run on Windows (there `requests` also consults the system proxy settings; `trust_env = False` skips those too, but this was not exercised). Not tested against a real proxy or a live Ollama.
- Remaining gaps: F073 unchanged. F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Non-loopback Ollama URLs keep using environment proxies. Reason: such a URL is only reachable after the user sets `identity.allow_external_providers: true`, and a remote server may legitimately need the proxy; changing that would be a behaviour change nobody asked for. Reversible in one line; veto if all Ollama traffic should be direct.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-11 — F003 loopback Ollama requests do not follow redirects

- Gap: `OllamaProvider` let `requests` follow HTTP redirects (its default, up to 30). A 307/308 response from whatever answers on the configured loopback port made the provider re-send the `/api/generate` POST, prompt and approved-memory context included, to the redirect target, which can be any host. That contradicts the module's "no prompt data leaves the machine through this provider" statement and CLAUDE.md's local-first rule, and the `identity.allow_external_providers` gate only inspects the configured `base_url`, not where a request ends up. `health_check` followed redirects too, so a server elsewhere could be reported as the healthy local one. Reproduced before the fix with two loopback servers: the redirect target received the POST body.
- Fix: when `OllamaProvider` creates its own session for a loopback `base_url`, it sets `session.max_redirects = 0` (next to the existing `trust_env = False`); `requests` then raises `TooManyRedirects` before sending anything to the target. `generate` turns that into a `ModelProviderError` that names the target and is not retried; `health_check` returns `(False, "No Ollama server at ...: the server answered with a redirect to '...', which was not followed")`. No interface, config or schema change.
- Test: `test_ollama_loopback_requests_do_not_follow_redirects` (two in-process loopback HTTP servers; asserts the target receives nothing, one attempt per call, error and health detail name the redirect) and `test_ollama_redirect_policy_applies_only_to_its_own_loopback_session` in tests/test_models.py. Both fail without the change (verified by stashing `odysseus/`: 2 failed, 147 passed).
- Suite: 149 passed (baseline 147, python3.12 venv outside the repo, cloud sandbox).
- Not done: a caller-supplied session is not altered. A non-loopback `base_url` still follows redirects. Not run on Windows. Not tested against a live Ollama (a real Ollama does not redirect these endpoints as far as I know; not verified here).
- Remaining gaps: F073 unchanged. F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Redirects are refused outright for a loopback server, including a redirect to another loopback address. Reason: simplest rule that cannot leak, and a local Ollama has no reason to redirect; the cost is that a local reverse proxy that redirects (e.g. http to https) now fails with a message naming the target, fixed by putting the final URL in `model.base_url`. Reversible in one line; veto if same-host redirects should be followed.
- Non-loopback Ollama URLs keep following redirects, same reasoning as the proxy decision above (explicit opt-in via `identity.allow_external_providers`). Note this means an allowed remote server can redirect the prompt to a third host; say if that should be restricted too.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-11 — F001/F003 chat reply and degraded reason cannot drive the terminal

- Gap: `chat` printed `result.text` (model output) and `result.degraded_reason` exactly as received. A reply containing ESC sequences could clear the screen, change the window title or, on terminals that allow OSC 52, write to the clipboard; a bare carriage return could overwrite the `Jarvis:` line already printed. The degraded reason quotes text chosen by the model server (`server said: ...`, the redirect target), which is whitespace-collapsed but not otherwise filtered, so the same applied on stderr and a newline in a custom provider's error could forge a second `(degraded: ...)` line. Listed as "Not covered: the model's reply printed by `chat`" in the memory-listing entry above.
- Fix: `cli._printable` gained `multiline=False`. `cmd_chat` prints the reply through `_printable(text, multiline=True)`: newline, tab, line/paragraph separators and bidi controls are kept, `\r\n` becomes a newline, every other control character (category Cc) is shown as a backslash escape. The degraded reason goes through the existing one-line `_printable`. Display only; no interface, config or schema change; `InteractionResult` and the audit log are untouched; the memory-listing behaviour is unchanged (existing tests still pass).
- Test: `test_cli_chat_reply_cannot_drive_the_terminal` and `test_cli_chat_degraded_reason_cannot_drive_the_terminal` in tests/test_cli.py, using a scripted provider patched in for `build_provider`. Both fail without the change (verified by stashing `odysseus/`: 2 failed). `test_cli_chat_reply_keeps_ordinary_multiline_and_right_to_left_text` is a guard that passes either way.
- Suite: 152 passed (baseline 149, python3.12 venv outside the repo, cloud sandbox).
- Not done: `health` details and `error: ...` messages are still printed as produced. A literal backslash is not doubled. Not run on Windows or looked at in a real terminal emulator; not exercised with a live model.
- Correction to my own assumption during this run: the built-in echo fallback did not have this problem (it quotes the prompt with `repr`), so no change or test was needed there.
- Remaining gaps: F073 unchanged. F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Bidi controls and Unicode line/paragraph separators are left as they are in a model reply (they are escaped in memory listings). Reason: a reply is prose, and right-to-left languages use these marks legitimately; escaping them would garble ordinary Arabic/Hebrew answers. Cost: a reply can still be displayed in an order different from its stored characters. Reversible by dropping the `multiline` exception; veto if replies should be escaped as strictly as listings.
- Stdout of `chat` changes only for replies that contain control characters other than newline/tab (and `\r\n` is printed as `\n`). A script that parsed raw control bytes out of the reply would see escapes instead; none exists in this repo.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-11 — F073 `health` report details cannot drive the terminal

- Gap: `health` (text mode) printed each check's detail exactly as produced. The `model_provider:ollama` detail quotes text chosen by whatever answers on the model port: the installed model names from `/api/tags`, the exception text for an unreachable server, a redirect target. An ESC sequence there could clear the screen or retitle the window, and a newline could add a forged `  - memory_store: ok — ...` line to the report a user reads to decide whether the system is healthy. Listed as "Not done: `health` details ... are still printed as produced" in the previous entry.
- Fix: `cmd_health` prints the summary line, each check name and each detail through the existing one-line `cli._printable`. Display only; `HealthReport`, exit codes and `health --json` are unchanged (`json.dumps` already escapes control characters). No interface, config or schema change.
- Test: `test_cli_health_details_cannot_drive_the_terminal` in tests/test_cli.py (scripted provider patched in for `build_provider`; asserts no raw ESC/CR/bidi override, exactly one `memory_store` line, and that `--json` round-trips the detail unchanged). Fails without the change (verified by stashing `odysseus/cli.py`: 1 failed). `test_cli_health_ordinary_details_print_unchanged` is a guard that passes either way.
- Suite: 154 passed (baseline 152, python3.12 venv outside the repo, cloud sandbox).
- Not done: `error: ...` messages printed by `main()` are still printed as produced (next candidate). A literal backslash is not doubled. Not run on Windows or looked at in a real terminal emulator; not exercised against a live Ollama.
- Environment note: the first `pip install -r requirements-dev.txt` into a fresh venv hung for over two minutes and was killed; a re-run completed immediately. The default `python` here is 3.11 without pytest, so the suite was run with `python3.12` in a venv.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Bidi controls are escaped in health output (one-line mode), unlike in a model reply. Reason: a report line is a status record, not prose, and a right-to-left override could reorder what a check appears to say. Cost: a data path containing right-to-left text shows `\u200f`-style escapes in the text report (`--json` is unaffected). Reversible in one line; veto if paths should print raw.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.
