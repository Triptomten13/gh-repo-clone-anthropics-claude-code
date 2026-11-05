"""Model residency: which local models stay in RAM, decided by measured memory, use and the resource mode.

Why (measured 2026-11-05 on the dev host): a cold read of model weights runs at ~14 MB/s (a 2.5 GB model ≈ 3 min) while
a page-cached reload takes ~10 s; the old fixed "max 2 loaded" rule reloaded 5 times in a 7-call chat/deep/eco
sequence. Policy instead:
  * keep models loaded while RAM allows (estimate = file size × 1.1 + KV cache), evicting least-recently-used idle
    models only when room is needed or available RAM falls below the reserve;
  * unload models idle longer than the mode's idle limit;
  * LOW_MEMORY / EMERGENCY (chosen, or entered automatically under memory pressure with hysteresis) keep one model;
  * prewarm (background, at start): load chat/eco/embedding, and read the deep model into the OS page cache so the
    first deep request does not pay the cold-disk cost.
Never unloads a model that is in use (its lock is held).
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

from . import state, telemetry

MODES: dict[str, dict[str, Any]] = {
    # max_resident None = limited by memory only
    "ECO": {"max_resident": 2, "idle_unload_s": 600, "reserve_gb": 1.5},
    "BALANCED": {"max_resident": None, "idle_unload_s": 1800, "reserve_gb": 1.5},
    "PERFORMANCE": {"max_resident": None, "idle_unload_s": 7200, "reserve_gb": 1.0},
    "DEEP": {"max_resident": None, "idle_unload_s": 3600, "reserve_gb": 1.5},
    "SPECIALIST": {"max_resident": None, "idle_unload_s": 1800, "reserve_gb": 1.5},
    "OFFLINE": {"max_resident": None, "idle_unload_s": 1800, "reserve_gb": 1.5},
    "LOW_MEMORY": {"max_resident": 1, "idle_unload_s": 120, "reserve_gb": 0.5, "n_ctx_cap": 2048},
    "EMERGENCY": {"max_resident": 1, "idle_unload_s": 60, "reserve_gb": 0.3, "n_ctx_cap": 1024},
}
PRESSURE_ENTER, PRESSURE_CRITICAL, PRESSURE_EXIT = 0.10, 0.05, 0.20  # fraction of RAM available

_auto_mode: str | None = None  # set when memory pressure forces a stricter mode
_lock = threading.Lock()


def configured_mode() -> str:
    try:
        return (state.load()["profile"] or "BALANCED").upper()
    except Exception:
        return "BALANCED"


def effective_mode() -> str:
    return _auto_mode or configured_mode()


def policy() -> dict[str, Any]:
    return MODES.get(effective_mode(), MODES["BALANCED"])


def available_bytes() -> int | None:
    s = telemetry.latest()
    if s and s.get("ram_available_bytes"):
        return s["ram_available_bytes"]
    mi = telemetry._meminfo()
    return mi.get("MemAvailable")


def make_room(provider: Any, need_bytes: int) -> None:
    """Evict least-recently-used idle models until the new one fits the mode's limits. Raises MemoryError if it cannot."""
    pol = policy()
    reserve = int(pol["reserve_gb"] * 1e9)
    while True:
        resident = provider.resident()
        avail = available_bytes()
        too_many = pol["max_resident"] is not None and len(resident) >= pol["max_resident"]
        too_big = avail is not None and avail - need_bytes < reserve
        if not (too_many or too_big):
            return
        victim = provider.lru_idle()
        if victim is None:
            if too_many and not too_big:
                return  # everything resident is busy; allow briefly exceeding the count rather than deadlocking
            raise MemoryError(f"not enough free RAM for this model ({(avail or 0) / 1e9:.1f} GB available, "
                              f"{need_bytes / 1e9:.1f} GB needed + {pol['reserve_gb']} GB reserve)")
        provider.unload(victim, reason="make_room")


def on_sample(s: dict[str, Any]) -> None:
    """Called by the telemetry loop: memory-pressure modes (with hysteresis) and idle unloading."""
    global _auto_mode
    total, avail = s.get("ram_total_bytes"), s.get("ram_available_bytes")
    if total and avail is not None:
        frac = avail / total
        new = _auto_mode
        if frac < PRESSURE_CRITICAL:
            new = "EMERGENCY"
        elif frac < PRESSURE_ENTER and _auto_mode is None:
            new = "LOW_MEMORY"
        elif frac > PRESSURE_EXIT:
            new = None
        if new != _auto_mode:
            telemetry.event("resource_mode", configured=configured_mode(), effective=new or configured_mode(),
                            reason=f"available RAM {frac:.0%}" if new else "pressure cleared")
            _auto_mode = new
    try:
        from .runtime import get_local

        p = get_local()
        pol = policy()
        now = time.time()
        for key, meta in list(p.meta.items()):
            if now - meta["last_used"] > pol["idle_unload_s"]:
                p.unload(key, reason="idle")
        if pol["max_resident"] is not None:
            while len(p.resident()) > pol["max_resident"]:
                v = p.lru_idle()
                if v is None:
                    break
                p.unload(v, reason=f"mode {effective_mode()}")
    except Exception as e:  # pragma: no cover - telemetry must never crash
        telemetry.event("residency_error", error=str(e)[:200])


def _page_cache(path: str) -> int:
    """Sequentially read a file so the OS caches it (no model load, no extra RSS). Returns bytes read."""
    n = 0
    try:
        if hasattr(os, "posix_fadvise"):
            fd = os.open(path, os.O_RDONLY)
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_WILLNEED)
            finally:
                os.close(fd)
        with open(path, "rb", buffering=0) as f:
            while chunk := f.read(8 << 20):
                n += len(chunk)
    except OSError:
        pass
    return n


def prewarm() -> None:
    """Background warm-up at start. Configurable: DAEMON settings local.prewarm = {"load": [...], "page_cache": [...]}."""
    if os.getenv("DAEMON_PREWARM", "1") != "1":
        return

    def run() -> None:
        from . import library
        from .runtime import get_local

        cfg = (state.load()["local"].get("prewarm") or {"load": ["chat", "eco", "embedding"], "page_cache": ["deep"]})
        p = get_local()
        for slot in cfg.get("load", []):
            try:
                m = library.resolve(None, slot)
                if not m:
                    continue
                if slot == "embedding":
                    p.embed(["warm-up"], "query")
                else:
                    p.ensure_loaded(slot)
                telemetry.event("prewarm_load", slot=slot, model=m.key)
            except Exception as e:
                telemetry.event("prewarm_failed", slot=slot, error=str(e)[:200])
        for slot in cfg.get("page_cache", []):  # last: slow cold reads must not delay the small models
            m = library.resolve(None, slot)
            if m:
                t0 = time.time()
                n = _page_cache(m.file_path)
                telemetry.event("prewarm_page_cache", slot=slot, model=m.key, mb=round(n / 1e6), seconds=round(time.time() - t0, 1))

    threading.Thread(target=run, name="daemon-prewarm", daemon=True).start()
