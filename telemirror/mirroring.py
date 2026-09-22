import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, Dict, List, Optional, Tuple, Union

from telethon import TelegramClient, errors, events, utils
from telethon.tl import functions, types

from config import DirectionConfig
from telemirror._patch import (
    forward_messages,
    send_file,
    send_message,
    set_album_event_timeout,
)
from telemirror.hints import EventAlbumMessage, EventLike, EventMessage
from telemirror.messagefilters import (
    MediaDownloadError,
    fetch_fresh_media,
    strict_media_mode,
)
from telemirror.messagefilters.base import FilterAction
from telemirror.misc import sdnotify
from telemirror.misc.links import private_message_link
from telemirror.misc.lrucache import LRUCache
from telemirror.misc.message_groups import iter_message_groups
from telemirror.misc.telegram_client import build_telegram_client, connect_with_timeout
from telemirror.misc.topics import topic_id_of
from telemirror.mixins import CopyEventMessage, UpdateEntitiesParams
from telemirror.storage import Database, MirrorMessage


# Matches t.me/c/{peer_id}/{msg_id} (private) and t.me/{username}/{msg_id} (public).
# Trailing ?query or #fragment allowed; extra path segments (threads) are NOT matched.
_TG_MSG_LINK_RE = re.compile(
    r"https?://t\.me/(?:c/(\d+)|([a-zA-Z][a-zA-Z0-9_]*))/(\d+)(?:[?#][^\s]*)?$",
    re.IGNORECASE,
)

# Same order of magnitude as past_mode._FLOOD_RETRY_LIMIT. Safe to retry this many
# times only because the media itself is tracked in the DB *before* this loop runs
# (see `track_media` in new_message/new_album): a crash mid-retry can no longer
# cause the media to be resent, so waiting out a long FloodWait here just risks
# losing time, not correctness.
_TAIL_SEND_FLOOD_RETRY_LIMIT = 20
# flood_sleep_threshold=300 is fixed project-wide, so any FloodWaitError caught
# here already represents a wait >300s — and Telegram can return waits of
# hours. Cap each attempt's sleep so the worst case is bounded (retry_limit *
# this cap) instead of unbounded; a capped-short sleep still lets the retry
# loop recover from a flood that clears quickly.
_TAIL_SEND_MAX_SINGLE_WAIT_SEC = 60

# Returned by an `on_caption_too_long` hook passed to
# `_send_with_reference_refresh` to say "already fully handled (including
# config.send_delay) — the caller should just move on to the next target,
# without tracking a message or sleeping again."
_CAPTION_SPLIT_HANDLED = object()


def _resolve_logger(logger: Optional[Union[str, logging.Logger]]) -> logging.Logger:
    """Normalizes a `str` name / `Logger` / `None` constructor arg into a `Logger`."""
    if isinstance(logger, str):
        return logging.getLogger(logger)
    if isinstance(logger, logging.Logger):
        return logger
    return logging.getLogger(__name__)


