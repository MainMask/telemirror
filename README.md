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

    Run `python login.py`: it logs in interactively (phone, code, 2FA password) with the Telegram Desktop app profile and saves `sessions/<phone>.jsession` (`python login.py --import PATH` takes an account already signed in elsewhere instead: a `tdata` folder or its ZIP, a `.session` with its `.json`), then set `SESSION_FILE=sessions/<phone>.jsession` in `.env`. The file carries the session **and** the app credentials/fingerprint, so `API_ID`/`API_HASH`/`SESSION_STRING`/`API_*` are not needed with it. The 2FA password is not stored. ❗ **DON'T USE** your own account.

    `docker-compose.yaml` mounts `./sessions` read-only into the container. Where a file can't be used (Heroku), set `SESSION_STRING` to the file's `auth_key` and `API_ID`/`API_HASH` to its `application.api_id`/`api_hash` instead.

4. Setup Postgres database or use `InMemoryDatabase` with `USE_MEMORY_DB=true` parameter in `.env` file

5. Fill `.env` with your data

    [.env-example](.env-example) contains the minimum environment configuration to run with an in-memory database.

    > ⚠️ The `.jsession` file (and `SESSION_STRING` in `.env`) is full access to the Telegram account. `login.py` writes it as `chmod 600`; do the same for `.env` on a shared host. Both `*.jsession` and `sessions/` are git- and docker-ignored.

    <details>
    <summary><b>.env</b> overview</b></summary>

    ```bash
    ###########################
    #    App configuration    #
    ###########################
    
    # Session file from login.py; replaces API_ID/API_HASH/SESSION_STRING/API_* below
    SESSION_FILE=sessions/79990000000.jsession
    # --- or, without a file ---
    # Telegram app ID
    API_ID=test
    # Telegram app hash
    API_HASH=test
    # Telegram session string (the `auth_key` of a login.py .jsession file)
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

    See [.env-example](.env-example) for the full list (broadcast sync, past mode, tech channel, delays).
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

    `./.configs/mirror.config.yml` or `.env` (limited) can be used to configure mirroring:

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

    <details>
    <summary><b>.env</b> mirroring config overview</summary>

    ```bash
    ###############################################
    #    Setup directions and filters from env    #
    ###############################################

    # Mapping between source and target channels/chats
    # Channel/chat id can be fetched by using @messageinformationsbot telegram bot
    # Channel id should be prefixed with -100
    # [id1, id2, id3:id4] means send messages from id1, id2, id3 to id4
    # id5:id6 means send messages from id5 to id6
    # [id1, id2, id3:id4];[id5:id6] semicolon means AND
    CHAT_MAPPING=[-100999999,-100999999,-100999999:-1009999999];
    
    # (Optional) YAML filter configuration thru single-lined env string (new lines (\n) should be replaced to \\n), other filter settings from env will be ignored
    YAML_CONFIG_ENV=
    
    # Remove URLs from incoming messages (true or false). Defaults to false
    REMOVE_URLS=false
    # Comma-separated list of URLs to remove (reddit.com,youtube.com)
    REMOVE_URLS_LIST=google.com,twitter.com
    # Comma-separated list of URLs to exclude from removal (google.com,twitter.com).
    # Will be applied after the REMOVE_URLS_LIST
    REMOVE_URLS_WL=youtube.com,youtu.be,vk.com,twitch.tv,instagram.com
    # Disable mirror message deleting (true or false). Defaults to false
    DISABLE_DELETE=false
    # Disable mirror message editing (true or false). Defaults to false
    DISABLE_EDIT=false
    ```
    </details>

    **Channel mirroring config priority**:

    - `YAML_CONFIG_ENV` from `.env`

    - from `./.configs/mirror.config.yml` file

    - `CHAT_MAPPING, REMOVE_URLS, REMOVE_URLS_LIST, REMOVE_URLS_WL, DISABLE_DELETE, DISABLE_EDIT` from `.env` file

    ❓ Channels ID can be fetched by using [Telegram bot](https://t.me/messageinformationsbot).

    ❗ Note: never push your `.env`/`.yml` files with real crendential to a public repo. Use a separate branch (eg, `heroku-branch`) with `.env`/`.yml` files to push to git-based deployment system like Heroku.

7. Make sure the account has joined source and target channels

8. **Be careful** with forwards from channels with [`RESTRICTED SAVING CONTENT`](https://telegram.org/blog/protected-content-delete-by-date-and-more). It may lead to an account ban

## Deploy
<details>
    <summary><b>Heroku</b></summary>
<br>

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/MainMask/telemirror)

### or via CLI:

1. Clone project

    ```bash
    git clone https://github.com/MainMask/telemirror.git
    ```
2. Create new heroku app within Heroku CLI

    ```bash
    heroku create {your app name}
    ```
3. Add heroku remote

    ```bash
    heroku git:remote -a {your app name}
    ```
4. Set environment variables from your `.env` on the heroku app

    ```bash
    # requires the `heroku-config` plugin: heroku plugins:install heroku-config
    heroku config:push
    ```

5. Upload on heroku host

    ```bash
    git push heroku master
    ```

6. Start heroku app

    ```bash
    heroku ps:scale web=1
    ```

#### Keep up-to-date with Heroku

If you deployed manually, move to step 2.

0. Get project to your PC:

    ```bash
    heroku git:clone -a {your app name}
    ```
1. Init upstream repo (this repository or its fork)

    ```bash
    git remote add origin https://github.com/MainMask/telemirror
    ```
2. Get latest changes

    ```bash
    git pull origin master
    ```
3. Push latest changes to heroku

    ```bash
    git push heroku master -f
    ```
</details>

### Linux (recommended):

Use the provided [Dockerfile](Dockerfile) — it includes all dependencies (ffmpeg, torch, LaMa inpainting) and works out of the box.

### Locally (macOS):
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
    python main.py
    ```

