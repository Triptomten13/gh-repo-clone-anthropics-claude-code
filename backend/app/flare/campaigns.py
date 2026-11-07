"""Creative Marketing Intelligence (§9): campaign identities, testing matrix, budget
recommendations, and the creative analyst that ranks by contribution — not likes.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import originality as O
from .schemas import CampaignCell
from .taxonomy import GENRES

IDENTITIES: dict[str, dict[str, Any]] = {
    "funny_self_aware": {"label": "Funny & self-aware", "hook": "Things {audience} pretend not to carry (until it rains).", "video": "skit → product reveal (15s)",
                         "platforms": ("tiktok", "instagram_reels"), "genres": ("pop_playful", "streetwear", "nostalgic_retro", "urban_commuter")},
    "premium_elegant": {"label": "Premium & elegant", "hook": "Made slowly. Built for {problem}.", "video": "macro material close-ups (10s)",
                        "platforms": ("instagram_reels", "pinterest"), "genres": ("luxury", "minimal_premium", "scandi_minimal", "artisan", "illuminated_manuscript")},
    "underground_rebellious": {"label": "Underground & rebellious", "hook": "Not sold in malls. Not for everyone.", "video": "raw handheld POV (12s)",
                               "platforms": ("tiktok", "youtube_shorts"), "genres": ("underground", "cyberpunk", "streetwear", "surveillance_dystopia", "techno_occult")},
    "educational_practical": {"label": "Educational & practical", "hook": "3 mistakes {audience} make with {product}.", "video": "tutorial with captions (30–45s)",
                              "platforms": ("youtube_shorts", "tiktok", "google_search"), "genres": ("diy_maker", "outdoor_adventure", "nordic_survival", "botanical_illustration")},
    "technical_professional": {"label": "Technical & professional", "hook": "Spec sheet in 20 seconds: {product}.", "video": "spec overlay demo (20s)",
                               "platforms": ("youtube_shorts", "google_search", "meta"), "genres": ("industrial", "tactical_utility", "sport_performance", "future_tech")},
    "emotional_lifestyle": {"label": "Emotional & lifestyle", "hook": "The commute you look forward to.", "video": "day-in-the-life montage (20s)",
                            "platforms": ("instagram_reels", "meta"), "genres": ("scandi_minimal", "organic_botanical", "japanese", "vintage_americana", "western")},
    "experimental_striking": {"label": "Experimental & visually striking", "hook": "You've never seen {product} like this.", "video": "stop-motion / visual loop (8s)",
                              "platforms": ("tiktok", "instagram_reels"), "genres": ("experimental_art", "psychedelic", "retro_futurism", "sacred_geometry", "alchemy_hermetic")},
    "community_hobby": {"label": "Community & hobby", "hook": "Show us your setup: {audience} edition.", "video": "community setups compilation (25s)",
                        "platforms": ("instagram_reels", "youtube_shorts", "reddit_organic"), "genres": ("diy_maker", "dark_academia", "norse_myth", "celestial_cartography", "secret_archive")},
}
MIN_TEST_ORDERS = 20


def test_budget(break_even_cac: float | None) -> float | None:
    """Enough spend to observe ~20 orders at break-even CAC — the minimum for a decision."""
    if not break_even_cac or break_even_cac <= 0:
        return None
    return round(MIN_TEST_ORDERS * break_even_cac, -1)


def testing_matrix(product_name: str, genre_ids: list[str], audience: str, problem: str, break_even_cac: float | None,
                   learned_identity: dict[str, float] | None = None, n_identities: int = 4, platforms_per: int = 2) -> list[CampaignCell]:
    learned_identity = learned_identity or {}
    scores = []
    for iid, spec in IDENTITIES.items():
        fit = sum(1.0 for g in genre_ids if g in spec["genres"]) + 0.3 * sum(GENRES[g].video_fit for g in genre_ids if g in GENRES) / max(1, len(genre_ids))
        adj = max(-1.0, min(1.0, learned_identity.get(iid, 0.0) / 10))
        scores.append((fit + adj, iid, adj))
    scores.sort(reverse=True)
    budget = test_budget(break_even_cac)
    cells = []
    noun = product_name.lower()
    for fit, iid, adj in scores[:n_identities]:
        spec = IDENTITIES[iid]
        hook = spec["hook"].format(audience=audience.split(" — ")[0] or "commuters", product=noun, problem=problem)
        flags = [f["detail"] for f in O.check_text(hook, "hook")]
        genre = next((g for g in genre_ids if g in spec["genres"]), genre_ids[0] if genre_ids else "")
        for platform in spec["platforms"][:platforms_per]:
            cells.append(CampaignCell(
                identity=iid, platform=platform, target_audience=audience, creative_genre=GENRES[genre].name if genre in GENRES else genre,
                hook=hook, main_message=f"{product_name}: built for {problem}. Claims limited to what has been tested.",
                visual_concept=(GENRES[genre].photography if genre in GENRES else "product in real use"), video_format=spec["video"],
                call_to_action="See the full spec" if iid == "technical_professional" else "Shop the kit",
                budget_recommendation_sek=budget,
                measurement={"primary": "contribution per order and CAC vs. break-even CAC", "secondary": "conversion rate",
                             "diagnostic": "hook rate, CTR (never optimise on likes alone)",
                             "decision_rule": f"≥{MIN_TEST_ORDERS} orders or budget exhausted, then scale / iterate / abandon"},
                flags=flags, reasoning=[f"identity fit {fit:.2f} with genres {', '.join(genre_ids)}"] + ([f"learned adjustment {adj:+.2f}"] if adj else []),
                confidence=0.4 + (0.2 if adj else 0), epistemic="hypothesis",
            ))
    return cells


def analyse(campaigns: list[Any], performance: list[Any], unit_contribution: dict[int, float] | None = None) -> dict[str, Any]:
    """Rank campaigns and creative identities by contribution after ad spend; compare with engagement ranking."""
    unit_contribution = unit_contribution or {}
    per: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in performance:
        d = per[r.campaign_id]
        d["impressions"] += r.impressions
        d["clicks"] += r.clicks
        d["engagements"] += r.engagements
        d["spend"] += r.spend
        d["orders"] += r.orders
        d["revenue"] += r.revenue
        if r.contribution is not None:
            d["contribution"] += r.contribution
        else:
            d["contribution"] += r.orders * unit_contribution.get(r.campaign_id, 0.0)
            d["estimated"] = 1
    rows = []
    for c in campaigns:
        if c.id not in per:
            continue
        d = per[c.id]
        profit = d["contribution"] - d["spend"]
        rows.append({"campaign_id": c.id, "name": c.name, "identity": c.identity, "genre": c.genre, "platform": c.platform,
                     "spend": round(d["spend"], 2), "orders": int(d["orders"]), "engagements": int(d["engagements"]),
                     "ctr": round(d["clicks"] / d["impressions"], 4) if d["impressions"] else None,
                     "cvr": round(d["orders"] / d["clicks"], 4) if d["clicks"] else None,
                     "cac": round(d["spend"] / d["orders"], 2) if d["orders"] else None,
                     "roas": round(d["revenue"] / d["spend"], 2) if d["spend"] else None,
                     "contribution_after_ads": round(profit, 2), "profit_per_100_spend": round(100 * profit / d["spend"], 1) if d["spend"] else None,
                     "contribution_estimated": bool(d.get("estimated"))})
    by_profit = sorted(rows, key=lambda r: r["contribution_after_ads"], reverse=True)
    by_eng = sorted(rows, key=lambda r: r["engagements"], reverse=True)
    insight = None
    if rows and by_profit[0]["campaign_id"] != by_eng[0]["campaign_id"]:
        insight = (f"Most engagement: '{by_eng[0]['name']}' — but most contribution: '{by_profit[0]['name']}'. "
                   "Optimise for contribution, not likes.")
    agg: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        for key in (f"identity:{r['identity']}", f"genre:{r['genre']}", f"platform:{r['platform']}"):
            agg[key]["spend"] += r["spend"]
            agg[key]["profit"] += r["contribution_after_ads"]
            agg[key]["n"] += 1
    return {"campaigns": by_profit, "engagement_ranking": [r["campaign_id"] for r in by_eng],
            "features": {k: {"campaigns": int(v["n"]), "spend": round(v["spend"], 2), "profit": round(v["profit"], 2),
                             "profit_per_100_spend": round(100 * v["profit"] / v["spend"], 1) if v["spend"] else None} for k, v in agg.items()},
            "insight": insight, "epistemic": "verified" if rows else "estimate"}
