"""Product Mutation Engine 2.0 (§6) and Survival Product Innovation Lab (Field Ops §3).

Every node is labelled with what it actually is:
  existing_product        – the product as it exists today
  supplier_customization  – an option the supplier has *documented* (flags on the Supplier record)
  proposed_modification   – a change to an existing product we propose (not yet made)
  original_concept        – new product development (nothing exists yet)
Conceptual modifications are never presented as manufactured products.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from ..engines import compliance
from .schemas import GraphEdgeOut, MutationNode

MUTATION_TYPES = ("functional", "material", "visual", "personalization", "bundle", "audience", "digital", "subscription",
                  "premium", "budget", "professional", "lifestyle", "seasonal", "community", "service")


def _risk(base_text: str, extra: str) -> tuple[int, list[str]]:
    rep = compliance.assess(f"{base_text} {extra}", non_eu_supplier=False)
    if rep.blockers:
        return 5, rep.blockers[:2]
    if rep.restrictions:
        return 3 + min(1, len(rep.restrictions) - 1), [r.split(":")[0] for r in rep.restrictions][:3]
    return 1, []


def _rank(n: dict) -> float:
    v = (0.28 * n["customer_value"] + 0.24 * n["profit_potential"] + 0.2 * n["differentiation"]
         - 0.1 * n["cost"] - 0.08 * n["complexity"] - 0.1 * n["regulatory_risk"])
    lo, hi = 0.28 + 0.24 + 0.2 - 0.5 - 0.4 - 0.5, (0.28 + 0.24 + 0.2) * 5 - 0.1 - 0.08 - 0.1
    return round(100 * (v - lo) / (hi - lo), 1)


def mutate(name: str, category: str = "", tags: list[str] | None = None, supplier: Any | None = None,
           retail_price: float | None = None, profile_tags: dict[str, float] | None = None) -> tuple[list[MutationNode], list[GraphEdgeOut]]:
    tags_l = {t.lower() for t in (tags or [])}
    pt = set((profile_tags or {}).keys())
    text = f"{name} {category} {' '.join(tags_l)}"
    sup_custom = bool(supplier and (getattr(supplier, "offers_custom_packaging", False) or getattr(supplier, "offers_private_label", False)))
    consumable = bool(tags_l & {"consumable", "refill"}) or bool(re.search(r"filter|refill|cartridge|tablet|fuel|tinder|tape|patch|battery", text.lower()))
    winterable = bool(pt & {"outdoor", "mobility", "survival", "apparel", "lighting", "winter"})
    nodes: list[dict] = [{"key": "base", "mutation_type": "existing", "title": name, "concept": "The product as currently sourced.",
                          "status": "existing_product", "customer_value": 3, "cost": 1, "complexity": 1, "differentiation": 1,
                          "profit_potential": 2, "regulatory_risk": 1, "reasoning": ["baseline"], "verification_needed": []}]

    def add(mt: str, title: str, concept: str, status: str, cv: int, cost: int, cx: int, diff: int, profit: int,
            reasons: list[str], verify: list[str] | None = None, risk_text: str = "") -> None:
        risk, risk_notes = _risk(name, risk_text or title)
        nodes.append({"key": mt, "mutation_type": mt, "title": title, "concept": concept, "status": status,
                      "customer_value": cv, "cost": cost, "complexity": cx, "differentiation": diff, "profit_potential": profit,
                      "regulatory_risk": risk, "reasoning": reasons + [f"regulatory: {n}" for n in risk_notes],
                      "verification_needed": verify or []})

    base = re.sub(r"\s+(starter\s+)?(kit|set|bundle)$", "", name, flags=re.I)
    add("functional", f"{base} with an added function", "Integrate the most-requested missing function (e.g. a mounting point, light loop or quick-release).",
        "proposed_modification", 4, 3, 3, 4, 3, ["new function is the strongest differentiator against identical listings"],
        ["prototype + user test before claiming the function"])
    add("material", f"{base} in upgraded materials", "Replace the weakest material (zip, fabric, coating) with a documented better spec.",
        "supplier_customization" if sup_custom else "proposed_modification", 4, 4, 2, 3, 4, ["materials are a visible quality signal"],
        ["material spec sheet from supplier", "durability test"])
    add("visual", f"{base} in a distinct colourway / finish", "Own colourway and finish matched to the brand genre.",
        "supplier_customization" if sup_custom else "proposed_modification", 3, 2, 1, 3, 3, ["low-cost way to stop looking identical to marketplace listings"])
    add("personalization", f"Personalised {base}", "Engraving, initials, custom patch or colour selection captured from the customer's own input.",
        "supplier_customization" if sup_custom else "proposed_modification", 4, 2, 2, 4, 4, ["personalisation lifts giftability and price"],
        ["confirm supplier/partner can personalise per order"])
    add("bundle", f"{base} complete kit", "Bundle with the 2–3 complements buyers otherwise purchase separately.", "proposed_modification",
        4, 3, 2, 3, 4, ["raises order value; reduces comparison shopping"])
    add("audience", f"{base} for an adjacent audience", "Re-spec and re-position for a neighbouring segment (e.g. commuters → tradespeople).",
        "proposed_modification", 3, 2, 2, 4, 3, ["new audience without a new supply chain"])
    add("digital", f"{base} digital companion", "Setup guide, maintenance checklist or configurator delivered digitally.", "original_concept",
        3, 1, 2, 3, 3, ["near-zero marginal cost; supports reviews and returns reduction"])
    if consumable:
        add("subscription", f"{base} replenishment plan", "Recurring delivery of the parts that are used up.", "original_concept",
            4, 2, 3, 3, 5, ["product has consumable/wear parts — natural recurring need"])
    add("premium", f"{base} premium edition", "Top materials, refined finish, rigid packaging, extended warranty.",
        "proposed_modification", 3, 4, 3, 4, 4, ["price anchor; higher margin per unit"], ["warranty terms costed by CFO"])
    add("budget", f"{base} essential edition", "Remove non-essential features to hit a lower price point without cutting safety.",
        "proposed_modification", 3, 2, 2, 2, 2, ["entry point for price-sensitive buyers"], ["confirm safety-relevant parts are unchanged"])
    add("professional", f"{base} pro / trade spec", "Heavier duty, spare parts, documentation for professional users.",
        "proposed_modification", 4, 4, 4, 4, 4, ["professionals pay for reliability and spare parts"], ["load/durability test report"])
    add("lifestyle", f"{base} lifestyle edition", "Design-led edition for display and gifting, same function.", "proposed_modification",
        3, 3, 2, 3, 3, ["broadens appeal beyond pure function"])
    if winterable:
        add("seasonal", f"{base} winter edition", "Cold-proofed version: gloves-friendly operation, reflective details, low-temperature materials.",
            "proposed_modification", 4, 3, 3, 4, 3, ["Nordic winters create a strong seasonal need"],
            ["cold test (e.g. −20 °C) before claiming winter performance"], risk_text="winter reflective")
    add("community", f"{base} owners' community", "Community around use cases: challenges, guides, member pricing.", "original_concept",
        3, 2, 3, 3, 3, ["community lowers CAC over time"])
    add("service", f"{base} setup & repair service", "Fitting, repair or personalisation as a paid service.", "original_concept",
        3, 3, 3, 3, 3, ["service margin and local moat"])

    out = []
    for n in nodes:
        n["rank_score"] = _rank(n) if n["key"] != "base" else 0.0
        n["confidence"] = 0.45 if n["status"] in ("proposed_modification", "original_concept") else 0.7
        n["epistemic"] = "verified" if n["status"] == "existing_product" else "hypothesis"
        out.append(MutationNode(**n))
    relations = {"bundle": "bundles", "premium": "price_ladder", "budget": "price_ladder", "subscription": "recurring",
                 "digital": "extends", "community": "extends", "service": "extends", "audience": "audience_crossover",
                 "professional": "upgrade", "seasonal": "variant", "lifestyle": "variant"}
    edges = [GraphEdgeOut(source="base", target=n.key, relation=relations.get(n.key, "variant_of")) for n in out if n.key != "base"]
    keys = {n.key for n in out}
    if {"premium", "budget"} <= keys:
        edges.append(GraphEdgeOut(source="budget", target="premium", relation="upgrade_path", note="good-better-best ladder"))
    if {"digital", "community"} <= keys:
        edges.append(GraphEdgeOut(source="digital", target="community", relation="feeds", note="guides seed community content"))
    if {"bundle", "subscription"} <= keys:
        edges.append(GraphEdgeOut(source="bundle", target="subscription", relation="recurring", note="kit owners need refills"))
    out.sort(key=lambda n: n.rank_score, reverse=True)
    return out, edges


# ---------------------------------------------------------------- Survival Innovation Lab
INNOVATION_QUESTIONS: list[tuple[str, str, str, Callable[[str, set[str]], bool], str]] = [
    ("smaller", "Can it become smaller?", "Compact version that packs into an EDC pouch.", lambda t, p: True, "pack-size comparison against current unit"),
    ("lighter", "Can it become lighter?", "Weight-optimised build (materials, cut-outs, fewer fasteners).", lambda t, p: True, "weighed sample vs. baseline"),
    ("durable", "Can it become more durable?", "Reinforce the known failure points.", lambda t, p: True, "drop/abrasion/cycle test per failure mode"),
    ("modular", "Can it become modular?", "Standard attachment interface so modules can be added or swapped.", lambda t, p: True, "interface tolerance test"),
    ("waterproof", "Can it become waterproof?", "Sealed version with a stated rating.", lambda t, p: True, "IEC 60529 (IPX) test before any waterproof claim"),
    ("carry", "Can it become easier to carry?", "Integrated carry: clip, strap, MOLLE-style webbing or handle.", lambda t, p: True, "load test of carry points"),
    ("winter", "Can it work in winter?", "Glove-operable controls, cold-tolerant materials and batteries.", lambda t, p: True, "operation test at −20 °C; battery capacity at low temperature"),
    ("multi_purpose", "Can it serve multiple purposes?", "Second function that shares the same parts.", lambda t, p: True, "user test of both functions"),
    ("edc", "Can it integrate with an EDC system?", "Fit standard EDC organisers and pouch sizes.", lambda t, p: "edc" in p or "storage" in p or "tool" in p or "lighting" in p, "fit check with common pouch sizes"),
    ("mobility", "Can it connect to e-mobility?", "Mount or carry solution for bikes and scooters.", lambda t, p: True, "fitment on named models — no universal claims"),
    ("emergency", "Can it become part of an emergency kit?", "Packed as a module of a home/vehicle preparedness kit.", lambda t, p: True, "align with MSB home-preparedness guidance before claiming"),
    ("personalized", "Can it be personalised?", "Engraving/patches/colours from customer input.", lambda t, p: True, "supplier capability confirmation"),
    ("materials", "Can it be manufactured with better materials?", "Specify recycled or higher-grade materials with documentation.", lambda t, p: True, "material certificates (e.g. REACH SVHC declaration)"),
    ("bundle", "Can it be bundled with complementary equipment?", "Complete kit with matched complements.", lambda t, p: True, "margin check by CFO"),
]


def innovation_lab(name: str, profile_tags: dict[str, float] | None = None) -> list[dict[str, Any]]:
    p = set((profile_tags or {}).keys())
    out = []
    for key, q, proposal, applies, verify in INNOVATION_QUESTIONS:
        if not applies(name.lower(), p):
            continue
        functional = 4 if key in ("durable", "waterproof", "winter", "modular", "multi_purpose") else 3
        if key == "mobility" and "mobility" not in p:
            functional = 2
        risk, notes = _risk(name, {"mobility": "bike mount", "winter": "heated", "waterproof": "", "emergency": "emergency"}.get(key, ""))
        out.append({"key": key, "question": q, "proposal": f"{proposal}", "status": "proposed_design" if key not in ("materials",) else "unverified_manufacturing_concept",
                    "functional_value": functional, "regulatory_risk": risk, "regulatory_notes": notes, "verification": verify,
                    "epistemic": "hypothesis"})
    out.sort(key=lambda x: (x["functional_value"], -x["regulatory_risk"]), reverse=True)
    return out
