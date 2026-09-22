import asyncio
import logging
from typing import Optional

from telethon import TelegramClient
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)


def _consume_task_result(task: "asyncio.Task") -> None:
    """Retrieve a done task's result so asyncio doesn't log
    'Task exception was never retrieved' for a fire-and-forget task."""
    if not task.cancelled():
        task.exception()


async def cancel_and_await(task: "asyncio.Task") -> None:
    """Cancel `task` and wait for it to actually settle before moving on.
    Swallows its own CancelledError; any other exception it settles with
    (e.g. an unrelated failure that happened to land in the same window we
    decided to cancel it, making `.cancel()` a no-op) is logged rather than
    silently dropped — the caller only needs to know the task is no longer
    running, not its outcome, but a real bug in it shouldn't vanish without
    a trace."""
    task.cancel()
    results = await asyncio.gather(task, return_exceptions=True)
    exc = results[0]
    if exc is not None and not isinstance(exc, asyncio.CancelledError):
        logger.warning(
            "cancel_and_await: task raised %s: %s", type(exc).__name__, exc
        )


async def connect_with_timeout(client: TelegramClient, timeout_sec: float = 30.0) -> None:
    """Bounded wait for `client.connect()`.

    Avoids `client.connect` hanging forever:
    https://github.com/LonamiWebs/Telethon/issues/1536
    https://github.com/LonamiWebs/Telethon/issues/4119
    `connect()` may report success before the transport is ready, and may
    also never return — so the whole wait is bounded.
    """
    if client.is_connected():
        return

    connection_task = asyncio.create_task(client.connect())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec

    try:
        while not connection_task.done() and not client.is_connected():
            if loop.time() >= deadline:
                break
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        # Don't leak connection_task racing a subsequent client.disconnect()
        # (e.g. SIGTERM during a slow handshake) — cancel it and wait for it
        # to settle before propagating our own CancelledError, not its
        # result: it can independently finish with an unrelated exception in
        # the same window, which must not replace ours.
        await cancel_and_await(connection_task)
        raise

    if client.is_connected():
        # Connected — don't block on the task settling; just make sure
        # its eventual result/exception is consumed.
        if not connection_task.done():
            connection_task.add_done_callback(_consume_task_result)
    else:
        try:
            # Not connected: either surface connect() errors or fail
            # on the remaining budget instead of spinning forever.
            await asyncio.wait_for(
                connection_task,
                timeout=max(0.0, deadline - loop.time()),
            )
        except asyncio.TimeoutError as e:
            connection_task.cancel()
            raise RuntimeError(
                "Timeout error while connecting to Telegram server, "
                "try restart or get a new session key (run login.py)"
            ) from e


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
