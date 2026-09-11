"""``restrict_saving`` must toggle ``noforwards`` only on recipients that don't
already have it, and do nothing under ``--dry-run``.
"""

import logging
import types as _t
from contextlib import asynccontextmanager

import pytest

from config import DirectionConfig
from skylon_set import restrict_saving
from telemirror.messagefilters import EmptyMessageFilter
from tests.conftest import run


def _cfg(topic=None):
    return DirectionConfig(
        disable_delete=False,
        disable_edit=False,
        filters=EmptyMessageFilter(),
        to_topic_id=topic,
    )


def test_collect_recipient_ids_dedups():
    src1, src2 = -1001, -1002
    recip_a, recip_b = -9001, -9002
    mapping = {
        src1: {recip_a: [_cfg(topic=3)], recip_b: [_cfg()]},
        src2: {recip_a: [_cfg(topic=5)]},  # same recipient, another donor
    }
    assert restrict_saving.collect_recipient_ids(mapping) == {recip_a, recip_b}


def test_course_recipient_ids_reads_to_targets(tmp_path):
    cfg = tmp_path / "courses.yml"
    cfg.write_text(
        "directions:\n"
        "- from: ['-100111#1']\n"
        "  to: ['-100222#5']\n"
        "- from: ['-100111#2']\n"
        "  to: ['-100222#6']\n"       # same recipient, another topic
        "- from: ['-100333']\n"
        "  to: ['-100444']\n",
        encoding="utf-8",
    )
    assert restrict_saving.course_recipient_ids(cfg) == {-100222, -100444}


def test_course_recipient_ids_missing_file(tmp_path):
    assert restrict_saving.course_recipient_ids(tmp_path / "nope.yml") == set()


class _FakeClient:
    def __init__(self, entities):
        self._entities = {e.id: e for e in entities}  # id -> entity
        self.toggled: list = []

    def is_connected(self):
        return True

    async def connect(self):
        pass

    async def get_entity(self, ref):
        key = ref.id if hasattr(ref, "id") else ref
        return self._entities[key]

    async def __call__(self, request):
        peer = request.peer
        key = peer.id if hasattr(peer, "id") else peer
        self.toggled.append(key)
        self._entities[key].noforwards = request.enabled
        return _t.SimpleNamespace()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import skylon_set._common as common

    async def _noop(*_a, **_kw):
        pass

    monkeypatch.setattr(common.asyncio, "sleep", _noop)


def _patch_client(monkeypatch, client):
    @asynccontextmanager
    async def _fake_open_client(logger, **kwargs):
        yield client, _t.SimpleNamespace(id=1)

    monkeypatch.setattr(restrict_saving, "open_client", _fake_open_client)
    monkeypatch.setattr(
        restrict_saving, "CHAT_MAPPING", {-1: {e.id: [_cfg()] for e in client._entities.values()}}
    )
    monkeypatch.setattr(restrict_saving, "course_recipient_ids", lambda *_a: set())


def _entity(cid, restricted):
    return _t.SimpleNamespace(id=cid, title=f"chat{cid}", noforwards=restricted)


def test_run_toggles_only_unrestricted(monkeypatch):
    entities = [_entity(-100, False), _entity(-200, True), _entity(-300, False)]
    client = _FakeClient(entities)
    _patch_client(monkeypatch, client)
    monkeypatch.setattr("builtins.input", lambda *_a: "y")

    run(restrict_saving._run(logging.getLogger("t"), dry_run=False))

    assert set(client.toggled) == {-100, -300}  # -200 was already restricted


def test_run_dry_run_makes_no_calls(monkeypatch):
    entities = [_entity(-100, False), _entity(-200, False)]
    client = _FakeClient(entities)
    _patch_client(monkeypatch, client)

    def _no_input(*_a):
        raise AssertionError("dry-run must not prompt")

    monkeypatch.setattr("builtins.input", _no_input)

    run(restrict_saving._run(logging.getLogger("t"), dry_run=True))

    assert client.toggled == []
