# telemirror — project overview (for AI agents)

Snapshot of the codebase at `master` 67ae470 (+ uncommitted work, 2026-11-19).
Repo: `/Users/skylonsky/Desktop/telemirror`. All paths below are repo-relative.
UI texts of the control panel are Russian and are quoted verbatim.

---

## 1. Purpose & stack

**What it is.** A Telegram *userbot* channel mirror (client API, not Bot API) that
copies or forwards posts from source channels/groups/forum topics into target
channels/topics, live and from history, with a filter pipeline that can skip or
rewrite posts (keywords, links, footers, captions, watermark removal/stamping,
file renaming, "restrict saving content" bypass). Around it: a multi-project
model (one project = one mirror config + one account session + one set of
systemd units) and a Russian-language **control panel bot** (`bot/`, aiogram 3)
that manages projects, accounts, directions, filters, history replay,
maintenance tasks, monitoring timers and notifications — so the operator does
not need SSH.

Origin: a fork of the open-source `telemirror` (Telethon), heavily extended.
The production deployment mirrors the "⚜️ Цитадель" channel set
(`.configs/mirror.config.yml` ~199 directions, `.configs/citadel_courses.config.yml` ~74).

**Stack**

| Area | Choice |
|---|---|
| Python | 3.13 (`.python-version`, `pyproject.toml` ruff/mypy target, CI `setup-python 3.13`) |
| Telegram client | `telethon==1.44.0` (+ `cryptg`), vendored send/forward fork in `telemirror/_patch/sending.py` (topic replies, `invert_media`, `message_effect_id`) |
| Event loop | asyncio + `uvloop` (non-Windows) |
| Panel bot | `aiogram==3.32.0` (Bot API, HTML parse mode), FSM in a custom `MemoryStorage` |
| DB | PostgreSQL via `psycopg[binary,pool]==3.3.5` (`AsyncConnectionPool` 1..10) **or** `InMemoryDatabase` (LRU, 100 entries, `USE_MEMORY_DB=true`) |
| Config | `python-decouple` (`.env`), `PyYAML` (mirror YAML read), `ruamel.yaml` (panel round-trip edits preserving comments) |
| HTTP | `aiohttp` (health endpoint, BotNotifier), `urllib` (sync alerts/selfcheck) |
| Media | `opencv-python-headless`, `numpy`, `pillow`, `simple-lama-inpainting` (installed `--no-deps` by `install.sh`), CPU `torch==2.5.1` (Linux only), system `ffmpeg` |
| Session import | `opentele-ng==1.5.0` (tdata), only in a child process (it monkey-patches Telethon) |
| Dev/CI | `pytest==9.1.1`, `pyflakes`, `ruff` (rules F,E9,B,PIE,C4,FLY,LOG), `mypy`; GitHub Actions `.github/workflows/ci.yml` runs all four + installs ffmpeg |
| Deploy | systemd only (Ubuntu VPS, 1 vCPU / 2 GB RAM), templates in `deploy/systemd/`; Docker/Heroku removed |

---

## 2. Repository map

### Top level
- `README.md` — user docs (setup, env, filters, past mode, tasks, panel menu tree).
- `CLAUDE.md` — coding rules for agents (think first, simplicity, surgical changes, verify, project consistency).
- `REVIEW.md` — 4k-line module review/sign-off journal (passes 1–36+; invariants, fixed bugs, deferred P3s). Skim headings only.
- `pyproject.toml` — pytest/ruff/mypy config only (no packaging). `_patch/*` excluded from B/PIE/C4 and mypy.
- `requirements.txt`, `requirements-dev.txt`, `install.sh` (LaMa `--no-deps` + CPU torch on Linux).
- `.env-example`, `.configs/mirror.config.yml-example` — must be kept in sync with config/filter/env changes.
- `.configs/mirror.config.yml`, `.configs/citadel_courses.config.yml` — **tracked production configs** (live and courses; migrated projects `live`/`crs` point at them).
- `conftest.py` — creates a throwaway project in a temp dir, sets `TELEMIRROR_PROJECTS_DIR`, `TELEMIRROR_PROJECT=test`, `USE_MEMORY_DB=true` so `telemirror.config` imports in tests.
- `deploy/` — systemd units, `bootstrap.sh`, `setup-swap.sh`, `cron.d/telemirror-tmp`, `README.md`.
- Git-ignored runtime data: `projects/`, `sessions/`, `*.jsession`, `.env`.

