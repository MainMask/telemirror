# Telegram message forwarder (client API)

### Functionality
- Live forwarding and updating messages
- Source and target channels/chats/topics (one-to-one, many-to-one, many-to-many) mapping
- Incoming message filters: word replacing, forward formating, skipping by keyword and more

## Prepare

1. [Create Telegram App](https://my.telegram.org/apps)

2. Obtain **API_ID** and **API_HASH**

    ![Telegram API Credentials](/README.md-images/telegramapp.png)

3. Get a session

    Run `python -m telemirror.login`: it logs in interactively (phone, code, 2FA password) with the Telegram Desktop app profile and saves `sessions/<phone>.jsession` (`python -m telemirror.login --import PATH` takes an account already signed in elsewhere instead: a `tdata` folder or its ZIP, a `.session` with its `.json`). Pick it as a project's account in the panel (or set `SESSION_FILE=sessions/<phone>.jsession` in `.env` for a run without a project). The file carries the session **and** the app credentials/fingerprint, so `API_ID`/`API_HASH`/`SESSION_STRING`/`API_*` are not needed with it. The 2FA password is not stored. ❗ **DON'T USE** your own account.

4. Setup Postgres database or use `InMemoryDatabase` with `USE_MEMORY_DB=true` parameter in `.env` file

5. Fill `.env` with your data

    [.env-example](.env-example) contains the minimum environment configuration to run with an in-memory database.

    > ⚠️ The `.jsession` file (and `SESSION_STRING` in `.env`) is full access to the Telegram account. `telemirror.login` writes it as `chmod 600`; do the same for `.env` on a shared host. Both `*.jsession` and `sessions/` are git-ignored.

    <details>
    <summary><b>.env</b> overview</b></summary>

    ```bash
    ###########################
    #    App configuration    #
    ###########################
    
    # Session file from telemirror.login; replaces API_ID/API_HASH/SESSION_STRING/API_* below
    SESSION_FILE=sessions/79990000000.jsession
    # --- or, without a file ---
    # Telegram app ID
    API_ID=test
    # Telegram app hash
    API_HASH=test
    # Telegram session string (the `auth_key` of a .jsession file)
    SESSION_STRING=test
    # Use an in-memory database instead of Postgres DB (true or false). Defaults to false
    USE_MEMORY_DB=false
    # Postgres credentials
    DATABASE_URL=postgres://user:pass@host/dbname
    # or
    DB_NAME=test
    DB_USER=test
    DB_HOST=test
    DB_PASS=test
    # Logging level (debug, info, warning, error or critical). Defaults to info
    LOG_LEVEL=info
    # The next optional parameters can be set to prevent bans/logouts.
    # Leave them out entirely to use the platform defaults.
    # See: https://github.com/LonamiWebs/Telethon/issues/4051
    # API_SYSTEM_VERSION=4.16.30-vxCUSTOM   # default: platform.uname().release
    # API_DEVICE_MODEL=Desktop              # default: platform.uname().machine
    # API_APP_VERSION=1.0                   # default: telethon.version.__version__
    ```

    See [.env-example](.env-example) for the full list (broadcast sync, delays).
    </details>

6. Setup mirror forwarding config:

    [mirror.config.yml-example](./.configs/mirror.config.yml-example) contains an example config: to set up a filter, specify the name of the filter (should be accessable from `./telemirror/messagefilters`) and pass named parameters with the same types but in yaml syntax. Example:

    ```yaml
    - ForwardFormatFilter:  # Filter name under telemirror/messagefilters
        # Filter string argument
        format: "{message_text}\n\nForwarded from [{channel_name}]({message_link})"

    - SkipUrlFilter:
        skip_mention: false # Filter bool argument

    - UrlMessageFilter:
        blacklist: !!set    # Filter set argument
            ? t.me
            ? google.com
    ```

    The mirror config is a YAML file: a project's own (`projects/<key>/project.yml` names it; the panel edits it), or `./.configs/mirror.config.yml` for a run without a project.

    <details>
    <summary><b>./.configs/mirror.config.yml</b> mirroring config overview</summary>

    ```yaml
    # (Optional) Global filters, will be applied in order
    filters:
      - ForwardFormatFilter: # Filter name under ./telemirror/messagefilters
          format: "{message_text}" # Filters arguments
      - EmptyMessageFilter
      - UrlMessageFilter:
          blacklist: !!set
            ? t.me
      - SkipUrlFilter:
          skip_mention: false

    # (Optional) Global settings
    disable_edit: true
    disable_delete: true
    mode: copy # or forward

    # (Required) Mirror directions
    directions:
      - from: [-1001, -1002, -1003]
        to: [-100203]

      - from: [-1000#3] # forwards from topic to topic
        to: [-1001#4]

      - from: [-100226]
        to: [-1006, -1008]
        # Overwrite global settings
        disable_edit: false
        disable_delete: false
        mode: forward
        # Overwrite global filters. mode: forward always sends the pristine
        # original, so only decision-only filters (skip/allow, no content
        # mutation) are valid here — a filter that rewrites text/media
        # (UrlMessageFilter, KeywordReplaceFilter, WatermarkRemovalFilter, ...)
        # requires mode: copy, and fails config loading if paired with forward.
        filters:
          - SkipWithKeywordsFilter:
              keywords: !!set
                ? "stopword"     # treat keyword as word
                ? "r'badword.*'" # treat keyword as regex expr
    ```
    </details>

    ❓ Channels ID can be fetched by using [Telegram bot](https://t.me/messageinformationsbot).

    ❗ Note: never push your `.env` or a session file to a public repo.

7. Make sure the account has joined source and target channels

8. **Be careful** with forwards from channels with [`RESTRICTED SAVING CONTENT`](https://telegram.org/blog/protected-content-delete-by-date-and-more). It may lead to an account ban

## Deploy

### Linux VPS (supported)

systemd units for every project's mirror, history replay and maintenance runs, the control panel, alerts and timers: see [deploy/README.md](deploy/README.md) (`deploy/bootstrap.sh` installs them). `python -m telemirror.selfcheck` (or ⚙️ Настройки → 🧾 Проверка установки in the bot) checks the installation afterwards.

### Locally (macOS)
1. Create and activate python virtual environment

    ```bash
    python3.13 -m venv .venv
    source ./.venv/bin/activate
    ```
2. Install dependencies via [install.sh](install.sh) (handles broken pillow pin in simple-lama-inpainting)

    ```bash
    bash install.sh
    ```
3. Run

    ```bash
    TELEMIRROR_PROJECT=<key> python -m telemirror.live   # a project's live mirror
    python -m telemirror.live                            # or: SESSION_FILE + .configs/mirror.config.yml
    ```

> ⚠️ **Note:** Watermark removal (LaMa inpainting) does **not** work on macOS — PyTorch does not publish binary wheels for Intel Mac, and Apple Silicon wheels are unavailable for Python 3.13. Photos are forwarded as-is (without removing the source watermark). Watermark removal needs Linux with torch installed.

## Optional features

The following environment variables (the channels also as YAML keys — the YAML wins) extend the base functionality. All are optional. See [.env-example](.env-example) and [.configs/mirror.config.yml-example](.configs/mirror.config.yml-example) for full examples.

| Variable | Default | Description |
|---|---|---|
| `BROADCAST_CHANNEL` | — | Channel ID whose messages are broadcast to **all** configured targets on startup (full sync) and live. Copied as they are: the YAML `filters:` and `mode:` don't apply to them. |
| `BROADCAST_TARGETS` | all targets | Comma-separated whitelist of targets for broadcast (`-100id` or `-100id#topic_id`). When unset, goes to all targets. |
| `BROADCAST_SEND_DELAY` | `0.5` | Delay (seconds) between sends during broadcast sync. |
| `SEND_DELAY` | `0.5` | Delay (seconds) between sends for live mirroring directions. |

> ⚠️ `USE_MEMORY_DB=true` holds at most 100 tracked messages for the whole process (not per channel). Beyond that, LRU eviction can silently break dedup, delete, and edit-reply lookups for older messages, not just `BROADCAST_CHANNEL` resync on restart — use PostgreSQL for a 24/7 deployment. Copying a not-copied post again (below) also relies on it: with the in-memory database, after a restart the post may land twice in the channels that already had it.

### Not-copied posts, the weekly report, repeats

A live mirror run as a project keeps, in `projects/<key>/`:

- `failed.json` — the posts it couldn't copy to some channel (the reason per channel; the last 300, up to 14 days). Instead of an error notice per send, the panel's admins get one summary a minute at most («❗ Не скопировано постов: N…») with **♻️ Повторить все** and **❗ Не скопировано** (the project's screen: copy one or all again, or clear the list). The panel only drops a request file into `projects/<key>/requests/`; the mirror picks it up within 15 s, fetches the post from the source again and sends it only where it's missing.
- `stats.json` — per-day counters by direction (copied, dropped by the filters, repeats, failed sends), 35 days. `python -m telemirror.report` (`telemirror-report.timer`, Mondays 10:00; ⚙️ Настройки → 📈 Сводка за неделю) sends each project's week: totals, directions that got nothing, the most failing ones, the ones where the filters drop ≥90%.

`dedup_hours: N` (YAML, project-wide or per direction; ⚙️ Настройки проекта → 🧬 Без повторов) — a post a channel already got from another source post within N hours isn't copied there again: the same text and the same photos/videos (a post without media — the same text of 20+ characters). The fingerprints are in the `post_fingerprint` table. A re-uploaded photo is another file, so it isn't caught. History replay (`telemirror.past`) honours it too.

## Replaying past messages (`telemirror.past`)

`python -m telemirror.past` replays a channel's history through the mirror pipeline for the directions that have `past_mode:` in the mirror config.

```bash
TELEMIRROR_PROJECT=<key> python -m telemirror.past   # what the bot's ⏪ История runs
```

It takes the project's session (a second process on one session refuses to start — the panel pauses the project's mirror meanwhile). Progress is checkpointed after each message: if interrupted, re-running resumes from where it left off. A second pass rewrites cross-channel links in already-sent messages.

## Maintenance tasks (`telemirror.tasks`)

> ⚠️ All tasks use the project's session (`TELEMIRROR_PROJECT=<key>`): in the panel (🛠 Инструменты) its mirror is paused for the run; by hand, stop it first — a second process on one session refuses to start.

| Task (`python -m telemirror.tasks.…`) | Description |
|---|---|
| `setup_mirrors` | Interactive wizard for the "⚜️ Цитадель" set: discovers donors from hardcoded name lists, creates the recipient channels/forum topics + copies avatars, then generates the config — live directions are merge-appended to `.configs/mirror.config.yml` (comments preserved, old file backed up to `*.bak`), course-only directions go to `.configs/citadel_courses.config.yml`. Idempotent, safe to re-run after a FloodWait. |
| `clear_channels` | Purges all messages in recipient channels/topics, then resets the `past_mode_checkpoint` and `binding_id` rows for the cleared targets (plus the broadcast channel's `broadcast_sync` state when a cleared target receives broadcasts, so the next start re-delivers the admin posts to it). Supports `--dry-run`; `--yes` skips the confirmation prompt (used by the control panel). |
| `sync_pins` | Mirrors donor pinned messages onto their recipient mirrors using the `binding_id` table (needs PostgreSQL + a prior history replay). Reconcile mode by default (also unpins what the donor unpinned, only among mirror-managed pins); `--additive` disables unpinning, `--dry-run` shows the plan; `--max-pins N` / `--only DONOR_ID` narrow it. |
| `anonymize_groups` | In every supergroup where the account is an admin: enables "Remain Anonymous" for the account, then "Hide Members" for the group (the latter only where Telegram allows it). Supports `--dry-run`; `--yes` skips the confirmation prompts (used by the control panel). |
| `check_access` | Read-only: checks that the account sees every source and the broadcast channel and may post in every recipient (from its own rights in its dialogs; topics aren't checked). Run as a project, writes `projects/<key>/access.json` for the panel. |
| `restrict_saving` | Enables "Restrict Saving Content" (`noforwards`) on every recipient channel/supergroup — live (`CHAT_MAPPING`) and course (`.configs/citadel_courses.config.yml`). Supports `--dry-run`; `--yes` skips the confirmation prompt (used by the control panel). |

## Projects and the control panel bot (`bot/`)

A **project** is an independent mirror: its own mirror config, its own Telegram
session (`sessions/*.jsession`) and its own systemd units
(`telemirror@<key>` — the live mirror, `telemirror-past@<key>` — history replay,
`telemirror-task@<key>` — maintenance). It lives in `projects/<key>/project.yml`
(name, icon, session, config, health port); `telemirror.live` / `telemirror.past`
run as a project with `TELEMIRROR_PROJECT=<key>`. Several projects may use one session —
they then run in turn (one process per session: a second one refuses to start).

The control panel is a separate Bot API bot (aiogram 3) that manages projects
from Telegram instead of SSH. Its UI is in Russian. It runs as its own process —
`python -m bot` / `telemirror-panel.service`; without `PANEL_BOT_TOKEN`
it exits immediately and nothing else changes. Supported deployment: the systemd VPS
setup from [`deploy/`](deploy/README.md) (it drives `systemctl`/`journalctl`).

| Variable | Description |
|---|---|
| `PANEL_BOT_TOKEN` | Token from @BotFather. Unset = panel disabled and no notices. Every notice goes through it (see below). |
| `PANEL_ADMIN_IDS` | Comma-separated Telegram user ids allowed to use the panel (required with a token; everyone else is ignored). |

The menu is data: `bot/registry.py` holds every screen, button,
hint and every other label (a form's choices, a list's rows); keyboards, screen
texts and menu paths are built from it, and the bot refuses to start with a
button nobody handles or a handler of a button it doesn't have. One emoji means
one thing across the bot (tests check every label); a screen's buttons sit under
subheadings (`Button.group`), and colours follow one rule: blue — the one step to
take now, red — what can't be undone (alone on its row), green — a confirmation.
How-it-works texts and technical details are folded (an expandable quote). ⬅️ Назад is always the last
row and returns to the page of the list it came from, ✖️ Отмена and `/cancel`
return to where a form began. A question comes first only when an action can't
be undone, deletes, or stops something else on the session (the confirmation
expires after 10 min); a check, a replay or a start on a free session just runs.

```
📁 Проекты — the list (state, directions) · ➕ Новый проект (name → icon → account)
└ 🪞 a project — ▶️ Запустить / ⏹ Остановить / 🔁 Перезапустить, 👉 the next step for a new one
   ├ 🔀 Направления — the list (channels by name, 🧹 / ✳️ = own filters / hand-written own settings),
   │   ➕ Добавить (source → targets → history), 🔎 Найти (by a channel's name or id),
   │   a direction: 📨 Откуда, 🎯 Куда (a channel list: add by id or a forwarded post, 🗑 one),
   │   ⏱ Пауза между постами, 🗑 Удалить, 🧹 Фильтры направления;
   │   📢 Рассылка (📢 Рассылка из канала, 📬 Куда рассылать)
   ├ 🧹 Фильтры — ➕ Добавить фильтр (Отсеять посты / Изменить посты), a filter (named for people):
   │   its lists (🗑 a value, ➕ Добавить), ☑️ toggles, 📝 values, 🔬 Тонкая настройка (rarely needed
   │   args), ⬆️ / ⬇️, 🗑 Удалить фильтр
   ├ ⏪ История — telemirror.past for the project (its mirror is paused meanwhile),
   │   Запуск: ▶️ Начать / ⏹ Прервать · Что и как: 📜 Что копировать (one choice for every
   │   direction), ⏱ Пауза при копировании
   ├ 🛠 Инструменты — 🛂 Проверка доступа (read-only), 🔒 Запрет копирования, 📌 Закрепы (Настройки
   │   запуска: flags, 📏 limit, 📍 Только источники), 🕶 Анонимность, 🧨 Очистка каналов — each the
   │   same: 🔍 Проверить, then ▶️ Выполнить; ⏹ Остановить while it runs; 📄 Журнал
   └ ⚙️ Настройки проекта — Копирование (for every direction): ✏️ Правки, ✂️ Удаления, ↔️ Режим,
       🔗 Ссылка вместо чужих · Проект: 🏷 Имя, 🎨 Значок, 👤 Аккаунт, 🗑 Удалить проект
       (moved to projects/.deleted/)
       └ 💾 Файл настроек — 📥 Скачать, 📤 Загрузить (diff + validation), ↩️ Откатить
📊 Задачи (/status) — every project's units and a unit's journal; its button opens where it's run
⚙️ Настройки — Присмотр за зеркалами: 🩺 / 🔁 timers on/off · 👤 Аккаунты: sessions, 🔑 Войти по номеру,
   📤 Загрузить сессию
```

- **Notifications** — the panel polls systemd every 30 s and messages the admins
  when a replay / maintenance run finishes, and when a mirror crashes and is
  restarted or comes back from `failed`. A unit entering `failed` is told once,
  by `telemirror.alert` (`OnFailure=`) — with its journal, even when the panel is
  down. The panel also brings back the mirrors paused for a run
  on their session. The mirrors send the rest themselves, through the same bot
  (`telemirror.notify`): their warnings and errors (repeats merged, at most 10 a
  minute), private messages to their account, a post a replay had to skip, and
  `telemirror.alert` / `telemirror.health` alerts — each signed with its project,
  with a 📊 Задача button. Admins must have pressed /start once.
- **Sign-in by phone** happens in the bot (number → code typed with spaces → 2FA
  password; 📲 sends a new code), with the Telegram Desktop profile `telemirror.login` uses;
  the messages with the code and the password are deleted, the password is never stored.
  A sign-in left unanswered is dropped (its connection closed) after 15 min.
- **An account signed in elsewhere** (📤 Загрузить сессию, or `python -m telemirror.login --import PATH`):
  a ZIP of a Telegram Desktop `tdata` folder (its local passcode is asked for if set), a
  Telethon `.session` with the seller's `.json` of the same name (sent together; its app and
  device are kept, the Telegram Desktop profile without it), a ZIP of those, or a `.jsession`.
  The key is reused as is — no 2FA password needed or stored — and saved as
  `sessions/<phone>.jsession` once a connection shows the account signed in; one account per
  upload, and a key already saved is refused without connecting. `tdata` is read by
  `opentele-ng` in a child process (it patches Telethon on import).

Config writes keep comments (ruamel round-trip), make a `*.bak`, refuse if the
file was edited by hand meanwhile, and are validated by importing `telemirror.config`
against the candidate in a subprocess (as the project's own service would) — an
invalid config is never written. Saved-but-unapplied changes also go live at the
daily 04:00 restart.

CLI-only by design: `telemirror.tasks.setup_mirrors` (`telemirror.login` itself too —
the bot signs in by phone on its own). Filters: any arg of a known type is edited in
the bot; adding `MappedNameForwardFormat` and args of other types (shown as
"меняется только в файле") go through 💾 Файл настроек → 📤 Загрузить.

A channel is given by its id, by a post forwarded from it, or picked with
📇 Выбрать из списка: 📺 Канал / 👥 Группа appear at the bottom (Bot API
`request_chat` — the admin's own chats; the main menu stays under them and is
back alone after the pick, or after the form is left without one). Every prompt that takes a channel has the button.

Channels are shown by their titles from `projects/<key>/chats.json`: the mirror
writes it at start (one `get_dialogs`), 🛂 Проверка доступа, a post forwarded
or a chat picked in the bot add to it. A channel not in it yet is shown by its id.

Edits, deletes, mode, the fallback link and the history are set once for all
the directions of a project (⚙️ Настройки проекта, ⏪ История); a
direction's own value of those can still be written in the file — the panel
shows it (✳️) but doesn't edit it.

Adding a filter to a direction without its own list copies the project's
filters into it first: a direction's own list replaces them. Deleting its last
own filter removes the list, and the direction is back on the project's.
