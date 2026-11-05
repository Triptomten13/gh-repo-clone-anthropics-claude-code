"""New commercial intelligence modules (§13). Deterministic analysers produce typed,
reasoned opportunity lists; they recommend, never act. Subscriptions are only
proposed for genuinely recurring needs; acquisitions always need human approval.
"""
from __future__ import annotations

import re
from typing import Any

from .schemas import CommercialOpportunity

MODULES = ("audience_monetization", "digital_assets", "b2b_opportunity", "licensing", "local_opportunity", "subscription_intel",
           "waste_to_value", "acquisition")


def _o(module: str, title: str, desc: str, model: str, effort: str, reasons: list[str], conf: float = 0.4, **kw: Any) -> CommercialOpportunity:
    return CommercialOpportunity(module=module, title=title, description=desc, model=model, effort=effort, reasoning=reasons,
                                 confidence=conf, epistemic="hypothesis", **kw)


def recurring_need(text: str, tags: set[str]) -> tuple[bool, list[str]]:
    t = text.lower()
    reasons = []
    if tags & {"consumable", "refill"}:
        reasons.append("tagged consumable")
    for kw, why in (("filter", "filters are replaced"), ("refill", "refills"), ("tinder", "tinder is used up"), ("fuel", "fuel is used up"),
                    ("battery", "batteries degrade"), ("tyre", "tyres wear"), ("tire", "tires wear"), ("brake pad", "pads wear"),
                    ("coffee", "beans/filters consumed"), ("seed", "seasonal seeds"), ("first aid", "contents expire"), ("food", "food expires"),
                    ("emergency", "supplies expire and need rotation")):
        if kw in t:
            reasons.append(why)
    return bool(reasons), reasons


