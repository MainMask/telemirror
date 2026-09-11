"""``anonymize_groups`` — Remain Anonymous carries every admin-right flag, and the
Hide Members pass only toggles groups that aren't hidden yet, skipping the ones
Telegram rejects as too small.
"""

import types as _t

import pytest
from telethon.errors import ParticipantsTooFewError
from telethon.tl.functions.channels import (
    EditAdminRequest,
    GetFullChannelRequest,
    GetParticipantRequest,
    ToggleParticipantsHiddenRequest,
)
from telethon.tl.types import ChannelParticipantAdmin, ChatAdminRights

from skylon_set import anonymize_groups
from tests.conftest import run


def test_get_rights_preserves_flags_and_sets_anonymous():
    src = ChatAdminRights(
        change_info=True, ban_users=True, pin_messages=True, anonymous=False
    )
    out = anonymize_groups.get_rights(src)
    assert out.anonymous is True
    assert out.change_info and out.ban_users and out.pin_messages
    assert not out.post_messages  # untouched flags stay falsy


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import skylon_set._common as common

    async def _noop(*_a, **_kw):
        pass

    monkeypatch.setattr(common.asyncio, "sleep", _noop)


class _FakeClient:
    def __init__(self, hidden_state, too_few=()):
        self._hidden = dict(hidden_state)  # entity_id -> bool
        self._too_few = set(too_few)
        self.toggled: list = []

    def is_connected(self):
        return True

    async def connect(self):
        pass

    async def __call__(self, request):
        cid = request.channel
        if isinstance(request, GetFullChannelRequest):
            return _t.SimpleNamespace(
                full_chat=_t.SimpleNamespace(participants_hidden=self._hidden[cid])
            )
        if isinstance(request, ToggleParticipantsHiddenRequest):
            if cid in self._too_few:
                raise ParticipantsTooFewError(request)
            self.toggled.append(cid)
            self._hidden[cid] = request.enabled
            return _t.SimpleNamespace()
        raise AssertionError(f"unexpected request {request!r}")


def _dialog(cid):
    return _t.SimpleNamespace(entity=cid, title=f"chat{cid}")


def test_apply_hide_members_toggles_only_visible(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a: "y")
    client = _FakeClient({-100: False, -200: True, -300: False}, too_few={-300})
    admin_of = [(_dialog(-100), None, False), (_dialog(-200), None, False),
                (_dialog(-300), None, False)]

    run(anonymize_groups.apply_hide_members(client, admin_of))

    assert client.toggled == [-100]  # -200 already hidden, -300 too few members


def test_apply_hide_members_declined(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a: "n")
    client = _FakeClient({-100: False})
    run(anonymize_groups.apply_hide_members(client, [(_dialog(-100), None, False)]))
    assert client.toggled == []


class _AnonFakeClient:
    def __init__(self, anon_state):
        self._anon = dict(anon_state)  # entity_id -> bool
        self.edited: list = []

    def is_connected(self):
        return True

    async def connect(self):
        pass

    async def __call__(self, request):
        cid = request.channel
        if isinstance(request, GetParticipantRequest):
            return _t.SimpleNamespace(
                participant=ChannelParticipantAdmin(
                    user_id=1, promoted_by=1, date=None,
                    admin_rights=ChatAdminRights(anonymous=self._anon.get(cid, False)),
                )
            )
        if isinstance(request, EditAdminRequest):
            self.edited.append(cid)
            self._anon[cid] = request.admin_rights.anonymous
            return _t.SimpleNamespace()
        raise AssertionError(f"unexpected request {request!r}")


def test_apply_anonymous_edits_only_non_anon(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a: "y")
    client = _AnonFakeClient({-100: False, -200: True})
    part = _t.SimpleNamespace(admin_rights=ChatAdminRights(change_info=True), rank="")
    admin_of = [(_dialog(-100), part, False), (_dialog(-200), part, True)]

    run(anonymize_groups.apply_anonymous(client, _t.SimpleNamespace(id=1), admin_of))

    assert client.edited == [-100]  # -200 was already anonymous
    assert client._anon[-100] is True  # verify pass re-read it as anonymous


def test_apply_anonymous_declined(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a: "n")
    client = _AnonFakeClient({-100: False})
    part = _t.SimpleNamespace(admin_rights=ChatAdminRights(), rank="")
    run(anonymize_groups.apply_anonymous(client, _t.SimpleNamespace(id=1),
                                         [(_dialog(-100), part, False)]))
    assert client.edited == []
