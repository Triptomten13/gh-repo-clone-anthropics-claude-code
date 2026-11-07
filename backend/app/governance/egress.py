"""DAEMON DEPLOYMENT MANAGER — outbound network policy for offline and AIR-GAPPED operation.

A process-wide guard on outbound TCP connects (socket.connect / connect_ex), so EVERY library in the API process is
covered — HTTP clients, SMTP, model downloads, SDKs — not only the code paths written for it. While offline mode or the
AIR_GAPPED profile is active, a connection is allowed only to: loopback; private networks (LAN workers, the database —
unless private networks are disabled); the configured database host; and explicit allow-list entries. Everything else
is refused BEFORE a packet leaves and recorded. In AIR_GAPPED the configured HTTP(S) proxy is refused too (through a
forward proxy the final destination would be invisible at the socket).
Limits, stated plainly: it governs this Python process (not other processes or containers on the host — use network
isolation for those; Independence Test B runs the app in a network namespace for OS-level proof), and allow-listed
host names are resolved when the policy is loaded.
"""
from __future__ import annotations

import collections
import ipaddress
import os
import socket
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

PROFILES = {
    "LOCAL_DEVELOPMENT": "one developer machine; external providers optional",
    "SELF_HOSTED": "single machine you operate; external providers only if enabled",
    "PRIVATE_NETWORK": "several machines on a private network (LAN model workers)",
    "CUSTOMER_VPC": "inside a customer's cloud network; egress limited to its allow-list",
    "ON_PREMISE": "customer data centre; egress limited to its allow-list",
    "AIR_GAPPED": "no outbound connections except loopback, private networks and the explicit allow-list; offline mode forced on",
}


class EgressDenied(ConnectionRefusedError):
    pass


# "private network" means these ranges only — NOT ipaddress.is_private, which also covers documentation, benchmarking
# and other special-purpose ranges (found by the self-test: TEST-NET-3 slipped through as "private")
PRIVATE_NETS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
                                                  "169.254.0.0/16", "fc00::/7", "fe80::/10")]


_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_installed = False
_attempts: collections.deque = collections.deque(maxlen=500)
_counts = {"allowed": 0, "denied": 0}
_cache: dict[str, Any] = {"at": 0.0}
_lock = threading.Lock()


def _resolve(host: str) -> set[str]:
    try:
        return {a[4][0].split("%")[0] for a in socket.getaddrinfo(host, None)}
    except (OSError, UnicodeError):
        return set()


def _policy() -> dict[str, Any]:
    """Cached for 2 s: a connect never waits on a database read in the common case."""
    if time.monotonic() - _cache["at"] < 2.0:
        return _cache["p"]
    from ..daemon import state

    st = state.load()
    dep = st.get("deployment") or {}
    profile = dep.get("profile", "SELF_HOSTED")
    enforce = profile == "AIR_GAPPED" or bool(st.get("offline_mode"))
    allow_ips: set[str] = set()
    for h in dep.get("egress_allowlist", []):
        allow_ips |= {h} if _is_ip(h) else _resolve(h)
    db_host = urlparse(os.getenv("DATABASE_URL", "")).hostname
    if db_host:
        allow_ips |= _resolve(db_host)
    deny_ips: set[str] = set()
    if profile == "AIR_GAPPED":
        for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY"):
            ph = urlparse(os.getenv(var, "")).hostname
            if ph:
                deny_ips |= _resolve(ph)
    p = {"enforce": enforce, "profile": profile, "allow_private": dep.get("allow_private_networks", True), "allow_ips": allow_ips, "deny_ips": deny_ips}
    _cache.update(at=time.monotonic(), p=p)
    return p


def invalidate() -> None:
    _cache["at"] = 0.0


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def decide(host: str, port: int | None = None) -> tuple[bool, str]:
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return True, "not an IP destination"
    if ip.is_loopback:
        return True, "loopback"
    p = _policy()
    if not p["enforce"]:
        return True, "egress not restricted (online, not air-gapped)"
    if str(ip) in p["deny_ips"]:
        return False, f"{ip} is the configured HTTP proxy — refused in AIR_GAPPED (the real destination would be hidden)"
    if str(ip) in p["allow_ips"]:
        return True, "allow-listed"
    if p["allow_private"] and any(ip in n for n in PRIVATE_NETS if n.version == ip.version):
        return True, "private network"
    return False, f"{ip}:{port} is outside the {p['profile'] if p['profile'] == 'AIR_GAPPED' else 'offline'} egress policy"


def _record(host: str, port: int | None, ok: bool, why: str) -> None:
    with _lock:
        _counts["allowed" if ok else "denied"] += 1
        if not ok or why not in ("loopback",):
            _attempts.append({"at": datetime.now(UTC).isoformat(), "host": host, "port": port, "allowed": ok, "reason": why})


def _check(addr: Any) -> None:
    if not isinstance(addr, tuple) or not addr:
        return  # unix sockets etc.
    host, port = str(addr[0]), addr[1] if len(addr) > 1 else None
    ok, why = decide(host, port)
    if why != "loopback" and why != "not an IP destination":
        _record(host, port, ok, why)
    if not ok:
        from ..daemon import telemetry

        telemetry.event("egress_denied", host=host, port=port)  # bounded in-memory event log; the denial is also in report()
        raise EgressDenied(f"egress refused: {why}")


def _connect(self, address):  # noqa: ANN001
    _check(address)
    return _orig_connect(self, address)


def _connect_ex(self, address):  # noqa: ANN001
    try:
        _check(address)
    except EgressDenied:
        import errno

        return errno.ECONNREFUSED
    return _orig_connect_ex(self, address)


def install() -> None:
    global _installed
    if not _installed:
        socket.socket.connect = _connect  # type: ignore[method-assign]
        socket.socket.connect_ex = _connect_ex  # type: ignore[method-assign]
        _installed = True


def uninstall() -> None:
    global _installed
    socket.socket.connect = _orig_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _orig_connect_ex  # type: ignore[method-assign]
    _installed = False


def report() -> dict[str, Any]:
    p = _policy()
    with _lock:
        return {"installed": _installed, "enforcing": p["enforce"], "profile": p["profile"], "allow_private_networks": p["allow_private"],
                "allow_list_ips": sorted(p["allow_ips"]), "blocked_proxy_ips": sorted(p["deny_ips"]), "counts": dict(_counts),
                "recent": list(_attempts)[-100:],
                "scope": "this API process; other processes need network isolation (see Independence Test B)"}


def probe() -> dict[str, Any]:
    """Self-test: try to open a TCP connection to a public address (IANA's example.com, 93.184.215.14:443). While egress
    is restricted the guard refuses it before any packet is sent; when it is not, the harmless connection is closed."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(("93.184.215.14", 443))
        return {"blocked": False, "result": "connected — egress is not restricted"}
    except EgressDenied as e:
        return {"blocked": True, "result": str(e)}
    except OSError as e:
        return {"blocked": False, "result": f"not blocked by policy ({type(e).__name__}) — egress is not restricted"}
    finally:
        s.close()