def analyse(module: str, name: str, text: str, tags: list[str] | None = None, retail: float | None = None,
            payload: dict[str, Any] | None = None) -> list[CommercialOpportunity]:
    tags_s = {x.lower() for x in (tags or [])}
    t = f"{name} {text}".lower()
    payload = payload or {}
    out: list[CommercialOpportunity] = []
    if module == "audience_monetization":
        out += [_o(module, f"{name} skills course", "Paid course teaching the skill behind the product.", "online_course", "medium",
                   ["audience needs know-how" if re.search(r"bushcraft|repair|craft|sourdough|maintenance|winter", t) else "only if users need skill"]),
                _o(module, "Membership with member pricing", "Community membership: guides, challenges, member drops.", "membership", "medium",
                   ["recurring relationship with the audience"]),
                _o(module, "Affiliate recommendations (disclosed)", "Curated guides recommending complementary gear we do not make.", "affiliate",
                   "low", ["earns from adjacent needs"], legal_notes=["mark affiliate links as advertising (Marknadsföringslagen)"]),
                _o(module, "Sponsored newsletter", "Niche newsletter with clearly labelled sponsorships.", "newsletter", "low", ["owned channel"],
                   legal_notes=["sponsorship disclosure"]),
                _o(module, "Events & field days", "Hands-on events or workshops.", "events", "high", ["community and content in one"])]
    elif module == "digital_assets":
        out += [_o(module, f"{name} printable checklist pack", "Printable checklists and field cards.", "digital_download", "low", ["near-zero marginal cost"]),
                _o(module, "Configurator micro-SaaS", "Tool that builds a kit or setup for a user's situation.", "micro_saas", "medium", ["drives product sales"]),
                _o(module, "Template & design asset pack", "Labels, layouts or planning templates for the niche.", "digital_download", "low", ["reusable"]),
                _o(module, "Specialised database", "Curated database (e.g. verified compatibility lists) sold or used as a moat.", "database", "high",
                   ["only with genuinely verified data"]),
                _o(module, "AI workflow", "Assistant that answers setup/maintenance questions from verified docs.", "ai_tool", "medium", ["support deflection"])]
    elif module == "b2b_opportunity":
        buyers = [("tradespeople & service fleets", r"tool|light|bag|organi|work"), ("municipalities & schools", r"emergency|reflect|safety|outdoor|first aid"),
                  ("bike/scooter-sharing operators", r"scooter|bike|lock|light|mount"), ("hospitality & cabin rentals", r"camp|outdoor|kit|light|blanket"),
                  ("corporate gifting", r"gift|personal|edc|kit")]
        for b, pat in buyers:
            if re.search(pat, t):
                out.append(_o(module, f"Sell to {b}", f"Volume and white-label versions for {b}; recurring contracts where consumption repeats.",
                              "b2b_distribution", "high", [f"product matches {b} needs ({pat})"],
                              legal_notes=["B2B terms, invoicing and public-procurement rules (LOU) where relevant"]))
    elif module == "licensing":
        owned = bool(payload.get("owns_ip"))
        if not owned:
            out.append(_o(module, "No licensable IP yet", "Licensing requires original designs, software or content we own.", "product_licensing", "low",
                          ["no owned IP recorded for this product"], conf=0.8))
        else:
            out += [_o(module, "License the design to regional retailers", "Royalty-based licence for original design.", "product_licensing", "medium",
                       ["original IP owned"], legal_notes=["register design (EUIPO) before licensing"]),
                    _o(module, "License educational content", "Course/guide licensing to schools or clubs.", "content_licensing", "low", ["owned content"])]
    elif module == "local_opportunity":
        reasons = []
        if re.search(r"winter|cold|dark|reflect|snow|ice|thermal", t):
            reasons.append("Nordic darkness and winter create stronger need than in southern markets")
        if re.search(r"outdoor|camp|hike|bushcraft", t):
            reasons.append("strong Nordic outdoor culture and right-of-public-access (allemansrätten) usage")
        if re.search(r"bike|cykel|scooter", t):
            reasons.append("cycling/commuting culture in Nordic cities; winter cycling segment")
        out.append(_o(module, "Validate in Sweden first", "Swedish-language landing page + local search test before expanding.", "local_validation", "low",
                      reasons or ["small market: cheap to test, but cap expectations"], conf=0.5,
                      legal_notes=["Swedish-language consumer information; prices incl. 25% VAT"]))
        out.append(_o(module, "Swedish-language content gap", "Guides in Swedish where most content is English.", "content_seo", "low",
                      ["local-language search often less competitive (verify with keyword data)"]))
    elif module == "subscription_intel":
        ok, reasons = recurring_need(t, tags_s)
        if ok:
            out.append(_o(module, f"{name} replenishment plan", "Subscribe to the parts that genuinely run out or expire.", "subscription_commerce",
                          "medium", reasons, conf=0.55, legal_notes=["easy online cancellation; clear renewal terms (consumer law)"]))
        else:
            out.append(_o(module, "No subscription recommended", "Customers need this product once; a subscription would be forced.", "none", "low",
                          ["no consumable, wear or expiry cycle detected"], conf=0.7))
    elif module == "waste_to_value":
        mats = [m for m in ("textile", "fabric", "leather", "wood", "aluminium", "canvas", "rubber", "tyre", "inner tube", "glass", "paper") if m in t]
        out.append(_o(module, "Off-cut and return-stock products", "Small goods (pouches, patches, tags) from production off-cuts or unsellable returns.",
                      "upcycled_products", "medium", [f"materials in use: {', '.join(mats) or 'unknown — ask supplier'}"],
                      legal_notes=["waste handling may require permits (Naturvårdsverket)", "product safety applies to upcycled goods"]))
        out.append(_o(module, "Repair & refurbish programme", "Take back worn units for repair/resale.", "service", "high", ["circular, builds loyalty"]))
    elif module == "acquisition":
        cands = payload.get("candidates") or []
        if not cands:
            out.append(_o(module, "Acquisition screening criteria", "Provide candidates (name, annual profit, asking price, traffic share by source) to screen.",
                          "acquisition", "low", ["no deal-flow source integrated — manual candidates only"], conf=0.8))
        for c in cands:
            profit, ask = float(c.get("annual_profit") or 0), float(c.get("asking_price") or 0)
            multiple = ask / profit if profit > 0 else None
            risks = []
            if multiple is None:
                risks.append("no profit: valuation unsupported")
            elif multiple > 4:
                risks.append(f"{multiple:.1f}× profit is high for a small digital business")
            if float(c.get("single_channel_share") or 0) > 0.7:
                risks.append("over 70% of traffic from one source")
            out.append(_o(module, f"Screen: {c.get('name')}", f"Asking {ask:.0f}, profit {profit:.0f}, multiple {multiple and round(multiple, 1)}.",
                          "acquisition", "high", risks or ["passes first screen — due diligence required"], conf=0.4, requires_approval=True,
                          legal_notes=["any offer or LOI requires LEVEL 5 human approval"]))
    else:
        raise ValueError(f"unknown module {module}")
    return out