class EventProcessor(CopyEventMessage, UpdateEntitiesParams):
    def __init__(
        self: "EventProcessor",
        chat_mapping: Dict[int, Dict[int, List[DirectionConfig]]],
        database: Database,
        client: TelegramClient,
        logger: logging.Logger,
        strict_media_errors: bool = False,
    ) -> None:
        """Message event processor

        Args:
            chat_mapping (`Dict[int, Dict[int, List[DirectionConfig]]]`): Chats mappings
            database (`Database`): Message IDs storage
            client (`TelegramClient`): Message sender client
            logger (`logging.Logger`): Logger
            strict_media_errors (`bool`): re-raise `MediaDownloadError` instead of
                logging and skipping. past_mode sets this so its retry wrapper
                re-runs from the checkpoint; the live mirror leaves it off and
                skips the message like any other filter failure.
        """
        self._chat_mapping = chat_mapping
        self._database = database
        self._client = client
        self._logger = logger
        self._strict_media_errors = strict_media_errors
        # Public t.me/<username> → Telethon peer id, resolved once per process.
        # Only successful resolutions are stored; a miss may become resolvable later.
        self._username_id_cache: LRUCache[str, int] = LRUCache(capacity=256)
        # (source_chat_id, source_message_id) -> futures resolved once a
        # new_message/new_album fan-out for that message finishes. A list, not
        # a single future: a redelivered/duplicate update for the same message
        # id would otherwise overwrite an older, still in-flight registration,
        # letting a waiter miss it entirely. delete_message/edit_message await
        # every in-flight entry before reading the DB, so a source message
        # deleted/edited right after posting can't race a still-in-progress
        # fan-out into an orphaned/unedited copy.
        self._fanout_inflight: Dict[Tuple[int, int], List[asyncio.Future]] = {}

    @asynccontextmanager
    async def _track_fanout(
        self: "EventProcessor", keys: List[Tuple[int, int]]
    ) -> AsyncIterator[None]:
        done_future: asyncio.Future = asyncio.get_running_loop().create_future()
        for key in keys:
            self._fanout_inflight.setdefault(key, []).append(done_future)
        try:
            yield
        finally:
            for key in keys:
                bucket = self._fanout_inflight.get(key)
                if bucket is not None:
                    try:
                        bucket.remove(done_future)
                    except ValueError:
                        pass
                    if not bucket:
                        self._fanout_inflight.pop(key, None)
            done_future.set_result(None)

    @property
    def logger(self: "EventProcessor") -> logging.Logger:
        """Read-only access for callers that hold an `EventProcessor` but
        aren't one themselves (e.g. `EventHandlers.on_private_message`)."""
        return self._logger

    @staticmethod
    def __handle_exceptions(fn):
        from functools import wraps

        @wraps(fn)
        async def wrapper(self: "EventProcessor", *args, **kw):
            try:
                return await fn(self, *args, **kw)
            except (errors.FloodWaitError, errors.FloodPremiumWaitError, MediaDownloadError):
                # >threshold FloodWait, or (past_mode only, via strict_media_mode)
                # a media download that outlived its retries: reach past_mode's
                # retry wrapper so the checkpoint isn't advanced past the message.
                raise
            except Exception as e:
                self._logger.error(e, exc_info=True)

        return wrapper

    async def _resolve_username_to_channel_id(
        self: "EventProcessor",
        username: str,
        source_chat_id: int,
        message: EventMessage,
    ) -> Optional[int]:
        """Resolve t.me username to Telethon peer ID; fast-path if it's the source channel."""
        source_chat = getattr(message, "_chat", None)
        source_username = getattr(source_chat, "username", None)
        if source_username and source_username.lower() == username.lower():
            return source_chat_id
        key = username.lower()
        cached = self._username_id_cache.get(key)
        if cached is not None:
            return cached
        try:
            entity = await self._client.get_entity(username)
            channel_id = utils.get_peer_id(entity)
            self._username_id_cache[key] = channel_id
            return channel_id
        except (errors.FloodWaitError, errors.FloodPremiumWaitError) as e:
            self._logger.warning(
                f"[Link rewrite]: flood-wait resolving @{username} ({e}); "
                "link left unresolved"
            )
            return None
        except Exception as e:
            self._logger.debug(
                f"[Link rewrite]: couldn't resolve @{username}: {type(e).__name__}: {e}"
            )
            return None

    async def _try_rewrite_tg_link(
        self: "EventProcessor",
        url: str,
        source_chat_id: int,
        message: EventMessage,
        outgoing_chat: int,
        fallback_link_url: Optional[str] = None,
        link_cache: Optional[dict] = None,
        to_topic_id: Optional[int] = None,
    ) -> Optional[str]:
        """Rewrite a t.me message URL to `outgoing_chat`'s own mirror
        equivalent, or return None.

        The DB lookup + entity fetch behind this depends only on ``url``, not
        on `outgoing_chat`/`to_topic_id`/`fallback_link_url` — see
        `__resolve_tg_link_mirrors` — so a per-event ``link_cache`` dict lets
        one message's links be resolved once instead of once per target/config,
        while still returning each target's own mirror rather than
        whichever target happened to be resolved first. ``to_topic_id`` is the
        current fan-out target's own topic (``config.to_topic_id``), used to
        pick the right mirror when the referenced channel holds more than one.
        """
        if link_cache is not None and url in link_cache:
            mirrors_by_channel = link_cache[url]
        else:
            mirrors_by_channel = await self.__resolve_tg_link_mirrors(
                url, source_chat_id, message
            )
            if link_cache is not None:
                link_cache[url] = mirrors_by_channel
        if mirrors_by_channel is None:
            return None
        mirror = self._with_legacy_topic_fallback(
            mirrors_by_channel, outgoing_chat, to_topic_id
        )
        if mirror is None:
            return fallback_link_url
        return private_message_link(mirror.mirror_channel, mirror.mirror_id)

    async def __resolve_tg_link_mirrors(
        self: "EventProcessor",
        url: str,
        source_chat_id: int,
        message: EventMessage,
    ) -> Optional[Dict[Tuple[int, Optional[int]], MirrorMessage]]:
        """Resolve a t.me message URL to its known mirrors, one per
        (target channel, target topic) pair that has an unambiguous one.

        Returns ``None`` when the URL isn't a recognized t.me message link, or
        the referenced channel has no configured mirror targets at all — in
        both cases every fan-out target must leave the link untouched
        regardless of ``fallback_link_url``. Otherwise returns a (possibly
        empty) ``{(mirror_channel, mirror_topic_id): MirrorMessage}`` map: a
        target/topic pair missing from it (not mirrored there, a username
        that failed to resolve, or reached via more than one still-ambiguous
        mirror — see `_unambiguous_mirror_per_channel`) falls back to
        ``fallback_link_url`` for that target instead of guessing another
        target's mirror.
        """
        m = _TG_MSG_LINK_RE.match(url)
        if not m:
            return None
        peer_id_str, username, msg_id_str = m.group(1), m.group(2), m.group(3)
        msg_id = int(msg_id_str)

        if peer_id_str:
            # t.me/c/{peer_id}/{msg_id} — private/supergroup channel
            referenced_channel_id = utils.get_peer_id(
                types.PeerChannel(int(peer_id_str))
            )
        else:
            # t.me/{username}/{msg_id} — public channel
            referenced_channel_id = await self._resolve_username_to_channel_id(
                username, source_chat_id, message
            )
            if referenced_channel_id is None:
                return {}

        # Find configured targets for the referenced source channel
        target_map = self._chat_mapping.get(referenced_channel_id, {})
        if not target_map:
            return None

        mirrors = await self._database.get_messages(msg_id, referenced_channel_id)
        candidates = [mm for mm in mirrors if mm.mirror_channel in target_map]
        return self._unambiguous_mirror_per_channel(candidates)

    async def _rewrite_links(
        self: "EventProcessor",
        message: EventMessage,
        source_chat_id: int,
        outgoing_chat: int,
        fallback_link_url: Optional[str] = None,
        link_cache: Optional[dict] = None,
        to_topic_id: Optional[int] = None,
    ) -> None:
        """Rewrite t.me message links in entities to point to `outgoing_chat`'s
        own mirrors.

        ``link_cache`` (optional): a per-event dict that memoizes link
        resolution across the fan-out; see `_try_rewrite_tg_link` — it's
        target-independent, so it's safe to share across every `outgoing_chat`
        this is called with for the same source event. ``to_topic_id`` is the
        current target's own topic (``config.to_topic_id``).
        """
        if not message.entities:
            return

        has_url_entity = any(
            isinstance(e, types.MessageEntityUrl) for e in message.entities
        )
        surrogate_text = utils.add_surrogate(message.message or "") if has_url_entity else None

        for entity in message.entities:
            if isinstance(entity, types.MessageEntityTextUrl):
                new_url = await self._try_rewrite_tg_link(
                    entity.url, source_chat_id, message, outgoing_chat,
                    fallback_link_url, link_cache, to_topic_id,
                )
                if new_url is not None:
                    entity.url = new_url

            elif isinstance(entity, types.MessageEntityUrl):
                if not surrogate_text:
                    continue
                old_url = utils.del_surrogate(
                    surrogate_text[entity.offset : entity.offset + entity.length]
                )
                new_url = await self._try_rewrite_tg_link(
                    old_url, source_chat_id, message, outgoing_chat,
                    fallback_link_url, link_cache, to_topic_id,
                )
                if new_url is not None:
                    new_surrogate = utils.add_surrogate(new_url)
                    surrogate_text = (
                        surrogate_text[: entity.offset]
                        + new_surrogate
                        + surrogate_text[entity.offset + entity.length :]
                    )
                    diff = len(new_surrogate) - entity.length
                    self.update_entities_params(
                        message.entities,
                        entity.offset,
                        entity.offset + entity.length,
                        diff,
                    )

        if surrogate_text:
            message.message = utils.del_surrogate(surrogate_text)

    def _matches_from_topic(
        self: "EventProcessor", config: DirectionConfig, message: EventMessage
    ) -> bool:
        """True if `message`'s incoming topic matches `config.from_topic_id`
        (or `config` isn't topic-scoped).

        message: topic_id = message.reply_to.reply_to_msg_id
        reply:   topic_id = message.reply_to.reply_to_top_id
        general topic: topic_id = 1
        """
        if config.from_topic_id is None:
            return True
        return config.from_topic_id == topic_id_of(message)

    def _restricted_content_blocks(
        self: "EventProcessor",
        config: DirectionConfig,
        restricted_saving_content: bool,
        chat_id: int,
        outgoing_chat: int,
    ) -> bool:
        """True (after logging) if `config` can't carry a `noforwards` source:
        forward mode can't bypass the restriction, and a filter chain that
        doesn't re-upload the media can't either. Shared by new_message and
        new_album.
        """
        blocked = restricted_saving_content and (
            not config.filters.restricted_content_allowed or config.mode == "forward"
        )
        if not blocked:
            return False
        self._logger.warning(
            f"Forwards from channel#{chat_id} "
            f"with `restricted saving content` "
            f"enabled to channel#{outgoing_chat} are not supported."
        )
        return True

    @staticmethod
    def _with_legacy_topic_fallback(mapping: dict, channel: int, topic_id: Optional[int]):
        """Look up `(channel, topic_id)`, falling back to `(channel, None)`
        — a pre-`mirror_topic_id` row with no recorded topic — when the
        topic-specific slot is missing. Without this, every mirror created
        before that column existed would silently stop being found by any
        topic-scoped direction the moment it ships (duplicate resends from
        the dedup guard, degraded reply-chains, un-rewritten links), until
        that row happens to be replaced. `mapping` may be a dict (returns
        the value) or the membership itself is checked by the caller via
        `in` on the *keys* — see the two calling shapes below.
        """
        found = mapping.get((channel, topic_id))
        if found is None and topic_id is not None:
            found = mapping.get((channel, None))
        return found

    @staticmethod
    def _configs_to_try_for_topic(
        configs: List[DirectionConfig],
        source_topic_id: Optional[int],
        mirror_topic_id: Optional[int],
        is_disabled: Callable[[DirectionConfig], bool],
    ) -> List[DirectionConfig]:
        """Ordered candidates for a mirror row with this `(source_topic_id,
        mirror_topic_id)` pair: an exact match on both is authoritative and
        the *only* candidate — that config's own decision (disabled, or its
        filter discarding/flooding) is final, since we know precisely which
        config produced the row. `mirror_topic_id` alone isn't enough: two
        directions can share the same destination topic (e.g. both
        `to_topic_id=None` for a non-forum target) while differing in
        `from_topic_id`, so `source_topic_id` (the row's own
        `DirectionConfig.from_topic_id`) disambiguates them. Falls back to
        every non-disabled config in `configs`, in list order, for a legacy
        row with no recorded topic or a topic-scoped direction that's since
        been removed from config — this project's behavior before either
        topic column existed, where it's genuinely unknown which config
        produced the row, so each is tried in turn. Used by
        `edit_message`/`delete_message`.
        """
        for c in configs:
            if c.from_topic_id == source_topic_id and c.to_topic_id == mirror_topic_id:
                return [c]
        return [c for c in configs if not is_disabled(c)]

    @staticmethod
    def _config_for_topic(
        configs: List[DirectionConfig],
        source_topic_id: Optional[int],
        mirror_topic_id: Optional[int],
        is_disabled: Callable[[DirectionConfig], bool],
    ) -> Optional[DirectionConfig]:
        """Single-candidate convenience wrapper for `delete_message`, which
        has no filter/discard concept to retry against (only
        `disable_delete`, already excluded by the fallback in
        `_configs_to_try_for_topic`) — see that method for the full
        rationale. `edit_message` uses `_configs_to_try_for_topic` directly
        so it can retry a sibling config when the fallback's first candidate
        discards or floods.
        """
        candidates = EventProcessor._configs_to_try_for_topic(
            configs, source_topic_id, mirror_topic_id, is_disabled
        )
        return candidates[0] if candidates else None

    def _already_mirrored_skip(
        self: "EventProcessor",
        kind_label: str,
        link: str,
        outgoing_chat: int,
        config: DirectionConfig,
        already_mirrored: set,
    ) -> bool:
        """True (after logging) if `outgoing_chat` already holds a mirror of
        this source produced by `config` specifically (its own
        `(from_topic_id, to_topic_id)` pair) and it's safe to skip
        re-sending. Checked per-config: two configs sharing an `outgoing_chat`
        are judged independently instead of either both skipping or both
        re-sending — including two configs that share a destination topic but
        differ in `from_topic_id`, which `mirror_topic_id` alone couldn't
        tell apart (see `_config_for_topic`). Falls back to a pre-migration
        `(outgoing_chat, None, None)` row, the same idea as
        `_with_legacy_topic_fallback` but keyed by set membership on a wider
        tuple rather than a dict lookup, so it isn't reused here. That
        fallback row is consumed (removed from `already_mirrored`) the first
        time some config claims it: it's genuinely unknown which config
        produced it, so it can justify skipping at most one config, not
        every topic-scoped config sharing this `outgoing_chat`. Shared by
        new_message and new_album.
        """
        key = (outgoing_chat, config.from_topic_id, config.to_topic_id)
        legacy_key = (outgoing_chat, None, None)
        if key not in already_mirrored:
            if key == legacy_key or legacy_key not in already_mirrored:
                return False
            already_mirrored.discard(legacy_key)
        self._logger.debug(
            "%s: %s already mirrored to chat#%s, skip", kind_label, link, outgoing_chat
        )
        return True

    @staticmethod
    def _resolve_reply_target(
        config: DirectionConfig,
        reply_to_messages: Dict[Tuple[int, Optional[int]], int],
        outgoing_chat: int,
    ) -> Tuple[Optional[int], Optional[int]]:
        """(reply_to, reply_to_topic_id) for one fan-out target: reply-chain
        to the mirrored parent when its mirror in this target's own topic is
        known, otherwise anchor a new top-level send to the target's own
        topic. Falls back to a pre-migration untagged row — see
        `_with_legacy_topic_fallback`. Shared by new_message and new_album.
        """
        reply_to_msg = EventProcessor._with_legacy_topic_fallback(
            reply_to_messages, outgoing_chat, config.to_topic_id
        )
        outgoing_topic_reply = reply_to_msg is not None and config.to_topic_id is not None
        reply_to = (
            reply_to_msg
            if outgoing_topic_reply or config.to_topic_id is None
            else config.to_topic_id
        )
        reply_to_topic_id = config.to_topic_id if outgoing_topic_reply else None
        return reply_to, reply_to_topic_id

    @staticmethod
    def _unambiguous_mirror_per_channel(
        mirrors: List[MirrorMessage],
    ) -> Dict[Tuple[int, Optional[int]], MirrorMessage]:
        """Group `mirrors` by `(mirror_channel, mirror_topic_id)`, keeping
        only slots reached by a single mirror. A pre-migration row (or a
        legitimate duplicate) with `mirror_topic_id is None` still collides
        with any sibling row that also has `mirror_topic_id is None` in the
        same channel — such a slot is left out entirely rather than
        guessing. Shared by `_reply_target_mirrors` and
        `__resolve_tg_link_mirrors`.
        """
        by_key: Dict[Tuple[int, Optional[int]], List[MirrorMessage]] = {}
        for mm in mirrors:
            by_key.setdefault((mm.mirror_channel, mm.mirror_topic_id), []).append(mm)
        return {key: rows[0] for key, rows in by_key.items() if len(rows) == 1}

    async def _reply_target_mirrors(
        self: "EventProcessor", chat_id: int, reply_to_msg_id: int
    ) -> Dict[Tuple[int, Optional[int]], int]:
        """Mirror id of ``reply_to_msg_id`` (from ``chat_id``) per
        ``(mirror_channel, mirror_topic_id)`` pair — used to reply-chain a
        mirrored message to its mirrored parent in the same topic.

        A mirror channel can hold more than one mirror of the same source
        message when it's reached by more than one topic-scoped
        ``DirectionConfig``. `_unambiguous_mirror_per_channel` resolves that
        by topic; a slot that's still ambiguous (e.g. pre-migration rows with
        no recorded topic) is left out entirely rather than reply-chaining to
        a mirror_id that may live in the wrong topic.
        """
        mirrors = await self._database.get_messages(reply_to_msg_id, chat_id)
        return {
            key: mm.mirror_id
            for key, mm in self._unambiguous_mirror_per_channel(mirrors).items()
        }

    async def _send_with_reference_refresh(
        self: "EventProcessor",
        *,
        send: Callable[[], Awaitable],
        apply_fresh_media: Callable[[List[types.TypeMessageMedia]], None],
        kind: str,
        outgoing_chat: int,
        chat_id: int,
        ids: List[int],
        source_link: str,
        flush_inserted: Callable[[], Awaitable[None]],
        on_caption_too_long: Optional[Callable[[], Awaitable]] = None,
        log_kind: Optional[str] = None,
        context_suffix: str = "",
    ):
        """Call `send()`; on ``FileReferenceExpiredError`` refresh the stale
        file_reference by refetching the source message(s) and call `send()`
        again, once, after `apply_fresh_media` has applied the fresh media. Because
        `apply_fresh_media` mutates whatever `send`'s closure reads (the
        outgoing message/album *and* the shared source message/album), the
        same `send` closure serves both attempts unchanged.

        `FloodWaitError`/`FloodPremiumWaitError` are flushed via `flush_inserted`
        and re-raised at either attempt, same contract as every send
        in this module. A ``MediaCaptionTooLongError`` from the *first* attempt
        is left uncaught for the caller's own handler to dispatch to its
        caption-split fallback; `on_caption_too_long` covers it recurring on
        the retried send (only relevant for `new_message`/`new_album`'s
        primary send — the caption-split fallbacks' own retry can't hit it,
        since their caption is already empty/safe by construction).

        Shared by `new_message`'s and `new_album`'s primary sends, and by
        `_send_with_caption_split`'s/`_send_album_with_caption_split`'s own
        retry-after-refresh. Returns `send()`'s result, or `None` if the
        caller should skip (as if via `continue`) this target.
        """
        log_kind = log_kind or kind

        async def _retry_after_refresh():
            try:
                return await send()
            except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                await flush_inserted()
                raise
            except Exception as e:
                if isinstance(e, errors.MediaCaptionTooLongError) and on_caption_too_long is not None:
                    return await on_caption_too_long()
                self._logger.error(
                    f"Error while sending {log_kind} to chat#{outgoing_chat}{context_suffix} "
                    f"after file_reference refresh. {type(e).__name__}: {e}"
                )
                return None

        try:
            return await send()
        except (errors.FloodWaitError, errors.FloodPremiumWaitError):
            await flush_inserted()
            raise
        except errors.FileReferenceExpiredError:
            # Refetch the source message(s) by id for a fresh file_reference
            # (the one grabbed when the message was iterated went stale
            # before send). `None` here means the caller should skip
            # (`continue`) this target: any source message is gone or has
            # lost its media.
            try:
                fresh_media = await fetch_fresh_media(self._client, chat_id, ids)
            except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                await flush_inserted()
                raise
            except Exception as e:
                self._logger.error(
                    f"Error while sending {kind} to chat#{outgoing_chat}. "
                    f"FileReferenceExpiredError: refetch failed. "
                    f"{type(e).__name__}: {e}"
                )
                return None
            if fresh_media is None:
                self._logger.error(
                    f"Error while sending {kind} to chat#{outgoing_chat}. "
                    f"FileReferenceExpiredError: source {kind} {source_link} "
                    f"is gone, can't refresh file_reference"
                )
                return None
            apply_fresh_media(fresh_media)
            return await _retry_after_refresh()
        except errors.MediaCaptionTooLongError:
            raise
        except Exception as e:
            self._logger.error(
                f"Error while sending {log_kind} to chat#{outgoing_chat}{context_suffix}. "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def _send_tail_text(
        self: "EventProcessor",
        *,
        outgoing_chat: int,
        text: str,
        entities: List[types.TypeMessageEntity],
        reply_to_id: int,
        reply_to_topic_id: Optional[int],
        what: str,
        context_suffix: str,
    ) -> None:
        """Send one caption-tail text (the part split off a too-long caption)
        with a bounded FloodWait retry, shared by `_send_with_caption_split`'s
        single text and `_send_album_with_caption_split`'s per-caption texts.
        Waiting out FloodWait in place here (rather than propagating, like every
        other send in this file) is safe only because the media/album it
        replies to is already tracked in the DB by the time this runs. Any
        other failure, or a FloodWait recurring past the retry limit, just
        loses this one tail text — the media stays delivered and tracked.
        """
        attempt = 0
        while True:
            try:
                # NB: this follow-up text message is intentionally not written
                # to the DB — only the media/album is tracked, so a later
                # edit/delete of the source won't touch it.
                await send_message(
                    self._client,
                    entity=outgoing_chat,
                    message=text,
                    formatting_entities=entities,
                    reply_to=reply_to_id,
                    reply_to_topic_id=reply_to_topic_id,
                )
                return
            except (errors.FloodWaitError, errors.FloodPremiumWaitError) as e:
                attempt += 1
                if attempt > _TAIL_SEND_FLOOD_RETRY_LIMIT:
                    self._logger.error(
                        f"Error while sending split {what} tail to chat#{outgoing_chat}"
                        f"{context_suffix}: FloodWait recurring after "
                        f"{_TAIL_SEND_FLOOD_RETRY_LIMIT} retries — giving up, caption "
                        f"text lost ({what} already delivered and tracked)"
                    )
                    return
                await asyncio.sleep(min(e.seconds, _TAIL_SEND_MAX_SINGLE_WAIT_SEC))
            except Exception as split_err:
                self._logger.error(
                    f"Error while sending split {what} tail to chat#{outgoing_chat}{context_suffix}. "
                    f"{type(split_err).__name__}: {split_err}"
                )
                return

    async def _send_with_caption_split(
        self: "EventProcessor",
        *,
        outgoing_chat: int,
        chat_id: int,
        message: EventMessage,
        source_link: str,
        filtered_message: EventMessage,
        reply_to: Optional[int],
        reply_to_topic_id: Optional[int],
        config: DirectionConfig,
        flush_inserted: Callable[[], Awaitable[None]],
        track_media: Callable[[types.Message], Awaitable[None]],
        context_suffix: str = "",
    ) -> None:
        """``MediaCaptionTooLongError`` fallback shared by `new_message`'s primary
        send attempt and its file_reference-refresh retry: send the media without
        a caption, then the caption as a separate reply.

        A ``FileReferenceExpiredError`` from this fallback's own send (the
        reference was already stale on the primary, not-yet-refreshed attempt)
        gets the same one-refresh-then-retry treatment as `new_message`'s outer
        handler, via `_send_with_reference_refresh`.
        """
        if not filtered_message.media or not filtered_message.message:
            self._logger.error(
                f"Error while sending message to chat#{outgoing_chat}{context_suffix}. "
                f"MediaCaptionTooLongError"
            )
            return
        # Caption > 1024 chars: send media without caption, then text separately
        text, entities = filtered_message.message, filtered_message.entities
        filtered_message.message = ""
        filtered_message.entities = None

        def _apply_fresh_message_media(fresh: List[types.TypeMessageMedia]) -> None:
            filtered_message.media = fresh[0]
            # Also refresh the shared source message: see new_message.
            message.media = fresh[0]

        outgoing_message = await self._send_with_reference_refresh(
            send=lambda: send_message(
                self._client,
                entity=outgoing_chat,
                message=filtered_message,
                formatting_entities=None,
                reply_to=reply_to,
                reply_to_topic_id=reply_to_topic_id,
                invert_media=filtered_message.invert_media,
                message_effect_id=filtered_message.effect,
            ),
            apply_fresh_media=_apply_fresh_message_media,
            kind="message",
            outgoing_chat=outgoing_chat,
            chat_id=chat_id,
            ids=[message.id],
            source_link=source_link,
            flush_inserted=flush_inserted,
            log_kind="split message",
            context_suffix=context_suffix,
        )
        if outgoing_message is None:
            return
        # Track the media now, before the tail-text send below: that send may
        # need to wait out a long FloodWait, and the media above is already
        # delivered — it must not depend on the tail's outcome to be recorded,
        # or a crash during the wait would make past_mode resend it.
        await track_media(outgoing_message)
        await self._send_tail_text(
            outgoing_chat=outgoing_chat,
            text=text,
            entities=entities,
            reply_to_id=outgoing_message.id,
            reply_to_topic_id=config.to_topic_id,
            what="message",
            context_suffix=context_suffix,
        )

    async def _send_album_with_caption_split(
        self: "EventProcessor",
        *,
        outgoing_chat: int,
        chat_id: int,
        idxs: List[int],
        album: EventAlbumMessage,
        album_link: str,
        files: List[types.TypeMessageMedia],
        captions: List[str],
        album_entities: List[List[types.TypeMessageEntity]],
        reply_to: Optional[int],
        reply_to_topic_id: Optional[int],
        config: DirectionConfig,
        flush_inserted: Callable[[], Awaitable[None]],
        track_media: Callable[[List[types.Message]], Awaitable[None]],
        invert_media: Optional[bool],
        message_effect_id: Optional[int],
        context_suffix: str = "",
    ) -> None:
        """``MediaCaptionTooLongError`` fallback shared by `new_album`'s primary
        send attempt and its file_reference-refresh retry: strip captions over
        1024 chars into separate text messages replying to the album, then send
        it with the safe captions.

        A ``FileReferenceExpiredError`` from this fallback's own send (the
        reference was already stale on the primary, not-yet-refreshed attempt)
        gets the same one-refresh-then-retry treatment as `new_album`'s outer
        handler, via `_send_with_reference_refresh`.
        """
        texts_to_send = []
        safe_captions = []
        safe_entities: List[List[types.TypeMessageEntity]] = []
        for i, caption in enumerate(captions):
            # Telegram counts caption length in UTF-16 code units, not Python
            # codepoints — an emoji-heavy caption can be <=1024 Python chars
            # while still exceeding the real limit (surrogate pairs).
            if len(utils.add_surrogate(caption)) > 1024:
                texts_to_send.append((i, caption, album_entities[i]))
                safe_captions.append("")
                safe_entities.append([])
            else:
                safe_captions.append(caption)
                safe_entities.append(album_entities[i])

        def _apply_fresh_album_media(fresh: List[types.TypeMessageMedia]) -> None:
            nonlocal files
            files = fresh
            # Also refresh the shared source album: see new_album.
            fresh_media_by_id = dict(zip(idxs, files, strict=True))
            for original_message in album:
                if original_message.id in fresh_media_by_id:
                    original_message.media = fresh_media_by_id[original_message.id]

        outgoing_messages = await self._send_with_reference_refresh(
            send=lambda: send_file(
                self._client,
                entity=outgoing_chat,
                caption=safe_captions,
                file=files,
                formatting_entities=safe_entities,
                reply_to=reply_to,
                reply_to_topic_id=reply_to_topic_id,
                invert_media=invert_media,
                message_effect_id=message_effect_id,
            ),
            apply_fresh_media=_apply_fresh_album_media,
            kind="album",
            outgoing_chat=outgoing_chat,
            chat_id=chat_id,
            ids=idxs,
            source_link=album_link,
            flush_inserted=flush_inserted,
            log_kind="split album",
            context_suffix=context_suffix,
        )
        if outgoing_messages is None:
            return
        # Track the album now, before the tail-caption sends below: those may
        # need to wait out a long FloodWait, and the album above is already
        # delivered — it must not depend on the tail's outcome to be recorded,
        # or a crash during the wait would make past_mode resend it.
        await track_media(outgoing_messages)
        for i, text, entities in texts_to_send:
            if i >= len(outgoing_messages):
                # Same "count mismatch, can't trust the mapping" case
                # track_media already guards for the DB insert — here it
                # means there's no sent message to anchor this tail text to.
                self._logger.error(
                    f"Error while sending split album tail to chat#{outgoing_chat}"
                    f"{context_suffix}: album send returned fewer messages than "
                    f"sent, can't anchor caption for source item {i}"
                )
                continue
            await self._send_tail_text(
                outgoing_chat=outgoing_chat,
                text=text,
                entities=entities,
                reply_to_id=outgoing_messages[i].id,
                reply_to_topic_id=config.to_topic_id,
                what="album",
                context_suffix=context_suffix,
            )

    def _make_flush_inserted(
        self: "EventProcessor", inserted: List[MirrorMessage], link: str
    ) -> Callable[[], Awaitable[None]]:
        """Closure over `inserted`: persists buffered `MirrorMessage` rows via
        `insert_batch`, leaving them queued for a later flush attempt if the
        write fails — the fan-out targets they describe are already sent, so
        losing their rows would strand them for a later edit/delete/resync.
        Shared by `new_message` and `new_album` so both fan-outs get the same
        already-sent-survives-a-DB-hiccup guarantee.
        """

        async def flush_inserted() -> None:
            if not inserted:
                return
            try:
                await self._database.insert_batch(inserted)
            except Exception as e:
                self._logger.error(
                    f"{len(inserted)} message(s) sent but NOT tracked in DB "
                    f"({link}): {type(e).__name__}: {e}"
                )
            else:
                # Written — drop them so a later flush in this same fan-out
                # doesn't re-insert them (duplicate binding_id rows).
                inserted.clear()

        return flush_inserted

    async def new_message(
        self: "EventProcessor", chat_id: int, message: EventMessage, message_link: str
    ):
        async with self._track_fanout([(chat_id, message.id)]):
            await self._new_message_impl(chat_id, message, message_link)

    @__handle_exceptions
    async def _new_message_impl(
        self: "EventProcessor", chat_id: int, message: EventMessage, message_link: str
    ):
        strict_media_mode.set(self._strict_media_errors)
        if message.action is not None:
            self._logger.info(
                f"[New message]: {message_link} is a service message, skipping"
            )
            return

        restricted_saving_content: bool = bool(message.chat and message.chat.noforwards)

        outgoing_chats = self._chat_mapping.get(chat_id)
        if not outgoing_chats:
            self._logger.warning(
                f"[New message]: No target chats for message {message_link}"
            )
            return

        self._logger.info(f"[New message]: {message_link}")

        reply_to_messages: Dict[Tuple[int, Optional[int]], int] = (
            await self._reply_target_mirrors(chat_id, message.reply_to_msg_id)
            if message.is_reply
            else {}
        )

        # Copy quiz poll as simple poll
        if isinstance(message.media, types.MessageMediaPoll):
            message.media.poll.quiz = None

        inserted: List[MirrorMessage] = []
        # Resolve each distinct t.me link once for the whole fan-out.
        link_cache: dict = {}
        # Targets that already hold a mirror of this source message in a given
        # topic — skip them so a past_mode retry (or a re-delivered update)
        # can't send a duplicate.
        already_mirrored = {
            (m.mirror_channel, m.source_topic_id, m.mirror_topic_id)
            for m in await self._database.get_messages(message.id, chat_id)
        }

        flush_inserted = self._make_flush_inserted(inserted, message_link)

        for outgoing_chat, configs in outgoing_chats.items():
            matching = [c for c in configs if self._matches_from_topic(c, message)]
            for config in matching:
                if self._already_mirrored_skip(
                    "[New message]", message_link, outgoing_chat, config, already_mirrored
                ):
                    continue
                if self._restricted_content_blocks(
                    config, restricted_saving_content, chat_id, outgoing_chat
                ):
                    continue

                message_copy = self.copy_message(message)
                # Rewrite internal t.me links BEFORE filters can strip them (copy mode only)
                if config.mode == "copy":
                    await self._rewrite_links(
                        message_copy, chat_id, outgoing_chat,
                        config.fallback_link_url, link_cache, config.to_topic_id,
                    )

                filtered_message: EventMessage
                try:
                    filter_action, filtered_message = await config.filters.process(
                        message_copy, events.NewMessage.Event
                    )
                except (
                    errors.FloodWaitError,
                    errors.FloodPremiumWaitError,
                    MediaDownloadError,
                ):
                    # earlier fan-out targets are already sent — persist their
                    # rows before this propagates (same as the send handlers)
                    await flush_inserted()
                    raise
                except Exception as e:
                    # A bug in one target's filter chain must not abort delivery
                    # to the remaining targets in this fan-out.
                    self._logger.error(
                        f"[New message]: filter chain failed for chat#{outgoing_chat}, "
                        f"skipping this target. {type(e).__name__}: {e}",
                        exc_info=True,
                    )
                    continue

                if filter_action is FilterAction.DISCARD:
                    self._logger.info(
                        f"[New message]: Message {message_link} was skipped "
                        f"by the filter for chat#{outgoing_chat}"
                    )
                    continue

                reply_to, reply_to_topic_id = self._resolve_reply_target(
                    config, reply_to_messages, outgoing_chat
                )

                async def track_media(
                    sent: types.Message,
                    filtered_message: EventMessage = filtered_message,
                    outgoing_chat: int = outgoing_chat,
                    config: DirectionConfig = config,
                ) -> None:
                    inserted.append(
                        MirrorMessage(
                            original_id=filtered_message.id,
                            original_channel=chat_id,
                            mirror_id=sent.id,
                            mirror_channel=outgoing_chat,
                            mirror_topic_id=config.to_topic_id,
                            source_topic_id=config.from_topic_id,
                        )
                    )
                    # Persist before the delay: a kill during the sleep must
                    # not leave an already-delivered message untracked (same
                    # write-then-sleep order as new_album).
                    await flush_inserted()

                def _apply_fresh_message_media(
                    fresh: List[types.TypeMessageMedia],
                    filtered_message: EventMessage = filtered_message,
                ) -> None:
                    filtered_message.media = fresh[0]
                    # Also refresh the shared source message: every remaining
                    # fan-out target for it copies from `message`, and would
                    # otherwise redo this same refetch against the same stale
                    # reference once per target.
                    message.media = fresh[0]

                async def _do_send(
                    outgoing_chat: int = outgoing_chat,
                    filtered_message: EventMessage = filtered_message,
                    reply_to: Optional[int] = reply_to,
                    reply_to_topic_id: Optional[int] = reply_to_topic_id,
                    config: DirectionConfig = config,
                ):
                    return (
                        await send_message(
                            self._client,
                            entity=outgoing_chat,
                            message=filtered_message,
                            formatting_entities=filtered_message.entities,
                            reply_to=reply_to,
                            reply_to_topic_id=reply_to_topic_id,
                            invert_media=filtered_message.invert_media,
                            message_effect_id=filtered_message.effect,
                        )
                        if config.mode == "copy"
                        else await forward_messages(
                            self._client,
                            entity=outgoing_chat,
                            messages=message,
                            reply_to_topic_id=config.to_topic_id,
                        )
                    )

                async def _on_caption_too_long(
                    outgoing_chat: int = outgoing_chat,
                    filtered_message: EventMessage = filtered_message,
                    reply_to: Optional[int] = reply_to,
                    reply_to_topic_id: Optional[int] = reply_to_topic_id,
                    config: DirectionConfig = config,
                ):
                    # Same caption-too-long fallback as the primary attempt
                    # above. Media presence was already confirmed by the
                    # refresh above.
                    await self._send_with_caption_split(
                        outgoing_chat=outgoing_chat,
                        chat_id=chat_id,
                        message=message,
                        source_link=message_link,
                        filtered_message=filtered_message,
                        reply_to=reply_to,
                        reply_to_topic_id=reply_to_topic_id,
                        config=config,
                        flush_inserted=flush_inserted,
                        track_media=track_media,
                        context_suffix=" after file_reference refresh",
                    )
                    # Tracking (if the media was actually delivered), and
                    # config.send_delay, already happened inside
                    # _send_with_caption_split / here.
                    if config.send_delay:
                        await asyncio.sleep(config.send_delay)
                    return _CAPTION_SPLIT_HANDLED

                try:
                    # The media's file_reference (grabbed when the message was
                    # iterated) can go stale before we get to send it —
                    # refetch the source message for a fresh one and retry
                    # once (FileReferenceExpiredError, copy mode only).
                    outgoing_message = await self._send_with_reference_refresh(
                        send=_do_send,
                        apply_fresh_media=_apply_fresh_message_media,
                        kind="message",
                        outgoing_chat=outgoing_chat,
                        chat_id=chat_id,
                        ids=[message.id],
                        source_link=message_link,
                        flush_inserted=flush_inserted,
                        on_caption_too_long=_on_caption_too_long,
                    )
                except errors.MediaCaptionTooLongError:
                    # MediaCaptionTooLongError can only originate from the
                    # send_message() call above, which only runs in copy mode.
                    await self._send_with_caption_split(
                        outgoing_chat=outgoing_chat,
                        chat_id=chat_id,
                        message=message,
                        source_link=message_link,
                        filtered_message=filtered_message,
                        reply_to=reply_to,
                        reply_to_topic_id=reply_to_topic_id,
                        config=config,
                        flush_inserted=flush_inserted,
                        track_media=track_media,
                    )
                    # Tracking (if the media was actually delivered) already
                    # happened inside _send_with_caption_split.
                    if config.send_delay:
                        await asyncio.sleep(config.send_delay)
                    continue

                if outgoing_message is _CAPTION_SPLIT_HANDLED:
                    continue
                if outgoing_message is None:
                    continue

                await track_media(outgoing_message)

                if config.send_delay:
                    await asyncio.sleep(config.send_delay)

        await flush_inserted()

    async def new_album(
        self: "EventProcessor", chat_id: int, album: EventAlbumMessage, album_link: str
    ) -> None:
        async with self._track_fanout([(chat_id, m.id) for m in album]):
            await self._new_album_impl(chat_id, album, album_link)

    @__handle_exceptions
    async def _new_album_impl(
        self: "EventProcessor", chat_id: int, album: EventAlbumMessage, album_link: str
    ) -> None:
        strict_media_mode.set(self._strict_media_errors)
        incoming_first_message: EventMessage = album[0]
        restricted_saving_content: bool = bool(
            incoming_first_message.chat and incoming_first_message.chat.noforwards
        )

        outgoing_chats = self._chat_mapping.get(chat_id)
        if not outgoing_chats:
            self._logger.warning(f"[New album]: No target chats for chat#{chat_id}")
            return

        self._logger.info(f"[New album]: {album_link}")

        reply_to_messages: Dict[Tuple[int, Optional[int]], int] = (
            await self._reply_target_mirrors(
                chat_id, incoming_first_message.reply_to_msg_id
            )
            if incoming_first_message.is_reply
            else {}
        )

        inserted: List[MirrorMessage] = []
        # Resolve each distinct t.me link once for the whole fan-out.
        link_cache: dict = {}
        already_mirrored = {
            (m.mirror_channel, m.source_topic_id, m.mirror_topic_id)
            for m in await self._database.get_messages(
                incoming_first_message.id, chat_id
            )
        }

        flush_inserted = self._make_flush_inserted(inserted, album_link)

        for outgoing_chat, configs in outgoing_chats.items():
            matching = [
                c for c in configs
                if self._matches_from_topic(c, incoming_first_message)
            ]
            for config in matching:
                if self._already_mirrored_skip(
                    "[New album]", album_link, outgoing_chat, config, already_mirrored
                ):
                    continue
                if self._restricted_content_blocks(
                    config, restricted_saving_content, chat_id, outgoing_chat
                ):
                    continue

                album_copy = self.copy_album(album)
                # Rewrite internal t.me links BEFORE filters can strip them (copy mode only)
                if config.mode == "copy":
                    for msg in album_copy:
                        await self._rewrite_links(
                            msg, chat_id, outgoing_chat,
                            config.fallback_link_url, link_cache, config.to_topic_id,
                        )

                filtered_album: EventAlbumMessage
                try:
                    filter_action, filtered_album = await config.filters.process(
                        album_copy, events.Album.Event
                    )
                except (
                    errors.FloodWaitError,
                    errors.FloodPremiumWaitError,
                    MediaDownloadError,
                ):
                    # earlier fan-out targets are already sent — persist their
                    # rows before this propagates (same as the send handlers)
                    await flush_inserted()
                    raise
                except Exception as e:
                    # A bug in one target's filter chain must not abort delivery
                    # to the remaining targets in this fan-out.
                    self._logger.error(
                        f"[New album]: filter chain failed for chat#{outgoing_chat}, "
                        f"skipping this target. {type(e).__name__}: {e}",
                        exc_info=True,
                    )
                    continue

                if filter_action is FilterAction.DISCARD:
                    self._logger.info(
                        f"[New album]: Message {album_link} was skipped "
                        f"by the filter for chat#{outgoing_chat}"
                    )
                    continue

                idxs: List[int] = []
                files: List[types.TypeMessageMedia] = []
                captions: List[str] = []
                album_entities: List[List[types.TypeMessageEntity]] = []
                for incoming_message in filtered_album:
                    idxs.append(incoming_message.id)
                    files.append(incoming_message.media)
                    # Use raw message text with explicit formatting_entities to avoid
                    # double-parsing (workaround for github.com/LonamiWebs/Telethon/issues/3065)
                    captions.append(incoming_message.message or "")
                    album_entities.append(incoming_message.entities or [])

                reply_to, reply_to_topic_id = self._resolve_reply_target(
                    config, reply_to_messages, outgoing_chat
                )

                async def track_media(
                    sent: List[types.Message],
                    idxs: List[int] = idxs,
                    outgoing_chat: int = outgoing_chat,
                    config: DirectionConfig = config,
                ) -> None:
                    if len(sent) != len(idxs):
                        # The positional zip below maps each sent message back to
                        # a source id; a count mismatch means we can't trust that
                        # mapping. Skip tracking rather than write wrong rows —
                        # the album is delivered, it just won't be reachable by a
                        # later edit/delete of the source.
                        self._logger.error(
                            f"[New album]: send to chat#{outgoing_chat} returned "
                            f"{len(sent)} message(s) for {len(idxs)} "
                            f"source item(s) — album NOT tracked (edit/delete of "
                            f"the source won't reach it)"
                        )
                        return
                    inserted.extend(
                        MirrorMessage(
                            original_id=idxs[message_index],
                            original_channel=chat_id,
                            mirror_id=sent_message.id,
                            mirror_channel=outgoing_chat,
                            mirror_topic_id=config.to_topic_id,
                            source_topic_id=config.from_topic_id,
                        )
                        for message_index, sent_message in enumerate(sent)
                    )
                    # Persist before the delay: a kill during the sleep must
                    # not leave an already-delivered album untracked (same
                    # write-then-sleep order as new_message).
                    await flush_inserted()

                # `files` is intentionally read by name (not bound as a
                # default arg like the other loop locals below) in `_do_send`
                # and `_on_caption_too_long`: it must see the *rebind* this
                # function does below when the retry needs the refreshed
                # media — a default arg would instead freeze the stale
                # pre-refresh value. Safe because `_do_send` and
                # `_on_caption_too_long` are only ever called synchronously
                # within this same loop iteration, never after it.
                def _apply_fresh_album_media(
                    fresh: List[types.TypeMessageMedia],
                    idxs: List[int] = idxs,
                ) -> None:
                    nonlocal files
                    files = fresh
                    # Also refresh the shared source album: every remaining
                    # fan-out target for it copies from `album`, and would
                    # otherwise redo this same refetch against the same stale
                    # references once per target.
                    fresh_media_by_id = dict(zip(idxs, files, strict=True))
                    for original_message in album:
                        if original_message.id in fresh_media_by_id:
                            original_message.media = fresh_media_by_id[
                                original_message.id
                            ]

                async def _do_send(
                    outgoing_chat: int = outgoing_chat,
                    captions: List[str] = captions,
                    album_entities: List[List[types.TypeMessageEntity]] = album_entities,
                    reply_to: Optional[int] = reply_to,
                    reply_to_topic_id: Optional[int] = reply_to_topic_id,
                    config: DirectionConfig = config,
                    invert_media: Optional[bool] = filtered_album[0].invert_media,
                    message_effect_id: Optional[int] = filtered_album[0].effect,
                ):
                    return (
                        await send_file(
                            self._client,
                            entity=outgoing_chat,
                            caption=captions,
                            file=files,  # noqa: B023 — see comment above _apply_fresh_album_media
                            formatting_entities=album_entities,
                            reply_to=reply_to,
                            reply_to_topic_id=reply_to_topic_id,
                            invert_media=invert_media,
                            message_effect_id=message_effect_id,
                        )
                        if config.mode == "copy"
                        else await forward_messages(
                            self._client,
                            entity=outgoing_chat,
                            messages=album,
                            reply_to_topic_id=config.to_topic_id,
                        )
                    )

                async def _on_caption_too_long(
                    outgoing_chat: int = outgoing_chat,
                    idxs: List[int] = idxs,
                    captions: List[str] = captions,
                    album_entities: List[List[types.TypeMessageEntity]] = album_entities,
                    reply_to: Optional[int] = reply_to,
                    reply_to_topic_id: Optional[int] = reply_to_topic_id,
                    config: DirectionConfig = config,
                    invert_media: Optional[bool] = filtered_album[0].invert_media,
                    message_effect_id: Optional[int] = filtered_album[0].effect,
                ):
                    # Same caption-too-long fallback as the primary attempt
                    # above.
                    await self._send_album_with_caption_split(
                        outgoing_chat=outgoing_chat,
                        chat_id=chat_id,
                        idxs=idxs,
                        album=album,
                        album_link=album_link,
                        files=files,  # noqa: B023 — see comment above _apply_fresh_album_media
                        captions=captions,
                        album_entities=album_entities,
                        reply_to=reply_to,
                        reply_to_topic_id=reply_to_topic_id,
                        config=config,
                        flush_inserted=flush_inserted,
                        track_media=track_media,
                        invert_media=invert_media,
                        message_effect_id=message_effect_id,
                        context_suffix=" after file_reference refresh",
                    )
                    if config.send_delay:
                        await asyncio.sleep(config.send_delay)
                    return _CAPTION_SPLIT_HANDLED

                try:
                    # See new_message: one of the album's file_references can
                    # go stale before send — refetch the source messages and
                    # retry once (FileReferenceExpiredError, copy mode only).
                    outgoing_messages = await self._send_with_reference_refresh(
                        send=_do_send,
                        apply_fresh_media=_apply_fresh_album_media,
                        kind="album",
                        outgoing_chat=outgoing_chat,
                        chat_id=chat_id,
                        ids=idxs,
                        source_link=album_link,
                        flush_inserted=flush_inserted,
                        on_caption_too_long=_on_caption_too_long,
                    )
                except errors.MediaCaptionTooLongError:
                    # MediaCaptionTooLongError can only originate from the
                    # send_file() call above, which only runs in copy mode.
                    await self._send_album_with_caption_split(
                        outgoing_chat=outgoing_chat,
                        chat_id=chat_id,
                        idxs=idxs,
                        album=album,
                        album_link=album_link,
                        files=files,
                        captions=captions,
                        album_entities=album_entities,
                        reply_to=reply_to,
                        reply_to_topic_id=reply_to_topic_id,
                        config=config,
                        flush_inserted=flush_inserted,
                        track_media=track_media,
                        invert_media=filtered_album[0].invert_media,
                        message_effect_id=filtered_album[0].effect,
                    )
                    # Tracking (if the album was actually delivered) already
                    # happened inside _send_album_with_caption_split.
                    if config.send_delay:
                        await asyncio.sleep(config.send_delay)
                    continue

                if outgoing_messages is _CAPTION_SPLIT_HANDLED:
                    continue
                if outgoing_messages is None:
                    continue

                # Expect non-empty list of messages
                if utils.is_list_like(outgoing_messages):
                    await track_media(outgoing_messages)

                if config.send_delay:
                    await asyncio.sleep(config.send_delay)

        await flush_inserted()

    @__handle_exceptions
    async def edit_message(
        self: "EventProcessor", chat_id: int, message: EventMessage, message_link: str
    ):
        # Same race as delete_message: a source message edited almost
        # immediately after posting can race a still in-progress
        # new_message/new_album fan-out for it — wait for that fan-out to
        # finish before reading the DB, so every target it actually reached
        # gets the edit, not just the ones tracked so far.
        pending = self._fanout_inflight.get((chat_id, message.id))
        if pending:
            await asyncio.gather(*pending)

        outgoing_messages = await self._database.get_messages(message.id, chat_id)
        if not outgoing_messages:
            self._logger.warning(
                f"[Edit message]: No target messages to edit for {message_link}"
            )
            return

        self._logger.info(f"[Edit message]: {message_link}")

        for outgoing_message in outgoing_messages:
            configs = self._chat_mapping.get(chat_id, {}).get(
                outgoing_message.mirror_channel
            )

            if configs is None:
                self._logger.warning(
                    f"[Edit message]: No direction configs for "
                    f"{chat_id}->{outgoing_message.mirror_channel}"
                )
                continue

            configs_to_try = self._configs_to_try_for_topic(
                configs,
                outgoing_message.source_topic_id,
                outgoing_message.mirror_topic_id,
                lambda c: c.disable_edit,
            )

            for config in configs_to_try:
                if config.disable_edit is True or config.mode == "forward":
                    continue

                try:
                    filter_action, filtered_message = await config.filters.process(
                        self.copy_message(message), events.MessageEdited.Event
                    )
                except Exception as e:
                    # Same "don't abort the rest of the fan-out" reasoning as
                    # the send below — see the comment there. Unlike
                    # new_message/new_album, FloodWaitError/MediaDownloadError
                    # aren't re-raised here: edit_message has no past_mode
                    # retry wrapper to catch them, so logging and moving on
                    # to the next target is already the right behavior for
                    # every exception type.
                    self._logger.error(
                        f"Error while filtering edited message for "
                        f"{outgoing_message.mirror_channel}#{outgoing_message.mirror_id}. "
                        f"{type(e).__name__}: {e}"
                    )
                    continue

                if filter_action is FilterAction.DISCARD:
                    self._logger.info(
                        f"[Edit message]: Message {message_link} was skipped "
                        f"by the filter for chat#{outgoing_message.mirror_channel}"
                    )
                    continue

                # process() is called with a single EventMessage (not an album),
                # so it always routes through _process_message and returns one
                # back — never the EventAlbumMessage half of FilterResult's type.
                assert not isinstance(filtered_message, list)

                # Prevent `MediaPrevInvalidError`: The old media cannot be edited
                # with anything else (such as stickers or voice notes).
                edit_media_allowed = (
                    not isinstance(filtered_message.media, types.MessageMediaDocument)
                    or not isinstance(filtered_message.media.document, types.Document)
                    or not any(
                        (isinstance(attr, types.DocumentAttributeAudio) and attr.voice is True)
                        or isinstance(attr, types.DocumentAttributeSticker)
                        for attr in filtered_message.media.document.attributes
                    )
                )
                async def _do_edit(
                    outgoing_message=outgoing_message,
                    filtered_message=filtered_message,
                    edit_media_allowed=edit_media_allowed,
                ):
                    await self._client.edit_message(
                        entity=outgoing_message.mirror_channel,
                        message=outgoing_message.mirror_id,
                        text=filtered_message.message,
                        formatting_entities=filtered_message.entities,
                        file=filtered_message.media if edit_media_allowed else None,
                        link_preview=isinstance(
                            filtered_message.media, types.MessageMediaWebPage
                        ),
                    )

                try:
                    await _do_edit()
                except errors.MessageNotModifiedError:
                    self._logger.warning(
                        f"Suppressed MessageNotModifiedError for message "
                        f"{outgoing_message.mirror_channel}#{outgoing_message.mirror_id}"
                    )
                except errors.FileReferenceExpiredError:
                    # Refetch the source message for a fresh file_reference
                    # (the one grabbed when the edit was dispatched went stale
                    # before send) and retry once, same contract as
                    # new_message/new_album's _send_with_reference_refresh.
                    try:
                        fresh_media = await fetch_fresh_media(
                            self._client, chat_id, message.id
                        )
                    except Exception as e:
                        self._logger.error(
                            f"Error while editing message "
                            f"{outgoing_message.mirror_channel}#{outgoing_message.mirror_id}. "
                            f"FileReferenceExpiredError: refetch failed. "
                            f"{type(e).__name__}: {e}"
                        )
                    else:
                        if fresh_media is None:
                            self._logger.error(
                                f"Error while editing message "
                                f"{outgoing_message.mirror_channel}#{outgoing_message.mirror_id}. "
                                f"FileReferenceExpiredError: source {message_link} "
                                f"is gone, can't refresh file_reference"
                            )
                        else:
                            filtered_message.media = fresh_media
                            # Also refresh the shared source message: every
                            # remaining outgoing_message/config for it copies
                            # from `message`, and would otherwise redo this
                            # same refetch against the same stale reference
                            # once per target — same reasoning as
                            # new_message/new_album's _apply_fresh_message_media.
                            message.media = fresh_media
                            try:
                                await _do_edit()
                            except errors.MessageNotModifiedError:
                                self._logger.warning(
                                    f"Suppressed MessageNotModifiedError for message "
                                    f"{outgoing_message.mirror_channel}#{outgoing_message.mirror_id}"
                                )
                            except Exception as e:
                                self._logger.error(
                                    f"Error while editing message "
                                    f"{outgoing_message.mirror_channel}#{outgoing_message.mirror_id} "
                                    f"after file_reference refresh. {type(e).__name__}: {e}"
                                )

                # FloodWaitError is deliberately NOT special-cased to propagate
                # here (unlike new_message/new_album): edit_message is only
                # reachable from the live on_edit_message handler and from
                # _sync_broadcast_channel's catch-up loop, neither of which has
                # a retry wrapper for it — propagating would only abort the
                # edit for every other, un-flooded outgoing_message in this
                # same loop, with no compensating benefit.
                except Exception as e:
                    self._logger.error(
                        f"Error while editing message "
                        f"{outgoing_message.mirror_channel}#{outgoing_message.mirror_id}. "
                        f"{type(e).__name__}: {e}"
                    )

                break  # edit each mirror message once regardless of how many configs exist

    @__handle_exceptions
    async def delete_message(
        self: "EventProcessor", chat_id: int, message_ids: List[int]
    ) -> None:
        # A source message deleted almost immediately after posting can race
        # a still in-progress new_message/new_album fan-out for it — wait for
        # any such fan-out to finish before reading the DB, so we see every
        # target it actually reached instead of only the ones tracked so far.
        pending = {
            future
            for mid in message_ids
            for future in self._fanout_inflight.get((chat_id, mid), [])
        }
        if pending:
            await asyncio.gather(*pending)

        deleting_messages = await self._database.get_messages_batch(
            message_ids, chat_id
        )
        if not deleting_messages:
            self._logger.warning(
                f"[Delete message]: No target messages to delete for chat#{chat_id}"
            )
            return

        self._logger.info(
            f"[Delete message]: Delete {len(message_ids)} messages from {chat_id}"
        )

        deleting_per_channel: Dict[int, List[int]] = {}

        for deleting_message in deleting_messages:
            configs = self._chat_mapping.get(chat_id, {}).get(
                deleting_message.mirror_channel
            )

            if configs is None:
                self._logger.warning(
                    f"[Delete message]: No direction configs for "
                    f"{chat_id}->{deleting_message.mirror_channel}"
                )
                continue

            config = self._config_for_topic(
                configs,
                deleting_message.source_topic_id,
                deleting_message.mirror_topic_id,
                lambda c: c.disable_delete,
            )
            if config is None or config.disable_delete is True:
                continue

            _ch_ids = deleting_per_channel.setdefault(
                deleting_message.mirror_channel, []
            )
            if deleting_message.mirror_id not in _ch_ids:
                _ch_ids.append(deleting_message.mirror_id)

        done_channels: List[int] = []
        for channel_id, mirror_ids in deleting_per_channel.items():
            try:
                await self._client.delete_messages(
                    entity=channel_id, message_ids=mirror_ids
                )
            except Exception as e:
                # FloodWaitError is deliberately NOT special-cased to propagate
                # here (unlike new_message/new_album): delete_message is only
                # reachable from the live on_deleted_message handler and from
                # _sync_broadcast_channel's catch-up loop, neither of which has
                # a retry wrapper for it — propagating would only abort the
                # delete for every other, un-flooded channel below, with no
                # compensating benefit. This channel's messages simply stay
                # untracked-as-done, so its rows are left in the DB below for
                # a future delete_message call to retry.
                self._logger.error(
                    f"Error while deleting messages from chat#{channel_id}. "
                    f"{type(e).__name__}: {e}"
                )
                continue
            done_channels.append(channel_id)

        if done_channels:
            try:
                # Scoped by mirror_id (not original_id): a channel reached by
                # more than one topic-scoped direction can hold several rows
                # sharing the same original_id, and only the ones actually
                # deleted from Telegram above (deleting_per_channel) may be
                # purged — a sibling topic's still-live row must survive. One
                # statement covers every done_channels entry.
                await self._database.delete_messages_for_channels_batch(
                    chat_id,
                    {cid: deleting_per_channel[cid] for cid in done_channels},
                )
            except Exception as e:
                self._logger.error(
                    f"Message(s) deleted from Telegram but DB purge failed for "
                    f"chat#{chat_id}, channels {done_channels}: {type(e).__name__}: {e}"
                )


class TelegramLogHandler(logging.Handler):
    """Sends WARNING+ log records to a Telegram channel.

    Identical messages (by text) are accumulated for _DEBOUNCE seconds,
    then sent once with ×N count. After sending, the same text is suppressed
    for _COOLDOWN seconds (total window ~60 s).
    """

    _DEBOUNCE = 5   # seconds to accumulate before sending
    _COOLDOWN = 55  # seconds of suppression after send (total ~60 s)

    _PREFIXES = {
        logging.WARNING:  "⚠️ WARNING",
        logging.ERROR:    "‼️ ERROR",
        logging.CRITICAL: "🚨 CRITICAL",
    }

    def __init__(self, client: TelegramClient, channel: int) -> None:
        super().__init__(logging.WARNING)
        self._client = client
        self._channel = channel
        self._loop = client.loop
        self._counts: dict = {}
        self._timers: dict = {}
        self._cooldown_until: dict = {}
        self._tasks: set = set()  # keep strong refs to in-flight send tasks

    def _format_record(self, record: logging.LogRecord) -> str:
        prefix = self._PREFIXES.get(record.levelno, "⚠️ WARNING")
        return f"{prefix}: {record.getMessage()}"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self._format_record(record)
        except Exception:
            self.handleError(record)
            return
        try:
            self._loop.call_soon_threadsafe(self._enqueue, text)  # thread-safe dispatch
        except RuntimeError:
            pass  # loop already closed (shutdown) — nothing we can do

    def _prune_cooldowns(self) -> None:
        """Drop expired cooldown entries so one-off messages don't leak."""
        now = self._loop.time()
        for text in [t for t, until in self._cooldown_until.items() if until <= now]:
            del self._cooldown_until[text]

    def _enqueue(self, text: str) -> None:
        """Runs in the event-loop thread — dict ops are safe here."""
        self._prune_cooldowns()
        if self._cooldown_until.get(text, 0) > self._loop.time():
            return  # within the suppression window

        self._counts[text] = self._counts.get(text, 0) + 1

        if text not in self._timers:  # only first occurrence schedules the send
            self._timers[text] = self._loop.call_later(self._DEBOUNCE, self._send, text)

    def _send(self, text: str) -> None:
        count = self._counts.pop(text, 1)
        self._timers.pop(text, None)
        self._cooldown_until[text] = self._loop.time() + self._COOLDOWN
        msg = f"{text} (×{count})" if count > 1 else text
        if not self._loop.is_closed():
            task = self._loop.create_task(self._do_send(msg))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _do_send(self, msg: str) -> None:
        try:
            await self._client.send_message(self._channel, msg)
        except Exception:
            pass  # handler must not raise; Telegram errors silently swallowed


class EventHandlers:
    def __init__(
        self: "EventHandlers",
        client: TelegramClient,
        chats: List[int],
        processor: EventProcessor,
        sender: Optional[TelegramClient] = None,
        tech_channel: Optional[int] = None,
    ) -> None:
        """Message event handler

        Args:
            client (`TelegramClient`): Message receiver client
            chats (`List[int]`): List of chats to be observed
            processor (`EventProcessor`): Event processor
            sender (`TelegramClient`, optional): Sender client for tech_channel notifications
            tech_channel (`int`, optional): Tech monitoring channel ID
        """
        client.add_event_handler(self.on_new_message, events.NewMessage(chats=chats))
        client.add_event_handler(self.on_album, events.Album(chats=chats))
        client.add_event_handler(
            self.on_edit_message, events.MessageEdited(chats=chats)
        )
        client.add_event_handler(
            self.on_deleted_message, events.MessageDeleted(chats=chats)
        )
        self._processor = processor

        if tech_channel and sender:
            self._sender = sender
            self._tech_channel = tech_channel
            client.add_event_handler(
                self.on_private_message,
                events.NewMessage(incoming=True, func=lambda e: e.is_private),
            )

    async def on_private_message(
        self: "EventHandlers", event: events.NewMessage.Event
    ) -> None:
        """Notify tech_channel about incoming private messages."""
        try:
            sender_obj = await event.get_sender()
            # sender-controlled — collapse whitespace and cap length so it
            # can't break or spam the tech-channel message.
            name = " ".join((utils.get_display_name(sender_obj) or "").split())[:100]
            username = f"@{sender_obj.username}" if getattr(sender_obj, "username", None) else "none"
            msg = f"📩 Private message from {name} ({username})"
            await self._sender.send_message(self._tech_channel, msg)
        except Exception as e:
            # Unlike every other handler here, this one doesn't go through
            # EventProcessor.__handle_exceptions — log through the same
            # logger it uses so a failure still reaches TECH_CHANNEL via
            # TelegramLogHandler, instead of only Telethon's own default
            # per-handler logging (a different logger, never attached to it).
            self._processor.logger.error(
                f"Error while notifying TECH_CHANNEL about a private message. "
                f"{type(e).__name__}: {e}"
            )

    def event_message_link(self: "EventHandlers", event: EventLike) -> str:
        """Get link to event message"""

        incoming_message_id: int
        if isinstance(event, (events.NewMessage.Event, events.MessageEdited.Event)):
            incoming_message_id = event.message.id
        elif isinstance(event, events.Album.Event):
            incoming_message_id = event.messages[0].id
        else:  # events.MessageDeleted.Event
            incoming_message_id = event.deleted_id

        return private_message_link(event.chat_id, incoming_message_id)

    async def on_new_message(
        self: "EventHandlers", event: events.NewMessage.Event
    ) -> None:
        """NewMessage event handler"""

        # Skip albums
        if hasattr(event, "grouped_id") and event.grouped_id is not None:
            return

        incoming_chat_id: int = event.chat_id
        incoming_message: EventMessage = event.message
        incoming_message_link: str = self.event_message_link(event)

        await self._processor.new_message(
            chat_id=incoming_chat_id,
            message=incoming_message,
            message_link=incoming_message_link,
        )

    async def on_album(self: "EventHandlers", event: events.Album.Event) -> None:
        """Album event handler"""

        incoming_chat_id: int = event.chat_id
        incoming_album: EventAlbumMessage = event.messages
        incoming_album_link: str = self.event_message_link(event)

        await self._processor.new_album(
            chat_id=incoming_chat_id,
            album=incoming_album,
            album_link=incoming_album_link,
        )

    async def on_edit_message(
        self: "EventHandlers", event: events.MessageEdited.Event
    ) -> None:
        """MessageEdited event handler"""

        # Skip updates with edit_hide attribute (reactions and so on...)
        if event.message.edit_hide is True:
            return

        incoming_chat_id: int = event.chat_id
        incoming_message: EventMessage = event.message
        incoming_message_link: str = self.event_message_link(event)

        await self._processor.edit_message(
            chat_id=incoming_chat_id,
            message=incoming_message,
            message_link=incoming_message_link,
        )

    async def on_deleted_message(
        self: "EventHandlers", event: events.MessageDeleted.Event
    ) -> None:
        """MessageDeleted event handler"""

        incoming_chat_id: int = event.chat_id
        deleted_ids: List[int] = event.deleted_ids

        await self._processor.delete_message(
            chat_id=incoming_chat_id, message_ids=deleted_ids
        )


class Mirroring:
    CONNECT_TIMEOUT_SEC = 30
    # Watchdog: how long telethon may stay disconnected (auto-reconnecting)
    # before we stop feeding systemd's watchdog and let it restart us fresh.
    WATCHDOG_DISCONNECT_GRACE_SEC = 1800
    # Bound on a single liveness round-trip; longer than this = the request
    # path is wedged, not slow.
    WATCHDOG_PROBE_TIMEOUT_SEC = 30
    # Consecutive failed round-trips on a live connection before we let systemd
    # restart us — absorbs a lone dropped packet / brief DC hiccup.
    WATCHDOG_PROBE_FAIL_STREAK = 3
    # No update of any kind for this long (while otherwise healthy) → warn to the
    # tech channel. Not a restart: a genuinely quiet feed looks the same.
    WATCHDOG_SILENCE_WARN_SEC = 7200

    def __init__(
        self: "Mirroring",
        chat_mapping: Dict[int, Dict[int, List[DirectionConfig]]],
        database: Database,
        receiver: TelegramClient,
        sender: TelegramClient,
        logger: Optional[Union[str, logging.Logger]] = None,
        broadcast_channel: Optional[int] = None,
        tech_channel: Optional[int] = None,
    ) -> None:
        """Configure channels mirroring

        Args:
            chat_mapping (`Dict[int, Dict[int, List[DirectionConfig]]]`): Chats mappings
            database (`Database`): Message IDs storage
            receiver (`TelegramClient`): Message receiver client
            sender (`TelegramClient`): Message sender client, can be same as `receiver`
            logger (`str` | `logging.Logger`, optional): Logger. Defaults to None.
            broadcast_channel (`int`, optional): Broadcast channel ID to sync on startup.
            tech_channel (`int`, optional): Technical monitoring channel ID.
        """
        logger = _resolve_logger(logger)

        self._chat_mapping = chat_mapping
        self._database = database
        self._receiver = receiver
        self._sender = sender
        self._broadcast_channel = broadcast_channel
        self._tech_channel = tech_channel

        self._processor = EventProcessor(
            chat_mapping=chat_mapping,
            database=database,
            client=sender,
            logger=logger,
        )
        self._logger = logger

    async def run(self: "Mirroring") -> None:
        self._logger.info(f"Channels mirroring config:\n{self.stringify_config()}")

        if self._sender != self._receiver:
            raise RuntimeError("Different clients are not supported now")

        await self.__connect_client(self._sender)

    def stringify_config(self: "Mirroring") -> str:
        """Stringify mirror config"""
        mirror_mapping = "\n".join(
            f"{source} -> {', '.join(f'{t} [{cfgs}]' for t, cfgs in targets.items())}"
            for source, targets in self._chat_mapping.items()
        )

        return f"Mirror mapping: \n{mirror_mapping}\nUsing database: {self._database}\n"

    async def _sync_broadcast_channel(
        self: "Mirroring", client: TelegramClient
    ) -> None:
        """Startup catch-up sync of the broadcast channel.

        Idempotent: a message is (re-)processed only when it is new or its
        ``edit_date`` advanced past what was last synced (`broadcast_sync`
        table). A restart on an already-synced channel does ~0 API calls.

        - Sends messages not yet mirrored.
        - Edits mirrors whose source was edited while the bot was offline.
        - Deletes mirrors whose source no longer exists.

        Streams `iter_messages` in one pass — only message IDs are held in
        memory, never the full history.

        When `broadcast_sync` is empty (first run after it was added) it is
        seeded from the `messages` table so previously mirrored posts are not
        re-sent.

        A message is marked synced regardless of send outcome; a rare failed
        first-time send won't auto-retry — clear the `broadcast_sync` rows for
        the channel (and its `messages` rows, or they are re-seeded) to force a
        full re-sync.

        `broadcast_sync` is keyed by source channel, not by target: a broadcast
        target added later is NOT backfilled by this sync.
        """
        bc = self._broadcast_channel
        assert bc is not None, "_sync_broadcast_channel requires broadcast_channel to be configured"
        self._logger.info(f"[Sync broadcast]: starting sync for channel#{bc}")

        synced = await self._database.get_broadcast_sync(bc)  # {msg_id: edit_ts|None}
        if not synced:
            # First run after `broadcast_sync` was introduced: seed it from the
            # messages already mirrored by earlier runs so this sync doesn't
            # re-send the whole channel history.
            for original_id in {
                m.original_id
                for m in await self._database.get_all_messages_for_channel(bc)
            }:
                await self._database.set_broadcast_sync(bc, original_id, None)
            synced = await self._database.get_broadcast_sync(bc)
        seen: set[int] = set()
        sent = edited = 0

        def _msg_link(msg_id: int) -> str:
            return private_message_link(bc, msg_id)

        def _edit_ts(msg: types.Message) -> Optional[int]:
            return int(msg.edit_date.timestamp()) if msg.edit_date else None

        async def process_single(msg: types.Message) -> None:
            nonlocal sent, edited
            ets = _edit_ts(msg)
            if msg.id not in synced:
                await self._processor.new_message(bc, msg, _msg_link(msg.id))
                await self._database.set_broadcast_sync(bc, msg.id, ets)
                sent += 1
            elif ets is not None and ets > (synced.get(msg.id) or 0):
                await self._processor.edit_message(bc, msg, _msg_link(msg.id))
                await self._database.set_broadcast_sync(bc, msg.id, ets)
                edited += 1

        async def process_album(album: List[types.Message]) -> None:
            nonlocal sent, edited
            first = album[0]
            if first.id not in synced:
                await self._processor.new_album(bc, album, _msg_link(first.id))
                for m in album:
                    await self._database.set_broadcast_sync(bc, m.id, _edit_ts(m))
                sent += 1
            else:
                for m in album:
                    ets = _edit_ts(m)
                    if ets is not None and ets > (synced.get(m.id) or 0):
                        await self._processor.edit_message(bc, m, _msg_link(m.id))
                        await self._database.set_broadcast_sync(bc, m.id, ets)
                        edited += 1

        async for group in iter_message_groups(
            client.iter_messages(bc, reverse=True)
        ):
            if isinstance(group, list):
                seen.update(m.id for m in group)
                await process_album(group)
            else:
                seen.add(group.id)
                await process_single(group)

        deleted = list(synced.keys() - seen)
        if deleted:
            self._logger.info(
                f"[Sync broadcast]: deleting {len(deleted)} removed message(s)"
            )
            await self._processor.delete_message(bc, deleted)
            await self._database.delete_broadcast_sync(bc, deleted)

        self._logger.info(
            f"[Sync broadcast]: done — {sent} sent, {edited} edited, "
            f"{len(deleted)} deleted"
        )

    async def __connect_client(self: "Mirroring", client: TelegramClient) -> None:
        watchdog_task: Optional[asyncio.Task] = None
        try:
            await connect_with_timeout(client, self.CONNECT_TIMEOUT_SEC)

            me = await client.get_me()
            if me is None:
                raise RuntimeError(
                    "There is no authorization for the user, "
                    "try restart or get a new session key (run login.py)"
                )

            at_username = f" (@{me.username})" if getattr(me, "username", None) else ""
            self._logger.info(
                f"Logged in as {utils.get_display_name(me)}{at_username}"
            )

            # Attach before the broadcast sync so its warnings/errors also reach
            # the tech channel.
            if self._tech_channel:
                logging.getLogger("telemirror").addHandler(
                    TelegramLogHandler(client, self._tech_channel)
                )

            # Auth confirmed — the service is up. Tell systemd (Type=notify) now,
            # before the potentially slow broadcast sync, and start pinging the
            # watchdog so a later hang gets us killed + restarted.
            sdnotify.notify("READY=1")
            watchdog_task = asyncio.create_task(
                sdnotify.watchdog_loop(self.__watchdog_probe(client))
            )

            # Register handlers BEFORE the broadcast sync: Telethon dispatches an
            # update to whatever is in `_event_builders` at the moment it arrives,
            # not a snapshot from when it was received — a handler added only
            # after the (potentially long) sync finishes would silently and
            # permanently miss any live update on ANY mirrored source channel
            # that arrived during the sync window. The trade-off this accepts is
            # narrower: a live broadcast-channel post arriving mid-sync could be
            # both dispatched live and picked up by the sync's own history walk,
            # sending it twice — a visible duplicate, not a silent loss.
            self._handlers = EventHandlers(
                client=self._receiver,
                chats=list(self._chat_mapping.keys()),
                processor=self._processor,
                sender=self._sender,
                tech_channel=self._tech_channel,
            )

            if self._broadcast_channel:
                try:
                    await self._sync_broadcast_channel(client)
                except Exception as e:
                    self._logger.error(
                        f"[Sync broadcast]: failed, live mirroring will continue. "
                        f"{type(e).__name__}: {e}",
                        exc_info=True,
                    )

            await client.run_until_disconnected()
        except (errors.UserDeactivatedBanError, errors.UserDeactivatedError):
            self._logger.critical(
                "Account banned/deactivated by Telegram. "
                "See https://github.com/lonamiwebs/telethon/issues/824"
            )
        except errors.PhoneNumberBannedError:
            self._logger.critical(
                "Phone number banned/deactivated by Telegram. "
                "See https://github.com/lonamiwebs/telethon/issues/824"
            )
        except (errors.SessionExpiredError, errors.SessionRevokedError):
            self._logger.critical(
                "The user's session has expired, "
                "try to get a new session key (run login.py)"
            )
        finally:
            if watchdog_task is not None:
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass
            sdnotify.notify("STOPPING=1")
            await client.disconnect()

    def __watchdog_probe(
        self: "Mirroring", client: TelegramClient
    ) -> Callable[[], Awaitable[bool]]:
        """Liveness check for ``sdnotify.watchdog_loop``. Healthy =
        connected *and* a bounded ``updates.GetState`` round-trip succeeds
        (catches a dead receive loop a bare ``is_connected()`` would miss). A
        few round-trips may fail in a row (``WATCHDOG_PROBE_FAIL_STREAK``) and a
        FloodWait counts as healthy — both are back-off situations, not hangs.
        While disconnected we stay 'healthy' for ``WATCHDOG_DISCONNECT_GRACE_SEC``
        so telethon's auto-reconnect gets a chance before a restart.

        A stalled update *dispatch* while requests still work can't be told from
        a genuinely quiet feed, so long silence only warns (to the tech channel),
        never restarts."""
        disconnected_since: Optional[float] = None
        fail_streak = 0
        last_silence_warn = 0.0
        self._last_update_ts = time.monotonic()

        async def _bump_last_update(_event) -> None:
            self._last_update_ts = time.monotonic()

        client.add_event_handler(_bump_last_update, events.Raw)

        async def probe() -> bool:
            nonlocal disconnected_since, fail_streak, last_silence_warn
            if client.is_connected():
                disconnected_since = None
                try:
                    await asyncio.wait_for(
                        client(functions.updates.GetStateRequest()),
                        timeout=self.WATCHDOG_PROBE_TIMEOUT_SEC,
                    )
                except (errors.FloodWaitError, errors.FloodPremiumWaitError) as e:
                    self._logger.warning("watchdog: rate-limited (%ss), still healthy", e.seconds)
                    fail_streak = 0
                    return True
                except Exception as e:  # noqa: BLE001 - transient until the streak runs out
                    fail_streak += 1
                    self._logger.warning(
                        "watchdog: GetState probe failed %d/%d (%s: %s)",
                        fail_streak, self.WATCHDOG_PROBE_FAIL_STREAK,
                        type(e).__name__, e,
                    )
                    return fail_streak < self.WATCHDOG_PROBE_FAIL_STREAK
                fail_streak = 0
                silent_for = time.monotonic() - self._last_update_ts
                if (
                    silent_for > self.WATCHDOG_SILENCE_WARN_SEC
                    and time.monotonic() - last_silence_warn > self.WATCHDOG_SILENCE_WARN_SEC
                ):
                    last_silence_warn = time.monotonic()
                    self._logger.warning(
                        "watchdog: no update in %.0f min — feed quiet or dispatch stalled",
                        silent_for / 60,
                    )
                return True
            now = time.monotonic()
            if disconnected_since is None:
                disconnected_since = now
            within_grace = now - disconnected_since < self.WATCHDOG_DISCONNECT_GRACE_SEC
            if not within_grace:
                self._logger.error(
                    "watchdog: disconnected > %ds, giving up on this process",
                    self.WATCHDOG_DISCONNECT_GRACE_SEC,
                )
            return within_grace

        return probe


class Telemirror:
    def __init__(
        self: "Telemirror",
        api_id: str,
        api_hash: str,
        session_string: str,
        chat_mapping: Dict[int, Dict[int, List[DirectionConfig]]],
        database: Database,
        logger: Optional[Union[str, logging.Logger]] = None,
        api_device_model: Optional[str] = None,
        api_system_version: Optional[str] = None,
        api_app_version: Optional[str] = None,
        broadcast_channel: Optional[int] = None,
        tech_channel: Optional[int] = None,
    ):
        """Telemirror

        Args:
            api_id (`str`): Telegram API id
            api_hash (`str`): Telegram API hash
            session_string (`str`): Telegram (telethon) session string
            chat_mapping (`Dict[int, Dict[int, List[DirectionConfig]]]`): Chats mappings
            database (`Database`): Message IDs storage
            logger (`str` | `logging.Logger`, optional): Logger. Defaults to None.
            api_device_model (`str`, optional): Telegram API device model. Defaults to `platform.uname().release`
            api_system_version (`str`, optional): Telegram API system version. Defaults to `platform.uname().machine`
            api_app_version (`str`, optional): Telegram API app version. Defaults to `telethon.version.__version__`
            broadcast_channel (`int`, optional): Broadcast channel ID to sync on startup. Defaults to None.
            tech_channel (`int`, optional): Technical monitoring channel ID. Defaults to None.
        """
        set_album_event_timeout(delay_sec=1.01)

        # Preparation for splitting receiver and sender. connection_retries=1000
        # keeps auto-reconnecting through a long outage instead of exiting; the
        # watchdog (Mirroring.WATCHDOG_DISCONNECT_GRACE_SEC) is what bounds how
        # long we wait before a fresh-process restart.
        recv_client = send_client = build_telegram_client(
            session_string,
            api_id,
            api_hash,
            device_model=api_device_model,
            system_version=api_system_version,
            app_version=api_app_version,
            connection_retries=1000,
            retry_delay=5,
        )

        logger = _resolve_logger(logger)

        self._logger = logger

        self._mirroring = Mirroring(
            chat_mapping=chat_mapping,
            database=database,
            receiver=recv_client,
            sender=send_client,
            logger=logger,
            broadcast_channel=broadcast_channel,
            tech_channel=tech_channel,
        )

    async def run(self: "Telemirror") -> None:
        """Start channels mirroring"""
        await self._mirroring.run()
