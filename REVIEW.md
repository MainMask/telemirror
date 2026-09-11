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
- `_sync_broadcast_channel` seeds `broadcast_sync` from `messages` when the table
  is empty, so it doesn't re-mirror the whole channel history.
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
- `_integrity_check`: `checkpoint < max(original_id of mirrors)` → the checkpoint
  is rolled forward to `max_mirrored` (gaps between them are skipped on resume —
  logged explicitly).
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
