# Module review sign-off journal

Each module goes through a fixed checklist: full read ×2, one shared correctness
checklist, a regression test for every past bug, `pyflakes` + `ruff` clean.
Stop rule: two consecutive full reads with no P1/P2 finding → module closed.
P3 (cosmetic, rare design edges) goes to "Deferred" and does not block closing.
Return to a closed module only for a specific reason.

Pass 7 (this journal) started at `188a550`. Use `git log --follow REVIEW.md` for
the history of a section.

---

## `telemirror/mirroring.py` — closed 2026-08-30

Full read ×2. Tests: 126 green, `pyflakes` + `ruff` clean.

### Invariants
- A row in the `messages` table exists only for a message that was actually
  delivered. The reverse (delivered but untracked) happens in exactly two
  documented places: the follow-up text message on `MediaCaptionTooLongError`,
  and — after the fix below — no longer on the split-path abort.
- On `FloodWaitError` / `FloodPremiumWaitError` during fan-out: what was already
  sent is persisted (`flush_inserted()` in `new_message`; per-target
  `insert_batch` in `new_album`), and the exception propagates up to
  `past_mode._replay_with_retry` without advancing the checkpoint. In live mode
  this aborts the rest of the fan-out for that message — a deliberate trade-off.
- `_sync_broadcast_channel` is idempotent: a restart on an already-synced channel
  does ~0 re-sends; only message ids are held in memory, never the history.
- `_sync_broadcast_channel` no longer seeds an empty `broadcast_sync` from
  `messages` (pass 20): every post goes through `new_message`, whose per-target
  `already_mirrored` dedup skips targets that still hold a mirror.
- `edit_message` edits each mirror once (first matching config); forward mode and
  `disable_edit` are skipped.
- `delete_message`: `disable_delete` is honored per-channel; the DB rows for the
  source id are dropped wholesale — safe, because the source message is gone.
- `TelegramLogHandler` never raises out of `emit`; Telegram errors are swallowed.
- `__connect_client` runs once per process lifetime (no reconnect loop), so
  `TelegramLogHandler` does not accumulate.

