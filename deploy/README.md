# deploy/ — running telemirror on a VPS under systemd

The wiring for keeping each project's mirror running 24/7, its history
replays and maintenance runs. Built for bare-metal Ubuntu with systemd — the
only supported deployment.

A **project** is an independent mirror: `projects/<key>/project.yml` names its
session (`sessions/*.jsession`), its mirror config and its health port. Every
unit is a template instantiated per project (`%i` = the project key); the
control panel creates projects, accounts and directions, and starts/stops the
units. Projects on one session file run in turn (one process per session —
`telemirror/misc/session_lock.py`; the panel pauses the other one and brings it
back).

## What's inside

| File | Purpose |
|---|---|
| `bootstrap.sh` | one-time installer: swap + unit symlinks + journal + cron + `daemon-reload` |
| `setup-swap.sh` | idempotent resize of `/swapfile` to 2 GB and `vm.swappiness=10` |
| `systemd/telemirror@.service` | a project's live mirror (`python -m telemirror.live`), 24/7 |
| `systemd/telemirror-past@.service` | a project's history replay of its `past_mode:` directions (`python -m telemirror.past`) |
| `systemd/telemirror-task@.service` | a project's maintenance run started by the panel (`python -m telemirror.tasks.<module>`) |
| `systemd/telemirror-alert@.service` | `OnFailure=`: tells the panel's admins (through its bot) that a unit gave up |
| `systemd/telemirror-health.{timer,service}` | every 10 min: alerts if a mirror is flapping or stuck non-active |
| `systemd/telemirror-restart.{timer,service}` | a clean restart of the running mirrors once a day (04:00) |
| `systemd/telemirror-report.{timer,service}` | Mondays 10:00: each project's weekly report to the panel's admins (`python -m telemirror.report`) |
| `systemd/telemirror-panel.service` | the Telegram control panel bot (`python -m bot`) |
| `systemd/journald.conf.d/telemirror.conf` | `SystemMaxUse=500M` — the journal won't fill up `/var` |
| `cron.d/telemirror-tmp` | hourly cleanup of orphaned `/tmp/telemirror-tmp-*` files |

## Requirements

- Ubuntu + systemd ≥ 254 (`RestartSteps=`/`RestartMaxDelaySec=`).
- A Python venv at `/root/telemirror/.venv` (`python3.13 -m venv .venv && source
  .venv/bin/activate`, then `bash install.sh` from the repo root — it refuses to run without that venv active;
  on Linux it also installs the CPU build of torch — LaMa needs it to remove a
  source's watermark from photos; without it photos keep the watermark).
- `ffmpeg` in `PATH` (`apt install ffmpeg`) — for the video watermark.
- PostgreSQL running locally (`postgresql.service`), with the `telemirror`
  database and role created and matching `.env` (all projects share it).
- `.env` at the repo root: `DB_*`, `PANEL_BOT_TOKEN`, `PANEL_ADMIN_IDS` (alerts
  and the panel go through the bot).
- If networking comes up through systemd-networkd — enable
  `systemctl enable systemd-networkd-wait-online.service`, otherwise
  `network-online.target` won't block the start (not critical: telethon
  reconnects on its own, and `Restart=always` covers the rest).

## Installation

```bash
cd /root/telemirror
sudo deploy/bootstrap.sh
systemctl enable --now telemirror-panel.service
```

The script: grows swap, installs unit symlinks into `/etc/systemd/system/`
(and drops the dangling links of the pre-project units), drops the cron file,
runs `daemon-reload`. It does **not** start any mirror — create a project in
the bot (📁 Проекты → ➕ Новый проект) and press ▶️ Запустить there, or by hand:
`systemctl enable --now telemirror@<key>.service`.

Then check the whole installation (also ⚙️ Настройки → 🧾 Диагностика сервера
in the bot): `.env`, the bot's token, the database and its tables, the unit
links, the timers, the panel, every project's session, config and mirror.
Read-only; exit code 1 when something is ❌.

```bash
.venv/bin/python -m telemirror.selfcheck
```

Units are symlinks into the repo, the cron file is a copy. If you edit
`deploy/cron.d/telemirror-tmp`, re-run `bootstrap.sh` (or copy it by hand); if
you edit a unit, `git pull` + `systemctl daemon-reload` is enough.

