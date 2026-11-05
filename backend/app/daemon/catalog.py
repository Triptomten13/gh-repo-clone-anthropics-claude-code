"""Curated local-model candidates.

Each entry was checked against the Hugging Face Hub API on 2026-11-05:
licence = the repository's own model-card metadata (`cardData.license`, matching the `license:` tag),
sha256/size = the file's Git-LFS object id and size from `/api/models/<repo>/tree/main`.
The installer re-checks both against the live Hub before downloading and refuses on any mismatch.
Open weights are not automatically unrestricted: commercial use is marked "permitted" only for
known permissive licences (attribution/NOTICE duties still apply) and "review_required" otherwise.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PERMISSIVE = {"apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause"}
TRUSTED_HOSTS = ("huggingface.co",)
CATALOG_VERIFIED_AT = "2026-11-05"


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    display_name: str
    family: str
    kind: str  # chat | embedding
    parameters: str
    quantization: str
    repo: str
    file: str
    license: str
    sha256: str
    size_bytes: int
    context_length: int
    languages: tuple[str, ...]
    capabilities: tuple[str, ...]
    suggested_slot: str  # chat | eco | embedding
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/main/{self.file}"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["url"] = self.url
        d["commercial_use"] = commercial_use(self.license)
        return d


def commercial_use(license_id: str) -> str:
    return "permitted" if (license_id or "").lower() in PERMISSIVE else "review_required"


CATALOG: list[CatalogEntry] = [
    CatalogEntry("qwen2.5-1.5b-instruct-q4_k_m", "Qwen2.5 1.5B Instruct (Q4_K_M)", "qwen2.5", "chat", "1.5B", "Q4_K_M",
                 "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "qwen2.5-1.5b-instruct-q4_k_m.gguf", "apache-2.0",
                 "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e", 1117320736, 32768,
                 ("multilingual", "en", "sv"), ("text", "structured_output", "streaming"), "chat",
                 "Primary CPU chat model. Multilingual (Swedish quality is modest — measure with the benchmark)."),
    CatalogEntry("qwen2.5-0.5b-instruct-q4_k_m", "Qwen2.5 0.5B Instruct (Q4_K_M)", "qwen2.5", "chat", "0.5B", "Q4_K_M",
                 "Qwen/Qwen2.5-0.5B-Instruct-GGUF", "qwen2.5-0.5b-instruct-q4_k_m.gguf", "apache-2.0",
                 "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db", 491400032, 32768,
                 ("multilingual", "en"), ("text", "structured_output", "streaming"), "eco",
                 "Small/fast model for classification, extraction and ECO/EMERGENCY profiles."),
    CatalogEntry("smollm2-360m-instruct-q8_0", "SmolLM2 360M Instruct (Q8_0)", "smollm2", "chat", "360M", "Q8_0",
                 "HuggingFaceTB/SmolLM2-360M-Instruct-GGUF", "smollm2-360m-instruct-q8_0.gguf", "apache-2.0",
                 "48ab3034d0dd401fbc721eb1df3217902fee7dab9078992d66431f09b7750201", 386404992, 8192,
                 ("en",), ("text", "streaming"), "chat",
                 "Different model family — used to prove model replacement (Independence Test C). English only."),
    CatalogEntry("smollm2-1.7b-instruct-q4_k_m", "SmolLM2 1.7B Instruct (Q4_K_M)", "smollm2", "chat", "1.7B", "Q4_K_M",
                 "HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF", "smollm2-1.7b-instruct-q4_k_m.gguf", "apache-2.0",
                 "decd2598bc2c8ed08c19adc3c8fdd461ee19ed5708679d1c54ef54a5a30d4f33", 1055609536, 8192,
                 ("en",), ("text", "streaming"), "chat", "Alternative English chat model."),
    CatalogEntry("nomic-embed-text-v1.5-q8_0", "nomic-embed-text v1.5 (Q8_0)", "nomic-bert", "embedding", "137M", "Q8_0",
                 "nomic-ai/nomic-embed-text-v1.5-GGUF", "nomic-embed-text-v1.5.Q8_0.gguf", "apache-2.0",
                 "3e24342164b3d94991ba9692fdc0dd08e3fd7362e0aacc396a9a5c54a544c3b7", 146146432, 2048,
                 ("en",), ("embeddings",), "embedding",
                 "768-d semantic embeddings; needs 'search_document: ' / 'search_query: ' prefixes (handled by the runtime).",
                 {"doc_prefix": "search_document: ", "query_prefix": "search_query: "}),
    CatalogEntry("bge-small-en-v1.5-q8_0", "BGE small en v1.5 (Q8_0)", "bert", "embedding", "33M", "Q8_0",
                 "CompendiumLabs/bge-small-en-v1.5-gguf", "bge-small-en-v1.5-q8_0.gguf", "mit",
                 "ec38e8da142596baa913124ae50550de284b6916bf59577ef2f0cb9660c2f514", 36806944, 512,
                 ("en",), ("embeddings",), "embedding", "Tiny 384-d embedder for very constrained machines.",
                 {"doc_prefix": "", "query_prefix": "Represent this sentence for searching relevant passages: "}),
]
BY_KEY = {e.key: e for e in CATALOG}
