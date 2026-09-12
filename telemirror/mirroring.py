import asyncio
import logging
import re
import time
from typing import Awaitable, Callable, Dict, List, Optional, Union

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
from telemirror.misc.telegram_client import build_telegram_client
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


def _consume_task_result(task: asyncio.Task) -> None:
    """Retrieve a done task's result so asyncio doesn't log
    'Task exception was never retrieved' for a fire-and-forget task."""
    if not task.cancelled():
        task.exception()


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
        except Exception:
            return None

    async def _try_rewrite_tg_link(
        self: "EventProcessor",
        url: str,
        source_chat_id: int,
        message: EventMessage,
        fallback_link_url: Optional[str] = None,
        link_cache: Optional[dict] = None,
    ) -> Optional[str]:
        """Rewrite a t.me message URL to its mirror equivalent, or return None.

        The resolution (DB lookup + entity fetch) depends only on
        ``(url, fallback_link_url)``, not on the fan-out target, so a per-event
        ``link_cache`` dict lets one message's links be resolved once instead of
        once per target/config.
        """
        cache_key = (url, fallback_link_url)
        if link_cache is not None and cache_key in link_cache:
            return link_cache[cache_key]
        result = await self.__resolve_tg_link_rewrite(
            url, source_chat_id, message, fallback_link_url
        )
        if link_cache is not None:
            link_cache[cache_key] = result
        return result

    async def __resolve_tg_link_rewrite(
        self: "EventProcessor",
        url: str,
        source_chat_id: int,
        message: EventMessage,
        fallback_link_url: Optional[str] = None,
    ) -> Optional[str]:
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
                return fallback_link_url

        # Find configured targets for the referenced source channel
        target_map = self._chat_mapping.get(referenced_channel_id, {})
        if not target_map:
            return None

        mirrors = await self._database.get_messages(msg_id, referenced_channel_id)
        mirror = next(
            (mm for mm in mirrors if mm.mirror_channel in target_map), None
        )
        if mirror is None:
            return fallback_link_url

        return private_message_link(mirror.mirror_channel, mirror.mirror_id)

    async def _rewrite_links(
        self: "EventProcessor",
        message: EventMessage,
        source_chat_id: int,
        fallback_link_url: Optional[str] = None,
        link_cache: Optional[dict] = None,
    ) -> None:
        """Rewrite t.me message links in entities to point to their mirrors.

        ``link_cache`` (optional): a per-event dict that memoizes link resolution
        across the fan-out; see ``_try_rewrite_tg_link``.
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
                    entity.url, source_chat_id, message, fallback_link_url, link_cache
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
                    old_url, source_chat_id, message, fallback_link_url, link_cache
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

    async def _refresh_file_reference(
        self: "EventProcessor",
        *,
        kind: str,
        outgoing_chat: int,
        chat_id: int,
        ids: List[int],
        source_link: str,
        flush_inserted: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> Optional[List[types.TypeMessageMedia]]:
        """Refetch source message(s) by id for a fresh file_reference (the one
        grabbed when the message was iterated went stale before send), shared
        by `new_message`'s and `new_album`'s ``FileReferenceExpiredError``
        handlers. Returns each id's fresh `.media`, in the same order as
        `ids`, or `None` if the caller should skip (`continue`) this target:
        any source message is gone or has lost its media. FloodWaitError
        propagates (after `flush_inserted`, if given) to past_mode's retry
        wrapper, same contract as every send attempt here.
        """
        try:
            fresh_media = await fetch_fresh_media(self._client, chat_id, ids)
        except (errors.FloodWaitError, errors.FloodPremiumWaitError):
            if flush_inserted is not None:
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
        return fresh_media

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
                await asyncio.sleep(e.seconds)
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
        handler, via the shared `_refresh_file_reference`, rather than being
        dropped by the generic exception handler below.
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
        try:
            outgoing_message = await send_message(
                self._client,
                entity=outgoing_chat,
                message=filtered_message,
                formatting_entities=None,
                reply_to=reply_to,
                reply_to_topic_id=reply_to_topic_id,
            )
        except (errors.FloodWaitError, errors.FloodPremiumWaitError):
            # Media not delivered: let past_mode's retry wrapper wait it out
            # without advancing the checkpoint past this message (same
            # contract as the outer handler in new_message).
            await flush_inserted()
            raise
        except errors.FileReferenceExpiredError:
            fresh_media = await self._refresh_file_reference(
                kind="message",
                outgoing_chat=outgoing_chat,
                chat_id=chat_id,
                ids=[message.id],
                source_link=source_link,
                flush_inserted=flush_inserted,
            )
            if fresh_media is None:
                return
            filtered_message.media = fresh_media[0]
            # Also refresh the shared source message: see new_message.
            message.media = fresh_media[0]
            try:
                outgoing_message = await send_message(
                    self._client,
                    entity=outgoing_chat,
                    message=filtered_message,
                    formatting_entities=None,
                    reply_to=reply_to,
                    reply_to_topic_id=reply_to_topic_id,
                )
            except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                await flush_inserted()
                raise
            except Exception as split_err:
                self._logger.error(
                    f"Error while sending split message to chat#{outgoing_chat}{context_suffix} "
                    f"after file_reference refresh. {type(split_err).__name__}: {split_err}"
                )
                return
        except Exception as split_err:
            self._logger.error(
                f"Error while sending split message to chat#{outgoing_chat}{context_suffix}. "
                f"{type(split_err).__name__}: {split_err}"
            )
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
        track_media: Callable[[List[types.Message]], Awaitable[None]],
        context_suffix: str = "",
    ) -> None:
        """``MediaCaptionTooLongError`` fallback shared by `new_album`'s primary
        send attempt and its file_reference-refresh retry: strip captions over
        1024 chars into separate text messages replying to the album, then send
        it with the safe captions.

        A ``FileReferenceExpiredError`` from this fallback's own send (the
        reference was already stale on the primary, not-yet-refreshed attempt)
        gets the same one-refresh-then-retry treatment as `new_album`'s outer
        handler, via the shared `_refresh_file_reference`, rather than being
        dropped by the generic exception handler below.
        """
        texts_to_send = []
        safe_captions = []
        safe_entities = []
        for i, caption in enumerate(captions):
            if len(caption) > 1024:
                texts_to_send.append((caption, album_entities[i]))
                safe_captions.append("")
                safe_entities.append([])
            else:
                safe_captions.append(caption)
                safe_entities.append(album_entities[i])
        try:
            outgoing_messages = await send_file(
                self._client,
                entity=outgoing_chat,
                caption=safe_captions,
                file=files,
                formatting_entities=safe_entities,
                reply_to=reply_to,
                reply_to_topic_id=reply_to_topic_id,
            )
        except (errors.FloodWaitError, errors.FloodPremiumWaitError):
            # Album not delivered: propagate to past_mode's retry wrapper
            # (same contract as the outer handler in new_album).
            raise
        except errors.FileReferenceExpiredError:
            fresh_files = await self._refresh_file_reference(
                kind="album",
                outgoing_chat=outgoing_chat,
                chat_id=chat_id,
                ids=idxs,
                source_link=album_link,
            )
            if fresh_files is None:
                return
            files = fresh_files
            # Also refresh the shared source album: see new_album.
            fresh_media_by_id = dict(zip(idxs, files, strict=True))
            for original_message in album:
                if original_message.id in fresh_media_by_id:
                    original_message.media = fresh_media_by_id[original_message.id]
            try:
                outgoing_messages = await send_file(
                    self._client,
                    entity=outgoing_chat,
                    caption=safe_captions,
                    file=files,
                    formatting_entities=safe_entities,
                    reply_to=reply_to,
                    reply_to_topic_id=reply_to_topic_id,
                )
            except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                raise
            except Exception as split_err:
                self._logger.error(
                    f"Error while sending split album to chat#{outgoing_chat}{context_suffix} "
                    f"after file_reference refresh. {type(split_err).__name__}: {split_err}"
                )
                return
        except Exception as split_err:
            self._logger.error(
                f"Error while sending split album to chat#{outgoing_chat}{context_suffix}. "
                f"{type(split_err).__name__}: {split_err}"
            )
            return
        # Track the album now, before the tail-caption sends below: those may
        # need to wait out a long FloodWait, and the album above is already
        # delivered — it must not depend on the tail's outcome to be recorded,
        # or a crash during the wait would make past_mode resend it.
        await track_media(outgoing_messages)
        for text, entities in texts_to_send:
            await self._send_tail_text(
                outgoing_chat=outgoing_chat,
                text=text,
                entities=entities,
                reply_to_id=outgoing_messages[0].id,
                reply_to_topic_id=config.to_topic_id,
                what="album",
                context_suffix=context_suffix,
            )

    @__handle_exceptions
    async def new_message(
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

        reply_to_messages: dict[int, int] = (
            {
                m.mirror_channel: m.mirror_id
                for m in await self._database.get_messages(
                    message.reply_to_msg_id, chat_id
                )
            }
            if message.is_reply
            else {}
        )

        # Copy quiz poll as simple poll
        if isinstance(message.media, types.MessageMediaPoll):
            message.media.poll.quiz = None

        inserted: List[MirrorMessage] = []
        # Resolve each distinct t.me link once for the whole fan-out.
        link_cache: dict = {}
        # Targets that already hold a mirror of this source message — skip them
        # so a past_mode retry (or a re-delivered update) can't send a duplicate.
        already_mirrored = {
            m.mirror_channel
            for m in await self._database.get_messages(message.id, chat_id)
        }

        async def flush_inserted() -> None:
            if not inserted:
                return
            try:
                await self._database.insert_batch(inserted)
            except Exception as e:
                # Messages are already sent; without their DB rows a later
                # edit/delete can't reach them and a resync may duplicate them.
                self._logger.error(
                    f"{len(inserted)} message(s) sent but NOT tracked in DB "
                    f"({message_link}): {type(e).__name__}: {e}"
                )
            else:
                # Written — drop them so a later flush in this same fan-out
                # doesn't re-insert them (duplicate binding_id rows).
                inserted.clear()

        for outgoing_chat, configs in outgoing_chats.items():
            matching = [c for c in configs if self._matches_from_topic(c, message)]
            # Skip a target we've already mirrored this message to — but only
            # when it has a single route: `binding_id` has no topic column, so
            # for a multi-topic target one delivered topic would wrongly skip
            # the rest.
            if outgoing_chat in already_mirrored and len(matching) <= 1:
                self._logger.debug(
                    "[New message]: %s already mirrored to chat#%s, skip",
                    message_link, outgoing_chat,
                )
                continue
            for config in matching:
                if restricted_saving_content and (
                    not config.filters.restricted_content_allowed
                    or config.mode == "forward"
                ):
                    self._logger.warning(
                        f"Forwards from channel#{chat_id} "
                        f"with `restricted saving content` "
                        f"enabled to channel#{outgoing_chat} are not supported."
                    )
                    continue

                message_copy = self.copy_message(message)
                # Rewrite internal t.me links BEFORE filters can strip them (copy mode only)
                if config.mode == "copy":
                    await self._rewrite_links(
                        message_copy, chat_id, config.fallback_link_url, link_cache
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

                if filter_action is FilterAction.DISCARD:
                    self._logger.info(
                        f"[New message]: Message {message_link} was skipped "
                        f"by the filter for chat#{outgoing_chat}"
                    )
                    continue

                outgoing_topic_reply = (
                    reply_to_messages.get(outgoing_chat) is not None
                    and config.to_topic_id is not None
                )
                reply_to = (
                    reply_to_messages.get(outgoing_chat)
                    if outgoing_topic_reply or config.to_topic_id is None
                    else config.to_topic_id
                )
                reply_to_topic_id = config.to_topic_id if outgoing_topic_reply else None

                async def track_media(
                    sent: types.Message,
                    filtered_message: EventMessage = filtered_message,
                    outgoing_chat: int = outgoing_chat,
                ) -> None:
                    inserted.append(
                        MirrorMessage(
                            original_id=filtered_message.id,
                            original_channel=chat_id,
                            mirror_id=sent.id,
                            mirror_channel=outgoing_chat,
                        )
                    )
                    # Persist before the delay: a kill during the sleep must
                    # not leave an already-delivered message untracked (same
                    # write-then-sleep order as new_album).
                    await flush_inserted()

                outgoing_message: types.Message = None
                try:
                    outgoing_message = (
                        await send_message(
                            self._client,
                            entity=outgoing_chat,
                            message=filtered_message,
                            formatting_entities=filtered_message.entities,
                            reply_to=reply_to,
                            reply_to_topic_id=reply_to_topic_id,
                        )
                        if config.mode == "copy"
                        else await forward_messages(
                            self._client,
                            entity=outgoing_chat,
                            messages=message,
                            reply_to_topic_id=config.to_topic_id,
                        )
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
                except errors.FileReferenceExpiredError:
                    # The media's file_reference (grabbed when the message was
                    # iterated) went stale before we got to send it — refetch the
                    # source message for a fresh one and retry once. Can only
                    # originate from the send_message() call above (copy mode).
                    fresh_media = await self._refresh_file_reference(
                        kind="message",
                        outgoing_chat=outgoing_chat,
                        chat_id=chat_id,
                        ids=[message.id],
                        source_link=message_link,
                        flush_inserted=flush_inserted,
                    )
                    if fresh_media is None:
                        continue
                    filtered_message.media = fresh_media[0]
                    # Also refresh the shared source message: every remaining
                    # fan-out target for it copies from `message`, and would
                    # otherwise redo this same refetch against the same stale
                    # reference once per target.
                    message.media = fresh_media[0]
                    try:
                        outgoing_message = await send_message(
                            self._client,
                            entity=outgoing_chat,
                            message=filtered_message,
                            formatting_entities=filtered_message.entities,
                            reply_to=reply_to,
                            reply_to_topic_id=reply_to_topic_id,
                        )
                    except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                        # Same contract as every other send attempt above: let
                        # past_mode's retry wrapper wait it out rather than
                        # silently skipping the message.
                        await flush_inserted()
                        raise
                    except errors.MediaCaptionTooLongError:
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
                        if config.send_delay:
                            await asyncio.sleep(config.send_delay)
                        continue
                    except Exception as e:
                        self._logger.error(
                            f"Error while sending message to chat#{outgoing_chat} "
                            f"after file_reference refresh. {type(e).__name__}: {e}"
                        )
                        continue
                except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                    # Let a >threshold FloodWait propagate: past_mode's retry
                    # wrapper handles it without advancing the checkpoint past
                    # this un-sent message. In live mode there is no retry, so
                    # this aborts the rest of the fan-out for this message — an
                    # accepted trade-off (a >300s wait means the account is
                    # already heavily limited). Persist what was already sent
                    # to earlier targets before unwinding.
                    await flush_inserted()
                    raise
                except Exception as e:
                    self._logger.error(
                        f"Error while sending message to chat#{outgoing_chat}. "
                        f"{type(e).__name__}: {e}"
                    )
                    continue

                if outgoing_message:
                    await track_media(outgoing_message)

                if config.send_delay:
                    await asyncio.sleep(config.send_delay)

        await flush_inserted()

    @__handle_exceptions
    async def new_album(
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

        reply_to_messages: dict[int, int] = (
            {
                m.mirror_channel: m.mirror_id
                for m in await self._database.get_messages(
                    incoming_first_message.reply_to_msg_id, chat_id
                )
            }
            if incoming_first_message.is_reply
            else {}
        )

        # Resolve each distinct t.me link once for the whole fan-out.
        link_cache: dict = {}
        already_mirrored = {
            m.mirror_channel
            for m in await self._database.get_messages(
                incoming_first_message.id, chat_id
            )
        }

        for outgoing_chat, configs in outgoing_chats.items():
            matching = [
                c for c in configs
                if self._matches_from_topic(c, incoming_first_message)
            ]
            # See new_message: only skip a single-route target (binding_id has
            # no topic column).
            if outgoing_chat in already_mirrored and len(matching) <= 1:
                self._logger.debug(
                    "[New album]: %s already mirrored to chat#%s, skip",
                    album_link, outgoing_chat,
                )
                continue
            for config in matching:
                if restricted_saving_content and (
                    not config.filters.restricted_content_allowed
                    or config.mode == "forward"
                ):
                    self._logger.warning(
                        f"Forwards from channel#{chat_id} with "
                        f"`restricted saving content` "
                        f"enabled to channel#{outgoing_chat} are not supported."
                    )
                    continue

                album_copy = self.copy_album(album)
                # Rewrite internal t.me links BEFORE filters can strip them (copy mode only)
                if config.mode == "copy":
                    for msg in album_copy:
                        await self._rewrite_links(
                            msg, chat_id, config.fallback_link_url, link_cache
                        )

                filtered_album: EventAlbumMessage
                filter_action, filtered_album = await config.filters.process(
                    album_copy, events.Album.Event
                )

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

                outgoing_topic_reply = (
                    reply_to_messages.get(outgoing_chat) is not None
                    and config.to_topic_id is not None
                )
                reply_to = (
                    reply_to_messages.get(outgoing_chat)
                    if outgoing_topic_reply or config.to_topic_id is None
                    else config.to_topic_id
                )
                reply_to_topic_id = config.to_topic_id if outgoing_topic_reply else None

                async def track_media(
                    sent: List[types.Message],
                    idxs: List[int] = idxs,
                    outgoing_chat: int = outgoing_chat,
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
                    await self._database.insert_batch(
                        [
                            MirrorMessage(
                                original_id=idxs[message_index],
                                original_channel=chat_id,
                                mirror_id=sent_message.id,
                                mirror_channel=outgoing_chat,
                            )
                            for message_index, sent_message in enumerate(sent)
                        ]
                    )

                outgoing_messages: List[types.Message] = None
                try:
                    outgoing_messages = (
                        await send_file(
                            self._client,
                            entity=outgoing_chat,
                            caption=captions,
                            file=files,
                            formatting_entities=album_entities,
                            reply_to=reply_to,
                            reply_to_topic_id=reply_to_topic_id,
                        )
                        if config.mode == "copy"
                        else await forward_messages(
                            self._client,
                            entity=outgoing_chat,
                            messages=album,
                            reply_to_topic_id=config.to_topic_id,
                        )
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
                        track_media=track_media,
                    )
                    # Tracking (if the album was actually delivered) already
                    # happened inside _send_album_with_caption_split.
                    if config.send_delay:
                        await asyncio.sleep(config.send_delay)
                    continue
                except errors.FileReferenceExpiredError:
                    # See new_message: one of the album's file_references went
                    # stale before send — refetch the source messages and retry
                    # once. Can only originate from the send_file() call above
                    # (copy mode).
                    files = await self._refresh_file_reference(
                        kind="album",
                        outgoing_chat=outgoing_chat,
                        chat_id=chat_id,
                        ids=idxs,
                        source_link=album_link,
                    )
                    if files is None:
                        continue
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
                    try:
                        outgoing_messages = await send_file(
                            self._client,
                            entity=outgoing_chat,
                            caption=captions,
                            file=files,
                            formatting_entities=album_entities,
                            reply_to=reply_to,
                            reply_to_topic_id=reply_to_topic_id,
                        )
                    except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                        # Same contract as new_message: propagate to past_mode's
                        # retry wrapper instead of silently skipping the album.
                        raise
                    except errors.MediaCaptionTooLongError:
                        # Same caption-too-long fallback as the primary attempt
                        # above.
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
                            track_media=track_media,
                            context_suffix=" after file_reference refresh",
                        )
                        if config.send_delay:
                            await asyncio.sleep(config.send_delay)
                        continue
                    except Exception as e:
                        self._logger.error(
                            f"Error while sending album to chat#{outgoing_chat} "
                            f"after file_reference refresh. {type(e).__name__}: {e}"
                        )
                        continue
                except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                    # See new_message: propagate to past_mode's retry wrapper
                    # (in live mode this aborts the rest of the fan-out).
                    raise
                except Exception as e:
                    self._logger.error(
                        f"Error while sending album to chat#{outgoing_chat}. "
                        f"{type(e).__name__}: {e}"
                    )
                    continue

                # Expect non-empty list of messages
                if utils.is_list_like(outgoing_messages):
                    await track_media(outgoing_messages)

                if config.send_delay:
                    await asyncio.sleep(config.send_delay)

    @__handle_exceptions
    async def edit_message(
        self: "EventProcessor", chat_id: int, message: EventMessage, message_link: str
    ):
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

            for config in configs:
                if config.disable_edit is True or config.mode == "forward":
                    continue

                filter_action, filtered_message = await config.filters.process(
                    self.copy_message(message), events.MessageEdited.Event
                )
                if filter_action is FilterAction.DISCARD:
                    self._logger.info(
                        f"[Edit message]: Message {message_link} was skipped "
                        f"by the filter for chat#{outgoing_message.mirror_channel}"
                    )
                    continue

                # Prevent `MediaPrevInvalidError`: The old media cannot be edited
                # with anything else (such as stickers or voice notes).
                edit_media_allowed = (
                    not isinstance(filtered_message.media, types.MessageMediaDocument)
                    or not isinstance(filtered_message.media.document, types.Document)
                    or not any(
                        isinstance(attr, types.DocumentAttributeAudio)
                        and attr.voice is True
                        for attr in filtered_message.media.document.attributes
                    )
                )
                try:
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
                except errors.MessageNotModifiedError:
                    self._logger.warning(
                        f"Suppressed MessageNotModifiedError for message "
                        f"{outgoing_message.mirror_channel}#{outgoing_message.mirror_id}"
                    )

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
        deleted_original_ids: set[int] = set()

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

            for config in configs:
                if config.disable_delete is True:
                    continue

                _ch_ids = deleting_per_channel.setdefault(
                    deleting_message.mirror_channel, []
                )
                if deleting_message.mirror_id not in _ch_ids:
                    _ch_ids.append(deleting_message.mirror_id)
                deleted_original_ids.add(deleting_message.original_id)
                break  # add to deletion list once per mirror message

        for channel_id, mirror_ids in deleting_per_channel.items():
            try:
                await self._client.delete_messages(
                    entity=channel_id, message_ids=mirror_ids
                )
            except Exception as e:
                self._logger.error(
                    f"Error while deleting messages from chat#{channel_id}. "
                    f"{type(e).__name__}: {e}"
                )

        if deleted_original_ids:
            await self._database.delete_messages_batch(
                list(deleted_original_ids), chat_id
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
        sender_obj = await event.get_sender()
        # sender-controlled — collapse whitespace and cap length so it can't
        # break or spam the tech-channel message.
        name = " ".join((utils.get_display_name(sender_obj) or "").split())[:100]
        username = f"@{sender_obj.username}" if getattr(sender_obj, "username", None) else "none"
        msg = f"📩 Private message from {name} ({username})"
        await self._sender.send_message(self._tech_channel, msg)

    def event_message_link(self: "EventHandlers", event: EventLike) -> str:
        """Get link to event message"""

        if isinstance(event, (events.NewMessage.Event, events.MessageEdited.Event)):
            incoming_message_id: int = event.message.id
        elif isinstance(event, events.Album.Event):
            incoming_message_id: int = event.messages[0].id
        else:  # events.MessageDeleted.Event
            incoming_message_id: int = event.deleted_id

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
        logger: Union[str, logging.Logger] = None,
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
            if not client.is_connected():
                # Avoid `client.connect` hang forever:
                # https://github.com/LonamiWebs/Telethon/issues/1536
                # https://github.com/LonamiWebs/Telethon/issues/4119
                # `connect()` may report success before the transport is ready,
                # and may also never return — so the whole wait is bounded.
                connection_task = asyncio.create_task(client.connect())
                loop = asyncio.get_running_loop()
                deadline = loop.time() + self.CONNECT_TIMEOUT_SEC

                while not connection_task.done() and not client.is_connected():
                    if loop.time() >= deadline:
                        break
                    await asyncio.sleep(0.05)

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
        logger: Union[str, logging.Logger] = None,
        api_device_model: str = None,
        api_system_version: str = None,
        api_app_version: str = None,
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

        if isinstance(logger, str):
            logger = logging.getLogger(logger)
        elif not isinstance(logger, logging.Logger):
            logger = logging.getLogger(__name__)

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
