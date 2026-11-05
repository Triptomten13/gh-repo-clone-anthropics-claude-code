"""Connector framework.

A connector wraps one external platform behind a uniform interface. Connectors:
* only use official APIs / authorised access (no scraping around restrictions);
* declare the env vars they need; ``status()`` reports missing configuration;
* raise ``NotConfigured`` instead of returning invented data;
* rate-limit themselves.

New platforms are added by subclassing ``Connector`` and registering in
``registry.py``; no other code changes are needed.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx


class NotConfigured(RuntimeError):
    def __init__(self, connector: str, missing: list[str]):
        self.connector = connector
        self.missing = missing
        super().__init__(f"{connector} is not configured; missing env: {', '.join(missing)}")


class NotImplementedPlatform(RuntimeError):
    pass


@dataclass
class Signal:
    """Normalised market observation produced by any connector."""

    keyword: str
    platform: str
    metric: str
    value: float
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_ref: str = ""
    region: str = "SE"


@dataclass
class ProductCandidate:
    name: str
    platform: str
    source_url: str = ""
    price: float | None = None
    currency: str = "SEK"
    category: str = ""
    description: str = ""
    review_count: int | None = None
    rating: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class RateLimiter:
    def __init__(self, per_second: float) -> None:
        self.interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._last + self.interval - now
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


class Connector:
    id: str = "base"
    name: str = "Base"
    kind: str = "research"  # research | commerce | payments | fulfillment | marketing
    required_env: tuple[str, ...] = ()
    docs_url: str = ""
    access_notes: str = ""
    implemented: bool = True
    rate_per_second: float = 1.0
    capabilities: tuple[str, ...] = ()

    def __init__(self, client: httpx.Client | None = None, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ
        self._client = client
        self._limiter = RateLimiter(self.rate_per_second)

    # ---- configuration
    def missing_env(self) -> list[str]:
        return [k for k in self.required_env if not self._env.get(k)]

    def configured(self) -> bool:
        return self.implemented and not self.missing_env()

    def env(self, key: str) -> str:
        return self._env.get(key, "")

    def require(self) -> None:
        if not self.implemented:
            raise NotImplementedPlatform(f"{self.name}: adapter planned, not implemented yet")
        missing = self.missing_env()
        if missing:
            raise NotConfigured(self.name, missing)

    @property
    def http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=20.0, headers={"User-Agent": "rocky-commerce-intel/0.1"})
        return self._client

    def get(self, url: str, **kw: Any) -> httpx.Response:
        self._limiter.wait()
        r = self.http.get(url, **kw)
        r.raise_for_status()
        return r

    def post(self, url: str, **kw: Any) -> httpx.Response:
        self._limiter.wait()
        r = self.http.post(url, **kw)
        r.raise_for_status()
        return r

    def status(self) -> dict[str, Any]:
        state = "not_implemented" if not self.implemented else ("configured" if self.configured() else "missing_credentials")
        return {
            "id": self.id, "name": self.name, "kind": self.kind, "state": state,
            "required_env": list(self.required_env), "missing_env": self.missing_env() if self.implemented else list(self.required_env),
            "docs_url": self.docs_url, "access_notes": self.access_notes, "capabilities": list(self.capabilities),
        }

    # ---- research capability (override)
    def search_signals(self, keyword: str) -> list[Signal]:
        raise NotImplementedPlatform(f"{self.name} does not provide signals")

    def search_products(self, keyword: str, limit: int = 20) -> list[ProductCandidate]:
        raise NotImplementedPlatform(f"{self.name} does not provide product search")
