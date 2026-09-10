#!/usr/bin/env bash
# Ресайз /swapfile до 2 ГБ и vm.swappiness=10. Идемпотентно: повторный запуск
# ничего не ломает. Причина — на 2 ГБ RAM без запаса ядро уже дважды роняло
# процессы по OOM во время работы с медиа.
set -euo pipefail

TARGET_MB=2048
SWAPFILE=/swapfile
SYSCTL_FILE=/etc/sysctl.d/99-telemirror.conf

if [ "$(id -u)" -ne 0 ]; then
    echo "Нужен root: sudo $0" >&2
    exit 1
fi

cur_bytes=0
[ -f "$SWAPFILE" ] && cur_bytes=$(stat -c %s "$SWAPFILE")
cur_mb=$(( cur_bytes / 1024 / 1024 ))

if [ "$cur_mb" -ge "$TARGET_MB" ]; then
    echo "swapfile уже ${cur_mb} МБ (>= ${TARGET_MB}) — ресайз не нужен"
else
    echo "ресайз ${SWAPFILE}: ${cur_mb} МБ -> ${TARGET_MB} МБ"
    # Если swap активен — выключаем строго (без || true): при нехватке RAM для
    # возврата страниц swapoff упадёт, и удалять активный файл нельзя.
    if swapon --show=NAME --noheadings 2>/dev/null | grep -qxF "$SWAPFILE"; then
        swapoff "$SWAPFILE"
    fi
    rm -f "$SWAPFILE"
    # dd, а не fallocate: swap не работает на разрежённом файле
    dd if=/dev/zero of="$SWAPFILE" bs=1M count="$TARGET_MB" status=progress
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE"
    swapon "$SWAPFILE"
fi

if ! grep -qE '^\s*/swapfile\s+(none|swap)\s+swap\s' /etc/fstab; then
    echo "добавляю /swapfile в /etc/fstab"
    echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi

if [ ! -f "$SYSCTL_FILE" ] || ! grep -qx 'vm.swappiness = 10' "$SYSCTL_FILE"; then
    echo "vm.swappiness = 10 -> ${SYSCTL_FILE}"
    echo 'vm.swappiness = 10' > "$SYSCTL_FILE"
    sysctl -q --system
fi

echo
swapon --show
echo "vm.swappiness = $(cat /proc/sys/vm/swappiness)"
