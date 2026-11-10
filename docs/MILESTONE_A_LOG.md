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
