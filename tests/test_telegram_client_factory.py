"""Phase 4 DRY cleanup: mirroring.py's Telemirror and past_mode.py's _run built
almost identical TelegramClient instances (differing only in connection_retries/
retry_delay) — build_telegram_client is the shared factory both now call."""

from telethon.extensions import markdown as md_parser

from telemirror.misc.telegram_client import build_telegram_client


def test_sets_markdown_parse_mode():
    client = build_telegram_client(
        "", 12345, "api_hash", connection_retries=5, retry_delay=1
    )
    # `client.parse_mode = "markdown"` resolves to Telethon's markdown parser
    # module internally — that resolution *is* the observable effect.
    assert client.parse_mode is md_parser


def test_forwards_flood_sleep_threshold_and_retry_policy():
    client = build_telegram_client(
        "", 12345, "api_hash", connection_retries=1000, retry_delay=5
    )
    assert client.flood_sleep_threshold == 300
    assert client._connection_retries == 1000
    assert client._retry_delay == 5


def test_different_callers_can_use_different_retry_policies():
    live = build_telegram_client(
        "", 12345, "hash", connection_retries=1000, retry_delay=5
    )
    operator_script = build_telegram_client(
        "", 12345, "hash", connection_retries=20, retry_delay=3
    )
    assert live._connection_retries == 1000
    assert operator_script._connection_retries == 20
