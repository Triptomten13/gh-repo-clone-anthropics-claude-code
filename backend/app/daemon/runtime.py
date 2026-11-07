"""Local inference adapters.

LocalLlamaProvider   in-process llama.cpp (llama-cpp-python) over GGUF files from the model library.
                     No network listener of its own — it is reachable only through the authenticated API.
OpenAICompatProvider any OpenAI-compatible endpoint you run (llama.cpp server, vLLM, LM Studio …),
                     used for registered DAEMON workers on other machines.
LocalGGUFEmbedder    semantic embeddings from the active embedding model.
"""
from __future__ import annotations

import contextlib
import contextvars
import ipaddress
import os
import re
import threading
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import httpx

from ..ai.providers import Completion, ProviderUnavailable, _parse_json
from . import catalog, hardware, state

# Measurement mode: greedy decoding with a fixed seed, so the same model on the same task gives the same answer and a
# championship measures models instead of sampling luck (found in the first real championship: unchanged models moved
# by up to 0.29 between two runs at temperature 0.2 with a random seed).
_DETERMINISTIC: contextvars.ContextVar[bool] = contextvars.ContextVar("daemon_deterministic", default=False)
EVAL_SEED = 1234


@contextlib.contextmanager
def deterministic() -> Iterator[None]:
    tok = _DETERMINISTIC.set(True)
    try:
        yield
    finally:
        _DETERMINISTIC.reset(tok)

THINK = re.compile(r"<think>(.*?)</think>", re.S)


def split_thinking(text: str) -> tuple[str, str, bool]:
    """(answer, reasoning, finished). `finished` is False when the model was still thinking when output stopped."""
    reasoning = "\n".join(m.strip() for m in THINK.findall(text))
    answer = THINK.sub("", text)
    if "<think>" in answer:  # opened but never closed: the budget ran out mid-thought
        head, _, tail = answer.partition("<think>")
        return head.strip(), (reasoning + "\n" + tail).strip(), False
    return answer.strip(), reasoning, True


def thinking_budget() -> int:
    """Max tokens a reasoning model may think before it must answer (DAEMON settings → local.thinking_tokens)."""
    env = os.getenv("DAEMON_THINKING_TOKENS")
    if env:
        return int(env)
    return int(state.load()["local"].get("thinking_tokens") or 1536)


def locality_of_url(url: str) -> str:
    """local (loopback) | lan (private network) | external (anything else, incl. unresolved names)."""
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost"):
        return "local"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback:
            return "local"
        if ip.is_private or ip.is_link_local:
            return "lan"
        return "external"
    except ValueError:
        return "lan" if host.endswith((".lan", ".local", ".internal", ".home.arpa")) else "external"


