"""Shared media helpers for filters that re-upload a message's media."""

import asyncio
import contextvars
import logging
import os
import tempfile
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Awaitable, Callable, Optional

from telethon import errors, utils
from telethon.tl import types

from ..hints import EventMessage
from ..misc.links import private_message_link
from .base import FilterAction, FilterResult

logger = logging.getLogger(__name__)

# Telegram upload limit for accounts without a Premium subscription.
# Larger files can't be re-uploaded through this session.
UPLOAD_LIMIT_BYTES = 2 * 1024**3

# ~20 min of retries across 7 attempts. past_mode adds its own outer retry loop;
# the live mirror relies on this budget alone before it degrades to the original.
_DOWNLOAD_RETRY_DELAYS = (15, 45, 90, 180, 300, 600)  # seconds between attempts

# True while past_mode is replaying: a filter that still can't download re-raises
# MediaDownloadError so the checkpoint stays put and the message is retried.
# False (live mirror): the filter mirrors the original instead of dropping it.
# Set per message by EventProcessor; asyncio copies it into each update's task.
strict_media_mode: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "strict_media_mode", default=False
)


class MediaDownloadError(Exception):
    """Raised by ``download_media_with_retry`` once its spaced retries are spent
    on a *transient* Telegram file-serving failure.

    A filter re-raises it only under ``strict_media_mode`` (past_mode) so its
    retry wrapper re-runs from the checkpoint instead of committing a degraded
    mirror; the live mirror mirrors the original (un-watermarked / unrenamed)
    rather than lose the message. ``message_id`` is the source message that
    could not be downloaded — past_mode uses it to skip past a permanently
    stuck message instead of retrying forever.
    """

    def __init__(self, *args, message_id: Optional[int] = None) -> None:
        super().__init__(*args)
        self.message_id = message_id


async def fetch_fresh_media(client, chat_id: int, ids):
    """Refetch source message(s) by id for a fresh ``.media`` (the one grabbed
    when a message was iterated can go stale before it's used). ``ids`` may be
    a single id or a list of ids; the return shape mirrors it — a single
    ``.media`` or a list of them, in the same order as ``ids``.

    Returns ``None`` if any target message is gone or has lost its media,
    leaving it to the caller to decide how to surface that (raise, log and
    skip, ...) — shared by `download_media_with_retry` below and
    `EventProcessor._refresh_file_reference` in mirroring.py, which differ
    only in that reaction.
    """
    fresh = await client.get_messages(chat_id, ids=ids)
    if not utils.is_list_like(ids):
        if fresh is None or not fresh.media:
            return None
        return fresh.media
    fresh_list = fresh if utils.is_list_like(fresh) else [fresh]
    if (
        not fresh_list
        or len(fresh_list) != len(ids)
        or any(item is None or not item.media for item in fresh_list)
    ):
        return None
    return [item.media for item in fresh_list]


async def download_media_with_retry(message: EventMessage, **kwargs):
    """``message._client.download_media(message=message, **kwargs)`` with spaced
    retries over transient Telegram file-serving errors.

    A Telegram DC hiccup makes ``GetFileRequest`` time out; Telethon's own ``_call``
    retries its server errors ~6× over ~12s and, with ``raise_last_call_error``
    off, collapses them into ``ValueError('Request was unsuccessful N time(s)')`` —
    so that string is the only ValueError worth a slow retry, a bare one is a real
    bug. FloodWaitError is a deliberate omission: it must reach past_mode's retry
    wrapper. When the retries are spent the failure is re-raised as
    ``MediaDownloadError``; a non-transient error propagates unchanged.

    ``FileReferenceExpiredError`` (the file_reference grabbed when the message was
    iterated went stale before download) is handled separately, once: the message
    is refetched for a fresh reference and the download retried immediately, with
    no delay — it isn't a transient DC hiccup. A second occurrence after the
    refresh, or a refresh that finds the source gone, is re-raised as
    ``MediaDownloadError`` — same as an exhausted transient failure — so
    ``strict_media_mode`` callers still get the checkpoint-preserving retry
    contract instead of silently falling through to a bare ``except Exception``.
    If the post-refresh retry itself hits a transient error, it falls back to
    whatever is left of the normal spaced-retry schedule below rather than
    giving up.
    """
    attempts = len(_DOWNLOAD_RETRY_DELAYS) + 1
    refreshed = False
    i = 0
    while i < attempts:
        try:
            return await message._client.download_media(message=message, **kwargs)
        except errors.FileReferenceExpiredError as e:
            link = private_message_link(message.chat_id, message.id)
            if refreshed:
                raise MediaDownloadError(
                    f"{link}: file_reference expired again after refresh",
                    message_id=message.id,
                ) from e
            fresh_media = await fetch_fresh_media(
                message._client, message.chat_id, message.id
            )
            if fresh_media is None:
                raise MediaDownloadError(
                    f"{link}: source message is gone, can't refresh file_reference",
                    message_id=message.id,
                ) from e
            # Mutate the caller's message in place (not `message = fresh`) so
            # the refreshed reference is visible to the caller too — mirrors.py
            # does the same for its own shared message/album objects, letting
            # a later fan-out target reuse this refresh instead of redoing it.
            message.media = fresh_media
            refreshed = True
            # Retry with the fresh reference at the same `i` — the refresh
            # itself doesn't spend a budgeted attempt. A transient failure on
            # this retry now falls into the ConnectionError/TimeoutError/
            # ValueError handler below and reuses the remaining schedule; a
            # second FileReferenceExpiredError re-enters this except block
            # with `refreshed` already True and raises, above.
            continue
        except (ConnectionError, asyncio.TimeoutError, ValueError) as e:
            transient = not isinstance(e, ValueError) or "unsuccessful" in str(e)
            if not transient:
                raise
            link = private_message_link(message.chat_id, message.id)
            if i == attempts - 1:
                raise MediaDownloadError(
                    f"{link}: download failed after {attempts} attempts ({e})",
                    message_id=message.id,
                ) from e
            delay = _DOWNLOAD_RETRY_DELAYS[i]
            logger.warning(
                "media download failed (%s: %s) %s — retry %d/%d in %ds",
                type(e).__name__,
                e,
                link,
                i + 1,
                attempts - 1,
                delay,
            )
            await asyncio.sleep(delay)
            i += 1


