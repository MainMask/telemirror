import re
from typing import Optional, Set, Type, Union
from urllib.parse import parse_qsl, urlencode

from telethon import events, types, utils

from ..hints import EventAlbumMessage, EventEntity, EventLike, EventMessage
from ..misc.urlmatcher import UrlMatcher
from ..mixins import (
    ChannelName,
    MappedChannelName,
    MessageLink,
    UpdateEntitiesParams,
)
from .base import FilterAction, FilterResult, MessageFilter


def _compile_keyword(keyword: str) -> re.Pattern[str]:
    """Compile one keyword rule: ``r'...'`` is a raw regex, anything else is a
    whole-word literal match — no letter or digit right before or after it.
    (Not a regex word boundary: it needs a word character on one side, so a
    keyword like ``@name`` never matched after a space or at the start.) Raises ``ValueError`` (not a bare
    ``re.error``) on a broken pattern so config mistakes fail fast with context."""
    if keyword.startswith("r'"):
        src = keyword.removeprefix("r'").removesuffix("'")
    else:
        src = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    if not src or src == r"(?<!\w)(?!\w)":
        # matches between any two non-letters: an erratic rule, not a keyword
        raise ValueError(f"empty keyword {keyword!r}")
    try:
        return re.compile(src, flags=re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"invalid keyword pattern {keyword!r}: {e}") from e


def _utf16_len(text: str) -> int:
    """Length in UTF-16 code units — Telegram's entity offsets count them."""
    return len(text) + sum(1 for ch in text if ord(ch) > 0xFFFF)


class EmptyMessageFilter(MessageFilter):
    """Do nothing with message"""

    async def process(
        self, entity: EventEntity, event_type: Type[EventLike]
    ) -> FilterResult[EventEntity]:
        return FilterResult(FilterAction.CONTINUE, entity)

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        raise NotImplementedError


class SkipAllFilter(MessageFilter):
    """Skips all messages"""

    async def process(
        self, entity: EventEntity, event_type: Type[EventLike]
    ) -> FilterResult[EventEntity]:
        return FilterResult(FilterAction.DISCARD, entity)

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        raise NotImplementedError


class SkipUrlFilter(MessageFilter):
    """Skip messages with URLs

    Args:
        skip_mention (`bool`, optional):
            Enable skipping text mentions (@channel). Defaults to True.
    """

    def __init__(self: "SkipUrlFilter", skip_mention: bool = True) -> None:
        self._skip_mention = skip_mention

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        if isinstance(message.media, types.MessageMediaWebPage):
            return FilterResult(FilterAction.DISCARD, message)

        for entity in message.entities or []:
            if isinstance(
                entity, (types.MessageEntityUrl, types.MessageEntityTextUrl)
            ) or (
                isinstance(
                    entity, (types.MessageEntityMention, types.MessageEntityMentionName)
                )
                and self._skip_mention
            ):
                return FilterResult(FilterAction.DISCARD, message)

        return FilterResult(FilterAction.CONTINUE, message)