class LocalLlamaProvider:
    id = "local"
    locality = "local"
    RECENT_S = 10  # a model used within this window is never chosen for eviction

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}
        self.meta: dict[str, dict[str, Any]] = {}  # cache_key → size, loaded_at, last_used, uses, load_ms
        self._locks: dict[str, threading.Lock] = {}
        self._load_locks: dict[str, threading.Lock] = {}
        self._glock = threading.RLock()
        self.last_error: str | None = None
        self.load_count = 0  # telemetry: model (re)loads — high numbers mean residency churn
        self.load_ms_total = 0
        self.unload_count = 0

    # -- availability
    def configured(self) -> bool:
        if not hardware.runtime_available().get("llama_cpp"):
            return False
        from . import library

        return library.resolve(None, "chat") is not None

    def health(self) -> dict[str, Any]:
        from . import library

        chat, eco, emb = (library.resolve(None, s) for s in ("chat", "eco", "embedding"))
        return {"configured": self.configured(), "runtime": hardware.runtime_available(), "loaded": self.resident(),
                "chat_model": chat.key if chat else None, "eco_model": eco.key if eco else None,
                "embedding_model": emb.key if emb else None, "network_listener": False, "last_error": self.last_error}

    # -- residency (decisions in daemon/residency.py)
    def resident(self) -> list[str]:
        with self._glock:
            return list(self._models)

    def residency(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._glock:
            return [{"cache_key": k, **m, "idle_s": round(now - m["last_used"]), "busy": self._locks[k].locked()} for k, m in self.meta.items()]

    def lru_idle(self) -> str | None:
        now = time.time()
        with self._glock:
            cands = [(m["last_used"], k) for k, m in self.meta.items() if not self._locks[k].locked() and now - m["last_used"] > self.RECENT_S]
        return min(cands)[1] if cands else None

    def unload(self, cache_key: str, reason: str = "") -> bool:
        from . import telemetry

        with self._glock:
            lock = self._locks.get(cache_key)
            if lock is None or not lock.acquire(blocking=False):
                return False  # unknown or in use: never pulled out from under a running inference
            try:
                llm = self._models.pop(cache_key, None)
                meta = self.meta.pop(cache_key, None)
            finally:
                lock.release()
        if llm is not None:
            close = getattr(llm, "close", None)
            if callable(close):
                close()
            del llm
            self.unload_count += 1
            telemetry.event("model_unload", model=cache_key, reason=reason, size_mb=round((meta or {}).get("size_bytes", 0) / 1e6))
        return True

    def unload_except(self, keep: set[str]) -> None:
        for k in [k for k in self.resident() if k.split("|")[0] not in keep]:
            self.unload(k, reason="activation changed")

    def ensure_loaded(self, model: str) -> None:
        from .library import is_thinking

        m = self._resolve(model)
        self._load(m.key, m.file_path, thinking=is_thinking(m))

    # -- model management
    def _load(self, key: str, path: str, *, embedding: bool = False, n_ctx: int | None = None, thinking: bool = False) -> Any:
        from . import residency, telemetry

        cache_key = f"{key}|{'emb' if embedding else 'gen'}"
        with self._glock:
            if cache_key in self._models:
                self.meta[cache_key]["last_used"] = time.time()
                self.meta[cache_key]["uses"] += 1
                return self._models[cache_key]
            load_lock = self._load_locks.setdefault(cache_key, threading.Lock())
        with load_lock:  # concurrent requests for the same model load it once
            with self._glock:
                if cache_key in self._models:
                    self.meta[cache_key]["last_used"] = time.time()
                    return self._models[cache_key]
            try:
                from llama_cpp import Llama
            except Exception as e:  # pragma: no cover - depends on install
                raise ProviderUnavailable(f"llama-cpp-python not installed: {e}") from e
            st = state.load()
            threads = st["local"]["n_threads"] or max(1, (hardware.snapshot()["cpu"]["usable_cores"]))
            ctx = n_ctx or (512 if embedding else (max(st["local"]["n_ctx"], 8192) if thinking else st["local"]["n_ctx"]))
            cap = residency.policy().get("n_ctx_cap")
            if cap and not embedding:
                ctx = min(ctx, cap)
            size = os.path.getsize(path) if os.path.exists(path) else 0
            need = int(size * 1.1 + 0.25e9 * max(1, ctx / 4096))
            try:
                residency.make_room(self, need)
            except MemoryError as e:
                raise ProviderUnavailable(f"{key}: {e}") from e
            t0 = time.monotonic()
            try:
                llm = Llama(model_path=path, n_ctx=ctx, n_threads=threads, embedding=embedding, verbose=False)
            except Exception as e:
                self.last_error = f"load {key}: {e}"[:300]
                raise ProviderUnavailable(f"could not load local model {key}: {e}") from e
            ms = int((time.monotonic() - t0) * 1000)
            self.load_count += 1
            self.load_ms_total += ms
            with self._glock:
                self._models[cache_key] = llm
                self._locks.setdefault(cache_key, threading.Lock())
                self.meta[cache_key] = {"model": key, "kind": "embedding" if embedding else "generation", "size_bytes": size, "n_ctx": ctx,
                                        "loaded_at": time.time(), "last_used": time.time(), "uses": 1, "load_ms": ms}
            telemetry.event("model_load", model=cache_key, ms=ms, size_mb=round(size / 1e6), n_ctx=ctx, mode=residency.effective_mode())
            return llm

    def _resolve(self, model: str):
        from . import library

        if model in ("chat", "eco", "deep"):
            m = library.resolve(None, model)
        else:
            from .. import db as dbmod
            from ..models import LocalModel

            s = dbmod.SessionLocal()
            try:
                m = s.query(LocalModel).filter(LocalModel.key == model).first()
                if m:
                    s.expunge(m)
            finally:
                s.close()
        if m is None or m.status != "installed" or not m.file_path or not os.path.exists(m.file_path):
            raise ProviderUnavailable(f"local model {model!r} is not installed/active")
        return m

    # -- inference
    def _messages(self, m: Any, model: str, system: str, prompt: str, schema: dict | None) -> tuple[list[dict], bool]:
        """Thinking models reason only when serving the deep slot without a JSON schema; elsewhere Qwen3's
        documented '/no_think' switch keeps them fast."""
        from .library import is_thinking

        thinking_model = is_thinking(m)
        think = thinking_model and model == "deep" and schema is None
        user = prompt + (" /no_think" if thinking_model and not think else "")
        return [{"role": "system", "content": system}, {"role": "user", "content": user}], think

    @staticmethod
    def _chatml(llm: Any) -> bool:
        return "<|im_start|>" in str((getattr(llm, "metadata", None) or {}).get("tokenizer.chat_template", ""))

    def _think(self, llm: Any, m: Any, system: str, prompt: str, answer_tokens: int) -> tuple[str, str, bool, int, int]:
        """Two-phase reasoning with a hard thinking budget (the thinking-budget technique from the Qwen3 technical report):
        phase 1 thinks until </think> or the budget; if the budget is hit, the model is told to conclude and the
        answer is generated from the reasoning so far — flagged as incomplete, never presented as finished."""
        head = (f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n"
                f"<|im_start|>assistant\n<think>\n")
        r1 = llm.create_completion(prompt=head, max_tokens=thinking_budget(), temperature=0.6, top_p=0.95, stop=["</think>"])
        thought = r1["choices"][0]["text"]
        complete = r1["choices"][0].get("finish_reason") == "stop"
        if not complete:
            thought = thought.rstrip() + ("\n\nConsidering the limited time, I have to give the solution based on the "
                                          "thinking directly now.\n")
        r2 = llm.create_completion(prompt=head + thought + "</think>\n\n", max_tokens=answer_tokens, temperature=0.6, top_p=0.95,
                                   stop=["<|im_end|>", "<|endoftext|>"])
        answer = THINK.sub("", r2["choices"][0]["text"]).strip()
        if r2["choices"][0].get("finish_reason") == "length" and answer:
            answer += "\n\n[answer cut off at the token limit]"  # visible, never silently truncated
        u1, u2 = r1.get("usage") or {}, r2.get("usage") or {}
        return answer, thought.strip(), complete, int(u1.get("prompt_tokens", 0)), int(u1.get("completion_tokens", 0)) + int(u2.get("completion_tokens", 0))

    def complete(self, *, model: str, system: str, prompt: str, schema: dict | None, effort: str, max_tokens: int) -> Completion:
        from .library import is_thinking

        m = self._resolve(model)
        llm = self._load(m.key, m.file_path, thinking=is_thinking(m))
        messages, think = self._messages(m, model, system, prompt, schema)
        cap = int(os.getenv("DAEMON_LOCAL_MAX_TOKENS", "1024"))
        answer_tokens = min(max_tokens, cap)  # max_tokens is the caller's budget for the ANSWER
        t0 = time.monotonic()
        if think and self._chatml(llm):
            with self._locks[f"{m.key}|gen"]:
                try:
                    text, reasoning, complete, p_tok, c_tok = self._think(llm, m, system, prompt, answer_tokens)
                except Exception as e:
                    self.last_error = str(e)[:300]
                    raise ProviderUnavailable(f"local reasoning failed: {e}") from e
            if not text:
                raise ProviderUnavailable(f"{m.key}: no answer after reasoning")
            return Completion(text, None, "local", m.key, p_tok, c_tok, 0.0, int((time.monotonic() - t0) * 1000), 0, reasoning,
                              not complete)
        kwargs: dict[str, Any] = {"messages": messages, "max_tokens": answer_tokens + (thinking_budget() if think else 0),
                                  "temperature": 0.6 if think else 0.2}
        if _DETERMINISTIC.get():
            kwargs.update(temperature=0.0, top_k=1, seed=EVAL_SEED)
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object", "schema": schema}
        with self._locks[f"{m.key}|gen"]:
            try:
                r = llm.create_chat_completion(**kwargs)
            except Exception as e:
                self.last_error = str(e)[:300]
                raise ProviderUnavailable(f"local inference failed: {e}") from e
        raw = r["choices"][0]["message"].get("content") or ""
        text, reasoning, finished = split_thinking(raw)
        u = r.get("usage") or {}
        if not finished or (think and not text):
            # never hand back half a thought as an answer; the router falls through to the next candidate
            raise ProviderUnavailable(f"{m.key}: thinking budget exhausted before an answer")
        return Completion(text, _parse_json(text, schema), "local", m.key, int(u.get("prompt_tokens", 0)),
                          int(u.get("completion_tokens", 0)), 0.0, int((time.monotonic() - t0) * 1000), 0, reasoning)

    def stream(self, *, model: str, system: str, prompt: str, effort: str, max_tokens: int) -> Iterator[str]:
        from .library import is_thinking

        m = self._resolve(model)
        messages, think = self._messages(m, model, system, prompt, None)
        if think:  # reasoning is not streamed; the answer arrives once the model has finished thinking
            yield self.complete(model=model, system=system, prompt=prompt, schema=None, effort=effort, max_tokens=max_tokens).text
            return
        llm = self._load(m.key, m.file_path, thinking=is_thinking(m))
        with self._locks[f"{m.key}|gen"]:
            for chunk in llm.create_chat_completion(messages=messages, max_tokens=min(max_tokens, int(os.getenv("DAEMON_LOCAL_MAX_TOKENS", "1024"))),
                                                    temperature=0.2, stream=True):
                delta = chunk["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield THINK.sub("", delta) if "</think>" in delta else delta.replace("<think>", "")

    def embed(self, texts: list[str], kind: str = "document") -> tuple[str, list[list[float]]]:
        m = self._resolve_embedding()
        extra = catalog.BY_KEY[m.key].extra if m.key in catalog.BY_KEY else {}
        prefix = extra.get("query_prefix" if kind == "query" else "doc_prefix", "")
        llm = self._load(m.key, m.file_path, embedding=True, n_ctx=min(m.context_length or 512, 2048))
        out: list[list[float]] = []
        lock = self._locks[f"{m.key}|emb"]
        for t in texts:
            # lock per text, not per batch: a background re-embed of a large document must not make an interactive
            # query wait for 64 chunks (measured: 22.5 s search during an upgrade vs 0.18–0.42 s without it)
            with lock:
                v = llm.embed(prefix + t[:6000])
            if v and isinstance(v[0], list):  # token-level output → mean-pool
                v = [sum(col) / len(v) for col in zip(*v, strict=True)]
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([round(x / n, 6) for x in v])
        return f"gguf:{m.key}", out

    def _resolve_embedding(self):
        from . import library

        m = library.resolve(None, "embedding")
        if m is None:
            raise ProviderUnavailable("no local embedding model active")
        return m


class OpenAICompatProvider:
    """An OpenAI-compatible server you control (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`)."""

    def __init__(self, pid: str, base_url: str, *, api_key: str | None = None, client: httpx.Client | None = None) -> None:
        self.id = pid
        self.base_url = base_url.rstrip("/")
        self.locality = locality_of_url(self.base_url)
        self._key = api_key
        self._client = client

    @property
    def http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=float(os.getenv("WORKER_TIMEOUT_S", "120")))
        return self._client

    def configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}"} if self._key else {}

    def health(self) -> dict[str, Any]:
        try:
            r = self.http.get(f"{self.base_url}/v1/models", headers=self._headers(), timeout=5)
            r.raise_for_status()
            return {"configured": True, "reachable": True, "locality": self.locality, "models": [m.get("id") for m in r.json().get("data", [])]}
        except httpx.HTTPError as e:
            return {"configured": True, "reachable": False, "locality": self.locality, "error": str(e)[:200]}

    def complete(self, *, model: str, system: str, prompt: str, schema: dict | None, effort: str, max_tokens: int) -> Completion:
        body: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "temperature": 0.2,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if schema is not None:
            body["response_format"] = {"type": "json_object"}
        t0 = time.monotonic()
        try:
            r = self.http.post(f"{self.base_url}/v1/chat/completions", json=body, headers=self._headers())
            if r.status_code == 429:
                raise ProviderUnavailable(f"{self.id}: rate limited (429)")
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"{self.id}: {e}") from e
        d = r.json()
        text = d["choices"][0]["message"].get("content") or ""
        u = d.get("usage") or {}
        return Completion(text, _parse_json(text, schema), self.id, d.get("model", model), int(u.get("prompt_tokens", 0)),
                          int(u.get("completion_tokens", 0)), 0.0, int((time.monotonic() - t0) * 1000))

    def stream(self, *, model: str, system: str, prompt: str, effort: str, max_tokens: int) -> Iterator[str]:
        c = self.complete(model=model, system=system, prompt=prompt, schema=None, effort=effort, max_tokens=max_tokens)
        yield c.text


_local: LocalLlamaProvider | None = None


def get_local() -> LocalLlamaProvider:
    global _local
    if _local is None:
        _local = LocalLlamaProvider()
    return _local


def local_embedder() -> tuple[str, Any] | None:
    """(model_id, embed(texts, kind)) for the active local embedding model, or None."""
    if not hardware.runtime_available().get("llama_cpp"):
        return None
    from . import library

    m = library.resolve(None, "embedding")
    if m is None:
        return None
    prov = get_local()

    def embed(texts: list[str], kind: str = "document") -> list[list[float]]:
        return prov.embed(texts, kind)[1]

    return f"gguf:{m.key}", embed
