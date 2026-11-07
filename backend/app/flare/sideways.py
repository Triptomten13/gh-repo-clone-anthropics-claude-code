"""THINK SIDEWAYS — the Unexpected Opportunity Engine (§7, Field Ops §11).

Deliberately searches *outside* the product's own category: domains are scored
by how far they are from the product (distance) and how strongly a shared
product trait connects them (bridge). Every suggestion names its bridge, so the
reasoning can be checked. Output is labelled hypothesis.
"""
from __future__ import annotations

import re
from typing import Any

from .schemas import GraphEdgeOut, SidewaysCombo, SidewaysItem

# product trait detectors
TRAITS: dict[str, tuple[str, ...]] = {
    "portable": ("portable", "compact", "pocket", "travel", "edc", "bag", "pouch", "kit", "bottle", "lamp", "light", "bank"),
    "organising": ("organiser", "organizer", "pouch", "case", "storage", "box", "pannier", "modular", "bag"),
    "lighting": ("light", "lamp", "led", "lantern", "headlamp", "flashlight", "reflect"),
    "power": ("power", "battery", "solar", "charger", "usb"),
    "weatherproof": ("waterproof", "weather", "rain", "winter", "insulated", "roll-top"),
    "personalisable": ("personal", "engrav", "custom", "initial", "embroider", "monogram"),
    "giftable": ("gift", "set", "kit", "edition", "personal"),
    "skill_based": ("bushcraft", "sourdough", "craft", "repair", "maintenance", "tool", "kit", "coffee", "garden"),
    "safety": ("safety", "emergency", "first aid", "reflect", "visibility", "helmet", "lock"),
    "outdoor": ("outdoor", "camp", "trail", "hike", "bushcraft", "tarp", "fire"),
    "mobility": ("bike", "scooter", "cycling", "commut", "pannier", "handlebar"),
    "aesthetic": ("design", "ceramic", "linen", "leather", "brass", "wood"),
    "consumable": ("refill", "filter", "tinder", "fuel", "tablet", "consumable", "patch", "tape"),
    "care": ("sleep", "wellness", "care", "comfort", "warm"),
}

