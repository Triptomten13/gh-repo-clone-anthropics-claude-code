"""Internet intelligence: the internet as an external knowledge environment, used deliberately.

http      one instrumented client: pooling, per-host rate limits, backoff, conditional requests, robots.txt, size caps
sources   official APIs (Wikipedia, arXiv, Crossref, GitHub, HN Algolia, PyPI, OSV, NVD, Hugging Face, RSS) + keyed web search
research  QUICK / STANDARD / DEEP research with ranking, extraction, contradiction flags, citations and a research cache
monitor   scheduled change detection for approved subjects
All retrieved text is untrusted data: it is wrapped before any model sees it and never changes instructions or permissions.
"""