class UrlMessageFilter(UpdateEntitiesParams, MessageFilter):
    """URLs message filter

    Args:
        placeholder (`str`, optional):
            URLs and mentions placeholder. Defaults to '***'.

        blacklist (`Set[str]`, optional):
            URLs blacklist -- remove only these URLs.
            Defaults to empty set (removes all URLs).

        whitelist (`Set[str]`, optional):
            URLs whitelist -- remove all URLs except these.
            Will be applied after the `blacklist`. Defaults to empty set.

        filter_mention (`Union[bool, Set[str]]`, optional):
            Filter text mentions (e.g. @channel, @nickname).
            Defaults to False.

        filter_by_id_mention (`bool`, optional):
            Filter all mentions without nicknames (by user id).
            Defaults to False.
    """

    def __init__(
        self: "UrlMessageFilter",
        placeholder: str = "***",
        blacklist: Optional[Set[str]] = None,
        whitelist: Optional[Set[str]] = None,
        filter_mention: Union[bool, Set[str]] = False,
        filter_by_id_mention: bool = False,
    ) -> None:
        self._placeholder = utils.add_surrogate(placeholder)
        self._placeholder_len = len(self._placeholder)

        self._url_matcher = UrlMatcher(blacklist or set(), whitelist or set())

        self._filter_mention = None
        self._mention_blacklist = None
        if isinstance(filter_mention, bool):
            self._filter_mention = filter_mention
        else:
            self._mention_blacklist = filter_mention

        self._filter_by_id_mention = filter_by_id_mention

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        filtered_text = utils.add_surrogate(message.message or "")
        filtered_entities = list[types.TypeMessageEntity]()

        for entity in message.entities or []:
            drop_entity = False
            update_pos = False

            entity_text = filtered_text[entity.offset : entity.offset + entity.length]
            if (
                isinstance(entity, types.MessageEntityUrl)
                and self._url_matcher.match(entity_text)
            ) or (
                isinstance(entity, types.MessageEntityMention)
                and self._match_mention(entity_text)
            ) or (
                isinstance(entity, types.MessageEntityTextUrl)
                and self._mention_blacklist is not None
                and self._match_mention(entity_text)
            ):
                filtered_text = (
                    filtered_text[: entity.offset]
                    + self._placeholder
                    + filtered_text[entity.offset + entity.length :]
                )
                entity_len_diff = self._placeholder_len - entity.length
                update_pos = True
                drop_entity = True
            elif (
                self._filter_by_id_mention
                and isinstance(entity, types.MessageEntityMentionName)
            ) or (
                isinstance(entity, types.MessageEntityTextUrl)
                and self._url_matcher.match(entity.url)
            ):
                drop_entity = True

            if update_pos is True:
                self.update_entities_params(
                    message.entities,
                    entity.offset,
                    entity.offset + entity.length,
                    entity_len_diff,
                )

            if drop_entity is False:
                filtered_entities.append(entity)

        # Double check for URLs in text
        offset_error = 0
        for start, end in self._url_matcher.search(filtered_text):
            actual_start = start + offset_error
            actual_end = end + offset_error

            filtered_text = (
                filtered_text[:actual_start]
                + self._placeholder
                + filtered_text[actual_end:]
            )

            diff = self._placeholder_len - (end - start)
            offset_error += diff

            self.update_entities_params(
                filtered_entities, actual_start, actual_end, diff
            )

        # Filter link preview
        if (
            isinstance(message.media, types.MessageMediaWebPage)
            and isinstance(message.media.webpage, types.WebPage)
            and self._url_matcher.match(message.media.webpage.url)
        ):
            message.media = None

        message.entities = filtered_entities
        message.message = utils.del_surrogate(filtered_text)

        return FilterResult(FilterAction.CONTINUE, message)

    def _match_mention(self, mention: str) -> bool:
        if self._filter_mention is not None:
            return self._filter_mention

        if self._mention_blacklist and mention not in self._mention_blacklist:
            return False

        return True


