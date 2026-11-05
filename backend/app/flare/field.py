"""ROCKY FLARE // Field Operations knowledge: pillars, customer segments, modular
ecosystems, mounting standards, documentation requirements and sourcing priority.

Segment profiles are research hypotheses to validate (labelled as such) — not
market facts. Compatibility is never assumed: the matrix defaults to 'unverified'.
"""
from __future__ import annotations

import re
from typing import Any

from ..engines import compliance

PILLARS: dict[str, dict[str, Any]] = {
    "A_tactical_lifestyle": {"label": "Tactical lifestyle", "keywords": ("edc", "utility", "modular", "backpack", "multi-tool", "multitool", "flashlight",
                             "headlamp", "belt", "case", "pouch", "organiser", "organizer", "workwear", "waterproof storage", "power bank", "navigation")},
    "B_survival": {"label": "Survival & self-reliance", "keywords": ("survival", "emergency", "first aid", "first-aid", "radio", "solar", "water filter", "water storage", "filtration",
                   "blanket", "stove", "camp", "tarp", "shelter", "fire", "ferro", "bushcraft", "cordage", "paracord", "repair kit", "winter", "thermal",
                   "preparedness", "off-grid", "hand warmer", "lantern")},
    "C_e_mobility": {"label": "E-mobility & personal transport", "keywords": ("scooter", "e-scooter", "e-bike", "ebike", "bicycle", "bike", "pannier",
                     "handlebar", "frame bag", "saddle bag", "commut", "cycling", "elcykel", "elsparkcykel", "mudguard", "bike light", "lock")},
    "D_esoteric_design": {"label": "Spiritual, ancient & esoteric design", "keywords": ("eden", "exodus", "babylon", "archive", "codex", "manuscript",
                          "alchemy", "celestial", "astrolabe", "rune", "sigil", "shepherd", "ark", "relic", "cartograph")},
}
SUBSECTIONS = {  # Field Ops dashboard subsection -> product keyword filter
    "tactical": ("A_tactical_lifestyle",), "survival": ("B_survival",), "nordic": ("winter", "nordic", "cold", "snow", "ice", "reflect", "thermal"),
    "escooter": ("scooter", "elsparkcykel"), "ebike": ("e-bike", "ebike", "bicycle", "bike", "pannier", "cykel"), "edc": ("edc", "pouch", "organiser", "organizer", "multi", "flashlight", "wallet"),
    "bushcraft": ("bushcraft", "camp", "tarp", "fire", "ferro", "knife", "axe", "cordage", "outdoor", "shelter"),
}


def classify_pillars(text: str) -> dict[str, int]:
    t = text.lower()
    return {p: hits for p, spec in PILLARS.items() if (hits := sum(1 for k in spec["keywords"] if k in t))}


def matches_subsection(text: str, sub: str) -> bool:
    keys = SUBSECTIONS.get(sub, ())
    t = text.lower()
    if keys and keys[0] in PILLARS:
        return keys[0] in classify_pillars(t)
    return any(k in t for k in keys)


