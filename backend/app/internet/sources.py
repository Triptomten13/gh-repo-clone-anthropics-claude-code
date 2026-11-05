"""Source connectors over OFFICIAL APIs. Each returns normalised items:
{source, url, title, text, published_at (ISO or None), reliability, license_note, id}.

Reliability tiers describe the KIND of source, not whether a given claim is true:
  primary   — the authority for its own subject (a paper's own abstract, a CVE record, a package's registry entry)
  secondary — reporting about something (news)
  tertiary  — compiled or community summaries (encyclopedia, discussion aggregators)
Reachability checked 2026-11-05 from the dev host: all below answered except OpenAlex (rate-limited, not used).
General web search needs an API key (Brave Search API adapter); it is off until an owner-authorised key is stored.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # noqa: S405 - Python ≥3.7.1 expat mitigates entity-expansion attacks; inputs are size-capped
from typing import Any

from .http import FetchError, get_json, request

Item = dict[str, Any]


def _clean(s: str | None, n: int = 1500) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("\\%", "%").replace("\\&", "&").replace("$", "")  # LaTeX markup in paper abstracts
    return re.sub(r"\s+", " ", s).strip()[:n]


def wikipedia(q: str, k: int = 3) -> list[Item]:
    api = "https://en.wikipedia.org/w/api.php"
    hits = get_json(api, params={"action": "query", "list": "search", "srsearch": q, "srlimit": k, "format": "json"})["query"]["search"]
    if not hits:
        return []
    titles = "|".join(h["title"] for h in hits)
    pages = get_json(api, params={"action": "query", "prop": "extracts|info", "exintro": 1, "explaintext": 1, "exlimit": k,
                                  "titles": titles, "inprop": "url", "format": "json"})["query"]["pages"]
    order = {h["title"]: i for i, h in enumerate(hits)}
    out = [{"source": "wikipedia", "id": f"wiki:{p['pageid']}", "url": p.get("fullurl", ""), "title": p.get("title", ""),
            "text": _clean(p.get("extract"), 2500), "published_at": p.get("touched"), "reliability": "tertiary",
            "license_note": "CC BY-SA 4.0 (Wikipedia)"} for p in pages.values() if "pageid" in p]
    return sorted(out, key=lambda x: order.get(x["title"], 99))


def arxiv(q: str, k: int = 5) -> list[Item]:
    r = request("GET", "https://export.arxiv.org/api/query", params={"search_query": f"all:{q}", "max_results": k, "sortBy": "relevance"},
                max_bytes=600_000)
    if r.status_code >= 400:
        raise FetchError(f"arxiv HTTP {r.status_code}")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(r.content)  # noqa: S314 - see module note
    out = []
    for e in root.findall("a:entry", ns):
        url = (e.findtext("a:id", default="", namespaces=ns) or "").strip()
        out.append({"source": "arxiv", "id": f"arxiv:{url.rsplit('/', 1)[-1]}", "url": url,
                    "title": _clean(e.findtext("a:title", default="", namespaces=ns), 300),
                    "text": _clean(e.findtext("a:summary", default="", namespaces=ns), 2500),
                    "published_at": e.findtext("a:published", default=None, namespaces=ns), "reliability": "primary",
                    "license_note": "arXiv preprint (not necessarily peer-reviewed); abstract licence set by the authors"})
    return out


def crossref(q: str, k: int = 5) -> list[Item]:
    d = get_json("https://api.crossref.org/works", params={"query": q, "rows": k, "select": "DOI,title,abstract,published,container-title,URL,type"})
    out = []
    for it in d.get("message", {}).get("items", []):
        parts = (it.get("published") or {}).get("date-parts") or [[None]]
        pub = "-".join(str(x) for x in parts[0] if x) or None
        out.append({"source": "crossref", "id": f"doi:{it.get('DOI')}", "url": it.get("URL", ""), "title": _clean((it.get("title") or [""])[0], 300),
                    "text": _clean(it.get("abstract") or ((it.get("container-title") or [""])[0] + f" ({it.get('type', '')})"), 2000),
                    "published_at": pub, "reliability": "primary", "license_note": "Crossref metadata (CC0); abstract licence per publisher"})
    return out


def github(q: str, k: int = 5) -> list[Item]:
    d = get_json("https://api.github.com/search/repositories", params={"q": q, "per_page": k},
                 headers={"Accept": "application/vnd.github+json"})
    return [{"source": "github", "id": f"gh:{r['full_name']}", "url": r["html_url"], "title": r["full_name"],
             "text": _clean(f"{r.get('description') or ''} — {r.get('stargazers_count', 0)} stars, licence "
                            f"{(r.get('license') or {}).get('spdx_id') or 'unknown'}, last push {r.get('pushed_at', '')[:10]}"),
             "published_at": r.get("pushed_at"), "reliability": "primary", "license_note": "repository metadata (GitHub API)"}
            for r in d.get("items", [])]


def hackernews(q: str, k: int = 5) -> list[Item]:
    d = get_json("https://hn.algolia.com/api/v1/search", params={"query": q, "hitsPerPage": k, "tags": "story"})
    return [{"source": "hn", "id": f"hn:{h['objectID']}", "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
             "title": _clean(h.get("title"), 300), "text": _clean(f"{h.get('title')} — {h.get('points', 0)} points, {h.get('num_comments', 0)} comments"),
             "published_at": h.get("created_at"), "reliability": "tertiary", "license_note": "discussion aggregator; follow the linked source"}
            for h in d.get("hits", [])]


def pypi(name: str, k: int = 1) -> list[Item]:
    try:
        d = get_json(f"https://pypi.org/pypi/{name}/json")
    except FetchError:
        return []
    info = d.get("info", {})
    rel = d.get("releases", {}).get(info.get("version", ""), [])
    return [{"source": "pypi", "id": f"pypi:{info.get('name')}", "url": info.get("package_url") or f"https://pypi.org/project/{name}/",
             "title": f"{info.get('name')} {info.get('version')}", "text": _clean(f"{info.get('summary') or ''}. Licence: {info.get('license') or 'unknown'}. "
                                                                              f"Requires Python {info.get('requires_python') or '?'}"),
             "published_at": rel[0].get("upload_time_iso_8601") if rel else None, "reliability": "primary", "license_note": "PyPI metadata"}]


def osv(name: str, k: int = 10, ecosystem: str = "PyPI") -> list[Item]:
    r = request("POST", "https://api.osv.dev/v1/query", json={"package": {"name": name, "ecosystem": ecosystem}})
    if r.status_code >= 400:
        raise FetchError(f"osv HTTP {r.status_code}")
    return [{"source": "osv", "id": f"osv:{v['id']}", "url": f"https://osv.dev/vulnerability/{v['id']}", "title": f"{v['id']} ({name})",
             "text": _clean(v.get("summary") or v.get("details"), 1200), "published_at": v.get("published") or v.get("modified"),
             "reliability": "primary", "license_note": "OSV database (CC BY 4.0)"} for v in (r.json().get("vulns") or [])[:k]]


def nvd(q: str, k: int = 5) -> list[Item]:
    d = get_json("https://services.nvd.nist.gov/rest/json/cves/2.0", params={"keywordSearch": q, "resultsPerPage": k})
    out = []
    for v in d.get("vulnerabilities", []):
        c = v.get("cve", {})
        desc = next((x["value"] for x in c.get("descriptions", []) if x.get("lang") == "en"), "")
        out.append({"source": "nvd", "id": f"nvd:{c.get('id')}", "url": f"https://nvd.nist.gov/vuln/detail/{c.get('id')}", "title": c.get("id", ""),
                    "text": _clean(desc, 1500), "published_at": c.get("published"), "reliability": "primary", "license_note": "NVD (US government, public domain)"})
    return out


def huggingface(q: str, k: int = 5) -> list[Item]:
    d = get_json("https://huggingface.co/api/models", params={"search": q, "limit": k, "sort": "downloads"})
    return [{"source": "hf", "id": f"hf:{m.get('id')}", "url": f"https://huggingface.co/{m.get('id')}", "title": m.get("id", ""),
             "text": _clean(f"{m.get('pipeline_tag') or 'model'} — {m.get('downloads', 0)} downloads; tags: "
                            f"{', '.join(t for t in m.get('tags', [])[:8])}"), "published_at": m.get("lastModified") or m.get("createdAt"),
             "reliability": "primary", "license_note": "model card metadata; licence per repository"} for m in d]


def rss(feeds: list[str], q: str, k: int = 5) -> list[Item]:
    terms = {t for t in re.findall(r"[a-z0-9]{3,}", q.lower())}
    out: list[Item] = []
    for f in feeds:
        r = request("GET", f, max_bytes=800_000)
        if r.status_code >= 400:
            continue
        root = ET.fromstring(r.content)  # noqa: S314 - see module note
        for it in root.iter("item"):
            title, desc = it.findtext("title") or "", it.findtext("description") or ""
            if terms and not terms & set(re.findall(r"[a-z0-9]{3,}", (title + " " + desc).lower())):
                continue
            out.append({"source": "rss", "id": f"rss:{it.findtext('link')}", "url": it.findtext("link") or f, "title": _clean(title, 300),
                        "text": _clean(desc, 800), "published_at": it.findtext("pubDate"), "reliability": "secondary",
                        "license_note": f"feed {f}; follow the article for the full text"})
    return out[:k]


def brave(q: str, k: int = 5) -> list[Item]:
    """Brave Search API (official, needs an owner-authorised key stored as provider 'brave-search'). Not exercised live here."""
    from ..daemon.credentials import secret_for

    key = secret_for("brave-search")
    if not key:
        return []
    d = get_json("https://api.search.brave.com/res/v1/web/search", params={"q": q, "count": k}, headers={"X-Subscription-Token": key})
    return [{"source": "web", "id": f"web:{r.get('url')}", "url": r.get("url", ""), "title": _clean(r.get("title"), 300),
             "text": _clean(r.get("description"), 800), "published_at": r.get("page_age"), "reliability": "unknown",
             "license_note": "web page; check the publisher"} for r in d.get("web", {}).get("results", [])]


REGISTRY = {"wikipedia": wikipedia, "arxiv": arxiv, "crossref": crossref, "github": github, "hn": hackernews, "pypi": pypi, "osv": osv,
            "nvd": nvd, "hf": huggingface, "rss": rss, "web": brave}