# domain -> traits it values, and opportunity seeds per category
DOMAINS: dict[str, dict[str, Any]] = {
    "pets": {"traits": ("portable", "lighting", "safety", "personalisable", "weatherproof", "care"), "groups": "dog owners walking in winter darkness",
             "uses": "night-walk visibility for dog and owner", "complements": "reflective leash and collar set", "services": "custom pet-ID engraving",
             "digital": "walk-route and darkness-hours planner", "recurring": "seasonal pet-care refill box", "channels": "veterinary clinics and dog-day-care counters",
             "identity": "Nordic dog-walk equipment house"},
    "home_design": {"traits": ("aesthetic", "organising", "lighting", "giftable"), "groups": "interior-design buyers who hate visible clutter",
                    "uses": "display-worthy storage for gear at home", "complements": "wall rail with modular hooks", "services": "home gear-wall styling consultation",
                    "digital": "printable gear-wall layout planner", "recurring": "quarterly design-object drop", "channels": "interior concept stores and design fairs",
                    "identity": "gallery-grade utility objects"},
    "photography": {"traits": ("portable", "organising", "weatherproof", "power", "lighting"), "groups": "outdoor and drone photographers",
                    "uses": "weatherproof carry for batteries, cards and filters", "complements": "battery and SD-card organiser", "services": "location-scouting trips",
                    "digital": "golden-hour + weather location app for shoots", "recurring": "photo-location guide membership", "channels": "camera stores and photo workshops",
                    "identity": "field kit for image makers"},
    "education": {"traits": ("skill_based", "safety", "outdoor"), "groups": "schools and scout groups running outdoor education",
                  "uses": "class sets for outdoor learning days", "complements": "illustrated field-guide cards", "services": "teacher training workshops",
                  "digital": "lesson plans and printable worksheets", "recurring": "term-based kit rental for schools", "channels": "school procurement and scout shops",
                  "identity": "outdoor classroom outfitter"},
    "hospitality": {"traits": ("aesthetic", "giftable", "outdoor", "care"), "groups": "cabin rentals and glamping hosts",
                    "uses": "guest welcome kits in rental cabins", "complements": "branded guest-guide booklet", "services": "white-label guest kits for hosts",
                    "digital": "host-branded digital welcome guide", "recurring": "restock subscription for hosts", "channels": "Airbnb host communities and cabin-rental agencies",
                    "identity": "hospitality-grade outdoor amenities"},
    "workplace_b2b": {"traits": ("safety", "organising", "lighting", "power"), "groups": "tradespeople and field-service technicians",
                      "uses": "van and jobsite organisation", "complements": "vehicle-mount organiser", "services": "fleet kitting for service companies",
                      "digital": "inventory checklist app for vans", "recurring": "B2B replenishment contracts", "channels": "builders' merchants and workwear distributors",
                      "identity": "trade-grade field supply"},
    "events_festivals": {"traits": ("portable", "lighting", "power", "weatherproof", "aesthetic"), "groups": "festival-goers and event crews",
                         "uses": "multi-day festival survival kit", "complements": "phone power + rain poncho bundle", "services": "on-site charging & locker service",
                         "digital": "festival-packing checklist", "recurring": "season pass bundles", "channels": "festival merch partnerships",
                         "identity": "festival field-supply brand"},
    "gaming_fandom": {"traits": ("aesthetic", "personalisable", "giftable"), "groups": "gamers and fantasy-world fans",
                      "uses": "lore-themed collector editions of practical gear", "complements": "collector box and art print", "services": "custom lore engraving",
                      "digital": "ARG / story companion", "recurring": "limited-edition drop club", "channels": "game conventions and creator collabs",
                      "identity": "story-world equipment house (original IP only)"},
    "fitness": {"traits": ("portable", "care", "safety", "weatherproof"), "groups": "runners and rucking/fitness walkers",
                "uses": "weighted rucking and night-run visibility", "complements": "reflective run vest", "services": "guided ruck-march events",
                "digital": "training plans for rucking", "recurring": "monthly challenge kit", "channels": "running clubs and gyms", "identity": "endurance utility brand"},
    "elder_care": {"traits": ("safety", "lighting", "care", "organising"), "groups": "adult children equipping elderly parents' homes",
                   "uses": "home-preparedness for power outages", "complements": "large-button emergency light", "services": "home preparedness check-up visits",
                   "digital": "family preparedness checklist", "recurring": "battery and supplies refresh service", "channels": "pharmacies and home-care services",
                   "identity": "calm home-readiness brand"},
    "gardening": {"traits": ("outdoor", "skill_based", "organising", "consumable"), "groups": "allotment and balcony gardeners",
                  "uses": "tool organisation on the allotment", "complements": "seed and tool roll", "services": "seasonal garden setup",
                  "digital": "planting calendar for Nordic zones", "recurring": "seasonal seed + consumables box", "channels": "garden centres and koloni associations",
                  "identity": "field-craft for growers"},
    "travel": {"traits": ("portable", "organising", "power", "weatherproof"), "groups": "rail and backpack travellers in the Nordics",
               "uses": "night-train and hostel organisation", "complements": "travel power + document organiser", "services": "trip-prep kit assembly",
               "digital": "packing list generator by trip type", "recurring": "travel essentials refill", "channels": "travel bookstores and rail-pass partners",
               "identity": "Nordic rail-nomad supply"},
    "vehicle_overlanding": {"traits": ("power", "outdoor", "organising", "safety", "weatherproof"), "groups": "van-lifers and car campers",
                            "uses": "vehicle emergency and camp organisation", "complements": "vehicle winter-emergency module", "services": "van fit-out consultation",
                            "digital": "winter road-trip safety checklist", "recurring": "seasonal vehicle-kit refresh", "channels": "car accessory retailers and van-life meetups",
                            "identity": "overland readiness outfitter"},
    "creative_makers": {"traits": ("skill_based", "organising", "aesthetic", "personalisable"), "groups": "makers, illustrators and crafters",
                        "uses": "tool rolls and studio organisation", "complements": "maker's apron and tool roll", "services": "custom workshop-wall builds",
                        "digital": "printable project templates", "recurring": "maker materials subscription", "channels": "craft fairs and makerspaces",
                        "identity": "studio utility goods"},
    "music_audio": {"traits": ("portable", "power", "organising", "aesthetic"), "groups": "touring musicians and DJs",
                    "uses": "cable, adapter and power organisation on tour", "complements": "cable organiser + power module", "services": "tour-kit assembly",
                    "digital": "gig-packing checklist", "recurring": "consumables (strings, batteries) refill", "channels": "music stores and rehearsal studios",
                    "identity": "road-crew supply"},
    "corporate_gifting": {"traits": ("giftable", "personalisable", "aesthetic"), "groups": "HR teams buying meaningful employee gifts",
                          "uses": "branded preparedness or outdoor kits as gifts", "complements": "personal card + guide", "services": "co-branded gift programmes",
                          "digital": "recipient choice portal", "recurring": "annual gift programme", "channels": "B2B gifting platforms and HR networks",
                          "identity": "meaningful corporate gift house"},
}
CATEGORY_LABELS = {"groups": "alternative customer group", "uses": "alternative use case", "complements": "complementary product",
                   "services": "potential service", "digital": "digital extension", "recurring": "recurring revenue",
                   "channels": "unusual distribution channel", "identity": "possible brand identity"}

