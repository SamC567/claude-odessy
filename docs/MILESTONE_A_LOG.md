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

## 2026-11-11 — F001 CLI `error:` messages cannot drive the terminal

- Gap: `main()` and the input-error paths of `chat` / `memory remember` printed `error: {exc}` exactly as produced. An error message can quote text that is not the program's own: a path from the config file, an environment variable or `--config`, a value from a corrupt memory row. Reproduced before the change: a config whose `memory.db_path` contained ESC `[2J` and a newline followed by `error: fake` made `chat` send the raw escape sequence to the terminal and print a second line starting with `error:`. Listed as "Not done: `error: ...` messages printed by `main()`" (next candidate) in the previous entry.
- Fix: new `cli._print_error(exc)`, used at all three `error:` sites. Each line of the message goes through the existing one-line `cli._printable`; line breaks are kept (pydantic and YAML configuration errors are multi-line) and continuation lines are indented two spaces, so only the first line can begin with `error:`. Display only; no interface, config or schema change; exception messages, exit codes and the audit log are untouched.
- Test: `test_cli_error_message_cannot_drive_the_terminal` in tests/test_cli.py (hostile `ODYSSEUS_MEMORY__DB_PATH` under a file that blocks directory creation; asserts no raw ESC/CR/bidi override and exactly one line starting with `error:`). Fails without the change (verified by stashing `odysseus/cli.py`: 1 failed, 155 passed). `test_cli_multiline_config_error_stays_readable` is a guard that passes either way.
- Suite: 156 passed (baseline 154, python3.12 venv outside the repo, cloud sandbox).
- Not done: log lines that `logging` writes to stderr (e.g. the "audit log ... is not writable" WARNING, which quotes `audit_log_path`) and argparse's own usage errors are still printed as produced. A literal backslash is not doubled. Not run on Windows or looked at in a real terminal emulator.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox). Seen while reading `OllamaProvider.generate`, not acted on: a whitespace-only `response` is accepted as a usable reply (an empty one is not), and the "no usable 'response' field" error quotes the whole response body without a length cap.

### Decisions

- Multi-line error messages stay multi-line, with continuation lines indented two spaces further than before, instead of being collapsed to one line with `\n` escapes. Reason: pydantic's "Invalid configuration" report is unreadable on one line. Cost: a script that matched continuation lines of stderr by exact leading whitespace would see two extra spaces; none exists in this repo. Reversible in one line; veto if errors should be strictly one line.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F003 a blank Ollama reply is not an answer; the error no longer quotes the response body

- Gap: `OllamaProvider.generate` refused only an empty `response` string. A whitespace-only one (`" "`, `"\n"`) was returned as a live model's answer, so the orchestrator did not fall back and `chat` printed a blank line labelled as a real reply. Separately, the "no usable 'response' field" error embedded the whole JSON body (`{data!r}`). A real `/api/generate` answer also carries `context` (token ids encoding the prompt) and timing fields, and that message goes to the audit log (`orchestrator.provider_failed`) and to the terminal as the `(degraded: ...)` reason. Both were noted as "seen, not acted on" in the previous entry.
- Fix: the check is now `not text.strip()`; new `_unusable_response_note(data)` in `odysseus/models/ollama_provider.py` builds the message: what was wrong with the field (missing / not text / empty / blank) plus `done_reason` only, whitespace-normalised and capped at the existing `_MAX_SERVER_ERROR_CHARS` (200). Still a `ModelProviderError`, still not retried (unchanged). A reply with real text keeps its surrounding whitespace. No interface, config or schema change.
- Test: in tests/test_models.py, `test_ollama_provider_whitespace_only_response_is_not_an_answer` (4 cases), `test_ollama_provider_unusable_response_error_does_not_quote_the_body` (5000-item `context`, marker string, `done_reason: "load"`), `test_ollama_provider_unusable_response_error_names_what_was_wrong` (5 cases). All 10 fail without the change (verified by stashing `odysseus/models/ollama_provider.py`: 10 failed, 157 passed). `test_ollama_provider_keeps_surrounding_whitespace_of_a_real_reply` is a guard that passes either way.
- Suite: 167 passed (baseline 156, python3.12 venv outside the repo, cloud sandbox).
- Not done: a blank reply is not retried (neither was an empty one). Models that put their output only in a separate `thinking` field would be reported as an empty reply; not handled, not verified against a live server. Log lines that `logging` writes to stderr and argparse usage errors are still printed as produced (from the previous entry).
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox). The simulated bodies here follow the documented `/api/generate` shape; `done_reason: "load"` for an empty reply is from Ollama's API documentation as recalled, not observed.

### Decisions

- The error message text changed ("Ollama returned no usable reply: ..." instead of "Ollama returned no usable 'response' field: {body}"). Reason: the body can hold prompt-derived data and be very large. Cost: the raw body is no longer available for debugging from the message (the exception type and the described cause are). Nothing in this repo matches on the old text. Reversible in one line; veto if the body should stay in the message (e.g. capped instead).
- Whitespace-only replies now trigger the fallback provider. Reason: a blank line presented as a live answer hides that the model produced nothing. Reversible by restoring `not text`; veto if a blank reply should be passed through.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F073/F003 config check warns about an unknown provider with the external gate open

