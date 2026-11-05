"""Genre intelligence: genre-to-market matching, hybrid fusion, creative directions.

All scores are computed from taxonomy attributes and product data, plus an
optional *learned* adjustment from Style DNA (actual campaign results). Nothing
here invents market facts; every recommendation carries its reasoning.
"""
from __future__ import annotations

import hashlib
from typing import Iterable

from .schemas import BrandSystem, CreativeDirection, DirectionScores, GenreMatch, HybridGenre
from .taxonomy import CLASHES, FAMILY_COMPLEMENT, GENRES, PRESET_HYBRIDS, Genre, ProductProfile

FAMILY_NOUNS = {
    "structural": ("Works", "Supply", "Systems"),
    "nature": ("Fieldworks", "Outfitters", "Expeditions"),
    "narrative": ("Archive", "Society", "Codex", "Order"),
    "cultural": ("Collective", "Club", "Supply"),
}
TAG_PHRASES = {
    "edc": "EDC organisers and pouches", "outdoor": "camp & trail kit", "survival": "preparedness kits", "mobility": "bike & scooter accessories",
    "winter": "winter-ready gear", "lighting": "lighting tools", "storage": "modular storage", "tech": "tech accessories", "kitchen": "kitchen tools",
    "home": "home objects", "gift": "gift editions", "garden": "garden tools", "apparel": "apparel capsule", "travel": "travel organisers",
    "tool": "field tools", "emergency": "emergency modules", "hobby": "hobby kits", "wellness": "wellness rituals", "pet": "pet accessories",
    "office": "desk tools", "fitness": "training gear", "food": "food & ration kits", "music": "audio accessories", "photo": "camera carry",
    "beauty": "care rituals", "kids": "family editions",
}


def _h(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest(), 16)


def get_genre(gid: str, custom: dict[str, Genre] | None = None) -> Genre:
    if gid in GENRES:
        return GENRES[gid]
    if custom and gid in custom:
        return custom[gid]
    raise KeyError(gid)


def match_genres(profile: ProductProfile, learned: dict[str, float] | None = None, top: int | None = None,
                 genres: Iterable[Genre] | None = None) -> list[GenreMatch]:
    learned = learned or {}
    out: list[GenreMatch] = []
    tw = sum(profile.tags.values()) or 1.0
    for g in (genres or GENRES.values()):
        fits = {t: w * g.affinity.get(t, 0.0) for t, w in profile.tags.items()}
        weighted = sum(fits.values()) / tw
        best = max((g.affinity.get(t, 0.0) for t in profile.tags), default=0.0)
        func_fit = 0.6 * weighted + 0.4 * best
        tier_fit = g.tiers.get(profile.tier, 0.5)
        channel = g.video_fit * (0.5 + 0.5 * profile.marketing_potential / 100)
        recog = g.recognition / 5
        reasons = []
        top_tags = sorted(fits, key=fits.get, reverse=True)[:2]
        if func_fit > 0.5:
            reasons.append(f"strong functional fit with {', '.join(top_tags)}")
        elif func_fit < 0.25:
            reasons.append("weak functional fit: aesthetic would feel imposed")
        reasons.append(f"{profile.tier} price tier fit {tier_fit:.1f}")
        if g.video_fit >= 0.8:
            reasons.append("strong short-form video potential")
        penalty = 0.0
        if {"kids", "pet"} & set(profile.tags) and {"occult", "conspiracy"} & set(g.sensitivity):
            penalty += 15
            reasons.append("occult/conspiracy codes are a poor fit for family or pet products")
        if g.id in profile.category_typical:
            penalty += 5
            reasons.append("competitors in this category already look like this (blends in)")
        adj = max(-10.0, min(10.0, learned.get(g.id, 0.0)))
        if adj:
            reasons.append(f"learned from campaign results: {adj:+.1f}")
        score = 100 * (0.5 * func_fit + 0.2 * tier_fit + 0.15 * channel + 0.15 * recog) + adj - penalty
        conf = 0.35 + 0.4 * min(1.0, len(profile.tags) / 3) + (0.15 if adj else 0)
        out.append(GenreMatch(genre_id=g.id, name=g.name, score=round(max(0, min(100, score)), 1), learned_adjustment=round(adj, 1),
                              reasoning=reasons, confidence=round(min(conf, 0.9), 2), epistemic="estimate"))
    out.sort(key=lambda m: m.score, reverse=True)
    return out[:top] if top else out


def compatibility(a: Genre, b: Genre) -> tuple[float, list[str]]:
    notes = []
    comp = FAMILY_COMPLEMENT.get(frozenset({a.family, b.family}), 0.5)
    if frozenset({a.id, b.id}) in CLASHES:
        comp *= 0.3
        notes.append(f"{a.name} and {b.name} clash visually or semantically")
    else:
        notes.append(f"{a.family} + {b.family} pairing (complementarity {comp:.2f})")
    return comp, notes


