#!/usr/bin/env bash
# One-time systemd setup for telemirror on a VPS. Idempotent.
# Units are installed as symlinks to files in the repo — `git pull` +
# daemon-reload updates them.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "Root required: sudo $0" >&2
    exit 1
fi

echo "== 1/5 swap =="
"$REPO_DIR/deploy/setup-swap.sh"

echo
echo "== 2/5 systemd units =="
for unit in \
    telemirror@.service \
    telemirror-past@.service \
    telemirror-task@.service \
    telemirror-alert@.service \
    telemirror-restart.service \
    telemirror-restart.timer \
    telemirror-health.service \
    telemirror-health.timer \
    telemirror-panel.service; do
    ln -sfn "$REPO_DIR/deploy/systemd/$unit" "/etc/systemd/system/$unit"
    echo "  /etc/systemd/system/$unit -> $REPO_DIR/deploy/systemd/$unit"
done
# The pre-project units (see deploy/README.md → Migrating): their files are gone
# from the repo, drop the dangling links.
for unit in telemirror.service telemirror-past-courses.service telemirror-past-live.service; do
    link="/etc/systemd/system/$unit"
    if [ -L "$link" ] && [ ! -e "$link" ]; then
        rm -f "$link"
        echo "  removed the dangling $link"
    fi
done

echo
echo "== 3/5 journal limit =="
install -d /etc/systemd/journald.conf.d
install -m 644 -o root -g root \
    "$REPO_DIR/deploy/systemd/journald.conf.d/telemirror.conf" \
    /etc/systemd/journald.conf.d/telemirror.conf
echo "  /etc/systemd/journald.conf.d/telemirror.conf"
# Persistent journal: without /var/log/journal, journald writes to tmpfs and
# SystemMaxUse is ignored.
install -d -g systemd-journal -m 2755 /var/log/journal
systemctl restart systemd-journald

echo
echo "== 4/5 /tmp cleanup cron =="
install -m 644 -o root -g root \
    "$REPO_DIR/deploy/cron.d/telemirror-tmp" /etc/cron.d/telemirror-tmp
echo "  /etc/cron.d/telemirror-tmp"

echo
echo "== 5/5 daemon-reload + timers =="
systemctl daemon-reload
systemctl enable --now telemirror-restart.timer telemirror-health.timer
echo "  telemirror-restart.timer, telemirror-health.timer enabled and started"

cat <<'EOF'

Done. Units are installed but NOT started. Next, by hand:

  # the Telegram control panel (needs PANEL_BOT_TOKEN + PANEL_ADMIN_IDS in .env):
  systemctl enable --now telemirror-panel.service
  journalctl -u telemirror-panel.service -f

  # then in the bot: 📁 Проекты → ➕ Новый проект → … → ▶️ Запустить
  # (coming from telemirror.service: python -m telemirror.projects migrate — deploy/README.md)
  # or by hand, for a project <key>:
  systemctl enable --now telemirror@<key>.service
  journalctl -u telemirror@<key>.service -f

Details — deploy/README.md
EOF
