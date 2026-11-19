import collections
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V], collections.OrderedDict[K, V]):
    """
    Dict with a limited length, ejecting LRUs as needed: once it holds more
    than ``capacity`` items, it is trimmed back to the newest half.
    """

    def __init__(self, *args, capacity: int, **kwargs):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self.capacity = capacity
        self.keep_last = max(1.0, capacity / 2)

        super().__init__(*args, **kwargs)

    def __setitem__(self, key: K, value: V):
        super().__setitem__(key, value)
        super().move_to_end(key)

        if len(self) > self.capacity:
            while len(self) > self.keep_last:
                oldkey = next(iter(self))
                super().__delitem__(oldkey)

    def __getitem__(self, key: K):
        val = super().__getitem__(key)
        super().move_to_end(key)

        return val

    def get(self, key: K, default=None):
        # dict.get bypasses __getitem__, so without this a read never refreshes
        # the entry's recency and it can be evicted before staler ones.
        return self[key] if key in self else default