- Gap: `build_provider` answers any `model.provider` it does not know with the echo fallback, whatever `identity.allow_external_providers` says (its docstring says the health module is where that is surfaced). `check_config` only warned while that flag was false. With the flag true, a typo (`olama`), a different case (`Ollama`) or a backend that does not exist here (`openai`) gave `config: ok — configuration loaded and valid` while every `chat` answer came from echo. No test covered an unknown provider name in the config check at all. The existing warning text ("is not a recognised local provider") also did not say what the system does instead.
- Fix: `check_config` in `odysseus/health/diagnostics.py` warns for any name outside `odysseus.models.registry.BUILTIN_PROVIDERS`, independent of the flag, and the detail names the known values, notes case-sensitivity and says the echo fallback will be used. `BUILTIN_PROVIDERS` is a new public frozenset in the registry (the previously unused `_BUILTIN_PROVIDERS` now aliases it), so diagnostics no longer keeps its own copy of the list. No config, schema or CLI change; the loader still accepts any provider name; status stays WARNING.
- Test: in tests/test_health.py, `test_config_check_warns_for_unknown_provider_whatever_the_external_gate` (3 names x gate closed/open; also asserts `build_provider` really returns echo for each) and `test_config_check_known_providers_follow_the_registry`. All 7 fail without the change (verified by stashing `odysseus/`: 7 failed, 167 passed). Of those, the three gate-open cases fail on the status (OK instead of WARNING); the three gate-closed cases fail only on the new detail wording, and the registry test fails because `BUILTIN_PROVIDERS` did not exist.
- Suite: 174 passed (baseline 167, python3.12 venv outside the repo, cloud sandbox).
- Smoke: `python -m odysseus.cli health` with `ODYSSEUS_MODEL__PROVIDER=Ollama` and the gate open, data paths in a scratch directory outside the repo, printed the new `config: warning` line and exited 0. Nothing was written inside the repo.
- Not done: provider names are not case-folded or trimmed (`Ollama` still means echo, now with a warning). There is no way to register a custom provider through config, so the field description's "or a custom key" has nothing behind it yet. Log lines that `logging` writes to stderr and argparse usage errors are still printed as produced (from earlier entries).
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- An unknown provider with `allow_external_providers: true` is now WARNING where it used to be OK, so `health` output and `overall_status` change for such a config (exit code stays 0; only CRITICAL exits 1). Reason: the report claimed a valid configuration while no model was called. Reversible by restoring the flag condition; veto if a custom provider key is meant to be silent when the gate is open.
- Kept WARNING rather than rejecting the name at config load. Reason: the registry deliberately keeps the system usable with a bad provider value, and rejecting would turn a working (echo) setup into a start-up error. Veto if an unknown provider should be a `ConfigError`.
- Did not make provider names case-insensitive. Reason: that changes which provider is built from an existing config (`Ollama` would start making network calls to the model server), which is a behaviour change better chosen by the user. Parked.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F073/F009 `health` reports stored memory entries that cannot be read

- Gap: `check_memory_store` ran SQLite's `quick_check`, counted rows by status and checked the file was writable. A row that cannot be decoded into a `MemoryEntry` (unknown status, tags that are not JSON, bad timestamp) passes all three, so `health` printed `memory_store: ok` while `memory list-approved` failed with `Corrupt memory row` and any `chat` whose retrieval returned that row answered degraded. The typed error for such a row was added on 2026-11-09; nothing told the user it existed before they hit it. No test covered it in the health check.
- Fix: new read-only `MemoryStore.unreadable_entry_ids()` (reads every row once, returns the ids `_row_to_entry` rejects). `check_memory_store` returns WARNING with the number of such rows and the first five ids ("and N more" beyond that). Called through `getattr`, so a store object without the method is checked as before. No config, schema or CLI change; nothing is repaired, moved or deleted.
- Test: in tests/test_health.py, `test_memory_store_check_warns_about_an_unreadable_row` (3 kinds of damage; also asserts `quick_check` still says ok and the row is left in place), `test_memory_store_check_caps_the_unreadable_ids_it_names`, `test_run_diagnostics_reports_an_unreadable_memory_row`. All 5 fail without the change (verified by stashing `odysseus/`: 5 failed, 175 passed). `test_memory_store_check_accepts_a_store_without_the_unreadable_scan` is a guard that passes either way.
- Suite: 180 passed (baseline 174, python3.12 venv outside the repo, cloud sandbox).
- Smoke: `python -m odysseus.cli health` against a scratch database outside the repo with one row's status set to `archived` printed `memory_store: warning — 1 stored memory entry cannot be read (id 1): ...` and exited 0. Nothing was written inside the repo.
- Not done: there is no command to repair, quarantine or export an unreadable row; the user has to fix it in SQLite by hand. The scan reads the whole table on every `health` run (not measured on a large database). Tags stored as a JSON string instead of a list still decode, one tag per character, and are not flagged. If the database is also not writable, only the not-writable warning is shown (one result per check). Log lines that `logging` writes to stderr and argparse usage errors are still printed as produced (from earlier entries).
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- WARNING, not CRITICAL. Reason: the store still accepts new memories and answers every query that does not return the damaged row; CRITICAL would make `health` exit 1 for a setup that mostly works. Cost: `overall_status` becomes WARNING for a database that used to report OK. Reversible in one word; veto if an unreadable row should fail the health command.
- Detection only; the row is left exactly as found. Reason: deleting or rewriting a memory row is not reversible and the content may still be recoverable by hand. A repair/quarantine command is parked until asked for.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009/F073 a `tags` column that is not a JSON list is a corrupt row

