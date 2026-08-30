from telethon import utils


def private_message_link(channel_id: int, message_id: int) -> str:
    """Build a ``https://t.me/c/<peer>/<id>`` link from a ``-100…`` channel id."""
    return f"https://t.me/c/{utils.resolve_id(channel_id)[0]}/{message_id}"
