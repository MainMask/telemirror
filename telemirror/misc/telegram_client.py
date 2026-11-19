import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from telethon import TelegramClient, errors, functions
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)


def _consume_task_result(task: "asyncio.Task") -> None:
    """Retrieve a done task's result so asyncio doesn't log
    'Task exception was never retrieved' for a fire-and-forget task."""
    if not task.cancelled():
        task.exception()


async def cancel_and_await(task: "asyncio.Task") -> None:
    """Cancel `task` and wait for it to actually settle before moving on.
    Swallows CancelledError surfacing from this await — whether it's `task`
    itself settling as cancelled, or the calling coroutine being cancelled
    again while suspended here (e.g. a second SIGTERM landing mid-shutdown):
    either way the caller's own cleanup after this call must still run, same
    as this collapsed before. Any other exception `task` settles with (e.g.
    an unrelated failure that happened to land in the same window we decided
    to cancel it, making `.cancel()` a no-op) is logged rather than silently
    dropped — the caller only needs to know the task is no longer running,
    not its outcome, but a real bug in it shouldn't vanish without a trace."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("cancel_and_await: task raised %s: %s", type(e).__name__, e)


# The watchdog's connection probe (``connection_probe``):
# how long telethon may stay disconnected (auto-reconnecting) before we stop
# feeding systemd's watchdog and let it restart us fresh;
WATCHDOG_DISCONNECT_GRACE_SEC = 1800
# the bound on a single liveness round-trip — longer = the request path is
# wedged, not slow;
WATCHDOG_PROBE_TIMEOUT_SEC = 30
# consecutive failed round-trips on a live connection before we let systemd
# restart us — absorbs a lone dropped packet / brief DC hiccup.
WATCHDOG_PROBE_FAIL_STREAK = 3


def connection_probe(
    client: TelegramClient,
    log: logging.Logger,
    *,
    grace_sec: float = WATCHDOG_DISCONNECT_GRACE_SEC,
    timeout_sec: float = WATCHDOG_PROBE_TIMEOUT_SEC,
    fail_streak: int = WATCHDOG_PROBE_FAIL_STREAK,
    on_healthy: Optional[Callable[[], None]] = None,
) -> Callable[[], Awaitable[bool]]:
    """Liveness check for ``sdnotify.watchdog_loop`` (the live mirror and the
    history replay). Healthy = connected *and* a bounded ``updates.GetState``
    round-trip succeeds (catches a dead receive loop a bare ``is_connected()``
    would miss). A few round-trips may fail in a row (``fail_streak``) and a
    FloodWait counts as healthy — both are back-off situations, not hangs.
    While disconnected we stay 'healthy' for ``grace_sec`` so telethon's
    auto-reconnect gets a chance before a restart. ``on_healthy``: called
    after each successful round-trip."""
    disconnected_since: Optional[float] = None
    failures = 0

    async def probe() -> bool:
        nonlocal disconnected_since, failures
        if client.is_connected():
            disconnected_since = None
            try:
                await asyncio.wait_for(client(functions.updates.GetStateRequest()), timeout=timeout_sec)
            except (errors.FloodWaitError, errors.FloodPremiumWaitError) as e:
                log.warning("watchdog: rate-limited (%ss), still healthy", e.seconds)
                failures = 0
                return True
            except Exception as e:  # noqa: BLE001 - transient until the streak runs out
                failures += 1
                log.warning(
                    "watchdog: GetState probe failed %d/%d (%s: %s)",
                    failures, fail_streak, type(e).__name__, e,
                )
                return failures < fail_streak
            failures = 0
            if on_healthy is not None:
                on_healthy()
            return True
        now = time.monotonic()
        if disconnected_since is None:
            disconnected_since = now
        within_grace = now - disconnected_since < grace_sec
        if not within_grace:
            log.error("watchdog: disconnected > %ds, giving up on this process", grace_sec)
        return within_grace

    return probe


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
        except asyncio.TimeoutError as e:  # wait_for has cancelled the task
            raise RuntimeError(
                "Timeout error while connecting to Telegram server, "
                "try restart or sign in again (python -m telemirror.login)"
            ) from e


def apply_lang_pack(client: TelegramClient, lang_pack: Optional[str]) -> None:
    """Send ``lang_pack`` in initConnection. Telethon has no parameter for it
    and hardcodes ``''`` into its private ``_init_request``; an official-app
    fingerprint (``.jsession`` ``application.lang_pack``) needs the real value."""
    if lang_pack:
        client._init_request.lang_pack = lang_pack


def new_tdesktop_client() -> TelegramClient:
    """A fresh, signed-out client with the Telegram Desktop fingerprint new
    sessions are created with (``jsession.TDESKTOP_APP``): the sign-in by phone
    of ``telemirror.login`` and of the panel's 👤 Аккаунты."""
    from telemirror.misc.jsession import TDESKTOP_APP

    client = TelegramClient(
        StringSession(), TDESKTOP_APP["api_id"], TDESKTOP_APP["api_hash"],
        device_model=TDESKTOP_APP["device_name"], system_version=TDESKTOP_APP["sdk"],
        app_version=TDESKTOP_APP["app_version"], system_lang_code=TDESKTOP_APP["system_lang_code"],
    )
    apply_lang_pack(client, TDESKTOP_APP["lang_pack"])
    return client


def build_telegram_client(
    session_string: str,
    api_id: str,
    api_hash: str,
    *,
    device_model: Optional[str] = None,
    system_version: Optional[str] = None,
    app_version: Optional[str] = None,
    lang_pack: Optional[str] = None,
    system_lang_code: Optional[str] = None,
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
    (``telemirror.past``) give up after a bounded window.
    """
    lang_kwargs = {"system_lang_code": system_lang_code} if system_lang_code else {}
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
        **lang_kwargs,
    )
    apply_lang_pack(client, lang_pack)
    client.parse_mode = "markdown"
    return client
