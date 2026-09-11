"""DocumentFilenameFilter._rename is a pure string transform — test it directly."""

import pytest
from telethon import events
from telethon.tl import types

from telemirror.messagefilters import MediaDownloadError
from telemirror.messagefilters.base import FilterAction
from telemirror.messagefilters.documentfilenamefilter import DocumentFilenameFilter
from tests.conftest import make_message, run


def test_suffix_applied_and_remove_substring_stripped():
    f = DocumentFilenameFilter(suffix="Movie", remove=["ADS"])
    assert f._rename("Movies Pack [ADS].mkv") == "Movies Pack - Movie.mkv"


def test_already_suffixed_is_idempotent():
    f = DocumentFilenameFilter(suffix="Movie")
    assert f._rename("X - Movie.mkv") == "X - Movie.mkv"


def test_stem_equal_to_bare_suffix_is_left_alone():
    f = DocumentFilenameFilter(suffix="Movie")
    assert f._rename("Movie.pdf") == "Movie.pdf"


def test_remove_strips_bracket_wrapping_and_one_separator():
    f = DocumentFilenameFilter(remove=["draft"])
    assert f._rename("report [draft].pdf") == "report.pdf"
    # fragment + one trailing separator is removed
    assert f._rename("report_draft_final.pdf") == "report_final.pdf"


def test_no_suffix_no_remove_is_noop():
    f = DocumentFilenameFilter()
    assert f._rename("whatever.zip") == "whatever.zip"


def _doc_message(client):
    media = types.MessageMediaDocument(
        document=types.Document(
            id=5, access_hash=0, file_reference=b"", date=None,
            mime_type="application/pdf", size=1024, dc_id=1,
            attributes=[types.DocumentAttributeFilename(file_name="lecture.pdf")],
        )
    )
    msg = make_message(media=media, channel_id=1000)
    msg._client = client
    return msg


class _MDEClient:
    async def download_media(self, message, file):
        raise MediaDownloadError("t.me/c/1/2: exhausted")


def test_media_download_error_propagates_when_strict(strict_media):
    """past_mode: a download that outlived its retries propagates so the replay
    wrapper retries — not swallowed into mirroring the old name."""
    f = DocumentFilenameFilter(suffix="@CitadelClan")
    with pytest.raises(MediaDownloadError):
        run(f._process_message(_doc_message(_MDEClient()), events.NewMessage.Event))


def test_media_download_error_mirrors_original_when_not_strict():
    """Live mirror: the document goes out under its original name rather than
    being dropped."""
    f = DocumentFilenameFilter(suffix="@CitadelClan")
    msg = _doc_message(_MDEClient())
    action, result = run(f._process_message(msg, events.NewMessage.Event))
    assert action is FilterAction.CONTINUE
    assert result.media is msg.media  # untouched original
