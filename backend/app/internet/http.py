"""One shared, instrumented HTTP client for all research traffic."""
from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
import threading
import time
import urllib.robotparser
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx

from ..daemon import cache, state, telemetry

USER_AGENT = "DemonkoncernenResearch/1.0 (self-hosted research assistant; respects robots.txt and rate limits)"
MAX_BYTES = 2_000_000
# polite per-host request rates (requests per second); unknown hosts get the default
RATES = {"en.wikipedia.org": 5, "export.arxiv.org": 0.33, "api.crossref.org": 5, "api.github.com": 0.5, "hn.algolia.com": 3,
         "pypi.org": 5, "api.osv.dev": 5, "services.nvd.nist.gov": 0.15, "huggingface.co": 3, "api.search.brave.com": 1}
DEFAULT_RATE = 1.0


class OfflineError(RuntimeError):
    pass


class FetchError(RuntimeError):
    pass


_client: httpx.Client | None = None
_lock = threading.Lock()
_next_slot: dict[str, float] = {}
_paused_until: dict[str, float] = {}  # host → time; set from Retry-After so nothing is sent before the server allows it
INLINE_WAIT_S = 5.0


_resolve = socket.getaddrinfo  # injectable for tests


def _host_ok(host: str) -> str | None:
    """None if every address the host resolves to is public; otherwise the reason it is refused."""
    if host in ("localhost", "") or host.endswith((".localhost", ".local", ".internal")):
        return "local host name"
    try:
        addrs = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addrs = [ipaddress.ip_address(a[4][0].split("%")[0]) for a in _resolve(host, None)]
        except (socket.gaierror, UnicodeError):
            # cannot resolve here: behind an egress proxy the proxy resolves (and enforces its own policy); without one the
            # connection would fail anyway
            return None if (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")) else "host does not resolve"
    bad = [str(a) for a in addrs if not a.is_global or a.is_multicast]
    return f"resolves to a non-public address ({', '.join(bad[:3])})" if bad else None


def guard_url(url: str) -> None:
    """SSRF guard for EVERY research request and every redirect hop: http(s) only, public addresses only.

    Research traffic must never reach this host, the LAN or cloud metadata endpoints (169.254.169.254), whoever configured
    the URL and whatever a remote server redirects to. Residual risk: DNS re-binding between this check and the connect.
    """
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise FetchError(f"refused: scheme '{u.scheme}' (only http/https)")
    host = (u.hostname or "").lower()
    why = cache.get("ssrf-guard", 60, maxsize=1024).get_or_set(host, lambda: _host_ok(host) or "")
    if why:
        telemetry.event("request_refused", host=host[:100], reason=why)
        raise FetchError(f"refused: {host} {why}")


def _make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(15, connect=8), follow_redirects=True, max_redirects=5, transport=transport,
                        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
                        limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
                        event_hooks={"request": [lambda req: guard_url(str(req.url))]})  # runs again on each redirect hop


def client() -> httpx.Client:
    global _client
    with _lock:
        if _client is None:
            _client = _make_client()
        return _client


def _throttle(host: str) -> None:
    rate = RATES.get(host, DEFAULT_RATE)
    with _lock:
        now = time.monotonic()
        slot = max(now, _next_slot.get(host, 0.0))
        _next_slot[host] = slot + 1.0 / rate
    if slot > now:
        time.sleep(min(slot - now, 10))


def ensure_online() -> None:
    if state.load()["offline_mode"]:
        raise OfflineError("offline mode is on — no internet requests are made")


def robots_allowed(url: str) -> bool:
    """robots.txt check for page fetches (API endpoints are governed by their own terms and rate limits)."""
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"

    def load() -> urllib.robotparser.RobotFileParser:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = client().get(base + "/robots.txt", timeout=8)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except httpx.HTTPError:
            rp.parse([])
        return rp

    rp = cache.get("robots", 86400, maxsize=512).get_or_set(base, load)
    return rp.can_fetch(USER_AGENT, url)


