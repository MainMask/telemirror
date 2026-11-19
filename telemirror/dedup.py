"""A post's fingerprint for ``dedup_hours`` (🧬 Без повторов): the same post
from another source — the same text and the same photos/videos — isn't sent
to a channel that already got it.

    text + media → both must match (a recurring caption under new photos isn't a repeat)
    text only    → the text, from MIN_TEXT characters (short ones repeat by chance)
    media only   → the photos/videos (a re-upload is another file: not caught)

Case and whitespace don't count."""

import hashlib
from typing import Iterable, Optional

from telemirror.hints import EventMessage
from telemirror.messagefilters import source_media_id

MIN_TEXT = 20


def fingerprint(messages: Iterable[EventMessage]) -> Optional[str]:
    """None: nothing to tell it by — never a repeat."""
    messages = list(messages)
    text = " ".join(" ".join((m.message or "").lower().split()) for m in messages).strip()
    media = sorted(mid for m in messages if (mid := source_media_id(m.media)) is not None)
    if media:
        key = f"m:{','.join(map(str, media))}|t:{text}"
    elif len(text) >= MIN_TEXT:
        key = f"t:{text}"
    else:
        return None
    return hashlib.sha1(key.encode()).hexdigest()
