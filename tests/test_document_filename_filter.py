"""DocumentFilenameFilter._rename is a pure string transform — test it directly."""

import pytest
from telethon import errors, events
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


def test_suffix_boundary_with_remove_cruft_still_cleans_on_first_pass():
    """A source filename whose stem happens to already look "suffixed" (ends
    with " - {suffix}") must still get its `remove`-list cleanup applied on a
    genuine first pass — the idempotency guard only skips re-appending the
    suffix, not the cleanup."""
    f = DocumentFilenameFilter(suffix="Repost", remove=["WATERMARK"])
    result = f._rename("SomeFile WATERMARK - Repost.pdf")
    assert "WATERMARK" not in result
    assert result.endswith("Repost.pdf")


def test_remove_and_suffix_together_stay_idempotent_on_second_pass():
    f = DocumentFilenameFilter(suffix="Repost", remove=["WATERMARK"])
    once = f._rename("Movie WATERMARK.mkv")
    twice = f._rename(once)
    assert once == twice == "Movie - Repost.mkv"


def test_remove_entry_matching_the_suffix_text_does_not_lose_the_suffix():
    """`remove` overlapping `suffix` (e.g. both configured as the same word)
    must not let the cleanup strip the suffix marker out from under a stale
    idempotency check — the suffix is always re-appended after cleanup, so
    the result is stable across repeated passes instead of oscillating."""
    f = DocumentFilenameFilter(suffix="Repost", remove=["Repost"])
    once = f._rename("Movie - Repost.mkv")
    twice = f._rename(once)
    assert once == twice == "Movie - Repost.mkv"


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


class _FloodClient:
    async def download_media(self, message, file):
        raise errors.FloodWaitError(request=None)


def test_flood_during_rename_reupload_propagates():
    """A >threshold FloodWait during the rename re-upload must reach past_mode's
    retry wrapper instead of being swallowed and sent under the old name."""
    f = DocumentFilenameFilter(suffix="@CitadelClan")
    with pytest.raises(errors.FloodWaitError):
        run(f._process_message(_doc_message(_FloodClient()), events.NewMessage.Event))