## Migrating from the pre-project units

Before projects there was one mirror (`telemirror.service` on
`.configs/mirror.config.yml`) and a course replay
(`telemirror-past-courses.service` on `.configs/citadel_courses.config.yml`),
both on the `.env` session. Once, after `git pull`:

```bash
cd /root/telemirror
systemctl disable --now telemirror.service telemirror-panel.service
systemctl stop telemirror-past-courses.service telemirror-past-live.service 2>/dev/null || true
.venv/bin/python -m telemirror.projects migrate   # projects/live + projects/crs, the .env session
sudo deploy/bootstrap.sh                          # new unit links, the old ones removed
systemctl enable --now telemirror@live.service telemirror-panel.service
journalctl -u telemirror@live.service -f
```

`migrate` keeps the configs where they are and takes the session from `.env`
(`SESSION_FILE`, or `SESSION_STRING` + `API_*` written to
`sessions/live.jsession`); `live` gets `PORT` (8000), `crs` the next one. It
does nothing for a project that already exists.

## A project's mirror

```bash
systemctl enable --now telemirror@<key>.service
journalctl -u telemirror@<key>.service -f
```

Reads the project's config (`project.yml` → `config`). Resyncs against the
`binding_id` table on startup, so a crash doesn't lose messages.

### How it stays up 24/7

| Failure | What happens |
|---|---|
| Crash / OOM-kill / clean exit | `Restart=always`, backoff 10s → 120s |
| Network drop / Telegram DC failure | telethon reconnects on its own (`connection_retries=1000`); the watchdog tolerates being disconnected for up to **30 min**, longer than that triggers a restart with a fresh process |
| **Dead receive loop / hung RPC** | `Type=notify` + `WatchdogSec=600`: a watchdog task does an `updates.GetState` round-trip every 300s (tolerates 3 failures in a row, a FloodWait is fine); no response → `WATCHDOG=1` stops going out → systemd sends `SIGTERM` and restarts it |
| Update dispatch itself is stuck (RPC still alive) | indistinguishable from a genuinely quiet feed → no auto-restart; after 2h with no update at all — a `warning` to the panel's admins |
| Fast crash-loop (<~4 min/iteration) | 15 crashes in an hour → `failed` → `OnFailure=telemirror-alert@` to the admins, the service stays down until `systemctl reset-failed && systemctl start` |
| Slow crash-loop / stuck non-`active` | `telemirror-health.timer` (10 min): alerts on ≥3 restarts in the interval, or stuck in a transitional state (not `active`/`inactive`/`failed`) twice in a row; `failed` itself is `OnFailure=`'s alert |
| Session already in use by another process | the session lock refuses the start (`Session … is in use by …`) instead of splitting updates with it — stop the other one, or let the panel run them in turn |
| Account ban / session revoked | falls into the crash-loop path above → alert; fix: a new sign-in in the bot (⚙️ Настройки → 👤 Аккаунты → 🔑 Войти по номеру), then the project's ⚙️ Настройки проекта → 👤 Аккаунт |
| Slow memory leak | `telemirror-restart.timer` — a clean restart at 04:00 |

Checks:
```bash
systemctl show telemirror@<key>.service -p Type -p WatchdogUSec -p NRestarts
systemctl list-timers 'telemirror-*'
python -m telemirror.health        # a one-off check
python -m telemirror.selfcheck     # the whole installation, ✅ / ⚠️ / ❌
python -m telemirror.report        # the weekly report, now
# simulate a hang — wait ~10 min for the watchdog restart:
systemctl kill -s STOP telemirror@<key>.service
```

## History replay and maintenance

- `telemirror-past@<key>.service` replays the history of the project's
  directions that have `past_mode:`; `telemirror-task@<key>.service` runs
  `check_access` / `restrict_saving` / `sync_pins` / `anonymize_groups` / `clear_channels` with the arguments the panel writes to
  `/run/telemirror-panel/<key>.env` right before the start (a manual
  `systemctl start` without that file fails on purpose).
