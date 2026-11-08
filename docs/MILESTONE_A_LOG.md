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

### Decisions
- Hardware thresholds kept as function defaults rather than adding config schema fields (reversible, no config contract change).
- Windows RAM path (ctypes) written but not run in this Linux cloud run.
