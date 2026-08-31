"""DocumentFilenameFilter._rename is a pure string transform — test it directly."""

from telemirror.messagefilters.documentfilenamefilter import DocumentFilenameFilter


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
