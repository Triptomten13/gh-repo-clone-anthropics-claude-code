"""Rocky Flare Originality Score + Anti-Generic Filter (§3C, §12E) and brand-name pre-screens.

The filter is a quality gate: a concept with blocking flags must be revised
before it can be approved. The trademark pre-screen only catches *known* marks
from a small list — it never replaces an official EUIPO/PRV search.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .schemas import OriginalityReport
from .taxonomy import GENRES, PREDICTABLE_PALETTES

GENERIC_NAME_TOKENS = {
    "pro", "max", "ultra", "smart", "eco", "hub", "prime", "elite", "plus", "go", "nova", "zen", "bliss", "pure", "vibe", "glow",
    "best", "top", "mega", "super", "tech", "store", "shop", "gear", "world", "zone", "direct", "online", "express", "co", "official",
    "premium", "deluxe", "trendy", "life", "style", "home", "goods", "mart", "x",
}
GENERIC_SUFFIXES = ("ify", "verse", "zilla", "topia", "ster")
AI_PHRASES = (
    "elevate your", "unlock", "game-changer", "game changer", "seamless", "in today's fast-paced world", "take your", "to the next level",
    "whether you're", "look no further", "revolutioni", "cutting-edge", "cutting edge", "delve", "tapestry", "embark", "unleash",
    "designed with you in mind", "perfect for any occasion", "must-have", "elevated", "effortlessly", "redefine", "the ultimate",
    "crafted with care", "sleek and stylish", "ever-evolving", "harness the power", "say goodbye to", "transform your",
)
OVERUSED_SLOGANS = ("just do it", "think different", "because you're worth it", "for every adventure", "built for life",
                    "live your best life", "made for you", "quality you can trust", "adventure awaits", "your journey starts here")
BUZZWORDS = ("synergy", "disruptive", "next-gen", "next gen", "innovative", "world-class", "best-in-class", "paradigm",
             "holistic", "leverage", "revolutionary", "state-of-the-art", "premium quality", "high quality")
UNSUBSTANTIATED = (r"\b(best|#1|number one|no\.? ?1)\b", r"\bmilitary[- ]grade\b", r"\bindestructible\b", r"\b100% waterproof\b",
                   r"\bbulletproof\b", r"\buniversal(ly)? (fit|compatible|compatibility)\b", r"\bfits all\b", r"\bclinically\b",
                   r"\bguaranteed\b", r"\bunbreakable\b", r"\blifetime\b(?! warranty)")
CONSPIRACY_AS_FACT = (r"truth they (don't|do not) want", r"proven cover[- ]?up", r"government is hiding", r"they are hiding",
                      r"what they won't tell you", r"the real truth", r"exposed:")
VAGUE_AUDIENCE = ("everyone", "anyone", "all ages", "people", "customers", "consumers", "users", "everybody")
REAL_AGENCIES = ("cia", "fbi", "nsa", "kgb", "mi6", "mi5", "mossad", "säpo", "sapo", "interpol", "nato", "pentagon", "försvarsmakten",
                 "department of defense", "secret service", "försvarets radioanstalt")
RELIGIOUS_TERMS = ("jesus", "christ", "g-sus", "gsus", "holy", "messiah", "allah", "buddha", "bible", "gospel")
# Well-known marks likely to conflict. NOT a trademark search — a cheap early warning only.
KNOWN_MARKS = {
    "black mirror": "TV series 'Black Mirror' (Netflix/House of Tomorrow) — strong existing mark",
    "g-sus": "'G-Sus' fashion brand existed (NL) — prior use risk", "gsus": "'G-Sus' fashion brand existed (NL) — prior use risk",
    "north face": "The North Face", "patagonia": "Patagonia", "fjällräven": "Fjällräven", "fjallraven": "Fjällräven",
    "haglöfs": "Haglöfs", "haglofs": "Haglöfs", "thule": "Thule", "ortlieb": "Ortlieb", "leatherman": "Leatherman",
    "victorinox": "Victorinox", "gerber": "Gerber", "fenix": "Fenix (lighting)", "petzl": "Petzl", "garmin": "Garmin",
    "xiaomi": "Xiaomi", "segway": "Segway", "ninebot": "Ninebot", "bosch": "Bosch", "shimano": "Shimano", "apple": "Apple",
    "nike": "Nike", "adidas": "Adidas", "ikea": "IKEA", "rolex": "Rolex", "supreme": "Supreme", "molle": "MOLLE (US military system name — descriptive use only)",
    "babylon": "common mark word (many registrations) — search required", "exodus": "common mark word — search required",
    "archivum": "search required", "sentinel": "common mark word — search required",
}
TYPICAL_PALETTE_TOLERANCE = 10.0  # OKLab ΔE×100, applied to the worst-matched stock colour


def _srgb_to_lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklab(hexc: str) -> tuple[float, float, float]:
    h = hexc.lstrip("#")
    r, g, b = (_srgb_to_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def delta_e(a: str, b: str) -> float:
    return 100 * math.dist(oklab(a), oklab(b))


def palette_distance(p: list[str], ref: tuple[str, ...]) -> float:
    """Worst-matched reference colour (max of nearest-match ΔE). Low only if p contains *every*
    colour of the stock palette — i.e. the palette really is the stock combination."""
    if not p:
        return 0.0
    return max(min(delta_e(r, c) for c in p) for r in ref)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zåäöæø0-9'-]+", text.lower())


def trademark_prescreen(name: str) -> dict[str, Any]:
    n = name.lower()
    hits = [{"term": k, "note": v} for k, v in KNOWN_MARKS.items() if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", n)]
    conflict = any("search required" not in h["note"] for h in hits)
    return {"status": "known_conflict" if conflict else "unscreened", "hits": hits,
            "required": "Official search in EUIPO eSearch / TMview and PRV (Sweden), plus domain and social-handle checks, before use."}


def check_name(name: str) -> list[dict[str, str]]:
    flags = []
    toks = _words(name)
    generic = [t for t in toks if t in GENERIC_NAME_TOKENS]
    if not toks:
        flags.append({"code": "empty_name", "severity": "block", "detail": "no name"})
    elif len(generic) >= max(1, math.ceil(len(toks) / 2)):
        flags.append({"code": "generic_name", "severity": "block", "detail": f"generic tokens: {', '.join(generic)}"})
    if any(t.endswith(GENERIC_SUFFIXES) and len(t) > 4 for t in toks):
        flags.append({"code": "template_suffix", "severity": "warn", "detail": "template-style suffix (-ify/-ly/-hub …)"})
    for a in REAL_AGENCIES:
        if re.search(r"(?<![a-zåäö])" + re.escape(a) + r"(?![a-zåäö])", name.lower()):
            flags.append({"code": "real_organisation", "severity": "block", "detail": f"uses a real organisation's name ('{a}'): impersonation / protected emblem risk"})
    return flags


def check_text(text: str, field: str) -> list[dict[str, str]]:
    t = text.lower()
    flags = []
    hits = [p for p in AI_PHRASES if p in t]
    if hits:
        flags.append({"code": "ai_phrases", "severity": "block" if len(hits) >= 2 else "warn", "detail": f"{field}: {', '.join(hits[:4])}"})
    sl = [s for s in OVERUSED_SLOGANS if s in t]
    if sl:
        flags.append({"code": "overused_slogan", "severity": "block", "detail": f"{field}: '{sl[0]}'"})
    bz = [b for b in BUZZWORDS if b in t]
    if len(bz) >= 2:
        flags.append({"code": "buzzwords", "severity": "warn", "detail": f"{field}: {', '.join(bz)}"})
    for pat in UNSUBSTANTIATED:
        m = re.search(pat, t)
        if m:
            flags.append({"code": "unsubstantiated_claim", "severity": "block", "detail": f"{field}: '{m.group(0)}' needs test evidence or removal"})
    for pat in CONSPIRACY_AS_FACT:
        m = re.search(pat, t)
        if m:
            flags.append({"code": "conspiracy_as_fact", "severity": "block", "detail": f"{field}: presents '{m.group(0)}' as fact — keep it clearly fictional"})
    for a in REAL_AGENCIES:
        if re.search(r"(?<![a-zåäö])" + re.escape(a) + r"(?![a-zåäö])", t):
            flags.append({"code": "real_organisation", "severity": "block", "detail": f"{field}: references real organisation '{a}'"})
    return flags


def sensitivity_flags(text: str, genres: list[str]) -> list[dict[str, str]]:
    flags = []
    t = text.lower()
    rel = [r for r in RELIGIOUS_TERMS if re.search(r"(?<![a-z])" + re.escape(r) + r"(?![a-z])", t)]
    sens = {s for g in genres if g in GENRES for s in GENRES[g].sensitivity}
    if rel:
        flags.append({"code": "religious_reference", "severity": "review",
                      "detail": f"sacred names ({', '.join(rel)}): review for respectful use; avoid puns or pairing with weapons/violence"})
    if "religious" in sens and not rel:
        flags.append({"code": "religious_imagery", "severity": "review", "detail": "biblical imagery: keep it understated and respectful"})
    if "conspiracy" in sens:
        flags.append({"code": "fiction_framing", "severity": "review", "detail": "conspiracy/archive aesthetics must read as fiction; no factual claims"})
    if "occult" in sens:
        flags.append({"code": "occult_imagery", "severity": "review", "detail": "use historical/fictional symbol systems; avoid real hate or extremist symbols"})
    if "cultural_heritage" in sens:
        flags.append({"code": "cultural_heritage", "severity": "review", "detail": "draw on heritage respectfully; avoid caricature and symbols co-opted by extremists"})
    return flags


def score_concept(concept: dict[str, Any], category_tags: list[str] | None = None, novel_hybrid: bool | None = None,
                  net_margin: float | None = None) -> OriginalityReport:
    """concept keys: name, tagline, story, usp, audience, palette (list), primary_genre, secondary_genre, description."""
    name = concept.get("name", "")
    text_fields = {k: concept.get(k, "") or "" for k in ("tagline", "story", "usp", "description")}
    flags = check_name(name)
    for k, v in text_fields.items():
        flags += check_text(v, k)
    genres = [g for g in (concept.get("primary_genre"), concept.get("secondary_genre")) if g]
    flags += sensitivity_flags(" ".join([name, *text_fields.values()]), genres)

    audience = (concept.get("audience") or "").strip()
    aud_words = _words(audience)
    if not audience or (len(aud_words) <= 3 and any(w in VAGUE_AUDIENCE for w in aud_words)):
        flags.append({"code": "no_target_customer", "severity": "block", "detail": "audience is missing or 'everyone'"})
    story = text_fields["story"] + " " + text_fields["description"]
    if len(_words(story)) < 12:
        flags.append({"code": "empty_description", "severity": "block", "detail": "story/description too thin to differentiate"})

    palette = [c for c in concept.get("palette", []) if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)]
    refs = list(PREDICTABLE_PALETTES["generic"])
    for t in category_tags or []:
        refs += list(PREDICTABLE_PALETTES.get(t, ()))
    pal_dist = min((palette_distance(palette, r) for r in refs), default=40.0) if palette else 0.0
    if palette and pal_dist < TYPICAL_PALETTE_TOLERANCE:
        flags.append({"code": "predictable_palette", "severity": "warn", "detail": "palette is close to a stock combination for this category"})
    if not palette:
        flags.append({"code": "no_palette", "severity": "warn", "detail": "no colour palette defined"})

    tm = trademark_prescreen(name)
    if tm["status"] == "known_conflict":
        flags.append({"code": "trademark_conflict", "severity": "block", "detail": "; ".join(h["note"] for h in tm["hits"])})

    # ---- components 0..100
    name_pen = sum(25 for f in flags if f["code"] in ("generic_name", "template_suffix", "trademark_conflict"))
    uniq = 70 - name_pen + (20 if novel_hybrid else 0 if novel_hybrid is None else -5)
    visual = min(100, 30 + pal_dist * 2.0) if palette else 20
    usp = text_fields["usp"]
    concrete = bool(re.search(r"\d|module|mount|waterproof|reflect|magnet|modular|insulat|weld|wool|steel|leather|ripstop|ip\d", usp.lower()))
    differentiation = (40 if usp else 0) + (35 if concrete else 0) + min(25, len(_words(usp)))
    audience_spec = 0 if any(f["code"] == "no_target_customer" for f in flags) else min(100, 40 + 6 * len(aud_words))
    ai_pen = sum(15 for f in flags if f["code"] in ("ai_phrases", "buzzwords", "overused_slogan"))
    storytelling = max(0, min(100, 20 + 2 * len(_words(story)) - ai_pen))
    coherence = 75
    if len(genres) == 2 and all(g in GENRES for g in genres):
        from .genres import compatibility
        coherence = int(40 + 60 * compatibility(GENRES[genres[0]], GENRES[genres[1]])[0])
    commercial = 50 if net_margin is None else max(0, min(100, 40 + net_margin * 150))
    comps = {"uniqueness": uniq, "visual_identity": visual, "product_differentiation": differentiation,
             "audience_specificity": audience_spec, "brand_storytelling": storytelling, "creative_coherence": coherence,
             "commercial_viability": commercial}
    comps = {k: round(max(0.0, min(100.0, float(v))), 1) for k, v in comps.items()}
    score = round(sum(comps.values()) / len(comps), 1)
    blocking = any(f["severity"] == "block" for f in flags)
    return OriginalityReport(score=score, components=comps, flags=flags, requires_revision=blocking or score < 55, trademark=tm)
