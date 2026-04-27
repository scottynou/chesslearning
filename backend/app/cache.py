from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    created_at: float = field(default_factory=time)


class MemoryCache(Generic[T]):
    def __init__(self, ttl_seconds: int = 600, max_items: int = 512) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._items: dict[str, CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        if time() - entry.created_at > self.ttl_seconds:
            self._items.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: T) -> None:
        if len(self._items) >= self.max_items:
            oldest_key = min(self._items, key=lambda item: self._items[item].created_at)
            self._items.pop(oldest_key, None)
        self._items[key] = CacheEntry(value=value)

    def clear(self) -> None:
        self._items.clear()
