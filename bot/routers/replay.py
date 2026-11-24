"""⏪ Старые посты: telemirror.past for a project (``telemirror-past@<key>``) — copies
the history of the directions that have ``past_mode:``; the project's mirror
is paused meanwhile and comes back when it's over. 📜 Что копировать sets it
for every direction at once (a hand-written mix is shown as such). 🐢 Темп
«N постов за M минут» (``past_mode.drip``) hands the history to the live
mirror instead: it copies it at that pace, without stopping."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import configedit, configparse, registry, settings, status, texts
from bot.callbacks import ChoiceCB, NavCB
from bot.configstore import ConfigStore
from bot.routers import _units
from bot.keyboards.common import choice_kb
from bot.routers._common import ask, input_kind, message_of, on_action, project_of, stale_tap, start_form
from bot.runtime import Runtime
from bot.screens import open_screen, show, view
from bot.states import Input, leave_form
from bot.systemd import Systemd
from bot.texts import esc, head
from bot.writes import save
from telemirror.projects import Project

router = Router(name="replay")


def with_history(project: Project) -> int:
    return sum(1 for d in status.project_info(project).directions if d.get("past_mode"))


def delay_text(data) -> str:
    values = {settings.REPLAY_DELAY_DEFAULT if v is None else v for v in configedit.replay_delays(data)}
    if not values:
        return texts.UNKNOWN
    if len(values) > 1:
        return "разная"
    return f"{esc(values.pop())} с"


def pace_text(data) -> str:
    values = {configedit.pace_key(v) for v in configedit.replay_paces(data)}
    if not values:
        return texts.UNKNOWN
    if len(values) > 1:
        return "разный"
    return texts.pace_text(configedit.replay_paces(data)[0])


def drips(data) -> bool:
    """Every direction with a history copies it at a pace: the live mirror's."""
    paces = configedit.replay_paces(data)
    return bool(paces) and all(p is not None for p in paces)


def history_summary(data) -> str:
    """What the directions copy: one choice for all, or «разное»."""
    dirs = configedit.directions(data)
    if not dirs:
        return texts.UNKNOWN
    kinds = {str(configedit.history_of(d)) for d in dirs}
    if len(kinds) > 1:
        return f"разное (у {sum(1 for d in dirs if configedit.history_of(d))} из {len(dirs)} направлений)"
    return texts.history_text(dirs[0].get("past_mode"))


def _replay(project: Project) -> NavCB:
    return NavCB(s="rpl", p=project.key)


@view("rpl")
async def replay_view(message: Message, edit: bool, nav: NavCB, *, project: Project, sysd: Systemd,
                      note: str = "", **_) -> None:
    info = status.project_info(project)
    drip = drips(info.data)
    if drip:
        # A replay started all at once before 🐢 Темп was set: shown — and
        # stoppable — till it ends, not «ждёт запуска зеркала».
        past = await status.unit_state(sysd, project.past_unit)
        drip = not (past and past.running)
    unit = project.live_unit if drip else project.past_unit
    st = await status.unit_state(sysd, unit)
    running = bool(st and st.running)
    # The mirror runs an older config — a pace set since its start, or dropped
    # while it still drips (its run's journal says so): as 📁
    # Проект's «Изменения ещё не применены», with its 🔁 right here. Not for any
    # other change: ▶️ reads the config itself, the mirror resumes with it.
    live = st if drip else await status.unit_state(sysd, project.live_unit)
    pending = bool(info.snapshot and live and live.running and live.since and info.snapshot.mtime > live.since
                   and (drip or await _units.dripping(sysd, project.live_unit, live)))
    if drip:
        kind, pairs = await _units.drip_state(sysd, unit, st) if running else ("", "")
        if not running:
            state = "⏸ ждёт запуска зеркала"
        elif kind == "done":
            state = "✅ старые посты скопированы"
        elif kind == "stopped":
            state = "⚠️ остановилось с ошибкой — продолжит после перезапуска зеркала"
        elif kind == "idle" and pending:  # the pace came after the mirror's start: it doesn't drip
            state = "⏸ ждёт перезапуска зеркала"
        else:
            state = "🐢 копируется порциями вместе с зеркалом" + (f", готово пар каналов: {pairs}" if pairs else "")
        lines = [f"Состояние: <b>{state}</b>"]
    else:
        lines = [f"Состояние: <b>{_units.state_text(project, unit, st)}</b>"]
    if line := await _units.progress(sysd, unit, st):
        lines.append(line)
    if pending:
        lines.append(f"⚠️ <b>Изменения ещё не применены</b> — нажмите «{registry.title('rpl_restart')}».")
    if info.writable and info.directions and not with_history(project):
        lines.append(f"👉 Сначала выберите, какие посты копировать: «{registry.title('rpl_hist')}».")
    if not sysd.available:
        lines.append(texts.SYSTEMD_UNAVAILABLE)
    hidden: tuple = ("rpl_start",) if running else ("rpl_stop",)
    if drip:
        hidden = ("rpl_start", "rpl_stop", "rpl_delay")
    if not pending:
        hidden += ("rpl_restart",)
    if not info.writable:
        hidden += ("rpl_hist", "rpl_delay", "rpl_pace")
    elif not with_history(project):
        hidden += ("rpl_delay", "rpl_pace")
    titles = {"rpl_hist": f"{registry.title('rpl_hist')}: {history_summary(info.data)}",
              "rpl_delay": f"{registry.title('rpl_delay')}: {delay_text(info.data)}",
              "rpl_pace": f"{registry.title('rpl_pace')}: {pace_text(info.data)}"}
    if drip:
        more = ("Старые посты копирует само зеркало, не останавливаясь: по одному через равные промежутки, "
                "вперемешку с новыми. Уже скопированные пропускаются без ожидания; после перезапуска "
                "зеркала продолжится с того же места. Новый темп начнёт действовать после перезапуска зеркала.")
    else:
        more = ("Уже скопированные посты пропускаются; если прервать, в следующий раз продолжится с того же места. "
                "Пока идёт копирование истории, новые посты этого аккаунта не копируются — догонят после.")
    primary = ("rpl_restart" if pending else
               "rpl_start" if not running and not drip and info.writable and with_history(project) else "")
    await show(message, edit, "rpl", project, body="\n".join(lines), more=more, note=note, hidden=hidden,
               titles=titles, pg=nav.pg, primary=primary)


