# deploy/ — running telemirror on a VPS under systemd

The wiring for keeping the live mirror running 24/7 and for a one-off course
history replay. Built for bare-metal Ubuntu with systemd (not Docker; a
`docker-compose.yaml` for Docker lives at the repo root).

## What's inside

| File | Purpose |
|---|---|
| `bootstrap.sh` | one-time installer: swap + unit symlinks + journal + cron + `daemon-reload` |
| `setup-swap.sh` | idempotent resize of `/swapfile` to 2 GB and `vm.swappiness=10` |
| `systemd/telemirror.service` | the live mirror (`main.py`), 24/7 |
| `systemd/telemirror-past-courses.service` | one-off course history replay (`past_mode.py`) |
| `systemd/telemirror-alert@.service` | `OnFailure=`: tells `TECH_CHANNEL` that a unit gave up |
| `systemd/telemirror-health.{timer,service}` | every 10 min: alerts if the mirror is flapping or stuck non-active |
| `systemd/telemirror-restart.{timer,service}` | a clean restart of the mirror once a day (04:00) |
| `systemd/telemirror-panel.service` | optional Telegram control panel bot (`python -m telemirror.panel`) |
| `systemd/telemirror-task@.service` | maintenance task started by the panel (`skylon_set.<module>`, stops the live mirror for its duration) |
| `systemd/journald.conf.d/telemirror.conf` | `SystemMaxUse=500M` — the journal won't fill up `/var` |
| `cron.d/telemirror-tmp` | hourly cleanup of orphaned `/tmp/tmp*.mp4` files |

## Requirements

- Ubuntu + systemd ≥ 254 (needs `OnSuccess=`, `RestartSteps=`/`RestartMaxDelaySec=`).
- A Python venv at `/root/telemirror/.venv` (`bash install.sh` from the repo root).
- `ffmpeg` in `PATH` (`apt install ffmpeg`) — for the video watermark.
- PostgreSQL running locally (`postgresql.service`), with the `telemirror`
  database and role created and matching `.env`.
- `.env` filled in at the repo root (`API_ID`, `API_HASH`, `SESSION_STRING`,
  `DB_*`). `SESSION_STRING` comes from `python login.py`. Crash alerts need
  `TECH_CHANNEL` (the id of the channel/chat the bot writes to).
- If networking comes up through systemd-networkd — enable
  `systemctl enable systemd-networkd-wait-online.service`, otherwise
  `network-online.target` won't block the start (not critical: telethon
  reconnects on its own, and `Restart=always` covers the rest).

## Installation

```bash
cd /root/telemirror
sudo deploy/bootstrap.sh
```

The script: grows swap, installs unit symlinks into `/etc/systemd/system/`,
drops the cron file, runs `daemon-reload`. It does **not** start the
services — that's done by hand below.

Units are symlinks into the repo, the cron file is a copy. If you edit
`deploy/cron.d/telemirror-tmp`, re-run `bootstrap.sh` (or copy it by hand); if
you edit a unit, `git pull` + `systemctl daemon-reload` is enough.

## Live mirror

```bash
systemctl status telemirror.service | grep -q masked && systemctl unmask telemirror.service
systemctl enable --now telemirror.service
journalctl -u telemirror.service -f
```

Reads `.configs/mirror.config.yml`. Resyncs against the `binding_id` table on
startup, so a crash doesn't lose messages.

### How it stays up 24/7

| Failure | What happens |
|---|---|
| Crash / OOM-kill / clean exit | `Restart=always`, backoff 10s → 120s |
| Network drop / Telegram DC failure | telethon reconnects on its own (`connection_retries=1000`); the watchdog tolerates being disconnected for up to **30 min**, longer than that triggers a restart with a fresh process |
| **Dead receive loop / hung RPC** | `Type=notify` + `WatchdogSec=600`: a watchdog task does an `updates.GetState` round-trip every 300s (tolerates 3 failures in a row, a FloodWait is fine); no response → `WATCHDOG=1` stops going out → systemd sends `SIGTERM` and restarts it |
| Update dispatch itself is stuck (RPC still alive) | indistinguishable from a genuinely quiet feed → no auto-restart; after 2h with no update at all — a `warning` to `TECH_CHANNEL` |
| Fast crash-loop (<~4 min/iteration) | 15 crashes in an hour → `failed` → `OnFailure=telemirror-alert@` to `TECH_CHANNEL`, the service stays down until `systemctl reset-failed && systemctl start` |
| Slow crash-loop / stuck non-`active` | `telemirror-health.timer` (10 min): alerts `TECH_CHANNEL` on ≥3 restarts in the interval, or `ActiveState≠active` twice in a row |
| Account ban / session revoked | falls into the crash-loop path above → alert; fix via `python login.py` |
| Slow memory leak | `telemirror-restart.timer` — a clean restart at 04:00 |

