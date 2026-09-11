"""L1: DB DSN must percent-encode credentials so a password with @ : / # ?
can't corrupt or redirect the connection URL."""

from urllib.parse import unquote, urlsplit

from config import build_dsn


def test_special_chars_encoded():
    dsn = build_dsn("us:er", "p@ss/w#rd?x", "db.internal", "telemirror")
    parts = urlsplit(dsn)
    assert parts.scheme == "postgres"
    assert parts.hostname == "db.internal"      # not hijacked by @ in the password
    assert parts.path == "/telemirror"
    assert parts.port is None                   # not truncated by : in the password
    assert unquote(parts.username) == "us:er"
    assert unquote(parts.password) == "p@ss/w#rd?x"


def test_plain_credentials_roundtrip():
    dsn = build_dsn("postgres", "secret", "localhost", "tm")
    assert dsn == "postgres://postgres:secret@localhost/tm"
