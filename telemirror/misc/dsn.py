"""The Postgres connection URL from ``DB_*`` credentials — shared by
``telemirror.config`` and ``telemirror.selfcheck`` (which must not import the
whole config)."""

from typing import Optional
from urllib.parse import quote

DB_PROTOCOL: str = "postgres"


def build_dsn(user: Optional[str], password: Optional[str], host: str, name: Optional[str]) -> str:
    """Assemble a libpq connection URL, percent-encoding the credentials so a
    password containing ``@ : / # ?`` doesn't corrupt/redirect the DSN."""
    return (
        f"{DB_PROTOCOL}://{quote(user or '', safe='')}:"
        f"{quote(password or '', safe='')}@{host}/{name}"
    )
