---
name: jarvis-development
description: Standing engineering workflow for implementing features (F001–F134) in this repository — understand acceptance criteria, inspect the existing architecture and Git state, plan, implement for real, test/lint/typecheck, fix failures, do a security/privacy/architecture self-check, update docs, commit and push to the authorised branch, and report honestly. Use for any non-trivial implementation task: a new feature or feature slice, a bugfix touching more than a couple of lines, a refactor, or anything spanning multiple files/modules. Skip or abbreviate for genuinely trivial changes (a typo, a one-line doc tweak, a config value flip) — use judgment on depth rather than running the full process on everything.
---

# Jarvis Development Workflow

This is the repeatable procedure for implementation work in the
Jarvis / Odysseus workspace, so each task follows the same engineering
process without the user re-pasting instructions. It assumes the
principles in the root `CLAUDE.md` (local-first, least-privilege,
modular, honest reporting) and does not relitigate them here.

Adapt depth to size and risk. A one-file, low-risk change can compress
steps 2–4 into a couple of sentences and skip the formal plan; a new
module or anything touching memory/model/security boundaries should go
through all eleven steps explicitly.

## 1. Understand the requested outcome and acceptance criteria

- Restate, in your own words (briefly, not back to the user unless
  genuinely ambiguous), what "done" means for this task.
- Identify which approved feature ID(s) (F001–F134) this belongs to, if
  any. **Do not silently expand scope** to a feature ID or capability
  that was not asked for — flag it instead if you notice adjacent work
  that seems necessary.
- If acceptance criteria are genuinely unclear or the task could mean
  two materially different things, ask one clarifying question
  (`AskUserQuestion`) rather than guessing — but prefer making a
  reasonable, stated assumption and proceeding when you can.

## 2. Inspect the repository

- Check `git status` / `git log` for uncommitted work, branch state,
  and recent history before changing anything.
- Read the relevant existing modules under `odysseus/` (and their
  tests under `tests/`) before writing new code — this repo's
  convention is small, interface-first modules
  (`odysseus/models/base.py`, `odysseus/memory/store.py`,
  `odysseus/health/diagnostics.py`, `odysseus/core/orchestrator.py`).
  New code should look like it belongs next to these.
- Check `docs/ARCHITECTURE.md` for the current module map and known
  limitations, and `docs/INTEGRATION.md` /
  `docs/MIGRATION_ASSUMPTIONS.md` for integration constraints, before
  assuming a clean slate.

## 3. Identify relevant files, interfaces, dependencies, conflicts

- Name the specific files/interfaces this task touches or must respect
  (e.g. "implements a new `ModelProvider`", "adds a method to
  `MemoryStore`", "new CLI subcommand in `odysseus/cli.py`").
- Check `requirements.txt` / `pyproject.toml` before adding a
  dependency — prefer stdlib or an already-used library
  (`pydantic`, `PyYAML`, `requests`, `pytest`). A new dependency needs
  a stated reason.
- Note any conflict with existing behaviour, tests, or in-flight work
  (uncommitted changes, open branches) before proceeding.

## 4. Produce a concise implementation plan

- A short list of the concrete changes (files to add/edit, new
  interfaces, migration/config impact), not a restatement of the task.
- For anything genuinely large or architecturally significant, use
  `EnterPlanMode` / the `Plan` agent as this harness normally would;
  for an ordinary feature slice, a few bullet points in your own
  response is enough — don't manufacture ceremony.

## 5. Implement the actual task

- Write working code, not a description of what should be written.
  Match existing patterns: dataclasses/pydantic models, typed
  exceptions (`odysseus/exceptions.py`) rather than letting
  backend-specific errors escape, `logging_setup.audit(...)` at
  autonomous decision points (memory writes, review decisions,
  provider fallback, or any new equivalent).
- Keep modules independent but interoperable: depend on interfaces
  (`ModelProvider`, `MemoryStore`, etc.), not concrete classes, unless
  you are the registry/factory that is explicitly allowed to know
  about concrete implementations (`odysseus/models/registry.py`).
- No hardcoded secrets. No unrestricted shell execution. If a new
  external call is involved, it must be explicit, configurable, and
  off by default unless the user has already authorised it.

## 6. Run tests, linting, type checks, validation

- Run the existing suite: `python -m pytest`.
- Add tests for the new behaviour in `tests/`, following the existing
  fixture style (`tests/conftest.py`'s `memory_store`/`config`
  fixtures, `tmp_path`-based isolation, no real network calls).
- If linting/type-checking tools are configured in the repo at the
  time of the task, run them; don't introduce a new tool
  (`ruff`, `mypy`, etc.) without saying so and checking it's wanted.
- Do a manual smoke test of any new CLI command or user-facing path
  (as done for the Milestone A CLI), then delete any data/artifacts
  the smoke test created before committing.

## 7. Diagnose failures, fix, and re-verify

- On any test/lint failure, fix the root cause, not the test — unless
  the test itself was wrong, in which case say that explicitly.
- Re-run the full suite after each fix, not just the previously
  failing test, to catch regressions.
- If something cannot be fixed in this session (e.g. an external
  dependency unreachable from this sandbox, as with `OllamaProvider`
  against a real Ollama server), say so plainly and document it as a
  known limitation rather than papering over it.

## 8. Security, privacy, and architecture review

- Before committing, check your own diff against: secrets/credentials,
  new network destinations, new write access to the filesystem outside
  the repo's data directory, anything that writes directly to
  "approved" memory bypassing the review inbox, and any new
  dependency's trust footprint.
- Prefer a second pass via the `jarvis-review` skill for anything
  non-trivial, especially security-sensitive changes — do not treat
  your own implementation pass as the review.

## 9. Update documentation and integration notes

- Update `docs/ARCHITECTURE.md` if the module map or known limitations
  changed.
- Update `docs/INTEGRATION.md` if a new interface, dependency, or
  config key was added that a future integration needs to know about.
- Update `README.md` if a user-facing command or capability changed.
- Add/update assumptions in `docs/MIGRATION_ASSUMPTIONS.md` if the
  change makes a new assumption about the (currently inaccessible)
  original Odysseus repository.

## 10. Commit and push

- Commit with a clear, descriptive message (what + why, feature ID if
  applicable).
- Push to the authorised development branch (`dev`) per `CLAUDE.md`.
  Never push to `main` without explicit instruction.
- Stage deliberately (`git status` after `git add`) — never commit
  generated data files (`data/`, `*.sqlite3`, logs) or anything that
  looks like a secret.

## 11. Final report

Report, concisely and honestly:
- What was completed (and which feature ID(s), if any).
- Files changed/added.
- Tests run and their result (pass/fail counts) — never claim "tests
  pass" without having actually run them in this session.
- Any failures encountered and how they were resolved, or why they
  remain unresolved.
- Known limitations or things explicitly left out of scope.
- Outstanding/follow-up work, if any, stated as suggestions, not as
  completed work.