def reupload_errors(
    fallback: Any,
    media_error_fmt: str,
    exception_fmt: str,
    log_arg=lambda message: message.chat_id,
):
    """Decorator for a re-upload coroutine ``(self, message, *a, **kw) -> T``,
    applying the contract every re-uploading filter needs:

    - ``FloodWaitError``/``FloodPremiumWaitError`` always propagate — past_mode's
      retry wrapper must see them, not a swallowed fallback.
    - ``MediaDownloadError`` propagates too under ``strict_media_mode``
      (past_mode replay); otherwise it's logged via ``media_error_fmt %
      log_arg(message)`` and ``fallback`` is returned.
    - Any other exception is logged (with traceback) via ``exception_fmt %
      log_arg(message)`` and also returns ``fallback``.

    ``fallback`` may be a plain value or a ``callable(message) -> T`` for a
    case that needs the message to build it (e.g. a distinct failure sentinel).
    ``log_arg`` defaults to the message's ``chat_id``; pass e.g.
    ``private_message_link`` when a site's existing log text needs the full link.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, message, *args, **kwargs):
            try:
                return await fn(self, message, *args, **kwargs)
            except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                raise
            except MediaDownloadError:
                if strict_media_mode.get():
                    raise  # past_mode: keep the checkpoint put and retry the message
                logger.warning(media_error_fmt, log_arg(message))
                return fallback(message) if callable(fallback) else fallback
            except Exception:
                logger.exception(exception_fmt, log_arg(message))
                return fallback(message) if callable(fallback) else fallback

        return wrapper

    return decorator


class ReuploadCache:
    """TTL + LRU cache of re-uploaded media, keyed by the source media id.

    A filter that downloads+re-uploads media runs once per fan-out target
    (`mirroring.py` copies the message and re-runs the whole chain for each
    target). Caching the produced handle lets the same upload be re-sent to all
    targets instead of re-downloading N times. One instance is created per
    filter *instantiation* in `config.build_filters`, which in practice is
    process-wide whenever directions share the top-level `default_filters`
    (true for every currently deployed config) — only a direction with its
    own YAML `filters:` override gets an isolated instance. A shared instance
    means a burst of more than `size` distinct media items across unrelated
    source channels within the TTL window can evict each other's entries.
    Instances live for the process either way.
    """

    def __init__(self, size: int = 16, ttl: float = 600.0) -> None:
        self._size = size
        self._ttl = ttl
        self._data: OrderedDict[int, tuple[float, Any]] = OrderedDict()
        self._inflight: dict[int, "asyncio.Future"] = {}

    def get(self, key: int) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            return None
        cached_at, value = entry
        if time.monotonic() - cached_at > self._ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def put(self, key: int, value: Any) -> None:
        self._data[key] = (time.monotonic(), value)
        self._data.move_to_end(key)
        while len(self._data) > self._size:
            self._data.popitem(last=False)

    async def get_or_create(
        self,
        key: int,
        factory: Callable[[], Awaitable[Any]],
        cacheable: Callable[[Any], bool] = lambda v: v is not None,
    ) -> Any:
        """Return the cached value for `key`, or run `factory()` once and
        cache its result. Concurrent callers for the same key (e.g. two
        Telegram updates dispatched as separate tasks that both process the
        same source media through a shared filter instance) await the same
        in-flight call instead of each redundantly downloading/re-encoding/
        re-uploading it. An exception from `factory()` propagates to every
        concurrent awaiter, matching each one's own expectation had it run
        alone (e.g. FloodWaitError must still reach past_mode's retry
        wrapper). `cacheable` decides whether a given result is worth
        caching — defaults to "not None" (a filter's own fallback value on
        failure is never cached, so the next attempt retries rather than
        being stuck with a remembered failure). It's evaluated exactly once,
        by whichever caller's `_run()` created the in-flight entry for this
        key — a caller that instead finds an existing `inflight` and just
        awaits it never gets its own `cacheable` argument consulted. Every
        caller sharing a given key must therefore agree on the caching
        policy for it (true today: each `@cached_reupload`-decorated method
        passes one fixed `cacheable` for the lifetime of its own `self._cache`
        instance) — this cache is not a fit for two call sites disagreeing on
        whether the same key's result is worth caching.

        Awaiting is shielded from the calling task's own cancellation: an
        awaiter being cancelled must not cancel `factory()` out from under
        any *other* concurrent awaiter of the same key. Cleanup of
        `_inflight[key]` happens once, via a done-callback on the shared
        task itself, rather than in each awaiter's own `finally` — so it
        can't race a still-waiting sibling either.
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        inflight = self._inflight.get(key)
        if inflight is None:

            async def _run() -> Any:
                result = await factory()
                if cacheable(result):
                    self.put(key, result)
                return result

            inflight = asyncio.ensure_future(_run())
            self._inflight[key] = inflight

            def _cleanup(_task: "asyncio.Future") -> None:
                if self._inflight.get(key) is inflight:
                    del self._inflight[key]

            inflight.add_done_callback(_cleanup)
        return await asyncio.shield(inflight)


