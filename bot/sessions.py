"""The Telegram sessions the mirrors run on (``sessions/*.jsession``): the
list, who they are, which projects use them, and the account picker of the
forms that choose one (➕ Новый проект, 👤 Аккаунт)."""

import os
from pathlib import Path

from bot.keyboards.common import choice_kb
from bot.registry import ROW_ACCOUNT, title
from telemirror import projects
from telemirror.misc.jsession import load_jsession


def session_files() -> list:
    """``sessions/*.jsession`` as repo-relative paths, sorted."""
    folder = projects.SESSIONS_DIR
    files = sorted(folder.glob("*.jsession")) if folder.is_dir() else []
    return [os.path.relpath(f, projects.REPO_DIR) for f in files]


def account_of(path: str) -> dict:
    try:
        return load_jsession(str(projects.REPO_DIR / path)).get("account") or {}
    except (OSError, ValueError):
        return {}


def account_label(path: str) -> str:
    """``+79131332002 · @name`` (the file name if it has no account data)."""
    acc = account_of(path)
    phone = f"+{acc['phone_number']}" if acc.get("phone_number") else Path(path).stem
    return f"{phone} · @{acc['username']}" if acc.get("username") else phone


def users_of(path: str) -> list:
    """The projects on this session."""
    mine = (projects.REPO_DIR / path).resolve()
    return [p for p in projects.list_projects() if p.session_path.resolve() == mine]


def picker(paths: list):
    """An account picker: the sessions by index, then a new one (🔑 / 📤) —
    answered by ``routers.accounts.on_pick``."""
    return choice_kb("acc_pick", [
        *((f"{ROW_ACCOUNT} {account_label(p)}", str(n)) for n, p in enumerate(paths)),
        (title("acc_login"), "login"),
        (title("acc_upload"), "upload"),
    ])
