"""Product Transformation Lab (spec section 5) and Revenue Multiplication (section 13).

The deterministic generator guarantees >= 10 transformations per product across
all seven families (A–G). The Transformation agent can enrich these with an LLM
when one is configured; the deterministic set is always available and testable.
"""
from __future__ import annotations

import re
from typing import Any

FAMILIES = ("personalization", "improvement", "bundling", "private_label", "digital", "service", "content")


def generate(name: str, category: str = "", complaints: list[str] | None = None, tags: list[str] | None = None) -> list[dict[str, Any]]:
    n = name.strip() or "the product"
    # "Sourdough starter kit" -> "Sourdough" so templates don't produce "... starter kit starter kit"
    base = re.sub(r"\s+(starter\s+)?(kit|set|bundle)$", "", n, flags=re.IGNORECASE) or n
    tags_l = {t.lower() for t in (tags or [])}
    complaints = [c for c in (complaints or []) if c.strip()]
    ideas: list[dict[str, Any]] = [
        {"family": "personalization", "title": f"Personalised {n}",
         "concept": f"Offer name/initial engraving or print and a custom colour selector for {n}.",
         "value_driver": "higher perceived value and giftability", "effort": "low"},
        {"family": "personalization", "title": f"{n} gift edition",
         "concept": "Custom gift packaging with a personal message card and a QR code to a short personal video.",
         "value_driver": "gift premium", "effort": "low"},
        {"family": "bundling", "title": f"{base} starter kit",
         "concept": f"{n} plus the 2–3 accessories beginners otherwise buy separately, with a quick-start card.",
         "value_driver": "higher AOV, less decision friction", "effort": "low"},
        {"family": "bundling", "title": f"{base} pro kit",
         "concept": "Premium tier with upgraded accessories and spare parts for serious users.",
         "value_driver": "price anchoring and premium margin", "effort": "medium"},
        {"family": "bundling", "title": f"{n} refill / replenishment subscription",
         "concept": "Recurring delivery of consumables or wear parts at a member price.",
         "value_driver": "recurring revenue", "effort": "medium",
         "applies": "consumable" in tags_l or "accessories" in tags_l},
        {"family": "improvement", "title": "Better instructions & onboarding",
         "concept": "Clear illustrated Swedish/English manual and a 3-minute setup video — the most common gap in cheap listings.",
         "value_driver": "fewer returns, better reviews", "effort": "low"},
        {"family": "private_label", "title": f"Own-brand {n}",
         "concept": "Commission the supplier for an exclusive variant (colour/material/logo) under an original brand with designed packaging.",
         "value_driver": "defensible brand, margin", "effort": "high"},
        {"family": "digital", "title": f"The {n} guide",
         "concept": "Downloadable guide / template pack teaching how to get the best results.",
         "value_driver": "near-100% margin add-on", "effort": "low"},
        {"family": "digital", "title": f"{n} AI companion",
         "concept": "A small web assistant that answers setup and usage questions, sold as an upgrade or used for support deflection.",
         "value_driver": "differentiation, lower support cost", "effort": "medium"},
        {"family": "service", "title": "Setup / personalisation service",
         "concept": "Paid configuration, installation or personalisation for customers who want it done for them.",
         "value_driver": "service margin, local moat", "effort": "medium"},
        {"family": "content", "title": f"{category or n} buying guide & comparison site",
         "concept": "Independent comparison content with disclosed affiliate links; also feeds organic traffic to own products.",
         "value_driver": "low-capital traffic asset", "effort": "medium"},
        {"family": "content", "title": "Short-form educational channel",
         "concept": "Problem/solution and demo videos for TikTok, Reels and Shorts, owned by the brand.",
         "value_driver": "owned audience, lower CAC", "effort": "medium"},
    ]
    for c in complaints[:5]:
        ideas.append({"family": "improvement", "title": f"Fix: {c[:60]}",
                      "concept": f"Source or design a variant that solves the recurring complaint: '{c}'.",
                      "value_driver": "differentiation from incumbents", "effort": "medium", "evidence": c})
    out = [i for i in ideas if i.pop("applies", True)]
    for i in out:
        i["epistemic"] = "hypothesis"
    return out


REVENUE_MULTIPLIERS = (
    ("accessories", "Can we sell accessories?"),
    ("replacement_parts", "Can we sell replacement parts?"),
    ("premium_version", "Can we create a premium version?"),
    ("budget_version", "Can we create a cheaper version?"),
    ("bundle", "Can we sell a bundle?"),
    ("subscription", "Can we create a subscription?"),
    ("education", "Can we sell educational material?"),
    ("digital_complement", "Can we create a complementary digital product?"),
    ("licensing", "Can we license the design?"),
    ("b2b", "Can we sell to businesses?"),
    ("maintenance", "Can we establish recurring maintenance?"),
    ("community", "Can we build a community around the product?"),
    ("application", "Can we create a specialised application?"),
    ("marketplace", "Can we create a marketplace around the niche?"),
)


def revenue_multiplication_questions(product_name: str) -> list[dict[str, str]]:
    return [{"id": k, "question": q, "product": product_name, "status": "open"} for k, q in REVENUE_MULTIPLIERS]
