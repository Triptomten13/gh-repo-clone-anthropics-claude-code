"""Resource Intelligence telemetry — real measurements only, bounded memory.

* System sampler (background thread, default every 5 s, last 720 samples ≈ 1 h): CPU %, RAM, swap, disk usage,
  disk read/write bytes/s, network rx/tx bytes/s, CPU temperature (if the kernel exposes it), GPU via nvidia-smi
  (if present), this process's RSS and CPU time. Linux /proc and /sys; elsewhere fields are None (unknown), never guessed.
* Request metrics (middleware): per route template — count, errors, latency reservoir (p50/p95), SQL statements,
  response bytes.
* Outbound HTTP metrics (per host): requests, bytes, latency, status classes, retries, cache revalidations.
* Event log (bounded deque) for notable events: model loads/unloads, memory-pressure mode changes, cache purges.
"""
from __future__ import annotations

import contextvars
import os
import shutil
import statistics
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

SAMPLE_EVERY_S = float(os.getenv("TELEMETRY_SAMPLE_S", "5"))
KEEP_SAMPLES = int(os.getenv("TELEMETRY_KEEP", "720"))
RESERVOIR = 200

_samples: deque[dict[str, Any]] = deque(maxlen=KEEP_SAMPLES)
_events: deque[dict[str, Any]] = deque(maxlen=300)
_lock = threading.Lock()
_started = False
_prev: dict[str, Any] = {}

sql_count: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar("sql_count", default=None)


# ------------------------------------------------------------------ /proc readers
def _read(path: str) -> str | None:
    try:
        return Path(path).read_text()
    except Exception:
        return None


def _cpu_times() -> tuple[int, int] | None:
    t = _read("/proc/stat")
    if not t:
        return None
    parts = [int(x) for x in t.splitlines()[0].split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    return sum(parts), idle


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        k, _, v = line.partition(":")
        if v.strip():
            out[k] = int(v.split()[0]) * 1024
    return out


def _disk_io() -> tuple[int, int] | None:
    t = _read("/proc/diskstats")
    if not t:
        return None
    try:  # whole block devices only (partitions would double-count)
        whole = {p.name for p in Path("/sys/block").iterdir() if not p.name.startswith(("loop", "ram", "zram", "dm-"))}
    except Exception:
        whole = set()
    rd = wr = 0
    for line in t.splitlines():
        f = line.split()
        if len(f) > 9 and f[2] in whole:
            rd += int(f[5]) * 512
            wr += int(f[9]) * 512
    return rd, wr


def _net_io() -> tuple[int, int] | None:
    t = _read("/proc/net/dev")
    if not t:
        return None
    rx = tx = 0
    for line in t.splitlines()[2:]:
        name, _, data = line.partition(":")
        if name.strip() == "lo":
            continue
        f = data.split()
        rx, tx = rx + int(f[0]), tx + int(f[8])
    return rx, tx


def _temperature_c() -> float | None:
    temps = []
    for z in Path("/sys/class/thermal").glob("thermal_zone*/temp") if Path("/sys/class/thermal").exists() else []:
        v = _read(str(z))
        if v and v.strip().lstrip("-").isdigit():
            temps.append(int(v) / 1000)
    return round(max(temps), 1) if temps else None


def _self_proc() -> dict[str, Any]:
    rss = None
    for line in (_read("/proc/self/status") or "").splitlines():
        if line.startswith("VmRSS:"):
            rss = int(line.split()[1]) * 1024
    t = os.times()
    return {"rss_bytes": rss, "cpu_s": round(t.user + t.system, 2), "threads": threading.active_count()}


def sample() -> dict[str, Any]:
    """One measurement. Rates are computed against the previous sample."""
    now = time.time()
    mem = _meminfo()
    cpu = _cpu_times()
    dio, nio = _disk_io(), _net_io()
    out: dict[str, Any] = {"ts": round(now, 1), "cpu_pct": None, "disk_read_bps": None, "disk_write_bps": None, "net_rx_bps": None,
                           "net_tx_bps": None}
    p = _prev
    if cpu and p.get("cpu"):
        dt, di = cpu[0] - p["cpu"][0], cpu[1] - p["cpu"][1]
        out["cpu_pct"] = round(100 * (1 - di / dt), 1) if dt > 0 else None
    if p.get("ts"):
        el = max(now - p["ts"], 1e-3)
        if dio and p.get("dio"):
            out["disk_read_bps"], out["disk_write_bps"] = int((dio[0] - p["dio"][0]) / el), int((dio[1] - p["dio"][1]) / el)
        if nio and p.get("nio"):
            out["net_rx_bps"], out["net_tx_bps"] = int((nio[0] - p["nio"][0]) / el), int((nio[1] - p["nio"][1]) / el)
    _prev.update({"ts": now, "cpu": cpu, "dio": dio, "nio": nio})
    try:
        from . import hardware

        du = shutil.disk_usage(hardware.models_dir())
        disk = {"disk_total_bytes": du.total, "disk_free_bytes": du.free}
    except Exception:
        disk = {"disk_total_bytes": None, "disk_free_bytes": None}
    out.update({"ram_total_bytes": mem.get("MemTotal"), "ram_available_bytes": mem.get("MemAvailable"),
                "page_cache_bytes": mem.get("Cached"), "swap_used_bytes": (mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)) if mem else None,
                **disk, "cpu_temp_c": _temperature_c(), "process": _self_proc()})
    try:
        from . import hardware

        out["gpus"] = hardware._gpus()  # [] when no NVIDIA GPU / nvidia-smi
    except Exception:
        out["gpus"] = []
    return out