- Gap: `_row_to_entry` decoded tags with `tuple(json.loads(row["tags"]))`. The store only writes a JSON list, but any other valid JSON that happens to be iterable was coerced: a stored `"work"` came back as the tags `w`, `o`, `r`, `k`, and `{"work": 1}` as `work`. `memory show` displayed those as the entry's tags, retrieval ignored them (`_searchable_text` already accepts lists only), and `health` reported `memory_store: ok`. Recorded as "not flagged" in the previous entry; the docstring of `unreadable_entry_ids` already said "tags that are not a JSON list".
- Fix: new `_decode_tags` in `odysseus/memory/store.py` refuses a decoded value that is not a list; `_row_to_entry` wraps that in the existing `MemoryError_("Corrupt memory row id=...")`. The message names the JSON type found (`str`, `dict`), not the stored value. Because `unreadable_entry_ids` goes through `_row_to_entry`, the `health` memory check now counts such a row with no change to diagnostics. No interface, config, schema or CLI change; nothing is repaired or deleted.
- Test: `test_tags_column_that_is_not_a_json_list_is_a_corrupt_row` in tests/test_memory.py, 5 cases. The string and object cases fail without the change (verified by stashing `odysseus/`: 2 failed, 183 passed). The number, null and bool cases were already refused (a `TypeError` from `tuple()`) and are guards that pass either way. The test also asserts a stored list still decodes.
- Suite: 185 passed (baseline 180, python3.12 venv outside the repo, cloud sandbox).
- Not done: no CLI smoke run this time (covered by the unit test and the existing health tests only). There is still no command to repair, quarantine or export an unreadable row. A list holding a non-string or blank tag was already refused by `MemoryEntry` and is unchanged. Log lines that `logging` writes to stderr and argparse usage errors are still printed as produced (from earlier entries).
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- A row with string or object tags is now unreadable where it used to be listed with wrong tags, so one such row makes `memory list-*` for its status fail and `health` report WARNING, as for any other corrupt row. Reason: showing tags nobody stored is silent misinformation about a memory's record, and it matches how non-JSON tags are already treated. Only a hand edit or foreign tool can produce such a row; this store never writes one. Reversible by restoring the one-line decode; veto if such rows should instead be read with empty tags.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009 `memory remember` says when the fact is already stored

- Gap: since 2026-11-08 `MemoryStore.submit_candidate` returns the existing PENDING/APPROVED entry when the same content is submitted again, and discards the new submission's source, confidence and tags. The CLI printed `Submitted as entry [N] with status=...` in both cases. For a fact that was already approved this read `Submitted as entry [1] with status=approved`, i.e. as if the new submission had been stored and auto-approved, and nothing told the user that the provenance they had just typed was not kept. No test covered the CLI output for a duplicate.
- Fix: new read-only `MemoryStore.find_duplicate(content)` (public wrapper around the existing `_find_live_duplicate`; `TypeError` for a non-string). `cmd_memory_remember` calls it before `Orchestrator.remember` and, when the returned entry is that existing one, prints `Already stored as entry [N] with status=... (source=..., confidence=...); not added again. The source, confidence and tags given here were not stored with it.` The shown source goes through `_printable`. Called through `getattr`, so a store without the method is reported as before. Exit code stays 0. `Orchestrator.remember`, `submit_candidate`, the schema and config are unchanged; `find_duplicate` is listed in docs/INTEGRATION.md.
- Test: `test_cli_memory_remember_says_when_the_fact_is_already_stored`, `test_cli_memory_remember_existing_source_cannot_drive_the_terminal` (tests/test_cli.py), `test_find_duplicate_reports_what_submit_candidate_would_keep` (tests/test_memory.py). All 3 fail without the change (verified by stashing `odysseus/`: 3 failed, 185 passed).
- Suite: 188 passed (baseline 185, python3.12 venv outside the repo, cloud sandbox).
- Smoke: `python -m odysseus.cli memory remember` twice with the same fact (different case/spacing, different source) against a scratch database and audit log outside the repo printed `Submitted as entry [1] with status=pending`, then the `Already stored as entry [1] ...` line, exit 0. Nothing was written inside the repo.
- Not done: provenance of a duplicate submission is still not merged into the entry (the 2026-11-08 decision stands); only the audit record `memory.duplicate_candidate` keeps the duplicate's source, not its confidence or tags. The lookup scans pending/approved rows a second time per `remember` (not measured on a large database). Two processes submitting the same new fact at the same moment can still both store it (no unique constraint; unchanged). There is still no command to repair, quarantine or export an unreadable row.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- The duplicate case keeps exit code 0 and prints on stdout. Reason: "the fact is in memory" is the outcome the user asked for, and a non-zero code would break scripts that re-run `remember`. Cost: a script that matched the text `Submitted as entry` now sees `Already stored as entry` for a duplicate. Reversible in the CLI alone; veto if a duplicate should exit non-zero or keep the old wording.
- Report only; a duplicate's source/confidence/tags are still dropped. Reason: merging provenance changes what a reviewed entry says after it was approved, which should be the user's call. Parked until asked for.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009 `memory search` shows what a text retrieves

- Gap: retrieval (`MemoryStore.query`) had no direct command. The only way to see which approved memories a text recalls was `chat`, which calls the model and prints ids and sources only (`(memory used: ...)`), not the content or the order. Checking why a memory was or was not recalled, or what a tag or the stop-word list does to a query, meant sending a prompt or opening SQLite.
- Fix: new read-only CLI command `memory search "text" [--limit N]` (`cmd_memory_search` in `odysseus/cli.py`). It prints the entries `MemoryStore.query` returns, best match first, one per line as `[id] (confidence, source) content` (stored text through `_printable`), or `No approved memories match.` The default limit is `memory.context_limit`, so the output is the set a `chat` with the same text would put in the prompt; `--limit` overrides it. Blank text and `--limit` below 1 are exit code 2 with an `error:` line. With `memory.context_limit: 0` and no `--limit` it prints that chat adds no memory and suggests `--limit`, exit 0. No store, orchestrator, schema or config change; nothing is written or audited. README and docs/ARCHITECTURE.md updated.
- Test: `test_cli_memory_search_shows_ranked_approved_matches_only`, `test_cli_memory_search_limit_defaults_to_what_chat_uses`, `test_cli_memory_search_with_context_limit_zero_says_so`, `test_cli_memory_search_rejects_blank_text_and_escapes_stored_text` (tests/test_cli.py). All 4 fail without the change (verified by stashing `odysseus/`: 4 failed, 188 passed).
- Suite: 192 passed (baseline 188, python3.12 venv outside the repo, cloud sandbox).
- Smoke: `remember` + `approve` + `memory search "what about pizza?"` against a scratch database and audit log outside the repo printed `[1] (0.80, user) Sam likes pizza`, exit 0; `search umbrella` printed `No approved memories match.`; `--limit 0` gave the error line, exit 2. The scratch files were deleted; nothing was written inside the repo.
- Not done: the output does not say why an entry ranked where it did (no match count per entry). Pending and rejected entries cannot be searched (by design of `query`). The retrieval limitation is unchanged: substring matching, no stemming, English-only stop words. Not run on Windows. Carried over: two processes submitting the same new fact at the same moment can both store it; no command to repair, quarantine or export an unreadable row.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- A search is not written to the audit log. Reason: it is a read the user typed, like the `list-*` and `show` commands, which are not audited either; `chat` still audits `orchestrator.memory_used`. Veto if every retrieval should leave a record.
- The default limit follows `memory.context_limit` instead of the store's own default of 20. Reason: the main use is "what would chat recall for this"; `--limit` covers the rest. Reversible in the CLI alone.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009 an id or limit beyond SQLite's integer range is not a crash

