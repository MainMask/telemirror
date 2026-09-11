#!/usr/bin/env bash
# Одноразовая установка systemd-обвязки telemirror на VPS. Идемпотентно.
# Юниты ставятся симлинками на файлы в репозитории — `git pull` + daemon-reload
# их обновляет.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "Нужен root: sudo $0" >&2
    exit 1
fi

echo "== 1/4 swap =="
"$REPO_DIR/deploy/setup-swap.sh"

echo
echo "== 2/4 systemd-юниты =="
for unit in telemirror.service telemirror-past-courses.service; do
    ln -sfn "$REPO_DIR/deploy/systemd/$unit" "/etc/systemd/system/$unit"
    echo "  /etc/systemd/system/$unit -> $REPO_DIR/deploy/systemd/$unit"
done

echo
echo "== 3/4 cron-очистка /tmp =="
install -m 644 -o root -g root \
    "$REPO_DIR/deploy/cron.d/telemirror-tmp" /etc/cron.d/telemirror-tmp
echo "  /etc/cron.d/telemirror-tmp"

echo
echo "== 4/4 daemon-reload =="
systemctl daemon-reload

cat <<'EOF'

Готово. Юниты установлены, но НЕ запущены. Дальше вручную:

  # живое зеркало 24/7:
  systemctl enable --now telemirror.service
  journalctl -u telemirror.service -f

  # разовый прогон истории курсов (остановит live на время, вернёт по завершении):
  systemctl start telemirror-past-courses.service
  journalctl -u telemirror-past-courses.service -f

Подробности — deploy/README.md
EOF
