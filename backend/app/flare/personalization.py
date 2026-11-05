"""Personalization without privacy invasion (§14).

A personalization offer may only use information the customer provides
voluntarily, for a stated purpose, with consent. The guard rejects inferred
fields, social-media-derived data and sensitive-category profiling (GDPR art. 9).
Customers may still *choose* meaningful content themselves (e.g. a verse or
symbol to engrave) — that is their own input, not a profile.
"""
from __future__ import annotations

from typing import Any

ALLOWED_SOURCES = {"customer_input"}
SENSITIVE = ("health", "religion", "religious_belief", "ethnicity", "race", "sexual_orientation", "political", "biometric", "genetic",
             "trade_union", "pregnancy", "disability", "income_vulnerability", "age_inferred")
MANIPULATIVE = ("urgency_by_profile", "price_by_profile", "vulnerability_targeting", "fear_targeting")


def validate_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    for f in fields:
        name = f.get("name", "?")
        if f.get("source") not in ALLOWED_SOURCES:
            errors.append(f"{name}: source '{f.get('source')}' not allowed — only data the customer enters themselves")
        if any(s in name.lower() or s == f.get("category") for s in SENSITIVE):
            errors.append(f"{name}: sensitive-category profiling is not allowed")
        if any(m in name.lower() for m in MANIPULATIVE):
            errors.append(f"{name}: manipulative personalization is not allowed")
        if not f.get("purpose"):
            errors.append(f"{name}: missing stated purpose")
        if f.get("source") == "customer_input" and f.get("stored") and not f.get("consent"):
            errors.append(f"{name}: storing customer input beyond the order requires consent")
    return {"valid": not errors, "errors": errors}


def offer(product_name: str, tags: list[str], supplier_can_personalise: bool) -> dict[str, Any]:
    fields = [
        {"name": "engraving_text", "source": "customer_input", "purpose": "engrave the product", "stored": False, "max_length": 24},
        {"name": "colourway", "source": "customer_input", "purpose": "choose colour", "stored": False},
        {"name": "kit_use_case", "source": "customer_input", "purpose": "recommend kit modules (commute / winter / touring)", "stored": False},
    ]
    if "giftable" in [t.lower() for t in tags]:
        fields.append({"name": "gift_message", "source": "customer_input", "purpose": "print gift card", "stored": False, "max_length": 200})
    check = validate_fields(fields)
    return {"product": product_name, "fields": fields, "validation": check,
            "status": "supplier_customization" if supplier_can_personalise else "proposed_modification",
            "rules": ["no inferred or scraped attributes", "no sensitive-category profiling", "no profile-based pricing or urgency",
                      "data used only for the order unless the customer consents to more"]}