class ForwardFormatFilter(ChannelName, MessageLink, UpdateEntitiesParams, MessageFilter):
    """Filter that adds a forwarding formatting (markdown supported):

    Example:
    ```
    {message_text}

    Forwarded from [{channel_name}]({message_link})
    ```

    Args:
        format (str): Forward header format,
        where `{channel_name}`, `{message_link}`, `{sender_title}`, `{sender_username}`
        and `{message_text}` are placeholders to actual incoming message values.
    """

    MESSAGE_PLACEHOLDER: str = "{message_text}"
    CHANNEL_NAME_PLACEHOLDER: str = "{channel_name}"
    MESSAGE_LINK_PLACEHOLDER: str = "{message_link}"
    SENDER_TITLE_PLACEHOLDER: str = "{sender_title}"
    SENDER_USERNAME_PLACEHOLDER: str = "{sender_username}"

    DEFAULT_FORMAT: str = (
        "{message_text}\n\nForwarded from [{channel_name}]({message_link})"
    )

    def __init__(self, format: str = DEFAULT_FORMAT) -> None:
        self._format = format

        if self.MESSAGE_PLACEHOLDER not in format:
            # Without it `_process_message` finds offset -1, drops the original
            # body and shifts header entities by a bogus diff.
            raise ValueError(
                f"ForwardFormatFilter: format must contain "
                f"{self.MESSAGE_PLACEHOLDER}: {format!r}"
            )

        try:
            probe = self._format.format(
                channel_name="", message_link="", sender_title="",
                sender_username="", message_text=self.MESSAGE_PLACEHOLDER,
            )
            probe.format(message_text="")
        except (KeyError, IndexError, ValueError) as e:
            raise ValueError(
                f"ForwardFormatFilter: invalid format string {self._format!r}: {e}"
            ) from e

        self._request_channel_name = (
            ForwardFormatFilter.CHANNEL_NAME_PLACEHOLDER in format
        )
        self._request_message_link = (
            ForwardFormatFilter.MESSAGE_LINK_PLACEHOLDER in format
        )
        self._request_sender_title = (
            ForwardFormatFilter.SENDER_TITLE_PLACEHOLDER in format
        )
        self._request_sender_username = (
            ForwardFormatFilter.SENDER_USERNAME_PLACEHOLDER in format
        )

        from telethon.extensions import markdown as md_parser

        self._parser = md_parser

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        # Skip format editing for empty album's items — except the one that
        # got the header when the album was sent (an edit would erase it)
        if (
            event_type is events.MessageEdited.Event
            and message.grouped_id
            and not message.message
            and not await self._carries_header(message)
        ):
            return FilterResult(FilterAction.CONTINUE, message)

        message_link = (
            self.message_link(message) or "" if self._request_message_link else ""
        )
        channel_name = (
            self.channel_name(message) or "" if self._request_channel_name else ""
        )

        sender_title: str = ""
        sender_username: str = ""

        if self._request_sender_title or self._request_sender_username:
            sender: Optional[
                Union[types.User, types.Channel]
            ] = await message.get_sender()

            if sender:
                if self._request_sender_title:
                    sender_title = utils.get_display_name(sender) or ""

                if self._request_sender_username:
                    sender_username = sender.username or ""

        # Fill all placeholders, except {message_text}
        pre_formatted_message = self._format.format(
            channel_name=channel_name,
            message_link=message_link,
            sender_title=sender_title,
            sender_username=sender_username,
            message_text=self.MESSAGE_PLACEHOLDER,
        )
        pre_formatted_text, pre_formatted_entities = self._parser.parse(
            pre_formatted_message
        )

        # In UTF-16 units, like every Telegram entity offset: an astral emoji
        # (e.g. 🚀) before the placeholder is 2 units, not 1 code point.
        message_offset = len(utils.add_surrogate(
            pre_formatted_text[: pre_formatted_text.find(self.MESSAGE_PLACEHOLDER)]
        ))

        if message.entities and message_offset > 0:
            # Move message entities to start of message placeholder
            for entity in message.entities:
                entity.offset += message_offset

        if pre_formatted_entities:
            # Update entities position after message placeholder
            message_placeholder_length_diff = len(
                # Telegram offsets are calculated with surrogates
                utils.add_surrogate(message.message or "")
            ) - len(self.MESSAGE_PLACEHOLDER)

            # Shift entities after the placeholder and resize the ones that
            # contain it (e.g. `**{message_text}**`) to the substituted body.
            self.update_entities_params(
                pre_formatted_entities,
                message_offset,
                message_offset + len(self.MESSAGE_PLACEHOLDER),
                message_placeholder_length_diff,
            )

            if message.entities:
                message.entities.extend(pre_formatted_entities)
            else:
                message.entities = pre_formatted_entities

        # `.replace`, not a second `.format()`: a channel/sender name that itself
        # contains `{`/`}` would make `str.format` raise KeyError here.
        message.message = pre_formatted_text.replace(
            self.MESSAGE_PLACEHOLDER, message.message or ""
        )

        return FilterResult(FilterAction.CONTINUE, message)

    @staticmethod
    async def _carries_header(message: EventMessage) -> bool:
        """Whether this empty album item got the header at send time: the
        album's first item when no item has text (``_process_album``). One
        request for the items around it (an album is at most 10); False when
        it can't tell — the item is then left as it is."""
        client = getattr(message, "_client", None)
        if client is None:
            return False
        try:
            around = await client.get_messages(
                # ids start at 1: the first posts of a channel have no 9 before them
                message.chat_id, ids=list(range(max(1, message.id - 9), message.id + 10))
            )
        except Exception:  # noqa: BLE001 - a best-effort guess, never fatal to the edit
            return False
        album = [m for m in around if m is not None and m.grouped_id == message.grouped_id]
        return (bool(album) and not any(m.message for m in album)
                and min(m.id for m in album) == message.id)

    async def _process_album(
        self, album: EventAlbumMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventAlbumMessage]:
        # Process first message with non-empty text or first message
        message_idx, message_album = next(
            ((idx, message) for idx, message in enumerate(album) if message.message),
            (0, album[0]),
        )

        filter_action, album[message_idx] = await self._process_message(
            message_album, event_type
        )

        return FilterResult(filter_action, album)


