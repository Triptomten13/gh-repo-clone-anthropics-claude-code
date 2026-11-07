"""Concept authoring: a persona turns a product into a full brand concept, passes it
through the Anti-Generic Filter, and revises until it passes (or gives up and
flags it). Deterministic by default; an LLM can author/revise when configured.
"""
from __future__ import annotations

import re
from typing import Any

from . import genres as G
from . import originality as O
from .taxonomy import GENRES, ProductProfile

MAX_REVISIONS = 3


def _story(name: str, product: str, h_primary, h_secondary, materials: list[str], audience: str, problem: str) -> str:
    return (f"{name} rebuilds {product} around {h_secondary.name.lower()} — {h_secondary.graphic_language.lower()} — on top of "
            f"{h_primary.name.lower()} construction in {', '.join(materials[:2])}. It is made for {audience}, "
            f"who deal with {problem}. Every claim on the label is one we can test.")


TAGLINE_ROTATION = ("practical", "imaginative", "technical", "warm", "terse", "systematic", "scholarly")


def _tagline(style: str, product_noun: str, app: str, problem: str, variant: int = 0) -> str:
    if variant:
        style = TAGLINE_ROTATION[(TAGLINE_ROTATION.index(style) + variant if style in TAGLINE_ROTATION else variant) % len(TAGLINE_ROTATION)]
    return {
        "cynical": f"{product_noun.capitalize()} that pays for its place in the bag.",
        "skeptical": f"Tested before it is promised: {app}.",
        "imaginative": f"{app.capitalize()} with a story worth carrying.",
        "systematic": f"One system for {problem}.",
        "practical": f"Built for {problem}.",
        "terse": f"{app.capitalize()}. Nothing extra.",
        "warm": f"For the days when {problem} is part of the plan.",
        "technical": f"{app.capitalize()}, specified and tested.",
        "scholarly": f"Old knowledge, new {app}.",
        "decisive": f"{app.capitalize()} — decided.",
    }.get(style, f"{app.capitalize()} for {problem}.")


def author_concept(persona: dict[str, Any], product: dict[str, Any], profile: ProductProfile, segments: list[dict[str, Any]],
                   innovation: list[dict[str, Any]], learned: dict[str, float] | None = None, usage: dict[str, int] | None = None,
                   seed: str = "", pick: int = 0) -> dict[str, Any]:
    dirs = G.creative_directions(profile, n=5, learned=learned, usage=usage, affinities=persona.get("genre_affinities"),
                                 novelty_appetite=float(persona.get("novelty_appetite", 0.5)), seed=seed + persona["id"],
                                 naming_style=persona.get("naming_style", ""))
    d = dirs[min(pick, len(dirs) - 1)]
    comps = d.hybrid_id.split("+")
    gp, gs = GENRES[comps[0]], GENRES[comps[1]]
    seg = segments[0] if segments else None
    audience = f"{seg['label'].lower()} — {seg['habits']}" if seg else gp.audience
    problem = seg["problems"][0] if seg else "gear that fails when conditions turn"
    top_inn = next((i for i in innovation if i["regulatory_risk"] <= 3), innovation[0] if innovation else None)
    usp = (f"Proposed: {top_inn['proposal'][0].lower() + top_inn['proposal'][1:]} Verification before any claim: {top_inn['verification']}."
           if top_inn else f"{gp.materials[0].capitalize()} construction with a {gs.name.lower()} identity no marketplace listing has.")
    noun = re.sub(r"\s+(starter\s+)?(kit|set|bundle)$", "", product["name"], flags=re.I).lower()
    app_tag = max(profile.tags, key=profile.tags.get) if profile.tags else ""
    app_phrase = G.TAG_PHRASES.get(app_tag, noun)
    concept = {
        "name": d.title, "tagline": _tagline(persona.get("communication_style", ""), noun, app_phrase, problem, pick),
        "primary_genre": comps[0], "secondary_genre": comps[1], "hybrid": {"id": d.hybrid_id, "name": d.title},
        "direction": d.brand_system.model_dump(), "audience": audience, "usp": usp,
        "story": _story(d.title, noun, gp, gs, d.brand_system.materials_textures, seg["label"].lower() if seg else gp.audience, problem),
        "positioning": d.scores.expected_positioning, "evaluation": d.scores.model_dump(), "palette": d.brand_system.color_palette,
        "why": d.why_it_fits,
    }
    return revise_until_clean(concept, profile, product, usage, persona)


def revise_until_clean(concept: dict[str, Any], profile: ProductProfile, product: dict[str, Any], usage: dict[str, int] | None,
                       persona: dict[str, Any] | None = None) -> dict[str, Any]:
    history = []
    for attempt in range(MAX_REVISIONS + 1):
        rep = O.score_concept(concept, list(profile.tags), novel_hybrid=(usage or {}).get(concept["hybrid"]["id"], 0) == 0,
                              net_margin=product.get("net_margin"))
        concept["originality"] = rep.model_dump()
        if not rep.requires_revision or attempt == MAX_REVISIONS:
            break
        history.append([f["code"] for f in rep.flags if f["severity"] == "block"])
        concept = deterministic_revision(concept, rep.flags, attempt, persona)
    concept["revision_history"] = history
    concept["status"] = "needs_revision" if concept["originality"]["requires_revision"] else "draft"
    return concept


def deterministic_revision(concept: dict[str, Any], flags: list[dict[str, str]], attempt: int, persona: dict[str, Any] | None) -> dict[str, Any]:
    c = dict(concept)
    codes = {f["code"] for f in flags}
    if codes & {"generic_name", "template_suffix", "trademark_conflict", "real_organisation", "empty_name"}:
        gp, gs = GENRES[c["primary_genre"]], GENRES[c["secondary_genre"]]
        styles = ["mythic", "latin", "single", "nordic"]
        old_name = c["name"]
        c["name"] = G._name(gp, gs, seed=f"rev{attempt}", naming_style=styles[attempt % len(styles)])
        c["hybrid"] = {**c["hybrid"], "name": c["name"]}
        if old_name:  # keep the copy consistent with the new name
            for f_ in ("tagline", "story", "usp"):
                c[f_] = re.sub(re.escape(old_name), c["name"], c.get(f_) or "")
    for field in ("tagline", "story", "usp", "description"):
        txt = c.get(field) or ""
        for p in O.AI_PHRASES + O.OVERUSED_SLOGANS + O.BUZZWORDS:
            txt = re.sub(re.escape(p), "", txt, flags=re.I)
        for pat in O.UNSUBSTANTIATED + O.CONSPIRACY_AS_FACT:
            txt = re.sub(pat, "", txt, flags=re.I)
        c[field] = re.sub(r"\s{2,}", " ", txt).strip()
    gp, gs = GENRES[c["primary_genre"]], GENRES[c["secondary_genre"]]
    if "no_target_customer" in codes:
        c["audience"] = gp.audience
    if not c.get("palette") or "predictable_palette" in codes or "no_palette" in codes:
        c["palette"] = list(dict.fromkeys([*gp.palette[:3], *gs.palette[:2]]))
        c["direction"] = {**(c.get("direction") or {}), "color_palette": c["palette"]}
    if len((c.get("usp") or "").split()) < 5:
        c["usp"] = (f"{gp.materials[0].capitalize()} and {gp.materials[1]} construction, modular where it matters, finished with "
                    f"{gs.graphic_language.split(',')[0].lower()} — a look no marketplace listing shares.")
    if "empty_description" in codes:
        c["story"] = (c.get("story") or "") + f" It borrows {GENRES[c['secondary_genre']].graphic_language.lower()} to make the product recognisable at a glance."
    return c
