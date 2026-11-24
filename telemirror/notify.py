"""Notices to the control panel's admins through its bot (``PANEL_BOT_TOKEN`` →
``PANEL_ADMIN_IDS``): whatever a mirror, a replay or a one-off alert has to say
about itself (its warnings and errors, a private message to its account, a
post a replay had to skip) goes there — there's no tech channel.

Best effort: a notice never raises and never logs at WARNING or above (the
mirror's log handler would send that one too). A notice from a project's
process is signed with the project and carries the panel's 📊 Статус и журнал button."""

import json
import logging
import urllib.request
from typing import Iterable, Optional

import aiohttp
from decouple import config as _env

from telemirror.projects import ProjectError, load_project

logger = logging.getLogger("telemirror.notify")

SEND_TIMEOUT = 20
MAX_TEXT = 4096
UNIT_KINDS = ("live", "past", "task")  # Project.units order: the panel's NavCB(s="unit", i=…)
BUTTON = "📊 Статус и журнал"  # bot.registry.TITLES["notice"]
RETRY_ALL = "♻️ Повторить все"  # bot.registry: the fail_all button
FAILED_SCREEN = "❗ Не скопировано"  # bot.registry.SCREENS["fail"].title


def parse_admins(raw: str) -> list:
    """``PANEL_ADMIN_IDS``: comma/semicolon-separated ids; a bad item is skipped."""
    out = []
    for item in raw.replace(";", ",").split(","):
        if item.strip().lstrip("-").isdigit():
            out.append(int(item.strip()))
    return out


def project_label(key: str) -> str:
    """«🪞 Зеркало» for a project's key; the key itself if it can't be read."""
    try:
        project = load_project(key)
    except ProjectError:
        return key
    return f"{project.icon} {project.name}"


def unit_button(key: str, kind: str) -> dict:
    """The panel's 📊 Статус и журнал screen of the project's unit — its ``NavCB`` packed
    by hand (this side doesn't import the bot; a test keeps them equal)."""
    return {"inline_keyboard": [[{"text": BUTTON,
                                  "callback_data": f"n:unit:{key}:{UNIT_KINDS.index(kind)}:0"}]]}


def failed_buttons(key: str) -> dict:
    """A not-copied-posts notice's buttons: ♻️ Повторить все (``ActCB(a="fail_all")``)
    and the panel's ❗ Не скопировано screen (``NavCB(s="fail")``), packed by hand
    like ``unit_button``."""
    return {"inline_keyboard": [[{"text": RETRY_ALL, "callback_data": f"a:fail_all:{key}:-1:0:"},
                                  {"text": FAILED_SCREEN, "callback_data": f"n:fail:{key}:-1:0"}]]}


def cut(text: str, limit: int = MAX_TEXT) -> str:
    """At most ``limit`` UTF-16 code units — Telegram's unit: an emoji outside
    the BMP (🪞, 📊…) is two, so a codepoint slice could still be too long."""
    units = 0
    for i, ch in enumerate(text):
        units += 2 if ord(ch) > 0xFFFF else 1
        if units > limit:
            return text[:i]
    return text


def _payload(chat_id: int, text: str, markup: Optional[dict]) -> dict:
    body = {"chat_id": chat_id, "text": cut(text), "disable_web_page_preview": True}
    if markup:
        body["reply_markup"] = markup
    return body


def _url(token: str) -> str:
    return f"https://api.telegram.org/bot{token}/sendMessage"


class BotNotifier:
    """Sends plain-text notices (never parsed as markup: log lines and names
    come from outside) to every admin, signed with ``label``."""

    def __init__(self, token: str, admins: Iterable[int], label: str = "",
                 markup: Optional[dict] = None) -> None:
        self._token = token
        self._admins = list(admins)
        self._label = label
        self._markup = markup

    @classmethod
    def from_env(cls, project_key: Optional[str] = None, kind: str = "live") -> Optional["BotNotifier"]:
        """From ``.env``; None when the panel's bot isn't set up (nobody to tell)."""
        token = _env("PANEL_BOT_TOKEN", default="")
        admins = parse_admins(_env("PANEL_ADMIN_IDS", default=""))
        if not token or not admins:
            return None
        if not project_key:
            return cls(token, admins)
        return cls(token, admins, project_label(project_key), unit_button(project_key, kind))

    def text(self, body: str) -> str:
        return f"{self._label}: {body}" if self._label else body

    async def send(self, body: str, markup: Optional[dict] = None) -> bool:
        """True if at least one admin got it. ``markup`` replaces the notifier's own buttons."""
        delivered = False
        timeout = aiohttp.ClientTimeout(total=SEND_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for admin in self._admins:
                    try:
                        payload = _payload(admin, self.text(body), markup or self._markup)
                        async with session.post(_url(self._token), json=payload) as response:
                            delivered |= bool((await response.json(content_type=None)).get("ok"))
                    except Exception as e:  # noqa: BLE001 - try the other admins
                        logger.info("notice to %s not sent: %s", admin, e)
        except Exception as e:  # noqa: BLE001 - a notice never breaks its caller
            logger.info("notice not sent: %s", e)
        return delivered

    def send_sync(self, body: str, markup: Optional[dict] = None) -> bool:
        """The same without an event loop (a one-shot process: ``telemirror.alert``)."""
        delivered = False
        for admin in self._admins:
            request = urllib.request.Request(
                _url(self._token), data=json.dumps(_payload(admin, self.text(body), markup or self._markup)).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=SEND_TIMEOUT) as response:
                    delivered |= bool(json.load(response).get("ok"))
            except Exception as e:  # noqa: BLE001 - try the other admins
                logger.warning("bot send to %s failed: %s", admin, e)
        return delivered
