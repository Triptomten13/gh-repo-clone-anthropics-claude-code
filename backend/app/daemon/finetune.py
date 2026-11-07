"""Fine-tuning lab — feasibility first. Nothing trains unless hardware, dependencies, data and consent all exist."""
from __future__ import annotations

from typing import Any

from . import hardware


def feasibility() -> dict[str, Any]:
    snap = hardware.snapshot()
    deps = {}
    for mod in ("torch", "peft", "transformers"):
        try:
            __import__(mod)
            deps[mod] = True
        except Exception:
            deps[mod] = False
    gpu = bool(snap["gpus"])
    ram_gb = snap["ram_total_bytes"] / 1e9
    blockers = []
    if not all(deps.values()):
        blockers.append(f"missing training libraries: {', '.join(k for k, v in deps.items() if not v)}")
    if not gpu:
        blockers.append("no GPU — LoRA on CPU is only conceivable for sub-1B models and would be very slow; not offered")
    return {
        "foundation_model_training": {"feasible": False, "reason": "requires large GPU clusters, budget and curated data that do not exist here"},
        "full_fine_tune": {"feasible": False, "reason": "no GPU" if not gpu else "not evaluated"},
        "lora_adapter": {"feasible": gpu and all(deps.values()) and ram_gb >= 16, "blockers": blockers},
        "alternatives_available_now": ["versioned prompts (Prompt engine)", "retrieval over the Archive", "few-shot examples in prompts",
                                       "model selection by benchmark"],
        "hardware": {"gpus": snap["gpus"], "ram_total_gb": round(ram_gb, 1), "cpu": snap["cpu"]["model"]},
        "dependencies": deps,
        "data_policy": "private user data is never used for training without explicit, recorded consent",
    }