- Both use the project's session: `Conflicts=telemirror@%i.service` stops its
  mirror. The panel (⏪ Старые посты / 🛠 Инструменты) also stops whatever else
  holds that session, records it in `projects/.resume.json`, and its watcher
  starts those mirrors again once the run is over — whatever the outcome. A run
  started by hand doesn't bring anything back. A mirror started on a session
  another project's mirror holds replaces it for good (that one is disabled):
  one mirror per session.
- The replay has the live mirror's watchdog too (`Type=notify`,
  `WatchdogSec=600`, the same `updates.GetState` probe): only the connection
  is checked, not progress — its FloodWaits may last hours. A dead connection
  → restarted, resumed from its checkpoints; otherwise a hung replay would keep
  the project's mirror stopped. Check: `systemctl show telemirror-past@<key>.service -p Type -p WatchdogUSec`.
- The history replay keeps checkpoints in the DB — an interruption resumes from
  where it left off. A full reset of history and recipients —
  `telemirror.tasks.clear_channels` (in the bot: 🛠 Инструменты → 🧨 Очистка каналов).

## Control panel

```bash
# .env: PANEL_BOT_TOKEN=… and PANEL_ADMIN_IDS=<your Telegram user id>
systemctl enable --now telemirror-panel.service
journalctl -u telemirror-panel.service -f
```

- A separate unit with **no** `Conflicts=` on the mirrors: it stays up while
  they are stopped or crash-looping. It talks to Telegram as a bot; a userbot
  session it opens only for a sign-in by phone. If the panel itself gives up
  (`StartLimitBurst`), `OnFailure=telemirror-alert@` reports it.
- Runs as root like the other units: it calls `systemctl`/`journalctl`, but only
  for the units of existing projects and the two timers (no user input in argv).
- Notifications: the panel polls `systemctl show` every 30 s and messages the
  admins about finished/failed runs and mirror crashes, and resumes paused
  mirrors.
- Config saves validate the candidate by importing `telemirror.config` in a child
  process (cv2 included) — hence `MemoryMax=600M` on the panel unit.
- Check on first deploy: `systemctl show telemirror@<key>.service --timestamp=unix -p
  ActiveEnterTimestamp` prints `@<unix>` (the card's "unapplied changes" hint
  relies on it; systemd ≥ 251).

## Memory and monitoring

The server is tight on RAM (2 GB). Units are capped at `MemoryHigh=1100M` /
`MemoryMax=1400M` each — a leak only kills that mirror, not some unrelated process.
Every running mirror takes its own share: plan the RAM per project.

```bash
systemctl status 'telemirror@*'
systemd-cgtop                       # per-cgroup usage
free -h
journalctl -k | grep -i oom        # any OOM-kills?
```

Don't leave the VS Code Remote Server running in production — it uses
~1.2 GB RAM and has caused OOM before.

## Updating

```bash
cd /root/telemirror && git pull
systemctl daemon-reload            # the units are symlinks into the repo: picks up their changes
systemctl restart 'telemirror@*.service' telemirror-panel.service
```

A new unit in the repo (e.g. `telemirror-report.{timer,service}`) has no
symlink yet: re-run `sudo deploy/bootstrap.sh` once (idempotent) — it links
and enables the timers. `python -m telemirror.selfcheck` says when that's
needed (❌ Юниты systemd: не установлены …).

## Notes

- **Single CPU core.** The video watermark is a full re-encode: a clip
  ≤ 5 min (`stamp_video_max_duration_s` in `mirror.config.yml`) pins the core
  for 6-13 minutes, and forwarding everything else gets delayed for that
  long. If that matters, lower the threshold to 120-180s or provision 2+
  cores. Videos longer than the threshold are forwarded as-is, unwatermarked.
- **Strict sandboxing is not enabled** (`ProtectHome`, `ProtectSystem=strict`):
  it breaks `__pycache__` writes under `/root/telemirror`, and the payoff for
  a solo bot is small. `PrivateTmp`, `NoNewPrivileges`, `ProtectSystem=full`
  are kept.
- **The `/tmp` cleanup cron** mainly matters for manual `telemirror.past` runs
  outside systemd — the units themselves clean up their temp files via
  `PrivateTmp=true`.
