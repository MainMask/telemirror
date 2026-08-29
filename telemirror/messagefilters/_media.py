"""Shared media helpers for filters that re-upload a message's media."""

import os
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

from telethon.tl import types

from ..hints import EventMessage

# Telegram upload limit for accounts without a Premium subscription.
# Larger files can't be re-uploaded through this session.
UPLOAD_LIMIT_BYTES = 2 * 1024**3


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
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            tmp_path = f.name
        await message._client.download_media(message=message, file=tmp_path)
        yield tmp_path
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
