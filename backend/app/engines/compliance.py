"""Compliance engine for Sweden / EU (spec section 16).

Produces a pre-launch checklist per product. Classification is keyword-based
and deliberately conservative: when in doubt, a product is routed to human
review. This engine never marks a product "approved" — only a human can.

This is decision support, not legal advice. Regulation references should be
re-verified by the Chief Risk Agent's monthly compliance review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

BASELINE = [
    ("gdpr", "GDPR (EU) 2016/679: privacy notice, lawful basis, consent for marketing, DPA with processors"),
    ("withdrawal", "Distance selling (Distansavtalslagen 2005:59 / Directive 2011/83/EU): 14-day withdrawal right, model withdrawal form, pre-contract info"),
    ("marketing_act", "Marknadsföringslagen (2008:486): no misleading claims; advertising must be identifiable"),
    ("price_info", "Prisinformationslagen + Omnibus (EU) 2019/2161: total price incl. VAT; reductions vs. lowest price in prior 30 days"),
    ("vat_oss", "VAT: Swedish VAT registration; OSS once EU cross-border B2C distance sales exceed EUR 10,000/yr"),
    ("gpsr", "GPSR (EU) 2023/988: EU responsible economic operator, product identifier, manufacturer contact, safety warnings shown in the online listing"),
    ("packaging", "Packaging producer responsibility (Sweden) and PPWR (EU) 2025/40: register / join a compliance scheme where applicable"),
    ("reach", "REACH (EC) 1907/2006: no restricted substances (Annex XVII); SVHC information duty >0.1%"),
    ("ip", "Intellectual property: no third-party trademarks, copyrighted images or designs without licence"),
    ("company_info", "E-commerce Act (2002:562): company name, org. number, address and contact details on the site"),
]

# category -> (keywords, checklist items, risk level: high => blocked pending review)
CATEGORIES: dict[str, tuple[tuple[str, ...], list[str], str]] = {
    "electronics": (
        ("electronic", "charger", "usb", "led", "lamp", "power bank", "bluetooth", "wifi", "wireless", "speaker",
         "headphone", "earbud", "smart", "gadget", "plug", "adapter", "heater", "electric"),
        ["CE marking + EU Declaration of Conformity (LVD 2014/35/EU, EMC 2014/30/EU)",
         "RoHS 2011/65/EU restricted substances",
         "WEEE 2012/19/EU: producer registration (Naturvårdsverket) and take-back",
         "Radio Equipment Directive 2014/53/EU if any radio (Bluetooth/Wi-Fi)",
         "Technical file obtainable from manufacturer"],
        "high",
    ),
    "batteries": (
        ("battery", "batteries", "rechargeable", "lithium", "power bank", "li-ion"),
        ["Battery Regulation (EU) 2023/1542: producer registration, labelling, take-back",
         "UN38.3 test summary for lithium batteries (transport)"],
        "high",
    ),
    "cosmetics": (
        ("cosmetic", "cream", "serum", "lotion", "shampoo", "makeup", "skincare", "lipstick", "perfume", "soap"),
        ["Cosmetics Regulation (EC) 1223/2009: EU Responsible Person, CPNP notification, safety report",
         "INCI ingredient labelling in Swedish"],
        "high",
    ),
    "food_contact": (
        ("mug", "bottle", "cup", "kitchen", "cutting board", "lunch box", "container", "utensil", "plate", "straw", "tumbler"),
        ["Food contact materials (EC) 1935/2004; plastics (EU) 10/2011; Declaration of Compliance",
         "Migration test report from an accredited lab"],
        "high",
    ),
    "childrens_products": (
        ("toy", "kid", "kids", "child", "children", "baby", "infant", "toddler"),
        ["Toy safety (2009/48/EC, and successor Regulation when applicable): CE, EN 71 test reports",
         "Age warnings in Swedish; small-parts assessment"],
        "high",
    ),
    "supplements_food": (
        ("supplement", "vitamin", "protein", "capsule", "tea", "snack", "food", "collagen"),
        ["Food supplements Directive 2002/46/EC; registration with Livsmedelsverket / municipality",
         "Nutrition & health claims Regulation (EC) 1924/2006: only authorised claims"],
        "high",
    ),
    "textiles": (
        ("shirt", "t-shirt", "hoodie", "textile", "apparel", "clothing", "sock", "dress", "fabric", "towel"),
        ["Textile Regulation (EU) 1007/2011: fibre composition labelling", "Care labelling in Swedish"],
        "medium",
    ),
    "ppe": (
        ("helmet", "protective", "safety glasses", "work gloves", "face mask", "respirator", "knee pad"),
        ["PPE Regulation (EU) 2016/425: CE, category assessment, notified body for cat. II/III"],
        "high",
    ),
}

PROHIBITED = (
    "replica", "counterfeit", "knockoff", "dupe of", "pepper spray", "taser", "stun gun", "knife", "weapon",
    "cbd", "thc", "nicotine", "vape", "e-cigarette", "prescription", "laser pointer", "firework",
    "fake review", "spy camera",
)
HEALTH_CLAIM_PATTERNS = (
    r"\bcures?\b", r"\bheals?\b", r"\btreats?\b", r"\bprevents?\b", r"\bweight loss\b", r"\bdetox\b",
    r"\banti[- ]?aging\b", r"\bboosts? (your )?immun", r"\bpain relief\b", r"\bmedical\b", r"\bclinically proven\b",
)


@dataclass
class ComplianceReport:
    # blocked    = prohibited goods / unlawful claims: must not be sold as-is
    # restricted = regulated category: launch gated on human-verified documentation
    # needs_review = no specific rule matched, but a human still signs off
    # The engine never returns "approved" — only a human can.
    status: str
    categories: list[str]
    checklist: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    disclaimer: str = "Decision support only, not legal advice. Final approval requires a human reviewer."

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _has(text: str, kw: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", text) is not None


def assess(name: str, description: str = "", category: str = "", tags: list[str] | None = None,
           marketing_copy: str = "", non_eu_supplier: bool = True, affiliate: bool = False) -> ComplianceReport:
    text = " ".join([name, description, category, " ".join(tags or [])]).lower()
    cats: list[str] = []
    checklist = [{"id": k, "item": v, "done": False, "category": "baseline"} for k, v in BASELINE]
    blockers: list[str] = []
    restrictions: list[str] = []
    warnings: list[str] = []

    for cat, (kws, items, risk) in CATEGORIES.items():
        if any(_has(text, k) for k in kws):
            cats.append(cat)
            checklist.extend({"id": f"{cat}_{i}", "item": it, "done": False, "category": cat} for i, it in enumerate(items))
            if risk == "high":
                restrictions.append(f"{cat}: regulated category — documentation must be verified by a human before launch")

    for kw in PROHIBITED:
        if _has(text, kw) or _has(marketing_copy.lower(), kw):
            blockers.append(f"prohibited/restricted term '{kw}': product may be illegal or IP-infringing in Sweden/EU")

    claims_text = (marketing_copy + " " + description).lower()
    for pat in HEALTH_CLAIM_PATTERNS:
        m = re.search(pat, claims_text)
        if m:
            blockers.append(f"health/medical claim '{m.group(0)}': requires substantiation and may trigger MDR (EU) 2017/745 or claims rules")

    if non_eu_supplier:
        checklist.append({"id": "import", "item": "Import: customs declaration, duty classification (HS code), EORI number, importer-of-record responsibilities",
                          "done": False, "category": "import"})
        warnings.append("non-EU supplier: an EU-based economic operator is required under GPSR")
    if affiliate:
        checklist.append({"id": "affiliate_disclosure", "item": "Affiliate links clearly disclosed as advertising (reklam/annonslänk)",
                          "done": False, "category": "marketing"})
    if not cats:
        warnings.append("category not recognised: route to human review for product-specific rules")

    status = "blocked" if blockers else ("restricted" if restrictions else "needs_review")
    return ComplianceReport(status=status, categories=cats, checklist=checklist, blockers=blockers,
                            restrictions=restrictions, warnings=warnings)