class MappedNameForwardFormat(MappedChannelName, ForwardFormatFilter):
    """Filter that adds a forwarding formatting (markdown supported)
    with mapped channel name:

    Example:
    ```
    {message_text}

    Forwarded from [{channel_name}]({message_link})
    ```

    Args:
        mapped (dict[int, str]): Mapped channel names: CHANNEL_ID -> CHANNEL_NAME

        format (str): Forward header format,
        where `{channel_name}`, `{message_link}` and `{message_text}`
        are placeholders to actual incoming message values.
    """

    def __init__(self, mapped: dict[int, str], format: str) -> None:
        MappedChannelName.__init__(self, mapped)
        ForwardFormatFilter.__init__(self, format)


class KeywordReplaceFilter(UpdateEntitiesParams, MessageFilter):
    """Filter that maps keywords
    Args:
        keywords (dict[str, str]): Keywords map
    """

    def __init__(self, keywords: dict[str, str]) -> None:
        # (compiled pattern, replacement, is_regex) — applied to the plain text,
        # not Telethon's surrogate form: there `.` or `[🔥]` could match half of
        # an emoji and leave a broken string behind.
        self._rules: list[tuple[re.Pattern[str], str, bool]] = []
        for k, v in keywords.items():
            pattern = _compile_keyword(k)
            is_regex = k.startswith("r'")
            if not is_regex:  # a plain keyword's replacement is inserted as is
                self._rules.append((pattern, v, False))
                continue
            try:
                # `Pattern.sub` validates the replacement template (group
                # references included) up front, even against an empty
                # string with no match — same fail-fast-at-load-time
                # contract as `_compile_keyword` for the pattern itself,
                # instead of a bare `re.error` the first time a real message
                # happens to match.
                pattern.sub(v, "")
            except re.error as e:
                raise ValueError(
                    f"invalid replacement {v!r} for keyword pattern {k!r}: {e}"
                ) from e
            self._rules.append((pattern, v, True))  # a regex: keeps configured casing

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        if not message.message:
            return FilterResult(FilterAction.CONTINUE, message)

        filtered_text = message.message
        filtered_entities = message.entities or []

        for regex, replacement, is_regex in self._rules:
            filtered_text = self._apply_rule(
                regex, replacement, is_regex, filtered_text, filtered_entities
            )

        message.entities = filtered_entities
        message.message = filtered_text

        return FilterResult(FilterAction.CONTINUE, message)

    def _apply_rule(
        self,
        regex: re.Pattern[str],
        replacement: str,
        is_regex: bool,
        text: str,
        entities: list[types.TypeMessageEntity],
    ) -> str:
        # `text` and `entities` share one coordinate space per rule, so the
        # running error starts at zero for every rule.
        offset_error = 0

        def repl(match: re.Match[str]) -> str:
            nonlocal offset_error
            # `\1` / `\g<0>` only in a regex rule's replacement: a plain
            # keyword's is literal text (a backslash in it stays a backslash).
            result = match.expand(replacement) if is_regex else replacement

            # Case-transfer only for plain word keywords; an explicit `r'...'`
            # replacement keeps its configured casing.
            if not is_regex:
                full_match = match.group()
                if full_match.islower():
                    result = result.lower()
                elif full_match.istitle():
                    result = result.title()
                elif full_match.isupper():
                    result = result.upper()

            # Entities count UTF-16 units (an emoji outside the BMP is two),
            # the match counts characters. Shift by the final string's length:
            # case transfer can change it (e.g. "ß".upper() == "SS").
            match_start = _utf16_len(text[: match.start()])
            match_end = match_start + _utf16_len(match.group())
            diff = _utf16_len(result) - (match_end - match_start)
            self.update_entities_params(
                entities,
                match_start + offset_error,
                match_end + offset_error,
                diff,
            )
            offset_error += diff
            return result

        return regex.sub(repl, text)