SEGMENTS: dict[str, dict[str, Any]] = {
    "urban_commuters": {"label": "Urban commuters", "match": ("commut", "city", "urban", "bag", "lock", "light"),
                        "problems": ["rain and darkness on the daily route", "carrying laptop + groceries", "theft at stations"],
                        "habits": "buys practical upgrades after a bad-weather week; compares on durability and look",
                        "equipment": ["backpack", "lock", "lights", "rain shell"], "unmet": ["one system that works on bike, scooter and on foot"],
                        "price_sensitivity": "medium", "genres": ["urban_commuter", "scandi_minimal", "tactical_utility"],
                        "subscriptions": "low (wear parts, seasonal refresh)", "community": "commuter route groups"},
    "escooter_owners": {"label": "E-scooter owners", "match": ("scooter", "elsparkcykel"), "problems": ["no storage on the stem", "phone mounting", "rain, puddles, punctures", "night visibility"],
                        "habits": "accessorises in the first months after purchase; searches by scooter model", "equipment": ["phone mount", "stem bag", "lock", "lights"],
                        "unmet": ["model-verified accessory bundles", "winter-capable kit"], "price_sensitivity": "medium-high",
                        "genres": ["urban_commuter", "cyberpunk", "tactical_utility"], "subscriptions": "low (tyre sealant, wear parts)", "community": "model owner groups and forums"},
    "ebike_commuters": {"label": "E-bike commuters", "match": ("e-bike", "ebike", "bike", "pannier", "cykel"), "problems": ["battery range in cold", "carrying loads", "theft", "charging at work"],
                        "habits": "invests in quality carry systems; values compatibility with existing racks", "equipment": ["panniers", "frame bag", "lights", "lock"],
                        "unmet": ["battery covers for winter", "modular rack-to-backpack carry"], "price_sensitivity": "medium",
                        "genres": ["urban_commuter", "nordic_survival", "scandi_minimal"], "subscriptions": "service plans", "community": "commuter clubs"},
    "outdoor_enthusiasts": {"label": "Outdoor enthusiasts", "match": ("outdoor", "hike", "trail", "camp"), "problems": ["weight vs. durability", "wet gear"],
                            "habits": "reads reviews and spec tables; buys before season", "equipment": ["pack", "shell", "stove", "lamp"],
                            "unmet": ["Nordic-weather-tested kit info in Swedish"], "price_sensitivity": "medium", "genres": ["outdoor_adventure", "nordic_survival", "celestial_cartography"],
                            "subscriptions": "trip-prep kits", "community": "hiking clubs (e.g. friluftsfrämjandet-style associations)"},
    "bushcraft": {"label": "Bushcraft hobbyists", "match": ("bushcraft", "fire", "ferro", "knife", "axe", "tarp", "cordage"), "problems": ["finding authentic, durable tools", "learning skills safely"],
                  "habits": "values craft and provenance; watches long-form tutorials", "equipment": ["knife", "axe", "firesteel", "tarp"],
                  "unmet": ["Swedish-language skill content tied to gear"], "price_sensitivity": "low-medium", "genres": ["artisan", "norse_myth", "botanical_illustration"],
                  "subscriptions": "skill courses, consumables (tinder)", "community": "courses and meetups"},
    "hikers": {"label": "Hikers", "match": ("hike", "trail", "trekking"), "problems": ["pack weight", "navigation", "blisters & weather"], "habits": "plans trips months ahead",
               "equipment": ["boots", "pack", "map/GPS"], "unmet": ["route-specific kit lists"], "price_sensitivity": "medium",
               "genres": ["outdoor_adventure", "celestial_cartography"], "subscriptions": "route guides", "community": "trail communities"},
    "campers": {"label": "Campers", "match": ("camp", "tent", "stove", "lantern"), "problems": ["setup time", "cold nights"], "habits": "family purchases before summer",
                "equipment": ["tent", "stove", "lantern"], "unmet": ["family-friendly winter camping kits"], "price_sensitivity": "medium-high",
                "genres": ["outdoor_adventure", "vintage_americana"], "subscriptions": "low", "community": "camping sites"},
    "preparedness": {"label": "Preparedness-minded households", "match": ("emergency", "preparedness", "radio", "water", "solar", "blanket", "kris"),
                     "problems": ["power outages", "not knowing what to store", "kits that expire unnoticed"], "habits": "buys after news events; wants checklists",
                     "equipment": ["radio", "water storage", "lighting", "power"], "unmet": ["calm, well-designed home kits that remind you to refresh"],
                     "price_sensitivity": "medium", "genres": ["nordic_survival", "scandi_minimal", "secret_archive"],
                     "subscriptions": "kit refresh service (natural fit)", "community": "neighbourhood preparedness (avoid fear marketing)"},
    "nordic_winter_commuters": {"label": "Nordic winter commuters", "match": ("winter", "reflect", "studded", "cold", "dark"), "problems": ["darkness 15+ hours", "ice", "battery drain", "cold hands"],
                                "habits": "buys in Oct–Nov when darkness arrives", "equipment": ["studded tyres", "lights", "reflectors", "gloves"],
                                "unmet": ["integrated winter commute system"], "price_sensitivity": "medium", "genres": ["nordic_survival", "urban_commuter", "norse_myth"],
                                "subscriptions": "seasonal refresh", "community": "winter-cycling groups"},
    "travellers": {"label": "Travellers", "match": ("travel", "passport", "organiser", "organizer"), "problems": ["chaotic bags", "charging on the move"],
                   "habits": "buys before trips", "equipment": ["organisers", "power bank"], "unmet": ["rail-travel-specific organisation"], "price_sensitivity": "medium",
                   "genres": ["expedition_nomad", "minimal_premium"], "subscriptions": "low", "community": "travel forums"},
    "diy": {"label": "DIY enthusiasts", "match": ("diy", "repair", "tool", "maker"), "problems": ["tool chaos", "finding spare parts"], "habits": "buys tools project by project",
            "equipment": ["tool kit", "storage"], "unmet": ["repair kits with guides"], "price_sensitivity": "medium", "genres": ["diy_maker", "industrial"],
            "subscriptions": "consumables", "community": "makerspaces"},
    "tradespeople": {"label": "Tradespeople", "match": ("work", "trade", "tool", "jobsite", "van"), "problems": ["van organisation", "lost tools", "durability"],
                     "habits": "buys through merchants; values warranties", "equipment": ["tool bags", "organisers", "lighting"], "unmet": ["modular van-to-site carry"],
                     "price_sensitivity": "low (if it lasts)", "genres": ["industrial", "tactical_utility"], "subscriptions": "B2B replenishment", "community": "trade forums"},
    "minimalist_edc": {"label": "Minimalist EDC users", "match": ("edc", "wallet", "keychain", "pouch", "flashlight"), "problems": ["pocket bulk", "quality vs. weight"],
                       "habits": "deep research, community recommendations", "equipment": ["light", "multitool", "wallet", "pen"], "unmet": ["coherent design language across carry"],
                       "price_sensitivity": "low-medium", "genres": ["minimal_premium", "secret_archive", "tactical_utility"], "subscriptions": "limited drops",
                       "community": "EDC communities (forums, Reddit)"},
    "off_grid": {"label": "Off-grid hobbyists", "match": ("solar", "off-grid", "power station", "water", "cabin"), "problems": ["energy autonomy", "water"],
                 "habits": "buys systems over time", "equipment": ["solar", "batteries", "water storage"], "unmet": ["cabin-scale kits with Nordic sizing"],
                 "price_sensitivity": "low-medium", "genres": ["expedition_nomad", "nordic_survival"], "subscriptions": "maintenance", "community": "cabin owner networks"},
    "cyclists": {"label": "Cyclists (sport & touring)", "match": ("cycling", "bike", "touring", "saddle"), "problems": ["bikepacking storage", "repairs on route"],
                 "habits": "upgrades components regularly", "equipment": ["bags", "pump", "tools"], "unmet": ["Nordic touring kits"], "price_sensitivity": "medium",
                 "genres": ["sport_performance", "outdoor_adventure"], "subscriptions": "service", "community": "clubs"},
    "outdoor_photographers": {"label": "Outdoor photographers", "match": ("camera", "photo", "drone", "tripod"), "problems": ["battery life in cold", "weatherproof carry"],
                              "habits": "spends on reliability", "equipment": ["camera bag", "batteries", "filters"], "unmet": ["cold-weather battery management"],
                              "price_sensitivity": "low", "genres": ["expedition_nomad", "celestial_cartography"], "subscriptions": "location guides", "community": "photo communities"},
}

