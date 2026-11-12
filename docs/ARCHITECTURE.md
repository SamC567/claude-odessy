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
    loopback.py        is_loopback_url(), shared by the registry and providers.

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
  distinct query terms matched (then confidence, then recency). A small
  built-in English stop-word list (`_STOP_WORDS` in `memory/store.py`)
  keeps words like "the"/"what" from acting as search terms; it is
  English-only and not configurable. An entry's tags are searched as
  well as its content. There is still no term weighting or
  stemming, and a word matches as a substring ("cat" matches "category",
  in content and in tags alike).
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

- `MemoryStore.get` / `approve` / `reject` / `retract` / `query` (F009) no longer let a raw `OverflowError` escape for an id or limit outside SQLite's 64-bit integer range. `sqlite3` raises `OverflowError` (not a `sqlite3.Error`) when asked to bind such a number, so it bypassed the store's typed errors: `memory show 99999999999999999999999`, `memory approve`/`reject`/`forget` with such an id and `memory search --limit` with such a number ended in a traceback. Such an id is now "not found" like any other unknown id (`get` returns `None`, review decisions raise `ReviewInboxError`), and such a limit means "all matches". No schema, config or interface change.

- CLI `memory search "text" [--limit N]` (F009 retrieval) prints the approved memories `MemoryStore.query` returns for a text, best match first, as `[id] (confidence, source) content`, without calling a model. Previously retrieval could only be observed through `chat` (the `(memory used: ...)` line, ids and sources only), so checking why a memory was or was not recalled meant sending a prompt to the model. The default limit is `memory.context_limit`, i.e. the set a `chat` with the same text would add to the prompt; with `context_limit: 0` it says so instead of listing nothing. Read-only and not audited; stored text is printed through `cli._printable`. It does not explain the ranking (no per-entry match count) and the retrieval limitation above (substring matching, no stemming) is unchanged.

- `memory remember` (F009) says when the fact is already stored. `MemoryStore.submit_candidate` keeps an existing PENDING/APPROVED entry with the same content instead of storing it twice, but the CLI printed `Submitted as entry [1] with status=approved` either way, which read as if the new submission had been stored (and auto-approved) and hid that its source, confidence and tags were dropped. The CLI now asks the new read-only `MemoryStore.find_duplicate(content)` first and prints `Already stored as entry [1] with status=approved (source=..., confidence=...); not added again. ...` (exit code 0). The stored entry is unchanged: provenance of a duplicate submission is still not merged; only the audit log's `memory.duplicate_candidate` record notes the duplicate's source.

- `MemoryStore` row decoding (F009/F073) treats a `tags` column that holds valid JSON other than a list as a corrupt row. The store only ever writes a JSON list, but a hand-edited value such as `"work"` used to be read back as one tag per character (`w`, `o`, `r`, `k`) and an object such as `{"work": 1}` as its keys, so `memory show` displayed tags nobody stored while retrieval (`_searchable_text`) ignored them. Such a row now raises `MemoryError_` like any other undecodable row (non-JSON tags, unknown status, bad timestamp), so `health`'s `memory_store` check counts it as an unreadable entry. The message names the JSON type found, not the stored value. Detection only: nothing is repaired or deleted.

- `health` memory check (F073/F009) reports stored entries that cannot be read. A row with an unknown status, tags that are not JSON, or a bad timestamp (a hand edit, a partial restore) passes SQLite's `quick_check` and is counted, so `memory_store` used to say `ok` while `memory list-*` failed and any `chat` whose retrieval returned that row answered degraded. `check_memory_store` now calls the new read-only `MemoryStore.unreadable_entry_ids()` and returns WARNING naming how many rows and the first five ids. Nothing is repaired or removed: there is still no command to fix or quarantine such a row, and the scan reads every row on each `health` run. A store object without `unreadable_entry_ids` is not checked for this (compatibility). Tags stored as a JSON string rather than a list still decode (one tag per character) and are not flagged.

- `health` config check (F073/F003) warns about an unknown `model.provider` whether or not `identity.allow_external_providers` is set. `build_provider` answers any name it does not know (a typo such as `olama`, a different case such as `Ollama`, a backend that does not exist here such as `openai`) with the echo fallback regardless of that flag, but `check_config` only warned while the flag was false; with it true the report said `config: ok — configuration loaded and valid` while no model was ever called. The warning now also says what happens and what would work: `model.provider='Ollama' is not a recognised provider (known: echo, ollama; names are case-sensitive): the echo fallback will be used`. The list of known names comes from `odysseus.models.registry.BUILTIN_PROVIDERS` (new public name for the existing set) instead of a second copy in diagnostics. Still a WARNING (exit code 0), and the config loader still accepts any provider name. Not covered: provider names are not case-folded or trimmed, and there is no mechanism for registering a custom provider through config, so every name other than the two built-ins gets this warning.