_FOOTER_LINK = re.compile(r"t\.me/|telegram\.me/|https?://|www\.|@\w{4,}", re.IGNORECASE)
_FOOTER_ENTITIES = (
    types.MessageEntityUrl,
    types.MessageEntityTextUrl,
    types.MessageEntityMention,
    types.MessageEntityMentionName,
)
_FOOTER_LINE_MAX = 100  # characters: a longer line is content, not a signature


def _bare_url(url: str) -> str:
    """``https://www.T.me/x/`` → ``t.me/x``: to tell a preview's URL in a text."""
    url = url.strip().lower().removeprefix("https://").removeprefix("http://")
    return url.removeprefix("www.").rstrip("/")


class StripFooterFilter(MessageFilter):
    """Cut the source's promo tail («Подпишись на @channel») off a post: bottom
    up, at most ``max_lines`` short lines (≤ 100 characters) with a link or an
    @mention (a text link counts), with the separator lines (no letters or
    digits: ``➖➖➖``, ``👇``) and blank lines around them. Stops at the first
    other line. The link preview goes too when its link was in the tail. A post
    without media that would end up empty stays as it is.

    Args:
        max_lines (`int`, optional): Lines with links to cut, at most. Defaults to 3.
    """

    def __init__(self, max_lines: int = 3) -> None:
        if int(max_lines) < 1:
            raise ValueError(f"StripFooterFilter: max_lines must be 1 or more, got {max_lines!r}")
        self._max_lines = int(max_lines)

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        if not message.message:
            return FilterResult(FilterAction.CONTINUE, message)
        text = utils.add_surrogate(message.message)  # the entities' UTF-16 coordinates
        entities = message.entities or []
        cut, links, pos = len(text), 0, len(text)
        while pos > 0 and links < self._max_lines:
            start = text.rfind("\n", 0, pos) + 1
            line = utils.del_surrogate(text[start:pos])
            has_link = bool(_FOOTER_LINK.search(line)) or any(
                isinstance(e, _FOOTER_ENTITIES) and e.offset < pos and e.offset + e.length > start
                for e in entities
            )
            if has_link and len(line.strip()) <= _FOOTER_LINE_MAX:
                links += 1
                cut = start
            elif any(ch.isalnum() for ch in line):
                break
            elif links and line.strip():  # a separator above a cut line goes with it
                cut = start
            pos = start - 1
        keep = len(text[:cut].rstrip())
        no_media = message.media is None or isinstance(message.media, types.MessageMediaWebPage)
        if cut == len(text) or (keep == 0 and no_media):
            return FilterResult(FilterAction.CONTINUE, message)

        if isinstance(message.media, types.MessageMediaWebPage) and isinstance(
            message.media.webpage, types.WebPage
        ):
            tail = utils.del_surrogate(text[keep:]).lower()
            tail_urls = {
                e.url for e in entities
                if isinstance(e, types.MessageEntityTextUrl) and e.offset + e.length > keep
            }
            preview = _bare_url(message.media.webpage.url)
            mention = "@" + preview.removeprefix("t.me/") if preview.startswith("t.me/") else None
            if preview in tail or (mention and mention in tail) or any(_bare_url(u) == preview for u in tail_urls):
                message.media = None
        kept = []
        for e in entities:
            if e.offset >= keep:
                continue
            e.length = min(e.length, keep - e.offset)
            kept.append(e)
        message.entities = kept
        message.message = utils.del_surrogate(text[:keep])
        return FilterResult(FilterAction.CONTINUE, message)


class SkipWithKeywordsFilter(MessageFilter):
    """Skips message if some keyword found

    Args:
        keywords (set[str]): Keywords set
    """

    def __init__(self, keywords: set[str]) -> None:
        if not keywords:
            # An empty set compiles to `re.compile("")`, which matches every
            # string — SkipWith would drop all messages, AllowWith would pass
            # all. That's a config typo, not a valid setup.
            raise ValueError(
                f"{type(self).__name__} requires a non-empty keywords set"
            )
        try:
            self._lookup_regex = re.compile(
                "|".join(_compile_keyword(k).pattern for k in keywords),
                flags=re.IGNORECASE,
            )
        except re.error as e:  # each compiles alone, not together (a group name used twice…)
            raise ValueError(f"keywords {sorted(keywords)!r} don't combine into one pattern: {e}") from e

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        return FilterResult(
            FilterAction.CONTINUE
            if self._lookup_regex.search(message.message or "") is None
            else FilterAction.DISCARD,
            message,
        )


