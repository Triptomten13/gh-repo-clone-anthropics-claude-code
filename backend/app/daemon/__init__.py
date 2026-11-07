"""DAEMON CORE — Demonkoncernen AB's self-hosted AI infrastructure.

hardware   what this machine can actually run
catalog    curated, licence-checked model candidates
library    install / verify / activate / roll back / remove local models
runtime    local inference adapters (llama.cpp in-process, OpenAI-compatible workers)
state      persisted operating settings: offline mode, execution profile, limits
policy     which provider/model may serve a request (offline, privacy, spend, quota)
gateway    the single entry point for internal AI calls (cache, tracing, energy estimate)
"""