def _name(primary: Genre, secondary: Genre, seed: str = "", naming_style: str = "") -> str:
    h = _h(primary.id, secondary.id, seed, naming_style)
    story_rank = {"narrative": 3, "nature": 2, "cultural": 1, "structural": 0}
    narrative = secondary if story_rank[secondary.family] > story_rank[primary.family] else primary
    other = primary if narrative is secondary else secondary
    root = narrative.vocab[h % len(narrative.vocab)]
    nouns = other.nouns or FAMILY_NOUNS[other.family]
    noun = nouns[(h // 7) % len(nouns)]
    if naming_style == "latin":
        return f"{root}{'um' if root[-1] not in 'aeiouym' else ''}".capitalize() + f" {noun}"
    if naming_style == "single":
        return root
    return f"{root} {noun}"


def fuse(primary: Genre, secondary: Genre, profile: ProductProfile | None = None, usage: dict[str, int] | None = None,
         extras: list[Genre] | None = None, name: str | None = None, seed: str = "", naming_style: str = "") -> HybridGenre:
    comp, notes = compatibility(primary, secondary)
    extras = extras or []
    structural = primary if primary.family == "structural" else secondary if secondary.family == "structural" else primary
    story = secondary if structural is primary else primary
    tags = list(profile.tags) if profile else []
    apps = [TAG_PHRASES[t] for t in tags if t in TAG_PHRASES and (primary.affinity.get(t, 0) >= .5 or secondary.affinity.get(t, 0) >= .5)]
    if not apps:
        apps = [TAG_PHRASES[t] for t in sorted(primary.affinity, key=primary.affinity.get, reverse=True)[:2] if t in TAG_PHRASES]
    palette = list(dict.fromkeys([*primary.palette[:3], *secondary.palette[:2], *(e.palette[0] for e in extras)]))[:6]
    hid = "+".join([primary.id, secondary.id, *(e.id for e in extras)])
    sens = sorted({*primary.sensitivity, *secondary.sensitivity, *(s for e in extras for s in e.sensitivity)})
    if sens:
        notes.append("sensitivity review: " + ", ".join(sens))
    used = (usage or {}).get(hid, 0)
    return HybridGenre(
        id=hid,
        name=name or _name(primary, secondary, seed, naming_style),
        components=[primary.id, secondary.id, *(e.id for e in extras)],
        concept=f"{primary.name} carrying a {secondary.name.lower()} story — {primary.graphic_language.lower()}, "
                f"layered with {secondary.graphic_language.lower()}.",
        philosophy=f"Function and build quality from {structural.name.lower()}; meaning, mood and memorability from {story.name.lower()}.",
        target_audience=f"{primary.audience}, crossing over with {secondary.audience}",
        palette=palette,
        typography={"display": story.display_type, "text": structural.text_type},
        materials=list(dict.fromkeys([*primary.materials[:2], *secondary.materials[:2], *(m for e in extras for m in e.materials[:1])])),
        surface_treatments=list(dict.fromkeys([*primary.surfaces[:2], *secondary.surfaces[:1]])),
        graphic_language=f"{primary.graphic_language}; overlaid with {secondary.graphic_language.lower()}",
        product_applications=apps[:4],
        packaging_direction=f"{primary.packaging}, finished with {secondary.packaging.lower()}",
        photography_direction=f"{primary.photography}; {secondary.photography.lower()}",
        marketing_identity=f"{primary.advertising} — voiced through {secondary.advertising.lower()}",
        novel=used == 0 and hid not in {p["id"] for p in PRESET_HYBRIDS},
        compatibility=round(comp, 2),
        sensitivity=sens,
        reasoning=notes,
        confidence=round(0.4 + 0.4 * comp, 2),
        epistemic="hypothesis",
    )


def preset_hybrids(profile: ProductProfile | None = None) -> list[HybridGenre]:
    out = []
    for p in PRESET_HYBRIDS:
        gs = [GENRES[c] for c in p["components"]]
        h = fuse(gs[0], gs[1], profile, extras=gs[2:], name=p["name"])
        out.append(h.model_copy(update={"id": p["id"]}))
    return out


def _brand_system(h: HybridGenre, primary: Genre, secondary: Genre) -> BrandSystem:
    return BrandSystem(
        primary_genre=primary.name, secondary_genre=secondary.name,
        visual_direction=h.graphic_language, color_palette=h.palette, typography=h.typography,
        materials_textures=[*h.materials, *h.surface_treatments], photography_style=h.photography_direction,
        packaging_style=h.packaging_direction, website_language=f"{primary.web}; {secondary.web.lower()}",
        social_identity=f"{primary.social}; {secondary.social.lower()}", advertising_direction=h.marketing_identity,
    )


def direction_scores(primary: Genre, secondary: Genre, m1: float, m2: float, comp: float, profile: ProductProfile) -> DirectionScores:
    typical = set(profile.category_typical)
    diff = 100 - 35 * (primary.id in typical) - 25 * (secondary.id in typical) + 10 * (primary.family != secondary.family)
    recog = (primary.recognition + secondary.recognition) / 2 * 20 * (0.75 + 0.25 * comp)
    scal = (primary.scalability + secondary.scalability) / 2 * 20
    mkt = (primary.video_fit + secondary.video_fit) / 2 * 100 * (0.5 + 0.5 * profile.marketing_potential / 100)
    cost = (6 - (primary.production_cost + secondary.production_cost) / 2) * 20
    tier = profile.tier
    if "luxury" in (primary.id, secondary.id) or (primary.tiers["premium"] + secondary.tiers["premium"]) / 2 > .85:
        tier = "premium"
    elif (primary.tiers["budget"] + secondary.tiers["budget"]) / 2 > .75:
        tier = "budget"
    aud = 0.6 * m1 + 0.4 * m2
    overall = 0.25 * aud + 0.2 * min(100, diff) + 0.15 * recog + 0.1 * scal + 0.15 * mkt + 0.15 * cost
    return DirectionScores(audience_relevance=round(aud, 1), competitive_differentiation=round(max(0, min(100, diff)), 1),
                           visual_recognition=round(recog, 1), brand_scalability=round(scal, 1), marketing_potential=round(mkt, 1),
                           production_cost=round(cost, 1), expected_positioning=tier, overall=round(overall, 1))


def creative_directions(profile: ProductProfile, n: int = 5, learned: dict[str, float] | None = None, usage: dict[str, int] | None = None,
                        affinities: dict[str, float] | None = None, novelty_appetite: float = 0.5, seed: str = "",
                        naming_style: str = "") -> list[CreativeDirection]:
    """≥ n distinct directions. ``affinities``/``novelty_appetite`` let a persona bias the search."""
    matches = match_genres(profile, learned)
    m = {x.genre_id: x.score for x in matches}
    pool = [x.genre_id for x in matches[:10]]
    if affinities:  # persona favourites join the pool even if they rank lower
        pool += [g for g in sorted(affinities, key=affinities.get, reverse=True)[:4] if g in GENRES and g not in pool]
    cands = []
    for a in pool:
        for b in pool:
            if a == b:
                continue
            ga, gb = GENRES[a], GENRES[b]
            comp, _ = compatibility(ga, gb)
            novel = (usage or {}).get(f"{a}+{b}", 0) == 0
            aff = ((affinities or {}).get(a, 0) + (affinities or {}).get(b, 0)) * 12
            s = (m[a] * 0.6 + m[b] * 0.4) * (0.65 + 0.35 * comp) + novelty_appetite * (8 if novel else 0) + aff
            if ga.family == gb.family:
                s -= 6
            cands.append((s, a, b, comp))
    cands.sort(reverse=True)
    chosen: list[tuple[float, str, str, float]] = []
    for c in cands:
        if len(chosen) >= n:
            break
        used_primary = {x[1] for x in chosen}
        used_pairs = {frozenset((x[1], x[2])) for x in chosen}
        if c[1] in used_primary or frozenset((c[1], c[2])) in used_pairs:
            continue
        chosen.append(c)
    out = []
    for _, a, b, comp in chosen:
        ga, gb = GENRES[a], GENRES[b]
        h = fuse(ga, gb, profile, usage, seed=seed, naming_style=naming_style)
        sc = direction_scores(ga, gb, m[a], m[b], comp, profile)
        why = [f"{ga.name}: " + "; ".join(next(x for x in matches if x.genre_id == a).reasoning[:2]),
               f"{gb.name}: " + "; ".join(next(x for x in matches if x.genre_id == b).reasoning[:2]),
               f"competitor aesthetics to avoid blending with: {', '.join(GENRES[t].name for t in profile.category_typical) or 'unknown'}"]
        out.append(CreativeDirection(title=h.name, hybrid_id=h.id, brand_system=_brand_system(h, ga, gb), why_it_fits=why, scores=sc,
                                     reasoning=h.reasoning, confidence=h.confidence, epistemic="hypothesis"))
    out.sort(key=lambda d: d.scores.overall, reverse=True)
    return out


def most_distinct(directions: list[CreativeDirection], k: int = 3) -> list[CreativeDirection]:
    """'Three radically different identities': greedy max-distance by genre families/components."""
    if not directions:
        return []
    picked = [directions[0]]
    while len(picked) < min(k, len(directions)):
        def dist(d: CreativeDirection) -> float:
            fam = {GENRES[c].family for c in d.hybrid_id.split("+") if c in GENRES}
            return min(len(set(d.hybrid_id.split("+")) ^ set(p.hybrid_id.split("+"))) +
                       len(fam ^ {GENRES[c].family for c in p.hybrid_id.split("+") if c in GENRES}) for p in picked)
        rest = [d for d in directions if d not in picked]
        picked.append(max(rest, key=dist))
    return picked