class AllowWithKeywordsFilter(SkipWithKeywordsFilter):
    """Allow message if some keyword found

    Args:
        keywords (set[str]): Keywords set
    """

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        return FilterResult(
            FilterAction.CONTINUE
            if self._lookup_regex.search(message.message or "") is not None
            else FilterAction.DISCARD,
            message,
        )


class SkipWithUrlFilter(MessageFilter):
    """Skip message if it contains a URL matching the blacklist.

    Checks MessageMediaWebPage (link preview URL), MessageEntityTextUrl (entity.url),
    MessageEntityUrl (bare URL text), and MessageEntityMention (@username).
    Matching is case-insensitive, scheme-independent, and prefix-based
    (e.g. blacklisting "t.me/channel" also blocks "t.me/channel/42").
    Every link form that opens the same chat — telegram.me / telegram.dog /
    www.t.me hosts, the <name>.t.me subdomain, the t.me/s/<name> web preview
    and tg://resolve?domain=… deep links (any parameter order) — is folded into
    the t.me/<name> form, so one t.me entry covers them all.

    Args:
        blacklist (Set[str]): URL prefixes to block.
    """

    @staticmethod
    def _normalize(url: str) -> str:
        norm = re.sub(r"^https?://", "", url, flags=re.IGNORECASE).lower()
        norm = norm.split("#", 1)[0]  # a fragment never changes the target chat
        # Every form below reaches the same chat as t.me/X — fold them into
        # one so a t.me/… entry covers all.
        if norm.startswith("tg://resolve?"):
            query = parse_qsl(norm[len("tg://resolve?"):])
            domain = next((v for k, v in query if k == "domain"), "")
            rest = [(k, v) for k, v in query if k != "domain"]
            norm = f"t.me/{domain}" + (f"?{urlencode(rest)}" if rest else "")
        norm = re.sub(
            r"^(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)(?=[/?]|$)", "t.me", norm
        )
        norm = re.sub(r"^([a-z0-9_]+)\.t\.me(?=[/?]|$)", r"t.me/\1", norm)  # <name>.t.me
        norm = re.sub(r"^t\.me/s/", "t.me/", norm)  # public channel web preview
        return norm.rstrip("/")

    def __init__(self, blacklist: Set[str]) -> None:
        self._blacklist = {self._normalize(u) for u in blacklist}
        # Extract usernames only from direct t.me/<username> entries (no sub-path)
        self._usernames = {
            b[len("t.me/"):]
            for b in self._blacklist
            if b.startswith("t.me/") and b.count("/") == 1
        }

    def _matches(self, url: str) -> bool:
        norm = self._normalize(url)
        return any(
            norm == b or norm.startswith((f"{b}/", f"{b}?"))
            for b in self._blacklist
        )

    async def _process_message(
        self, message: EventMessage, event_type: Type[EventLike]
    ) -> FilterResult[EventMessage]:
        if isinstance(message.media, types.MessageMediaWebPage):
            url = getattr(getattr(message.media, "webpage", None), "url", None)
            if url and self._matches(url):
                return FilterResult(FilterAction.DISCARD, message)
        surrogate = utils.add_surrogate(message.message or "")
        for entity in message.entities or []:
            if isinstance(entity, types.MessageEntityTextUrl):
                if self._matches(entity.url):
                    return FilterResult(FilterAction.DISCARD, message)
            elif isinstance(entity, types.MessageEntityUrl):
                url_text = utils.del_surrogate(
                    surrogate[entity.offset : entity.offset + entity.length]
                )
                if self._matches(url_text):
                    return FilterResult(FilterAction.DISCARD, message)
            elif isinstance(entity, types.MessageEntityMention) and self._usernames:
                mention = utils.del_surrogate(
                    surrogate[entity.offset : entity.offset + entity.length]
                )
                if mention.lstrip("@").lower() in self._usernames:
                    return FilterResult(FilterAction.DISCARD, message)
        return FilterResult(FilterAction.CONTINUE, message)


