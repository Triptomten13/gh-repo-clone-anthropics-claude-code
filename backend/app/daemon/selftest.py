"""Offline-readiness self-test and the independence verdict. Every check runs for real; nothing is assumed."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..ai import llm
from ..models import Agent, Document, MemoryItem
from . import hardware, library, policy, runtime, state


def _check(name: str, fn) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        ok, detail = fn()
        return {"check": name, "ok": bool(ok), "detail": detail, "ms": int((time.monotonic() - t0) * 1000)}
    except Exception as e:
        return {"check": name, "ok": False, "detail": f"{type(e).__name__}: {e}"[:300], "ms": int((time.monotonic() - t0) * 1000)}


def run(db: Session, *, generate: bool = True) -> dict[str, Any]:
    st = state.load(db)
    checks = [
        _check("database", lambda: (db.execute(text("SELECT 1")).scalar() == 1, "reachable")),
        _check("local_runtime", lambda: (hardware.runtime_available().get("llama_cpp"), hardware.runtime_available())),
        _check("local_chat_model", lambda: ((m := library.resolve(db, "chat")) is not None, m.key if m else "none active")),
    ]
    if generate and checks[-1]["ok"]:
        def gen():
            c = runtime.get_local().complete(model="chat", system="Reply with exactly: OK", prompt="Say OK.", schema=None, effort="low", max_tokens=8)
            return "ok" in c.text.lower(), {"model": c.model, "output": c.text[:40], "latency_ms": c.latency_ms}
        checks.append(_check("local_generation", gen))

    def emb():
        from ..knowledge.process import embedder

        mid, fn = embedder()
        v = fn(["offline test"], kind="query")
        return bool(v and v[0]), {"model": mid, "dims": len(v[0]), "semantic": mid.startswith(("gguf:", "ollama:"))}
    checks.append(_check("local_embeddings", emb))

    def offline_chain():
        router = llm.get_router()
        leaks = []
        for tier in ("fast", "standard", "deep"):
            cands, _ = policy.plan(tier, router._all_providers(), profile="OFFLINE")
            leaks += [f"{c.provider}:{c.model}" for c in cands if c.locality == "external"]
        return not leaks, {"external_candidates_in_offline_profile": leaks}
    checks.append(_check("no_external_fallback_in_offline", offline_chain))
    checks.append(_check("archive", lambda: (True, {"documents": db.scalar(select(func.count(Document.id)))})))
    checks.append(_check("memory", lambda: (True, {"items": db.scalar(select(func.count(MemoryItem.id)))})))
    checks.append(_check("agents", lambda: ((n := db.scalar(select(func.count(Agent.id)))) > 0, {"registered": n})))
    return {"offline_mode": st["offline_mode"], "profile": st["profile"], "checks": checks, "ok": all(c["ok"] for c in checks),
            "independence": independence(db)}


def independence(db: Session) -> dict[str, Any]:
    """Runtime dependencies on external services, with the reason each one is or is not mandatory."""
    chat = library.resolve(db, "chat")
    emb = library.resolve(db, "embedding")
    rt = hardware.runtime_available().get("llama_cpp")
    mandatory = []
    if not (rt and chat):
        mandatory.append("text generation: no local chat model active — generation needs an external provider or is unavailable")
    optional = []
    if llm.get_router().providers.get("anthropic") and llm.get_router().providers["anthropic"].configured():
        optional.append("Anthropic API (configured; used only where policy allows — never in offline mode or for private data)")
    if not emb:
        optional.append("semantic embeddings: lexical hash embedder in use (local, but lexical) — activate a local embedding model")
    install_time = ["Python packages (PyPI) and npm packages at install/build time", "model weights from Hugging Face at install time "
                    "(or offline import of a checksum-verified file)"]
    return {"independent": not mandatory, "mandatory_external_runtime_dependencies": mandatory, "optional_external": optional,
            "install_time_external": install_time,
            "statement": ("Core AI runs on this machine: local generation, local embeddings, local orchestration, local storage."
                          if not mandatory else "NOT independent: " + "; ".join(mandatory))}
