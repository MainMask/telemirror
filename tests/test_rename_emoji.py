from skylon_set.rename_emoji import normalize_title


def test_old_emoji_swapped_and_spacing_normalized():
    assert normalize_title("News🗝Archonum Trade") == "News ⚜️ Archonum Trade"


def test_already_normalized_returns_none():
    assert normalize_title("News ⚜️ Archonum Trade") is None


def test_no_archonum_after_emoji_is_skipped_not_mangled():
    # "Archonum" before the emoji: previously produced "Archonum ⚜️ Archonum"
    assert normalize_title("Archonum ⚜️ News") is None


def test_unrelated_title_untouched():
    assert normalize_title("Some Other Channel") is None
