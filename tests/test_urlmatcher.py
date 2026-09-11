from telemirror.misc.urlmatcher import UrlMatcher


def test_empty_matcher_matches_any_url():
    m = UrlMatcher()
    assert m.match("https://example.com") is True


def test_blacklist_host_match():
    m = UrlMatcher(blacklist={"t.me"})
    assert m.match("https://t.me") is True
    assert m.match("http://t.me/channel") is True
    assert m.match("https://example.com") is False


def test_blacklist_full_url_match():
    m = UrlMatcher(blacklist={"t.me/joinchat"})
    assert m.match("https://t.me/joinchat") is True
    assert m.match("https://t.me/other") is False


def test_whitelist_overrides_blacklist():
    m = UrlMatcher(blacklist={"t.me"}, whitelist={"t.me/c/"})
    assert m.match("https://t.me/c/123/45") is False  # whitelisted prefix
    assert m.match("https://t.me/spam") is True


def test_case_insensitive():
    m = UrlMatcher(blacklist={"T.ME"})
    assert m.match("https://t.me/x") is True


def test_search_returns_spans():
    m = UrlMatcher(blacklist={"bad.com"})
    text = "see bad.com and good.com"
    spans = m.search(text)
    assert [text[s:e] for s, e in spans] == ["bad.com"]


def test_match_none_is_false():
    assert UrlMatcher(blacklist={"t.me"}).match(None) is False


def test_default_matchers_are_independent():
    a = UrlMatcher()
    b = UrlMatcher()
    a._blacklist.add("t.me")
    assert b._blacklist == set()