> ⚠️ **Note:** Watermark removal (LaMa inpainting) does **not** work on macOS — PyTorch does not publish binary wheels for Intel Mac, and Apple Silicon wheels are unavailable for Python 3.13. Photos are forwarded as-is (without removing the source watermark). Watermark removal works only on Linux via Docker.

## Optional features

The following environment variables (and their YAML equivalents) extend the base functionality. All are optional. See [.env-example](.env-example) and [.configs/mirror.config.yml-example](.configs/mirror.config.yml-example) for full examples.

| Variable | Default | Description |
|---|---|---|
| `BROADCAST_CHANNEL` | — | Channel ID whose messages are broadcast to **all** configured targets on startup (full sync) and live. |
| `BROADCAST_TARGETS` | all targets | Comma-separated whitelist of targets for broadcast (`-100id` or `-100id#topic_id`). When unset, goes to all targets. |
| `BROADCAST_SEND_DELAY` | `0.5` | Delay (seconds) between sends during broadcast sync. |
| `TECH_CHANNEL` | — | Channel ID that receives WARNING+ log alerts and incoming DM notifications. |
| `SEND_DELAY` | `0.5` | Delay (seconds) between sends for live mirroring directions. |
| `PAST_MODE` | — | History to replay when `past_mode.py` is run (env-mode only; `main.py` never replays). Values: `last_n=N`, `full_history`, `since_date=YYYY-MM-DDTHH:MM:SS`. |

> ⚠️ `USE_MEMORY_DB=true` holds at most 100 tracked messages for the whole process (not per channel). Beyond that, LRU eviction can silently break dedup, delete, and edit-reply lookups for older messages, not just `BROADCAST_CHANNEL` resync on restart — use PostgreSQL for a 24/7 deployment.

## Replaying past messages (`past_mode.py`)

`past_mode.py` replays a channel's history through the mirror pipeline for directions that have `past_mode:` configured in the YAML config (or `PAST_MODE=` in env-mode).

```bash
# Stop main.py first — both use the same session (a second process on it refuses to start)
python past_mode.py

# a project's replay (what the bot's ⏪ Догрузка runs):
TELEMIRROR_PROJECT=<key> python past_mode.py
```