- Gap: SQLite integers are 64-bit, and Python's `sqlite3` raises `OverflowError` when asked to bind a larger int. That is not a `sqlite3.Error`, so it passed straight through `MemoryStore._read` and out of the store, contrary to the documented rule that storage failures surface as `MemoryError_` / `ReviewInboxError`. Reproduced before the change: `memory show 99999999999999999999999`, `memory approve 99999999999999999999999 --reviewer x` and `memory search pizza --limit 99999999999999999999999` each ended in a traceback (`OverflowError: Python int too large to convert to SQLite INTEGER`). No test covered it.
- Fix: in `odysseus/memory/store.py`, `get` returns `None` for an int id outside the signed 64-bit range (no such row can exist), which also makes `approve` / `reject` / `retract` raise their usual `ReviewInboxError("No memory entry with id=...")` because they look the entry up first; `query` clamps `limit` to the largest SQLite integer (a larger limit means "all matches"). No CLI, schema, config or interface change. docs/ARCHITECTURE.md "Recent fixes" updated.
- Test: `test_ids_and_limits_beyond_sqlite_integer_range_do_not_raise_overflow` (tests/test_memory.py), `test_cli_memory_id_or_limit_beyond_sqlite_range_is_not_a_traceback` (tests/test_cli.py). Both fail without the change (verified by stashing `odysseus/`: 2 failed, 192 passed).
- Suite: 194 passed (baseline 192, python3.12 venv outside the repo, cloud sandbox).
- Smoke: against a scratch database and audit log outside the repo, `memory show`, `memory approve` and `memory forget` with the id above printed `error: No memory entry with id=...`, exit 2; `memory search pizza --limit 99999999999999999999999` printed the one approved entry, exit 0. The scratch files were deleted; nothing was written inside the repo.
- Not done: `get` with a non-int id (a string, a float) is unchanged and still returns `None` or whatever SQLite's comparison gives; only the out-of-range int case was reproduced and fixed. `memory.context_limit` is already capped at 50 by config, so `chat` was not affected. Not run on Windows. Carried over: two processes submitting the same new fact at the same moment can both store it; no command to repair, quarantine or export an unreadable row; `memory search` does not say why an entry ranked where it did.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- An out-of-range id is reported as "not found", not as a separate "invalid id" error. Reason: it is true (no such row can exist), it matches what every other unknown id already does, and it needs no new error path in callers. Reversible in `MemoryStore.get` alone; veto if such an id should be rejected with its own message.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009 the same fact submitted twice at the same moment is stored once

- Gap: `MemoryStore.submit_candidate` looked for a live duplicate on one connection, closed it, then inserted on another. Two submitters of the same new fact (two CLI processes, or two threads sharing a database) could both find nothing and both insert, leaving two PENDING entries for one fact, which the de-duplication from 2026-11-08 is meant to prevent. Carried in "Not done" since the `memory remember` entry of 2026-11-12. No test covered it.
- Fix: in `odysseus/memory/store.py`, `submit_candidate` opens one connection, takes the write lock with `BEGIN IMMEDIATE`, runs the duplicate lookup on that connection and inserts only if nothing was found, then commits. `_find_live_duplicate` takes an optional connection for this; `find_duplicate` and every read path are unchanged. A second submitter waits at `BEGIN IMMEDIATE` until the first commits, then sees its row and returns it (audited `memory.duplicate_candidate` as before). No schema, config, CLI or interface change. docs/ARCHITECTURE.md "Recent fixes" updated.
- Test: `test_same_fact_submitted_concurrently_is_stored_once` (tests/test_memory.py). It holds the first submitter between its lookup and its insert while a second store on the same file submits the same fact from another thread. Fails without the change (verified by stashing `odysseus/`: 1 failed, 194 passed; two rows stored).
- Suite: 195 passed (baseline 194, python3.12 venv outside the repo, cloud sandbox).
- Not done: no CLI smoke run and no test with two real processes (the test uses two threads with separate connections, which take the same SQLite file lock). A submitter that cannot get the write lock within the connection's 5 s timeout now fails with `MemoryError_("Could not store memory candidate: database is locked")`; before, only the insert itself could hit that. The schema still has no unique constraint, so a row inserted by another tool is not prevented. The test adds about one second to the suite (it waits for the second submitter). Not run on Windows or on a network drive, where SQLite file locking is less reliable. Carried over: no command to repair, quarantine or export an unreadable row; `memory search` does not say why an entry ranked where it did.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Used a transaction, not a unique index on normalised content. Reason: an index needs a schema migration and would fail to build on a database that already holds duplicates, and REJECTED rows must stay re-submittable; the transaction changes no stored data. Reversible in `submit_candidate` alone; veto if a schema-level guarantee is wanted.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F001/F003 a provider that raises the wrong exception type still gets the fallback