- `OllamaProvider.generate` (F003) treats a whitespace-only `response` as no answer, and its "no usable reply" error describes the body instead of quoting it. Previously only an empty string was refused, so a reply of spaces or newlines was returned as a live model's answer (`is_live_model=True`, no fallback) and `chat` printed a blank line. The error for an unusable reply used to embed the whole JSON body (`{data!r}`); a real `/api/generate` answer also carries `context` (thousands of token ids that encode the prompt) and timing fields, and that message is written to the audit log (`orchestrator.provider_failed`) and shown as the `(degraded: ...)` reason. The message now says what was wrong with the field (missing, not text, empty, blank) and quotes only `done_reason`, shortened to 200 characters (e.g. `'load'`, which is what Ollama reports when it only loaded the model). A reply with real text keeps its surrounding whitespace unchanged. Built against a simulated server, like the rest of this provider; not exercised against a live Ollama.

- CLI `error: ...` messages (F001) are printed with control characters made visible. `main()` and the two input-error paths (`chat`, `memory remember`) print through `cli._print_error`: each line of the message goes through the one-line `cli._printable` (control characters, Unicode line/paragraph separators and bidirectional-text controls shown as backslash escapes), line breaks are kept because configuration errors are multi-line, and every continuation line is indented by two spaces so only the first line can begin with `error:`. A message can quote text that is not the program's own: a path from the config file, an environment variable or `--config`, a value from a corrupt memory row. Previously a `memory.db_path` containing an escape sequence and a newline cleared the screen and printed a second, forged `error:` line (reproduced in this sandbox before the change). Display only: exception types, messages, exit codes and the audit log are unchanged, and a single-line message without such characters prints exactly as before; continuation lines of a multi-line message are now indented two spaces further. This closes the "`error: ...` messages are still printed as produced" item in the two entries below. Not covered: log lines written to stderr by `logging` (for example the "audit log ... is not writable" WARNING, which quotes `audit_log_path`) and argparse's own usage errors are printed as produced; a literal backslash is not doubled. Not run on Windows or looked at in a real terminal emulator.

- `health` CLI (F073) prints its human-readable report with control characters made visible: the summary line, each check's name and each check's detail go through the one-line `cli._printable` (control characters, Unicode line/paragraph separators and bidirectional-text controls shown as backslash escapes such as `\x1b`, `\n`, `\u202e`). A detail can quote text chosen by the model server (the installed model names from `/api/tags`, an error body, a redirect target), so previously that text could clear the screen or, with a newline, add a forged `  - memory_store: ok — ...` line to the report. Display only: `HealthReport`, the exit code and `health --json` are unchanged (JSON output already escapes control characters), and a report without such characters prints exactly as before. Not covered: `error: ...` messages printed by `main()` are still printed as produced; a path containing right-to-left text is shown with its bidi controls escaped; a literal backslash is not doubled. Tested with a scripted provider, not a live Ollama or a real terminal emulator.

- `chat` CLI (F001/F003) prints the model's reply and the `(degraded: ...)` reason with control characters made visible instead of sending them to the terminal. The reply goes through `cli._printable(..., multiline=True)`: line breaks, tabs, Unicode line/paragraph separators and bidirectional-text controls are kept (a reply is prose and may be multi-line or right-to-left), `\r\n` is printed as a plain newline, and every other control character (ESC, BEL, NUL, a bare carriage return, the C1 range) is shown as a backslash escape such as `\x1b`. Previously the reply was printed as received, so text produced by the model could clear the screen, retitle the window, overwrite the line already printed, or on some terminals write to the clipboard. The degraded reason, which can quote the model server's error body or redirect target, gets the one-line treatment used for memory listings (newlines and bidi controls escaped too). Display only: `InteractionResult.text` and the audit log are unchanged, and a reply without such characters prints exactly as before. Not covered: `health` details and `error: ...` messages are still printed as produced; bidi controls in a reply are not escaped, so a reply can still display in a different order from its stored characters; a literal backslash is not doubled. The built-in echo fallback was not affected (it already quotes the prompt with `repr`). Tested with a scripted provider, not a live model or a real terminal emulator.

