"""Sign-off coverage for RestrictSavingContentBypassFilter: a >threshold flood
during re-upload must propagate (so past_mode retries), while any other failure
becomes a DISCARD (protected media can't be sent without a fresh re-upload)."""

from datetime import datetime, timezone

import pytest
from telethon import errors, events
from telethon.tl import types

from telemirror.messagefilters.base import FilterAction
from telemirror.messagefilters.restrictsavingfilter import (
    RestrictSavingContentBypassFilter,
)
from tests.conftest import make_message, run


def _photo_message(client):
    media = types.MessageMediaPhoto(
        photo=types.Photo(
            id=1, access_hash=1, file_reference=b"x",
            date=datetime.now(timezone.utc), sizes=[], dc_id=1,
        )
    )
    msg = make_message(media=media)
    msg._chat = _NoForwards()
    msg._client = client
    return msg


class _NoForwards:
    noforwards = True


class _FloodClient:
    async def download_media(self, message, file):
        raise errors.FloodWaitError(request=None)


class _BrokenClient:
    async def download_media(self, message, file):
        raise RuntimeError("download failed")


def test_flood_during_reupload_propagates():
    f = RestrictSavingContentBypassFilter()
    with pytest.raises(errors.FloodWaitError):
        run(f._process_message(_photo_message(_FloodClient()), events.NewMessage.Event))


def test_other_failure_discards():
    f = RestrictSavingContentBypassFilter()
    action, _ = run(
        f._process_message(_photo_message(_BrokenClient()), events.NewMessage.Event)
    )
    assert action is FilterAction.DISCARD
