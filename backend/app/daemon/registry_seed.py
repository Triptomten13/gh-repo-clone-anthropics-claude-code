"""Initial provider registry. Facts carry their source; anything not verified from an official source is "unknown".
No free tier, quota or price is recorded for a provider until someone verifies it from that provider's own documentation."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import ProviderRecord

UNKNOWN = "unknown — not verified from official documentation"
BUILD_DATE = datetime(2026, 11, 5, tzinfo=UTC)

SEED: list[dict[str, Any]] = [
    {"id": "local-llamacpp", "name": "llama.cpp in-process (llama-cpp-python)", "kind": "local_runtime",
     "website": "https://github.com/abetlen/llama-cpp-python", "docs_url": "https://llama-cpp-python.readthedocs.io",
     "facts": {"license": "MIT (llama-cpp-python package metadata, checked 2026-11-05)", "api_cost": "none — runs on own hardware",
               "rate_limits": "none; bounded by CPU/RAM", "data_leaves_machine": False, "registration": "none"},
     "adapter": True, "status": "operational", "last_verified_at": BUILD_DATE, "verified_by": "build: installed package metadata"},
    {"id": "ollama", "name": "Ollama (local server)", "kind": "local_runtime", "website": "https://ollama.com",
     "facts": {"license": UNKNOWN, "api_cost": "none — runs on own hardware", "data_leaves_machine": "no, when bound to localhost/LAN"},
     "adapter": True, "status": "unverified"},
    {"id": "openai-compatible", "name": "OpenAI-compatible worker (llama.cpp server, vLLM, LM Studio …)", "kind": "local_runtime",
     "facts": {"note": "Generic adapter for endpoints you run yourself; licence depends on the server you choose."},
     "adapter": True, "status": "operational"},
    {"id": "huggingface-hub", "name": "Hugging Face Hub (model source)", "kind": "model_hub", "website": "https://huggingface.co",
     "docs_url": "https://huggingface.co/docs/hub",
     "facts": {"use": "download of open-weight GGUF files; licence taken from each repository's model-card metadata",
               "inference": "not used — no hosted inference is called"},
     "adapter": True, "status": "operational", "last_verified_at": BUILD_DATE, "verified_by": "build: Hub API used for licence + checksum"},
    {"id": "anthropic", "name": "Anthropic Claude API", "kind": "api", "website": "https://www.anthropic.com",
     "docs_url": "https://platform.claude.com/docs", "pricing_url": "https://platform.claude.com/docs/en/about-claude/pricing",
     "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
     "facts": {"pricing_usd_per_mtok": {"claude-opus-5-5": [4.0, 20.0], "claude-sonnet-5-5": [2.0, 10.0], "claude-haiku-5-5": [0.10, 0.50]},
               "pricing_source": "Anthropic model table as cached in the claude-api reference (2026-10-06)",
               "prompt_cache": "cache writes ≈1.25× input price, cache reads ≈0.1× input price",
               "free_tier": "none recorded — not assumed", "rate_limits": "organisation limits by usage tier — see official rate-limits page; not tracked numerically here",
               "rate_limits_url": "https://platform.claude.com/docs/en/api/rate-limits", "data_leaves_machine": True,
               "registration": "account owner must create the account and accept the terms"},
     "adapter": True, "status": "operational", "last_verified_at": BUILD_DATE, "verified_by": "build: claude-api reference (cached 2026-10-06)"},
]
DISCOVERED = [("openai", "OpenAI API", "https://openai.com"), ("google-gemini", "Google Gemini API", "https://ai.google.dev"),
              ("mistral", "Mistral AI", "https://mistral.ai"), ("groq", "Groq", "https://groq.com"),
              ("openrouter", "OpenRouter", "https://openrouter.ai"), ("together", "Together AI", "https://www.together.ai"),
              ("cohere", "Cohere", "https://cohere.com")]


def seed(db: Session) -> None:
    for e in SEED:
        if db.get(ProviderRecord, e["id"]) is None:
            db.add(ProviderRecord(**{k: v for k, v in e.items()}))
    for pid, name, site in DISCOVERED:
        if db.get(ProviderRecord, pid) is None:
            db.add(ProviderRecord(id=pid, name=name, kind="api", website=site, adapter=False, status="unverified",
                                  facts={k: UNKNOWN for k in ("free_tier", "rate_limits", "token_limits", "commercial_use", "privacy",
                                                               "geographic_restrictions", "registration")},
                                  notes="Discovered candidate, no adapter. Nothing about free tiers, quotas, prices or terms is recorded "
                                        "until verified from the provider's official documentation."))
    db.flush()