ECOSYSTEMS: dict[str, dict[str, Any]] = {
    "edc_modular": {"label": "Modular EDC system", "modules": [
        ("main_pack", "Main backpack", ("backpack", "pack")), ("organiser", "Detachable organiser", ("organiser", "organizer")),
        ("dry_pouch", "Waterproof pouch", ("waterproof", "dry bag", "pouch")), ("first_aid", "First-aid module", ("first aid", "first-aid")),
        ("electronics", "Electronics module", ("cable", "power bank", "charger")), ("tools", "Tool module", ("multi-tool", "multitool", "tool")),
        ("battery", "Battery organiser", ("battery",)), ("bike_mount", "Bicycle attachment", ("bike", "bicycle")),
        ("scooter_mount", "Scooter attachment", ("scooter",)), ("travel", "Travel organiser", ("travel", "passport"))]},
    "nordic_survival": {"label": "Nordic survival system", "modules": [
        ("winter_kit", "Winter preparedness kit", ("winter", "thermal", "blanket")), ("lighting", "Compact lighting system", ("headlamp", "lantern", "flashlight", "light")),
        ("power", "Emergency power kit", ("power bank", "solar", "power station")), ("storage", "Waterproof storage", ("waterproof", "dry bag")),
        ("repair", "Outdoor repair kit", ("repair",)), ("vehicle", "Vehicle preparedness kit", ("vehicle", "car"))]},
    "mobility_commuter": {"label": "E-mobility commuter system", "modules": [
        ("commuter", "Commuter kit (bag + mount)", ("bag", "pannier", "mount")), ("winter", "Winter riding kit", ("winter", "glove", "studded")),
        ("touring", "Touring kit", ("touring", "frame bag", "saddle bag")), ("night", "Night riding kit", ("light", "reflect")),
        ("repair", "Repair kit", ("repair", "pump", "tyre", "tire")), ("theft", "Theft-prevention kit", ("lock", "alarm", "tracker"))]},
}
MOUNTING_STANDARDS = [
    {"id": "handlebar_22_2", "name": "Handlebar Ø22.2 mm clamp", "applies": "many scooters and flat-bar bikes", "verify": "measure bar at clamp position"},
    {"id": "handlebar_31_8", "name": "Handlebar Ø31.8 mm clamp", "applies": "many modern bikes (centre section)", "verify": "check clamp zone vs. cables/display"},
    {"id": "stem_round", "name": "Round stem strap mount (Ø30–45 mm)", "applies": "most e-scooter stems", "verify": "check folding mechanism clearance"},
    {"id": "rack_mik_like", "name": "Rack-top quick-release plate (proprietary systems vary)", "applies": "rear racks", "verify": "systems are brand-specific — test each"},
    {"id": "webbing_25mm", "name": "25 mm webbing / PALS-style grid", "applies": "bags, packs, frames", "verify": "load test of attachment"},
    {"id": "tripod_1_4", "name": "1/4\"-20 thread", "applies": "lights, cameras, phone mounts", "verify": "thread depth and vibration loosening"},
    {"id": "bottle_cage", "name": "Bottle-cage bolts (64 mm spacing)", "applies": "most bike frames", "verify": "frame bosses present; e-bike battery clearance"},
]
DOC_REQUIREMENTS = {  # compliance category -> documents to demand from suppliers
    "electronics": ["EU Declaration of Conformity", "LVD/EMC test reports", "RoHS declaration"],
    "batteries": ["UN38.3 test summary", "IEC 62133 report", "battery labelling plan"],
    "e_mobility_vehicle": ["EN 15194 or EN 17128 test report", "DoC", "battery & charger reports"],
    "vehicle_safety_component": ["strength/fatigue test (e.g. ISO 4210 part)", "per-model fitment list"],
    "helmets_ppe": ["EU type-examination certificate", "EN 1078 / EN ISO 20471 report"],
    "water_treatment": ["microbiological test report", "BPR authorisation (if chemical)"],
    "first_aid_medical": ["CE/MDR documentation per medical item"],
    "fire_and_fuel": ["EN 417 / EN 13869 certificates", "SDS and transport classification"],
    "radio_communication": ["RED DoC", "frequency/power specification"],
    "food_contact": ["Declaration of Compliance", "migration test"],
    "blades": ["material spec", "lock/sheath safety test"],
}
REGION_PRIORITY = {"SE": 4, "NO": 3, "DK": 3, "FI": 3, "IS": 3}
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DE", "EE", "ES", "FR", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI"}


