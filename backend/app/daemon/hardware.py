"""What this machine can actually run. Read from the OS — nothing is assumed."""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

def models_dir() -> Path:
    p = Path(os.getenv("MODELS_DIR", Path(__file__).resolve().parents[2] / "data" / "models"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            out[k] = int(v.strip().split()[0]) * 1024
    except Exception as e:  # non-Linux: report unknown (0) rather than guess
        log.debug("meminfo unavailable: %s", e)
    return out


def _cpu() -> dict[str, Any]:
    model, flags = platform.processor() or "", set()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            elif line.startswith("flags") and not flags:
                flags = set(line.split(":", 1)[1].split())
    except Exception as e:
        log.debug("cpuinfo unavailable: %s", e)
    try:
        usable = len(os.sched_getaffinity(0))
    except Exception:
        usable = os.cpu_count() or 1
    return {"model": model or platform.machine(), "logical_cores": os.cpu_count() or 1, "usable_cores": usable,
            "simd": sorted(f for f in flags if f in {"avx", "avx2", "avx512f", "fma", "f16c", "neon", "asimd"}),
            "arch": platform.machine()}


def _gpus() -> list[dict[str, Any]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],  # noqa: S603 - fixed argv, resolved binary, no shell
                           capture_output=True, text=True, timeout=5, check=False)
        out = []
        for line in r.stdout.strip().splitlines():
            name, total, free = (x.strip() for x in line.split(","))
            out.append({"vendor": "nvidia", "name": name, "vram_total_mb": int(total), "vram_free_mb": int(free)})
        return out
    except Exception:
        return []


def runtime_available() -> dict[str, Any]:
    try:
        import llama_cpp

        return {"llama_cpp": True, "llama_cpp_version": getattr(llama_cpp, "__version__", "?")}
    except Exception as e:  # not installed / incompatible CPU
        return {"llama_cpp": False, "llama_cpp_error": f"{type(e).__name__}: {e}"[:200]}


def snapshot() -> dict[str, Any]:
    mem = _meminfo()
    du = shutil.disk_usage(models_dir())
    gpus = _gpus()
    return {
        "os": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
        "cpu": _cpu(),
        "ram_total_bytes": mem.get("MemTotal", 0), "ram_available_bytes": mem.get("MemAvailable", 0),
        "disk_free_bytes": du.free, "models_dir": str(models_dir()),
        "gpus": gpus, "accelerator": "cuda" if gpus else "cpu",
        "runtime": runtime_available(),
    }


def fit(size_bytes: int, n_ctx: int = 4096, snap: dict[str, Any] | None = None) -> dict[str, Any]:
    """Will a GGUF model of this size run here? Rule of thumb, stated as such: weights are memory-mapped,
    plus a KV cache/compute overhead that grows with context (≈ 0.25 GB per 4K tokens for ≤2B models)."""
    s = snap or snapshot()
    need = int(size_bytes * 1.1 + 0.25e9 * max(1, n_ctx / 4096) + 0.3e9)
    avail = s["ram_available_bytes"] or s["ram_total_bytes"]
    disk_ok = s["disk_free_bytes"] > size_bytes * 1.05
    if not s["runtime"].get("llama_cpp"):
        verdict = "no_runtime"
    elif need > avail:
        verdict = "does_not_fit"
    elif need > avail * 0.7:
        verdict = "tight"
    else:
        verdict = "fits"
    return {"verdict": verdict, "ram_needed_bytes": need, "ram_available_bytes": avail, "disk_ok": disk_ok,
            "basis": "estimate: file size ×1.1 + context-scaled KV cache + runtime overhead"}
