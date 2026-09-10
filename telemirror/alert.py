"""Send a one-off notice to TECH_CHANNEL.

Used by ``telemirror-alert@.service`` (OnFailure=) and by ``telemirror.health``.
Reads only the keys it needs straight from ``.env`` (never ``import config`` —
that builds the whole mapping and can raise on a partial env, exactly when we
most need the alert to go out).

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


def journal_tail(unit: str, lines: int = 15) -> str:
    try:
        out = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() or "(журнал пуст)"
    except Exception as e:  # noqa: BLE001 - best effort
        return f"(журнал недоступен: {e})"


def _failed_state_message(unit: str) -> str:
    return f"⚠️ {unit} вошёл в failed state\n\n{journal_tail(unit)[-3000:]}"


async def _connect_and_send(text: str) -> None:
    tech_channel = _env("TECH_CHANNEL", default=None)
    if not tech_channel:
        print("telemirror.alert: TECH_CHANNEL не задан — пропускаю", file=sys.stderr)
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    body = f"{text}\n\nхост: {socket.gethostname()}  •  {now}"

    client = TelegramClient(
        StringSession(_env("SESSION_STRING")),
        _env("API_ID"),
        _env("API_HASH"),
    )
    try:
        await asyncio.wait_for(client.connect(), _CONNECT_TIMEOUT)
        if not await client.is_user_authorized():
            print("telemirror.alert: сессия не авторизована", file=sys.stderr)
            return
        await asyncio.wait_for(
            client.send_message(int(tech_channel), body, parse_mode=None),
            _SEND_TIMEOUT,
        )
    finally:
        await client.disconnect()


def send_alert(text: str) -> None:
    """Best-effort: deliver ``text`` to TECH_CHANNEL, never raise (an alert must
    not fail the caller — an OnFailure chain or the health timer)."""
    try:
        asyncio.run(_connect_and_send(text))
    except Exception as e:  # noqa: BLE001
        print(
            f"telemirror.alert: не смог отправить ({type(e).__name__}: {e})",
            file=sys.stderr,
        )


def main() -> None:
    unit = sys.argv[1] if len(sys.argv) > 1 else "telemirror.service"
    send_alert(_failed_state_message(unit))
    sys.exit(0)


if __name__ == "__main__":
    main()