### Fixed in this pass
- **P2** `new_message` / `new_album`, `MediaCaptionTooLongError` split path: when
  the media message was already sent but the follow-up text send failed,
  `except split_err` did `continue` → the delivered media was never written to
  the DB (a later edit/delete of the source can't reach it). Now falls through:
  the media is tracked, only the text tail is lost. Tests:
  `tests/test_caption_too_long_split.py`.

### Fixed in pass 8 (whole-project sweep re-run on explicit request)
- **P2** `new_message` / `new_album`, `MediaCaptionTooLongError` split path: the
  inner `except Exception as split_err` also caught `FloodWaitError` /
  `FloodPremiumWaitError` raised while (re)sending the *media* — the outer flood
  handler only covers the first send. In past_mode this swallowed the flood and
  the checkpoint advanced past an un-mirrored message (same class as the pass-7
  `RestrictSavingContentBypassFilter` fix). Now the media (re)send has its own
  `except (FloodWaitError, FloodPremiumWaitError)` → `flush_inserted()` (new_message
  only) + `raise`; the text/caption tail keeps its broad `except` → swallow (the
  tail is still allowed to be lost). Tests: `tests/test_caption_too_long_split.py`
  (`..._flood_on_media_retry_propagates`, `..._flood_on_text_tail_is_swallowed`).
- **P3 → fixed** `new_album` tracking: `original_id=idxs[message_index]` over
  `enumerate(outgoing_messages)` positionally zips the sent messages against the
  source ids. A count mismatch from `send_file` meant either an `IndexError`
  (swallowed by `__handle_exceptions` → the whole album untracked) or rows mapped
  to the wrong `original_id` (a later edit/delete of source X hits mirror Y). Now
  guarded: on `len(outgoing_messages) != len(idxs)` the album is left untracked
  with an explicit `[New album]: ... NOT tracked` error log instead of a
  wrong/partial write. Test: `tests/test_new_album_index_guard.py`.

### Missing regression tests added for past-pass bugs
- `tests/test_mirroring_signoff.py`:
  - a `noforwards` source with copy-mode filters that don't allow restricted
    content → nothing sent or tracked (pass 1: `bool()` wrap on the guard);
  - `event_message_link` on a `MessageDeleted` event → the `else` branch, no
    `NameError` (pass 4: `elif` → `else`).

### Deferred (P3, non-blocking)
- `_sync_broadcast_channel`: a crash between `new_album()` returning and the
  `set_broadcast_sync` loop → the whole album is re-sent on the next start
  (narrow partial-failure window; the docstring already allows "a rare failed
  first-time send won't auto-retry").
- `_sync_broadcast_channel`: a message missing from `iter_messages` due to an API
  hiccup is treated as a source deletion → the mirror is deleted.
- `new_album` ~line 569: `idxs[message_index]` over `enumerate(outgoing_messages)`
  still assumes the returned messages are in the same *order* as the source items
  when the *counts* match (the count-mismatch case is now guarded — see above).
- `new_album` forward mode: `is_list_like(outgoing_messages)` — a single-message
  `forward_messages` response would not be tracked.
- `new_message` ~line 387: `original_id=filtered_message.id` — works
  (`copy_message` preserves `.id`), but `message.id` would read clearer.
- (pass 8) `edit_message`: the `except Exception` around `client.edit_message`
  also swallows a `FloodWait` > 300s — the edit is silently skipped. No message
  loss (the mirror is already delivered) and no checkpoint move; consistent with
  the "edits are best-effort" stance elsewhere.
- (pass 8) `delete_message`: a `FloodWait` (or any error) on `delete_messages` is
  logged, then `delete_messages_batch` drops the DB rows anyway → the mirror
  message survives as an orphan with no way to retry the delete. Over-retention,
  not loss; the source message is already gone.
- (pass 8) `_sync_broadcast_channel` runs (line ~1138) before `EventHandlers` is
  constructed (~1146); on a first-time / post-downtime sync that takes a long
  time, live updates in non-broadcast source channels during that window may be
  missed. Startup-only, and the sync itself is idempotent. Not re-verified
  against Telethon's actual update-buffering behaviour — raise to P2 if a normal
  path is shown to drop updates.

---

## `config.py` — closed 2026-08-30

Full read ×2. Tests: 126 green, `pyflakes` + `ruff` clean. No code change — no
P1/P2 found.

### Invariants
- Config loading is entirely fail-fast at import: any format error (unknown
  filter, non-numeric id, ≠1 `past_mode` strategy, empty `CHAT_MAPPING`) crashes
  the process at startup, not at runtime.
- Source priority: `YAML_CONFIG_ENV` → `.configs/mirror.config.yml` → env
  (`CHAT_MAPPING`). The YAML and env branches are mutually exclusive.
- `_channel_id`: `""` and `"0"` mean "unset" (None); anything else non-numeric →
  `ValueError` naming the variable.
- `PastModeConfig.__post_init__`: `since_date` from datetime/date/ISO string is
  normalized to `datetime`; exactly one strategy or `ValueError`.
- Broadcast expansion (`BROADCAST_CHANNEL`): synthetic `BROADCAST_CHANNEL → target`
  directions are created for every target from the other directions (or from an
  explicit `BROADCAST_TARGETS`), deduped by `(target, to_topic_id)` against
  hand-configured ones. Always `EmptyMessageFilter` + `mode="copy"`.
- Filter instances: in the env branch, one shared across all directions; in the
  YAML branch, fresh per pair except the shared `default_filters` fallback.
  Filters are treated as stateless (or with an intentionally shared cache —
  `DocumentFilenameFilter`).

### Regression tests for past bugs (present, `tests/test_config.py`)
- `_channel_id` blank/zero/non-numeric (pass 5).
- `since_date` coercion datetime/date/str (pass 1).
- `PastModeConfig` strategy count.
- `build_dsn` percent-encoding — `tests/test_build_dsn.py`.

### Deferred (P3, non-blocking)
- Trailing comma in env `CHAT_MAPPING` (`filter(None, …)`, pass 5.1) — no direct
  test: `build_mapping_from_env` is a nested function in the env branch, which is
  inactive under tests (YAML is always present). The fix is trivial and obvious.
- Empty YAML file (`yaml.safe_load` → None) → an opaque `TypeError` instead of a
  clear error at `"broadcast_channel" in yaml_config` / `yaml_config["directions"]`.
- `RepositoryMultilineEnv.__init__(encoding=...)`: the `Ellipsis` default is never
  exercised (decouple always passes `encoding=`), but would break on its own.
- `build_filters`: a YAML filter dict with >1 key silently takes only the first.
- Synthetic broadcast directions ignore the global YAML `filters:` / `mode:`
  (always `EmptyMessageFilter` + copy) — by design, but non-obvious.

---

## `telemirror/storage.py` — closed 2026-08-30

Full read ×2. Tests: 134 green, `pyflakes` + `ruff` clean. No code change — no
P1/P2 found. Added the missing `tests/test_storage.py` (8 tests over the
`InMemoryDatabase` public contract).

### Invariants
- `InMemoryDatabase.__storage` is an `LRUCache` of `MAX_CAPACITY=100` keys of the
  form `"{channel}:{original_id}"`. Inserts (`insert`/`insert_batch`) go through
  `setdefault` → `__setitem__` → eviction works; `get_messages` goes through
  `LRUCache.get` → `__getitem__` → recency is refreshed.
- `get_all_messages_for_channel` / `..._for_channel_pair` filter by the
  `"{channel}:"` prefix — the `:` is the boundary, channel `100` does not match
  `1000:5`.
- `get_broadcast_sync` returns a copy (`dict(...)`) — a caller's mutation does not
  leak into storage.
- Checkpoints and `broadcast_sync` are plain dicts, not LRU (one entry per
  source/target pair — small, growth is not a concern).
- `PostgresDatabase.__pg_cursor`: `OperationalError` (a `DatabaseError` subclass,
  checked first) → `pool.check()` + reraise without rollback; other
  `DatabaseError` → `con.rollback()` + reraise. The pool auto-commits/rolls back
  on exit from `pool.connection()`.
- `close()`: Postgres closes the pool (safe even if never opened), InMemory is a
  no-op. Only reachable after a successful `AsyncConnectionPool(...)` in
  `_async__init__`.

### Regression tests for past bugs
- `LRUCache.get` recency (pass 3) — `tests/test_lrucache.py`.
- `broadcast_sync` (pass 5) — `tests/test_broadcast_sync.py` + new
  `tests/test_storage.py`.
- New `tests/test_storage.py`: insert_batch/get roundtrip, batch queries,
  deletion, capacity eviction, prefix-exact channel filter, checkpoints,
  copy semantics of `get_broadcast_sync`.

### Deferred (P3, non-blocking)
- `PostgresDatabase` is not covered (needs a live server) — reviewed by reading:
  DDL, `class_row(MirrorMessage)`, `executemany` for the batch, `ANY(%s)` are all
  correct.
- `get_messages` (InMemory) returns the internal list itself, not a copy —
  theoretical aliasing, but no caller mutates it.
- `insert` via `setdefault` on an existing key does not `move_to_end` (a second
  mirror of the same message doesn't bump recency).
- `raise e` instead of `raise` in `__pg_cursor` (style; traceback is not lost in
  py3).

---

## `past_mode.py` — closed 2026-08-30

Full read ×2. Tests: 135 green, `pyflakes` + `ruff` clean. No code change — no
P1/P2 found. Added a test for `_edit_links_pass` (was uncovered).

### Invariants
- The checkpoint advances only after a message/album is processed
  (`process_single`/`process_album` after `new_message`/`new_album`). `min_id` is
  exclusive — resume continues from the next one.
- `FloodWaitError` / `FloodPremiumWaitError` (from `iter_messages` or from a send,
  re-raised by `mirroring`) do NOT advance the checkpoint: they propagate up to
  `_replay_with_retry`, which sleeps `e.seconds` and restarts `_replay_direction`
  (which re-reads the already-advanced checkpoint).
- A partial/failed (non-flood) `new_album` in past_mode STILL advances the
  checkpoint (`__handle_exceptions` swallows it) — the same trade-off as live.
- `_integrity_check` never rolls the checkpoint forward (pass 20): rows past it
  can come from the live mirror, and already-mirrored messages are skipped per
  target by `new_message`'s own dedup.
- `last_n` without a checkpoint → buffer into memory (newest first), reverse;
  with a checkpoint → stream with `min_id`, `iter_total = last_n - mirrors_done`.
- Service messages (`iter_message_groups` drops non-`Message` items) produce no
  mirror and do not advance the checkpoint.
- `_edit_links_pass` — a second, best-effort pass: fixes cross-channel `t.me`
  links in already-sent mirrors via `_rewrite_links` + `client.edit_message`.

### Regression tests for past bugs (`tests/test_past_mode.py`)
- `_replay_with_retry` covers both flood types (pass 6).
- FloodWait during a send does not advance the checkpoint (both types).
- integrity-check: no checkpoint / checkpoint without mirrors / stale rollback /
  healthy.
- grouping + checkpoint, `last_n` buffer, resume from checkpoint.
- New: `_edit_links_pass` rewrites a cross-message link to its mirror.

### Deferred (P3, non-blocking)
- `_run`: `await client.connect()` has no time bound (unlike
  `Mirroring.__connect_client`) — an operator script, the operator will see it
  hang.
- `_run`: `database` is created and `client.connect()`/`get_me()` run before the
  `try/finally` — on their failure `database.close()` / `client.disconnect()` are
  not called (the process exits anyway).
- `_edit_links_pass`: `except Exception` on `client.edit_message` also swallows a
  FloodWait > 300s — edits are simply skipped (best-effort pass).

---

## `telemirror/messagefilters/messagefilters.py` + `base.py` — closed 2026-08-30

Full read ×2. Tests: 143 green, `pyflakes` + `ruff` clean.

### Invariants
- `FilterAction`: `CONTINUE` (next in the chain), `FORCE_SEND` (send as-is, exit),
  `DISCARD` (do not send). `CompositeMessageFilter` and `_process_album` stop on
  `DISCARD`/`FORCE_SEND`.
- `restricted_content_allowed` defaults to `False`; `CompositeMessageFilter` is
  `any(...)` over its sub-filters.
- `_compile_keyword`: `r'...'` → raw regex, otherwise `\bliteral\b`; a broken
  pattern → `ValueError` with context (not a bare `re.error`).
- An empty keyword set for `SkipWithKeywordsFilter`/`AllowWithKeywordsFilter` →
  `ValueError` (otherwise `re.compile("")` matches everything).
- `KeywordReplaceFilter._apply_rule`: `re.sub` runs left to right, `match.span()`
  is in original coordinates, `offset_error` maps into result coordinates;
  case-transfer applies only to plain keywords, `r'...'` keeps its casing.
- `UrlMessageFilter`: first edits per entity (`update_entities_params` on the
  placeholder diff), then a "double check" — a second `search` over the text with
  a running `offset_error`. A link preview with a blacklisted URL → `media = None`.
- `ForwardFormatFilter`: `{message_text}` substitution via `.replace` (not a
  second `.format`), so `{`/`}` in a channel name can't drop the message;
  header entities are shifted by the real text length; for an album the first
  non-empty item is processed.

### Fixed in this pass
- **P2** `ForwardFormatFilter.__init__`: a format string without `{message_text}`
  passed validation, but at runtime `_process_message` found `offset == -1`,
  dropped the original message text, and shifted header entities by a nonsense
  diff. Now a `ValueError` at construction. Test: a new case in
  `tests/test_forward_format_filter.py::test_invalid_format_rejected`.

### Regression tests for past bugs
- `ForwardFormatFilter` `.replace` instead of a second `.format` + format
  validation (passes 1/5) — `tests/test_forward_format_filter.py`.
- `_compile_keyword` / regex casing / entity alignment (passes 1/5) —
  `tests/test_keyword_replace_filter.py`.
- Empty/broken keyword set — `tests/test_keyword_replace_filter.py`.
- Filters don't crash on `message.message is None` (pass A4) —
  `tests/test_filters_captionless.py`.
- New `tests/test_url_filters.py`: `SkipUrlFilter` (url entity, mention toggle),
  `SkipWithUrlFilter` (prefix match on TextUrl and mention), `UrlMessageFilter`
  (blacklist redaction, whitelist preservation).

### Deferred (P3, non-blocking)
- `_compile_keyword`: an empty-string key (`""`) → `\b\b`, matches almost
  everything (only the empty set is caught, not an empty element).
- `KeywordReplaceFilter`: `.lower()/.title()/.upper()` are applied to a surrogate
  string; rare breakage for non-BMP — harmless in practice.
- `SkipWithUrlFilter._normalize` ignores `www.` and non-http(s) schemes
  (documented).
- `EmptyMessageFilter`/`SkipAllFilter` override `process`, and their
  `_process_message` is `raise NotImplementedError` — fine, since `process` never
  delegates.
- (pass 8) `_compile_keyword` raw branch (`r'...'`): the pattern is compiled and
  run against every message body with no size / ReDoS guard. The pattern comes
  from the operator's own config, so this is self-inflicted; noted only.
- (pass 8) `SkipWithKeywordsFilter` / `AllowWithKeywordsFilter`: the final
  `re.compile("|".join(...))` over the combined alternation is not wrapped in the
  contextual `ValueError` that per-element `_compile_keyword` gets — a broken raw
  element surfaces as a bare `re.error`.
- (pass 8) `KeywordReplaceFilter._apply_rule`: for a plain (non-`r'...'`) keyword
  the replacement string is still passed through `match.expand`, so a literal
  replacement containing `\1` / `\g<0>` / a stray backslash is reinterpreted
  rather than inserted verbatim. Needs an unusual config to hit.

---

## `telemirror/messagefilters/` — media filters — closed 2026-08-30

`_media.py`, `restrictsavingfilter.py`, `documentfilenamefilter.py`,
`watermarkfilter.py`. Full read ×2. Tests: 145 green, `pyflakes` + `ruff` clean.

### Invariants
- `ReuploadCache` (TTL 600s, LRU 16): one re-upload is reused across the whole
  fan-out (key = `source_media_id`: `photo.id` / `document.id`). One instance per
  direction, lives for the process.
- `downloaded_tempfile` / watermark temp files: `delete=False` + a guaranteed
  `os.unlink` in `finally` (including on download failure).
- `RestrictSavingContentBypassFilter`: noforwards + media → download + re-upload;
  non-file media (poll/geo/...) passes through; a document > ~2 GB or any
  re-upload failure → `DISCARD` (protected media can't be sent without a fresh
  file).
- `DocumentFilenameFilter` / `WatermarkRemovalFilter`: a processing failure →
  log + `CONTINUE` with the original (degrade without losing the message; the
  rename / watermark removal is skipped).
- `DocumentFilenameFilter._rename` is idempotent (`stem == suffix` or
  `endswith(f" - {suffix}")`), safe for media already re-uploaded upstream
  (`InputMediaUploadedDocument` — `file_name` patched in place).

### Fixed in this pass
- **P2** `RestrictSavingContentBypassFilter._process_message`: `except Exception`
  also caught `FloodWaitError`/`FloodPremiumWaitError` → turned them into a
  `DISCARD` → in past_mode the checkpoint advanced past an un-mirrored message
  (silent loss). Now both flood types propagate (the same contract as
  `mirroring.py` / `past_mode._replay_with_retry`). Test:
  `tests/test_restrict_saving_filter.py`.

### Regression tests for past bugs
- `_rename` idempotency (passes 5/5.1) — `tests/test_document_filename_filter.py`.
- `ReuploadCache` TTL/LRU (pass 5) — `tests/test_reupload_cache.py`.
- media helpers — `tests/test_media_helpers.py`.
- watermark oversize-video guard — `tests/test_watermark_size_guard.py`.
- New `tests/test_restrict_saving_filter.py`: flood → propagate, else → DISCARD.

### Deferred (P3, non-blocking)
- `DocumentFilenameFilter` / `WatermarkRemovalFilter`: `except Exception` also
  swallows a flood > 300s — but here that only skips cosmetics (the message is
  still sent), so it's not critical.
- `RestrictSavingContentBypassFilter._process_document` carries the original
  `doc.attributes` onto the re-uploaded file (including video/audio attrs) — fine
  in practice.

---

## `telemirror/mixins.py` + `telemirror/misc/*` — closed 2026-08-30

`mixins.py`, `misc/urlmatcher.py`, `misc/message_groups.py`, `misc/links.py`,
`misc/log_setup.py`, `misc/lrucache.py`. Full read ×2. Tests: 145 green,
`pyflakes` + `ruff` clean. No code change — no P1/P2 found.

### Invariants
- `update_entities_params`: 5 branches recompute `offset`/`length` on a substring
  replace `[start,end) → diff`; the branches cover every relative position
  (after / enclosing / partial head overlap / partial tail overlap / inside). The
  boundaries `offset==start`, `offset==end`, `offset+length==end` are handled
  correctly.
- `copy_message`: `message`, `entities`, `media` are deep-copied (immutability for
  filters); other fields are shallow (filters don't touch them).
- `iter_message_groups`: non-`Message` items (service messages, `None`) are
  skipped; an album is a maximal consecutive run of one `grouped_id`; a
  single-item album → a `list` of 1.
- `UrlMatcher.match`: blacklist is an exact host or host+path match; whitelist is
  prefix-based (with a `/` or `?` boundary); an empty blacklist means "match
  everything".
- `UrlMatcher.search`: spans in text order (`finditer`), filtered by `match()`.
- `setup_stdout_logger`: the level is set on every call, the handler is added
  once, `propagate=False`.
- `private_message_link`: `utils.resolve_id` → raw peer id in `t.me/c/<peer>/<id>`.

### Regression tests for past bugs
- `update_entities_params` boundaries and "silent message loss" (passes 1/5) —
  `tests/test_update_entities_params.py`.
- `MessageLink.message_link` (pass 4) — `tests/test_mixins.py`.
- `LRUCache.get` recency, eviction (pass 3) — `tests/test_lrucache.py`.
- `UrlMatcher` TLD `{2,24}`, whitelist prefix boundary (pass 5) —
  `tests/test_urlmatcher.py`.
- `iter_message_groups` — `tests/test_message_groups.py`.
- `setup_stdout_logger` idempotency — `tests/test_log_setup.py`.

### Deferred (P3, non-blocking)
- `UrlMessageFilter` with an empty blacklist ("strip all URLs"): the greedy
  `SEARCH_URL_RE` also redacts `file.ext`-style tokens in the text. Inherent to
  the "strip all" mode, documented.
- `copy_message` won't carry new `Message` fields if Telethon adds them (fixed
  attribute list).
- `links.py` has no dedicated test — 1 line, covered indirectly via `test_mixins`.

---

## `telemirror/watermark/processor.py` — closed 2026-08-30

Full read ×2. Tests: 145 green, `pyflakes` + `ruff` clean. No code change — no
P1/P2 found.

### Invariants
- The whole module is best-effort: any failure (no template, no torch/LaMa,
  ffmpeg returned non-zero, no readable frame) → `return None`/`False`, and the
  caller `WatermarkRemovalFilter` sends the original. No message loss.
- `WatermarkConfig.__post_init__` coerces YAML strings to float/int.
- `_load_stamp` / `_load_template` — a process-global cache keyed by path; callers
  only read / `.resize()` (a new object), the cached one is not mutated.
- `_get_lama` — a lazy singleton with a double-checked `threading.Lock`.
- ffmpeg calls: `timeout=300`, `check=False`, stderr logged on a non-zero code.
- CPU-bound work runs in `loop.run_in_executor(None, ...)`.

### Regression tests for past bugs
- `WatermarkConfig` string→number (pass 5) — `tests/test_watermark_config.py`.
- Oversize-video guard — `tests/test_watermark_size_guard.py`.
- Detection accuracy — the manual `tests/watermark/benchmark_detection.py`
  (not pytest).

### Deferred (P3, non-blocking)
- `_template_cache` / `_stamp_cache` have no lock (unlike `_lama`): a race between
  two executor threads causes a redundant recompute, not corruption (idempotent,
  GIL).
- `remove_watermark_from_video`: bbox arithmetic right at the frame edge can
  produce `w`/`h` ≤ 0 → ffmpeg errors out → `False` (no crash).
- The cv2/ffmpeg paths are not pytest-covered (need binaries + image fixtures;
  inpainting needs a VPS) — reviewed by reading.

---

## `main.py` + `login.py` — closed 2026-08-30

Full read ×2. Tests: 145 green, `pyflakes` + `ruff` clean. No code change — no
P1/P2 found. Entry points have no tests (by nature).

### Invariants
- `main.run_telemirror`: `try/finally` around `telemirror.run()` guarantees
  `database.close()`.
- `USE_MEMORY_DB` is always a real bool (`cast=bool`), so `is False` is correct.
- uvloop on non-Windows; on Windows + Postgres, `WindowsSelectorEventLoopPolicy`.
- `login.py` is one-shot: interactive login via `with TelegramClient(...)`, prints
  `client.session.save()`.

### Deferred (P3, non-blocking)
- `login.py` does `from config import ...`, which executes all of `config.py`,
  and that requires `SESSION_STRING` (no default) plus a valid `CHAT_MAPPING`/YAML
  — i.e. to generate a session you already need a filled `.env` with a
  placeholder `SESSION_STRING`. A pre-existing papercut; workaround is a temporary
  value.
- `main.py`: `serve_health_endpoint()` and `await PostgresDatabase(...)` run
  before the `try/finally`; on a DB failure the health site stays up (the process
  crashes anyway). `runner.cleanup()` is never called (lives for the process).

---

## `skylon_set/*` — closed 2026-08-30

`_common.py`, `setup_mirrors.py`, `clear_channels.py`, `set_anonymous.py`,
`rename_emoji.py`. Full read ×2. Tests: 149 green, `pyflakes` + `ruff` clean. No
code change — no P1/P2 found. Operator scripts, not runtime.

### Invariants
- `safe_call`: `ChannelPrivateError` + `skip_errors` → `None`; FloodWait is always
  waited out (`e.seconds`); `ConnectionError`/`OSError` retried up to
  `max_retries=20`, then re-raised (a dead session doesn't hang forever).
- Every destructive op (`DeleteChannelRequest`, `DeleteHistoryRequest`, bulk
  `EditTitleRequest`, message deletion) is behind a `y/N` prompt or `--dry-run`.
- `clear_channels`: `DeleteHistory` only for channels without topic scoping
  (`channels_for_full_clear`); topic-scoped ones are cleared per-topic via
  `purge`. Then `past_mode_checkpoint` and `binding_id` are reset for the cleared
  targets.
- `setup_mirrors.write_directions`: overwrites only the `directions` key, keeps
  the other config keys, makes a `.bak`.
- `setup_mirrors.find_recipient`: exact title match first, then fuzzy by
  `name_key` (brand + emoji stripped).
- Lambdas in loops everywhere capture variables via default arguments.

### Regression tests for past bugs
- `safe_call` retry exhaustion (pass 5) — `tests/test_safe_call.py`.
- `normalize_title` skip-instead-of-mangle (pass 5) — `tests/test_rename_emoji.py`.
- `clear_channels` DeleteHistory scoping — `tests/test_clear_channels.py`.
- `write_directions` key preservation + backup (pass A8) —
  `tests/test_setup_mirrors_config.py`.
- New `tests/test_setup_mirrors_helpers.py`: `has_de_sklad` / `to_archonum` /
  `name_key` / `find_recipient` (fuzzy matching gates the destructive ops).

### Deferred (P3, non-blocking)
- The scripts' `from config import ...` requires a valid `.env` (see `login.py`
  above).
- Hand-editing the config can cause a `KeyError` in `step_verify` (`d["to"][0]`) —
  fail-fast, acceptable.
- `full_id` builds `-100{id}` as a string instead of `utils.get_peer_id` —
  consistent throughout the script, good enough for its purpose.
- `set_anonymous.main` / `rename_emoji.main` have no `try/finally` around
  `disconnect()` — on an unhandled exception the connection isn't closed (the
  process exits anyway).

---

# Pass 7 summary

All runtime and operator code is closed against the fixed checklist. Found and
fixed 3 P2 defects (all: silent message loss on an edge path):
`mirroring` `MediaCaptionTooLongError` split path, `ForwardFormatFilter` without
`{message_text}`, `RestrictSavingContentBypassFilter` swallowing a FloodWait.
Tests: 122 → 149.

**Stop rule in effect**: the whole-project sweep is no longer run. Work on a
closed module is point-targeted only, for a specific reason, adding a
justification section here. Deferred P3 items are not bugs — they are documented
edge-case trade-offs; touch them only on an explicit request.

---

# Pass 9 — prophylactic whole-project sweep (explicit request)

Full re-read of every runtime and operator module with the checklist narrowed to
**memory leaks / performance holes / dead code**. `pyflakes` + `ruff` clean,
`vulture` shows only false positives (`hints` used in string annotations,
`_handlers` keeps a strong ref, psycopg `row_factory`, the yaml `ignore_aliases`
override, `album._HACK_DELAY`). Tests: 196 → 199.

## Fixed

- **P3 (perf)** `skylon_set/setup_citadel.py`: `_run` traversed each forum's
  topic list twice — `sync_topics` fetched donor + recipient topics, then
  `build_forum_directions` fetched the same two again. On the 2 `FORUM_PAIRS`
  that is 4 redundant paginated `GetForumTopicsRequest` sequences (each with a
  0.3 s per-page sleep and FloodWait exposure on a large forum). Now `_run`
  fetches the donor list once and the recipient list twice (before and after
  topic creation — `sync_topics` may add topics), and passes the lists into
  `sync_topics` (no longer takes `donor_id`) and `build_forum_directions` (now a
  pure sync function taking `donor_id, recip_id, donor_topics, recip_topics`).
  Test: `tests/test_setup_citadel.py` (per-peer call count + `directions`
  title-pairing).
- **P3 (memory)** `past_mode.py` `_edit_links_pass`: it fetched every source
  message for a pair into one `src_messages` list before iterating it once —
  for a `full_history` replay `mirrors` can be tens of thousands, so this was a
  needless transient spike of `Message` objects. Now each 100-id batch is
  processed inside the fetch loop; `mirror_map` (needed for lookup) is the only
  full-size structure. A fetch failure now `break`s (keeping batches already
  processed) instead of abandoning the whole direction — the pass is
  idempotent, so partial progress is safe and a re-run finishes the rest.
  Test: `tests/test_past_mode.py::test_edit_links_pass_streams_source_messages_in_batches`.

## Reviewed, no change — acknowledged trade-offs re-affirmed

- `mirroring._sync_broadcast_channel`: `seen: set[int]` holds every message id of
  the broadcast channel for the duration of the startup sync. Documented
  ("only message IDs are held in memory, never the full history"); startup-only,
  released after. Not a leak.
- `mirroring.TelegramLogHandler`: `_counts` / `_timers` are popped in `_send`
  (always fires after `_DEBOUNCE`); `_cooldown_until` is pruned in
  `_prune_cooldowns`; `_tasks` discards on done-callback. Bounded. `__connect_client`
  runs once per process so the handler is attached once.
- LRU capacities (`InMemoryDatabase` 100, `ReuploadCache` 16 / 600 s,
  `LRUCache` free-factor trim) — sized on purpose, per REVIEW passes 3/5/8.
- `watermark/processor.py` `_template_cache` / `_stamp_cache`: unbounded by
  *path* (1–2 paths in practice) and lock-free (a race recomputes, never
  corrupts — idempotent under the GIL). Already in "Deferred".
- `telemirror/_patch/sending.py`, `_patch/album.py`: deliberate near-verbatim
  copies of Telethon functions for easy upstream merges — editing them defeats
  the purpose.
- `mixins.copy_message` re-imports `deepcopy` per call (a `sys.modules` dict hit,
  effectively free) and deep-copies `media`/`entities` by design (filter
  immutability). No change.
- Operator scripts (`setup_mirrors.py`, `clear_channels.py`, `set_anonymous.py`,
  `rename_emoji.py`): each step re-runs `get_dialogs()` — intentional, the view
  changes between steps (pairs created, dupes deleted). `clear_channels.purge`
  iterates full channel history client-side for topic-scoped targets — inherent
  to per-topic filtering, rare destructive op behind a `y/N` prompt.
- P3 items from passes 1–8 remain documented trade-offs, not touched.

---

# Pass 10 — whole-project sweep + `skylon_set/` refactor (explicit request)

Re-run of the pass-9 checklist (memory leaks / perf holes / dead code) plus, on
explicit request, a systemic refactor of the operator scripts (which pass 9 only
read, not optimised). Runtime memory/perf conclusions from pass 9 re-confirmed by
an independent full read — no leaks, hot path clean. Tests: 199 → 206.
`pyflakes` + `ruff` clean; `vulture` unchanged (only the `_patch/sending.py`
`hints` false positive).

## Fixed — runtime (`telemirror/`)

- **P3 (perf)** `mirroring.EventProcessor._rewrite_links` / `_try_rewrite_tg_link`:
  the per-link resolution (`database.get_messages` — a DB round-trip — plus, for
  public links, `client.get_entity` — a network round-trip) ran once per fan-out
  target even though the result depends only on `(url, fallback_link_url)`. A
  broadcast message with an internal link cost N DB queries + N entity fetches for
  N targets. Now `new_message` / `new_album` build a per-event `link_cache: dict`
  and thread it through; the string/entity mutation stays per-copy, only the
  resolution is memoised. Other callers (`past_mode._edit_links_pass`,
  `_sync_broadcast_channel`) pass no cache → identical behaviour. Test:
  `tests/test_link_rewrite_cache.py::test_link_resolution_is_cached_across_fanout`.
- **P3 (perf)** `mirroring.EventProcessor._resolve_username_to_channel_id`: added
  an instance-level `LRUCache[str, int](capacity=256)` so a `t.me/<username>` link
  reused across messages is resolved once. Only successful resolutions are cached
  (a miss may become resolvable later); capacity-bounded, staleness on username
  reassignment matches Telethon's own entity cache. Test:
  `..._username_resolution_is_cached_on_the_processor`.
- **cleanup** `EventProcessor.GENERAL_TOPIC_ID` + the branchy topic-of-message
  logic in `_matches_from_topic` were duplicated in
  `skylon_set/clear_channels.py`. Extracted to `telemirror/misc/topics.py`
  (`topic_id_of`, `GENERAL_TOPIC_ID`); `_matches_from_topic` is now a two-liner.
  All `tests/test_matches_from_topic.py` cases green (behaviour identical).

## Added — `telemirror/storage.py` (Database protocol extension, approved)

- `delete_past_mode_checkpoint(source, target)` and
  `delete_bindings_for_mirror(mirror_channel)` on `Database` /
  `InMemoryDatabase` / `PostgresDatabase`. Lets `clear_channels` reset DB state
  through the pooled `PostgresDatabase` instead of opening two raw
  `psycopg.AsyncConnection`s with per-row `DELETE` loops. Tests in
  `tests/test_storage.py`.

## Fixed — `skylon_set/`

- **perf** `clear_channels.purge`: took a full `iter_messages` pass over the whole
  channel history **per configured topic** (K passes for K topics), filtering
  client-side. Now one pass routes every message to the right topic set. Also:
  channels that get `DeleteHistory` (no topic scoping) are no longer streamed +
  deleted message-by-message first — `DeleteHistory` alone wipes them. The inner
  hand-rolled `FloodWait` loop is replaced by `safe_call`. Message set deleted is
  unchanged (the total-count log for full-clear channels no longer includes the
  now-skipped streaming pass). Test:
  `tests/test_clear_channels.py::test_purge_sweeps_history_once_and_routes_by_topic`.
- **latent bug** `setup_mirrors.py` had three separate `GetForumTopicsRequest`
  call sites with `limit=100` and **no pagination** — a forum with >100 topics was
  silently truncated. Unified onto `skylon_set/_common.fetch_all_topics` (paginated,
  ported from `setup_citadel.fetch_topics`, which was the one correct copy).
  `setup_citadel` now imports it too. `step_create_pairs`' own
  `GetForumTopicsRequest` (wrapped in `safe_call`, one-shot channel setup) is left
  as-is — converting it would drop the retry wrapper. Test:
  `tests/test_fetch_all_topics.py`.
- **robustness** `rename_emoji.py` / `set_anonymous.py` disconnected the client
  only on the happy paths — an exception (e.g. `safe_call` exhausting retries,
  `input()` interrupted) leaked the connection. Both `main()` bodies are now
  wrapped in `try/…/finally: disconnect()`. (Was pass-7 deferred P3.)
- **dedup** New `skylon_set/_common.open_client` async context manager (connect +
  `get_me` auth check + "logged in as" line + guaranteed disconnect + the
  "stop main.py" warning), adopted by `clear_channels`, `setup_citadel`,
  `sync_pins`. `_common.configure_logging` (a no-op wrapper over
  `setup_stdout_logger`) removed; the three callers use `setup_stdout_logger`
  directly.

## Reviewed, no change — acknowledged trade-offs

- `binding_id` has no `UNIQUE` constraint → a re-sync / double event can write
  duplicate rows that then fan out into duplicate edits/deletes. Correctness, not
  perf; adding the constraint to a live table with possible existing dupes is a
  risky migration and a behaviour change. Left for a dedicated decision.
- `FilterAction.FORCE_SEND` is half-wired (propagated by `CompositeMessageFilter`
  / `_process_album`, but no filter returns it and `mirroring.py` treats it like a
  normal send). Dead branch, but `FilterAction` is exported — not removed.
- `Database.insert` / `Database.delete_messages` (single-row) are unused outside
  tests but part of the public `Database` protocol — kept.
- `setup_mirrors` running `get_dialogs()` once per full-cycle step — re-confirmed
  intentional (pass 9): the dialog view legitimately changes between steps.
- `sync_pins.sync_pair` materialises a channel pair's full `binding_id` history in
  memory — released between pairs, inherent to the pin-diff; not touched.
- `past_mode.py` still open-codes its own client bootstrap (own
  `connection_retries` / `retry_delay` strategy) — deliberately not folded into
  `open_client`.

---

# «⚜️ Цитадель» batch 2 + `setup_citadel.py` removed

Batch 2 (donors «🏴‍☠️ D{È,É,E} SKLAD» → recipients «⚜️ Цитадель», 12 live + 23
course) added via `setup_mirrors.py`, which was retargeted from the old brand name
«Archonum» to «⚜️ Цитадель». Live directions merge-appended to
`.configs/mirror.config.yml` (text append, comments preserved); course-only
directions written to `.configs/citadel_courses.config.yml` (no `broadcast_channel`,
consumed only by `YAML_CONFIG_ENV=… python past_mode.py`).

`skylon_set/setup_citadel.py` + `tests/test_setup_citadel.py` deleted: it was a
one-shot for batch 1 (id-pair driven, print-only), its output is permanent in the
config, it was never re-run, and `setup_mirrors.py` is now the sole «⚜️ Цитадель»
generator. `skylon_set/rename_emoji.py` + `tests/test_rename_emoji.py` deleted
too: it was the Archonum-era 🗝→⚜️ title normaliser, wholly coupled to the
«Archonum» keyword (which the owner has fully retired) and a no-op on «⚜️ Цитадель»
titles — `step_final_verify` covers recipient-title drift for the current batch.
Earlier passes' references to both files are historical.

Fixed along the way: `_common.fetch_all_topics` dropped `ForumTopicDeleted`
tombstones (crashed callers on `.title`) and now pages from the last non-deleted
topic; `setup_mirrors._sync_forum_topics` makes topic creation idempotent after a
FloodWait abort; `classify_donor` excludes already-created «⚜️ Цитадель» recipients
so they can't be re-picked as donors; the duplicate detector skips an empty
`name_key` (bare-«Цитадель» titles no longer collapse into one false group).

---

# Pass 11 — full restart (production-readiness overhaul)

This is a ground-up restart, not a continuation: every module gets a full
independent re-read regardless of any earlier "closed" status. Prior entries
above remain as historical record and a source of previously-found invariants
to re-verify, not as a reason to shorten this pass. Batches are audited and
fixed in the order listed below, each with its own gate run.

## Batch A — `telemirror/storage.py`, `config.py`, `telemirror/hints.py`

Full read ×2. Tests: 271 green (270 + 1 new), `pyflakes` + `ruff` clean. No
P1/P2 found.

### Correction to a previously recorded invariant

The `telemirror/storage.py` (pass 7) "Deferred" section states: *"`insert` via
`setdefault` on an existing key does not `move_to_end` (a second mirror of the
same message doesn't bump recency)."* Verified empirically (Python 3.12,
`collections.OrderedDict` C implementation) that this is no longer accurate,
if it ever was: `OrderedDict.setdefault` resolves an existing key through the
subclass's overridden `__getitem__`, so it *does* bump recency, and resolves a
missing key through the overridden `__setitem__`, so eviction still fires on
capacity overflow via `setdefault`-based inserts too. Both paths were traced
directly (instrumented `__getitem__`/`__setitem__`) and pinned down with a new
regression test, `test_setdefault_on_existing_key_refreshes_recency` in
`tests/test_lrucache.py`, alongside the existing `test_get_refreshes_recency`.
No code change — the actual behavior was already correct; only the record was
wrong. The rest of pass 7/9/10's `storage.py`/`config.py` invariants and
deferred P3 items were independently re-verified and still hold as documented
(YAML-vs-env fail-fast priority, `_channel_id` blank/zero handling,
`PastModeConfig` single-strategy validation, `build_dsn` percent-encoding,
broadcast-direction dedup by `(target, to_topic_id)`, `PostgresDatabase`
reviewed by inspection only).

### Deferred (P3, non-blocking, re-affirmed from pass 7)

- Empty YAML `directions:`/file → an opaque `TypeError` instead of a clear
  startup error.
- `build_filters`: a YAML filter dict with >1 key silently takes only the
  first.
- Synthetic broadcast directions ignore the global YAML `filters:`/`mode:` by
  design (always `EmptyMessageFilter` + copy) — non-obvious but intentional.
- Several `config.py` module-level annotations (e.g. `DB_URL: str = ...
  default=None`) are typed as non-Optional despite a `None` default —
  cosmetic, no runtime effect.

---

## Batch B — `telemirror/mirroring.py`, `telemirror/mixins.py`, `telemirror/messagefilters/*`, `telemirror/watermark/processor.py`

Full read ×2. Tests: 273 green (271 + 2 new), `pyflakes` + `ruff` clean.

### Fixed in this pass

- **P2** `Mirroring._Mirroring__connect_client`: `EventHandlers` was constructed
  *after* `await self._sync_broadcast_channel(...)`. Read Telethon 1.44's actual
  dispatch code (`client/updates.py::_dispatch_update`) to settle what pass 8
  left as "not re-verified against Telethon's actual update-buffering behaviour
  — raise to P2 if a normal path is shown to drop updates": `_dispatch_update`
  iterates `self._event_builders` live, at the moment an update is dispatched,
  not a snapshot from when it was received — a handler added later never sees
  updates dispatched before it existed, and Telethon does not replay them. On a
  broadcast channel with real history (or just a slow first run), any live
  update on *any* mirrored source channel arriving during that window was
  silently and permanently lost — the same "silent message loss" class as
  pass 7/8's P2 fixes. Now `EventHandlers` is constructed first. Trade-off this
  accepts: a broadcast-channel post arriving exactly during the sync can be both
  dispatched live and picked up by the sync's own history walk → a visible
  duplicate, not a silent loss. Test:
  `tests/test_broadcast_sync.py::test_handlers_registered_before_broadcast_sync`
  (asserts call order via stubs, since exercising Telethon's live dispatch race
  itself isn't practical to simulate in a unit test).
- **P2** `telemirror/watermark/processor.py::remove_watermark_from_video`: the
  ffmpeg `delogo` re-encode used a flat `timeout=300`, while the comparable (or
  cheaper — `stamp_watermark_on_video` has no `-c:v copy` either, same libx264
  path) stamp step uses `_ffmpeg_timeout(duration)` (300s floor, scales up).
  `deploy/README.md` documents 6-13 minute real-world stamp times on the
  production single-vCPU host — a video that clears the `stamp_video_max_duration_s`
  gate (default 300s) could legitimately take longer than 300s to delogo-encode
  and hit a false `TimeoutExpired`, silently discarding a would-have-succeeded
  removal (caught by `WatermarkRemovalFilter`'s broad `except Exception`, so no
  message loss — the source is mirrored unwatermarked instead — but the feature
  quietly doesn't work for exactly the videos it's supposed to handle). Now uses
  the same `_ffmpeg_timeout(duration)`, with `duration` computed the same way
  `stamp_watermark_on_video` does (`frame_count / fps`). Test:
  `tests/test_watermark_video_encode.py::test_remove_watermark_timeout_scales_with_duration`.

### Correction to a previously recorded item

Pass 8's watermark/processor.py review did not flag the `remove_watermark_from_video`
timeout inconsistency (it predates `_ffmpeg_timeout`, added later alongside
`stamp_watermark_on_video`'s dynamic budget, without updating the sibling
function) — noted here since it's a real behavioral gap, not a re-affirmation.

### Re-verified, no change

- `telemirror/watermark/processor.py`'s missing bundled `reference_watermark.png`
  (`_DEFAULT_TEMPLATE`) is intentional and already handled: `_load_template`
  explicitly special-cases the default path, logs a warning, and disables
  detection (stamping still runs) — matches the documented "whole module is
  best-effort" invariant. Not a defect.
- All other pass-7/8 invariants for `mirroring.py` (flood/media-error
  propagation contract, broadcast-sync idempotency, `edit_message`/`delete_message`
  semantics) and pass-7's media-filters/messagefilters invariants re-read and
  still hold as documented.

### Deferred (P3, non-blocking, re-affirmed from pass 7/8)

- All P3 items listed under the pass-7/8 `mirroring.py`, messagefilters, and
  watermark/processor.py sections above still apply and were independently
  re-checked against the current code.

---

## Batch C — `past_mode.py`

Full read ×2. Tests: 273 green (unchanged), `pyflakes` + `ruff` clean. No code
change — no P1/P2 found.

The pass-7 `past_mode.py` section was closed 2026-08-30, before the most recent
commit on this file (`0677f37`, 2026-09-10: topic-safe dedup in `mirroring.py` +
skip-stuck-message in `_replay_with_retry`) — so the closed snapshot predates
current behavior. Independently re-verified the current code, focusing on what
that commit changed:

- `_replay_with_retry`'s stuck-message skip: traced the
  `media_failure_checkpoint` sentinel/reset logic by hand against
  `_MEDIA_RETRY_LIMIT` — a fresh checkpoint value (progress since the last
  stall) resets the failure count and re-arms a full retry budget for the new
  stuck point; skipping past a message sets the checkpoint to `e.message_id`
  and correctly seeds `media_failure_checkpoint` so the very next message's
  first failure isn't miscounted as a continuation of the skipped one. Matches
  `tests/test_past_mode.py::test_replay_with_retry_skips_stuck_message_after_limit`.
  No `message_id` on the error → re-raise (can't skip what can't be named) —
  matches `..._reraises_when_stuck_message_unknown`.
  `MediaDownloadError` is excluded from `EventProcessor.__handle_exceptions`'s
  broad catch (confirmed in Batch B) and propagates uncaught through
  `process_single`/`process_album`'s plain `async for` loop, reaching this
  retry wrapper — no swallow point in between.
- Multi-topic-per-pair replay: `_replay_direction` builds one `EventProcessor`
  per (source, target) pair with *all* the pair's topic `cfgs`, so
  `_matches_from_topic` alone decides routing per message — one history pass,
  one checkpoint, no per-topic re-fetch. Matches
  `..._replay_multi_topic_single_pass`.
- `_integrity_check`'s `get_messages_for_channel_pair` is intentionally
  topic-blind (`binding_id` has no topic column — confirmed in Batch A) so
  `max_mirrored` correctly spans every topic of the pair, consistent with the
  single-checkpoint-per-pair design above.

### Re-verified, no change

- Checkpoint-advances-only-after-send, `min_id` exclusivity, flood propagation
  not advancing the checkpoint, `_integrity_check` rollback, `last_n`
  buffer-vs-stream selection, service-message drop, and `_edit_links_pass`'s
  best-effort second pass — all re-read against the current code and still
  hold as pass-7 documented them.

### Deferred (P3, non-blocking, re-affirmed from pass 7)

- `_run`: `await client.connect()` has no time bound (unlike
  `Mirroring.__connect_client`) — an operator script, the operator will see it
  hang.
- `_run`: `database` and `client.connect()`/`get_me()` run before the
  `try/finally` — on their failure, cleanup is skipped (the process exits
  anyway).
- `_edit_links_pass`: `except Exception` on `client.edit_message` also
  swallows a FloodWait > 300s — edits are simply skipped (best-effort pass).

---

## Batch D — `main.py`, `login.py`, `telemirror/misc/*`, `telemirror/alert.py`, `telemirror/health.py`

Full read ×2. Tests: 274 green (273 + 1 new), `pyflakes` + `ruff` clean.

`telemirror/alert.py` and `telemirror/health.py` had **no prior REVIEW.md
section at all** — grepped the whole file for both names and found zero hits,
despite both shipping in the same "24/7 hardening" work that pass 7-10 covered
for everything else. Read them with the same scrutiny a from-scratch module
gets, cross-checked directly against the actual `deploy/systemd/*.service`
files (not just `deploy/README.md`'s prose) since their whole job is reacting
correctly to those units' real state transitions.

### Fixed in this pass

- **P2** `telemirror/health.py::check`: the "stuck outside `active` for two
  checks" alert fired on `ActiveState == "inactive"` too. Cross-checked against
  `deploy/systemd/telemirror.service` and `telemirror-past-courses.service`:
  the latter's `Conflicts=telemirror.service` + former's `Restart=always` mean
  starting a course backfill *cleanly stops* the live mirror
  (`ActiveState=inactive`) for the whole backfill — which `citadel_courses.config.yml`'s
  ~85 `full_history` directions can keep running for hours — and
  `OnSuccess=telemirror.service` on the backfill unit restarts it after.
  `telemirror-health.timer` runs every ~10 min, so every single backfill run
  (a normal, documented, operator-triggered workflow, not a failure) would have
  paged `TECH_CHANNEL` repeatedly for its whole duration — exactly the kind of
  noise that trains an operator to ignore real alerts. `Restart=always` also
  means a unit that's actually crash-looping essentially never settles into a
  stable `inactive` on its own (it cycles through `activating`/`failed`
  instead, both already covered by the flap-count and `failed`-state checks),
  so excluding `inactive` doesn't weaken real-failure detection. Test:
  `tests/test_health.py::test_deliberate_stop_for_course_backfill_does_not_alert`.

### Re-verified, no change

- `main.py`/`login.py`: matches pass-7 invariants (uvloop selection,
  `try/finally` around `telemirror.run()`, `USE_MEMORY_DB` always a real bool).
- `telemirror/misc/*` (`links.py`, `log_setup.py`, `message_groups.py`,
  `urlmatcher.py`, `lrucache.py`): matches pass-7 invariants, re-read in full.
  `topics.py` and `sdnotify.py` (added after pass 7) read for the first time as
  part of this restart — `topic_id_of`'s General-topic/reply fallback and
  `sdnotify`'s no-op-without-`NOTIFY_SOCKET` contract match their docstrings and
  existing tests (`test_matches_from_topic.py`, `test_sdnotify.py`).
- `telemirror/alert.py`: `send_alert` never raises (broad `except Exception` in
  both `send_alert` and `journal_tail`); `_connect_and_send`'s `finally:
  client.disconnect()` runs even when `is_user_authorized()` is False or the
  connect/send `wait_for` times out.

### Deferred (P3, non-blocking)

- `telemirror/alert.py`: `TECH_CHANNEL` is read raw via `decouple`
  (`_env("TECH_CHANNEL", default=None)`), not through `config.py`'s
  `_channel_id` (which treats `""`/`"0"` as "unset" everywhere else in the
  project). Setting `TECH_CHANNEL=0` here would not print the "TECH_CHANNEL
  not set — skipping" line and would instead attempt `client.send_message(0,
  ...)`, failing and being swallowed by `send_alert`'s broad `except`. Same
  outcome either way (no alert sent) — deliberately setting a channel id to
  the literal zero-string is not a realistic config, and `alert.py`'s
  docstring explains it avoids `config.py` on purpose (must work on a broken
  env).
- `telemirror/alert.py::journal_tail`: a non-zero `journalctl` exit with empty
  stdout (e.g. permission denied) is reported as "(journal is empty)" — the
  message says "empty" when it may mean "inaccessible". Cosmetic; `check=False`
  was a deliberate choice not to raise here.
- (Phase 5) `telemirror/alert.py`, `telemirror/health.py`: all remaining
  Russian strings translated to English (log/print text, error messages);
  `tests/test_health.py`'s two assertions on the alert text updated to match.
  No behavior change — only the emitted text.
- Pre-existing `main.py`/`login.py` P3s (health site/DB before `try/finally`,
  `login.py` needs a fully-valid `.env` including a placeholder
  `SESSION_STRING`) still apply.

---

## Batch E — `telemirror/_patch/*` (vendored/patched Telethon)

Full read ×2. Tests: 274 green (unchanged), `pyflakes` + `ruff` clean. No code
change — no P1/P2 found.

Different judgment call here than the rest of the project: a "defect" in a
vendored patch means an unintended deviation from the upstream function it
forks, not a correctness bug in isolation. Pass 9 recorded these as "deliberate
near-verbatim copies... editing them defeats the purpose" but that was a
by-eye read, not a verified diff. This pass extracted the actual matching
`send_message`/`send_file`/`_send_album`/`forward_messages` implementations
from the installed Telethon 1.44.0 (`.venv/lib/.../telethon/client/{messages,uploads}.py`)
and diffed them structurally against `_patch/sending.py` (normalizing
`self`→`client`, quote style, and Black-style wrapping so only real content
differences remain).

### Re-verified, no change

- The diff confirms the *only* functional deviations across all four functions
  are the `reply_to_topic_id`/`top_msg_id` additions this patch exists for —
  threaded consistently into every `InputReplyToMessage`/`ForwardMessagesRequest`
  construction, with no upstream call site missed.
- `_patch/album.py`'s `set_album_event_timeout` still targets a real, present
  attribute: confirmed `telethon.events.album._HACK_DELAY` exists in the
  installed version (module-level default `0.5`, read by `AlbumHack` at
  instantiation) — the monkeypatch isn't silently dead against this Telethon
  version.

### Deferred (P3, non-blocking)

- `_patch/sending.py::send_file` dropped upstream's `mime_type` parameter (and
  its forwarding into `client._file_to_media(..., mime_type=...)`) — the one
  incidental (not topic-related) gap the diff surfaced. Confirmed harmless
  today: nothing in this project calls `send_file`/`send_message` with a
  `mime_type` argument (checked all call sites in `mirroring.py` and the
  `messagefilters/` package in Batch B), and `_file_to_media`'s own default is
  `mime_type=None`, identical to never passing it. Not adding it back
  speculatively — record it here so a future filter that needs to pin a MIME
  type doesn't waste time discovering this fork silently drops it.

---

## Batch F — `skylon_set/*` (`_common.py`, `anonymize_groups.py`, `clear_channels.py`, `restrict_saving.py`, `sync_pins.py`, `setup_mirrors.py`)

Full read ×2 (dependency order: `_common.py` first, `setup_mirrors.py` last as
the largest). Tests: 275 green (274 + 1 new), `pyflakes` + `ruff` clean.

### Fixed in this pass

- **P2** `clear_channels.py::_run`: DB state (`past_mode_checkpoint` +
  `binding_id`) was reset via `_reset_db_state(targets, ...)` using the *full*
  target set collected from `CHAT_MAPPING`, not the subset that was actually
  cleared. Both `purge()` and `DeleteHistoryRequest` failures are caught,
  logged, and the loop moves on to the next channel (correct — one bad channel
  shouldn't abort the whole run) — but the channel stayed in `targets` and so
  still got its checkpoint deleted and `binding_id` rows wiped at the end. A
  channel whose purge failed (network blip, exhausted FloodWait retries, no
  admin rights) would then look "clean" to a later `past_mode.py`/live run,
  which would re-mirror its entire history into a channel that still holds the
  old, un-deleted messages — duplicating content, the opposite of what
  `clear_channels.py` exists to do. Now a `cleared` dict is built incrementally
  from only the channels whose `purge()`/`DeleteHistoryRequest` call actually
  returned, and only that subset is passed to `_reset_db_state`. Test:
  `tests/test_clear_channels.py::test_run_only_resets_db_state_for_successfully_cleared_channels`.

### Re-verified, no change

- `_common.safe_call`/`open_client`/`fetch_all_topics`: matches pass-10
  invariants (FloodWait always waited out, transport errors retried up to
  `max_retries`, forum-topic pagination past 100 with tombstone-safe cursor).
- `anonymize_groups.py`, `restrict_saving.py`, `sync_pins.py`: re-read in full,
  matches existing test coverage (`test_anonymize_groups.py`,
  `test_restrict_saving.py`, `test_sync_pins_*.py`) — no new findings.
- `setup_mirrors.py` (851 lines, the largest and most business/brand-specific
  script): re-read in full including `write_directions`/`_append_directions_text`'s
  merge-dedup, `step_final_verify`'s config-vs-reality reconciliation, and the
  donor/recipient classification helpers — matches pass-9/10's documented
  invariants and existing test coverage
  (`test_setup_mirrors_config.py`, `test_setup_mirrors_helpers.py`,
  `test_setup_mirrors_sync_topics.py`, `test_setup_mirrors_forum_api.py`).

### Deferred (P3, non-blocking)

- `_common.fetch_all_topics`: if an *entire* 100-topic page were all
  `ForumTopicDeleted` tombstones, the cursor falls back to `r.topics[-1]` (a
  tombstone), whose missing `top_message`/`date` reset `offset_id`/`offset_date`
  to 0 — exactly the "zero cursor breaks pagination" failure the tombstone-aware
  cursor was added to avoid (pass 10), just for this specific all-deleted-page
  case. Not fixed: the actual behavior of `GetForumTopicsRequest` with a
  zeroed offset_id/date alongside a real offset_topic isn't documented, so a
  guess-based fix risks trading a rare hang for a rare wrong-page skip. 100
  consecutive deleted topics with no live one in between is an extreme edge
  even for a forum with heavy topic churn; flagging for awareness rather than
  guessing at Telegram's undocumented semantics.
- `_common.safe_call`: reconnects the client on every `FloodWaitError`, not
  only on the transport errors it's built for — heavier than necessary but
  harmless for an operator script (not perf-sensitive).
- Pre-existing pass-9/10 `skylon_set/*` P3s (config `KeyError` on hand-edit,
  `full_id`'s string-built id, scripts requiring a valid `.env`) still apply.

---

## Batch G — `deploy/*` (bootstrap.sh, setup-swap.sh, systemd units, cron, README)

Not covered by `pyflakes`/`ruff`/`pytest`. Manual verification performed and
recorded per-item below, per the plan's requirement for this batch.

**Verified**:
- `bash -n deploy/bootstrap.sh` and `bash -n deploy/setup-swap.sh` — both clean
  (syntax only; no `shellcheck` available in this environment, so unused-var/
  quoting-style classes of issues were checked by manual reading instead, not
  tooling).
- `systemd-analyze verify --recursive-errors=no` (systemd 255, meets the
  documented `≥254` requirement) against all 5 `.service` and 2 `.timer` files
  in `deploy/systemd/` — zero errors/warnings from any unit, including the one
  this pass edited.
- `deploy/cron.d/telemirror-tmp`: manually confirmed the 5 time fields +
  `root` user field match `/etc/cron.d/*` syntax (not a user crontab, which
  has no user field), and that the `find` invocation's flags
  (`-maxdepth 1 -name 'tmp*.mp4' -mmin +180 -delete`) are individually valid.
  No sandbox execution attempted (destructive-by-design, targets `/tmp`).
- Re-read `deploy/README.md` in full directly (not from a prior summary) and
  cross-checked its failure-mode table and unit inventory against the actual
  current `deploy/systemd/*` files line by line — accurate except for the gap
  fixed below, now updated.

### Fixed in this pass

- **P2** `deploy/systemd/telemirror-past-courses.service`: had no `OnFailure=`,
  unlike `telemirror.service`. Traced the failure path by hand: this unit's
  `Conflicts=telemirror.service` stops the live mirror the moment a course
  backfill starts; `OnSuccess=telemirror.service` brings it back only on a
  *successful* finish. If `past_mode.py` instead fails outright — `Restart=
  on-failure`/`RestartSec=60` exhausts `StartLimitBurst=3` within
  `StartLimitIntervalSec=600` and the unit settles into `failed` — nothing
  brings the live mirror back up, and nothing tells anyone: `OnSuccess=` never
  fires on failure, and this pass's own Batch D fix to `telemirror-health.py`
  (excluding `ActiveState=inactive` from the "stuck" alert, precisely so a
  *normal* backfill doesn't page anyone) means the live mirror can now sit
  silently stopped indefinitely with no alert at all. Added
  `OnFailure=telemirror-alert@%n.service`, the exact mechanism
  `telemirror.service` already uses, so a failed backfill pages `TECH_CHANNEL`
  immediately instead of relying on an operator to notice the mirror is down.
  `deploy/README.md`'s course-replay section updated to document this and the
  manual recovery step (`systemctl start telemirror.service`). No automated
  test possible (systemd unit semantics); verified via
  `systemd-analyze verify` and by hand-tracing the `Restart=`/`StartLimit*=`/
  `OnFailure=`/`OnSuccess=` interaction against `telemirror.service`'s already
  battle-tested pattern.
- **P3** `deploy/bootstrap.sh`: step counter printed `1/4` for the first of 5
  steps (steps 2-5 correctly said `.../5`) — a leftover from before a step was
  added. Fixed to `1/5`.

### Deferred (P3, non-blocking)

- A course backfill that hangs indefinitely without ever exiting (neither
  succeeding nor reaching `failed`) would still evade both `OnSuccess=`/
  `OnFailure=` and `telemirror-health.py` (which only watches
  `telemirror.service`, not `telemirror-past-courses.service`). Not fixed: a
  `RuntimeMaxSec=` timeout would misfire on a legitimately slow multi-hour
  `full_history` run, and extending `health.py` to also watch the
  courses unit's state adds real complexity for a failure mode with no
  concrete evidence it occurs (past_mode.py has its own FloodWait/
  MediaDownloadError retry loops that already terminate or propagate). Flagging
  for awareness rather than guessing at a fix.
- `telemirror-alert@.service`'s `TimeoutStartSec=60` is not generously above
  `telemirror/alert.py`'s own worst-case budget (10s journalctl + 20s connect +
  20s send ≈ 50s) once Python/venv startup overhead is added — plausible to
  occasionally hit under load. Low impact (an alert-about-a-failure failing
  doesn't cascade, by design) and no incident evidence; not tuned speculatively.

---

## Phase 3+4 — dead code sweep + SOLID cleanup (whole-tree pass)

### Phase 3 — dead code

Ran `vulture` (min-confidence 0) over `telemirror/`, `skylon_set/`, `main.py`,
`past_mode.py`, `login.py`, `config.py`, plus manual greps for commented-out
code blocks and a full cross-check of every `config.py` env/YAML key against
its consumers. All 9 vulture hits are the same confirmed false positives
independently re-verified during Batches B/E (`_HACK_DELAY` — read by Telethon
internally; `hints` import — used only in string type-annotations vulture
doesn't parse; `file_handle` tuple-unpack — matches upstream Telethon's own
pattern; `.quiz`/`row_factory` — writes that configure behavior, not values
ever read back in this codebase; `self._handlers` — kept alive intentionally,
not read again). No commented-out code found anywhere in the tree. No unused
config keys found — every `config()`-sourced name is consumed somewhere.
**Nothing removed — no real dead code found**, beyond what earlier passes
already deleted (`rename_emoji.py`, `setup_citadel.py`, etc., pre-dating this
restart).

### Phase 4 — SOLID/DRY

Two candidates identified across the batches, both approved by the project
owner before implementation, both verified with a new regression test and a
full green gate:

- **`config.py`**: the YAML and legacy-env branches each parsed a
  `"chat_id"` / `"chat_id#topic_id"` value with the *identical* 5-line
  `if "#" in x: ... else: int(x)` snippet, twice per branch (source and
  target). Extracted to `_parse_chat_topic(value) -> (chat_id, topic_id)`,
  called from both branches; behavior unchanged (verified: bare id, `#`-suffixed
  id, and YAML's already-parsed-int case all produce the same result as
  before). Test: `tests/test_config.py::test_parse_chat_topic_shared_by_yaml_and_env_branches`.
  The YAML-vs-env branches were deliberately **not** unified further: they have
  genuinely different feature sets (YAML supports per-direction filters/mode/
  `past_mode`; env applies one global filter/`past_mode` to every direction),
  both are documented in README as supported configuration methods, and a
  deeper merge would be a speculative rewrite for a code path that only runs
  once at process startup — not "the smallest change that fixes a genuine
  violation."
- **`telemirror/mirroring.py` (`Telemirror.__init__`) + `past_mode.py` (`_run`)**:
  both built an almost-identical `TelegramClient` (same session/API args,
  same `flood_sleep_threshold=300`, same `parse_mode="markdown"`), differing
  only in `connection_retries`/`retry_delay` (the live mirror retries
  indefinitely through an outage — the watchdog decides when to give up;
  `past_mode.py` is a bounded operator run and gives up after ~1 minute).
  Extracted to `telemirror/misc/telegram_client.py::build_telegram_client(...)`,
  keeping the retry policy as caller-supplied parameters so each call site's
  distinct trade-off is preserved exactly, not merged away. `skylon_set/_common.py::make_client`
  was deliberately left alone — different shape (generic `**extra_kwargs`
  passthrough, no baked-in `flood_sleep_threshold`/`parse_mode`, used by five
  different operator scripts with their own override needs) and out of the
  approved scope. Tests: `tests/test_telegram_client_factory.py` (parse mode,
  `flood_sleep_threshold`, and that two callers can independently choose a
  retry policy).

Both refactors: `pyflakes`/`ruff` clean, full suite green (275 → 279: +1
`_parse_chat_topic` test, +3 `build_telegram_client` tests), re-ran `vulture`
afterward with no new findings.

---

## Phase 5 — full English conversion

Translated every remaining Russian string in tracked files: `config.py` (2
error strings, already fixed in Batch A), `telemirror/mirroring.py` (1
comment + `on_private_message`'s TECH_CHANNEL notification text),
`telemirror/alert.py`, `telemirror/health.py`, `past_mode.py` (549 lines,
was ~100% Russian), all of `skylon_set/*` (`_common.py`,
`anonymize_groups.py`, `clear_channels.py`, `restrict_saving.py`,
`sync_pins.py`, `setup_mirrors.py` — 851 lines, the largest and most
business/brand-specific file), all of `deploy/*` (`bootstrap.sh`,
`setup-swap.sh`, `cron.d/telemirror-tmp`, all 5 `.service` + 2 `.timer`
files, `journald.conf.d/telemirror.conf`, `README.md`), the "Output Format"
section of `skylon_set/telemirror-review-prompt.md`, and the two
structural/generator comments in `.configs/citadel_courses.config.yml` /
`.configs/mirror.config.yml`. `REVIEW.md` itself was already fully English
(confirmed by re-scanning — pass 7-10's authors already wrote it that way).
Tests: 279 green throughout (no new tests needed — pure text changes),
`pyflakes`/`ruff` clean after every file, `systemd-analyze verify` re-run
clean on every edited unit, `bash -n` clean on both edited shell scripts.

### Explicitly NOT translated (product content / functional data, verified case by case)

- `.configs/*.yml`'s `SkipWithKeywordsFilter`/`SkipWithUrlFilter` entries
  (`"O Λ И M П"`, `"Олимп"`, `"Золотой билет"`, the `t.me/...` bot handles) —
  literal spam-detection data matched against real incoming message text.
  Translating these would silently change what the filter actually catches.
- Brand strings everywhere («⚜️ Цитадель», «🏴‍☠️ DÈ SKLAD»/variants, «Archonum»
  historical references) — per the Language section's explicit exception.
- `setup_mirrors.py`'s `_LIVE_DONOR_TITLES`/`_COURSE_DONOR_TITLES` lists —
  literal real Telegram channel titles (several already Russian, e.g.
  "Обучение от КОВЧЕГА...", "Activity | Курс для новичков 2024") matched
  exactly against live dialog titles; translating them would break donor
  classification outright, not just cosmetics.
- `README.md` (root) and `tests/test_setup_mirrors_helpers.py` — brand/donor-title
  references only, same reasoning as above.

### Checkpoints resolved during this phase (asked, not guessed)

- Confirmed with the project owner: no external tooling/saved commands grep
  specific Russian substrings from `TECH_CHANNEL` alerts, `journalctl`, or
  operator-script stdout — cleared to translate all log/print text normally.
  (3 test assertions that checked Russian substrings in alert/log text —
  `test_health.py` ×2, `test_past_mode.py` ×1 — were updated in lockstep with
  their source strings.)
- Confirmed with the project owner: no live Telegram channels currently carry
  the `setup_mirrors.py` `"[ДУБЛЬ]"` duplicate-marker prefix from a prior run
  — cleared to translate it to `"[DUPLICATE]"` (the script both writes this
  marker into real channel titles via `EditTitleRequest` and searches for it
  on the next run, so a live-state mismatch here would have orphaned
  previously-marked channels).
- Confirmed with the project owner: `skylon_set/telemirror-review-prompt.md`'s
  own `## Language: All output must be in Russian` directive governs a
  *future, separate* review run and must be preserved as-is; only the
  document's own English-language instructions and its Russian "Output
  Format" template section were translated.
- `skylon_set/telemirror-production-overhaul-prompt.md` (untracked): read in
  full — already entirely English prose (only a quoted brand-name example
  contains Cyrillic). Nothing to translate; left untracked for Phase 6 to
  fold into the history rewrite, per the earlier decision to commit it
  translated (no-op here since translation isn't needed).

---

# Pass 12 — watermark-stamped GIFs lose their animated presentation

Targeted investigation (not a full sweep), triggered by a specific bug report about
mirrored Telegram "GIFs". Tests: 280 green (279 + 1 new), `pyflakes`/`ruff` clean.

## Fixed

- **P2** `telemirror/messagefilters/watermarkfilter.py::WatermarkRemovalFilter._process_video`:
  Telegram "GIFs" are soundless `.mp4` documents carrying both `DocumentAttributeVideo`
  *and* `DocumentAttributeAnimated`. `_process_message` only branches on
  `DocumentAttributeVideo` (it has no separate GIF handling), so a GIF that clears the
  duration/size/encode-cost gates was routed through `_process_video` like any other
  video, which returned the **bare re-upload handle** from `upload_file()` and let it
  flow straight into `message.media`. Read the installed Telethon 1.44 source
  (`.venv/lib/python3.12/site-packages/telethon`) to confirm rather than assume: an
  `InputFile`/`InputFileBig` handle carries no media metadata at all
  (`client/uploads.py:669,757-759`); `mirroring.py`'s send path never forwards an
  explicit `attributes=` for this branch (`mirroring.py:371-382`,
  `telemirror/_patch/sending.py:273-289`), so Telethon's own `utils.get_attributes()`
  auto-infers only a dummy `DocumentAttributeVideo` from the `.mp4` filename extension
  (no real width/height/duration) — and **never** constructs `DocumentAttributeAnimated`
  anywhere in that path (confirmed by grep: the only other occurrences are in the
  unrelated bot `file_id` codec and in `Message.gif`'s own presence-check property,
  `tl/custom/message.py:615-624`). Net effect: a mirrored GIF was silently re-sent as a
  plain video (loses autoplay/loop/no-controls presentation) with no error or log line.
  Fixed by reusing the pattern two sibling filters already use for exactly this
  re-upload-preserves-attributes problem
  (`RestrictSavingContentBypassFilter._process_document`,
  `restrictsavingfilter.py:122-124`, and `DocumentFilenameFilter`,
  `documentfilenamefilter.py:130-132`): wrap the upload handle in
  `types.InputMediaUploadedDocument(file=handle, mime_type=doc.mime_type,
  attributes=doc.attributes)` instead of assigning the bare handle. Verified this
  passthrough is airtight, not just "probably fine": `client._file_to_media` treats an
  already-built `InputMedia` instance as final and routes it through
  `utils.get_input_media`, which for anything with `SUBCLASS_OF_ID ==
  crc32('InputMedia')` (true for `InputMediaUploadedDocument`) does a bare `return media`
  (`utils.py:438-439`) — Telethon's attribute-guessing code is never reached, so the
  original `DocumentAttributeVideo` (real dimensions/duration, not re-guessed) and
  `DocumentAttributeAnimated` survive verbatim. Test:
  `tests/test_watermark_stamp_only.py::test_gif_keeps_animated_attribute_after_stamping`
  (confirmed it fails against the pre-fix code, reproducing the bug, before confirming it
  passes with the fix). Three existing assertions that expected the pre-fix bare-handle
  return value for videos (`test_video_stamp_only_skips_detection`,
  `test_cheap_hd_video_still_stamped`, `test_video_removal_only_skips_stamp`) were updated
  in lockstep to expect the wrapped `InputMediaUploadedDocument`.

---

# Pass 13 — live/past-mode production-safety re-audit (24/7 systemd operation, explicit request)

Independent re-verification against the *current* code (not trusting this journal's
prior "closed"/"no P1/P2" claims), run as three parallel focused investigations
(live-mode runtime, past-mode replay, systemd/health/alert config) specifically
hunting for memory leaks, OOM risk, unhandled crashes, and gaps in systemd's
self-recovery/alerting. Tests: 279 → 286, `pyflakes`/`ruff` clean,
`systemd-analyze verify --recursive-errors=no` clean on all 5 `.service` files.

## Fixed

- **P1** `mirroring.py::new_message`: the DB tracking row (`binding_id`) for
  each successfully-sent fan-out target was batched into a single
  `insert_batch` call after the *entire* fan-out loop returned, with any
  per-target `send_delay` sleep happening before that write —
  `new_album` already does the opposite, correct thing (write, then sleep).
  A raw process kill (SIGKILL, OOM-kill, host crash) during that sleep left an
  already-delivered message with no DB row at all. In past_mode this is a real,
  reachable duplicate on resume: `process_single` only writes the checkpoint
  after `new_message` returns, `_integrity_check` only rolls checkpoints
  *forward*, so it can't detect "sent but untracked" — the message gets
  resent from the old checkpoint. `send_delay` defaults to 0.5s for every
  direction (`config.py:183,220,322`) and the deployed
  `citadel_courses.config.yml` has ~85 `full_history` directions with no
  override, so every message in every backfill run passed through this
  window. In live mode the same gap orphans the message against any later
  edit/delete (the same failure class as the pass-7/8
  `MediaCaptionTooLongError` fixes). Fixed by flushing each successful send
  immediately after appending it, before that target's `send_delay` sleep —
  matching `new_album`'s write-then-sleep order — with `flush_inserted()` now
  clearing `inserted` on a successful write so a later flush in the same
  fan-out can't re-insert already-written rows. Test:
  `tests/test_new_message_batch.py::test_db_write_happens_before_send_delay_sleep`;
  the pre-existing `test_single_insert_batch_for_fanout` (which asserted the
  old single-batch-at-the-end behavior by design) was renamed to
  `test_insert_batch_per_successful_target` and updated to assert one
  `insert_batch` call per target instead.
- **P2** `watermarkfilter.py` / `watermark/processor.py`: Telethon dispatches
  updates concurrently (`sequential_updates` defaults to `False`, never
  overridden), so a burst of videos across channels can trigger several
  concurrent `_process_video` calls, each spawning its own `ffmpeg` child
  process. The host is documented as 1 vCPU
  (`WatermarkConfig.stamp_video_encode_realtime_ratio`'s own docstring,
  `deploy/README.md`'s 6-13 min stamp times) — concurrent encodes don't run
  faster there, they only multiply peak RSS inside the same
  `telemirror.service` cgroup, risking a self-inflicted `MemoryMax=1400M`
  OOM-kill-and-resync on ordinary traffic volume. Added
  `WatermarkConfig.max_concurrent_video_encodes: int = 1` (coerced in
  `__post_init__` alongside the other numeric fields) and a process-wide
  `asyncio.Semaphore` in `watermarkfilter.py`, created lazily (no `await`
  between the check and the assignment, so no race under asyncio's
  single-threaded scheduling — no lock needed), wrapping only the two
  CPU-heavy calls (`async_remove_watermark_from_video`,
  `async_stamp_watermark_on_video`) — not the download, which is I/O-bound.
  Test: `tests/test_watermark_video_encode.py::test_concurrent_video_encodes_are_serialized`.
- **P2** `past_mode.py::_replay_with_retry`: the `(FloodWaitError,
  FloodPremiumWaitError)` branch retried forever (`while True`, sleep
  `e.seconds`, loop) with no cap — unlike the `MediaDownloadError` branch two
  cases below it, which is correctly bounded by `_MEDIA_RETRY_LIMIT`. If
  Telegram keeps reissuing a >300s FloodWait against the same stuck point,
  the process stays alive but makes no progress indefinitely: `Restart=`
  never triggers (the process never exits) and `telemirror-health.py`
  doesn't watch `telemirror-past-courses.service` at all, so this failure
  mode paged nobody and never self-healed. Fixed by mirroring the exact
  `MediaDownloadError` pattern: a `flood_failures` counter and
  `flood_failure_checkpoint` sentinel, reset whenever the checkpoint has
  actually advanced since the last flood wait (normal multi-direction churn
  must not trip this), capped at a new `_FLOOD_RETRY_LIMIT = 20`; past the
  cap, log an error and `raise` instead of retrying, so the process exits and
  `Restart=on-failure` / `StartLimitBurst` / the already-wired
  `OnFailure=telemirror-alert@%n.service` (Batch G) take over — a bounded
  stall becomes a detectable, alertable crash instead of an invisible hang.
  Tests: `tests/test_past_mode.py::test_replay_with_retry_gives_up_after_flood_retry_limit_at_same_checkpoint`,
  `..._flood_retry_counter_resets_on_checkpoint_progress`.
- **P3** `deploy/cron.d/telemirror-tmp`: the cleanup glob (`tmp*.mp4`) only
  matched the watermark filter's video temp files.
  `_media.py:downloaded_tempfile` (used by `documentfilenamefilter.py` and
  `restrictsavingfilter.py` for arbitrary re-uploaded documents) creates temp
  files with the real/mimetype-derived extension instead — `.pdf`, `.zip`,
  none, etc. — all still `tmp`-prefixed (Python's default) but never
  `.mp4`. The cron job's own stated purpose (manual `past_mode.py` runs
  outside systemd, and OOM crashes — exactly where `PrivateTmp=true` doesn't
  apply) had no cleanup path at all for these. Broadened the glob to `tmp*`
  and added `-type f` (scoping it to regular files only, so it can never
  touch an unrelated tool's `tempfile.mkdtemp` directory).
- **P3** `deploy/systemd/telemirror-restart.service`: had no `OnFailure=`,
  unlike `telemirror.service` and `telemirror-past-courses.service`. Added
  `OnFailure=telemirror-alert@%n.service` for consistency — a failed daily
  clean-restart now pages immediately instead of relying on
  `telemirror-health.timer`'s ~10-20 min backstop.

## Investigated, found to be a false positive — corrected here

- One of the three parallel investigations flagged `mirroring.py`'s
  2-hour-silence watchdog warning
  (`self._logger.warning("watchdog: no update in %.0f min...")`,
  ~line 1382) as a P1 on the grounds that it only logs, never reaching
  TECH_CHANNEL, contradicting `deploy/README.md`'s documented behavior.
  Traced by hand and found incorrect: `self._logger` *is*
  `logging.getLogger("telemirror")` — the exact same logger object
  `main.py:117` creates via `setup_stdout_logger("telemirror", LOG_LEVEL)`
  and passes down through `Telemirror.__init__` → `Mirroring.__init__` — and
  `mirroring.py:1270` attaches a `TelegramLogHandler` (forwards WARNING+ to
  TECH_CHANNEL, debounced/cooled-down) to `logging.getLogger("telemirror")`
  by that same name, before the watchdog task is even started. So the
  watchdog's `.warning()` call already reaches TECH_CHANNEL through the
  attached handler — no code change made; recorded here so this isn't
  mistakenly "fixed" into a second, duplicate alert path later.

## Reviewed, no change — raised with the project owner, explicitly declined

- No non-Telegram fallback alert channel (dead-man's-switch heartbeat, SMTP):
  `alert.py` and the in-process `TelegramLogHandler` path are both entirely
  dependent on the same Telegram/network connectivity the bot itself needs,
  so a VPS-wide network outage silences every alert path at once even though
  the bot still self-heals via systemd. Owner confirmed this is acceptable —
  human notification of an outage is secondary to the bot's own recovery,
  which doesn't depend on alerting succeeding.
- `OOMScoreAdjust`/`OOMPolicy` tuning on `telemirror.service`: the host also
  runs `postgresql.service` (`telemirror.service`'s own
  `After=network-online.target postgresql.service`), which isn't
  self-healing the way `telemirror.service`'s `Restart=always` is — a
  system-wide OOM kill (as opposed to telemirror's own cgroup `MemoryMax`,
  which is already scoped to telemirror alone) could in theory pick postgres
  over telemirror. Owner declined — a separate host-level tuning decision,
  out of scope for this pass.

---

# Pass 14 — re-audit of pass 13 itself, plus the modules pass 13 hadn't covered (explicit repeat request)

The owner repeated the pass-13 request verbatim before its diff was committed.
Treated as a genuine second pass, not a rubber-stamp: one investigation
specifically self-reviewed pass 13's own (still-uncommitted) diff for
regressions/edge cases the fixes themselves might have introduced, a second
swept `telemirror/storage.py`, `config.py`, the non-watermark messagefilters,
`telemirror/mixins.py` + `telemirror/misc/*`, and a quick `skylon_set/*`
interference check — areas pass 13's three agents hadn't gone deep on. Tests:
286 → 288, `pyflakes`/`ruff` clean.

**The sweep of untouched modules came back clean.** `InMemoryDatabase`'s LRU
(capacity 100) and `ReuploadCache` (TTL 600s / LRU 16) are correctly bounded
at construction; `PostgresDatabase.__pg_cursor` was traced against the
actually-installed `psycopg_pool` source and leaks no connection/cursor under
any exception path. More importantly: `InMemoryDatabase` turned out to be
moot in production — the real `.env` has `USE_MEMORY_DB=false`, so
`PostgresDatabase` is what actually runs both `telemirror.service` and
`telemirror-past-courses.service`. `config.py`'s filter instances hold only
immutable compiled regexes/sets, confirmed zero per-message accumulation.
`telemirror/mixins.py` and `telemirror/misc/*` had nothing new. The one
result from this half was a documentation fix (below), not a bug.

**The self-review of pass 13's own diff found the core logic sound** (no
double-inserts, no dropped rows, correct exception propagation out of
`_replay_with_retry` through to process exit, the two retry counters —
flood and media — don't interfere with each other) but surfaced three real
gaps in the fixes themselves, closed in this pass:

## Fixed

- **P2** `telemirror/watermark/processor.py::WatermarkConfig.__post_init__`:
  the new `max_concurrent_video_encodes` field (pass 13) had no lower-bound
  check, unlike sibling fields that document "0 = disable." `asyncio.
  Semaphore(0)` is legal Python and blocks every `acquire()` forever since
  nothing ever holds a permit to release — a config author following the
  sibling-field convention and setting `max_concurrent_video_encodes: 0`
  expecting "no cap" would instead get a silent, permanent hang of the whole
  watermark pipeline (a hang, not a crash, so `Restart=` never sees it).
  Not triggered by either real deployed config, but a footgun in the exact
  mechanism pass 13 added to prevent an OOM. Now validated `>= 1` at
  construction, raising `ValueError` (matches the existing `stamp_video_preset`
  fail-fast pattern right below it). Test:
  `tests/test_watermark_video_encode.py::test_zero_max_concurrent_video_encodes_rejected_at_config_time`.
- **P2** `telemirror/messagefilters/watermarkfilter.py`: the pass-13
  semaphore is sized once, from whichever `WatermarkConfig` is seen *first
  at runtime* (nondeterministic — depends on message arrival order, not
  config-declaration order); every other direction's
  `max_concurrent_video_encodes` was then silently ignored process-wide for
  the rest of the process's lifetime. Not reachable today — both real
  configs (`.configs/mirror.config.yml`, `.configs/citadel_courses.config.yml`)
  declare `WatermarkRemovalFilter` once, shared via `default_filters`,
  confirmed by reading `config.py::build_filters` — but a future
  per-direction override would silently not apply, with zero signal,
  quietly re-opening the OOM risk pass 13 exists to close. Not fixed by
  resizing the live semaphore (real complexity/risk of getting the permit
  accounting wrong for no evidenced need); instead the mismatch is now
  logged (`logger.warning`, reaching TECH_CHANNEL through the existing
  `TelegramLogHandler` wiring) so it's visible instead of silent. Test:
  `tests/test_watermark_video_encode.py::test_mismatched_limit_logs_a_warning_instead_of_silently_ignoring_it`.
- **P2** `deploy/cron.d/telemirror-tmp` + `_media.py::downloaded_tempfile` +
  `watermarkfilter.py::_process_video`: pass 13 broadened the cleanup glob
  from `tmp*.mp4` to `tmp*` to also catch non-video orphaned temp files —
  but `tmp` is Python's (and many other tools') *default* `tempfile` prefix,
  so the broadened glob, run hourly as `root` against anything sitting
  directly in shared `/tmp` for >180 minutes, was no longer
  telemirror-specific. This host also runs `postgresql.service`
  (`telemirror.service`'s own `After=`); any other process relying on
  `tempfile`'s default naming could have had its own legitimate scratch
  files deleted — `-type f` protects directories but does nothing about
  this. Fixed by giving telemirror's own temp files a distinctive
  `telemirror-tmp-` prefix (`tempfile.NamedTemporaryFile(prefix=...)`,
  which replaces Python's default rather than appending to it) at both call
  sites, and narrowing the cron glob to match only that prefix — keeps
  pass 13's actual goal (every extension, not just `.mp4`) without the
  blast-radius regression. No test needed (no code path depended on the old
  naming; verified by grep before the change).

## Fixed — documentation only

- **P3** `telemirror/messagefilters/_media.py::ReuploadCache` docstring
  claimed "Instances are created once per direction in
  `config.build_filters`" — false for both real deployed configs, which
  share one instance process-wide via `default_filters` (confirmed by
  reading `config.py` and both `.configs/*.yml` files). Not a bug (the
  cache is still hard-capped at 16 entries regardless of sharing scope), but
  misleading about actual cross-direction isolation. Docstring corrected to
  describe the real per-filter-*instantiation* scope and its practical
  consequence (a burst of >16 distinct media items across unrelated source
  channels within the 600s TTL can evict each other's entries).

## Reviewed, no change — accepted trade-offs

- `new_message`'s per-target flush (pass 13) is now O(N) DB round-trips per
  fan-out instead of O(1) — quantified against the real ~199-target
  broadcast direction in `.configs/mirror.config.yml`: a small, proportionate
  overhead next to the per-target Telegram `send_message` call that already
  dominates fan-out latency. The correct trade-off for the crash-safety it
  buys.
- A flush that fails to receive `insert_batch`'s server-side ack (but which
  Postgres actually committed) can produce a duplicate `binding_id` row on
  retry — a pre-existing risk (not introduced by pass 13, `binding_id` has
  no UNIQUE constraint, documented since pass 7), now exercised up to N times
  per message instead of once; harmless (a duplicate row just makes a later
  edit/delete touch the mirror twice, already caught/logged).
- `past_mode.py`'s bounded FloodWait retry (pass 13) caps *count* (20), not
  cumulative *wall-clock time* — `FloodWaitError.seconds` has no documented
  upper bound from Telegram, so a pathological stretch could still take a
  long time to give up, and `_replay_with_retry` runs strictly sequentially
  per direction so a stuck one blocks the rest of that run. Strictly better
  than the pre-pass-13 infinite retry either way; not tightened further
  without evidence this is a real-world problem.

## Pass 14 self-review — one test-isolation bug found and fixed

A dedicated cleanliness/correctness pass over the pass-13 + pass-14 diff
itself (two independent reviewers: one for the six source/config files, one
for the three test files). The source-code review came back clean — no bugs,
one NIT (the watermark mismatch-warning logs on every mismatched call rather
than once, harmless given `TelegramLogHandler`'s existing debounce, not
worth changing). The test review found one real bug:

- **BUG** `tests/test_watermark_video_encode.py`:
  `test_concurrent_video_encodes_are_serialized` and
  `test_max_concurrent_video_encodes_raises_the_cap` each reset the module
  global `_video_encode_semaphore` via `monkeypatch.setattr(wf, "_video_encode_semaphore",
  None)` before running, but neither reset the companion global
  `_video_encode_semaphore_limit` pass 14 added. `monkeypatch.setattr` only
  restores a patched attribute to its pre-patch value on teardown — since
  `_video_encode_semaphore_limit` was never patched, the `global`-statement
  assignment `_get_video_encode_semaphore` makes to it during the test body
  persisted unreverted, leaving the two globals out of sync with each other
  after the file runs (confirmed empirically: after
  `test_max_concurrent_video_encodes_raises_the_cap`, teardown restored
  `_video_encode_semaphore` to a stale leftover object with real capacity 1
  while `_video_encode_semaphore_limit` stayed at 2). Didn't fail anything
  today only by alphabetical test-file-ordering luck; a future test
  requesting limit 2 without resetting first would have silently received
  the stale capacity-1 semaphore with no warning logged — reproducing,
  inside the test suite's own state, the exact silent-mismatch failure mode
  pass 14 exists to surface. Fixed by also resetting
  `_video_encode_semaphore_limit` to `None` in both tests, matching the
  third new test in the same file
  (`test_mismatched_limit_logs_a_warning_instead_of_silently_ignoring_it`),
  which already reset both globals correctly. Verified by re-running the
  full watermark test-file group and inspecting both globals afterward —
  consistent (`value:1` / `limit: 1`), no leaked stale state.

---

# Pass 15 — review of the uncommitted `FileReferenceExpiredError` diff, plus a gap check for commits after pass 14

Triggered by a general "review the whole project and fix bugs" request. Two
uncommitted files (`telemirror/messagefilters/_media.py`,
`telemirror/mirroring.py`) had just added `FileReferenceExpiredError` handling
(Telegram's stale-file-reference error: refetch the source message(s) for a
fresh reference and retry the send/download once) with no test coverage and no
journal entry yet — reviewed from scratch by direct code trace rather than
assumption. Also checked whether the three commits after this journal's
previous entry (`7b7976f`, `912dcc3`, `a056c32`) needed logging here. Tests:
288 → 298 (10 new across this pass and its self-review below),
`pyflakes`/`ruff` clean.

## Fixed

- **P2** `mirroring.py::new_album`'s `FileReferenceExpiredError` handler
  refetches all of an album's source messages
  (`self._client.get_messages(chat_id, ids=idxs)`) and rebuilds `files` from
  the result, but kept reusing the original `captions`/`album_entities` lists
  built from `idxs`-order — so correctness depends on the refetch preserving
  both order *and* count. The existing per-item guard
  (`any(fresh is None or not fresh.media ...)`) only catches an individually
  missing message; it does not catch `get_messages` returning a different
  *length* outright. The non-refresh success path two dozen lines below
  already treats exactly this risk class as untrustworthy
  (`len(outgoing_messages) != len(idxs)`, log + skip tracking rather than
  write a wrong mapping) — the new refresh branch violated that same
  established convention. Fixed by adding `len(fresh_list) != len(idxs)` to
  the guard, same treatment (log + `continue`). Test:
  `tests/test_file_reference_refresh.py::test_new_album_refresh_length_mismatch_skips_tracking`
  (constructs a two-item album with a `get_messages` stub that returns only
  one refreshed message; confirmed it fails — via an unguarded misalignment,
  not a clean skip — against the pre-fix code before confirming the fix
  makes it pass).
- **P3** Both `new_message`'s and `new_album`'s `FileReferenceExpiredError`
  handlers retried with `... if config.mode == "copy" else await
  forward_messages(...)`, but the `forward_messages` arm is dead code: traced
  `telemirror/_patch/sending.py::forward_messages` (lines 446-498) — it
  forwards by id via `ForwardMessagesRequest` server-side and never touches a
  message's `file_reference`, so `FileReferenceExpiredError` cannot originate
  from a `forward_messages` call in the primary attempt above. By the time
  either except-handler runs, `config.mode == "copy"` is already guaranteed,
  so the `else` branch could never execute. Simplified both handlers to call
  `send_message`/`send_file` directly, with a comment recording why forward
  mode is unaffected. Not a live bug (the branch was simply unreachable), but
  worth trimming since it obscured the handler's actual precondition. Tests:
  `tests/test_file_reference_refresh.py::test_new_message_refresh_success_tracks_message`
  and `::test_new_album_refresh_success_tracks_with_correct_mapping` lock in
  the intended copy-mode refresh-and-resend behavior now that the dead branch
  is gone.

## Reviewed, no change

- `_media.py::download_media_with_retry`'s own `FileReferenceExpiredError`
  branch (scalar refetch via `get_messages(message.chat_id, ids=message.id)`)
  has no ordering/alignment exposure — a single-item refetch can't be
  misaligned. (A separate, real bug in this same branch — unrelated to
  alignment — was found by a follow-up self-review; see below.)
- Checked whether the three commits after this journal's previous entry
  needed a catch-up log here. `7b7976f` (merge of upstream `khoben/telemirror`
  at `19cf3ac`) is confirmed content-neutral for `telemirror/`
  (`git diff 0e2020b..a056c32 --stat -- telemirror/` shows only the changes
  `912dcc3`/`a056c32` themselves introduce; the merge commit's own `--stat` is
  empty). `912dcc3` and `a056c32` already carry their own full journal entries
  (Pass 12, Pass 13, Pass 14, and the pass-14 self-review above) committed in
  the same diffs — there was no actual gap, just this pass's own initial
  assumption that needed checking against the real commit contents rather
  than commit order alone.

## Pass 15 self-review — three more bugs found and fixed

A dedicated re-check of this pass's own diff (still uncommitted), prompted by
an explicit request to verify the just-written code once more. Traced each
`FileReferenceExpiredError` branch's control flow line by line instead of
trusting the "Reviewed, no change" note above. A follow-up request to also
act on two efficiency/cleanliness observations from the first pass (not bugs)
led to one more fix below. Tests: 291 → 298 (7 new).

## Fixed

- **P2** `_media.py::download_media_with_retry`: the `FileReferenceExpiredError`
  branch set `message = fresh` and `refreshed = True` but then relied on the
  enclosing `for i in range(attempts)` loop's *next* iteration to actually
  retry the download. When the error's first (and only, since a second
  occurrence re-raises) occurrence happens on the *last* attempt, there is no
  next iteration — the loop simply ends and the function falls off the end,
  implicitly returning `None` instead of the downloaded bytes or a raised
  error. Confirmed by direct simulation before touching the code: 6 transient
  `ValueError`s to exhaust `_DOWNLOAD_RETRY_DELAYS`, then a
  `FileReferenceExpiredError` on the 7th call reproducibly returned `None`
  after 7 total calls with the pre-fix code. A caller silently receiving
  `None` where it expects bytes (e.g. `downloaded_tempfile` writing an empty
  file, or `RestrictSavingContentBypassFilter` re-uploading `photo_bytes=None`)
  is a worse failure mode than a raised exception, since nothing in the call
  chain treats `None` as an error signal. Fixed by retrying the download
  inline within the `except` block itself right after the refresh, instead of
  depending on loop iteration — matches the docstring's own description
  ("retried immediately") and needs no attempt-budget bookkeeping. Tests:
  `tests/test_media_helpers.py::test_download_retry_refreshes_on_last_attempt`
  (reproduces the exact exhausted-budget-then-expired-reference sequence;
  confirmed it fails with `None != b"payload"` against the pre-fix code),
  plus `test_download_retry_refreshes_file_reference_and_succeeds` and
  `test_download_retry_second_file_reference_expired_raises` for the ordinary
  and second-occurrence cases, which had no direct test before either.
- **P1** `mirroring.py::new_message` and `mirroring.py::new_album`: the
  `FileReferenceExpiredError` handler's retried `send_message`/`send_file`
  call was wrapped only in a generic `except Exception as e: ... continue` —
  unlike every other send attempt in this same function (the primary attempt,
  and the `MediaCaptionTooLongError` split-caption retry), which all
  special-case `(errors.FloodWaitError, errors.FloodPremiumWaitError)` to
  re-raise instead of swallowing. A `FloodWaitError` raised by the refreshed
  retry was therefore logged and skipped like an ordinary failure, and
  `new_message`/`new_album` returned normally — `past_mode.py`'s
  `process_single`/`process_album` unconditionally advance the checkpoint
  right after these return, so a flood wait hit during exactly this retry
  permanently skipped the message/album instead of reaching past_mode's
  retry wrapper, the same checkpoint-safety invariant pass 13 (`## Fixed`,
  first entry above) already spent significant effort establishing elsewhere
  in this file. Fixed by adding the same
  `except (errors.FloodWaitError, errors.FloodPremiumWaitError): raise`
  (with `flush_inserted()` first in `new_message`, matching its sibling
  split-caption handler) before the generic `except Exception` in both
  handlers. Tests:
  `tests/test_file_reference_refresh.py::test_new_message_refresh_retry_does_not_swallow_floodwait`
  and `::test_new_album_refresh_retry_does_not_swallow_floodwait` (both
  confirmed to fail with "DID NOT RAISE FloodWaitError" against the pre-fix
  code before confirming the fix makes them pass).
- **P3** `mirroring.py::new_message` and `mirroring.py::new_album`: a refreshed
  file_reference was only written onto the current fan-out target's local
  copy (`filtered_message.media` / the rebuilt `files` list), never back onto
  the shared `message`/`album` object every remaining target in the same
  fan-out loop builds its own copy from (`copy_message`/`copy_album`, both
  `deepcopy`-based). A source message mapped to N outgoing chats therefore
  redid the identical `get_messages` refetch against the identical stale
  reference for each of the N targets instead of once — real waste on the
  project's own broadcast direction (`.configs/mirror.config.yml`, ~199
  targets, referenced elsewhere in this journal). Fixed by also assigning
  `message.media = fresh.media` in `new_message`, and writing each refreshed
  media back onto the matching-by-id message in `album` in `new_album` (matched
  by id rather than position, since `idxs`/`fresh_list` come from the
  *filtered* album, not necessarily identical objects to the ones in `album`).
  Tests: `tests/test_file_reference_refresh.py::test_new_message_refresh_is_reused_across_fanout_targets`
  and `::test_new_album_refresh_is_reused_across_fanout_targets` (two-target
  chat_mapping, distinguishable stale/fresh media marker types so a copy
  survives the `deepcopy` in `copy_message`/`copy_album`; both confirmed to
  fail — one extra `send` call and a second `get_messages` call — against the
  pre-fix code before confirming the fix makes them pass).

## Considered, not changed

- The refetch-check-retry pattern is duplicated across three sites
  (`_media.py::download_media_with_retry`, `mirroring.py::new_message`,
  `mirroring.py::new_album`). Considered extracting a shared helper; declined
  — the three sites differ in enough real ways (scalar vs. list refetch,
  download vs. send, and different post-refresh error handling) that a
  unifying abstraction would mostly hide branching rather than remove
  duplication, for three call sites total. Revisit if a fourth site appears.

## Follow-up — the refreshed retry send had no caption-split fallback

A dedicated whole-project review (independent of pass 15 above) traced the two
independent retry paths this same pair of functions now has —
`FileReferenceExpiredError` (refetch + resend once) and `MediaCaptionTooLongError`
(split into media + text) — and found they were only composed one way.

## Fixed

- **P2** `mirroring.py::new_message` and `mirroring.py::new_album`: the retry
  `send_message`/`send_file` call inside each `FileReferenceExpiredError`
  handler had no `MediaCaptionTooLongError` clause, only the generic
  `except Exception: ... continue` also covered by pass 15's P1 fix above (for
  `FloodWaitError`) but never extended to this error. A message/album with
  *both* a stale file_reference and a caption over 1024 chars — plausible
  together during a past_mode replay of old history — would refresh
  correctly, then have its resend rejected as too-long, and be logged and
  dropped instead of delivered split, unlike the identical situation on the
  primary (non-refreshed) attempt a few lines above, which already handles it.
  Fixed by adding the same split-media-then-text-tail fallback (duplicated
  from the primary attempt's existing handler rather than extracted into a
  shared helper, matching this file's established convention of parallel,
  independently-maintained retry blocks) to both refresh-retry paths. Tests:
  `tests/test_file_reference_refresh.py::test_new_message_refresh_retry_caption_too_long_splits`
  and `::test_new_album_refresh_retry_caption_too_long_splits` (both confirmed
  to fail — the split media/text calls never happened, the message was
  silently dropped — against the pre-fix code before confirming the fix makes
  them pass). Full suite: 298 → 300, `ruff` clean.

## Follow-up 2 — refetch error handling and a dead-code guard in the same retry paths

A review of the still-uncommitted diff from the two follow-ups above found
three more issues in the same `FileReferenceExpiredError` machinery.

## Fixed

- **P1** `mirroring.py::new_message`'s and `mirroring.py::new_album`'s
  `FileReferenceExpiredError` handlers refetch the source message(s)
  (`self._client.get_messages(...)`) to get a fresh reference. `new_message`
  only caught `FloodWaitError`/`FloodPremiumWaitError` from that call;
  `new_album` caught nothing at all. Any other exception (a dropped
  connection, a generic RPCError) therefore escaped the function entirely
  instead of being logged and skipped for just the current `outgoing_chat` —
  `@__handle_exceptions` swallows it silently, and past_mode advances the
  checkpoint right after, permanently dropping the message/album for every
  target not yet reached in that fan-out. Fixed by wrapping both refetch
  calls the same way every other send/refetch attempt in this file already
  is: `(FloodWaitError, FloodPremiumWaitError)` still propagates (with
  `flush_inserted()` first in `new_message`, matching its siblings), a
  generic `Exception` is now logged and `continue`s to the next config/chat.
  Tests:
  `tests/test_file_reference_refresh.py::test_new_message_refresh_refetch_generic_error_skips_target_only`
  and `::test_new_album_refresh_refetch_generic_error_skips_target_only`
  (two-target fan-out, refetch always raises `ConnectionError`; confirmed
  both targets' refetch attempts happened and neither call raised out of
  `new_message`/`new_album`, against a pre-fix run where the second target
  was never reached at all).
- **P3** `_media.py::download_media_with_retry`: the `if refreshed: raise`
  guard at the top of the `FileReferenceExpiredError` handler was dead code —
  the post-refresh retry was a one-off inline call outside the `for i in
  range(attempts)` loop's accounting, so control could never re-enter this
  except block a second time with `refreshed` already `True`. As a side
  effect, a transient error (`ConnectionError`/timeout/retryable `ValueError`)
  on that same inline retry converted straight to `MediaDownloadError`
  instead of falling back to whatever was left of `_DOWNLOAD_RETRY_DELAYS` —
  a short-lived DC hiccup right after a refresh was treated as permanent even
  with most of the ~20-minute budget unspent. Both share one root cause:
  fixed by turning the loop into `while i < attempts` with `i` incremented
  manually, and replacing the inline retry with a plain `continue` back into
  the loop at the same `i` (the refresh itself still doesn't spend a
  budgeted attempt). A second `FileReferenceExpiredError` now naturally
  re-enters the except block with `refreshed == True` and the guard raises it
  (no longer dead); a transient error on the retry now falls into the
  existing `ConnectionError`/`TimeoutError`/`ValueError` handler and reuses
  the remaining schedule instead of giving up immediately. Traced against all
  5 pre-existing tests for this function call-by-call before changing
  anything — all pass unchanged, including the last-attempt edge case the
  inline retry existed to handle. Test:
  `tests/test_media_helpers.py::test_download_retry_transient_error_after_refresh_uses_remaining_schedule`
  (refresh succeeds, the immediate retry hits a transient `ConnectionError`,
  the next attempt succeeds; confirmed it fails as `MediaDownloadError`
  against the pre-fix code before confirming the fix makes it pass). Full
  suite: 300 → 303, `ruff` clean.

---

# Pass 16 — token-limited-pass findings, verified and fixed (`skylon_set/telemirror-bugfix-review-prompt.md`)

Picked up 10 candidate findings left by an earlier, deliberately cheap review
pass (3 parallel agents scoped to disjoint file groups, one manual
read-and-verify pass per finding, no whole-project sweep). Re-verified every
one against the current code (several months of fixes had landed since they
were written) rather than transcribing them, then ran the cross-cutting
sweeps the prompt calls for (UTF-16 vs codepoint length, dict/set key
collapsing, `zip()` strictness, event-handler exception-wrapping
consistency, `except Exception` near checkpoint state, union type-hint
handling, blocking calls inside `async def`, and an ad hoc `mypy` run — no
type checker was previously configured for this project). Tests: 310 → 315,
`pyflakes`/`ruff` clean after each fix.

## Verified from the 2026-09-13 pass

- **#1 — real, fixed below.** `mirroring.py` `new_message`/`new_album`:
  `reply_to_messages` built as `{m.mirror_channel: m.mirror_id for m in ...}`
  collapses two `MirrorMessage` rows that share a `mirror_channel` (possible
  whenever one outgoing chat is reached by more than one topic-scoped
  `DirectionConfig` matching the same source topic — e.g. a
  `from_topic_id=None` catch-all plus a specific one — `binding_id` has no
  topic column, confirmed in `storage.py`).
- **#2 — real, still open, see plan.** `mirroring.py::_send_album_with_caption_split`
  (line ~541): `len(caption) > 1024` is a Python codepoint count, not
  Telegram's UTF-16 code-unit count; an emoji-heavy caption can pass this
  check unsplit and still exceed Telegram's real limit, hitting the "Can't
  actually happen" catch-all a few lines below and dropping the whole album.
  Independently re-found by this pass's own UTF-16 sweep.
- **#3 — false positive, re-affirmed.** `watermarkfilter.py`
  `_process_video`/`_process_photo`: an exhausted `MediaDownloadError` in
  live mode does return `None` → the original media is forwarded
  unwatermarked, but this is the module's own documented invariant
  ("best-effort … no message loss", closed 2026-08-30) — there is no
  "branding guarantee" elsewhere in the codebase this contradicts. Not a bug.
- **#4 — false positive.** `past_mode.py::_edit_links_pass`'s
  `zip(msg_copy.entities, entities_before, strict=False)`: traced
  `_rewrite_links`/`update_entities_params` — they only mutate existing
  entities' `.url`/`.offset`/`.length` in place, never append/remove list
  elements, so the two zipped lists are always equal length by construction.
  The hypothesized entity-count-changing scenario doesn't occur.
- **#5 — real but not reachable via any documented config; fixed below as a
  type-hint correction.** `watermarkfilter.py::WatermarkRemovalFilter.__init__`
  types `channels` as `Optional[list[int | str]]` but does `int(c)`
  unconditionally — a literal `@username` string would crash bot startup.
  No real config (the docstring, `.configs/mirror.config.yml`, or any other
  filter in the project) ever passes a string here; owner chose to correct
  the type hint rather than add real username support.
- **#6 — real, fixed below.** `messagefilters.py::KeywordReplaceFilter._apply_rule`:
  `match.expand(replacement)` for a raw-regex rule has no error handling. A
  rule referencing a non-existent capture group (a realistic operator typo —
  raw-regex rules are a documented feature) raises `re.error` at
  message-processing time; caught by `__handle_exceptions` (contained, one
  message lost, not fatal) but with no load-time signal, so a config typo
  silently breaks every future message matching that pattern.
- **#7 — real, confirmed cosmetic-only, not fixed.** `past_mode.py`: on a
  resumed `full_history`/`since_date` run, `iter_total` stays the whole
  channel total while `processed` restarts at 0, skewing the progress/ETA
  log. Confirmed it feeds only that log line — no retry/stop condition
  depends on it. Left as a documented P3 (see "Deferred" below); a fix would
  need to thread "already-mirrored count at resume" through
  `_replay_direction`, more machinery than a cosmetic log line warrants.
- **#8 — real, fixed below.** `mirroring.py::EventHandlers.on_private_message`
  is the only event handler with no exception handling. Because it never
  calls into `EventProcessor`, an exception here (e.g. `FloodWaitError`
  sending the tech-channel notification) is caught by Telethon's own default
  per-handler logging under the `"telethon"` logger — not `"telemirror"` —
  so it never reaches `TelegramLogHandler`/`TECH_CHANNEL`, unlike every other
  failure path in this module.
- **#9 — architectural gap, not a bug; raised with the project owner per the
  prompt's own instructions, not fixed.** No periodic reconciliation job
  exists for live-mode fan-out gaps left by a mid-broadcast `FloodWaitError`;
  the only recovery mechanism (`past_mode.py::_integrity_check`) is
  manually triggered. Owner declined to add one for now — see "Reviewed, no
  change" below.
- **#10 — false positive, re-affirmed against the actual pinned toolchain.**
  `watermark/processor.py`'s watermark-PNG overlay (no `-loop 1`) relies on
  ffmpeg `overlay`'s `eof_action=repeat` default. Confirmed the `Dockerfile`
  installs ffmpeg via plain `apt-get install ffmpeg` on `python:3.13-slim-bookworm`
  (Debian bookworm's repo package, `7:5.1.8-0+deb12u1`) — no static build, no
  pin overriding the default, and `eof_action=repeat` has been ffmpeg's
  default since the filter's introduction (≥2.8, 2015), well before 5.1.x.
  Nothing in `processor.py`'s constructed filter graph sets `eof_action`.

## New findings from this pass's cross-cutting sweeps

- **#11 — real, fixed below.** `past_mode.py::_edit_links_pass`:
  `mirror_map = {m.original_id: m for m in mirrors}` has the identical
  collapsing bug as #1, one layer over — `get_messages_for_channel_pair` is
  intentionally topic-blind (confirmed multi-topic-per-pair replay is an
  actively supported, tested feature per Batch C), so the same source
  message mirrored into two topics of one target channel collapses to one
  `MirrorMessage` in this dict, and the link-fix pass only ever corrects one
  topic's copy — the other keeps a stale/un-rewritten `t.me` link
  permanently (this pass runs once, best-effort, no retry).
- **#12 — real, minor, not fixed.** `past_mode.py` (~line 586): the
  `len(full) <= 4096` check for the TECH_CHANNEL run-summary message is a
  Python codepoint count, not UTF-16. Same class of bug as #2 but on an
  internal-only admin message built mostly from channel IDs plus one BMP
  emoji header — practically never reachable, and splitting an
  occasionally-oversized internal summary into two Telegram messages has no
  correctness impact. Left as documented, not worth the code for the risk.

## Fixed

- **P2** `mirroring.py::new_message`/`new_album` — finding #1 above.
  Extracted `EventProcessor._reply_target_mirrors(chat_id, reply_to_msg_id)`,
  used by both functions: it groups `get_messages(...)` results by
  `mirror_channel` and returns only channels with exactly one mirror,
  dropping ambiguous ones instead of picking one arbitrarily (last-write-wins
  in the old dict comprehension). An ambiguous target now falls back to the
  pre-existing "no known mirror to reply to" path (`reply_to` = the
  destination topic anchor, no reply chain) instead of risking a reply
  pointed at a mirror living in the wrong topic. Test:
  `tests/test_reply_to_topic_ambiguity.py::test_ambiguous_reply_target_across_topics_is_not_guessed`
  (two topic-scoped configs on one target both matching the same source
  topic, two pre-seeded `MirrorMessage` rows sharing `mirror_channel`;
  confirmed it fails — both configs got the same wrong `mirror_id`, `222`,
  as their reply target — against the pre-fix code before confirming the fix
  makes it pass).
- **P2** `mirroring.py::_send_album_with_caption_split` — finding #2 above.
  `len(caption) > 1024` → `len(utils.add_surrogate(caption)) > 1024`,
  matching the UTF-16-aware pattern already used elsewhere in this file
  (`_rewrite_links`). Test:
  `tests/test_caption_too_long_split.py::test_new_album_split_measures_caption_in_utf16_not_codepoints`
  (a 600-non-BMP-emoji caption — 600 Python chars, 1200 UTF-16 units — with a
  `send_file` stub that emulates Telegram's real UTF-16-based rejection;
  confirmed it fails — the retried send got the same untouched over-limit
  caption and the album was silently dropped, never tracked — against the
  pre-fix code before confirming the fix correctly strips the caption to a
  separate tail text and tracks the album).
- **P2** `messagefilters.py::KeywordReplaceFilter.__init__` — finding #6
  above. Validates each rule's replacement at construction time by running
  the compiled pattern's own `.sub(replacement, "")` against an empty
  string — `re.Pattern.sub` compiles/validates the replacement template
  (including group references) up front, even with no match, so an invalid
  reference now raises `ValueError` at config load, the same fail-fast
  contract `_compile_keyword` already gives the pattern half of each rule.
  Test:
  `tests/test_keyword_replace_filter.py::test_replacement_referencing_nonexistent_group_raises_value_error_at_construction`
  (confirmed it fails — `KeywordReplaceFilter({r"r'(foo)'": r"\2"})`
  constructed without error — against the pre-fix code before confirming the
  fix raises `ValueError` at that same call).
- **P3** `mirroring.py::EventHandlers.on_private_message` — finding #8 above.
  Wrapped in `try`/`except Exception`, logging through
  `self._processor._logger` (the same "telemirror"-named logger every other
  path in this module uses, with `TelegramLogHandler` attached to it) rather
  than letting the exception fall through to Telethon's own default
  per-handler logging under a different logger name. Test:
  `tests/test_on_private_message.py::test_notification_failure_is_logged_not_left_unhandled`
  (confirmed it fails — `RuntimeError` propagated straight out of
  `on_private_message` — against the pre-fix code before confirming the fix
  logs it and returns normally).
- **P2** `past_mode.py::_edit_links_pass` — finding #11 above. `mirror_map`
  is now `Dict[int, List[MirrorMessage]]` (was `Dict[int, MirrorMessage]`),
  built with `setdefault(...).append(...)` instead of a plain dict
  comprehension, and the `client.edit_message` call is now a loop over
  `mirror_map[src_msg.id]` instead of a single lookup — every mirror of a
  multi-topic source message gets its link fixed, not just the
  last-inserted one. Test:
  `tests/test_past_mode.py::test_edit_links_pass_fixes_every_mirror_of_a_multi_topic_source_message`
  (two `MirrorMessage` rows sharing `original_id=10` but different
  `mirror_id`s in the same target pair; confirmed it fails — only `920`
  (the later-inserted row) got edited, `910` silently kept its stale link —
  against the pre-fix code before confirming the fix edits both).

## Fixed — documentation/type-hint only

- **P3** `watermarkfilter.py::WatermarkRemovalFilter.__init__` — finding #5
  above. `channels: Optional[list[int | str]]` → `Optional[list[int]]`, and
  the docstring now spells out "numeric … int, or a numeric string … not a
  `@username`". No runtime behavior changes — `int(c)` already only ever
  worked for numeric values, and no shipped config passes anything else
  (`.configs/mirror.config.yml` confirmed) — this only corrects the type/doc
  to stop inviting a value that would crash bot startup. No dedicated test:
  nothing observable changed to regress. Owner chose this over adding real
  `@username` support.

## Cross-cutting sweeps — clean beyond #2/#11/#12 above

UTF-16-vs-codepoint length, dict/set key collapsing, `zip()` strictness,
event-handler exception-wrapping consistency, `except Exception` near
checkpoint state, union type-hint handling, and blocking calls inside
`async def` were each swept project-wide (grep-driven, every hit judged
individually, cross-checked against this journal's existing invariants).
Nothing beyond #1/#2/#6/#8/#11/#12 survived — every other hit was either
already-safe by construction (e.g. `zip(idxs, files, strict=True)` in
`mirroring.py`, `_patch/sending.py`'s vendored `zip_longest`) or an
already-documented accepted trade-off (`edit_message`/`delete_message`'s
broad `except Exception`, both from pass 8).

An ad hoc `mypy` run (no type checker was previously configured for this
project — installed once into the venv just for this sweep, per the review
prompt's own instruction) surfaced ~90 diagnostics, almost all downstream of
one root cause: `telemirror/hints.py`'s `EventMessage = tl.patched.Message`
is a runtime alias Telethon doesn't expose as a proper static type, so mypy
treats every `EventMessage`-typed value as effectively `Any` and then
complains about attribute access on it throughout `mirroring.py`/
`messagefilters.py` — none of these are real bugs (traced several by hand:
`watermarkfilter.py:201`'s `bytes | None` assignment is immediately
`None`-checked before use; `config.py:393`'s `EmptyMessageFilter`/
`UrlMessageFilter` variable is a legitimate either-or, both implement the
same `MessageFilter` protocol; `storage.py`'s two "`__init__` must return
None" hits are a harmless `-> "ClassName"` return-annotation typo mypy
flags but Python never enforces). No genuine new finding from this run
beyond what the manual sweeps above already caught; setting up `mypy` for
real (fixing `hints.py`'s type alias, adding `no_implicit_optional`
suppressions for the vendored `_patch/sending.py`) would be a substantial,
unrequested effort out of this pass's scope.

## Deferred (P3, non-blocking)

- **#7** `past_mode.py`: on a resumed `full_history`/`since_date` run,
  `iter_total` stays the whole channel total instead of the remaining count
  while `processed` restarts at 0 — the progress/ETA log after a resume or
  flood-wait retry is misleading. Confirmed to feed only that log line, no
  retry/stop condition. Not fixed: correctly threading "already-mirrored
  count at resume" through `_replay_direction` is more machinery than a
  cosmetic log line warrants.
- **#12** `past_mode.py` (~line 586): the TECH_CHANNEL run-summary's
  `len(full) <= 4096` check is a Python codepoint count, not UTF-16 — same
  class of bug as #2, but on an internal admin-only message built mostly
  from channel IDs, practically unreachable. Not fixed.

## Reviewed, no change — raised with the project owner, explicitly declined

- **#9** No periodic reconciliation job exists for live-mode fan-out gaps
  left by a mid-broadcast `FloodWaitError` (documented trade-off, see
  `mirroring.py`'s Invariants above); the only recovery mechanism
  (`past_mode.py::_integrity_check`) is manually triggered
  (`telemirror-past-courses.service` has no `[Install]`/timer). Raised with
  the project owner per this pass's own instructions — not a bug, an
  architectural gap needing a product decision (added Telegram API load from
  a periodic full-history reconciliation vs. the current manual-recovery
  trade-off). Owner declined a periodic job — manual `past_mode.py` runs on
  request remain the sole recovery path. Not built.

## Pass 16 self-review — one encapsulation nit found and fixed

A dedicated re-read of this pass's own (still-uncommitted) diff, requested
explicitly by the project owner after the `/code-review ultra` cross-check
above. The production-code logic itself held up (re-traced `_reply_target_mirrors`,
the UTF-16 caption check, the `KeywordReplaceFilter` construction-time
validation, and `_edit_links_pass`'s per-mirror loop against their tests and
callers — no new correctness issue). One style nit surfaced:

- **NIT → fixed** `mirroring.py::EventHandlers.on_private_message`'s new
  `except` block reached across an object boundary into
  `self._processor._logger` — every other cross-reference to `_processor` in
  `EventHandlers` calls one of its public methods
  (`new_message`/`new_album`/`edit_message`/`delete_message`); this was the
  only place in the file reading another instance's single-underscore
  attribute directly. Added a `logger` read-only `@property` on
  `EventProcessor` and switched the callsite to `self._processor.logger`.
  `tests/test_on_private_message.py`'s `ProcessorStub` updated to expose
  `logger` instead of `_logger` to match. Not a behavior change — same
  logger object, same log line — full suite (315) and `ruff`/`pyflakes`
  re-confirmed green after the change.

## Independent cross-check — `/code-review ultra`

Run by the project owner per this pass's own instructions, over the whole
`master` branch (9 files changed, 469 insertions/47 deletions — this pass's
own not-yet-committed diff), review-only (no `--fix`). **Zero findings.**
Nothing to add to the findings list or push through the verify → fix
pipeline. One clean independent pass; per this journal's stop rule (two
consecutive full reads with no P1/P2 finding → module closed) this counts as
one of the two needed before the modules touched in this pass could be
considered re-closed — not a claim that the project is bug-free.

# Pass 17 — fan-out dedup + delete-purge scoping + flood-propagation contract sweep

Continuation of the ongoing audit: extracted the ~250-line duplication
between `new_message`/`new_album`'s per-target loop into three shared
`EventProcessor` helpers, then, while tracing their shared code paths,
found and fixed a premature-DB-purge bug in `delete_message` and a second
occurrence of pass 16's #1 "ambiguous mirror" bug (this time in the
`t.me` link-rewrite path rather than the reply-target path). A sweep of
every `except Exception`/generic catch touching a re-uploading filter or a
FloodWait-adjacent code path turned up two more instances of the
`documentfilenamefilter.py`/`watermarkfilter.py` FloodWait-swallowing
pattern pass 16 didn't cover, plus one `edit_message` fan-out abort bug.
Tests: 315 → 337, `ruff` clean.

## Fixed

- **P2** `mirroring.py::delete_message` — `delete_messages_batch` purges an
  `original_id`'s DB row by `(original_id, chat_id)` with no `mirror_channel`
  scoping, so it used to fire as soon as *any* one channel's Telegram delete
  in the current batch succeeded (`deleted_original_ids.add(...)` ran per
  successfully-queued channel, not per-original_id-fully-done). A channel
  that floods, that has no direction config (removed from `CHAT_MAPPING`),
  or that has `disable_delete=True` never gets its Telegram message removed
  but its DB tracking row silently vanished anyway — a still-live mirror
  permanently loses the one thing (`binding_id`) that lets it ever be edited,
  link-rewritten, pin-synced, or retried for deletion. Replaced the single
  `deleted_original_ids` set with `needed_channels_by_original` (every
  channel a DB row currently names for that `original_id`, gathered
  unconditionally before any config/disable_delete filtering) and
  `done_channels` (channels whose `delete_messages` call actually returned
  without raising); an `original_id` is purged only when its full channel
  set is a subset of `done_channels`. The purge call itself also got a
  `try`/`except` — a DB failure after a successful Telegram delete is now
  logged instead of raised (the message is already gone from Telegram
  either way, so the purge failure has nothing left to protect by
  propagating). Tests: `tests/test_delete_message_flood_flush.py` (partial
  flood purges only the fully-done original_id, a message needing the
  flooded channel is kept, a message needing an unconfigured channel is
  kept, a message needing a `disable_delete` channel is kept, a DB purge
  failure is logged and swallowed).
- **P2** `mirroring.py::__resolve_tg_link_rewrite` — same class of bug as
  pass 16's finding #1, in the sibling code path: a referenced message
  mirrored more than once into the same channel (reached via two
  topic-scoped `DirectionConfig`s matching the same source topic —
  `binding_id` has no topic column) could have its `t.me` link rewritten to
  an arbitrary one of those mirror ids instead of falling back to
  `fallback_link_url`. Fixed by routing both this method and
  `_reply_target_mirrors` through one extracted
  `EventProcessor._unambiguous_mirror_per_channel(mirrors)` (groups by
  `mirror_channel`, keeps only channels with exactly one mirror) instead of
  `_reply_target_mirrors` alone having pass 16's fix. Test:
  `tests/test_link_rewrite_cache.py::test_ambiguous_topic_mirrors_are_not_guessed`.
- **P2** `mirroring.py::edit_message` — `config.filters.process(...)` had no
  exception handling; a `FloodWaitError`/`FloodPremiumWaitError`/
  `MediaDownloadError` from a re-uploading filter (e.g.
  `DocumentFilenameFilter`, `WatermarkRemovalFilter`) propagated straight
  out of `edit_message`, aborting the edit for every other, un-flooded
  `outgoing_message`/config still left in the loop — with no compensating
  benefit, since neither `on_edit_message` nor `_sync_broadcast_channel`'s
  catch-up loop has a retry wrapper for it (unlike `new_message`/`new_album`,
  which `past_mode.py` replays). Wrapped in `try`/`except`, log-and-continue,
  matching the existing `except Exception` around `client.edit_message`
  itself a few lines below. Test:
  `tests/test_edit_delete_flood_propagates.py::test_edit_message_flood_from_filters_process_does_not_abort_the_others`.
- **P2** `messagefilters/documentfilenamefilter.py::DocumentFilenameFilter._process_message`
  and `messagefilters/watermarkfilter.py::WatermarkRemovalFilter._process_photo`/
  `_process_video` — a `FloodWaitError`/`FloodPremiumWaitError` raised by
  `download_media_with_retry` (deliberately left unretried there so it
  reaches `past_mode`'s own retry wrapper, per that function's own
  docstring) fell into each filter's generic `except Exception`, was logged,
  and the message was silently mirrored un-renamed / unwatermarked instead
  of being retried — the same class of contract violation
  `RestrictSavingContentBypassFilter` was already fixed against (referenced
  by this pass's own new tests). Added an explicit
  `except (errors.FloodWaitError, errors.FloodPremiumWaitError): raise`
  ahead of each generic handler, one per filter/media-kind. Tests:
  `tests/test_document_filename_filter.py::test_flood_during_rename_reupload_propagates`,
  `tests/test_watermark_flood_propagates.py::test_photo_flood_during_reupload_propagates`
  (video path shares the same code shape, covered by inspection, not a
  duplicate test).
- **P2** `telemirror/misc/topics.py::topic_id_of` — `reply_to.forum_topic`
  was accessed unconditionally; Telethon's `MessageReplyStoryHeader` (a
  reply to a Telegram Story) has no `forum_topic` field, so a story reply
  raised `AttributeError` out of `_matches_from_topic`, uncaught, wherever
  it's called from `new_message`/`new_album`'s per-target loop — losing the
  whole fan-out for that message, not just the story-reply handling. Changed
  to `getattr(reply_to, "forum_topic", False)`, so an unrecognized
  `reply_to` variant now resolves to the General topic like any other
  non-forum reply, instead of crashing. Test:
  `tests/test_matches_from_topic.py::test_reply_to_story_is_general_topic`.
- **P2** `skylon_set/sync_pins.py::SyncPair.to_topics` — `sorted(set(...))`
  over `topic_map.values()` raises `TypeError` (`'<' not supported between
  instances of 'NoneType' and 'int'`) the moment one donor→recipient pair
  combines a topic-scoped direction (`to_topic_id` = int) with a
  from-topic-only direction whose `to_topic_id` is `None` (mirrors the whole
  recipient chat) — a supported `CHAT_MAPPING` shape, not a hypothetical
  one. Filtered `None` out before sorting. Test:
  `tests/test_sync_pins_directions.py::test_mixed_topic_scoped_and_whole_chat_to_topics_does_not_raise`.
- **P3** `skylon_set/setup_mirrors.py::step_verify`/`step_final_verify` —
  both only ever looked at `direction["to"][0]`, silently ignoring every
  other recipient of a multi-recipient fan-out direction: `step_verify`'s
  dupe-detection missed known channel ids past the first, and
  `step_final_verify`'s channel-title/topic-title checks never verified (or
  offered to fix) recipient 2+ at all. Both now iterate every entry in
  `direction["to"]`. No dedicated test — this is an operational script with
  no existing test coverage (consistent with the rest of `skylon_set/*`'s
  fixes in this journal); verified by tracing `entity_cache`/`topic_cache`
  population (`get_topics` calls `get_entity` internally) to confirm the
  added per-recipient lookups are still cached correctly.

## Cleanup (no behavior change)

- `mirroring.py::new_message`/`new_album` — extracted the near-identical
  restricted-content-check, already-mirrored-skip, and reply-target-resolution
  blocks each duplicated between the two functions into
  `_restricted_content_blocks`, `_already_mirrored_skip`, and
  `_resolve_reply_target`. Covered directly by
  `tests/test_fanout_shared_helpers.py` in addition to the existing
  `new_message`/`new_album` integration tests continuing to pass unchanged.
- `mirroring.py::_send_message_with_caption_split`/
  `_send_album_with_caption_split` — removed the `try`/`except
  errors.MediaCaptionTooLongError` wrapper around
  `_send_with_reference_refresh`; both call sites' captions are already
  guaranteed short (the split already happened), and the `except` bodies'
  own comments said as much ("Can't actually happen … but keep the same
  catch-all contract"). Dead code, not a behavior change.
- `messagefilters/watermarkfilter.py::WatermarkRemovalFilter._process_message` —
  added a logged branch for `message.media` already being an
  `InputMediaUploadedPhoto`/`InputMediaUploadedDocument` handle (an earlier
  filter, e.g. `RestrictSavingContentBypassFilter`, already re-uploaded it,
  so there are no raw bytes left to watermark). The outcome is identical to
  before (the `if isinstance(...)`/`elif isinstance(...)` chain simply
  didn't match, `handle` stayed `None`, media passed through unwatermarked)
  — this only replaces a silent no-op with a visible one. Test:
  `tests/test_watermark_flood_propagates.py::test_already_reuploaded_media_is_left_alone_and_logged`.

## Pass 17 self-review — clean

A dedicated re-read of this pass's own diff before commit, same discipline
as passes 14–16: re-traced `delete_message`'s purge-scoping against all
four of its new tests by hand, re-checked exception ordering in both
message filters (`FloodWaitError` caught ahead of the generic handler in
every modified branch), confirmed the `_unambiguous_mirror_per_channel`
extraction preserves `_reply_target_mirrors`'s pass-16 behavior exactly
(same grouping, same "leave out rather than guess" rule, now shared with
the link-rewrite path), and confirmed `entity_cache`/`topic_cache` in
`setup_mirrors.py` are populated for every `to_id` the new per-recipient
loops visit. No new finding. Full suite (337) and `ruff` green.

# Pass 18 — independent `/code-review` of pass 17's commit, one bug found and fixed

Requested by the project owner immediately after pass 17's commit
(`71dcf42`) landed, before pushing: run the `code-review` skill (not
`ultra`) over `HEAD~1..HEAD` as a second, independent opinion on top of
pass 17's own self-review. It confirmed every pass-17 fix as correct and
surfaced one real bug — pre-existing, not introduced by pass 17, but living
in a function pass 17's own ambiguity fix touched.

## Found — real, pre-existing (confirmed present at `HEAD~1`, before pass 17)

`mirroring.py::__resolve_tg_link_rewrite` (pass 17's name — see below) chose
one arbitrary mirror for a referenced message's `t.me` link and returned a
single rewritten URL string, which `_try_rewrite_tg_link` then cached in
`link_cache` keyed by `(url, fallback_link_url)` — a key with no
`outgoing_chat` in it, even though `link_cache` is created once per source
event and shared across every fan-out target (`link_cache: dict = {}` at the
top of `new_message`/`new_album`, read inside the per-`outgoing_chat` loop).
So whenever a source channel fans out to two or more target channels
(the normal topology for this project — see the two-recipient config split
and "⚜️ Цитадель" batch mirroring) and a message links to another message
that's *also* mirrored into more than one of those same targets, only the
first-resolved target's mirror link ever got computed — every other
target's copy of the message received the **same** link, pointing at the
first target's mirror instead of its own. A reader on target B could end up
with a link into target A's channel, which may be private or otherwise
inaccessible to them. Pass 17's own ambiguity fix
(`_unambiguous_mirror_per_channel`) only addressed a narrower, different
ambiguity (the *same* channel reached via two topic-scoped configs); it
didn't touch this pick-one-arbitrary-target-and-cache-it-globally shape,
which predates pass 17 entirely (verified against `git show HEAD~1`).

## Fixed

- **P2** `mirroring.py` — split link resolution into two layers.
  `__resolve_tg_link_rewrite` is renamed `__resolve_tg_link_mirrors` and now
  returns `Optional[Dict[int, MirrorMessage]]` (one entry per *unambiguous*
  target channel, via the existing `_unambiguous_mirror_per_channel`) instead
  of picking a single mirror and building the final URL itself; `None` means
  "not a recognized/configured t.me link, leave every target's copy
  untouched" (the only case-independent-of-target outcome), otherwise a
  target missing from the returned map falls back to that target's own
  `fallback_link_url`. `_try_rewrite_tg_link` gained an `outgoing_chat`
  parameter and now looks up its own entry in the resolved map, so each
  fan-out target gets its *own* mirror link. `link_cache` is keyed by `url`
  alone now (simpler than before, since the per-target/per-fallback work
  moved out of the cached path) — still one DB round-trip per event
  regardless of fan-out width, confirmed by
  `tests/test_link_rewrite_cache.py::test_link_resolution_is_cached_across_fanout`
  continuing to pass unchanged. `_rewrite_links` and both its
  `new_message`/`new_album` call sites, plus the one call site in
  `past_mode.py::_edit_links_pass` (passes `target_id`, the single mirror
  target that pass's `EventProcessor` is scoped to), now thread
  `outgoing_chat` through. Test:
  `tests/test_link_rewrite_cache.py::test_each_fanout_target_gets_its_own_mirror_link`
  (a source message mirrored into two different target channels, each
  linking to the same referenced message which is itself mirrored into both
  targets; confirmed each target's link now resolves to its own mirror,
  not the other target's).

## Pass 18 self-review — clean

Re-read the fix's own diff before commit: traced the `None`-vs-`{}` sentinel
split (`None` = "don't rewrite, ignore fallback"; `{}`/partial map = "rewrite
per-target, falling back per-target") against every one of
`__resolve_tg_link_mirrors`'s four return points, confirmed no other caller
of the renamed method or of `_rewrite_links`/`_try_rewrite_tg_link` was
missed (`past_mode.py`'s call site was caught this way — it broke 3 tests on
the first run, since it hadn't been updated to pass `outgoing_chat`; fixed
by passing `target_id`, the pair's single scoped target). Full suite
(337 → 338) and `ruff` green.

## Independent cross-check — `/code-review` (high, non-ultra)

Run by the project owner over `HEAD~1..HEAD` (this pass's own commit,
`c52d2c7`) after it landed, before pushing — a second opinion independent of
this pass's own self-review above, same discipline as pass 16's `ultra`
cross-check but at the smaller `code-review` scope. Manually traced every
changed function and call site, the `None`-vs-empty-dict branch semantics,
and the `past_mode.py` `chat_mapping` interaction, plus a separate
fresh-context agent pass with no shared history. **Zero findings** — nothing
to add to this pass's fix list.

# Pass 19 — whole-project production-readiness audit + mypy enabled in CI

Requested by the project owner: a fresh whole-project review and a verdict on
production readiness. Rather than re-reading ~10k lines this journal had
already closed pass after pass, this pass verified the journal's claims
against the current `HEAD` (full test suite + `ruff` green) and covered
ground the correctness-focused checklist above doesn't: deployment
(`Dockerfile`, `docker-compose.yaml`, `deploy/systemd/*`), secrets handling
(`.env` permissions/exclusion), and injection surfaces (SQL — all
parameterized; `subprocess` calls — list-args, no `shell=True`, no untrusted
input in `ffmpeg`/`ffmpeg`-adjacent commands). No new correctness finding;
the existing deploy/CI setup was already sound.

One deferred item from pass 7/8 (`telemirror/mirroring.py`'s "Deferred"
section, "not re-verified against Telethon's actual update-buffering
behaviour") was flagged in the initial verdict as still open — that was
stale: pass 11 (`aac5bf8`) had already investigated and fixed it (reordered
`EventHandlers` construction before `_sync_broadcast_channel`, see Batch B
there). No action needed; noted here only to correct the record.

## `mypy` — enabled as a blocking CI step

The owner asked to add `mypy` to CI, then, on discovering the scope, to fix
the pre-existing debt rather than run it non-blocking. Baseline: 213 raw
errors, 111 after excluding missing-stub noise for `telethon`/`yaml`
(`ignore_missing_imports = true`, `pyproject.toml`). Fixed down to 0:

- `telemirror/storage.py::Database` — changed base class from `Protocol` to
  `ABC`. Both `InMemoryDatabase`/`PostgresDatabase` already used it via
  nominal inheritance only (no structural/duck typing anywhere in the
  codebase relies on `Protocol`'s special behavior), and mypy has a known
  false-positive with `Protocol` subclasses: a concrete (non-abstract) method
  with a trivial body (docstring only) was misidentified as still abstract,
  making mypy claim `InMemoryDatabase`/`PostgresDatabase` couldn't be
  instantiated — confirmed a false positive by a minimal repro (`ABC`: clean;
  `Protocol`: same error) and by runtime instantiation succeeding either way.
  `Database.close`'s empty body then needed `# noqa: B027` (ruff's bugbear
  check for the same "empty method, no `@abstractmethod`" shape — here
  intentional, it's a no-op default hook).
- `telemirror/hints.py::EventMessage` — `tl.patched.Message` (telethon has no
  `py.typed` marker) needed an explicit `TypeAlias` annotation for mypy to
  treat it as a type rather than an ambiguous variable; this alone resolved
  most of the `mirroring.py`/`messagefilters.py` `EventMessage? has no
  attribute` errors downstream.
- `telemirror/mirroring.py::Mirroring.__init__` — the `logger:
  Union[str, Logger]` parameter was passed straight through to
  `EventProcessor(logger=...)` (which correctly expects a plain `Logger`)
  without narrowing; `Telemirror.__init__` already had the
  str-name-or-Logger-or-None → `Logger` resolution snippet, just one layer
  up. Initially copied verbatim into `Mirroring` (same-shape fix, not a
  behavior change: every real caller only ever reaches `Mirroring` via
  `Telemirror`, which had already resolved it) — then, per a `/code-review`
  pass over this pass's own diff (below), extracted into a shared
  module-level `_resolve_logger` helper used by both constructors instead.
- `implicit-Optional` params (`x: int = None` instead of `Optional[int] =
  None`) in `main.py`, `telemirror/mirroring.py` — mechanical, no behavior
  change.
- `past_mode.py` — `pm = cfgs[0].past_mode` and `cfg.past_mode` are typed
  `Optional[PastModeConfig]` on `DirectionConfig`, but both call sites
  (`_replay_direction`, `_edit_links_pass`) only ever see `cfgs`/`pairs`
  pre-filtered to `past_mode is not None` (`_run`'s `pm_cfgs` list-comp) —
  added `assert ... is not None` at each site to encode that invariant for
  mypy; no `assert` existed anywhere in this codebase before, but it's the
  standard idiom for this exact situation and there was no established
  alternative to match.
- `telemirror/mirroring.py::EventHandlers.edit_message` — `filtered_message`
  from `config.filters.process(...)` is typed
  `EventMessage | EventAlbumMessage` (the general `process()` signature
  shared with the album path), but this call site always passes a single
  message, never a list. `assert not isinstance(filtered_message, list)`
  narrows it back to a single message for the rest of the block.
- `telemirror/mirroring.py::event_message_link` — three branches each
  re-annotated `incoming_message_id: int` (mypy treats repeated annotations
  as a redefinition error); annotated once above the `if`/`elif`/`else`
  instead. `_send_media_group_caption_fallback`'s `safe_entities = []` got an
  explicit `List[List[types.TypeMessageEntity]]` annotation (mypy couldn't
  infer the element type across the two append sites, one of them `[]`).
- `telemirror/mirroring.py::_sync_broadcast_channel` — `bc =
  self._broadcast_channel` is `Optional[int]`; every caller only invokes this
  method inside `if self._broadcast_channel:`, a guarantee mypy can't see
  across the method boundary. Added the same `assert bc is not None` idiom.
- `telemirror/messagefilters/base.py::MessageFilter.process` —
  `isinstance(entity, EventMessage)` where `EventMessage` resolves to `Any`
  (no telethon stubs) is a `mypy` error class of its own
  (`Cannot use isinstance() with Any type`) distinct from the `TypeAlias` fix
  above; silenced with `# type: ignore[misc]` — an actual stub gap, not
  fixable from this side.
- `telemirror/watermark/processor.py` — `Image.LANCZOS` → `Image.Resampling.
  LANCZOS` (the pre-Pillow-9.1 alias still works at runtime but current
  stubs don't declare it — switched to the non-deprecated form, a genuine
  cleanup, not just a type-checker workaround). `cv2.normalize(mag, None,
  ...)` (`dst=None`, valid OpenCV usage for auto-allocated output) isn't
  covered by the bundled stubs' overloads — `# type: ignore[call-overload]`.
- `telemirror/messagefilters/watermarkfilter.py::WatermarkRemovalFilter.__init__`
  — `**config: object` couldn't satisfy `WatermarkConfig`'s typed
  (`str`/`float`/`int`/`bool`) fields when unpacked; changed to `**config:
  Any` (these kwargs are always loosely-typed, YAML-config-driven values by
  design — `object` was never actually enforcing anything real here).
  `_process_photo`'s `output` variable held `bytes` on one branch and
  `Optional[bytes]` on the other (mypy infers a variable's type from its
  first assignment); added an explicit `output: Optional[bytes]` annotation
  above the `if`.
- `config.py` — `message_filter` assigned `UrlMessageFilter(...)` in one
  branch, `EmptyMessageFilter()` in the other (same first-assignment
  inference issue); annotated `message_filter: MessageFilter` above the
  `if`.
- `telemirror/storage.py::InMemoryDatabase.__init__` /
  `PostgresDatabase.__init__` — both were annotated `-> "InMemoryDatabase"` /
  `-> "PostgresDatabase"` instead of `-> None` (copy-paste from the
  `_async__init__`/`__await__` factory pattern next to them, which
  legitimately returns `self`) — `__init__` must return `None`; harmless at
  runtime (the annotation is never checked there) but wrong, and it's what
  produced the "missing return statement" / "return type must be None"
  errors. Fixed both to `-> None`.

`telemirror/_patch/*` (vendored Telethon fork, kept close to upstream —
already exempted from `ruff`'s B/PIE/C4 in `pyproject.toml`) is exempted the
same way for `mypy` (`ignore_errors = true` override), consistent with the
existing policy of not touching that code to satisfy local lint/type
preferences.

Full suite (338) and `ruff` green throughout; `mypy .` clean at 0 errors.
`python -m mypy .` added as a blocking step in `.github/workflows/ci.yml`,
`mypy==2.3.1` pinned in `requirements-dev.txt` (matching the version already
installed and exercised in `.venv` during this pass).

## Pass 19 self-review — `/code-review` over this pass's own diff, one dedup fixed

Requested by the project owner immediately after the pass landed (before
committing) — same discipline as pass 18's independent cross-check. One
finding, not a bug: the logger str/None → `Logger` resolution snippet
(3 lines) was duplicated verbatim between `Mirroring.__init__` and
`Telemirror.__init__` rather than shared, introduced by this pass itself
when narrowing the type. Fixed by extracting a module-level
`_resolve_logger(logger) -> logging.Logger` helper, used by both. Full
suite (338), `ruff`, and `mypy .` re-verified green after the fix.

# Pass 20 — whole-project review, two bugs + three P3 fixed

Requested by the project owner: a whole-project code review per `CLAUDE.md`,
with every suspected bug re-verified (intended vs. real) before a verdict,
then "fix everything". Baseline at `0ddb56a`: 433 tests, `ruff`, `mypy` green.
Each fix below has a regression test confirmed to fail on the pre-fix code.

## Fixed

- **P2** `past_mode.py::_integrity_check` rolled the checkpoint forward to the
  highest mirrored `original_id` of the pair. Rows past the checkpoint also
  come from the live mirror (`main.py`) running between two past_mode runs:
  a backfill interrupted at 50, then a live post 9000 mirrored, made the next
  resume jump to 9000 and silently skip 51..8999 (only a stdout WARNING).
  This also contradicted README ("re-running resumes from where it left
  off") and pass 16's #9 (past_mode as the manual recovery path for live
  gaps — it jumped over them). The roll-forward is redundant with
  `new_message`/`new_album`'s per-target `already_mirrored` dedup, so it was
  removed. Cost: a resume now also walks already-mirrored messages past the
  checkpoint — one `get_messages` DB lookup each, ~1 `iter_messages` request
  per 100, and the `pm.send_delay` sleep (0.5s default) in
  `process_single`/`process_album`, which dominates (~17 min per 2 000
  live-mirrored posts). `telemirror-past-courses.service` is unaffected (0
  channel pairs shared with `mirror.config.yml`). Tests:
  `tests/test_past_mode.py::test_integrity_keeps_checkpoint_below_max_mirrored`
  (replaces `..._rolls_back_stale_checkpoint`),
  `::test_integrity_does_not_skip_history_after_live_mirror_ran`.
- **P2** `skylon_set/clear_channels.py::_reset_db_state` wiped `binding_id` and
  checkpoints but not `broadcast_sync`, so after clearing broadcast targets
  every admin post stayed marked synced and the next startup sync sent
  nothing back. Owner's choice: reset `broadcast_sync` for `BROADCAST_CHANNEL`
  when any cleared channel is one of its targets (reusing
  `get_broadcast_sync`/`delete_broadcast_sync`, no `Database` change), **and**
  drop `_sync_broadcast_channel`'s seed-from-`binding_id` step — with the seed,
  a partial clear would re-mark a post synced as soon as any untouched target
  still held it. `Database.get_all_messages_for_channel` (+ both
  implementations) was only used by that seed and was removed as orphaned by
  this change; its prefix-exactness test now covers
  `get_messages_for_channel_pair`, which shares the same key-prefix logic.
  Tests: `tests/test_broadcast_sync.py::test_empty_broadcast_sync_is_not_seeded_from_existing_mirrors`,
  `::test_cleared_target_gets_broadcast_posts_back_other_target_is_skipped`
  (real `EventProcessor`), `tests/test_clear_channels.py::test_reset_db_state_resets_broadcast_sync_only_for_broadcast_targets`.
- **P3** `config.py`: `build_filters` for a direction's own `filters:` ran
  inside the source × target loop, so each pair got its own filter instance
  (and `ReuploadCache` — the same media downloaded/re-encoded per target).
  Built once per direction now; `_media.py::ReuploadCache` docstring aligned.
  Not triggered by the deployed configs (no direction-level `filters:`).
  Test: `tests/test_config.py::test_direction_level_filters_are_built_once_per_direction`
  (subprocess — `config.py` builds `CHAT_MAPPING` at import).
- **P3** `mirroring.py::EventProcessor.edit_message`: a FloodWait from the
  filter chain still fell through to the next sibling config immediately —
  the same account-wide-flood reasoning `0ddb56a` applied to the edit send.
  Now logs and gives up on that mirror message. Test:
  `tests/test_edit_delete_flood_propagates.py::test_edit_message_flood_from_filters_process_skips_sibling_configs`.
- **P3** `telemirror/health.py`: `ActiveState=failed` (and, via the "not
  active twice in a row" rule, a second wording of it) was re-alerted every
  10 minutes while the unit stayed failed, on top of `OnFailure=`'s alert.
  Owner's choice: alert only on the transition into `failed`; `failed` now
  counts as settled for the stuck-unit rule. Test:
  `tests/test_health.py::test_failed_state_alerts_only_once`.

## Re-verified, intended — no change

- `DocumentFilenameFilter` mutating a cached re-upload handle's filename
  attribute in place: `_rename` is idempotent and media is deep-copied per
  target.
- `edit_message`'s `fetch_fresh_media(…, message.id)` returning a single
  media: the return shape mirrors `ids`.
- Watchdog fail streak (3) vs. `WatchdogSec=600`, and the `/tmp` cron's
  `-mmin +180` vs. real encode budgets.

Full suite 433 → 440, `ruff` and `mypy .` green.

## Pass 20 self-review — one regression from this pass found and fixed, plus a compose DSN fix

A second whole-project review, requested by the owner before commit, covered
this pass's own diff line by line, plus the files the first read only skimmed
(`Dockerfile`, `docker-compose.yaml`, CI, `install.sh`, `setup-swap.sh`,
`setup_mirrors.py`'s config writers).

- **P2, regression introduced by this pass (fixed).** Dropping the
  `broadcast_sync` seed left `EventProcessor._already_mirrored_skip` as the
  only guard against a repeat send, and its legacy fallback kept
  `(channel, None, None)` rows in a **set**: N untagged rows collapsed into one
  key that could justify skipping only one config per channel. The broadcast
  channel shipped on 2026-09-11 but `mirror_topic_id` only on 2026-09-17, so
  posts from that window have one untagged row per topic of every forum
  target. When `clear_channels.py` reset `broadcast_sync` while a forum
  broadcast target was not cleared (its purge failed), the next startup sync
  re-sent those posts into every topic of that forum but one. Reproduced
  (2 legacy rows, topic configs 10 and 20 → a repeat send to topic 20).
  Fixed by counting instead of collapsing: `already_mirrored` is a
  `collections.Counter` in `new_message`/`new_album`, and each untagged row
  covers exactly one config (N rows → up to N skips). Exact-key matches stay
  non-consuming, as before. This also closes the same shape in live
  redelivery and past_mode dedup. Tests:
  `tests/test_broadcast_sync.py::test_empty_sync_does_not_duplicate_into_uncleared_forum_with_legacy_rows`
  (fails before the fix), and
  `tests/test_fanout_shared_helpers.py::test_already_mirrored_skip_two_legacy_rows_cover_two_configs`.
  The existing helper tests now pass a `Counter`, with unchanged expectations.
- **P3 (fixed).** `docker-compose.yaml` set a raw
  `DATABASE_URL: postgres://${DB_USER}:${DB_PASS}@postgres/${DB_NAME}`, which
  bypassed `config.build_dsn`'s percent-encoding. Confirmed with psycopg's
  `conninfo_to_dict`: password `p@ss/w#rd` parses as `password='p'`,
  `host='ss'`. It now sets `DB_HOST: postgres`, which overrides the `.env`
  value, so `build_dsn` assembles the DSN. Production (systemd + `.env` with
  `DB_*`) is unaffected.

Re-verified, no change: the `#1 → #1` directions in both configs are forum
General topics (every such recipient also has other topics); the non-forum
supergroup branch of `setup_mirrors.step_build_config` doesn't occur in
either config. `_append_directions_text` is guarded (`directions:` must be
the last top-level key, `.bak` copy).

Full suite 440 → 442, `ruff` and `mypy .` green.

## Pass 20 follow-up — vendored `_patch` read in full, two `parse_mode` bugs fixed

A further review pass on an unchanged tree read the one production module never
read end to end: the vendored `telemirror/_patch/sending.py` (synced with
Telethon 1.40, installed 1.44), traced against how `mirroring.py` calls it.
Both findings were reproduced on a real `TelegramClient` with the outgoing
request intercepted (no network).

- **P2 (fixed)** `EventProcessor._send_tail_text` sent a split caption tail
  with `formatting_entities=entities`, which is `None` when the >1024-char
  caption of a single message had no formatting. The patched `send_message`
  then runs a string through the client's `parse_mode` — `"markdown"`, set
  project-wide by `build_telegram_client`. Repro: `"snake__case_var and
  **2**x [a](b)"` was sent as `"snake__case_var and 2x a"` with a Bold entity
  and a hidden link to `b`. This is not intended: the code deliberately sends
  raw text plus explicit entities to avoid double-parsing (Telethon #3065,
  `new_album`), and the patch passes `parse_mode=None` "to force using even
  empty formatting_entities". Albums were unaffected (entities always `[]`).
  Fixed with `formatting_entities=entities or []`. Test:
  `tests/test_caption_too_long_split.py::test_tail_text_without_entities_is_not_markdown_parsed`
  — the existing split tests stub `send_message` and could not see this.
- **P3 (fixed)** `EventHandlers.on_private_message` sent the sanitised but
  sender-controlled display name to TECH_CHANNEL through the same markdown
  parse. A sender named `[Support](https://evil.example)` rendered as
  "Support" with a hidden link. `TelegramLogHandler._do_send` has the same
  class of problem: log text is never authored as markdown, so `__`/`**`/`[..](..)`
  in exception messages or paths were mangled. Both now pass
  `parse_mode=None`, as `telemirror/alert.py` already did. `past_mode.py`'s
  final summary is left as is: it uses backticks deliberately. Tests:
  `tests/test_on_private_message.py::test_sender_name_is_not_markdown_parsed`,
  `tests/test_log_handler.py::test_do_send_disables_markdown_parsing`. The
  fakes' `send_message` now accept `**kw`.

Re-verified, no change:
- the watermark / restrict-saving `InputFile` handles (`photo.jpg`) resolve to
  `InputMediaUploadedPhoto` in both the single-message and album paths
  (`utils.is_image` on the file name);
- `InputMediaUploadedDocument` in an album goes through `UploadMediaRequest`
  with its attributes intact;
- album captions are never parsed (a list of per-item entity lists is always
  truthy);
- no divergence between the 1.40-synced patch and installed Telethon 1.44 in
  any code path used here.

Full suite 442 → 445, `ruff` and `mypy .` green.

## Pass 20 follow-up 2 — mirrored edits were markdown-parsed

The next review pass swept every send/edit call site outside the vendored patch
for the same bug class as `_send_tail_text` above: text passed with `None`
entities goes through the client's markdown `parse_mode`.

- **P2 (fixed)** `EventProcessor.edit_message` edits the mirror through the
  *unpatched* `client.edit_message(text=…, formatting_entities=filtered_message.entities)`.
  For a source message with no formatting, `entities` is `None`, and
  Telethon 1.44 (`telethon/client/messages.py`, `edit_message`: `if
  formatting_entities is None: text, formatting_entities = await
  self._parse_message_text(text, parse_mode)`) then parses the text as
  markdown. Reproduced on a real `EventProcessor` + `TelegramClient`, with
  the request intercepted: `"snake__case and **2**x [a](b)"` was sent in the
  `EditMessageRequest` as `"snake__case and 2x a"` with Bold and a hidden
  link. `disable_edit: false` is set globally in `mirror.config.yml`, so any
  source edit of an unformatted post containing `**`, `__`, backticks or
  `[..](..)` corrupted the mirror. It is not intended for the same reason as
  `_send_tail_text` (raw text + explicit entities, Telethon #3065). New-message
  sends were never affected: the patched `send_message` doesn't parse a
  `Message` object. Fixed with `formatting_entities=filtered_message.entities
  or []`. Test: `tests/test_edit_message_markdown.py::test_edit_without_entities_is_not_markdown_parsed`
  (fails before the fix).

Re-verified, no change: `past_mode._edit_links_pass` only edits messages that
carry URL entities (never `None`); `_notify_skipped` sends a plain `t.me/c/…`
link; the past_mode final summary uses backticks on purpose; `alert.py`,
`TelegramLogHandler` and `on_private_message` already pass `parse_mode=None`.

Full suite 445 → 446, `ruff` and `mypy .` green.

## Pass 20 follow-up 3 — entity-offset fuzzing, one latent KeywordReplaceFilter fix

The next pass on an unchanged tree checked the code that shifts entity offsets
when text changes. It used property-based fuzzing rather than reading: random
texts with emoji, surrogate pairs, Cyrillic and nested entities, checked
against an independent oracle.

- `KeywordReplaceFilter`, 20 000 cases (plain and `r'…'` rules, group
  references, empty replacements). Invariant: an entity not touched by any
  match covers the same text afterwards, and no entity goes out of bounds.
  Clean.
- `EventProcessor._rewrite_links` (live, copy mode), 8 000 cases mixing
  mirrored and unmirrored `t.me/c/…` links. The text matches the oracle; URL
  entities cover the rewritten links; bold entities that are disjoint from a
  link, or contain it whole, stay correct. Clean. An entity covering *part* of
  a link is trimmed/resized by `update_entities_params`' documented rules,
  which is intended.

- **P3, latent (fixed)** `KeywordReplaceFilter._apply_rule` computed the
  entity shift from `match.expand(replacement)` *before* the case transfer
  (`.lower()`/`.title()`/`.upper()`), so a case transfer that changes the
  string length misaligned every later entity. Repro: rule `{"foo":
  "straße"}` on `"FOO tail"` with Bold over `tail` → `"STRASSE tail"` with
  Bold over `' tai'`. The final (case-transferred) string is now computed
  first and the shift is taken from its length. The filter is not used in
  either live config (only `mirror.config.yml-example`), and Cyrillic case
  mapping is length-preserving, so it never fired in production. Test:
  `tests/test_keyword_replace_filter.py::test_case_transfer_that_changes_length_keeps_entities_aligned`
  (fails before the fix); the fuzz still reports 0 violations.

Full suite 446 → 447, `ruff` and `mypy .` green.

## Pass 20 follow-up 4 — remaining filters fuzzed; one latent fix, two live filter gaps closed

This pass on an unchanged tree fuzzed or probed the filters not yet covered.

Clean:
- `DocumentFilenameFilter._rename` with the live settings (`suffix:
  "@CitadelClan"`, `remove: [@openfrm, openfrm]`), 50 000 generated names: it
  is idempotent (the cached-handle re-rename depends on this). `openfrm` only
  survives after the last dot, i.e. in the extension, which is intentionally
  untouched.
- `UrlMessageFilter`, 10 000 cases: untouched entities stay aligned and in
  bounds, and blacklisted URLs are always redacted.

Fixed:
- **P3, latent** `ForwardFormatFilter._process_message` computed
  `message_offset` with `str.find` (code points), while Telegram entity
  offsets are UTF-16 units. Every astral emoji (🚀, 😀) in the header before
  `{message_text}` shifted all body entities by one. Repro: channel
  `🚀 Crypto`, format `{channel_name}\n{message_text}` → Bold `hi` covered
  `'\nh'`. The default format (body first) and `⚜️ Цитадель` (BMP) were
  unaffected, and the filter is unused in live configs. The offset is now
  measured with `utils.add_surrogate`. Test:
  `tests/test_forward_format_filter.py::test_astral_emoji_in_header_keeps_body_entities_aligned`.
- **Live gap, `SkipWithUrlFilter`** (owner's choice: normalize in code). Hidden
  links `https://telegram.me/godolympbot` and `tg://resolve?domain=godolympbot`
  bypassed the `t.me/…` blacklist, though they reach the same chat. `_normalize`
  now folds `telegram.me` / `telegram.dog` / `www.t.me` hosts and `tg://resolve`
  deep links into the `t.me/…` form, for blacklist entries and checked URLs
  alike. Configs are unchanged. Test:
  `tests/test_url_filters.py::test_skip_with_url_filter_matches_telegram_link_aliases`
  (8 cases, including negatives such as `nottelegram.me` and a longer username).
- **Live gap, `SkipWithKeywordsFilter`** (owner's choice: one regex). The
  whole-word rule `Олимп` missed the case forms (`Олимпа`, `в олимпе`, …). In
  both `mirror.config.yml` and `citadel_courses.config.yml` it is replaced by
  `r'\bолимп(?:а|у|ом|е)?\b'`, which covers Олимп/Олимпа/Олимпу/Олимпом/Олимпе
  in any case but not «олимпиада» / «олимпийский» (a broad `олимп\w*` was
  rejected for those false positives). YAML loading was verified to keep
  `\b` literal, and both real configs were probed end to end. Test:
  `tests/test_keyword_replace_filter.py::test_olimp_rule_catches_case_forms_not_derived_words`.
  The config change takes effect on the next `telemirror.service` restart.

Full suite 447 → 463, `ruff` and `mypy .` green.

## Pass 20 follow-up 5 — SkipWithUrlFilter link normalization completed

The next pass probed the URL normalization added in follow-up 4.

- **P3, regression in follow-up 4 (fixed)** `SkipWithUrlFilter._normalize`
  folded `tg://resolve?domain=X` only when `domain` was the first parameter and
  nothing but `&…` followed. `tg://resolve?start=x&domain=godolympbot` and
  `tg://resolve?domain=godolympbot#frag` still bypassed the blacklist,
  contradicting the docstring's unqualified claim. The query is now parsed
  with `urllib.parse.parse_qsl` (order-independent, fragment dropped).
- **Gaps in the same category (closed)** Two more forms open the same chat as
  `t.me/<name>` and bypassed a `t.me/<name>` entry: the `t.me/s/<name>[/…]`
  public-channel web preview and the `<name>.t.me[/…]` username subdomain.
  Both are now folded into `t.me/<name>[/…]`. The subdomain rule runs after
  `www.` is stripped and needs `.t.me` directly after one label, so
  `x.nott.me` and `a.b.t.me` are untouched.

Test: `tests/test_url_filters.py::test_skip_with_url_filter_folds_all_chat_link_forms`
— 6 DISCARD cases (all failed before the fix) and 5 CONTINUE negatives
(`t.me/iv?…`, `x.nott.me`, a longer subdomain name, `tg://resolve` without
`domain`, `t.me/s/other`). Both real configs were probed with every form.
Configs are unchanged.

Full suite 463 → 474, `ruff` and `mypy .` green.

## Pass 20 follow-up 6 — `<name>.t.me?…` / fragments; property test added to the suite

The next pass ran a property check over `SkipWithUrlFilter._normalize`:
20 000 random names × tails, requiring every link form to normalize exactly
like `t.me/<name>` with the same tail.

- **P3, regression in follow-up 5 (fixed)** The `<name>.t.me` subdomain rule's
  lookahead `(?=/|$)` did not fold a query directly after the host.
  `https://godolympbot.t.me?start=ref` — the typical bot-promo form — passed
  the filter, while `…t.me/?start=ref` and `t.me/godolympbot?start=ref` were
  dropped, even though the docstring promises the subdomain form is folded.
  Both host rules now use `(?=[/?]|$)`.
- **Pre-existing gap (closed)** `_matches` accepts only `==`, `b/` and `b?`,
  so any link with a `#fragment` right after the name (`t.me/godolympbot#x`)
  was never matched. `_normalize` now drops the fragment up front (it never
  changes the target chat), which also replaces the tg:// branch's own
  fragment handling.

Test: `tests/test_url_filters.py::test_skip_with_url_filter_every_form_normalizes_like_t_me`.
It is a deterministic property test over 9 tails × 2 names × every form
(`t.me`, `https`, `HTTP://www.`, `telegram.me`, `telegram.dog`, `t.me/s/`,
`<name>.t.me`, `tg://resolve`). It checks that each form normalizes like
`t.me/<name>{tail}`, that normalization is idempotent, and that an alias-form
blacklist entry matches every form but not a longer name. The `?start=1` / `#x`
cases failed before the fix. With this test in the suite, a future
normalization change is checked across every form at once — the previous two
follow-ups each fixed one form and missed another. The 20 000-case scratch
run and both real configs were re-probed: clean.

Full suite 474 → 492, `ruff` and `mypy .` green.

# Pass 21 — whole-project review; one live bug, four P3, sticker hardening

Requested by the project owner: a whole-project code review per `CLAUDE.md`,
with every suspected bug re-verified (intended vs. real) before a verdict,
then "fix everything in the best way". Baseline at `8497e7d`: 492 tests,
`pyflakes`, `ruff`, `mypy` green. Each fix below has a regression test
confirmed to fail on the pre-fix code.

## Fixed

- **P2, live** `watermark/processor.py`: a video with an odd width or height
  was never stamped — libx264 with `-pix_fmt yuv420p` refuses it ("width not
  divisible by 2"), so `stamp_watermark_on_video` returned False and the video
  was mirrored unstamped with an ERROR in the tech channel. Repro: a real
  853×481 clip. The delogo path (`remove_watermark_from_video`) failed the
  same way. Both filtergraphs now end in
  `crop=trunc(iw/2)*2:trunc(ih/2)*2`: no resampling, a no-op on an even frame,
  and it drops the stray edge pixel of an odd one. Tests:
  `tests/test_watermark_video_encode.py::test_stamp_handles_odd_frame_dimensions`,
  `::test_delogo_handles_odd_frame_dimensions` (real ffmpeg, skipped without it).
- **P3** `past_mode.py::_edit_links_pass` compared the rewritten text with the
  *source*, not with the mirror. Every mirror whose link was already resolved
  at send time (the common case: history is replayed in order) got an
  identical edit on every run. Each one cost an edit request with no
  `send_delay` after the resulting `MessageNotModifiedError`, plus a WARNING.
  Repro: `new_message` for 7, then for 10 (linking to 7); the pass then
  re-sent 10's exact content. The pass now fetches each batch's mirrors (one
  `get_messages` per ≤100) and edits only a mirror whose text/entities
  differ. Deleted mirrors are skipped. A mirror sent through the caption-split
  fallback (media with an empty caption, text >1024 UTF-16 units) is skipped
  too: its caption can't hold the text. The cheap "does rewriting change any link at all" pre-check
  is kept, so messages with only foreign links cost no mirror fetch. Tests:
  `tests/test_past_mode.py::test_edit_links_pass_skips_mirror_that_already_has_the_link`,
  `::test_edit_links_pass_skips_split_caption_mirror`.
- **P3, latent** Same pass: the edit carried the raw source text and bypassed
  the direction's filters, so it reverted text filters. Repro:
  `KeywordReplaceFilter({"see": "look"})` — the mirror got "look", and the pass
  edited it back to "see". The edit is now built like `new_message` builds the
  mirror: rewrite links, then `cfg.filters.process(..., NewMessage.Event)`, with
  `media` dropped first. Only text is edited, and every re-uploading filter is
  a no-op without media, so nothing is downloaded. DISCARD skips the mirror.
  Neither live config has a text filter. Tests:
  `::test_edit_links_pass_keeps_text_filter_output`,
  `::test_edit_links_pass_respects_a_discarding_filter`.
- **P3, latent** `ForwardFormatFilter`: a header entity that contains
  `{message_text}` kept the placeholder's 14-unit length. `**{message_text}**`
  bolded `'hello world\n\nf'`, and `__Note: {message_text}__` cut a long body
  short. The filter now uses the shared `UpdateEntitiesParams` mixin, which
  shifts entities after the placeholder and resizes the ones containing it.
  Unused in live configs. Tests:
  `tests/test_forward_format_filter.py::test_header_entity_wrapping_the_body_is_resized`
  (3 cases), `::test_header_entity_after_the_body_still_shifts`.
- **P3** `mirroring.py::edit_message`: a mirror sent through the caption-split
  fallback (source caption >1024) failed every edit of its source with
  `MediaCaptionTooLongError` → an ERROR in the tech channel, and a media change
  in that edit was lost. `_do_edit` now re-reads the mirror and retries once
  with the caption the mirror already holds (empty for a split mirror), so the
  media still updates, and logs a WARNING that the text wasn't updated. Both call sites (primary and
  file_reference-refresh retry) get it. Test:
  `tests/test_edit_message_caption_split.py`.

## Hardening — media-like documents

The next two can't be confirmed offline: they depend on the shape of
Telegram's sticker documents. Both fixes are correct whichever shape
Telegram uses.

- `WatermarkRemovalFilter`: a video sticker (webm with alpha that carries
  `DocumentAttributeVideo`) was re-encoded to H.264/MP4, which has no alpha,
  and still declared a `video/webm` sticker (reproduced locally with a real
  VP9-alpha webm). Documents with `DocumentAttributeSticker` now pass through.
  Separately, a stamped video is now declared `video/mp4` and gets a `.mp4`
  filename (on copied attributes), because ffmpeg always writes MP4. A
  .webm/.mkv source used to keep its old container label. Tests:
  `tests/test_watermark_stamp_only.py::test_video_sticker_is_not_stamped`,
  `::test_stamped_webm_is_declared_as_mp4`.
- `DocumentFilenameFilter`'s docstring promised that stickers, voice notes
  and GIFs pass through "having no filename". Telegram does attach one to
  some of them (e.g. `sticker.webp`), and each such document was downloaded
  and re-uploaded under a renamed file. The filter now decides by kind
  (`_is_media_like`: sticker, animated/GIF, voice, round video), in both the
  raw and the already-uploaded branch. **Behavior change:** GIFs and stickers
  are no longer renamed or re-uploaded. Tests:
  `tests/test_document_filename_filter.py::test_media_like_documents_pass_through_untouched`,
  `::test_media_like_already_uploaded_documents_keep_their_name` (4 kinds each),
  `::test_regular_document_is_still_renamed`.

## Re-verified, intended — no change

- `setup_mirrors.step_build_config`'s non-forum `#1 → #1` branch: it doesn't
  occur in either config (pass 20).
- A live FloodWait aborts the rest of one message's fan-out: a documented
  trade-off (`mirroring.py` invariants).
- A re-uploaded photo is an `InputFile` named `photo.jpg`. `utils.is_image`
  accepts it, so it is sent as a photo, not a document.
- Filter order Watermark → RestrictSaving → DocumentFilename: the in-place
  rename of a shared cached `InputMediaUploadedDocument` is idempotent (fuzzed
  in pass 20 follow-up 4).
- `clear_channels.py` / `sync_pins.py` cover `CHAT_MAPPING` only (courses via
  `YAML_CONFIG_ENV`). Raised with the owner, who kept it as is.

Full suite 492 → 514, `pyflakes`, `ruff` and `mypy .` green.

## Pass 21 self-review — three bugs in this pass's own diff, one doc fix

A second whole-project review, requested by the owner before commit, re-read
this pass's diff line by line and the files the first read only skimmed
(`README.md`, `app.json`, `Procfile`, `pyproject.toml`, CI, dependabot).
Each finding was reproduced with a test that fails before its fix.

- **P2, regression from this pass (fixed).** The `edit_message`
  caption-too-long fallback always retried with an empty caption. That is
  right for a split mirror, but a mirror sent with its whole (≤1024) caption,
  whose source caption was later edited past the limit, lost its caption
  entirely (before this pass it just kept the old one). The fallback now
  re-reads the mirror (`get_messages`, only on this rare error path) and keeps
  its current caption and entities. Test:
  `tests/test_edit_message_caption_split.py::test_unsplit_mirror_keeps_its_caption_when_the_source_outgrows_the_limit`.
- **P3, from this pass (fixed).** `_edit_links_pass` skipped every media
  mirror whose text is >1024, but a Premium mirror account sends such a
  caption whole, so its links would never be fixed. Only an *empty*-caption
  media mirror (a split one) is skipped now. Test:
  `tests/test_past_mode.py::test_edit_links_pass_fixes_long_caption_sent_whole`.
- **P3, latent, from this pass (fixed).** `_edit_links_pass` ran every mirror
  through the pair's *first* copy-mode direction's filters. Two topic
  directions of one pair with different `filters:` got each other's chain.
  Each mirror now uses its own direction (`EventProcessor._config_for_topic`
  on the row's `source_topic_id`/`mirror_topic_id`), for `fallback_link_url`
  as well. Both live configs share one filter chain, so it never fired. Test:
  `tests/test_past_mode.py::test_edit_links_pass_uses_each_mirrors_own_direction_filters`.
- **Docs (fixed).** `README.md`'s variable table and `app.json` said
  `PAST_MODE` replays history "on startup". `main.py` (and `Procfile`'s
  `web: python main.py`) never reads it: only `past_mode.py` replays. Both
  texts now say so.

Re-verified, no change: the crop filter, the MP4 declaration, and the
media-like skips were re-read against GIF (`.gif.mp4` keeps its name), static
sticker, and stamped-GIF-then-rename paths. The `ForwardFormatFilter` mixin
switch leaves an entity that ends exactly at the placeholder untouched.

Full suite 514 → 517, `pyflakes`, `ruff` and `mypy .` green.