- `OllamaProvider` (F003) does not follow HTTP redirects from a loopback `base_url`: the session it creates for `localhost` / a loopback IP has `max_redirects = 0`, so a redirect is refused before anything is sent to its target. Previously `requests` followed redirects, and a 307/308 answer from whatever was listening on the loopback port made it re-send the `/api/generate` POST, prompt and approved-memory context included, to the redirect target, which could be any host; `health_check` could likewise report a server somewhere else as the healthy local one. `generate` now raises `ModelProviderError` naming the target ("the server answered with a redirect to '...', which was not followed") after a single attempt, so `chat` falls back to echo with that reason; `health_check` returns unhealthy with the same note (diagnostics WARNING). Not covered: a session passed in by the caller is left as given; a non-loopback `base_url` (only reachable with `identity.allow_external_providers: true`) still follows redirects, including to hosts other than the configured one; the redirect target is quoted in the error and audit log as sent by the server (whitespace-collapsed, capped at 200 characters). Verified against two in-process loopback HTTP servers, not a live Ollama.

- `OllamaProvider` (F003) connects directly to a loopback `base_url`, ignoring proxy environment variables: when it creates its own HTTP session for `localhost` / a loopback IP it sets `trust_env = False`. Previously `requests` applied `HTTP_PROXY` / `ALL_PROXY` to the call unless `NO_PROXY` happened to list the host, so on a machine with a proxy configured the prompt (with its approved-memory context) was handed to that proxy instead of the local server, and the local model looked unreachable. `is_loopback_url` moved to `odysseus/models/loopback.py` so the provider can use it without importing the registry; it is still importable from `odysseus.models.registry`. Not covered: a session passed in by the caller is left as given; a non-loopback `base_url` (only reachable with `identity.allow_external_providers: true`) still honours proxy variables; `trust_env = False` also turns off `~/.netrc` credentials and the `REQUESTS_CA_BUNDLE` override for that session, which a plain-HTTP loopback server does not use. Verified against two in-process loopback HTTP servers, not a real proxy or a live Ollama.

- Config `memory.context_limit` (F001/F009): the number of approved memories the orchestrator may add to one model prompt is a configuration value (default 3, range 0-50, env `ODYSSEUS_MEMORY__CONTEXT_LIMIT`) instead of the literal `3` that only a caller constructing `Orchestrator` in code could change. The CLI passes it to `Orchestrator(memory_context_limit=...)`. `0` keeps approved memory out of the prompt altogether while leaving it stored, listable and reviewable. A boolean, a fractional number or a value outside the range is a `ConfigError`. Default behaviour is unchanged. Not covered: the limit counts entries, not characters or tokens, so a few very long memories can still crowd a small model's context window; `Orchestrator` itself does not validate a `memory_context_limit` passed directly in code (a negative value behaves like 0).

