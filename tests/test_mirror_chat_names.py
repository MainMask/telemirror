"""The mirror writes its chats' titles for the panel (projects/<key>/chats.json)
at start — and keeps running when it can't."""

import logging
from datetime import datetime
from types import SimpleNamespace

from telethon.tl.types import Channel, ChatPhotoEmpty

from telemirror import projects
from telemirror.mirroring import Mirroring
from telemirror.storage import InMemoryDatabase
from tests.conftest import run


def _channel(cid: int, title: str) -> Channel:
    return Channel(id=cid, title=title, photo=ChatPhotoEmpty(), date=datetime.now(), access_hash=1)


class Client:
    def __init__(self, dialogs=None, error=None):
        self.dialogs, self.error = dialogs or [], error

    async def get_dialogs(self):
        if self.error:
            raise self.error
        return [SimpleNamespace(entity=e) for e in self.dialogs]


def _mirroring(key: str) -> Mirroring:
    return Mirroring(
        chat_mapping={-1001111111111: {-1002222222222: []}},
        database=run(InMemoryDatabase()),
        client=object(),
        logger=logging.getLogger("test"),
        broadcast_channel=-1003333333333,
        chat_names_key=key,
    )


def test_the_configured_chats_titles_are_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    (tmp_path / "p").mkdir()
    client = Client([_channel(1111111111, "Источник"), _channel(2222222222, "Зеркало"),
                     _channel(3333333333, "Рассылка"), _channel(4444444444, "Чужой")])
    run(_mirroring("p")._save_chat_names(client))
    assert projects.load_chat_names("p") == {
        -1001111111111: "Источник", -1002222222222: "Зеркало", -1003333333333: "Рассылка"}


def test_a_failure_is_only_a_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    (tmp_path / "p").mkdir()
    run(_mirroring("p")._save_chat_names(Client(error=ConnectionError("down"))))
    assert projects.load_chat_names("p") == {}
    assert "Could not save chat titles" in caplog.text