def request(method: str, url: str, *, params: dict | None = None, json: Any = None, headers: dict | None = None, conditional: dict | None = None,
            max_bytes: int = MAX_BYTES, retries: int = 2) -> httpx.Response:
    """GET/POST with throttling, backoff on 429/5xx (Retry-After honoured), conditional headers and a size cap."""
    ensure_online()
    host = urlparse(url).hostname or ""
    if _paused_until.get(host, 0) > time.time():
        raise FetchError(f"{host}: rate-limited by the server, retry after {int(_paused_until[host] - time.time())} s (respected, not retried)")
    h = dict(headers or {})
    if conditional:
        if conditional.get("etag"):
            h["If-None-Match"] = conditional["etag"]
        if conditional.get("last_modified"):
            h["If-Modified-Since"] = conditional["last_modified"]
    attempt = 0
    while True:
        _throttle(host)
        t0 = time.monotonic()
        try:
            with client().stream(method, url, params=params, json=json, headers=h) as r:
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        break
                r._content = body[:max_bytes]  # noqa: SLF001 - bounded body for the caller
        except httpx.HTTPError as e:
            telemetry.record_http(host, (time.monotonic() - t0) * 1000, None, 0, len(str(json or "")), retry=attempt > 0)
            if attempt < retries:
                attempt += 1
                time.sleep(min(2 ** attempt, 8))
                continue
            raise FetchError(f"{host}: {type(e).__name__}") from e
        telemetry.record_http(host, (time.monotonic() - t0) * 1000, r.status_code, len(r.content), len(str(json or "")), retry=attempt > 0)
        if r.status_code in (429, 502, 503, 504) and attempt < retries:
            ra = r.headers.get("retry-after", "")
            wait = float(ra) if ra.isdigit() else 2 ** (attempt + 1)
            if wait > INLINE_WAIT_S:  # do not block the caller; respect the server by pausing this host
                _paused_until[host] = time.time() + wait
                telemetry.event("host_paused", host=host, seconds=int(wait), status=r.status_code)
                return r
            attempt += 1
            time.sleep(wait)
            continue
        return r


def paused_hosts() -> dict[str, int]:
    now = time.time()
    return {h: int(t - now) for h, t in _paused_until.items() if t > now}


def get_json(url: str, **kw: Any) -> Any:
    key = (url, tuple(sorted((kw.get("params") or {}).items())))
    r = cache.flight.do(("GET", key), lambda: request("GET", url, **kw))  # identical concurrent calls share one request
    if r.status_code >= 400:
        raise FetchError(f"{urlparse(url).hostname}: HTTP {r.status_code}")
    return r.json()


def fetch_page(db: Any, url: str, *, source: str = "web", ttl: timedelta = timedelta(days=1)) -> dict[str, Any]:
    """Fetch a public page (robots.txt respected) with conditional revalidation against the research cache."""
    from ..models import WebResource

    if not robots_allowed(url):
        raise FetchError("robots.txt disallows this URL for automated agents")
    wr = db.query(WebResource).filter(WebResource.url == url).first()
    now = datetime.now(UTC)
    if wr and wr.expires_at.replace(tzinfo=wr.expires_at.tzinfo or UTC) > now:
        return {"url": url, "title": wr.title, "text": wr.excerpt, "cached": True, "revalidated": False}
    r = request("GET", url, conditional={"etag": wr.etag, "last_modified": wr.last_modified} if wr else None)
    if r.status_code == 304 and wr:
        wr.expires_at, wr.retrieved_at = now + ttl, now
        db.flush()
        return {"url": url, "title": wr.title, "text": wr.excerpt, "cached": True, "revalidated": True}
    if r.status_code >= 400:
        raise FetchError(f"HTTP {r.status_code}")
    text = r.text
    return {"url": url, "title": "", "text": text, "cached": False, "etag": r.headers.get("etag", ""),
            "last_modified": r.headers.get("last-modified", ""), "hash": hashlib.sha256(r.content).hexdigest(), "bytes": len(r.content)}
