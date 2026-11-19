import inspect
from typing import List, Optional

from telethon import types, utils

from .hints import EventAlbumMessage, EventMessage
from .misc.links import private_message_link

_MESSAGE_FIELDS = tuple(inspect.signature(EventMessage.__init__).parameters)[1:]  # without self


class MappedChannelName:
    def __init__(self, mapped: dict[int, str]) -> None:
        self.__mapped = mapped

    def channel_name(self, message: EventMessage) -> Optional[str]:
        """Get chat/channel display name"""
        return self.__mapped.get(message.chat_id, utils.get_display_name(message.chat))


class ChannelName:
    def channel_name(self, message: EventMessage) -> Optional[str]:
        """Get chat/channel display name"""
        return utils.get_display_name(message.chat)


class MessageLink:
    def message_link(self, message: EventMessage) -> Optional[str]:
        """Get link to message from origin channel"""
        if not isinstance(message.peer_id, types.PeerUser):
            if hasattr(message.chat, "username") and message.chat.username:
                link = f"https://t.me/{message.chat.username}/{message.id}"
            else:
                link = private_message_link(message.chat_id, message.id)
            return link
        return None


class CopyEventMessage:
    def copy_message(self, message: EventMessage) -> EventMessage:
        """Copy message via constructor:
        `message`, `entities` and `media` properties
        shouldn't be affected by changes from original message

        Args:
            message (`EventMessage`): Source message

        Returns:
            `EventMessage`: Copied message
        """
        from copy import deepcopy

        # Every field the constructor takes, so one Telethon adds isn't lost
        # (a fixed list missed offline, factcheck, rich_message…).
        cloned = EventMessage(**{
            field: deepcopy(getattr(message, field, None)) if field in ("media", "entities")
            else getattr(message, field, None)
            for field in _MESSAGE_FIELDS
        })
        cloned._chat = message._chat
        cloned._client = message._client
        return cloned

    def copy_album(self, album: EventAlbumMessage) -> EventAlbumMessage:
        """Copy album via constructor:
        `message`, `entities` and `media` properties
        shouldn't be affected by changes from original album

        Args:
            album (`EventAlbumMessage`): Source album

        Returns:
            `EventAlbumMessage`: Copied album
        """
        return [self.copy_message(message) for message in album]


class UpdateEntitiesParams:
    def update_entities_params(
        self,
        entities: List[types.TypeMessageEntity],
        start: int,
        end: int,
        diff: int,
    ) -> None:
        """In-place iterative update entities `offset` and `length`:

        `[ ] ()`: Update `offset` += `diff`

        `( [ ] )`: Update `length` += `diff`

        `( [ ) ]`: Update `length` to `( )[ ]`

        `[ ( ] )`: Update `offset` to `[ ]( )`

        `[ ( ) ]`: Update `offset` and `length` to `[( )]`
        """
        if not entities or diff == 0:
            return

        for entity in entities:
            if entity.offset >= end:
                # After
                entity.offset += diff
            elif entity.offset <= start and entity.offset + entity.length >= end:
                # Before & After
                entity.length += diff
            elif entity.offset < start and start < entity.offset + entity.length < end:
                # Before with partial overlap
                entity.length -= (entity.offset + entity.length) - start
            elif start < entity.offset < end and entity.offset + entity.length > end:
                # After with partial overlap: the replaced span ate the entity's
                # head — keep only the tail that lies past `end`
                entity.length -= end - entity.offset
                entity.offset = end + diff
            elif (
                start <= entity.offset < end
                and start < entity.offset + entity.length <= end
            ):
                # Fully inside (may touch either edge; the full-span case is
                # already handled by the "Before & After" branch above): resize
                # to match the replacement.
                entity.offset = start
                entity.length = (end - start) + diff