def source_media_id(media: Optional["types.TypeMessageMedia"]) -> Optional[int]:
    """Stable id of the source photo/document, for `ReuploadCache` keys."""
    if isinstance(media, types.MessageMediaPhoto) and isinstance(
        media.photo, types.Photo
    ):
        return media.photo.id
    if isinstance(media, types.MessageMediaDocument) and isinstance(
        media.document, types.Document
    ):
        return media.document.id
    return None


def cached_media_result(
    cache: "ReuploadCache", message: EventMessage
) -> Optional["FilterResult[EventMessage]"]:
    """Applies a cached re-upload to `message.media` and returns the
    `FilterResult` a filter's `_process_message` should return immediately,
    or `None` if there's nothing cached yet for this media's source id — the
    caller should fall through to its own pre-check work in that case. Lets a
    filter's `_process_message` short-circuit before its own pre-check work
    (rename, size checks, attribute scans) on a fan-out target whose media a
    prior target already cached — `@cached_reupload`'s own single-flight
    cache alone only skips the expensive re-upload itself, not that up-front
    work. Shared by every re-uploading filter (`WatermarkRemovalFilter`,
    `DocumentFilenameFilter`, `RestrictSavingContentBypassFilter`) so this
    short-circuit is written once instead of identically copy-pasted into
    each `_process_message`.
    """
    key = source_media_id(message.media)
    if key is None:
        return None
    cached = cache.get(key)
    if cached is None:
        return None
    message.media = cached
    return FilterResult(FilterAction.CONTINUE, message)


def cached_reupload(
    cacheable: Callable[[Any], bool] = lambda v: v is not None,
):
    """Decorator for a re-upload coroutine ``(self, message, *a, **kw) -> T``:
    single-flighted and cached by ``source_media_id(message.media)`` via
    ``self._cache`` (a `ReuploadCache`). Stack it *outside*
    ``@reupload_errors`` (applied first / listed last) so a propagating
    FloodWaitError still reaches every concurrent awaiter, and a swallowed
    failure's fallback value is never cached (see ``cacheable``).
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, message, *args, **kwargs):
            key = source_media_id(message.media)
            if key is None:
                return await fn(self, message, *args, **kwargs)
            cache: ReuploadCache = self._cache
            return await cache.get_or_create(
                key, lambda: fn(self, message, *args, **kwargs), cacheable
            )

        return wrapper

    return decorator


def filename_of(document: types.Document) -> Optional[str]:
    """Return the ``DocumentAttributeFilename`` value, or ``None``."""
    return next(
        (
            a.file_name
            for a in document.attributes
            if isinstance(a, types.DocumentAttributeFilename)
        ),
        None,
    )


@asynccontextmanager
async def downloaded_tempfile(message: EventMessage, suffix: str = ""):
    """Download ``message``'s media to a temp file, yield its path, always clean up."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="telemirror-tmp-", suffix=suffix, delete=False
        ) as f:
            tmp_path = f.name
        await download_media_with_retry(message, file=tmp_path)
        yield tmp_path
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
