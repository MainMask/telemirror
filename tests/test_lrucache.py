from telemirror.misc.lrucache import LRUCache


def test_basic_put_get():
    c = LRUCache[str, int](capacity=10)
    c["a"] = 1
    assert c.get("a") == 1
    assert c.get("missing") is None
    assert c.get("missing", 0) == 0


def test_get_refreshes_recency():
    """A read via .get() must mark the entry recently-used, or it would be
    evicted before entries that were only ever written."""
    c = LRUCache[str, int](capacity=10)  # free_factor 0.5 -> purge keeps 5 newest
    for i in range(10):
        c[f"k{i}"] = i
    c.get("k0")        # touch the oldest via .get
    c["k10"] = 10      # overflow -> purge least-recently-used
    assert c.get("k0") == 0     # survived because .get refreshed it
    assert "k1" not in c        # k1 was the true LRU and got evicted


def test_setitem_eviction_keeps_capacity_bound():
    c = LRUCache[int, int](capacity=5)
    for i in range(20):
        c[i] = i
    assert len(c) <= 5
    assert c.get(19) == 19  # newest always present
