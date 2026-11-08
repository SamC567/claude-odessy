---
name: jarvis-review
description: Independent review workflow for a change in this repository — a diff, a commit, a PR, or work just completed in this session (by this session or another one). Checks correctness and edge cases, security/permission boundaries, privacy and data handling, architectural compatibility with the existing modular design, unnecessary complexity or dependencies, test quality/coverage gaps, and documentation accuracy. Distinguishes verified defects from unverified concerns and never treats a change as approved just because it was the model's own recent output. Use when asked to review, audit, or sanity-check code, or as the self-check step of jarvis-development for non-trivial changes.
---

# Jarvis Review Workflow

Independent review for the Jarvis / Odysseus workspace. This is a
separate pass from implementation — if you (this session) just wrote
the code under review, treat it with the same scrutiny as someone
else's PR, not as a formality to close out. Do not auto-approve your
own just-completed work.

## What to review

Default to the current diff (`git diff`, or against the merge-base of
the working branch vs. `dev`/`main`) unless given a specific target
(PR number, branch, commit range, file path). If invoked right after
`jarvis-development`, review the actual diff produced, not the plan
that preceded it.

## Checklist

For each dimension, look for concrete evidence in the diff — don't
assert a category is fine without having actually checked it.

1. **Correctness and edge cases**
   - Empty/None/boundary inputs (empty prompt, confidence at 0.0/1.0,
     empty memory store, missing config file).
   - Error paths: does a failure raise the right typed exception
     (`odysseus/exceptions.py`) rather than leaking a backend-specific
     one? Does the caller actually handle it, or just happen not to
     crash in the happy path tested?
   - Off-by-one / state-transition bugs, especially around the memory
     review-inbox lifecycle (pending → approved/rejected) and any new
     status transitions.

2. **Security and permission boundaries**
   - No hardcoded secrets, tokens, or credentials.
   - No new unrestricted shell execution or path traversal.
   - Any new network call: is it to a declared, local-by-default
     destination? Is it gated behind explicit config rather than
     always-on?
   - Least privilege: does new code request/assume more access than
     it needs (filesystem, network, memory-store writes)?

3. **Privacy and data handling**
   - Does anything send prompt content, memory contents, or user data
     to an external service? If so, is that explicitly authorised and
     documented, not incidental?
   - Does new code respect the review-inbox gate — i.e. no path writes
     directly to `APPROVED` status, bypassing `MemoryStore.approve`?
   - Is `allow_external_providers` (or an equivalent permission gate)
     actually checked before anything non-local is used?

4. **Architectural compatibility**
   - Does new code depend on interfaces (`ModelProvider`, `MemoryStore`)
     rather than reaching into a concrete implementation's internals?
   - Does it fit the existing module boundaries (`odysseus/core`,
     `odysseus/models`, `odysseus/memory`, `odysseus/health`) or does
     it blur them?
   - Does it introduce a new orchestration path that duplicates
     `Orchestrator`'s responsibilities instead of extending it?

5. **Unnecessary complexity or dependencies**
   - New third-party dependency: justified, or could stdlib /
     already-used libraries do it?
   - Over-engineered abstraction for a one-off need, or a shortcut that
     will clearly need rework at the next feature (call this out as a
     concern, not a defect, if uncertain).

6. **Test quality and coverage gaps**
   - Do new tests exercise the actual failure modes (provider
     unavailable, invalid confidence, unknown entry id), not just the
     happy path?
   - Any test that passes vacuously (e.g. asserts something trivially
     true, or never calls the code under test)?
   - Run the suite yourself (`python -m pytest`) rather than trusting
     a prior "tests pass" claim — report the actual result.

7. **Documentation accuracy**
   - Does `docs/ARCHITECTURE.md` / `docs/INTEGRATION.md` /
     `README.md` still match what the code actually does after this
     change, including any new limitation?
   - Do docstrings/comments describe current behaviour, not a stale or
     aspirational version of it?

## Reporting findings

- State each finding as a **concrete failure scenario**: what input or
  state leads to what wrong behaviour, not a vague "this could be an
  issue."
- Separate **CONFIRMED** defects (you traced the exact path to a wrong
  outcome, ideally by running something) from **PLAUSIBLE** concerns
  (reasonable suspicion, not yet traced to a concrete failure) — label
  them as such; don't present a hunch as a confirmed bug.
- Note what you checked and found *fine*, briefly — a review that only
  lists problems looks the same whether it checked everything or
  almost nothing.
- End with an explicit verdict: approve as-is, approve with the noted
  follow-ups, or do-not-merge with the blocking defects named. Don't
  leave the user to infer the verdict from the findings list.
- If this skill is being run on this session's own just-completed
  work, say so explicitly in the report ("self-review of the preceding
  change") rather than presenting it as independent.
