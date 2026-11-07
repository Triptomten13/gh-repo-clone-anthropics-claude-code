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
         "headphone", "earbud", "smart", "gadget", "plug", "adapter", "heater", "electric", "solar", "power station",
         "inverter", "heated", "hand warmer", "headlamp", "flashlight", "torch", "lantern", "gps"),
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

# --- Survival, tactical & mobility division (Field Operations) -------------------------------
CATEGORIES.update({
    "e_mobility_vehicle": (
        ("e-scooter", "electric scooter", "elsparkcykel", "e-bike", "ebike", "electric bicycle", "elcykel", "pedelec",
         "hoverboard", "electric unicycle", "conversion kit", "hub motor"),
        ["EPAC e-bikes: EN 15194 (≤25 km/h, ≤250 W, pedal assist — otherwise a type-approved vehicle under (EU) 168/2013)",
         "Light personal e-vehicles (e-scooters): EN 17128; Machinery/LVD/EMC conformity",
         "Swedish classification and rules (Transportstyrelsen): verify speed/power class, where riding is allowed, helmet rules for under-15s",
         "Battery pack + charger documentation (Battery Regulation (EU) 2023/1542, IEC 62133 / UN38.3)"],
        "high",
    ),
    "vehicle_safety_component": (
        ("brake", "brake pad", "tyre", "tire", "inner tube", "mirror", "reflector", "bike light", "bicycle light", "scooter light",
         "front light", "rear light", "tail light", "fork", "handlebar", "stem", "kickstand", "mudguard", "fender", "rack",
         "pannier rack", "child seat", "grip"),
        ["Component affects vehicle safety: verify fitment per model and load/strength testing (ISO 4210 for bicycle parts where relevant)",
         "Lighting/reflectors: Swedish requirements for cycles in darkness (white front, red rear, reflectors) — verify current rules",
         "No universal-compatibility claims: publish a verified compatibility list only",
         "Installation instructions and torque/weight limits in Swedish"],
        "high",
    ),
    "helmets_ppe": (
        ("helmet", "hjälm", "knee pad", "elbow pad", "back protector", "hi-vis", "high visibility", "reflective vest"),
        ["PPE Regulation (EU) 2016/425: EU type-examination by a notified body where required",
         "Bicycle helmets: EN 1078; high-visibility clothing: EN ISO 20471 (only if certified — otherwise no protective claims)"],
        "high",
    ),
    "water_treatment": (
        ("water filter", "water purifier", "purification", "filtration", "purifying tablet", "water treatment"),
        ["Claims about removing bacteria/viruses require lab test evidence to a recognised protocol",
         "Chemical purification tablets: Biocidal Products Regulation (EU) 528/2012",
         "Food-contact materials for wetted parts"],
        "high",
    ),
    "first_aid_medical": (
        ("first aid", "first-aid", "bandage", "tourniquet", "trauma kit", "medical kit", "ifak", "splint", "burn gel"),
        ["Contents may be medical devices: Medical Device Regulation (EU) 2017/745 — CE + documentation per item",
         "No medical advice in product copy or content without qualified review"],
        "high",
    ),
    "fire_and_fuel": (
        ("fire starter", "fire-starting", "ferro rod", "firesteel", "fire steel", "stove", "gas canister", "gas cartridge",
         "fuel", "lighter", "tinder", "matches"),
        ["Gas cartridges: EN 417 and dangerous-goods transport rules (ADR / IATA) — check carrier acceptance",
         "Lighters: child-resistance EN 13869 and ISO 9994",
         "Fire-risk warnings and local fire-ban guidance in Swedish (eldningsförbud)"],
        "high",
    ),
    "blades": (
        ("knife", "knives", "machete", "axe", "hatchet", "saw", "multi-tool", "multitool", "blade"),
        ["Knivlagen (1988:254): no marketing that encourages carrying in public; age-verification policy",
         "Blade-lock and sheath safety; clear 'tool, not weapon' positioning"],
        "high",
    ),
    "radio_communication": (
        ("radio", "walkie", "walkie-talkie", "pmr", "two-way radio", "transceiver", "satellite messenger"),
        ["Radio Equipment Directive 2014/53/EU",
         "Licence-free use only on permitted bands (e.g. PMR446); other transceivers may need a licence (PTS)"],
        "high",
    ),
})

