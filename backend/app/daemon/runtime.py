"""Local inference adapters.

LocalLlamaProvider   in-process llama.cpp (llama-cpp-python) over GGUF files from the model library.
                     No network listener of its own — it is reachable only through the authenticated API.
OpenAICompatProvider any OpenAI-compatible endpoint you run (llama.cpp server, vLLM, LM Studio …),
                     used for registered DAEMON workers on other machines.
LocalGGUFEmbedder    semantic embeddings from the active embedding model.
"""
from __future__ import annotations

import ipaddress
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import httpx

from ..ai.providers import Completion, ProviderUnavailable, _parse_json
from . import catalog, hardware, state


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
    MAX_LOADED = int(os.getenv("DAEMON_MAX_LOADED_MODELS", "2"))

    def __init__(self) -> None:
        self._models: OrderedDict[str, Any] = OrderedDict()
        self._locks: dict[str, threading.Lock] = {}
        self._glock = threading.Lock()
        self.last_error: str | None = None

    # -- availability
    def configured(self) -> bool:
        if not hardware.runtime_available().get("llama_cpp"):
            return False
        from . import library

        return library.resolve(None, "chat") is not None

    def health(self) -> dict[str, Any]:
        from . import library

        chat, eco, emb = (library.resolve(None, s) for s in ("chat", "eco", "embedding"))
        return {"configured": self.configured(), "runtime": hardware.runtime_available(), "loaded": list(self._models),
                "chat_model": chat.key if chat else None, "eco_model": eco.key if eco else None,
                "embedding_model": emb.key if emb else None, "network_listener": False, "last_error": self.last_error}

    # -- model management
    def _load(self, key: str, path: str, *, embedding: bool = False, n_ctx: int | None = None) -> Any:
        cache_key = f"{key}|{'emb' if embedding else 'gen'}"
        with self._glock:
            if cache_key in self._models:
                self._models.move_to_end(cache_key)
                return self._models[cache_key]
        try:
            from llama_cpp import Llama
        except Exception as e:  # pragma: no cover - depends on install
            raise ProviderUnavailable(f"llama-cpp-python not installed: {e}") from e
        st = state.load()
        threads = st["local"]["n_threads"] or max(1, (hardware.snapshot()["cpu"]["usable_cores"]))
        ctx = n_ctx or (512 if embedding else st["local"]["n_ctx"])
        try:
            llm = Llama(model_path=path, n_ctx=ctx, n_threads=threads, embedding=embedding, verbose=False)
        except Exception as e:
            self.last_error = f"load {key}: {e}"[:300]
            raise ProviderUnavailable(f"could not load local model {key}: {e}") from e
        with self._glock:
            self._models[cache_key] = llm
            self._locks.setdefault(cache_key, threading.Lock())
            while len(self._models) > self.MAX_LOADED:
                old, _ = self._models.popitem(last=False)
                self._locks.pop(old, None)
        return llm

    def unload_except(self, keep: set[str]) -> None:
        with self._glock:
            for k in [k for k in self._models if k.split("|")[0] not in keep]:
                self._models.pop(k, None)

    def _resolve(self, model: str):
        from . import library

        if model in ("chat", "eco"):
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
    def complete(self, *, model: str, system: str, prompt: str, schema: dict | None, effort: str, max_tokens: int) -> Completion:
        m = self._resolve(model)
        llm = self._load(m.key, m.file_path)
        kwargs: dict[str, Any] = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                                  "max_tokens": min(max_tokens, int(os.getenv("DAEMON_LOCAL_MAX_TOKENS", "1024"))),
                                  "temperature": 0.2}
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object", "schema": schema}
        t0 = time.monotonic()
        with self._locks[f"{m.key}|gen"]:
            try:
                r = llm.create_chat_completion(**kwargs)
            except Exception as e:
                self.last_error = str(e)[:300]
                raise ProviderUnavailable(f"local inference failed: {e}") from e
        text = r["choices"][0]["message"].get("content") or ""
        u = r.get("usage") or {}
        return Completion(text, _parse_json(text, schema), "local", m.key, int(u.get("prompt_tokens", 0)),
                          int(u.get("completion_tokens", 0)), 0.0, int((time.monotonic() - t0) * 1000))

    def stream(self, *, model: str, system: str, prompt: str, effort: str, max_tokens: int) -> Iterator[str]:
        m = self._resolve(model)
        llm = self._load(m.key, m.file_path)
        with self._locks[f"{m.key}|gen"]:
            for chunk in llm.create_chat_completion(messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                                                    max_tokens=min(max_tokens, int(os.getenv("DAEMON_LOCAL_MAX_TOKENS", "1024"))),
                                                    temperature=0.2, stream=True):
                delta = chunk["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield delta

    def embed(self, texts: list[str], kind: str = "document") -> tuple[str, list[list[float]]]:
        m = self._resolve_embedding()
        extra = catalog.BY_KEY[m.key].extra if m.key in catalog.BY_KEY else {}
        prefix = extra.get("query_prefix" if kind == "query" else "doc_prefix", "")
        llm = self._load(m.key, m.file_path, embedding=True, n_ctx=min(m.context_length or 512, 2048))
        out: list[list[float]] = []
        with self._locks[f"{m.key}|emb"]:
            for t in texts:
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