def match_segments(text: str) -> list[dict[str, Any]]:
    t = text.lower()
    out = []
    for sid, s in SEGMENTS.items():
        hits = [m for m in s["match"] if m in t]
        if hits:
            out.append({"id": sid, "label": s["label"], "fit": min(1.0, 0.3 + 0.2 * len(hits)), "matched_on": hits,
                        **{k: s[k] for k in ("problems", "unmet", "price_sensitivity", "genres", "subscriptions", "community", "habits", "equipment")},
                        "epistemic": "hypothesis", "validate_with": "customer interviews, search data, review mining"})
    out.sort(key=lambda x: x["fit"], reverse=True)
    return out


def build_ecosystem(template: str, products: list[Any]) -> dict[str, Any]:
    eco = ECOSYSTEMS[template]
    modules = []
    for mid, label, kws in eco["modules"]:
        filled = [{"product_id": p.id, "name": p.name, "is_demo": p.is_demo} for p in products
                  if any(k in f"{p.name} {p.category} {' '.join(p.tags or [])}".lower() for k in kws)]
        modules.append({"id": mid, "label": label, "status": "covered" if filled else "gap (proposed module)", "products": filled[:5]})
    edges = []
    prev = None
    for m in modules:
        if prev:
            edges.append({"source": prev, "target": m["id"], "relation": "bundles_with"})
        prev = m["id"]
    return {"template": template, "label": eco["label"], "modules": modules,
            "mounting_standards": MOUNTING_STANDARDS if template in ("mobility_commuter", "edc_modular") else [],
            "coverage": round(sum(1 for m in modules if m["products"]) / len(modules), 2), "edges": edges,
            "note": "Module fit and mount compatibility are unverified until tested on named models."}


