"""Send a one-off notice: through the control panel bot to its admins when
``PANEL_BOT_TOKEN`` is set, otherwise from the userbot session to TECH_CHANNEL.

The bot comes first: with several projects there's no single session to send
from, and an account that was banned or logged out can't report it itself.

Used by ``telemirror-alert@.service`` (OnFailure=) and by ``telemirror.health``.
Reads only the keys it needs straight from ``.env`` (never ``import config`` —
that builds the whole mapping and can raise on a partial env, exactly when we
most need the alert to go out).

    python -m telemirror.alert telemirror@live.service
"""

import asyncio
import json
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Optional

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
        return out.stdout.strip() or "(journal is empty)"
    except Exception as e:  # noqa: BLE001 - best effort
        return f"(journal unavailable: {e})"


def _failed_state_message(unit: str) -> str:
    return f"⚠️ {unit} entered failed state\n\n{journal_tail(unit)[-3000:]}"


async def _connect_and_send(text: str) -> Optional[bool]:
    """Returns None when there's deliberately nothing to do (TECH_CHANNEL
    unset — not a failure), True on a confirmed send, False on a real
    delivery failure."""
    tech_channel = _env("TECH_CHANNEL", default=None)
    if not tech_channel:
        print("telemirror.alert: TECH_CHANNEL not set — skipping", file=sys.stderr)
        return None

    body = _stamp(text)

    client = TelegramClient(
        StringSession(_env("SESSION_STRING")),
        _env("API_ID"),
        _env("API_HASH"),
    )
    try:
        await asyncio.wait_for(client.connect(), _CONNECT_TIMEOUT)
        if not await client.is_user_authorized():
            print("telemirror.alert: session not authorized", file=sys.stderr)
            return False
        await asyncio.wait_for(
            client.send_message(int(tech_channel), body, parse_mode=None),
            _SEND_TIMEOUT,
        )
        return True
    finally:
        await client.disconnect()


def _stamp(text: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{text}\n\nhost: {socket.gethostname()}  •  {now}"


def _send_via_bot(token: str, admins: str, text: str) -> bool:
    """True if at least one admin got it."""
    delivered = False
    for chat_id in filter(None, (a.strip() for a in admins.replace(";", ",").split(","))):
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": int(chat_id), "text": _stamp(text)}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_SEND_TIMEOUT) as response:
                delivered |= bool(json.load(response).get("ok"))
        except Exception as e:  # noqa: BLE001 - try the other admins
            print(f"telemirror.alert: bot send to {chat_id} failed: {e}", file=sys.stderr)
    return delivered


def send_alert(text: str) -> Optional[bool]:
    """Best-effort: deliver ``text`` (bot → admins, else userbot → TECH_CHANNEL),
    never raise (an alert must
    not fail the caller — an OnFailure chain or the health timer). Returns
    None when TECH_CHANNEL isn't configured (deliberately nothing to do),
    True on a confirmed send, False on a real delivery failure — so the
    caller (a oneshot systemd unit) can surface an actual failed send
    without also flagging the unremarkable "alerting isn't configured" case."""
    try:
        token = _env("PANEL_BOT_TOKEN", default="")
        if token:
            return _send_via_bot(token, _env("PANEL_ADMIN_IDS", default=""), text)
        return asyncio.run(_connect_and_send(text))
    except Exception as e:  # noqa: BLE001
        print(
            f"telemirror.alert: failed to send ({type(e).__name__}: {e})",
            file=sys.stderr,
        )
        return False


def main() -> None:
    unit = sys.argv[1] if len(sys.argv) > 1 else "telemirror@live.service"
    sys.exit(1 if send_alert(_failed_state_message(unit)) is False else 0)


if __name__ == "__main__":
    main()
