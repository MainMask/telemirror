"""Sign-off coverage for setup_mirrors pure helpers: they decide which channels
get paired / renamed / deleted, so mis-matching could mis-target a destructive op."""

from types import SimpleNamespace

from skylon_set import setup_mirrors as sm


def test_has_de_sklad_variants():
    assert sm.has_de_sklad("News DÈ SKLAD 🗝")
    assert sm.has_de_sklad("News DE SKLAD")
    assert not sm.has_de_sklad("News Archonum")


def test_to_archonum_replaces_all_variants():
    assert sm.to_archonum("A DÉ SKLAD B") == "A Archonum B"
    assert sm.to_archonum("no brand here") == "no brand here"


def test_name_key_strips_brand_and_emoji():
    assert sm.name_key("Deals 🗝 DÈ SKLAD") == sm.name_key("Deals ⚜️ Archonum")
    assert sm.name_key("Deals Archonum") == "Deals"


def test_find_recipient_exact_then_fuzzy():
    exact = SimpleNamespace(title="Deals Archonum")
    fuzzy = SimpleNamespace(title="Deals ⚜️ Archonum")
    recipients = {"Deals ⚜️ Archonum": fuzzy, "Other Archonum": object()}

    # exact title wins when present
    assert sm.find_recipient("Deals ⚜️ Archonum", recipients) is fuzzy
    # otherwise fall back to brand/emoji-stripped name match
    assert sm.find_recipient("Deals Archonum", {**recipients, "Deals Archonum": exact}) is exact
    assert sm.find_recipient("Deals Archonum", recipients) is fuzzy
    assert sm.find_recipient("Nonexistent Archonum", recipients) is None