def recommend_ecosystems(text: str) -> list[str]:
    t = text.lower()
    out = []
    if re.search(r"scooter|bike|cykel|pannier|handlebar|commut", t):
        out.append("mobility_commuter")
    if re.search(r"winter|survival|emergency|thermal|solar|power|lantern|preparedness", t):
        out.append("nordic_survival")
    if re.search(r"edc|pouch|organi[sz]er|multi|backpack|flashlight|wallet", t) or not out:
        out.append("edc_modular")
    return out


def sourcing_assessment(product_text: str, suppliers: list[Any]) -> list[dict[str, Any]]:
    cats = compliance.assess(product_text).categories
    needed = sorted({d for c in cats for d in DOC_REQUIREMENTS.get(c, [])})
    rows = []
    for s in suppliers:
        cc = (s.country or "").upper()[:2]
        region = REGION_PRIORITY.get(cc, 2 if (cc in EU or s.eu_based) else 1)
        have = {c.lower() for c in (s.certifications or [])}
        missing = [d for d in needed if not any(w in " ".join(have) for w in d.lower().split()[:2])]
        score = region * 15 + (s.reliability_score or 40) * 0.3 + (10 if s.spare_parts_available else 0) + min(10, (s.warranty_months or 0) / 2.4) \
            - 6 * len(missing) + (5 if s.qc_process else 0)
        rows.append({"supplier_id": s.id, "name": s.name, "country": s.country, "region_priority": region,
                     "region_label": {4: "Sweden", 3: "Nordic", 2: "EU", 1: "non-EU"}[region],
                     "documents_required": needed, "documents_missing": missing, "spare_parts": s.spare_parts_available,
                     "warranty_months": s.warranty_months, "score": round(score, 1), "is_demo": s.is_demo,
                     "safety_critical": bool({"e_mobility_vehicle", "vehicle_safety_component", "helmets_ppe", "batteries", "first_aid_medical"} & set(cats))})
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows
