"""DocumentFilenameFilter._rename is a pure string transform — test it directly."""

from telemirror.messagefilters.documentfilenamefilter import DocumentFilenameFilter


def test_prefix_applied_and_remove_substring_stripped():
    f = DocumentFilenameFilter(prefix="Movie", remove=["ADS"])
    # previously returned unchanged because the stem starts with "Movie"
    assert f._rename("Movies Pack [ADS].mkv") == "Movie - Movies Pack.mkv"


def test_already_prefixed_is_idempotent():
    f = DocumentFilenameFilter(prefix="Movie")
    assert f._rename("Movie - X.mkv") == "Movie - X.mkv"


def test_stem_equal_to_bare_prefix_is_left_alone():
    f = DocumentFilenameFilter(prefix="Movie")
    assert f._rename("Movie.pdf") == "Movie.pdf"


def test_remove_strips_bracket_wrapping_and_one_separator():
    f = DocumentFilenameFilter(remove=["draft"])
    assert f._rename("report [draft].pdf") == "report.pdf"
    # fragment + one trailing separator is removed
    assert f._rename("report_draft_final.pdf") == "report_final.pdf"


def test_no_prefix_no_remove_is_noop():
    f = DocumentFilenameFilter()
    assert f._rename("whatever.zip") == "whatever.zip"
