# Jarvis / Odysseus — Project Instructions

## Project identity

This repository (`claude-odessy`) is an **independent development and
validation workspace** for the Jarvis / Odysseus assistant project. It
is **not** the original Odysseus repository, which is currently
inaccessible. Code here is built to be integration-ready, not assumed
already merged — see `docs/INTEGRATION.md` and
`docs/MIGRATION_ASSUMPTIONS.md`.

Feature IDs span **F001–F134**. Only the features explicitly approved
for the current milestone are in scope at any given time (currently
Milestone A: F001, F003, F009, F073 — see `docs/ARCHITECTURE.md`).
**Do not expand scope to other feature IDs without being asked.**

## Governing principles (apply to every task, not just Milestone A)

- **Local-first, privacy-first.** No outbound network calls beyond an
  explicitly configured local model server (loopback by default). No
  prompt, memory, or personal data leaves the machine to an external
  service without the user's explicit, informed authorisation.
- **Modular architecture, documented interfaces.** New features are
  independent-but-interoperable modules with a clear interface, in the
  style of `odysseus/models/base.py` (`ModelProvider`) and
  `odysseus/memory/store.py` (`MemoryStore`). Depend on interfaces, not
  concrete implementations, so pieces stay swappable and testable.
- **Least privilege, explicit permissions, reversible operations.**
  Every autonomous action should be logged (`odysseus.logging_setup.audit`)
  and, where feasible, reversible. No unrestricted shell execution. No
  hardcoded secrets, API keys, or credentials anywhere in the repo —
  use environment variables / config examples (see `config/.env.example`)
  and never commit real values.
- **No unapproved external data transfers.** Treat any new integration
  that could send local data (memory contents, user input, file
  contents) to an external API as requiring explicit sign-off before
  implementation, not after.
- **Preserve compatibility.** Changes that affect existing module
  interfaces need a documented adapter or a migration note in
  `docs/INTEGRATION.md` / `docs/MIGRATION_ASSUMPTIONS.md`, not a silent
  breaking change.
- **Honesty over completeness.** Never claim something has been
  tested, completed, or integrated unless it actually has, verified in
  this session (test output, a command run, a passing check). If a
  feature is partial, say so explicitly and document what remains in
  `docs/ARCHITECTURE.md`'s limitations section or equivalent.
- **Follow existing conventions.** Match this repo's existing patterns
  (module layout under `odysseus/`, dataclasses + pydantic config,
  `ModelProviderError`-style typed exceptions, pytest with `tmp_path`
  fixtures, audit logging at decision points) rather than introducing a
  new style or a new dependency unnecessarily. Prefer stdlib and the
  already-used libraries (`pydantic`, `PyYAML`, `requests`, `pytest`).

## Workflow

For any non-trivial implementation task (new feature, bugfix touching
more than a couple of lines, refactor, or anything spanning multiple
files), **use the `jarvis-development` skill** — it is the standing
procedure for understanding, planning, implementing, testing, and
reporting on work in this repo. Invoke it automatically when a task's
shape matches (see that skill's description for triggers); it can also
be invoked explicitly as `/jarvis-development`.

For reviewing a change — your own just-completed work, another
session's diff, or an existing PR — **use the `jarvis-review` skill**
(`/jarvis-review`). It is independent of the development skill and
must not be treated as a rubber stamp on work just produced in the same
session.

Skip both skills' full process for genuinely trivial changes (a typo, a
one-line doc fix) — use judgment on depth, per the skill's own
guidance.

## Branching

Develop on `dev` and push there unless explicitly told otherwise. Do
not push to `main` without explicit instruction.
