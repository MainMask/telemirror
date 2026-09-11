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
    telemirror.service \
    telemirror-past-courses.service \
    telemirror-alert@.service \
    telemirror-restart.service \
    telemirror-restart.timer \
    telemirror-health.service \
    telemirror-health.timer; do
    ln -sfn "$REPO_DIR/deploy/systemd/$unit" "/etc/systemd/system/$unit"
    echo "  /etc/systemd/system/$unit -> $REPO_DIR/deploy/systemd/$unit"
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

  # live mirror, 24/7 (if the unit was masked — first: systemctl unmask telemirror.service):
  systemctl enable --now telemirror.service
  journalctl -u telemirror.service -f

  # one-off course history replay (stops the live mirror, brings it back when done):
  systemctl start telemirror-past-courses.service
  journalctl -u telemirror-past-courses.service -f

Details — deploy/README.md
EOF
