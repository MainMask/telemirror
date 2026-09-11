#!/usr/bin/env bash
# Resizes /swapfile to 2 GB and sets vm.swappiness=10. Idempotent: re-running
# doesn't break anything. Reason: on 2 GB RAM with no headroom, the kernel had
# already OOM-killed processes twice while working with media.
set -euo pipefail

TARGET_MB=2048
SWAPFILE=/swapfile
SYSCTL_FILE=/etc/sysctl.d/99-telemirror.conf

if [ "$(id -u)" -ne 0 ]; then
    echo "Root required: sudo $0" >&2
    exit 1
fi

cur_bytes=0
[ -f "$SWAPFILE" ] && cur_bytes=$(stat -c %s "$SWAPFILE")
cur_mb=$(( cur_bytes / 1024 / 1024 ))

if [ "$cur_mb" -ge "$TARGET_MB" ]; then
    echo "swapfile is already ${cur_mb} MB (>= ${TARGET_MB}) — no resize needed"
else
    echo "resizing ${SWAPFILE}: ${cur_mb} MB -> ${TARGET_MB} MB"
    # If swap is active — turn it off strictly (no || true): if there isn't
    # enough RAM to reclaim the pages, swapoff will fail, and an active file
    # must not be removed.
    if swapon --show=NAME --noheadings 2>/dev/null | grep -qxF "$SWAPFILE"; then
        swapoff "$SWAPFILE"
    fi
    rm -f "$SWAPFILE"
    # dd, not fallocate: swap doesn't work on a sparse file
    dd if=/dev/zero of="$SWAPFILE" bs=1M count="$TARGET_MB" status=progress
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE"
    swapon "$SWAPFILE"
fi

if ! grep -qE '^\s*/swapfile\s+(none|swap)\s+swap\s' /etc/fstab; then
    echo "adding /swapfile to /etc/fstab"
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
