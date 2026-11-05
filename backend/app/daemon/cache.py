"""L1 in-process caches (bounded, TTL, LRU) with hit/miss statistics, plus single-flight duplicate suppression.

Every cache is registered by name so the Control Center can show its hit rate, and can be invalidated by name when the
underlying data changes (model activation, settings change). Only system-wide, non-personal values live here; anything
user-scoped carries the user in its key or is not cached at all.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(self, name: str, ttl_s: float, maxsize: int = 256) -> None:
        self.name, self.ttl_s, self.maxsize = name, ttl_s, maxsize
        self._d: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = self.misses = self.evictions = 0

    def get(self, key: Hashable) -> tuple[bool, Any]:
        now = time.monotonic()
        with self._lock:
            hit = self._d.get(key)
            if hit and hit[0] > now:
                self._d.move_to_end(key)
                self.hits += 1
                return True, hit[1]
            if hit:
                del self._d[key]
            self.misses += 1
            return False, None

    def set(self, key: Hashable, value: Any, ttl_s: float | None = None) -> None:
        with self._lock:
            self._d[key] = (time.monotonic() + (self.ttl_s if ttl_s is None else ttl_s), value)
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)
                self.evictions += 1

    def get_or_set(self, key: Hashable, fn: Callable[[], T], ttl_s: float | None = None) -> T:
        ok, v = self.get(key)
        if ok:
            return v
        v = flight.do((self.name, key), fn)
        self.set(key, v, ttl_s)
        return v

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def stats(self) -> dict[str, Any]:
        n = self.hits + self.misses
        return {"name": self.name, "layer": "L1", "size": len(self._d), "maxsize": self.maxsize, "ttl_s": self.ttl_s, "hits": self.hits,
                "misses": self.misses, "evictions": self.evictions, "hit_rate": round(self.hits / n, 3) if n else None}


class SingleFlight:
    """Concurrent callers with the same key share one execution (duplicate request suppression)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[Hashable, tuple[threading.Event, list[Any]]] = {}
        self.suppressed = 0

    def do(self, key: Hashable, fn: Callable[[], T]) -> T:
        with self._lock:
            call = self._calls.get(key)
            leader = call is None
            if leader:
                call = (threading.Event(), [None, None])
                self._calls[key] = call
            else:
                self.suppressed += 1
        ev, box = call
        if not leader:
            ev.wait()
            if box[1] is not None:
                raise box[1]
            return box[0]
        try:
            box[0] = fn()
            return box[0]
        except BaseException as e:
            box[1] = e
            raise
        finally:
            with self._lock:
                self._calls.pop(key, None)
            ev.set()


flight = SingleFlight()
_registry: dict[str, TTLCache] = {}


def get(name: str, ttl_s: float, maxsize: int = 256) -> TTLCache:
    c = _registry.get(name)
    if c is None:
        c = _registry[name] = TTLCache(name, ttl_s, maxsize)
    return c


def invalidate(*names: str) -> None:
    for n in names or tuple(_registry):
        if n in _registry:
            _registry[n].clear()


def stats() -> list[dict[str, Any]]:
    return [c.stats() for c in _registry.values()] + [{"name": "single-flight", "layer": "L1", "suppressed": flight.suppressed}]
