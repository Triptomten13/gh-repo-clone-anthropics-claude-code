"""Model registry: what each configured model is, what it can do, and what it costs.

Only facts we can stand behind are recorded. Anthropic pricing/context comes from
Anthropic's published model table (cached 2026-10). Local (Ollama) models have no
API price — they run on your own hardware, which is not "free". Capabilities are
never inferred across providers: each entry lists its own.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

CAPABILITIES = ("text", "streaming", "tool_use", "structured_output", "vision", "long_context", "thinking", "embeddings", "audio")


@dataclass
class ModelSpec:
    provider: str
    model_id: str
    display_name: str
    capabilities: tuple[str, ...]
    context_window: int | None
    max_output_tokens: int | None
    input_usd_per_mtok: float | None
    output_usd_per_mtok: float | None
    intended_use: str
    tiers: tuple[str, ...] = ()
    notes: str = ""
    evaluations: list[dict[str, Any]] = field(default_factory=list)

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        if self.input_usd_per_mtok is None or self.output_usd_per_mtok is None:
            return 0.0
        return round(input_tokens / 1e6 * self.input_usd_per_mtok + output_tokens / 1e6 * self.output_usd_per_mtok, 6)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["capabilities"] = list(self.capabilities)
        d["tiers"] = list(self.tiers)
        return d


ANTHROPIC = [
    ModelSpec("anthropic", "claude-opus-5-5", "Claude Opus 5.5", ("text", "streaming", "tool_use", "structured_output", "vision", "long_context", "thinking"),
              1_000_000, 128_000, 4.00, 20.00, "deep reasoning, orchestration, complex creative work", ("deep",),
              "Adaptive thinking only (no budget_tokens); default effort medium."),
    ModelSpec("anthropic", "claude-sonnet-5-5", "Claude Sonnet 5.5", ("text", "streaming", "tool_use", "structured_output", "vision", "long_context", "thinking"),
              1_000_000, 128_000, 2.00, 10.00, "everyday agent work, drafting, analysis", ("standard",)),
    ModelSpec("anthropic", "claude-haiku-5-5", "Claude Haiku 5.5", ("text", "streaming", "tool_use", "structured_output", "vision", "long_context"),
              1_000_000, 128_000, 0.10, 0.50, "fast classification, extraction, cheap sub-tasks", ("fast",),
              "Price shown is for prompts up to 100K tokens; longer prompts cost $0.50 / $2.50 per MTok."),
]
LOCAL_HASH = ModelSpec("local", "local-hash-256", "Local hashing embedder (256-d)", ("embeddings",), None, None, 0.0, 0.0,
                       "always-available lexical embeddings for hybrid search; replace with a real embedding model for true semantic recall",
                       notes="Feature-hashed word/bigram vectors. Lexical similarity, not deep semantics.")


def _ollama_specs() -> list[ModelSpec]:
    out = []
    for m in [x.strip() for x in os.getenv("OLLAMA_MODELS", "").split(",") if x.strip()]:
        out.append(ModelSpec("ollama", m, f"{m} (local)", ("text", "streaming", "structured_output"), None, None, 0.0, 0.0,
                             "local inference on your hardware", ("local",), "No API cost; capability/context depend on the model you pulled."))
    emb = os.getenv("OLLAMA_EMBED_MODEL", "").strip()
    if emb:
        out.append(ModelSpec("ollama", emb, f"{emb} (local embeddings)", ("embeddings",), None, None, 0.0, 0.0, "local semantic embeddings"))
    return out


def all_models() -> list[ModelSpec]:
    return [*ANTHROPIC, *_ollama_specs(), LOCAL_HASH]


def find(provider: str, model_id: str) -> ModelSpec | None:
    return next((m for m in all_models() if m.provider == provider and m.model_id == model_id), None)


def tier_chain(tier: str) -> list[tuple[str, str]]:
    """Ordered (provider, model) candidates for a tier. Override with MODEL_CHAIN_<TIER>='anthropic:claude-opus-5-5,ollama:llama3.1'."""
    env = os.getenv(f"MODEL_CHAIN_{tier.upper()}")
    if env:
        return [tuple(x.split(":", 1)) for x in env.split(",") if ":" in x]  # type: ignore[misc]
    model = os.getenv({"deep": "MODEL_DEEP", "standard": "MODEL_STANDARD", "fast": "MODEL_FAST"}.get(tier, "MODEL_STANDARD"),
                      {"deep": "claude-opus-5-5", "standard": "claude-sonnet-5-5", "fast": "claude-haiku-5-5"}.get(tier, "claude-sonnet-5-5"))
    chain = [("anthropic", model)]
    local = [m.model_id for m in _ollama_specs() if "text" in m.capabilities]
    if local:  # local model as last-resort fallback when configured
        chain.append(("ollama", local[0]))
    return chain