CHALLENGES: list[dict[str, str]] = [
    {"id": "nordic_scooter_ecosystem", "text": "Turn a standard e-scooter into a complete Nordic commuter ecosystem.", "engine": "ecosystem:mobility_commuter+nordic"},
    {"id": "modular_survival", "text": "Find five survival accessories that could be improved through modular design.", "engine": "innovation:modular"},
    {"id": "manuscript_edc", "text": "Create a premium EDC collection inspired by ancient manuscripts.", "engine": "fusion:tactical_utility+illuminated_manuscript"},
    {"id": "bushcraft_cycling_prep", "text": "Find products that connect bushcraft, cycling, and emergency preparedness.", "engine": "bridge:outdoor,mobility,safety"},
    {"id": "shepherd_of_eden", "text": "Build a product family around the concept of the Shepherd of Eden.", "engine": "fusion:outdoor_adventure+biblical_heritage"},
    {"id": "ebike_overlooked", "text": "Find ten overlooked accessories for electric bicycles.", "engine": "ecosystem:mobility_commuter"},
    {"id": "winter_commute", "text": "Create a weatherproof winter commuting system.", "engine": "ecosystem:mobility_commuter+nordic"},
    {"id": "premium_emergency", "text": "Transform a standard emergency kit into a recognizable premium brand.", "engine": "fusion:nordic_survival+luxury"},
    {"id": "edc_community", "text": "Find ways to monetize the EDC community beyond selling physical products.", "engine": "commercial:audience_monetization"},
    {"id": "cartography_survival", "text": "Combine ancient cartography, futuristic industrial design, and practical survival equipment.", "engine": "fusion:celestial_cartography+future_tech+tactical_utility"},
    {"id": "ordinary_extraordinary", "text": "Find ordinary products that could become extraordinary through customization.", "engine": "mutation:personalization"},
]

QUESTION_MODES = [
    (r"what else|else could|become", "full"), (r"unexpected market|markets", "markets"), (r"premium|luxury", "premium"),
    (r"ecosystem", "ecosystem"), (r"nobody|business model|not using", "unused_model"), (r"identit|radically", "identities"),
    (r"audience rather|monetize the audience|monetise the audience", "audience"),
]


def product_traits(text: str) -> dict[str, int]:
    t = text.lower()
    return {k: sum(1 for kw in kws if kw in t) for k, kws in TRAITS.items() if any(kw in t for kw in kws)}


def classify_question(q: str) -> str:
    for pat, mode in QUESTION_MODES:
        if re.search(pat, q.lower()):
            return mode
    return "full"


def think_sideways(name: str, text: str, own_tags: set[str] | None = None, margin: float | None = None,
                   n_domains: int = 5) -> dict[str, Any]:
    traits = product_traits(f"{name} {text}")
    own = {t.lower() for t in (own_tags or set())}
    own_domain_hint = {"pet": "pets", "garden": "gardening", "fitness": "fitness", "travel": "travel", "music": "music_audio",
                       "photo": "photography", "home": "home_design"}
    excluded = {own_domain_hint[t] for t in own if t in own_domain_hint}
    scored = []
    for d, spec in DOMAINS.items():
        if d in excluded:
            continue
        shared = [t for t in spec["traits"] if t in traits]
        bridge = sum(traits[t] for t in shared)
        if not shared:
            continue
        scored.append((bridge + 0.5 * len(shared), d, shared))
    scored.sort(reverse=True)
    picked = scored[:n_domains]
    items: list[SidewaysItem] = []
    for cat, label in CATEGORY_LABELS.items():
        for score, d, shared in picked:
            items.append(SidewaysItem(category=label, text=DOMAINS[d][cat], domain=d, bridge=" + ".join(shared),
                                      reasoning=[f"shares '{', '.join(shared)}' with the product"], confidence=round(min(0.7, 0.25 + 0.08 * score), 2)))
    combos: list[SidewaysCombo] = []
    for score, d, shared in picked:
        recurring_bonus = 15 if "consumable" in traits or "skill_based" in traits else 5
        potential = min(100.0, 30 + 8 * score + recurring_bonus + (20 * margin if margin else 0))
        combos.append(SidewaysCombo(title=f"{DOMAINS[d]['identity']} × {DOMAINS[d]['recurring']}", customer_group=DOMAINS[d]["groups"],
                                    recurring=DOMAINS[d]["recurring"], channel=DOMAINS[d]["channels"], potential=round(potential, 1),
                                    reasoning=[f"bridge: {', '.join(shared)}", "recurring element present" if recurring_bonus > 5 else "recurring element needs validation"],
                                    confidence=0.35))
    combos.sort(key=lambda c: c.potential, reverse=True)
    edges = [GraphEdgeOut(source="product", target=f"domain:{d}", relation="bridge", note=" + ".join(shared)) for _, d, shared in picked]
    for _, d, _s in picked:
        for cat in ("groups", "recurring", "digital"):
            edges.append(GraphEdgeOut(source=f"domain:{d}", target=f"{d}:{cat}", relation=CATEGORY_LABELS[cat]))
    return {"traits": traits, "domains": [{"domain": d, "bridge": shared, "strength": round(s, 1)} for s, d, shared in picked],
            "items": [i.model_dump() for i in items], "high_potential": [c.model_dump() for c in combos[:3]],
            "graph_edges": [e.model_dump() for e in edges], "epistemic": "hypothesis",
            "note": "Cross-industry ideas are hypotheses from trait bridges — validate demand before investing."}