### `telemirror/` (the mirror core; every entry point is `python -m telemirror.<x>`)
- `config.py` — import-time settings: `.env` + the project's YAML → `CHAT_MAPPING: Dict[source, Dict[target, List[DirectionConfig]]]`, `BROADCAST_CHANNEL/TARGETS`, DB URL, session/fingerprint, `PORT`. `build_filters()` instantiates filters by name via `getattr(messagefilters, name)`. Validators: `_validate_mode`, `_validate_forward_filters` (content-mutating filters forbidden with `mode: forward`), `_validate_watermark_filter_order`. Fails the import on any bad value.
- `directions.py` — frozen dataclasses `DirectionConfig` and `PastModeConfig` (kept out of config.py so core doesn't import config).
- `projects.py` — `Project` dataclass (`key,name,icon,session,config,port` + `live_unit/past_unit/task_unit`), `load_project/list_projects/create_project/update_project/delete_project` (moves to `projects/.deleted/`), `make_key` (Cyrillic transliteration slug ≤20), `sharing_session`, path helpers (`chats.json`, `failed.json`, `stats.json`, `access.json`, `requests/`), `write_json` (atomic, per-pid tmp), `save_chat_names`, and `python -m telemirror.projects migrate` (creates `live`/`crs` from the pre-project `.env` setup).
- `live.py` — live mirror entry: session lock, uvloop, aiohttp health endpoint (`GET /` → 204 on `HOST:PORT`), opens DB, builds `Telemirror` with `BotNotifier` and `LiveSink`.
- `mirroring.py` (2.8k lines) — the engine:
  - `EventProcessor` — `new_message`, `new_album`, `edit_message`, `delete_message`; link rewriting (`_rewrite_links`, `_try_rewrite_tg_link`), reply chaining, topic routing, per-target dedup (`already_mirrored`), `dedup_hours` (`_is_repeat/_remember_sent`), file-reference refresh, caption-too-long split, in-flight fan-out tracking, outcome recording.
  - `NoticeLogHandler` — WARNING+ log records → panel admins (debounce 5 s, cooldown 55 s, ≤10/min, ≤10 in flight, "held back" counter).
  - `EventHandlers` — registers Telethon `NewMessage/Album/MessageEdited/MessageDeleted` for source chats, plus private-message notice.
  - `Mirroring` — connect, READY/WATCHDOG, handlers, sink loop (15 s), `chats.json`, broadcast sync, retry requests; `Telemirror` — builds the client (`connection_retries=1000`).
- `past.py` — history replay (`telemirror-past@`): per (source,target) pair, checkpointed, FloodWait/media retry wrapper, second "edit links" pass, exit 143 on SIGTERM.
- `storage.py` — `MirrorMessage` NamedTuple, `Database` ABC, `InMemoryDatabase`, `PostgresDatabase` (auto-creates tables/indexes/columns), `open_database()`.
- `account.py` — `open_account()` async CM for scripts (lock, client with session fingerprint, bounded connect, `get_me` auth check).
- `login.py` — CLI sign-in (Telegram Desktop fingerprint) or `--import PATH` (tdata/ZIP/.session+.json) → `sessions/<phone>.jsession`.
- `notify.py` — `BotNotifier` (Bot API `sendMessage` to every `PANEL_ADMIN_IDS`, async + sync), hand-packed panel callback buttons (`unit_button`, `failed_buttons`), UTF-16-aware `cut`.
- `alert.py` — `python -m telemirror.alert <unit>` (OnFailure=) with journal tail; `send_alert()` used by health.
- `health.py` — `python -m telemirror.health`: flapping (≥3 restarts since last run) / stuck-transitional detection per live unit; state in `/run/telemirror-health.json`.
- `report.py` — weekly report per project from `stats.json` + `failed.json`.
- `selfcheck.py` — read-only installation check (env, bot token, DB tables, unit links, timers, panel, projects' sessions/configs/live mirror health port).
- `outcomes.py` — `Outcomes`/`Target` per-fan-out result (sent/filtered/dup/failed + reason), `OutcomeSink` protocol, `current` ContextVar.
- `sink.py` — `LiveSink`: feeds `Stats` and `FailedQueue`, one "❗ Не скопировано постов: N…" notice per minute max.
- `failed.py` — `FailedQueue` (`failed.json`, ≤300 entries, ≤14 days), panel request files (`requests/<id>|all|clear`), `entry_id` (sha1[:8]).
- `stats.py` — per-day per-pair counters `[sent, filtered, dup, failed]`, 35 days, `quiet_days()`.
- `dedup.py` — `fingerprint()` of a post/album (sha1 of normalized text + sorted source media ids; text-only needs ≥20 chars).
- `hints.py` — type aliases (`EventMessage`, `EventAlbumMessage`, `EventLike`).
- `mixins.py` — `CopyEventMessage` (deep-copies media/entities via the Message constructor's full field list), `UpdateEntitiesParams` (entity offset/length shifting), `ChannelName`, `MappedChannelName`, `MessageLink`.
- `messagefilters/` — filter pipeline (see §6): `base.py` (`FilterAction`, `FilterResult`, `MessageFilter` protocol, `CompositeMessageFilter`), `messagefilters.py` (text/skip filters), `restrictsavingfilter.py`, `documentfilenamefilter.py`, `watermarkfilter.py`, `_media.py` (download with retry, `MediaDownloadError`, `strict_media_mode`, `ReuploadCache`, `reupload_errors`, `fetch_fresh_media`, `source_media_id`, temp files prefixed `telemirror-tmp-`).
- `watermark/processor.py` — `WatermarkConfig`; detection (CLAHE + Sobel gradient template matching over scales), LaMa inpainting for photos (one at a time process-wide), ffmpeg `delogo` for video removal, PIL/ffmpeg overlay stamping of `watermark/my_watermark.png`, encode-time estimator, ffmpeg cancellation. Default `reference_watermark.png` is **not** in the repo (removal then disabled unless `template_path` given).
- `_patch/` — vendored Telethon `send_message`/`forward_messages`/`send_file`/`_send_album` with `reply_to_topic_id`; `album.set_album_event_timeout` (patches `telethon.events.album._HACK_DELAY`).
- `misc/` — `dsn.py` (percent-encoded DSN), `jsession.py` (`.jsession` load/save, `TDESKTOP_APP` fingerprint, 0600, `.bak` on overwrite), `links.py` (`private_message_link`), `log_setup.py`, `lrucache.py`, `message_groups.py` (`iter_message_groups` → message or album list), `sdnotify.py` (READY/WATCHDOG/STOPPING, `watchdog_loop`), `session_import.py` (tdata via child process, `.session` SQLite + seller `.json`, `.jsession`; ZIP ≤100 MB unzipped; dedups by key), `session_lock.py` (`flock` on `<session>.lock`, waits 30 s, writes holder pid/argv), `signals.py` (`cancel_on_sigterm`), `telegram_client.py` (`build_telegram_client` with `flood_sleep_threshold=300`, `connect_with_timeout`, `connection_probe`, `new_tdesktop_client`, `cancel_and_await`), `topics.py` (`topic_id_of`, General=1), `urlmatcher.py` (`UrlMatcher` black/whitelist by host/path).
- `tasks/` — maintenance scripts (`python -m telemirror.tasks.<x>`), see §3: `_common.py` (`fetch_all_topics`, `entity_type`, `safe_call` with FloodWait/reconnect), `check_access.py`, `restrict_saving.py`, `sync_pins.py`, `anonymize_groups.py`, `clear_channels.py`, `setup_mirrors.py` (CLI-only wizard).

### `bot/` (control panel, `python -m bot`)
- `__main__.py` — exits 0 without `PANEL_BOT_TOKEN`, 1 without `PANEL_ADMIN_IDS`; `Bot(parse_mode=HTML)`, `SafeEdit` request middleware, `set_my_commands`, `start_polling`.
- `app.py` — `build_dispatcher()`: checks registry↔handlers consistency (`registry.unhandled_actions/unknown_actions`), middlewares, router order, DI (`sysd`, `store`, `runtime`, `admin_ids`), watcher start/stop, error handler (`texts.INTERNAL_ERROR` to the user).
- `settings.py` — env (`PANEL_BOT_TOKEN`, `PANEL_ADMIN_IDS`, `LOG_LEVEL`) and constants (timers, `TASK_MODULES`, sync_pins flag whitelist, `/run/telemirror-panel`, page sizes, TTLs, cooldown 120 s, upload limits, watch 30 s, crash-notice cooldown 600 s). Never imports `telemirror.config`.
- `registry.py` — the whole menu as data: `Button`, `Screen`, `SCREENS`, `TITLES`, `MAIN_MENU`, `ACTIONS`, colour styles (PRIMARY/DANGER/SUCCESS, Bot API 9.4), `menu_path()`, emoji rules.
- `screens.py` — `@view(id)` registry `VIEWS`, `screen_text` (note, title breadcrumb, body, buttons with hints grouped, children, folded "more"), `show`, `open_screen` (loads project; deleted → 📁 Проекты).
- `callbacks.py` — `NavCB` (`n:` screen), `ActCB` (`a:` action), `FltCB` (`f:` filter editor ops v/x/+/t/e/u/w/r/n), `ChoiceCB` (`c:` form choice — the only callback that keeps a form alive). ≤64 bytes.
- `states.py` — FSM groups (see §4), `leave_form`, `PanelStorage`.
- `middlewares.py` — `AdminOnly`, `Services` (`deps` dict), `LeaveFormOnNavigation`, `ChatPicked` (Bot API `request_chat` result), `AlbumMiddleware` (files sent together, 0.7 s).
- `runtime.py` — in-memory `Runtime` (restart cooldown per unit, last task `Launch` per (project, task) with config sha, sync_pins flags/options).
- `turns.py` — one-process-per-session orchestration: `start()` stops other holders, records paused live mirrors in `projects/.resume.json`; `due()` resumes them when the run ends.
- `watcher.py` — 30 s systemd polling loop → push notices (task finished/failed/interrupted, mirror crashed/back) and `turns.due`.
- `systemd.py` — async `systemctl`/`journalctl` wrapper (`--no-block`), `UnitState` (`running`, `completed`), whitelist `_check()` (only existing projects' units + 3 timers).
- `configstore.py` — `ConfigStore.update/replace_text/restore_backup`: ruamel round-trip, PyYAML semantic round-trip check, subprocess validation (`import telemirror.config` against a temp project), `.bak`, sha-guarded atomic replace, asyncio lock; `text_diff`, `check_yaml` (≤256 KB, must have `directions:` list).
- `configedit.py` — pure mutations of the ruamel data: directions (add/delete/refs/values), globals (toggle, values), history/past_mode, replay delay, filters (add/delete/move/args/items) with fingerprints so a changed list is refused (`ConfigError("stale")`).
- `configparse.py` — input parsing (`normalize_chat_ref` `-100…[#topic]`, delays, hours, last_n, since date, URLs, filter items, numbers) and `ConfigError(code, detail)`.
- `filtercatalog.py` — per-filter arg kinds/defaults (`FILTER_ARGS`), required args, placement rules (`EARLY_FILTERS`, `AFTER_EARLY_FILTERS`), Russian names/descriptions/arg labels, advanced args.
- `status.py` — `unit_state`, `find`, `running_units`, `session_holders`, `ProjectInfo`/`project_info` (config snapshot, readable/writable, names).
- `sessions.py` — `sessions/*.jsession` listing, account labels, `users_of`, account picker keyboard.
- `pending.py` — per-chat non-FSM state: `Login` (live Telethon client), `Upload` (files awaiting tdata passcode), `Picker`; 15-min TTL; `close_all` on shutdown.
- `writes.py` — `save()`: ⏳ → `ConfigStore` op → reopen screen with `texts.SAVED` / `SAVED_STOPPED`, or refusal.
- `texts.py` — all fixed Russian strings, formatting helpers (`esc`, `head`, `more` = expandable quote, chat names, durations, `CONFIG_ERRORS`).
- `safe_edit.py` — swallows "message is not modified", falls back to a new message when not editable, ignores too-old callback answers.
- `keyboards/common.py` (button/markup/choice/cancel/confirm/pick/back/paging), `keyboards/menu.py` (reply main menu, `chat_picker` with `KeyboardButtonRequestChat`, `screen_kb` built from registry).
- `routers/` — `_common.py` (decorators `on_action`, `with_project`, `input_kind`→`INPUTS`, `confirmed`→`CONFIRMED`, `ask_confirm`/`take_confirm` with token + 10-min TTL, forms helpers, `remember_chat`), `_units.py` (start/stop/restart of units with session/cooldown checks), and one router per section (see §4).

### `tests/` (102 files, ~809 test functions; `pytest -q`)
Areas covered (by file name):
- **Mirroring engine**: `test_new_message_batch`, `test_new_album_batch`, `test_new_album_index_guard`, `test_album_event_delay_race`, `test_broadcast_sync`, `test_caption_too_long_split`, `test_delete_message*` (flood flush, waits for fan-out), `test_edit_message_*` (caption split, fan-out race, file-ref refresh, link rewrite, markdown, media unchanged, reupload single-flight), `test_edit_media_allowed_sticker`, `test_edit_delete_flood_propagates`, `test_fanout_*`, `test_file_reference_refresh`, `test_invert_media_effect`, `test_link_rewrite_cache`, `test_tg_message_link_forms`, `test_matches_from_topic`, `test_reply_to_topic_ambiguity`, `test_mirroring_signoff`, `test_mirroring_watchdog`, `test_on_private_message`, `test_mirror_chat_names`, `test_main_startup`, `test_log_handler`.
- **Filters/media/watermark**: `test_filters_captionless`, `test_forward_format_filter`, `test_keyword_replace_filter`, `test_strip_footer_filter`, `test_url_filters`, `test_urlmatcher`, `test_document_filename_filter`, `test_restrict_saving_filter`, `test_restrict_saving_cache_shortcut`, `test_reupload_cache`, `test_media_helpers`, `test_watermark_*` (config, encode estimate, flood propagates, reupload cache, size guard, stamp only, real video encode needs ffmpeg).
- **Past mode**: `test_past_mode`, `test_past_watchdog`, `test_replay_with_retry_album_checkpoint`.
- **Storage/config/misc**: `test_storage`, `test_config`, `test_build_dsn`, `test_jsession`, `test_lrucache`, `test_message_groups`, `test_mixins`, `test_update_entities_params`, `test_sdnotify`, `test_signals`, `test_session_lock`, `test_session_import`, `test_telegram_client_factory`, `test_connect_timeout`, `test_log_setup`, `test_readme_examples` (README/example YAML must load).
- **Ops**: `test_alert`, `test_health`, `test_notify`, `test_report`, `test_selfcheck`, `test_failed_posts`, `test_dedup`, `test_projects`.
- **Tasks**: `test_anonymize_groups`, `test_check_access`, `test_clear_channels`, `test_restrict_saving`, `test_safe_call`, `test_fetch_all_topics`, `test_setup_mirrors_*`, `test_sync_pins_*`.
- **Panel**: `test_panel_bot` (dispatcher via `feed_update`, helpers in `tests/_panel.py`), `test_panel_configstore`, `test_panel_registry` (labels/emoji/callback sizes/toast length), `test_panel_systemd`, `test_panel_watcher`.

---

## 3. Entry points, processes and how they talk

| Command | systemd unit | What it does |
|---|---|---|
| `python -m telemirror.live` | `telemirror@<key>.service` (`Type=notify`, `WatchdogSec=600`, `Restart=always` 10→120 s backoff, `StartLimitBurst=15/3600s`, `MemoryMax=1400M`, `Conflicts=telemirror-past@%i telemirror-task@%i`, `OnFailure=telemirror-alert@%n`, `[Install]` multi-user) | 24/7 live mirror of project `<key>` (`TELEMIRROR_PROJECT=%i`). Health endpoint on the project's `port`. |
| `python -m telemirror.past` | `telemirror-past@<key>.service` (`Type=notify`, watchdog, `Restart=on-failure` 60 s, `SuccessExitStatus=143`, `Conflicts=telemirror@%i`, no `[Install]`) | History replay of directions with `past_mode:`; resumable. Started by the panel (⏪ История) or by hand. |
| `python -m telemirror.tasks.<module> $TASK_ARGS` | `telemirror-task@<key>.service` (`EnvironmentFile=/run/telemirror-panel/%i.env` with `TASK_MODULE`, `TASK_ARGS`; no Restart; `Conflicts=telemirror@%i`) | One maintenance run started by the panel; fails on purpose without the env file. |
| `python -m telemirror.alert <unit>` | `telemirror-alert@.service` (oneshot) | OnFailure alert with journal tail via the panel bot. |
| `python -m telemirror.health` | `telemirror-health.{service,timer}` (boot+5 min, every 10 min) | Flapping / stuck detection for every project's live unit. |
| `systemctl try-restart telemirror@*.service` | `telemirror-restart.{service,timer}` (04:00 ±5 min) | Daily clean restart of running mirrors (also applies saved-but-unapplied config). |
| `python -m telemirror.report` | `telemirror-report.{service,timer}` (Mon 10:00, `Persistent=true`) | Weekly report per project. |
| `python -m bot` | `telemirror-panel.service` (`Restart=on-failure`, `StartLimitBurst=5/600s`, `OnFailure=` alert, `RuntimeDirectory=telemirror-panel`, `MemoryMax=600M`, no Conflicts) | Control panel. |
| `python -m telemirror.selfcheck` | — (also panel 🧾) | Installation check, exit 1 on ❌. |
| `python -m telemirror.login [--import PATH]` | — | Create `sessions/<phone>.jsession`. |
| `python -m telemirror.projects migrate` | — | One-time migration from the pre-project units. |
| `python -m telemirror.tasks.setup_mirrors` | — (CLI only) | Interactive "⚜️ Цитадель" wizard (hard-coded donor title lists; creates recipient channels/topics, avatars; merges into `.configs/mirror.config.yml`, courses into `.configs/citadel_courses.config.yml`). |

All units run as root from `/root/telemirror` with `.venv/bin/python`, `NoNewPrivileges`, `ProtectSystem=full`, `PrivateTmp` (mirror/past/task/panel), `Nice`. `deploy/bootstrap.sh` (idempotent): swap to 2 GB + `vm.swappiness=10`, symlinks all units into `/etc/systemd/system/`, removes dangling pre-project unit links, journald cap (`SystemMaxUse=500M`, persistent journal), cron `/etc/cron.d/telemirror-tmp` (hourly delete `/tmp/telemirror-tmp-*` older than 3 h), `daemon-reload`, enables the 3 timers. It never starts mirrors.

**Maintenance tasks** (`telemirror/tasks/`, all use the project's session via `open_account`):
- `check_access` — read-only; account sees each source & broadcast channel and may post in each target (dialog rights; topics not checked); notes `noforwards` sources; writes `projects/<key>/access.json` and merges titles into `chats.json`.
- `restrict_saving [--dry-run] [--yes]` — `ToggleNoForwardsRequest` on every target (live `CHAT_MAPPING` **and** hard-coded `.configs/citadel_courses.config.yml`).
- `sync_pins [--dry-run] [--additive] [--allow-clear] [--include-broadcast] [--thorough] [--max-pins N] [--only DONOR_ID]…` — reconcile donor pins onto mirrors using `binding_id` (only mirror-managed pins are unpinned).
- `anonymize_groups [--dry-run] [--yes]` — "Remain Anonymous" for the account + "Hide Members" in supergroups where it is admin.
- `clear_channels [--dry-run] [--yes]` — deletes all messages in targets (`DeleteHistoryRequest` for whole channels, per-message deletes for topic-scoped targets), then resets `past_mode_checkpoint`, `binding_id` rows for the target and `broadcast_sync` if the target receives broadcasts (requires Postgres).
- Panel whitelist: `settings.TASK_MODULES = {ca: check_access, rs: restrict_saving, sp: sync_pins, ag: anonymize_groups, cc: clear_channels}`; `maintenance.build_task_args` only emits whitelisted flags and integer options.

**Inter-process communication** (no sockets/queues between our processes; everything goes through files, the DB and systemd):

| Channel | Writer → Reader | Purpose |
|---|---|---|
| `projects/<key>/project.yml` | panel / `migrate` → everyone | project definition |
| mirror YAML (`projects/<key>/mirror.config.yml` or `.configs/*.yml`) | panel (`ConfigStore`) or hand → mirror/past/tasks at start | config (read once at import) |
| `projects/<key>/chats.json` | mirror at start (`get_dialogs`), `check_access`, panel (forwarded post / picked chat) → panel, report, sink | channel titles |
| `projects/<key>/failed.json` | live mirror only → panel ❗, report | not-copied posts |
| `projects/<key>/requests/<id>|all|clear` | panel → live mirror (polled every 15 s, then deleted) | retry / clear requests |
| `projects/<key>/stats.json` | live mirror (every 10 min + on stop) → report, panel (🔇 quiet directions) | counters |
| `projects/<key>/access.json` | `check_access` → panel 🛂 | access report |
| `projects/.resume.json` | panel `turns` → panel watcher, selfcheck | mirrors paused for a run on the same session |
| `projects/.deleted/<key>-<ts>/` | panel | undoable project deletion |
| `/run/telemirror-panel/<key>.env` | panel → `telemirror-task@` | task module + args |
| `/run/telemirror-health.json` | health timer | last NRestarts/ActiveState |
| `sessions/<phone>.jsession(.lock,.bak)` | login/panel → mirror/past/tasks | account + lock |
| PostgreSQL (shared by all projects) | mirror/past/tasks | bindings, checkpoints, broadcast sync, fingerprints |
| systemd (`systemctl show/start/stop/enable/disable/restart`, `journalctl`) | panel ↔ units | lifecycle, state, journals, progress lines |
| Telegram Bot API (`PANEL_BOT_TOKEN`) | mirror/past/alert/health/report (`BotNotifier`) and panel → admins | all notifications |

---

## 4. Control panel (`bot/`)

### Access control & model
- **Who**: only Telegram user ids in `PANEL_ADMIN_IDS` (`bot.middlewares.AdminOnly` outer middleware drops every other update silently, with a warning log). No roles: every admin can do everything. `PanelStorage` avoids creating FSM records for strangers. Admin ids are read-only in the panel (live in `.env`).
- The bot runs as root and calls `systemctl`/`journalctl` only for units of existing projects and the three timers (`bot.systemd._check`); no user input reaches argv.
- **Multi-project**: any number of projects; each has its own config, session, port, units. **Multi-account**: sessions in `sessions/*.jsession`; several projects may share one session → they run *in turn* (`bot/turns.py` + `telemirror/misc/session_lock.py`). Starting a replay/task pauses every unit on that session and records live mirrors to resume; starting a mirror on a busy session **disables** the other mirrors for good (one mirror per session).
- Commands (`app.COMMANDS`): `/start` — «Главный экран» (welcome + main reply keyboard), `/status` — «Что сейчас выполняется» (opens 📊 Задачи without leaving a form), `/cancel` — «Выйти из ввода».
- Main reply keyboard (`registry.MAIN_MENU`): `📁 Проекты`, `📊 Задачи`, `⚙️ Настройки`.
- UI conventions (from `registry.py`/README): buttons listed with hints under group subheadings; `🔄 Обновить` + `⬅️ Назад` last row; colours: blue (PRIMARY) = the next step, red (DANGER) = irreversible, green = confirmation; confirmations only for irreversible/deleting/session-stopping actions, expire after 10 min (`CONFIRM_TTL_SEC`); `✖️ Отмена` / `/cancel` return to where a form began; any non-`ChoiceCB` tap leaves the current form; startup fails if a registry button has no handler or vice versa.

### Menu tree (screen id — title — buttons; from `bot/registry.py`)
```
📁 Проекты (prj, paged list of projects)        [➕ Новый проект] (name → icon → account)
└ 📁 Проект (card: state, account, directions count, shared-session note,
  │          "⚠️ Изменения ещё не применены" when config mtime > ActiveEnterTimestamp, 👉 next step)
  │   [▶️ Запустить | ⏹ Остановить | 🔁 Перезапустить]
  ├ 🔀 Направления (dirs, paged; rows «N. Источник → Канал» + marks 🧹 own filters, ✳️ own settings, 🔇 silent ≥7 days)
  │   [➕ Добавить] (source → targets → mode/history choice)   [🔎 Найти] (by name or id)
  │   ├ 🔀 Направление (dir): [📨 Откуда] [🎯 Куда] (channel list: add by id/forward/📇 pick, 🗑 one, ✅ Готово)
  │   │                       [⏱ Пауза между постами] [🗑 Удалить]   (shows last post: сегодня/вчера/N дн.)
  │   │   └ 🧹 Фильтры направления (dflt) — own filter list (copy of project's on first add)
  │   └ 📢 Рассылка (bc): [📢 Рассылка из канала] [📬 Куда рассылать]
  ├ 🧹 Фильтры (flt): ➕ Добавить фильтр (Отсеять посты / Изменить посты) → 🧹 Фильтр (fv):
  │     list args (🗑 value, ➕ Добавить, 📝 Только эти @…), ☑️ toggles, typed values,
  │     🔬 Тонкая настройка (advanced args), ⬆️ Выше / ⬇️ Ниже, 🗑 Удалить фильтр
  ├ ⏪ История (rpl): Запуск: [▶️ Начать] [⏹ Прервать]; Что и как: [📜 Что копировать]
  │     (⏭ Без истории / 📚 Вся история / 🔢 Последние N… / 📅 С даты…) [⏱ Пауза при копировании];
  │     shows the current progress line from the journal
  ├ 🛠 Инструменты (mnt)
  │   ├ 🛂 Проверка доступа (ca): [🔍 Проверить] [⏹ Остановить] [📄 Журнал] + last access.json report
  │   ├ 🔒 Запрет копирования (rs): [🔍 Проверить] [▶️ Выполнить] [⏹ Остановить] [📄 Журнал]
  │   ├ 📌 Закрепы (sp): same 4 + Настройки запуска: [☑️ Только добавлять] [☑️ Снимать все]
  │   │      [☑️ С рассылкой] [☑️ Тщательно] [📏 Лимит закрепов] [📍 Только источники]
  │   ├ 🕶 Анонимность (ag): same 4
  │   └ 🧨 Очистка каналов (cc): same 4, ▶️ Выполнить is DANGER
  ├ ❗ Не скопировано (fail, paged): [♻️ Повторить все] [🧽 Очистить список] + per-post retry rows (fail_one)
  └ ⚙️ Настройки проекта (mng)
        Копирование: [✏️ Правки] [✂️ Удаления] [↔️ Режим] [🔗 Ссылка вместо чужих] [🧬 Без повторов]
        Проект: [🏷 Имя] [🎨 Значок] [👤 Аккаунт] [🗑 Удалить проект]
        └ 💾 Файл настроек (cfg): [📥 Скачать] [📤 Загрузить] (diff + validation + confirm) [↩️ Откатить]
📊 Задачи (tsk, paged: every project's 3 units) └ 📊 Задача (unit): state + journal; button to where it's run
⚙️ Настройки (set): Присмотр за зеркалами: [🩺 Проверка зеркал] [🔁 Перезапуск по расписанию] [📈 Сводка за неделю]
  ├ 👤 Аккаунты (acc, paged): [🔑 Войти по номеру] [📤 Загрузить сессию] └ 👤 Аккаунт (acct): [🗑 Удалить]
  └ 🧾 Проверка установки (chk): telemirror.selfcheck output
```
Extra labels (`registry.TITLES`): `📋 Копия`, `↪️ Пересылка`, `⏭ Без истории`, `📚 Вся история`, `🔢 Последние N…`, `📅 С даты…`, `➕ Добавить фильтр`, `🗑 Удалить фильтр`, `➕ Добавить`, `📝 Только эти @…`, `⬆️ Выше`, `⬇️ Ниже`, `🔬 Тонкая настройка`, `✅ Готово`, `➕ Новое направление`, `📇 Выбрать из списка`, `📺 Канал`, `👥 Группа`, `📲 Отправить код заново`, `📊 Задача` (notice button). Confirm labels `✅ Да`, `🗑 Да, удалить`.

Channels can be entered as `-100…` id (`#topic` for topics), as a forwarded post, or picked with `📇 Выбрать из списка` (Bot API `request_chat`, the admin's own chats).

### FSM states (`bot/states.py`)
- `NewProject.name → icon → account`
- `Login.phone → code → password` (sign-in by phone; code typed with spaces; code/password messages deleted; client kept in `pending.Login`; 15-min TTL; 2FA password never stored)
- `UploadSession.file → passcode` (tdata local passcode)
- `AddDirection.source → targets → choice`
- `Input.value` — any single typed value; FSM `kind` selects the handler in `_common.INPUTS`: `dir_find`, `dir_delay`, `dir_src`, `dir_dst`, `flt_new`, `flt_new_items`, `filter_items`, `filter_value`, `sp_max`, `sp_only`, `global` (broadcast_channel / broadcast_targets / fallback_link_url / dedup_hours), `rename`, `icon`, `account`, `rpl_delay`, `rpl_hist`, `rpl_last`, `rpl_since`.
- `UploadConfig.file` (then a `Confirm`)
- `Confirm.pending` — token-bound confirmation; kinds in `_common.CONFIRMED`: `unit_start`, `unit_stop`, `unit_restart`, `acc_del`, `cfg_put`, `cfg_undo`, `dir_del`, `flt_del`, `task`, `delete` (project).

### Routers (order in `app.ROUTERS`: menu, projects, directions, filters, params, replay, maintenance, failed, config_file, tasks, accounts, settings, stale)
- `menu.py` — `/start` (welcome with project/running counts and "Как начать"), main-menu buttons, `/status`, `/cancel`, `NavCB` navigation, `📇` picker, `✖️ Отмена`, yes/no confirmations dispatch, `Input.value` dispatch (forwarded post/picked chat accepted for channel-taking inputs).
- `projects.py` — `prj` list, `card` view (`next_step`), `start` (refuses without config/directions; `_units.ask_start`), `stop`/`restart`, ➕ Новый проект form (name ≤40, icon, account picker → `create_project`, next free port), rename, icon, account change, delete (disables all 3 units, moves folder to `.deleted`, `runtime.forget`).
- `directions.py` — list (paged, marks), 🔎 find, direction card (effective mode/edits/deletes, own hand-written settings shown not edited), 📨/🎯 channel list editor, ⏱ per-direction `send_delay`, 🗑 delete (confirm), ➕ Добавить wizard (source, targets, `📋 Копия`/`↪️ Пересылка`, history choice).
- `filters.py` — project and direction filter lists; add from `filtercatalog.ADDABLE_FILTERS` (placement: skip filters first, `StripFooterFilter` right after); card editing per arg kind (`set/list/map/ids` item-wise, `bool` toggle, `text/number` typed); move up/down; delete (confirm); adding a filter to a direction without own list copies the project's list first; deleting the last own filter removes the list.
- `params.py` — ⚙️ Настройки проекта view; toggles `p_edits→disable_edit`, `p_dels→disable_delete`, `p_mode→mode` (project-wide); values `p_bc→broadcast_channel`, `p_bct→broadcast_targets`, `p_link→fallback_link_url`, `p_dedup→dedup_hours`; 📢 Рассылка view. Shows how many directions override a value.
- `replay.py` — ⏪ История view (progress line grep from journal), start/stop of `telemirror-past@`, 📜 Что копировать (sets `past_mode` for **every** direction; keeps existing `send_delay`), ⏱ replay delay.
- `maintenance.py` — five tool screens; dry-run first, **▶️ Выполнить offered only right after a successful, completed dry-run with the same args and same config sha** (`can_run_real`); writes `/run/telemirror-panel/<key>.env`, starts `telemirror-task@`; stop; journal; sync_pins flags/options in `Runtime`; `access_text` renders `access.json`.
- `failed.py` — ❗ Не скопировано list from `failed.json`; ♻️ all / 🧽 clear / per-post retry → `telemirror.failed.request()` (mirror must be running to act).
- `config_file.py` — 📥 download YAML, 📤 upload (size/shape check, diff, validation, confirm, sha guard), ↩️ rollback (swap with `.bak`, itself undoable).
- `tasks.py` — 📊 Задачи list and 📊 Задача unit card with journal (`JOURNAL_LINES=15`, ≤2500 chars), button to the screen that runs the unit.
- `accounts.py` — 👤 Аккаунты list/card/delete (only if unused), 🔑 sign-in by phone (Telegram Desktop fingerprint `TDESKTOP_APP`, `📲` resend), 📤 upload (tdata ZIP + passcode, `.session` + `.json` album, ZIP, `.jsession`; ≤20 MB; checked by connecting; refused if the key is already saved), `then` routing back to the new project / project account.
- `settings.py` — ⚙️ Настройки view (admins shown read-only), timer toggles (`set_health/set_restart/set_report` → enable/disable the timer, no confirmation), 🧾 selfcheck view.
- `stale.py` — answers any unhandled button/message (stale button, no step, buttons-only step).
- `_units.py` — common start/stop/restart: systemd available, session file exists, 120 s cooldown, confirmation when other units on the session would be stopped (`pause_text`), `turns.start`.

### Notifications the admins receive
- From the panel watcher (`bot/watcher.py`, every 30 s; first poll = baseline): replay/task `✅ … закончилось успешно`, `⏹ … прервано`, `‼️ … закончилось с ошибкой`; mirror `⚠️ … упало и запущено снова` (≤1 per 10 min per unit), `🟢 … снова работает` after failed; `▶️ Снова запущено: … — после «…»` when paused mirrors are resumed.
- From other processes through `BotNotifier` (signed «icon name: …», with `📊 Задача` button): `telemirror.alert` (🔴 unit gave up / ‼️ task failed + journal), `telemirror.health` (flapping / stuck), mirror `NoticeLogHandler` (⚠️ Предупреждение / ‼️ Ошибка / 🚨 Критично), `📩 Аккаунту написали в личку`, `❗ Не скопировано постов: N…` (with `♻️ Повторить все` / `❗ Не скопировано` buttons), replay "пропустило пост", weekly `📈 Сводка за неделю`. Admins must have pressed /start once.

---

## 5. Data model

### Mirror config YAML (`telemirror/config.py`)
```yaml
filters: [ - FilterName: {args} | - FilterName ]   # project-wide default chain (EmptyMessageFilter if absent)
mode: copy | forward                               # default copy
disable_edit: bool                                 # default false
disable_delete: bool                               # default false
fallback_link_url: "https://t.me/…"                # replaces unresolvable t.me links to mirrored sources
dedup_hours: N                                     # 0/absent = off
broadcast_channel: -100…                           # YAML wins over BROADCAST_CHANNEL env
broadcast_targets: [-100…, "-100…#topic"]          # YAML wins over BROADCAST_TARGETS env
directions:                                        # required list (may be [])
  - from: [-100…, "-100…#topic"]
    to:   [-100…, "-100…#topic"]
    # per-direction overrides: mode, disable_edit, disable_delete, fallback_link_url,
    # dedup_hours, send_delay (default SEND_DELAY env, 0.5), filters (replaces global list)
    past_mode:            # exactly one strategy
      last_n: 100 | full_history: true | since_date: "2024-01-01T00:00:00"
      send_delay: 0.5
```
- Each direction's filter list is built once and shared by all its (source,target) pairs (shared `ReuploadCache`).
- Broadcast channel: auto-added directions to all targets (or the whitelist) with `EmptyMessageFilter`, `mode: copy`, edits/deletes on, `BROADCAST_SEND_DELAY`.
- `DirectionConfig(disable_delete, disable_edit, filters, from_topic_id, to_topic_id, mode, past_mode, send_delay, fallback_link_url, dedup_hours)`; `PastModeConfig(send_delay=0.5, since_date, last_n, full_history)` (`telemirror/directions.py`).
- Load-time validation failures: bad mode; content-mutating filter (`WatermarkRemovalFilter, DocumentFilenameFilter, RestrictSavingContentBypassFilter, UrlMessageFilter, KeywordReplaceFilter, ForwardFormatFilter, StripFooterFilter`) with `mode: forward`; a re-uploading filter before `WatermarkRemovalFilter` that applies to the source; multi-key filter entry; bad past_mode; `BROADCAST_TARGETS` without channel.

### `project.yml`
`name, icon, session (repo-relative .jsession), config (default projects/<key>/mirror.config.yml), port`. New project config template: `mode: copy`, edits/deletes on, `directions: []`.

### Environment variables (`.env` at repo root; decouple reads `os.environ` first)
- Account: `SESSION_FILE` (or project's session), else `API_ID`, `API_HASH`, `SESSION_STRING`, optional `API_SYSTEM_VERSION`, `API_DEVICE_MODEL`, `API_APP_VERSION` (ignored with a .jsession; lang pack/system lang code come from the file).
- Project: `TELEMIRROR_PROJECT` (set by units), `TELEMIRROR_PROJECTS_DIR` (tests).
- DB: `USE_MEMORY_DB`, `DATABASE_URL` or `DB_NAME/DB_USER/DB_PASS/DB_HOST` (one DB shared by all projects).
- Mirror: `BROADCAST_CHANNEL`, `BROADCAST_TARGETS`, `BROADCAST_SEND_DELAY` (0.5), `SEND_DELAY` (0.5), `LOG_LEVEL`, `HOST` (0.0.0.0), `PORT` (8000; project port wins).
- Panel/notices: `PANEL_BOT_TOKEN`, `PANEL_ADMIN_IDS` (comma/semicolon list).
- Task unit: `TASK_MODULE`, `TASK_ARGS` (from `/run/telemirror-panel/<key>.env`).

### Database (`telemirror/storage.py`, PostgreSQL schema auto-created)
- `binding_id(id serial pk, original_id, original_channel, mirror_id, mirror_channel, mirror_topic_id, source_topic_id, source_media_id)`; indexes `(original_channel, original_id)`, `(original_channel, mirror_channel)`. Row = `MirrorMessage`. Used for dedup, edits, deletes, reply chaining, link rewriting, sync_pins, replay integrity.
- `past_mode_checkpoint(source_channel, target_channel, last_message_id)` PK (source,target).
- `broadcast_sync(source_channel, message_id, synced_edit_ts)` PK (source,message).
- `post_fingerprint(target_channel, target_topic, fingerprint, original_channel, original_id, created_at)`; indexes `(target_channel, fingerprint)`, `(created_at)`; pruned hourly by each mirror for its own sources/targets only.
- `Database` ABC methods: `insert_batch, get_messages, get_messages_batch, delete_messages_for_channels_batch, get_messages_for_channel_pair, update_source_media_id, get/set/delete_past_mode_checkpoint, delete_bindings_for_mirror, get/set/delete_broadcast_sync, seen_fingerprint, remember_fingerprint, prune_fingerprints, close`.
- `InMemoryDatabase`: `LRUCache` of 100 source messages for the whole process (trims to half when exceeded) — dedup/edit/delete break silently past it; selfcheck warns.

### JSON state files
- `failed.json`: list of `{id (sha1(chat:first_id)[:8]), at, chat, ids[], link, targets: [{chat, topic, reason}]}`; `chat: 0` (`ALL_CHATS`) = broke off before any target.
- `stats.json`: `{"pairs": [[src, tgt]…], "days": {"YYYY-MM-DD": {"src>tgt": [sent, filtered, dup, failed]}}}`; a day with `{}` = mirror ran without posts.
- `chats.json`: `{"<chat id>": "title"}` (merged, several writers, atomic per-pid tmp).
- `access.json`: `{"at": ts, "chats": [{id, title, roles[source|target|broadcast], ok, reason(not_member|cannot_post), note(noforwards)}]}`.
- `projects/.resume.json`: `[{"after": unit, "resume": [live units], "at": ts, "seen": bool}]`.
- `requests/`: empty files named `<entry id>`, `all`, `clear`.

### Sessions
`sessions/<phone>.jsession` (0600): `{"auth_key": <Telethon StringSession>, "account": {first_name,last_name,user_id,added_at,phone_number,username}, "application": {api_id, api_hash, device_name, app_version, sdk, lang_pack, system_lang_code}, "proxy", "password": null, "registered_at"}`. An overwritten file is kept as `<file>.<ts>.bak`. `<file>.lock` = flock holder (pid + argv). New sign-ins use the Telegram Desktop fingerprint (`api_id 2040`).

---

## 6. Mirroring pipeline

### Live mode (`telemirror/mirroring.py`)
1. `Telemirror.__init__`: album event delay set to 1.01 s; client with `connection_retries=1000`, `flood_sleep_threshold=300`.
2. `Mirroring.__connect_client`: attach `NoticeLogHandler` to logger `telemirror` → connect (30 s bound) → `get_me` (no auth → RuntimeError) → `READY=1` → watchdog task → register `EventHandlers` for `chats=list(CHAT_MAPPING)` (before broadcast sync on purpose) → sink loop → `chats.json` → broadcast sync → `run_until_disconnected`. Ban/deactivation/session revoked → CRITICAL log (→ notice) and exit (→ systemd restart/alert).
3. `on_new_message` skips album items (handled by `on_album`); `on_edit_message` skips `edit_hide` (reactions); `on_deleted_message` → `delete_message`.
4. `new_message` / `new_album` fan-out (per target chat, per matching `DirectionConfig`):
   - service messages skipped; quiz polls copied as plain polls;
   - topic routing `_matches_from_topic` (`topic_id_of`: `reply_to_top_id` or `reply_to_msg_id` when `forum_topic`, else General=1);
   - per-target dedup `already_mirrored` from `binding_id` keyed `(mirror_channel, source_topic_id, mirror_topic_id)` with legacy-row fallback (prevents duplicates on redelivery/past retries);
   - `noforwards` source blocked unless the chain has `restricted_content_allowed` and mode is copy;
   - `dedup_hours` repeat check (fingerprint) → outcome `dup`;
   - message copy → in copy mode `_rewrite_links` **before filters** (t.me/c/…, t.me/<user>/…, telegram.me/dog, topic segment; resolved to the target's own mirror via DB, else `fallback_link_url`; per-event link cache; username → id LRU 256);
   - `config.filters.process()` → DISCARD = `filtered`; filter exception = this target fails, others continue; FloodWait/MediaDownloadError propagate (after flushing inserted rows);
   - reply chain to the mirrored parent in the same topic (`_resolve_reply_target`, ambiguity → top-level in target topic);
   - send: copy = patched `send_message` (entities, `invert_media`, `message_effect_id`, `reply_to_topic_id`) / `send_file` album; forward = patched `forward_messages` of the pristine original;
   - `FileReferenceExpiredError` → refetch source (`fetch_fresh_media`) once; filter-uploaded items kept (`_keep_filter_uploads`);
   - `MediaCaptionTooLongError` → send media with empty caption + caption text as a reply (`_send_with_caption_split`, tail sent with bounded FloodWait retry, tail not tracked);
   - `track_media` writes `binding_id` **before** `send_delay` sleep; remembers fingerprint.
   - In-flight futures (`_fanout_inflight`) let edit/delete wait for a running fan-out.
5. `edit_message`: waits for fan-outs (+1.5 s grace for fresh album items), for each mirror row picks the producing config (`_configs_to_try_for_topic`), skips `disable_edit` or forward mode, drops media for caption-only edits / voice/sticker (no re-download), rewrites links, runs filters, `client.edit_message`; caption too long → keep mirror caption; records new `source_media_id`; FloodWait → gives up for that mirror (no retry).
6. `delete_message`: waits for fan-outs (+grace), groups mirror ids per channel honoring `disable_delete`, deletes, then purges exactly those rows; per-channel failures leave rows for later.
7. `_sync_broadcast_channel` (startup, if a broadcast channel is set): walks full history, sends new, edits those whose `edit_date` advanced, deletes mirrors of posts gone (re-checked by id), tracked in `broadcast_sync`. Targets added later are not backfilled.

### Past/history mode (`telemirror/past.py`)
- Pairs = (source,target) with any `past_mode` direction; all topic-directions of a pair in one pass (first strategy wins, warning if they differ).
- Strategies: `last_n` (buffer newest `last_n+10` keeping albums whole, reverse) or bounded resume by raw-message budget; `since_date` (`offset_date`, reverse); `full_history` (reverse). Resume via `min_id=checkpoint`; checkpoint is never rolled forward to the max mirrored id (live mirror may have filled gaps).
- `EventProcessor(strict_media_errors=True)`, chat_mapping overridden to the one pair; checkpoint after each message/album; progress logs every 25 + overall ETA; `send_delay` between messages.
- `_replay_with_retry`: FloodWait > 300 s → sleep and retry (give up after 20 consecutive at the same checkpoint → exit, systemd alerts); `MediaDownloadError` → wait 120 s, retry ≤5, then skip the message/album, notify admins.
- Second pass `_edit_links_pass`: rewrites cross-channel links in already-sent mirrors (only when changed, skips caption-split mirrors, waits out FloodWait once).
- Watchdog = connection probe only. SIGTERM → exit 143 (clean stop, not "finished"). No `LiveSink`: replay failures are not added to `failed.json`, and replay logs are not pushed to admins via `NoticeLogHandler` (only the skip notice + watcher/alert).

### Albums
Telethon `events.Album` with `_HACK_DELAY=1.01 s`; history uses `iter_message_groups`. Album filters run per item (`MessageFilter._process_album`; any DISCARD drops the whole album). Caption split for albums handles per-item captions. Album retry ids = all item ids.

### Filter pipeline (`telemirror/messagefilters/`)
`FilterAction`: `CONTINUE`, `FORCE_SEND` (stop chain, send), `DISCARD`. `CompositeMessageFilter` applies in order; `restricted_content_allowed` = any member allows. Filters are named in YAML by class name (`getattr(messagefilters, name)`).

| Filter | Parameters (defaults) | Behaviour |
|---|---|---|
| `EmptyMessageFilter` | — | no-op (default when no `filters:`) |
| `SkipAllFilter` | — | discard everything («Пауза») |
| `SkipUrlFilter` | `skip_mention=True` | discard posts with a link preview, URL/TextUrl entity, or (opt.) mention |
| `SkipWithUrlFilter` | `blacklist: Set[str]` (required) | discard if preview URL / TextUrl / bare URL / @mention matches a prefix; normalizes scheme, t.me/telegram.me/dog/www, `<name>.t.me`, `t.me/s/`, `tg://resolve?domain=` |
| `SkipWithKeywordsFilter` | `keywords: Set[str]` (required, non-empty) | discard if any keyword (whole-word literal or `r'regex'`, case-insensitive) found |
| `AllowWithKeywordsFilter` | `keywords: Set[str]` | pass only posts with a keyword |
| `UrlMessageFilter` | `placeholder="***"`, `blacklist=None` (all URLs), `whitelist=None`, `filter_mention: bool|Set[str]=False`, `filter_by_id_mention=False` | replace matching URLs/mentions with placeholder, fix entities |
| `KeywordReplaceFilter` | `keywords: Dict[str,str]` (word or `r'regex'` → replacement, group refs validated) | replace in plain text, entity offsets updated |
| `StripFooterFilter` | `max_lines=3` (≥1) | cut trailing ≤100-char lines with links/@mentions + separators; drop preview if its link was in the tail; never empties a media-less post |
| `ForwardFormatFilter` | `format="{message_text}\n\nForwarded from [{channel_name}]({message_link})"` (must contain `{message_text}`; also `{sender_title}`, `{sender_username}`) | markdown header/footer; album edits keep the header on the item that carries it |
| `MappedNameForwardFormat` | `mapped: Dict[int,str]`, `format` | same with own channel names (hand-written only in panel) |
| `RestrictSavingContentBypassFilter` | — | for `noforwards` sources: download + re-upload media (≤2 GB; unsupported doc → DISCARD on failure); `restricted_content_allowed=True`; must come after WatermarkRemovalFilter |
| `DocumentFilenameFilter` | `suffix=""` (`{name} - {suffix}`), `remove: List[str]=None` (case-insensitive, brackets/separator cleaned) | rename document files (not stickers/voice/round/GIF); re-uploads plain documents |
| `WatermarkRemovalFilter` | `channels: List[int]=None` + `WatermarkConfig`: `remove_watermark=True`, `stamp_watermark=True`, `template_path`, `match_threshold=0.31`, `scale_min=0.2`, `scale_max=1.0`, `scale_steps=80`, `inpaint_dilate_px=6`, `stamp_watermark_path=my_watermark.png`, `stamp_opacity=0.55`, `stamp_scale=0.35`, `stamp_video_max_duration_s=300`, `stamp_video_preset="veryfast"`, `stamp_video_crf=18`, `stamp_video_max_encode_s=180`, `stamp_video_encode_realtime_ratio=0.73`, `max_concurrent_video_encodes=1` (process-wide) | photos: detect + LaMa inpaint and/or stamp; videos: ffmpeg delogo and/or overlay re-encode (H.264, faststart), skipped if too long or predicted encode too slow; video stickers never touched |

Shared media machinery (`_media.py`): `download_media_with_retry` (delays 15,45,90,180,300,600 s for Telethon's "Request was unsuccessful" errors) → `MediaDownloadError`; `strict_media_mode` ContextVar (past = raise, live = fall back to original media); `reupload_errors` decorator; `ReuploadCache` (TTL 600 s, 16 entries, single-flight per source media id, shared across fan-out targets); `UPLOAD_LIMIT_BYTES = 2 GiB`; temp files `telemirror-tmp-*`.

Panel ordering rule (`bot/filtercatalog.py`): cheap skip filters first, then `StripFooterFilter`, then transforming/media filters.

### Dedup layers
1. Per target/topic "already mirrored" via `binding_id` (always on).
2. `dedup_hours` cross-source repeat detection via `post_fingerprint` (text+media ids; media-only re-uploads not caught; lookup failure = not a repeat).
3. Broadcast sync idempotency via `broadcast_sync`.

### Restrict-saving (`noforwards`) handling
Source with `chat.noforwards`: forward mode never works; copy works only if the chain contains `RestrictSavingContentBypassFilter` (re-upload). Otherwise warning "Forwards … with `restricted saving content` … are not supported" and the target is skipped (not counted). `check_access` flags such sources; `restrict_saving` task enables `noforwards` on *our* targets.

### Rate limits / flood
- Telethon auto-sleeps FloodWait ≤300 s everywhere. Larger: live send → propagates out of the fan-out (rows flushed), recorded as failed post (retryable); edit → give up for that mirror; delete → per-channel error; replay → retry loop; tasks → `safe_call` waits it out; panel retries → stop processing requests, rest stay.
- Pacing: `send_delay` per direction (default 0.5 s), `BROADCAST_SEND_DELAY`, `past_mode.send_delay`.
- Video encodes limited to 1 at a time, photo inpainting 1 at a time (1 vCPU host).

### Failure handling & replay of failed posts
- `Outcomes` per fan-out; `LiveSink.record` counts every target state in `stats.json`, upserts failed targets into `FailedQueue` (removed when a later attempt fully succeeds).
- One summary notice per minute instead of per-error notices (log records carry `extra={"notice": False}`).
- Panel ♻️ → request file → `Mirroring._handle_requests` (every 15 s) → `_retry`: refetch from source; gone → forgotten; else `sink.retrying` (un-counts the old failure) and re-run `new_message/new_album` (targets already holding it are skipped by `already_mirrored`).

---

## 7. Ops features

- **Health endpoint**: aiohttp `GET /` → 204 on project port (selfcheck probes it).
- **systemd watchdog**: `WatchdogSec=600`, ping every 300 s if `connection_probe` is healthy (connected, `updates.GetState` within 30 s, tolerates 3 failures, FloodWait = healthy, disconnected ≤30 min tolerated). Live mirror warns after 2 h without any update (`WATCHDOG_SILENCE_WARN_SEC`), no restart.
- **Alert** (`telemirror.alert`, `OnFailure=` on mirror, past, task, panel, restart service): message + last 15 journal lines + hostname/UTC stamp.
- **Health timer** (`telemirror.health`, 10 min): ≥3 restarts since last check, or two checks in a transitional state.
- **Restart timer**: daily 04:00 `try-restart telemirror@*` (only running mirrors).
- **Weekly report** (`telemirror.report`, Mon 10:00): totals (copied / filtered / repeats / send errors), silent directions, top-5 failing, filters dropping ≥90% of ≥10 posts, waiting retries (+ buttons). "Зеркало всю неделю не работало" when no day recorded.
- **Self-check** (`telemirror.selfcheck` / 🧾): ✅/⚠️/❌/⚪ lines; never connects sessions (AUTH_KEY_DUPLICATED risk); loads each project's config in a subprocess.
- **Stale/watchdog in panel**: 🔇 mark on directions silent ≥7 days (`stats.quiet_days`), "last post" on direction card; "⚠️ Изменения ещё не применены" on card.
- **Session lock**: refuses a second process per session (waits 30 s).
- **Notifications**: see §4.
- **Logging**: stdout handlers (`misc/log_setup.py`, format `LEVEL time [file:line]:logger: msg`, no propagation), loggers `telemirror`, `past_mode`, `telethon` (WARNING), `bot`, `aiogram` (WARNING); journald captures (capped 500 MB). Panel progress lines are read back from the journal (`journalctl --grep`).
- **Memory guards**: `MemoryHigh=1100M/MemoryMax=1400M` per mirror/past/task, 600M panel; swap 2 GB.
- **Temp cleanup**: `PrivateTmp` + hourly cron.

---

## 8. Feature list

| Feature | Status | Files |
|---|---|---|
| Live copy/forward of posts (1→1, N→1, N→M) | done | `telemirror/mirroring.py`, `live.py`, `config.py` |
| Forum topic → topic routing, replies kept in topics | done | `mirroring.py`, `misc/topics.py`, `_patch/sending.py` |
| Albums (live + history) | done | `mirroring.py` (`new_album`), `misc/message_groups.py`, `_patch/album.py` |
| Edit sync (text, caption, media replacement) | done | `mirroring.py` (`edit_message`) |
| Delete sync | done | `mirroring.py` (`delete_message`) |
| Reply chaining to mirrored parent | done | `mirroring.py` (`_reply_target_mirrors`) |
| Cross-channel t.me link rewriting + fallback link | done | `mirroring.py` (`_rewrite_links`), `past.py` (`_edit_links_pass`) |
| Caption-too-long split | done | `mirroring.py` |
| File-reference refresh | done | `mirroring.py`, `messagefilters/_media.py` |
| Broadcast channel to all/whitelisted targets + startup sync | done | `config.py`, `mirroring.py` (`_sync_broadcast_channel`) |
| History replay (last_n / since_date / full) with checkpoints | done | `past.py`, `storage.py` |
| Filter pipeline (13 filters) | done | `messagefilters/*` |
| Watermark removal (photo LaMa, video delogo) | partial (needs Linux+torch, template file not in repo; noted untested on VPS in memory) | `messagefilters/watermarkfilter.py`, `watermark/processor.py` |
| Own watermark stamping (photo/video) | done | same |
| Restrict-saving bypass (re-upload) | done | `messagefilters/restrictsavingfilter.py` |
| Document renaming | done | `messagefilters/documentfilenamefilter.py` |
| Cross-source dedup (`dedup_hours`) | done (not verified on VPS) | `dedup.py`, `storage.py`, `mirroring.py` |
| Not-copied posts list + retry from panel | done (not verified on VPS) | `failed.py`, `sink.py`, `outcomes.py`, `bot/routers/failed.py` |
| Per-day stats + weekly report | done (not verified on VPS) | `stats.py`, `report.py`, `deploy/systemd/telemirror-report.*` |
| PostgreSQL + in-memory DB | done | `storage.py` |
| Projects (multi-mirror) + migration | done | `projects.py` |
| Multi-account sessions, sign-in by phone, session import (tdata/.session/.jsession) | done | `login.py`, `misc/session_import.py`, `misc/jsession.py`, `bot/routers/accounts.py` |
| One-process-per-session lock + panel turn-taking | done | `misc/session_lock.py`, `bot/turns.py` |
| Control panel: projects, directions, filters, params, broadcast | done | `bot/routers/*`, `bot/configedit.py`, `bot/configstore.py` |
| Safe config writes (round-trip, validate, .bak, sha guard, rollback, upload) | done | `bot/configstore.py`, `bot/routers/config_file.py` |
| Panel history replay control + progress | done | `bot/routers/replay.py` |
| Maintenance tools from panel (dry-run gated) | done | `bot/routers/maintenance.py`, `telemirror/tasks/*`, `telemirror-task@.service` |
| Access check report | done | `tasks/check_access.py`, `bot/routers/maintenance.py` |
| Pin sync | done (requires Postgres + prior replay) | `tasks/sync_pins.py` |
| Restrict saving on targets | done | `tasks/restrict_saving.py` |
| Anonymize groups | done | `tasks/anonymize_groups.py` |
| Clear channels + DB reset | done | `tasks/clear_channels.py` |
| Citadel setup wizard | done (CLI-only, project-unaware, hard-coded names) | `tasks/setup_mirrors.py` |
| Unit list / journals / status in panel | done | `bot/routers/tasks.py`, `bot/systemd.py` |
| Push notifications (watcher, alerts, log notices, private messages) | done | `bot/watcher.py`, `notify.py`, `alert.py`, `mirroring.NoticeLogHandler` |
| Health/flapping timer, daily restart, timers toggle in panel | done | `health.py`, `deploy/systemd/*`, `bot/routers/settings.py` |
| Self-check | done (not verified on VPS) | `selfcheck.py`, `bot/routers/settings.py` |
| systemd watchdog (live + past) | done | `misc/sdnotify.py`, `misc/telegram_client.py` |
| Chat titles cache for panel | done | `projects.py` (`chats.json`), `mirroring._save_chat_names` |
| Silent-direction marks / last post | done | `bot/routers/directions.py`, `stats.py` |
| Premoderation, ads, delays, "where is the copy?" | not started (proposed backlog) | — |

---

## 9. Known limitations / architectural constraints (observations)

- **YAML is the source of truth; read once at import.** Any config change (panel or hand) takes effect only after a restart of the mirror (🔁 Перезапустить, or the 04:00 restart). The card shows "Изменения ещё не применены" by comparing config mtime with `ActiveEnterTimestamp`.
- **Project-wide settings in the panel**: edits/deletes/mode/link/dedup/history are set for all directions at once; per-direction overrides exist only when hand-written in YAML (panel shows ✳️ but doesn't edit them). `MappedNameForwardFormat` and args of unknown types are file-only.
- **Single operator model**: flat admin list in `.env`, no roles/audit; panel runs as root. FSM, cooldowns, dry-run gating and sync_pins options live in memory (lost on panel restart; a real task run then needs a new dry-run).
- **One process per session**: projects sharing an account cannot mirror simultaneously; a replay/task pauses the project's (and session-mates') live mirror.
- **No catch-up of posts missed while a mirror is down** (observation): clients use an in-memory `StringSession` and `catch_up` is never enabled, so source posts published while the live mirror is stopped (restart, crash-loop, a replay/task pause, a session-mate running) are not mirrored live; only the broadcast channel is re-synced at start. Gaps need a history replay (`past_mode`, deduped by `binding_id`). Edits/deletes during downtime are likewise missed.
- **Shared PostgreSQL** for all projects (no per-project schema); in-memory DB capacity is 100 messages process-wide (unsafe for 24/7).
- **Linux/systemd only** for the panel's unit control, health, selfcheck and alerts; macOS dev runs lack watermark removal (no torch wheels).
- **Resource limits**: 1 vCPU / 2 GB target host; video stamping blocks for minutes; encodes serialized; each project's mirror is its own process (~RAM per project).
- **Broadcast sync** pages the whole channel history on every start; targets added later are not backfilled; a failed first send is marked synced.
- **Edits**: no retry on FloodWait; forward-mode mirrors never edited; caption-split tail texts are untracked (not edited/deleted).
- **History replay** has no failed-post tracking (`failed.json`) and does not push its warnings to admins (only the skip notice and unit finish/failure).
- **Failed-post retry** needs the live mirror running (requests are file-polled every 15 s); `failed.json` keeps ≤300 entries/14 days.
- **dedup_hours** cannot detect re-uploaded media (different file ids); lookup errors default to "send".
- **Panel validation cost**: each save spawns `python -c "import telemirror.config"` (cv2/numpy load, seconds, ~600 MB cap on the panel unit).
- **Legacy/hard-coded paths**: `restrict_saving` always also reads `.configs/citadel_courses.config.yml`; `setup_mirrors` writes `.configs/mirror.config.yml` regardless of project; production configs are tracked in git under `.configs/`.
- **Watermark detection** needs a template file per source (`reference_watermark.png` default absent); settings of `max_concurrent_video_encodes` are process-wide (first seen wins).
- **Account safety**: running a userbot on mirrored `noforwards` content risks bans (README warning); a ban leads to crash-loop → alert → re-sign-in via panel.
- **Notifications** require admins to have pressed /start; if `PANEL_BOT_TOKEN`/`PANEL_ADMIN_IDS` are missing there are no alerts at all (only journal).
- **Process status per memory notes**: many recent passes (panel, failed posts, report, selfcheck, dedup) are marked "не проверено на VPS"; commits/pushes require explicit user permission and go straight to `master`.
