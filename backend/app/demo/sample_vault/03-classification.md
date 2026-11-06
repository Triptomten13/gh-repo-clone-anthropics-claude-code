title: Data classification and model routing
classification: PUBLIC
evidence_class: primary_source
description: Platform documentation — which models may see which data (from docs/CONTROL_PLANE.md)
---
# Data classification and model routing

Documents in the Knowledge Vault carry a classification: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED or
HIGHLY_SENSITIVE. Access is checked before any passage is scored or placed in a model context, so retrieval never
returns a passage the requesting person or agent may not read.

The highest classification among the retrieved passages decides which models may process them. PUBLIC and INTERNAL
data may go to any permitted provider. CONFIDENTIAL data stays on local models or self-hosted workers on the private
network. RESTRICTED data stays on this machine's models. HIGHLY_SENSITIVE data is processed only by in-process local
models. A failing local model never falls back to a destination the classification excludes.

In offline mode no external provider, research API or download is ever used — not even as a fallback. The public demo
always runs in offline mode, so no visitor can cause an external call or spend money.
