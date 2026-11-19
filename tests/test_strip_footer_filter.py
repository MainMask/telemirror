"""StripFooterFilter: cuts the source's promo tail, keeps the post's own text."""

import pytest
from telethon import events
from telethon.tl import types

from telemirror.messagefilters.base import FilterAction
from telemirror.messagefilters.messagefilters import StripFooterFilter
from tests.conftest import entity_text, make_message, run


def _strip(text, entities=None, media=None, **kw):
    action, res = run(StripFooterFilter(**kw)._process_message(
        make_message(text, entities=entities, media=media), events.NewMessage.Event))
    assert action == FilterAction.CONTINUE
    return res


def _webpage(url):
    return types.MessageMediaWebPage(webpage=types.WebPage(
        id=1, url=url, display_url=url, hash=0))


def test_cuts_mention_and_link_lines_with_blank_lines():
    res = _strip("Новость дня.\n\n👉 Подписаться: @source_chan\nt.me/source_chan\n\n")
    assert res.message == "Новость дня."


def test_cuts_separator_above_and_below_the_tail():
    res = _strip("Текст поста\n➖➖➖➖\n@source_chan\n👇")
    assert res.message == "Текст поста"


def test_text_link_on_a_word_counts_as_a_link():
    text = "Текст поста\nПодписаться"
    link = types.MessageEntityTextUrl(offset=12, length=11, url="https://t.me/source_chan")
    res = _strip(text, entities=[link])
    assert res.message == "Текст поста"
    assert res.entities == []


def test_stops_at_the_first_ordinary_line():
    res = _strip("Начало @mention_in_body\nОбычная строка\n@source_chan")
    assert res.message == "Начало @mention_in_body\nОбычная строка"


def test_a_long_line_with_a_link_is_content():
    body = "Подробный разбор " + "очень " * 20 + "https://site.com/article"
    assert _strip(f"Заголовок\n{body}").message == f"Заголовок\n{body}"


def test_no_tail_leaves_the_post_untouched():
    msg = _strip("Просто текст\nбез ссылок")
    assert msg.message == "Просто текст\nбез ссылок"


def test_max_lines_limits_the_cut():
    res = _strip("Текст\n@a_chan1\n@b_chan2\n@c_chan3", max_lines=2)
    assert res.message == "Текст\n@a_chan1"


def test_post_of_only_a_link_without_media_stays():
    assert _strip("@source_chan").message == "@source_chan"


def test_caption_of_only_a_link_with_media_goes():
    photo = types.MessageMediaPhoto(photo=types.PhotoEmpty(id=1))
    res = _strip("@source_chan", media=photo)
    assert res.message == ""
    assert res.media is photo


def test_entities_are_kept_and_trimmed_in_utf16():
    text = "😀 Жирный текст\n@source_chan"
    bold = types.MessageEntityBold(offset=3, length=6)  # "Жирный" after a 2-unit emoji
    over = types.MessageEntityItalic(offset=10, length=20)  # "текст\n@source…": crosses the cut
    mention = types.MessageEntityMention(offset=16, length=12)
    res = _strip(text, entities=[bold, over, mention])
    assert res.message == "😀 Жирный текст"
    assert [entity_text(res, e) for e in res.entities] == ["Жирный", "текст"]


def test_preview_of_the_cut_link_goes_body_preview_stays():
    res = _strip("Текст\nt.me/source_chan", media=_webpage("https://t.me/source_chan"))
    assert res.message == "Текст" and res.media is None
    body = _webpage("https://site.com/a")
    res = _strip("Читать https://site.com/a и ещё очень много слов, чтобы строка была длинной " * 2
                 + "\n@source_chan", media=body)
    assert res.media is body


def test_preview_of_a_cut_mention_goes():
    res = _strip("Текст\n@source_chan", media=_webpage("https://t.me/source_chan"))
    assert res.media is None


def test_album_caption_is_cut():
    album = [make_message("Подпись альбома\n@source_chan"), make_message("")]
    action, res = run(StripFooterFilter().process(album, events.NewMessage.Event))
    assert action == FilterAction.CONTINUE
    assert [m.message for m in res] == ["Подпись альбома", ""]


def test_max_lines_below_one_is_refused():
    with pytest.raises(ValueError):
        StripFooterFilter(max_lines=0)
