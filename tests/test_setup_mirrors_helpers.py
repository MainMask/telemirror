"""Sign-off coverage for setup_mirrors pure helpers: they decide which channels
get paired / renamed / deleted, so mis-matching could mis-target a destructive op."""

from types import SimpleNamespace

from skylon_set import setup_mirrors as sm


def test_has_de_sklad_variants():
    assert sm.has_de_sklad("News DÈ SKLAD 🗝")
    assert sm.has_de_sklad("News DE SKLAD")
    assert not sm.has_de_sklad("News ⚜️ Цитадель")


def test_to_citadel_replaces_trailer_and_appends_suffix():
    assert sm.to_citadel("CRYPTO ANGEL 🏴‍☠️ DÈ SKLAD") == "CRYPTO ANGEL ⚜️ Цитадель"
    assert sm.to_citadel("VECTRUM CLUB 🏴‍☠️DÈ SKLAD") == "VECTRUM CLUB ⚜️ Цитадель"
    assert sm.to_citadel("Pentagon Pro 🏴‍☠️ DE SKLAD") == "Pentagon Pro ⚜️ Цитадель"
    # no trailer → suffix is just appended (Q4: «Activity | …»)
    assert sm.to_citadel("Activity | Начинающий дропхантер") == (
        "Activity | Начинающий дропхантер ⚜️ Цитадель"
    )


def test_name_key_strips_brand_and_emoji():
    assert sm.name_key("Deals 🗝 DÈ SKLAD") == sm.name_key("Deals ⚜️ Цитадель")
    assert sm.name_key("Deals Цитадель") == "Deals"


def test_classify_donor():
    assert sm.classify_donor("CRYPTO ANGEL 🏴‍☠️ DÈ SKLAD") == "live"
    assert sm.classify_donor("Maloletoff Education 2024 🏴‍☠️ DÈ SKLAD") == "course"
    assert sm.classify_donor("Activity | Курс для новичков 2024") == "course"
    assert sm.classify_donor("Some Other Channel 🏴‍☠️ DÈ SKLAD") == "unknown"
    # an already-created recipient must never be picked up as a donor
    assert sm.classify_donor("CRYPTO ANGEL ⚜️ Цитадель") == "unknown"


def test_find_recipient_exact_then_fuzzy():
    exact = SimpleNamespace(title="Deals Цитадель")
    fuzzy = SimpleNamespace(title="Deals ⚜️ Цитадель")
    recipients = {"Deals ⚜️ Цитадель": fuzzy, "Other Цитадель": object()}

    # exact title wins when present
    assert sm.find_recipient("Deals ⚜️ Цитадель", recipients) is fuzzy
    # otherwise fall back to brand/emoji-stripped name match
    assert sm.find_recipient("Deals Цитадель", {**recipients, "Deals Цитадель": exact}) is exact
    assert sm.find_recipient("Deals Цитадель", recipients) is fuzzy
    assert sm.find_recipient("Nonexistent Цитадель", recipients) is None