PROHIBITED = (
    "replica", "counterfeit", "knockoff", "dupe of", "pepper spray", "taser", "stun gun", "weapon", "brass knuckles",
    "knuckle duster", "throwing star", "switchblade", "butterfly knife", "body armor", "body armour",
    "speed unlock", "derestrict", "de-restrict", "speed limiter bypass", "remove speed limit", "unlock speed", "tuning kit",
    "chip tuning", "tuning chip",
    "cbd", "thc", "nicotine", "vape", "e-cigarette", "prescription", "laser pointer", "firework",
    "fake review", "spy camera",
)
HEALTH_CLAIM_PATTERNS = (
    r"\bcures?\b", r"\bheals?\b", r"\btreats?\b", r"\bprevents?\b", r"\bweight loss\b", r"\bdetox\b",
    r"\banti[- ]?aging\b", r"\bboosts? (your )?immun", r"\bpain relief\b", r"\bmedical\b", r"\bclinically proven\b",
)


PERFORMANCE_CLAIMS = (
    r"\buniversal(ly)? (fit|compatible|compatibility|mount)\b", r"\bfits all\b", r"\bfits every\b", r"\b100% waterproof\b",
    r"\bmilitary[- ]grade\b", r"\bindestructible\b", r"\bbulletproof\b", r"\bunbreakable\b",
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
    mobility_class: str | None = None  # vehicle | electrical_system | vehicle_safety_affecting | ordinary_accessory
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

    for pat in PERFORMANCE_CLAIMS:
        m = re.search(pat, claims_text)
        if m:
            blockers.append(f"performance claim '{m.group(0)}': requires verified test evidence (or remove it)")

    # An accessory *for* an e-scooter is not the vehicle itself.
    accessory = re.search(r"\b(bag|pouch|mount|holder|cover|lock|case|strap|organi[sz]er|pannier|basket|light|lamp|mirror|"
                          r"grip|mudguard|fender|reflector|helmet|glove|kit|pump|tool|charger|battery bag|phone)\b", text)
    drivetrain = re.search(r"conversion kit|hub motor|motor kit|controller", text)
    if "e_mobility_vehicle" in cats and accessory and not drivetrain:
        cats.remove("e_mobility_vehicle")
        checklist = [c for c in checklist if c["category"] != "e_mobility_vehicle"]
        restrictions = [r for r in restrictions if not r.startswith("e_mobility_vehicle")]
    # Mount *location* words (handlebar, stem, rack …) don't make a bag or phone holder a safety component.
    if "vehicle_safety_component" in cats:
        comps = [k for k in CATEGORIES["vehicle_safety_component"][0] if _has(text, k)]
        location_only = set(comps) <= {"handlebar", "stem", "fork", "rack", "pannier rack", "grip"}
        storage = re.search(r"\b(bag|pouch|holder|case|organi[sz]er|basket|phone|cover|box|bottle)\b", text)
        if location_only and storage:
            cats.remove("vehicle_safety_component")
            checklist = [c for c in checklist if c["category"] != "vehicle_safety_component"]
            restrictions = [r for r in restrictions if not r.startswith("vehicle_safety_component")]
            warnings.append("mounts on the vehicle: state max load; must not obstruct steering, brakes, lights or reflectors")
    mobility_ctx = re.search(r"scooter|bike|bicycle|cykel|e-mobility|commut|pannier|handlebar", text)
    mobility_class = None
    if "e_mobility_vehicle" in cats:
        mobility_class = "vehicle"
    elif mobility_ctx and re.search(r"charger|charging|battery pack|spare battery|controller|wiring|dc[- ]?dc|display|throttle", text):
        mobility_class = "electrical_system"
    elif "vehicle_safety_component" in cats or ("helmets_ppe" in cats and re.search(r"bike|scooter|cykel", text)):
        mobility_class = "vehicle_safety_affecting"
    elif mobility_ctx:
        mobility_class = "ordinary_accessory"

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
                            restrictions=restrictions, warnings=warnings, mobility_class=mobility_class)
