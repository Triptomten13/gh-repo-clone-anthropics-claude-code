"""Provider adapters behind one internal interface.

Each adapter speaks its provider's own API — no provider is assumed to share
another's request shape. Adapters raise:
  ProviderUnavailable – not configured / unreachable / circuit open → router may fall back
  LLMRefused          – the model declined → never silently re-routed to another provider
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from . import registry


class ProviderUnavailable(RuntimeError):
    pass


class LLMRefused(RuntimeError):
    pass


@dataclass
class Completion:
    text: str
    data: Any | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class Provider(Protocol):
    id: str

    def configured(self) -> bool: ...
    def health(self) -> dict[str, Any]: ...
    def complete(self, *, model: str, system: str, prompt: str, schema: dict | None, effort: str, max_tokens: int) -> Completion: ...
    def stream(self, *, model: str, system: str, prompt: str, effort: str, max_tokens: int) -> Iterator[str]: ...


def _parse_json(text: str, schema: dict | None) -> Any | None:
    if schema is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"model returned invalid JSON: {e}") from e


# ----------------------------------------------------------------------------- Anthropic
class AnthropicProvider:
    id = "anthropic"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def configured(self) -> bool:
        return self._client is not None or bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self.configured():
                raise ProviderUnavailable("ANTHROPIC_API_KEY not set")
            import anthropic

            self._client = anthropic.Anthropic(timeout=float(os.getenv("ANTHROPIC_TIMEOUT_S", "300")), max_retries=2)
        return self._client

    def health(self) -> dict[str, Any]:
        # No free "ping" endpoint is assumed; configuration is reported and live status comes from recent calls.
        return {"configured": self.configured(), "check": "configuration only — live status from recent calls"}

    def complete(self, *, model: str, system: str, prompt: str, schema: dict | None, effort: str, max_tokens: int) -> Completion:
        output_config: dict[str, Any] = {"effort": effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        kwargs: dict[str, Any] = dict(model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": prompt}],
                                      thinking={"type": "adaptive"}, output_config=output_config)
        t0 = time.monotonic()
        try:
            import anthropic

            try:
                if model in ("claude-opus-5-5", "claude-sonnet-5-5"):
                    resp = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
                else:
                    resp = self.client.messages.create(**kwargs)
            except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
                raise ProviderUnavailable(f"anthropic: {type(e).__name__}: {e}") from e
        except ImportError as e:  # pragma: no cover
            raise ProviderUnavailable("anthropic SDK not installed") from e
        if resp.stop_reason == "refusal":
            raise LLMRefused(f"model declined the request ({getattr(resp, 'stop_details', None)})")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        spec = registry.find("anthropic", model)
        u = resp.usage
        return Completion(text, _parse_json(text, schema), "anthropic", resp.model, u.input_tokens, u.output_tokens,
                          spec.cost(u.input_tokens, u.output_tokens) if spec else 0.0, int((time.monotonic() - t0) * 1000))

    def stream(self, *, model: str, system: str, prompt: str, effort: str, max_tokens: int) -> Iterator[str]:
        with self.client.messages.stream(model=model, max_tokens=max_tokens, system=system, thinking={"type": "adaptive"},
                                         output_config={"effort": effort}, messages=[{"role": "user", "content": prompt}]) as s:
            yield from s.text_stream


# ----------------------------------------------------------------------------- Ollama (local)
class OllamaProvider:
    """Local models through Ollama's HTTP API (/api/chat, /api/embed, /api/tags)."""

    id = "ollama"

    def __init__(self, client: httpx.Client | None = None, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "")).rstrip("/")
        self._client = client

    def configured(self) -> bool:
        return bool(self.base_url)

    @property
    def http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=float(os.getenv("OLLAMA_TIMEOUT_S", "120")))
        return self._client

    def _post(self, path: str, body: dict) -> httpx.Response:
        if not self.configured():
            raise ProviderUnavailable("OLLAMA_BASE_URL not set")
        try:
            r = self.http.post(f"{self.base_url}{path}", json=body)
            r.raise_for_status()
            return r
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"ollama: {e}") from e

    def health(self) -> dict[str, Any]:
        if not self.configured():
            return {"configured": False}
        try:
            r = self.http.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            return {"configured": True, "reachable": True, "models": [m.get("name") for m in r.json().get("models", [])]}
        except httpx.HTTPError as e:
            return {"configured": True, "reachable": False, "error": str(e)[:200]}

    def complete(self, *, model: str, system: str, prompt: str, schema: dict | None, effort: str, max_tokens: int) -> Completion:
        body: dict[str, Any] = {"model": model, "stream": False, "options": {"num_predict": max_tokens},
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if schema is not None:
            body["format"] = schema
        t0 = time.monotonic()
        d = self._post("/api/chat", body).json()
        text = (d.get("message") or {}).get("content", "")
        return Completion(text, _parse_json(text, schema), "ollama", model, int(d.get("prompt_eval_count", 0)), int(d.get("eval_count", 0)),
                          0.0, int((time.monotonic() - t0) * 1000))

    def stream(self, *, model: str, system: str, prompt: str, effort: str, max_tokens: int) -> Iterator[str]:
        body = {"model": model, "stream": True, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if not self.configured():
            raise ProviderUnavailable("OLLAMA_BASE_URL not set")
        with self.http.stream("POST", f"{self.base_url}/api/chat", json=body) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.strip():
                    chunk = json.loads(line)
                    if (chunk.get("message") or {}).get("content"):
                        yield chunk["message"]["content"]

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        d = self._post("/api/embed", {"model": model, "input": texts}).json()
        return d["embeddings"]


# ----------------------------------------------------------------------------- embeddings
TOKEN = re.compile(r"[a-zåäöæøéüß0-9]+", re.I)
STOP = {"the", "and", "of", "to", "a", "in", "is", "it", "that", "for", "on", "with", "as", "was", "be", "by", "this", "are", "or", "an",
        "och", "att", "det", "som", "en", "på", "är", "av", "för", "med", "till", "den", "har", "de", "inte", "om", "ett", "i"}


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text) if t.lower() not in STOP and len(t) > 1]


class LocalHashEmbedder:
    """Feature-hashed word + bigram vectors, L2-normalised. Deterministic, offline, lexical."""

    id = "local-hash-256"
    dims = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dims
            toks = tokenize(t)
            feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
            for f in feats:
                h = int(hashlib.md5(f.encode(), usedforsecurity=False).hexdigest()[:8], 16)
                v[h % self.dims] += 1.0 if (h >> 9) & 1 else -1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([round(x / n, 5) for x in v])
        return out


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))