Checks:
```bash
systemctl show telemirror.service -p Type -p WatchdogUSec -p NRestarts
systemctl list-timers 'telemirror-*'
python -m telemirror.health        # a one-off check
# simulate a hang — wait ~10 min for the watchdog restart:
systemctl kill -s STOP telemirror.service
```

## Course history replay

```bash
systemctl start telemirror-past-courses.service
journalctl -u telemirror-past-courses.service -f
```

- The config is injected from `.configs/citadel_courses.config.yml` via
  `YAML_CONFIG_ENV` (`main.py` itself never reads this file).
- `Conflicts=telemirror.service`: starting the backfill **stops** the live
  mirror (shared `SESSION_STRING`); `OnSuccess=` brings it back up once the
  backfill finishes successfully.
- If the backfill fails outright (after `Restart=on-failure`/`RestartSec=60`
  and `StartLimitBurst=3` exhaust within 10 minutes, the unit goes to
  `failed`) — `OnFailure=` alerts `TECH_CHANNEL`, same as `telemirror.service`.
  Without this, the live mirror would stay silently stopped by `Conflicts=`:
  `OnSuccess=` never fires, and `telemirror-health.timer` deliberately doesn't
  treat `inactive` as stuck (it's the normal state during a backfill) — bring
  the mirror back up by hand (`systemctl start telemirror.service`) once
  you've fixed whatever caused the failure.
- The unit doesn't start on boot (no `[Install]`).
- `past_mode.py` keeps checkpoints in the DB — an interruption resumes from
  where it left off. A full reset of history and recipients —
  `skylon_set/clear_channels.py`.

## Control panel (optional)

```bash
# .env: PANEL_BOT_TOKEN=… and PANEL_ADMIN_IDS=<your Telegram user id>
systemctl enable --now telemirror-panel.service
journalctl -u telemirror-panel.service -f
```

- A separate unit with **no** `Conflicts=` on the mirror: it stays up while the
  mirror is stopped or crash-looping. It only uses the Bot API, never
  `SESSION_STRING`.
- Runs as root like the other units: it calls `systemctl`/`journalctl`, but only
  for the units listed in `telemirror/panel/settings.py` (no user input in argv).
- Maintenance runs (`restrict_saving`, `sync_pins`) go through
  `telemirror-task@<module>.service`: `Conflicts=telemirror.service` stops the
  mirror, `OnSuccess=`/`OnFailure=` start it again (a failure also alerts). The
  panel writes the arguments to `/run/telemirror-panel/<module>.env` right before
  the start; a manual `systemctl start telemirror-task@…` without that file fails
  on purpose.
- Config saves validate the candidate by importing `config.py` in a child
  process (cv2 included) — hence `MemoryMax=600M` on the panel unit.
- Check on first deploy: `systemctl show telemirror.service --timestamp=unix -p
  ActiveEnterTimestamp` prints `@<unix>` (the panel's "unapplied changes" hint
  relies on it; systemd ≥ 251).

## Memory and monitoring

The server is tight on RAM (2 GB). Units are capped at `MemoryHigh=1100M` /
`MemoryMax=1400M` — a leak only kills telemirror, not some unrelated process.

```bash
systemctl status telemirror.service
systemd-cgtop                       # per-cgroup usage
free -h
journalctl -k | grep -i oom        # any OOM-kills?
```

Don't leave the VS Code Remote Server running in production — it uses
~1.2 GB RAM and has caused OOM before.

## Updating

```bash
cd /root/telemirror && git pull
systemctl daemon-reload            # if files under deploy/systemd/ changed
systemctl restart telemirror.service
```

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
- **The `/tmp` cleanup cron** mainly matters for manual `past_mode.py` runs
  outside systemd — the units themselves clean up their temp files via
  `PrivateTmp=true`.