Progress is checkpointed after each message: if interrupted, re-running resumes from where it left off. A second pass rewrites cross-channel links in already-sent messages.

## Utility scripts (`skylon_set/`)

> ⚠️ All scripts use the same session as the main service (`TELEMIRROR_PROJECT=<key>` picks a project's). Stop its mirror before running them — a second process on one session refuses to start.

| Script | Description |
|---|---|
| `skylon_set/setup_mirrors.py` | Interactive wizard for the "⚜️ Цитадель" set: discovers donors from hardcoded name lists, creates the recipient channels/forum topics + copies avatars, then generates the config — live directions are merge-appended to `.configs/mirror.config.yml` (comments preserved, old file backed up to `*.bak`), course-only directions go to `.configs/citadel_courses.config.yml`. Idempotent, safe to re-run after a FloodWait. |
| `skylon_set/clear_channels.py` | Purges all messages in recipient channels/topics, then resets the `past_mode_checkpoint` and `binding_id` rows for the cleared targets (plus the broadcast channel's `broadcast_sync` state when a cleared target receives broadcasts, so the next start re-delivers the admin posts to it). Supports `--dry-run`; `--yes` skips the confirmation prompt (used by the control panel). |
| `skylon_set/sync_pins.py` | Mirrors donor pinned messages onto their recipient mirrors using the `binding_id` table (needs PostgreSQL + a prior `past_mode.py` run). Reconcile mode by default (also unpins what the donor unpinned, only among mirror-managed pins); `--additive` disables unpinning, `--dry-run` shows the plan; `--max-pins N` / `--only DONOR_ID` narrow it. |
| `skylon_set/anonymize_groups.py` | In every supergroup where the account is an admin: enables "Remain Anonymous" for the account, then "Hide Members" for the group (the latter only where Telegram allows it). Supports `--dry-run`; `--yes` skips the confirmation prompts (used by the control panel). |
| `skylon_set/check_access.py` | Read-only: checks that the account sees every source and the broadcast channel and may post in every recipient and the tech channel (from its own rights in its dialogs; topics aren't checked). Run as a project, writes `projects/<key>/access.json` for the panel. |
| `skylon_set/restrict_saving.py` | Enables "Restrict Saving Content" (`noforwards`) on every recipient channel/supergroup — live (`CHAT_MAPPING`) and course (`.configs/citadel_courses.config.yml`). Supports `--dry-run`; `--yes` skips the confirmation prompt (used by the control panel). |

## Projects and the control panel bot (`telemirror/panel`)

A **project** is an independent mirror: its own mirror config, its own Telegram
session (`sessions/*.jsession`) and its own systemd units
(`telemirror@<key>` — the live mirror, `telemirror-past@<key>` — history replay,
`telemirror-task@<key>` — maintenance). It lives in `projects/<key>/project.yml`
(name, icon, session, config, health port); `main.py` / `past_mode.py` run as a
project with `TELEMIRROR_PROJECT=<key>`. Several projects may use one session —
they then run in turn (one process per session: a second one refuses to start).

The control panel is a separate Bot API bot (aiogram 3) that manages projects
from Telegram instead of SSH. Its UI is in Russian. It runs as its own process —
`python -m bot` / `telemirror-panel.service`; without `PANEL_BOT_TOKEN` it exits
immediately and nothing else changes. Supported deployment: the systemd VPS
setup from [`deploy/`](deploy/README.md) (it drives `systemctl`/`journalctl`;
Docker/Heroku are not supported).

| Variable | Description |
|---|---|
| `PANEL_BOT_TOKEN` | Token from @BotFather. Unset = panel disabled. Also used for crash alerts (`telemirror.alert`). |
| `PANEL_ADMIN_IDS` | Comma-separated Telegram user ids allowed to use the panel (required with a token; everyone else is ignored). |

The menu is data: `telemirror/panel/registry.py` holds every screen, button and
its hint; keyboards, screen texts and menu paths are built from it, and the bot
refuses to start with a button nobody handles. One emoji means one thing across
the bot, ⬅️ Назад is always the last row, every destructive action asks first
(the confirmation expires after 10 min), ✖️ Отмена and `/cancel` return to where
a form began.

```
📁 Проекты — the list (state, directions) · ➕ Новый проект (name → icon → account)
└ 🪞 a project — ▶️ Запустить / ⏹ Остановить / 🔁 Перезапустить
   ├ 🔀 Направления — the list · ➕ Добавить · a direction: 📨 Источники, 🎯 Получатели,
   │   ✏️ Правки, ✂️ Удаления, ↔️ Режим, ⏱ Задержка, 📜 История, ⏱ Задержка догрузки, 🔗 Ссылка-замена,
   │   🧹 Фильтры направления, 🗑 Удалить
   ├ 🧹 Фильтры — ➕ Добавить фильтр, a filter: its lists, ☑️ toggles, 📝 values, ⬆️ / ⬇️, 🗑 Удалить фильтр
   ├ 🔧 Параметры — default edits/deletes/mode, 🛰 Техканал, 📢 Рассылка, 📬 Получатели рассылки, 🔗 Ссылка-замена
   ├ ⏪ Догрузка — past_mode.py for the project (its mirror is paused meanwhile), ⏱ Задержка
   ├ 🛠 Обслуживание — 🛂 Доступ (read-only), 🔒 Запрет сохранения, 📌 Закрепы (flags, 📏 limit,
   │   📍 donors), 🕶 Анонимность, 🧨 Очистка каналов (a check first, then the real run)
   ├ 🗂 Конфиг — 📥 Скачать, 📤 Загрузить (diff + validation), ↩️ Откатить
   └ 🧰 Управление — 🏷 Переименовать, 🎨 Значок, 👤 Аккаунт, 🗑 Удалить проект (moved to projects/.deleted/)
📊 Задачи (/status) — every project's units, a unit's journal, ▶️ / ⏹ / 🔁
⚙️ Настройки — admins, 🩺 / 🔁 monitoring timers on/off · 👤 Аккаунты: sessions, 🔑 Войти по номеру, 📤 Загрузить сессию
```

- **Notifications** — the panel polls systemd every 30 s and messages the admins
  when a replay / maintenance run finishes or fails, and when a mirror crashes,
  enters `failed` or comes back; it also brings back the mirrors paused for a run
  on their session. Admins must have pressed /start once.
- **Sign-in by phone** happens in the bot (number → code typed with spaces → 2FA
  password; 📲 sends a new code), with the Telegram Desktop profile `login.py` uses;
  the messages with the code and the password are deleted, the password is never stored.
- **An account signed in elsewhere** (📤 Загрузить сессию, or `python login.py --import PATH`):
  a ZIP of a Telegram Desktop `tdata` folder (its local passcode is asked for if set), a
  Telethon `.session` with the seller's `.json` of the same name (sent together; its app and
  device are kept, the Telegram Desktop profile without it), a ZIP of those, or a `.jsession`.
  The key is reused as is — no 2FA password needed or stored — and saved as
  `sessions/<phone>.jsession` once a connection shows the account signed in; one account per
  upload, and a key already saved is refused without connecting. `tdata` is read by
  `opentele-ng` in a child process (it patches Telethon on import).

Config writes keep comments (ruamel round-trip), make a `*.bak`, refuse if the
file was edited by hand meanwhile, and are validated by importing `config.py`
against the candidate in a subprocess (as the project's own service would) — an
invalid config is never written. Saved-but-unapplied changes also go live at the
daily 04:00 restart.

CLI-only by design: `skylon_set/setup_mirrors.py` (`login.py` itself too — the
bot signs in by phone on its own). Filters: any arg of a known type is edited in
the bot; adding `MappedNameForwardFormat` and args of other types (shown as
"правится в файле") go through 🗂 Конфиг → 📤 Загрузить.

Adding a filter to a direction without its own list copies the project's
filters into it first: a direction's own list replaces them. Deleting its last
own filter removes the list, and the direction is back on the project's.