- Gap: `Orchestrator.respond` caught only `ModelProviderError` from the primary provider. The `ModelProvider` interface asks providers to raise only that type, but nothing enforced it, so any other exception from `provider.generate` (a bug in a new or third-party backend, e.g. a `KeyError` on an unexpected reply shape) ended the interaction with a traceback instead of the fallback answer. Diagnostics already guards a crashing provider check (`model_provider:<name>`); the orchestrator did not. Reproduced before the change with a test provider raising `KeyError("choices")`. No test covered it.
- Fix: in `odysseus/core/orchestrator.py`, `respond` also catches `Exception` from the primary provider's `generate` and degrades the same way (fallback answers, `degraded=True`, `used_fallback=True`). `degraded_reason` reads `provider '<name>' raised an unexpected <Type>: <message>` (after any memory failure), and the `orchestrator.provider_failed` audit record gains `unexpected='<Type>'`. `KeyboardInterrupt` and `SystemExit` are not `Exception` and still pass through. No interface, config, CLI or schema change. docs/ARCHITECTURE.md "Recent fixes" updated.
- Test: `test_respond_falls_back_when_provider_raises_an_unexpected_exception`, `test_unexpected_provider_exception_keeps_the_memory_failure_in_the_reason` (tests/test_orchestrator.py). Both fail without the change (verified by stashing `odysseus/`: 2 failed, 196 passed). `test_keyboard_interrupt_from_a_provider_is_not_swallowed` is a guard that passes with and without the change.
- Suite: 198 passed (baseline 195, python3.12 venv outside the repo, cloud sandbox).
- Not done: no CLI smoke run (the built-in providers have no known path that raises a non-`ModelProviderError`, so `chat` could not show it without a test double). A fallback provider that itself raises still ends the interaction. A provider that returns something other than a `GenerationResponse`, or blank text, is not checked by the orchestrator. The fallback block is repeated in both `except` branches rather than factored out. Not run on Windows. Carried over: no command to repair, quarantine or export an unreadable row; `memory search` does not say why an entry ranked where it did.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Caught `Exception` broadly instead of leaving the crash visible. Reason: the project rule is that the system stays usable when a model backend fails; the bug is not hidden, since the exception type and message are in `degraded_reason` (printed by `chat` on stderr) and in the audit log. Reversible in `Orchestrator.respond` alone; veto if a provider bug should stop the interaction with a traceback.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F001/F003 a provider that returns no usable reply still gets the fallback

- Gap: `Orchestrator.respond` trusted whatever the primary provider's `generate` returned. A provider returning `None` or another non-`GenerationResponse` value (a bug in a new or third-party backend) ended the interaction with an `AttributeError` traceback, because the reply is read after the `try` block; a `GenerationResponse` with blank text was passed on as a live model's answer (`is_live_model=True`, `degraded=False`), so `chat` would print an empty line. Listed under "Not done" in the previous entry. Reproduced before the change with a test provider. No test covered it.
- Fix: in `odysseus/core/orchestrator.py`, the new module-level `_reply_problem(response)` describes why a reply is unusable (not a `GenerationResponse`, `text` not a string, blank text) and `respond` raises `ModelProviderError` inside the existing `try` when it does, so the existing fallback branch handles it: fallback answers, `degraded=True`, `used_fallback=True`, `degraded_reason` = `provider '<name>' returned no usable reply: <problem>`, audit `orchestrator.provider_failed`. The reply is described, never quoted. No interface, config, CLI or schema change. docs/ARCHITECTURE.md "Recent fixes" updated.
- Test: `test_respond_falls_back_when_provider_returns_no_usable_reply` (5 cases), `test_unusable_reply_is_audited_as_a_provider_failure_not_a_generation` (tests/test_orchestrator.py). All 6 fail without the change (verified by stashing `odysseus/`: 6 failed, 199 passed). `test_usable_reply_with_surrounding_whitespace_is_returned_unchanged` is a guard that passes with and without the change.
- Suite: 205 passed (baseline 198, python3.12 venv outside the repo, cloud sandbox).
- Not done: no CLI smoke run (no built-in provider returns such a reply, so `chat` could not show it without a test double). The fallback provider's reply is not checked, and a fallback that raises still ends the interaction. Only `text` is checked; a `GenerationResponse` with a wrong-typed `provider_name` or `is_live_model` is passed through. Not run on Windows. Carried over: no command to repair, quarantine or export an unreadable row; `memory search` does not say why an entry ranked where it did.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Treated a blank reply as a provider failure rather than passing it through. Reason: `OllamaProvider` already applies this rule to itself ("a blank reply is not an answer", 2026-11-12), and a labelled fallback answer with the reason on stderr is more honest than an empty line presented as a model answer. Reversible in `Orchestrator.respond` alone; veto if an empty model reply should be shown as-is.
- Raised `ModelProviderError` (ordinary failure wording) rather than the "unexpected <Type>" wording. Reason: nothing was raised by the provider, so naming an exception type would be untrue.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F001/F003 a fallback provider that fails ends with one typed error, not a traceback

- Gap: `Orchestrator.respond` called `fallback_provider.generate` unguarded and unchecked. A custom fallback that raised a non-`ModelProviderError` exception or returned a non-`GenerationResponse` value ended the interaction with a traceback; one returning blank text was shown as the answer; one raising `ModelProviderError` surfaced only its own message, losing the primary provider's failure. Listed under "Not done" in the previous two entries. Reproduced before the change with test doubles. No test covered it.
- Fix: in `odysseus/core/orchestrator.py`, the new `Orchestrator._answer_from_fallback(request, primary_failure)` replaces the two duplicated fallback calls. It applies `_reply_problem` to the fallback's reply and catches `Exception` from it; on any failure it audits `orchestrator.fallback_failed` (with `unexpected='<Type>'` for a non-`ModelProviderError`) and raises `ModelProviderError("no provider could answer: <primary failure>; fallback provider '<name>' <problem>")`, chained to the original exception. The CLI's existing `OdysseusError` handler prints that as `error: ...` with exit code 2. No interface, config, CLI or schema change. docs/ARCHITECTURE.md "Recent fixes" and the data-flow step 4 updated.
- Test: `test_failing_fallback_ends_with_one_typed_error_naming_both_failures` (4 cases), `test_failing_fallback_is_audited_and_never_recorded_as_a_generation` (tests/test_orchestrator.py). All 5 fail without the change (verified by stashing `odysseus/`: 5 failed, 206 passed). `test_keyboard_interrupt_from_a_fallback_is_not_swallowed` is a guard that passes with and without the change.
- Suite: 211 passed (baseline 205, python3.12 venv outside the repo, cloud sandbox).
- Not done: no CLI test or smoke run (the CLI always uses the built-in `EchoProvider` fallback, which has no failing path, and no config option selects another). The raised error is always plain `ModelProviderError`; a fallback's `ModelUnavailableError` subtype survives only as `__cause__`. Only `text` is checked on a reply; a wrong-typed `provider_name` or `is_live_model` is passed through. Not run on Windows. Carried over: no command to repair, quarantine or export an unreadable row; `memory search` does not say why an entry ranked where it did.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Raised a typed error instead of substituting a built-in `EchoProvider` as a last resort. Reason: the caller chose that fallback explicitly, and silently answering from a third provider would hide that both configured providers failed; an error that names both is the honest outcome and changes no successful path. Reversible in `Orchestrator._answer_from_fallback` alone; veto if a last-resort echo answer is preferred.
- A fallback's own `ModelProviderError` message is now wrapped in the combined message rather than propagated as-is. Reason: the primary's failure was otherwise lost. Callers catching `ModelProviderError` are unaffected; one catching `ModelUnavailableError` specifically from `respond` would no longer match (none exists in this repo).
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009 a corrupt memory row can still be read with `memory show <id> --raw`

