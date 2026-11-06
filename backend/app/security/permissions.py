"""Least-privilege permission model (spec section 21).

LEVEL 0 research · 1 analysis · 2 drafting · 3 reversible internal ops ·
4 approved external publishing · 5 financial transactions / contracts.

Actions at level >= 4 always require an approved human Approval, regardless of the
agent's own level. Agents can never change permissions: only the admin API does,
and every change is audited.
"""
from __future__ import annotations

from enum import IntEnum


class Level(IntEnum):
    RESEARCH = 0
    ANALYSIS = 1
    DRAFTING = 2
    INTERNAL_OPS = 3
    EXTERNAL_PUBLISH = 4
    FINANCIAL = 5


ACTION_LEVELS: dict[str, Level] = {
    # research / analysis
    "market.research": Level.RESEARCH,
    "trend.analyze": Level.ANALYSIS,
    "product.score": Level.ANALYSIS,
    "product.economics": Level.ANALYSIS,
    "compliance.assess": Level.ANALYSIS,
    "opportunity.generate": Level.ANALYSIS,
    "portfolio.review": Level.ANALYSIS,
    # drafting
    "content.draft": Level.DRAFTING,
    "brand.draft": Level.DRAFTING,
    "supplier.inquiry_draft": Level.DRAFTING,
    # reversible internal
    "product.update_status": Level.INTERNAL_OPS,
    "experiment.create": Level.INTERNAL_OPS,
    "store.create_draft_listing": Level.INTERNAL_OPS,
    "brand.create": Level.INTERNAL_OPS,
    "concept.revise": Level.DRAFTING,
    "asset.generate": Level.DRAFTING,
    "campaign.draft": Level.DRAFTING,
    # external publishing (approval required)
    "store.publish_listing": Level.EXTERNAL_PUBLISH,
    "content.publish": Level.EXTERNAL_PUBLISH,
    "price.change_live": Level.EXTERNAL_PUBLISH,
    "customer.message": Level.EXTERNAL_PUBLISH,
    "supplier.send_inquiry": Level.EXTERNAL_PUBLISH,
    "product.launch": Level.EXTERNAL_PUBLISH,
    "brand.launch": Level.EXTERNAL_PUBLISH,
    "asset.publish": Level.EXTERNAL_PUBLISH,
    # creative intelligence (DAEMON CREATIVE INTELLIGENCE)
    "creative.tournament": Level.DRAFTING,       # local / verified-free models, within budget: autonomous, recorded
    "creative.benchmark": Level.ANALYSIS,
    "providers.discover": Level.RESEARCH,        # list candidates; never makes them routable
    "creative.tournament.paid": Level.EXTERNAL_PUBLISH,  # paid model spend above CREATIVE_AUTONOMOUS_USD: a human approves
    # financial (approval required)
    "ads.launch_campaign": Level.FINANCIAL,
    "ads.budget_change": Level.FINANCIAL,
    "purchase.order": Level.FINANCIAL,
    "supplier.agreement": Level.FINANCIAL,
    "experiment.run_paid": Level.FINANCIAL,
    "campaign.launch": Level.FINANCIAL,
    "acquisition.offer": Level.FINANCIAL,
}

APPROVAL_THRESHOLD = Level.EXTERNAL_PUBLISH


class PermissionDenied(Exception):
    pass


def required_level(action: str) -> Level:
    if action not in ACTION_LEVELS:
        # unknown actions are treated as the most sensitive
        return Level.FINANCIAL
    return ACTION_LEVELS[action]


def needs_approval(action: str) -> bool:
    return required_level(action) >= APPROVAL_THRESHOLD


def check(agent_level: int, action: str) -> None:
    req = required_level(action)
    if agent_level < req:
        raise PermissionDenied(f"action '{action}' requires level {int(req)}; agent has level {agent_level}")
