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
generator. Earlier passes' references to the file are historical.

Fixed along the way: `_common.fetch_all_topics` dropped `ForumTopicDeleted`
tombstones (crashed callers on `.title`) and now pages from the last non-deleted
topic; `setup_mirrors._sync_forum_topics` makes topic creation idempotent after a
FloodWait abort; `classify_donor` excludes already-created «⚜️ Цитадель» recipients
so they can't be re-picked as donors; the duplicate detector skips an empty
`name_key` (bare-«Цитадель» titles no longer collapse into one false group).
