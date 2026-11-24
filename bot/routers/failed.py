"""❗ Не скопировано: the posts a project's mirror couldn't copy
(``telemirror.failed``) — copy one or all again, or forget them. The panel
only asks (a request file); the mirror does it within ``Mirroring.SINK_TICK_SEC``."""

from typing import Optional

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot import settings, status, texts
from bot.callbacks import ActCB, NavCB
from bot.keyboards.common import button, paged_rows, pages
from bot.registry import title
from bot.routers._common import message_of, on_action, stale_tap, with_project
from bot.screens import open_screen, show, view
from bot.systemd import Systemd
from bot.texts import esc
from telemirror import failed
from telemirror.outcomes import ALL_CHATS
from telemirror.projects import Project, load_chat_names

router = Router(name="failed")

ROW = "♻️"  # a row copies its post again — the emoji of ♻️ Повторить все


def _target_text(target: dict, names) -> str:
    return "все каналы" if target["chat"] == ALL_CHATS else texts.chat(target["chat"], names)


def _target_plain(target: dict, names) -> str:
    return "все каналы" if target["chat"] == ALL_CHATS else texts.chat_plain(target["chat"], names)


async def _running(sysd: Systemd, project: Project) -> Optional[bool]:
    st = await status.unit_state(sysd, project.live_unit) if sysd.available else None
    return None if st is None else st.running


def _when(running: Optional[bool]) -> str:
    if running:
        return "Зеркало сделает это в течение минуты — нажмите 🔄 Обновить."
    if running is None:
        return "Зеркало сделает это в течение минуты, если оно запущено."
    return "Зеркало сейчас остановлено: сделает это, когда его запустят."


@view("fail")
async def failed_view(message: Message, edit: bool, nav: NavCB, *, project: Project, sysd: Systemd,
                      note: str = "", **_) -> None:
    entries = list(reversed(failed.load(project.key)))  # the newest first
    names = load_chat_names(project.key)
    if not entries:
        await show(message, edit, "fail", project, body="Список пуст: все посты скопированы.", note=note,
                   hidden=("fail_all", "fail_clear"), pg=nav.pg)
        return
    page = nav.pg % pages(len(entries), settings.PAGE_SIZE)
    shown = entries[page * settings.PAGE_SIZE:(page + 1) * settings.PAGE_SIZE]
    lines = [f"Ждут повтора: <b>{len(entries)}</b>"]
    items = []
    for n, e in enumerate(entries):
        first = e["targets"][0] if e["targets"] else {"chat": ALL_CHATS}
        label = f"{ROW} {texts.fmt_ts(e['at'])} · {texts.chat_plain(e['chat'], names)} → {_target_plain(first, names)}"
        items.append(button(texts.cut(label, 60), ActCB(a="fail_one", p=project.key, i=n, pg=page, h=e["id"])))
    for e in shown:
        where = "; ".join(f"{_target_text(t, names)}: {esc(t['reason'])}" for t in e["targets"][:5])
        more_targets = f" и ещё {len(e['targets']) - 5}" if len(e["targets"]) > 5 else ""
        lines.append(f"{texts.fmt_ts(e['at'])} · {texts.chat(e['chat'], names)} · {esc(e['link'])}\n"
                     f"→ {where}{more_targets}")
    if await _running(sysd, project) is False:
        lines.append("Зеркало сейчас остановлено: повторить получится, когда его запустят.")
    more = ("Пост копируется заново только в те каналы, куда он не дошёл. Если в источнике его уже удалили, "
            "он просто пропадёт из списка. Список хранит последние 300 постов за 14 дней.")
    own = paged_rows(items, page, settings.PAGE_SIZE, lambda pg: NavCB(s="fail", p=project.key, pg=pg))
    await show(message, edit, "fail", project, body="\n\n".join(lines), more=more, note=note, own=own,
               own_hints=[(ROW, "скопировать заново один пост")], pg=page, primary="fail_all")


@on_action(router, "fail_all", "fail_clear")
async def on_bulk(callback: CallbackQuery, callback_data: ActCB, project: Project, sysd: Systemd,
                  deps: dict) -> None:
    """Also the not-copied-posts notice's ♻️ Повторить все (telemirror.notify.failed_buttons)."""
    copy = callback_data.a == "fail_all"
    failed.request(project.key, failed.ALL if copy else failed.CLEAR)
    await callback.answer()
    note = f"{title(callback_data.a)}: {'принято' if copy else 'список будет очищен'}. " + _when(
        await _running(sysd, project))
    await open_screen(NavCB(s="fail", p=project.key), message_of(callback), True, deps, note=note)


@router.callback_query(ActCB.filter(F.a == "fail_one"))
@with_project(ActCB)
async def on_one(callback: CallbackQuery, callback_data: ActCB, project: Project, sysd: Systemd,
                 deps: dict) -> None:
    if not any(e["id"] == callback_data.h for e in failed.load(project.key)):
        await stale_tap(callback)
        return
    failed.request(project.key, callback_data.h)
    await callback.answer()
    note = f"{ROW} Пост будет скопирован заново. " + _when(await _running(sysd, project))
    await open_screen(NavCB(s="fail", p=project.key, pg=callback_data.pg), message_of(callback), True, deps,
                      note=note)
