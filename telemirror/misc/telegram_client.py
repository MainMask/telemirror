from typing import Optional

from telethon import TelegramClient
from telethon.sessions import StringSession


def build_telegram_client(
    session_string: str,
    api_id: str,
    api_hash: str,
    *,
    device_model: Optional[str] = None,
    system_version: Optional[str] = None,
    app_version: Optional[str] = None,
    connection_retries: int,
    retry_delay: int,
) -> TelegramClient:
    """Build a markdown-parse-mode ``TelegramClient`` from the shared session
    and API credentials.

    ``flood_sleep_threshold=300`` is fixed project-wide: Telethon auto-sleeps
    any FloodWait under that, and both the live mirror and past_mode's retry
    loop are built to handle only the larger ones themselves.
    ``connection_retries``/``retry_delay`` are left to the caller since the
    live mirror retries indefinitely through an outage while operator scripts
    (``past_mode.py``) give up after a bounded window.
    """
    client = TelegramClient(
        StringSession(session_string),
        api_id,
        api_hash,
        device_model=device_model,
        system_version=system_version,
        app_version=app_version,
        flood_sleep_threshold=300,
        connection_retries=connection_retries,
        retry_delay=retry_delay,
    )
    client.parse_mode = "markdown"
    return client
