"""OnFailure= handler: ping TECH_CHANNEL when a telemirror unit gives up.

Wired from ``telemirror-alert@.service``. Reads only the few keys it needs
straight from ``.env`` (never ``import config`` — that builds the whole mapping
and can raise on a partial env, exactly when we most need the alert to go out).

    python -m telemirror.alert telemirror.service
"""

import asyncio
import socket
import subprocess
import sys
from datetime import datetime, timezone

from decouple import config as _env
from telethon import TelegramClient
from telethon.sessions import StringSession

_CONNECT_TIMEOUT = 20
_SEND_TIMEOUT = 20


def _journal_tail(unit: str, lines: int = 15) -> str:
    try:
        out = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() or "(журнал пуст)"
    except Exception as e:  # noqa: BLE001 - best effort
        return f"(журнал недоступен: {e})"


def _message(unit: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    tail = _journal_tail(unit)
    # Plain text (parse_mode=None on send): a raw journal tail with backticks or
    # stray * / _ would otherwise break Markdown entity parsing and the alert
    # would silently fail — exactly when we need it.
    return (
        f"⚠️ {unit} вошёл в failed state\n"
        f"хост: {socket.gethostname()}  •  {now}\n\n"
        f"{tail[-3000:]}"
    )


async def _send(unit: str) -> int:
    tech_channel = _env("TECH_CHANNEL", default=None)
    if not tech_channel:
        print("telemirror.alert: TECH_CHANNEL не задан — пропускаю", file=sys.stderr)
        return 0

    client = TelegramClient(
        StringSession(_env("SESSION_STRING")),
        _env("API_ID"),
        _env("API_HASH"),
    )
    try:
        await asyncio.wait_for(client.connect(), _CONNECT_TIMEOUT)
        if not await client.is_user_authorized():
            print("telemirror.alert: сессия не авторизована", file=sys.stderr)
            return 0
        await asyncio.wait_for(
            client.send_message(
                int(tech_channel), _message(unit), parse_mode=None
            ),
            _SEND_TIMEOUT,
        )
    finally:
        await client.disconnect()
    return 0


def main() -> None:
    unit = sys.argv[1] if len(sys.argv) > 1 else "telemirror.service"
    try:
        sys.exit(asyncio.run(_send(unit)))
    except Exception as e:  # noqa: BLE001 - an alert must never fail the OnFailure chain
        print(f"telemirror.alert: не смог отправить ({type(e).__name__}: {e})", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