@on_action(router, "rpl_delay")
async def on_delay(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    if not with_history(project):
        await stale_tap(callback, texts.config_error("no_history"))
        return
    current = delay_text(status.project_info(project).data)
    await start_form(
        callback, state, Input.value,
        f"{head(registry.title('rpl_delay'))} — сейчас: {current}.\n\n"
        "Сколько секунд ждать между старыми постами, когда они копируются сразу, подряд.\n\n"
        "Пришлите число от 0 до 60, например <code>1.5</code>. Чем больше пауза, тем дольше идёт "
        "копирование, но тем реже Telegram ограничивает частую отправку. Обычно менять не нужно.\n\n"
        f"<code>-</code> — вернуть значение по умолчанию ({settings.REPLAY_DELAY_DEFAULT} с).\n\n"
        "<i>Выбор действует для всех направлений, где копируются старые посты.</i>",
        _replay(project), data={"kind": "rpl_delay", "p": project.key},
    )


@input_kind("rpl_delay")
async def set_delay(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                    store: ConfigStore, deps: dict, **_) -> None:
    delay = None if raw == configparse.CLEAR else configparse.parse_delay(raw)
    await leave_form(message.chat.id, state)
    await save(message, False, project,
               lambda p: store.update(p, lambda cfg: configedit.set_replay_delay(cfg, delay)),
               _replay(project), deps)


@on_action(router, "rpl_pace")
async def on_pace(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    if not with_history(project):
        await stale_tap(callback, texts.config_error("no_history"))
        return
    current = pace_text(status.project_info(project).data)
    await start_form(
        callback, state, Input.value,
        f"{head(registry.title('rpl_pace'))} — сейчас: {current}.\n\n"
        "Как выкладывать старые посты?\n\n"
        "🐢 <b>Порциями</b> — пришлите «сколько постов / за сколько минут», например <code>5/45</code>: "
        "5 постов за 45 минут, то есть один пост каждые 9 минут на весь проект: источники по кругу, "
        "по одному посту из каждого. Старые посты будут выходить равномерно, "
        "вперемешку с новыми, и зеркало не останавливается. Можно от 1 до 100 постов за 1–1440 минут "
        "(до суток). Или пришлите интервал в секундах, например <code>30с</code>: один пост каждые "
        "30 секунд. Начнётся после перезапуска зеркала.\n\n"
        f"⚡️ <b>Сразу</b> — пришлите <code>-</code>: после «{registry.title('rpl_start')}» все старые посты "
        "скопируются подряд, а новые на это время подождут (зеркало приостанавливается).\n\n"
        "<i>Выбор действует для всех направлений, где копируются старые посты.</i>",
        _replay(project), data={"kind": "rpl_pace", "p": project.key},
    )


@input_kind("rpl_pace")
async def set_pace(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                   store: ConfigStore, deps: dict, **_) -> None:
    pace = None if raw == configparse.CLEAR else configparse.parse_pace(raw)
    await leave_form(message.chat.id, state)
    await save(message, False, project,
               lambda p: store.update(p, lambda cfg: configedit.set_replay_pace(cfg, pace)),
               _replay(project), deps)


@on_action(router, "rpl_restart")
async def on_restart(callback: CallbackQuery, project: Project, state: FSMContext, sysd: Systemd) -> None:
    await _units.ask_stop(callback, state, sysd, project, project.live_unit, True, _replay(project))


@on_action(router, "rpl_start")
async def on_start(callback: CallbackQuery, project: Project, state: FSMContext, sysd: Systemd,
                   runtime: Runtime, deps: dict) -> None:
    unit = project.past_unit
    if not await _units.can_start(callback, sysd, runtime, project, unit):
        return
    if not with_history(project):
        await stale_tap(callback, texts.config_error("no_history"))
        return
    if drips(status.project_info(project).data):  # a pace set since: the mirror copies it
        await stale_tap(callback)
        return
    question = (f"{head(registry.title('rpl_start'))} копирование истории?\n\nСкопируются старые посты "
                f"направлений, где это выбрано. Ход виден здесь и в {registry.TASKS}.")
    if await _units.ask_start(callback, state, sysd, project, unit, question, _replay(project)) \
            and await _units.launch(callback, sysd, runtime, project, unit):
        await open_screen(_replay(project), message_of(callback), True, deps, note=_units.STARTING)


@on_action(router, "rpl_stop")
async def on_stop(callback: CallbackQuery, project: Project, state: FSMContext, sysd: Systemd) -> None:
    await _units.ask_stop(callback, state, sysd, project, project.past_unit, False, _replay(project))


# ── 📜 Что копировать: one choice for every direction ──────────────────────

HISTORY = [(registry.TITLES[k], k) for k in ("hist_none", "hist_full", "hist_last", "hist_since")]


@on_action(router, "rpl_hist")
async def on_history(callback: CallbackQuery, project: Project, state: FSMContext) -> None:
    info = status.project_info(project)
    if not info.directions:
        await stale_tap(callback, texts.config_error("no_directions"))
        return
    await start_form(
        callback, state, Input.value,
        f"{head(registry.title('rpl_hist'))} — сейчас: {history_summary(info.data)}.\n\n"
        "Какие посты, вышедшие в источниках раньше, скопировать в ваши каналы?\n\n"
        f"{head(registry.TITLES['hist_none'])} — старые посты не копировать\n"
        f"{head(registry.TITLES['hist_full'])} — всё, что есть в источнике\n"
        f"{head(registry.TITLES['hist_last'])} — заданное число последних постов каждого источника\n"
        f"{head(registry.TITLES['hist_since'])} — всё, начиная с выбранного дня\n\n"
        "Новые посты копируются в любом случае.\n"
        f"<i>Выбор действует для всех направлений проекта (их {len(info.directions)}).</i>",
        _replay(project), markup=choice_kb("rpl_hist", HISTORY, widths=(2,)),
        data={"kind": "rpl_hist", "p": project.key}, choice=True,
    )


async def _set_history(message: Message, edit: bool, state: FSMContext, project: Project, value,
                       store: ConfigStore, deps: dict) -> None:
    await leave_form(message.chat.id, state)
    await save(message, edit, project, lambda p: store.update(p, lambda cfg: configedit.set_history(cfg, value)),
               _replay(project), deps)


@router.callback_query(Input.value, ChoiceCB.filter(F.scope == "rpl_hist"))
async def on_history_pick(callback: CallbackQuery, callback_data: ChoiceCB, state: FSMContext,
                          store: ConfigStore, deps: dict) -> None:
    data = await state.get_data()
    if data.get("kind") != "rpl_hist" or callback_data.value not in {k for _, k in HISTORY}:
        await stale_tap(callback)
        return
    if (project := await project_of(callback, data["p"])) is None:
        return
    await callback.answer()
    if callback_data.value in ("hist_last", "hist_since"):
        kind = "rpl_last" if callback_data.value == "hist_last" else "rpl_since"
        ask_text = ("сколько последних постов?\n\nПришлите целое число от 1 до 1 000 000, например "
                    "<code>100</code>: из каждого источника скопируются его последние 100 постов."
                    if kind == "rpl_last" else
                    "с какого дня?\n\nПришлите дату, например <code>31.01.2024</code>: скопируются посты, "
                    "вышедшие начиная с этого дня. Можно указать и время: <code>31.01.2024 12:00</code>.\n\n"
                    "<i>Время — московское.</i>")
        await message_of(callback).edit_reply_markup(reply_markup=None)
        await ask(message_of(callback), state, Input.value, f"{head(registry.title('rpl_hist'))} — {ask_text}",
                  kind=kind)
        return
    value = None if callback_data.value == "hist_none" else {"full_history": True}
    await _set_history(message_of(callback), True, state, project, value, store, deps)


@input_kind("rpl_hist")
async def history_typed(message: Message, **_) -> None:
    await message.answer(texts.USE_BUTTONS)


@input_kind("rpl_last")
@input_kind("rpl_since")
async def set_history(message: Message, state: FSMContext, raw: str, data: dict, project: Project,
                      store: ConfigStore, deps: dict, **_) -> None:
    value = ({"last_n": configparse.parse_last_n(raw)} if data["kind"] == "rpl_last"
             else {"since_date": configparse.parse_since(raw)})
    await _set_history(message, False, state, project, value, store, deps)