- Memory CLI output (F009 review workflow) shows stored text with control characters made visible: `memory list-pending` / `list-approved` / `list-rejected` / `show` and the `(memory used: ...)` line of `chat` print content, source, tags and reviewer through `cli._printable`, which renders control characters (newline, tab, ESC, ...), Unicode line/paragraph separators and bidirectional-text controls as backslash escapes (`\n`, `\x1b`, `\u202e`). Previously they were printed as stored, so a candidate containing a newline could forge a second `[id] (...) ...` line in the review inbox, and terminal escape sequences or a right-to-left override could hide or reorder what the reviewer was approving. Display only: the stored entry, retrieval and the text injected into the model prompt are unchanged. Not covered: `health` details and error messages (the model's reply and degraded reason printed by `chat` are handled separately, see above); a literal backslash is not doubled, so the two characters `\n` typed by a user look the same as an escaped newline; other invisible format characters (zero-width space/joiner) are left alone because ordinary text in several scripts and emoji uses them.

- `MemoryStore.query` (F009) searches an entry's tags as well as its content: an approved entry tagged `allergy` is retrieved by "any allergy?" even when its content never uses the word. Previously tags were stored and displayed (`memory show`) but ignored by retrieval, so tagging a memory had no effect on what reached the model prompt. Matching follows the content rules (case-insensitive including non-ASCII, substring, stop words ignored, approved-only); a term found in both content and a tag counts once for ranking, and a phrase cannot match across the content/tag boundary or across two tags. No interface, schema or config change; the internal SQL helper `fold` was replaced by `searchable(content, tags)`. A row whose stored tags are not valid JSON is matched on content alone and, as before, raises `MemoryError_` only if it is actually returned. Tag matches are not weighted differently from content matches, and there is no tag-only filter (e.g. "everything tagged X") in the store or CLI.

- `MemoryStore.query` (F009) no longer uses English stop words ("the", "what", "with", ... — `_STOP_WORDS`, about 55 words of three or more letters) as search terms. Previously almost any question matched every approved entry containing "the" or "what", so with fewer relevant entries than the orchestrator's limit of 3, unrelated memories were injected into the model prompt (and shown as `memory used`). The whole query text is still matched as a substring, so `query("the")` and phrases such as "the umbrella" behave as before; a query made only of stop words and words under three letters now returns nothing unless the whole text matches. English only; words that are also common names or nouns ("will", "can", "may") are deliberately not in the list.

- `health` (F073/F003) diagnoses the fallback provider as well as the primary one: `run_diagnostics(..., fallback_provider=)` adds a `fallback_provider:<name>` check, and the CLI passes the orchestrator's fallback (the built-in `EchoProvider`). Previously only the primary provider was checked, so a report showing `model_provider:ollama: warning` gave no evidence about whether the provider `chat` degrades to could answer. An unhealthy fallback is WARNING while the primary is healthy and CRITICAL when the primary is not healthy either (no provider can answer). The check is omitted when no fallback is passed or it is the same object as the primary, so existing callers are unaffected. With the built-in echo fallback the check is always OK; the non-OK states are reachable only with a custom fallback provider and are tested with test doubles. Still open for F073: there is no check for services other than the model providers, memory store and audit log (Milestone A has no other services).

- Config `audit_log_path` (F001/F073): the audit trail's location is a configuration value (top-level, default `data/audit.log`, env `ODYSSEUS_AUDIT_LOG_PATH`) instead of the literal `"data/audit.log"` repeated three times in `cli.py`. `chat`/`memory`/`config` write the trail there and `health`'s `audit_log` check inspects the same path. A blank value is a `ConfigError` (it would otherwise silently make the trail stderr-only). Default behaviour is unchanged. Still open: a relative `audit_log_path` or `memory.db_path` is resolved against the process working directory, not the project root (the `memory.db_path` field description says "project root"), so running the CLI from another directory uses a different `data/` folder unless absolute paths are configured.

- CLI `memory show <id>` (F009 source tracking) prints one entry's full stored record: content, status, source, confidence, tags, creation time, reviewer and review time (UTC). Previously tags given to `memory remember --tags` and an entry's creation time were stored but shown by no command, so they could only be read from SQLite directly. Read-only, uses the existing `MemoryStore.get`; an unknown id prints `error: No memory entry with id=N` and exits 2. Tags are still not used by retrieval (`MemoryStore.query` matches content only).

- `MemoryStore.list_rejected()` and CLI `memory list-rejected` (F009 review workflow): rejected and retracted entries were kept in the database "so the action is inspectable", but nothing could list them — only `list-pending` and `list-approved` existed, so who rejected or withdrew a fact, and when, could only be read from `data/audit.log` or SQLite directly. The command prints id, confidence, source, reviewer, review time (UTC) and content, oldest first. Read-only. A rejection and a retraction both carry the REJECTED status, so the listing does not say which of the two an entry was (the audit log's `previous=` field does).

- `chat` CLI (F009 source tracking) prints which approved memories informed an answer, e.g. `(memory used: [1] source=user-note)`, on stderr; the `[id]` is the one `memory forget` takes. Previously `InteractionResult.memory_sources` was recorded and audited but never shown, so a user could not tell from the CLI that memory shaped an answer, or which entry to retract. Only id and source are shown (not the content); nothing is printed when no memory was used. Stdout is unchanged.

- `MemoryStore(db_path)` (F009/F073) raises `MemoryError_` when the database's directory cannot be created (a file where the directory should be, an unwritable parent); previously a raw `OSError` escaped, so every CLI command ended in a traceback and `health` produced no report. `health` now shows `memory_store` CRITICAL with the rest of the report; other commands print `error: ...` and exit 2. A caller that caught `OSError` from the constructor must catch `MemoryError_` instead (none in this repo). Windows ACL behaviour untested here.

- `OllamaProvider.generate` (F003) no longer retries an HTTP 4xx response other than 408/429: a model that has not been pulled answers 404 on every attempt, so the previous `max_retries` extra requests only delayed the fallback. 5xx, 408, 429, timeouts and responses with no readable status are retried as before. The error now reports the attempts actually made (`after 1 attempt(s)`) rather than `max_retries + 1`. Tested against a simulated server only.

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