def _loop() -> None:  # pragma: no cover - background thread
    while True:
        try:
            s = sample()
            with _lock:
                _samples.append(s)
            from . import residency

            residency.on_sample(s)
        except Exception as e:
            event("telemetry_error", error=str(e)[:200])
        time.sleep(SAMPLE_EVERY_S)


def start() -> None:
    global _started
    if _started or os.getenv("TELEMETRY_DISABLED") == "1":
        return
    _started = True
    sample()  # prime rate counters
    threading.Thread(target=_loop, name="daemon-telemetry", daemon=True).start()


def latest() -> dict[str, Any] | None:
    with _lock:
        return dict(_samples[-1]) if _samples else None


def history(points: int = 120) -> list[dict[str, Any]]:
    with _lock:
        return [{k: s.get(k) for k in ("ts", "cpu_pct", "ram_available_bytes", "net_rx_bps", "net_tx_bps", "disk_read_bps")}
                | {"rss_bytes": (s.get("process") or {}).get("rss_bytes")} for s in list(_samples)[-points:]]


def event(kind: str, **data: Any) -> None:
    _events.append({"ts": round(time.time(), 1), "kind": kind, **data})


def events(limit: int = 50) -> list[dict[str, Any]]:
    return list(_events)[-limit:][::-1]


# ------------------------------------------------------------------ request metrics
class _RouteStats:
    __slots__ = ("count", "errors", "lat", "sql", "bytes")

    def __init__(self) -> None:
        self.count, self.errors, self.sql, self.bytes = 0, 0, 0, 0
        self.lat: deque[float] = deque(maxlen=RESERVOIR)


_routes: dict[str, _RouteStats] = defaultdict(_RouteStats)


def record_request(route: str, ms: float, status: int, sql: int, nbytes: int) -> None:
    with _lock:
        r = _routes[route]
        r.count += 1
        r.errors += 1 if status >= 500 else 0
        r.lat.append(ms)
        r.sql += sql
        r.bytes += nbytes


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(len(s) * q))], 1)


def routes(top: int = 30) -> list[dict[str, Any]]:
    with _lock:
        rows = [{"route": k, "count": v.count, "errors": v.errors, "p50_ms": _pct(list(v.lat), 0.5), "p95_ms": _pct(list(v.lat), 0.95),
                 "sql_per_request": round(v.sql / v.count, 1) if v.count else 0, "avg_bytes": int(v.bytes / v.count) if v.count else 0,
                 "total_ms": round(sum(v.lat) / max(len(v.lat), 1) * v.count)} for k, v in _routes.items()]
    return sorted(rows, key=lambda r: -r["total_ms"])[:top]


# ------------------------------------------------------------------ outbound HTTP
class _HostStats:
    __slots__ = ("requests", "bytes_in", "bytes_out", "lat", "status", "retries", "not_modified", "errors")

    def __init__(self) -> None:
        self.requests = self.bytes_in = self.bytes_out = self.retries = self.not_modified = self.errors = 0
        self.lat: deque[float] = deque(maxlen=RESERVOIR)
        self.status: dict[str, int] = defaultdict(int)


_hosts: dict[str, _HostStats] = defaultdict(_HostStats)


def record_http(host: str, ms: float, status: int | None, bytes_in: int, bytes_out: int, retry: bool = False) -> None:
    with _lock:
        h = _hosts[host]
        h.requests += 1
        h.bytes_in += bytes_in
        h.bytes_out += bytes_out
        h.lat.append(ms)
        h.retries += 1 if retry else 0
        if status is None:
            h.errors += 1
            h.status["error"] += 1
        else:
            h.status[f"{status // 100}xx"] += 1
            h.not_modified += 1 if status == 304 else 0


def hosts() -> list[dict[str, Any]]:
    with _lock:
        return sorted([{"host": k, "requests": v.requests, "bytes_in": v.bytes_in, "bytes_out": v.bytes_out, "p50_ms": _pct(list(v.lat), 0.5),
                        "errors": v.errors, "retries": v.retries, "not_modified": v.not_modified, "status": dict(v.status)}
                       for k, v in _hosts.items()], key=lambda r: -r["requests"])


def reset() -> None:
    with _lock:
        _routes.clear()
        _hosts.clear()
        _events.clear()


def summary_latency() -> dict[str, Any]:
    with _lock:
        lat = [x for r in _routes.values() for x in r.lat]
    return {"p50_ms": _pct(lat, 0.5), "mean_ms": round(statistics.mean(lat), 1) if lat else None}
