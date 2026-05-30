# Telegram message forwarder (client API)

### Functionality
- Live forwarding and updating messages
- Source and target channels/chats/topics (one-to-one, many-to-one, many-to-many) mapping
- Incoming message filters: word replacing, forward formating, skipping by keyword and more

## Prepare

1. [Create Telegram App](https://my.telegram.org/apps)

2. Obtain **API_ID** and **API_HASH**

    ![Telegram API Credentials](/README.md-images/telegramapp.png)

3. Get **SESSION_STRING**

    **SESSION_STRING** can be obtained by running [login.py](login.py) with provided **API_ID** and **API_HASH** environment variables. ❗ **DON'T USE** your own account.

4. Setup Postgres database or use `InMemoryDatabase` with `USE_MEMORY_DB=true` parameter in `.env` file

5. Fill `.env` with your data

    [.env-example](.env-example) contains the minimum environment configuration to run with an in-memory database.

    <details>
    <summary><b>.env</b> overview</b></summary>

    ```bash
    ###########################
    #    App configuration    #
    ###########################
    
    # Telegram app ID
    API_ID=test
    # Telegram app hash
    API_HASH=test
    # Telegram session string (telethon session, see login.py in root directory)
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
    # Optional parameters can be removed
    # The next optional parameters can be set to prevent bans/logouts
    # (Optional) System version info for telegram client. You can set it to `4.16.30-vxCUSTOM` or any other value if you believe it will help fix the bans. Default is `platform.uname().release`
    # See: https://github.com/LonamiWebs/Telethon/issues/4051 
    API_SYSTEM_VERSION=
    # (Optional) Device model info for telegram client. Default is `platform.uname().machine`
    API_DEVICE_MODEL=
    # (Optional) Application version info for telegram client. Default is `telethon.version.__version__`
    API_APP_VERSION=
    ```
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
          format: ""           # Filters arguments
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
        # Overwrite global filters
        filters:
          - UrlMessageFilter:
              blacklist: !!set
                ? t.me
          - KeywordReplaceFilter:
              keywords:
                "google.com": "bing.com"    # treat keyword as word
                "r'google\\.com.*'": "bing.com" # treat keyword as regex expr
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

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/khoben/telemirror)

### or via CLI:

1. Clone project

    ```bash
    git clone https://github.com/khoben/telemirror.git
    ```
2. Create new heroku app within Heroku CLI

    ```bash
    heroku create {your app name}
    ```
3. Add heroku remote

    ```bash
    heroku git:remote -a {your app name}
    ```
4. Set environment variables to your heroku app from .env by running bash script

    ```bash
    ./set_heroku_env.bash
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
    git remote add origin https://github.com/khoben/telemirror
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
| `PAST_MODE` | — | Replay past messages on startup (env-mode only). Values: `last_n=N`, `full_history`, `since_date=YYYY-MM-DDTHH:MM:SS`. |

> ⚠️ `USE_MEMORY_DB=true` is incompatible with `BROADCAST_CHANNEL` if the broadcast channel has more than 100 messages — use PostgreSQL for reliable broadcast sync.

## Replaying past messages (`past_mode.py`)

`past_mode.py` replays a channel's history through the mirror pipeline for directions that have `past_mode:` configured in the YAML config (or `PAST_MODE=` in env-mode).

```bash
# Stop main.py first — both use the same SESSION_STRING
python past_mode.py
```

Progress is checkpointed after each message: if interrupted, re-running resumes from where it left off. A second pass rewrites cross-channel links in already-sent messages.

## Utility scripts (`skylon_set/`)

> ⚠️ All scripts use the same `SESSION_STRING` as the main service. Stop `main.py` before running them.

| Script | Description |
|---|---|
| `skylon_set/setup_mirrors.py` | Interactive wizard for creating donor/recipient channel pairs and generating the YAML config. |
| `skylon_set/clear_channels.py` | Purges all messages in recipient channels/topics and resets past_mode checkpoints. Supports `--dry-run`. |
| `skylon_set/rename_emoji.py` | Bulk-renames Archonum recipient channel titles (replaces 🏴‍☠️ with 🗝). |