- Gap: a stored row the store refuses as corrupt (unknown status, tags that are not a JSON list, a bad timestamp) was named by `health` (2026-11-12, `unreadable_entry_ids`) but its contents could not be read through this project: `memory show <id>` printed only `error: Corrupt memory row id=N: <reason>`, and every listing that included the row failed. The stored text could be recovered only by opening the SQLite file with another tool. Carried under "Not done" ("no command to repair, quarantine or export an unreadable row") in every entry since the health change. No test covered it.
- Fix: new read-only `MemoryStore.raw_row(entry_id)` in `odysseus/memory/store.py` returns one row's column values as stored (a dict; `None` for an unknown or out-of-range id), with no decoding or validation. In `odysseus/cli.py`, `memory show <id> --raw` prints them one per line as Python literals (`NULL` for no value), passed through `_printable` so a stored value cannot forge a line or drive the terminal. `memory show <id>` on a corrupt row keeps its error and exit code 2 and adds a second stderr line pointing to `--raw` (only when the raw read works). Nothing is written or audited. No schema or config change; `get` and every existing path are unchanged. docs/ARCHITECTURE.md "Recent fixes" and README.md updated.
- Test: tests/test_cli.py `test_cli_memory_show_raw_prints_a_corrupt_row_as_stored`, `test_cli_memory_show_on_a_corrupt_row_points_to_raw`, `test_cli_memory_show_raw_cannot_forge_lines_or_drive_the_terminal`, `test_cli_memory_show_raw_unknown_id_is_a_clean_error`, `test_cli_memory_show_raw_changes_nothing`; tests/test_memory.py `test_raw_row_returns_stored_values_of_a_row_get_refuses`, `test_raw_row_unknown_or_out_of_range_id_is_none`. All 7 fail without the change (verified by stashing `odysseus/`: 7 failed, 211 passed).
- Suite: 218 passed (baseline 211, python3.12 venv outside the repo, cloud sandbox).
- Smoke run (cloud sandbox, temporary directory outside the repo, echo provider): stored one fact, hand-edited its status to `x`, then `memory show 1` printed the error plus the `--raw` pointer and `memory show 1 --raw` printed the eight stored columns.
- Not done: this narrows the carried item to "read"; there is still no command to repair or quarantine an unreadable row, so listings and answers that would include it keep failing until the file is fixed by hand. `--raw` has no JSON output. The `health` detail does not mention `--raw` (the pointer is only on `memory show`). `raw_row` is not part of any documented store interface; the CLI looks it up with `getattr`, as it does `find_duplicate`. Not run on Windows. Carried over: `memory search` does not say why an entry ranked where it did.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Added a read-only view and did not add a repair or quarantine command. Reason: repairing means rewriting or removing stored memory, which is not reversible without a backup convention this repo does not have yet; reading is safe and lets the user re-enter the fact. Veto or direct if a repair command is wanted, and say what it may change (e.g. set status to rejected, rewrite tags to `[]`).
- `--raw` is not written to the audit log. Reason: it is a read, like `memory show` and `memory search`, which are not audited either.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009 `memory search --explain` shows which search terms each memory matched

