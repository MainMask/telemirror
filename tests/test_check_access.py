"""``check_access`` — which chat needs what (see sources, post in recipients)
and how the account's own rights in a dialog decide it. Read-only: it never
sends a request that changes anything."""

import types as _t

from telethon.tl.types import ChatAdminRights, ChatBannedRights

from config import DirectionConfig
from skylon_set import check_access
from telemirror.messagefilters import EmptyMessageFilter


def _cfg():
    return DirectionConfig(disable_delete=False, disable_edit=False, filters=EmptyMessageFilter())


def _chat(**kw):
    base = {"creator": False, "admin_rights": None, "banned_rights": None, "default_banned_rights": None,
            "broadcast": False, "megagroup": False, "noforwards": False, "title": "t"}
    base.update(kw)
    return _t.SimpleNamespace(**base)


def test_roles_cover_sources_targets_broadcast_and_tech():
    mapping = {-1001: {-9001: [_cfg()]}, -1777: {-9001: [_cfg()], -9002: [_cfg()]}}
    roles = check_access.collect_roles(mapping, broadcast=-1777, tech=-5555)
    assert roles == {-1001: {"source"}, -1777: {"broadcast"}, -9001: {"target"}, -9002: {"target"},
                     -5555: {"tech"}}


def test_can_post():
    assert check_access.can_post(_chat(broadcast=True, creator=True))
    assert check_access.can_post(_chat(broadcast=True, admin_rights=ChatAdminRights(post_messages=True)))
    assert not check_access.can_post(_chat(broadcast=True, admin_rights=ChatAdminRights(edit_messages=True)))
    assert not check_access.can_post(_chat(broadcast=True))  # a mere subscriber
    assert check_access.can_post(_chat(megagroup=True))  # a member of an open group
    assert not check_access.can_post(_chat(
        megagroup=True, default_banned_rights=ChatBannedRights(until_date=None, send_messages=True)))
    assert check_access.can_post(_chat(  # an admin isn't bound by the group's defaults
        megagroup=True, admin_rights=ChatAdminRights(),
        default_banned_rights=ChatBannedRights(until_date=None, send_messages=True)))


def test_check_chat_reasons_and_notes(monkeypatch):
    monkeypatch.setattr(check_access.utils, "get_display_name", lambda e: e.title)
    assert check_access.check_chat(-1, {"source"}, None)["reason"] == "not_member"
    row = check_access.check_chat(-2, {"target"}, _chat(broadcast=True, title="Mirror"))
    assert (row["ok"], row["reason"], row["title"]) == (False, "cannot_post", "Mirror")
    row = check_access.check_chat(-3, {"source"}, _chat(broadcast=True, noforwards=True))
    assert row["ok"] and row["note"] == "noforwards"  # a source is only read
