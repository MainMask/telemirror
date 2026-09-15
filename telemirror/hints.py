from typing import List, TypeAlias, Union

from telethon import events, tl

EventLike = Union[
    events.NewMessage.Event,
    events.MessageEdited.Event,
    events.Album.Event,
    events.MessageDeleted.Event,
]

EventMessage: TypeAlias = tl.patched.Message

EventAlbumMessage = List[EventMessage]

EventEntity = Union[EventMessage, EventAlbumMessage]