- Gap: `memory search` listed the approved memories a text retrieves, best match first, but gave no reason for the order. `MemoryStore.query` ranks by the number of distinct search terms an entry contains, then confidence, then recency; neither the terms (stop words and short words are dropped, the whole text is a term of its own) nor an entry's count could be seen through this project, so a lower-confidence memory listed above a higher-confidence one could only be explained by reading the code. Carried under "Not done" ("`memory search` does not say why an entry ranked where it did") in every entry since the search command was added. No test covered it.
- Fix: in `odysseus/memory/store.py`, the term rule that was inline in `query` moved unchanged into the module-level `_query_terms(text)` (whole text first, then the significant words in the order typed), which `query` now calls. Two read-only methods use the same helper and touch no database: `MemoryStore.search_terms(text)` and `MemoryStore.matched_terms(text, entry)` (the terms an entry's content or tags contain, same case-insensitive substring rule as `query`). In `odysseus/cli.py`, `memory search "text" --explain` prints a `Search terms (N): ...` line and, under each memory, `    matched K of N: ...`; terms go through `_printable`. Without the flag the output is byte-for-byte what it was. Nothing is stored or audited. No schema or config change; `query`'s results and order are unchanged. docs/ARCHITECTURE.md "Recent fixes" and README.md updated.
- Test: tests/test_cli.py `test_cli_memory_search_explain_names_the_terms_each_memory_matched`, `test_cli_memory_search_explain_cannot_forge_lines_or_drive_the_terminal`; tests/test_memory.py `test_search_terms_are_the_whole_text_then_its_significant_words`, `test_matched_terms_account_for_the_order_query_returns`, `test_matched_terms_agree_with_query_on_what_matches` (the last checks, over seven query texts including `100%`, `snake_case` and stop-word queries, that `query` returns an approved entry exactly when it has a matched term). All 5 fail without the change (verified by stashing `odysseus/`: 5 failed, 218 passed).
- Suite: 223 passed (baseline 218, python3.12 venv outside the repo, cloud sandbox).
- Smoke run (cloud sandbox, temporary directory outside the repo, echo provider): stored and approved two facts, then `memory search "does Sam like pizza with olives?" --explain` printed five search terms, the two memories, and `matched 4 of 5` / `matched 3 of 5` beneath them.
- Not done: the explanation covers the entries returned, not why another entry was left out (below the limit, not approved, or no term matched). The confidence/recency tie-break is described in `--help` only, not shown per entry. `chat` has no equivalent flag. `--explain` has no JSON output. The CLI calls the two new methods directly rather than through `getattr` (it always builds a `MemoryStore` itself); they are not part of any documented store interface in docs/INTEGRATION.md. Matching in SQL (`LIKE`) and in Python (`in`) are two implementations of the same rule, held together by the agreement test, not by construction. Not run on Windows. Carried over: no command to repair or quarantine an unreadable row.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Made the explanation opt-in (`--explain`) instead of adding it to the default output. Reason: the default output is asserted line-for-line by existing tests and may be read by scripts; an extra flag changes nothing for existing use. Veto if the explanation should always be shown.
- Counted the whole text as a search term in the `K of N` figures, although the user typed fewer words. Reason: that is how `query` scores, and a figure that differed from the real score would not explain the order. The terms line lists it first so the count can be checked.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009 `memory list-approved --tag` lists the approved memories filed under one tag

- Gap: tags were stored, shown per entry and matched by retrieval, but there was no way to ask for everything filed under a tag. `memory search allergy` is a substring search over content and tags together, so it also returns entries that only mention the word or carry a longer tag (`allergy-history`), and it is capped by `--limit`. Recorded as not covered ("there is no tag-only filter ... in the store or CLI") in docs/ARCHITECTURE.md since tags became searchable. No test covered it.
- Fix: `MemoryStore.list_approved` in `odysseus/memory/store.py` takes an optional keyword-only `tag`; with it, only approved entries having a tag equal to it (case-insensitive via `casefold`, surrounding whitespace ignored) are returned, oldest first. A blank tag is a `ValueError` and a non-string a `TypeError`, so a mistake cannot fall through to "list everything". In `odysseus/cli.py`, `memory list-approved --tag <tag>` uses it; no match prints `No approved memories tagged "<tag>".` (the tag goes through `_printable`), a blank `--tag` prints `error: tag must not be empty` and exits 2. Calling `list_approved()` with no argument and `memory list-approved` without the flag behave exactly as before. Read-only, not audited. No schema or config change. docs/ARCHITECTURE.md "Recent fixes" and README.md updated.
- Test: tests/test_memory.py `test_list_approved_by_tag_returns_only_entries_filed_under_that_tag`, `test_list_approved_by_tag_matches_non_ascii_tags_case_insensitively`, `test_list_approved_refuses_a_blank_or_non_string_tag`; tests/test_cli.py `test_cli_memory_list_approved_tag_lists_only_that_tag`, `test_cli_memory_list_approved_blank_tag_is_a_clean_error`, `test_cli_memory_list_approved_tag_cannot_forge_lines_or_drive_the_terminal`. All 6 fail without the change (verified by stashing `odysseus/`: 6 failed, 223 passed).
- Suite: 229 passed (baseline 223, python3.12 venv outside the repo, cloud sandbox).
- Smoke run (cloud sandbox, temporary directory outside the repo, echo provider): stored and approved two facts tagged `Allergy food` and `category`; `memory list-approved --tag allergy` printed the first only, `--tag cat` printed `No approved memories tagged "cat".`, `--tag " "` printed the error with exit code 2, and plain `list-approved` printed both.
- Not done: one tag per call (no combination of tags). Approved entries only; `list-pending` and `list-rejected` have no `--tag`. No command lists the tags in use. The filter runs in Python over every approved row, so an unreadable approved row fails it as it fails plain `list-approved`, and it is not indexed. `tag` is not described in docs/INTEGRATION.md, which lists the store's interface only in outline. Not run on Windows. Carried over: no command to repair or quarantine an unreadable row.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Extended `list_approved` with an optional keyword-only argument instead of adding a new method. Reason: existing calls are unaffected and the listing order and decoding stay in one place. A replacement store without the keyword would fail only when `--tag` is used. Reversible; veto if a separate method is preferred.
- Whole-tag, case-insensitive match rather than substring. Reason: `memory search` already gives the substring behaviour; a filter that returned `category` for `cat` would add nothing to it.
- A blank tag is an error, not "no filter". Reason: listing everything in answer to a mistaken filter would be misleading.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F009 an unreadable memory row can be moved aside with `memory quarantine <id>`

- Gap: a stored row that cannot be decoded (unknown status, tags that are not a JSON list, a bad timestamp) could be reported (`health`) and read (`memory show <id> --raw`), but nothing in this project could act on it. `approve`/`reject`/`forget` fail on it, and `list-approved`, `memory search` and `chat` retrieval fail whenever they would return it, so one bad approved row could switch memory off for matching prompts until the SQLite file was edited with another tool. Carried as "no command to repair or quarantine an unreadable row" in every entry since the unreadable-row health check. No test covered it.
- Fix: `MemoryStore.quarantine(entry_id, reviewer)` in `odysseus/memory/store.py` moves such a row from `memory_entries` into a `memory_quarantine` table in the same database, in one `BEGIN IMMEDIATE` transaction, with every stored value and its stored type unchanged plus `quarantined_at` / `quarantined_by`. It raises `ReviewInboxError` for a readable entry (any status), an unknown id, or a blank reviewer, and is audited as `memory.quarantine`. `MemoryStore.list_quarantined()` returns the quarantined rows as stored (read-only; empty if the table does not exist). The table is created on first use, not in the store's opening schema. In `odysseus/cli.py`: `memory quarantine <id> [--reviewer NAME]` and `memory list-quarantined`; the raw-value printing of `memory show --raw` moved unchanged into `_print_raw_values`, which both use. No config change; no existing method changed. docs/ARCHITECTURE.md "Recent fixes", docs/MIGRATION_ASSUMPTIONS.md (state surfaces) and README.md updated.
- Test: tests/test_memory.py `test_quarantine_moves_an_unreadable_row_aside_and_memory_works_again`, `test_quarantine_keeps_the_stored_value_and_its_type` (4 cases), `test_quarantine_refuses_a_readable_entry_in_any_status`, `test_quarantine_unknown_id_or_blank_reviewer_is_a_review_error`, `test_quarantined_id_is_not_reused_and_a_second_quarantine_is_not_found`, `test_quarantine_is_audited_and_never_creates_its_table_unless_used`; tests/test_cli.py `test_cli_memory_quarantine_moves_a_corrupt_row_aside`, `test_cli_memory_quarantine_refuses_a_readable_or_unknown_entry`, `test_cli_memory_list_quarantined_cannot_forge_lines_or_drive_the_terminal`. All 12 fail without the change (verified by stashing `odysseus/`: 12 failed, 229 passed).
- Suite: 241 passed (baseline 229, python3.12 venv outside the repo, cloud sandbox).
- Smoke run (cloud sandbox, temporary directory outside the repo, echo provider): approved two facts and spoiled the second's `created_at`; `memory list-approved` failed and `health` warned about id 2; `memory quarantine 1` was refused as readable (exit 2); `memory quarantine 2` succeeded; `list-approved` then printed entry 1, `list-quarantined` printed entry 2's stored values, `health` reported `memory_store=ok`, and the audit log held one `memory.quarantine` line.
- Not done: no command puts a quarantined row back or repairs it. `health` does not mention quarantined rows and `count_by_status` does not count them. One id per call. `list-quarantined` has no JSON output. The transaction's rollback on a mid-way failure follows from SQLite's behaviour and is not tested by fault injection. The two new methods are not listed in docs/INTEGRATION.md, which names the store's interface in outline only; the CLI calls them directly. Not run on Windows.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Quarantine moves the row; it never deletes it. Reason: this run may not make a destructive choice, and the row may hold a fact the user wants back. Every stored value stays in the same database file and is shown by `memory list-quarantined`. Veto if unreadable rows should stay where they are until repaired by hand.
- Left out a "restore" command. Reason: putting an unreadable row back unchanged restores the failure, and a repair command needs rules for what a valid correction is; that is a separate change. The data needed for either is kept.
- Only an unreadable row can be quarantined. Reason: otherwise the command would be a way to remove approved memory without a recorded review decision (`reject` / `forget` exist for that).
- The `memory_quarantine` table is created on first use, not when the store opens. Reason: opening an existing database (including a read-only one) must not start changing its schema.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.

## 2026-11-12 — F073/F009 `health` reports how many memory rows are quarantined

- Gap: a row moved aside with `memory quarantine` is in no status count, and `health` said nothing about it, so stored data could sit outside memory with no sign of it unless someone ran `memory list-quarantined`. Recorded as not done ("`health` does not mention quarantined rows") in the previous entry and in docs/ARCHITECTURE.md. No test covered it.
- Fix: `MemoryStore.count_quarantined()` in `odysseus/memory/store.py` returns the number of rows in `memory_quarantine` (read-only; 0 when the table does not exist, and it never creates it). `check_memory_store` in `odysseus/health/diagnostics.py` appends `quarantined=N (see `memory list-quarantined`)` to the `memory_store` detail when N is above zero, in the OK result and in the warnings alike. The check's status does not change because of it. With nothing quarantined the detail is exactly as before. A store without `count_quarantined` is not asked (`getattr`, as for `unreadable_entry_ids`). No config, schema or CLI argument change. docs/ARCHITECTURE.md "Recent fixes" updated, and the two statements in the quarantine entry that this makes untrue were corrected.
- Test: tests/test_health.py `test_memory_store_check_mentions_quarantined_rows`, `test_count_quarantined_does_not_create_the_quarantine_table`, `test_run_diagnostics_reports_quarantined_rows_without_degrading`. All 3 fail without the change (verified by stashing `odysseus/`: 3 failed, 241 passed).
- Suite: 244 passed (baseline 241, python3.12 venv outside the repo, cloud sandbox).
- Smoke run (cloud sandbox, temporary directory outside the repo, echo provider): stored two facts and spoiled the second's `created_at`; `health` warned about id 2; after `memory quarantine 2`, `health` printed `memory_store: ok — ... counts={'pending': 1} quarantined=1 (see `memory list-quarantined`)`, and `health --json` carried the same detail.
- Not done: `health` gives the count only, not the ids or dates. No threshold turns many quarantined rows into a warning. `count_by_status` still excludes them. `count_quarantined` is not listed in docs/INTEGRATION.md, which names the store's interface in outline only. Not run on Windows. Carried over: no command puts a quarantined row back or repairs it.
- Remaining gaps: F003 is still untested against a live Ollama process (cannot be closed from this sandbox).

### Decisions

- Quarantined rows are reported as information and leave the status at OK. Reason: quarantining is the remedy the project offers, and a permanent WARNING after using it would make `health` warn forever, since there is no restore or repair command yet. Veto if any quarantined row should keep `health` at WARNING.
- Added a separate `count_quarantined()` instead of adding a key to `count_by_status()`. Reason: `count_by_status` is printed in the detail and summed by callers and tests as "rows in memory"; a new key would change both.
- Still awaiting the user's choice from 2026-11-11 (audit log entry): relative `memory.db_path` / `audit_log_path` anchoring ((a) project root, (b) keep CWD and fix the description). Not acted on.
