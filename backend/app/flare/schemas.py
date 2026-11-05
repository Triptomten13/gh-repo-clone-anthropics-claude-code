"""Typed schemas for every Rocky Flare output. Engines build these models; agents
return ``model_dump()`` so results stored on tasks are validated structures."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Epistemic = Literal["verified", "estimate", "assumption", "hypothesis"]
ProductStatus = Literal["existing_product", "supplier_customization", "proposed_modification", "original_concept"]


class Reasoned(BaseModel):
    reasoning: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.5)
    epistemic: Epistemic = "hypothesis"


class GenreMatch(Reasoned):
    genre_id: str
    name: str
    score: float
    learned_adjustment: float = 0.0


class BrandSystem(BaseModel):
    """The 11 brand-direction fields required for every concept."""

    primary_genre: str
    secondary_genre: str
    visual_direction: str
    color_palette: list[str]
    typography: dict[str, str]
    materials_textures: list[str]
    photography_style: str
    packaging_style: str
    website_language: str
    social_identity: str
    advertising_direction: str


class HybridGenre(Reasoned):
    id: str
    name: str
    components: list[str]
    concept: str
    philosophy: str
    target_audience: str
    palette: list[str]
    typography: dict[str, str]
    materials: list[str]
    surface_treatments: list[str]
    graphic_language: str
    product_applications: list[str]
    packaging_direction: str
    photography_direction: str
    marketing_identity: str
    novel: bool = False
    compatibility: float = 0.0
    sensitivity: list[str] = Field(default_factory=list)


class DirectionScores(BaseModel):
    audience_relevance: float
    competitive_differentiation: float
    visual_recognition: float
    brand_scalability: float
    marketing_potential: float
    production_cost: float  # higher = cheaper to produce
    expected_positioning: Literal["budget", "mid", "premium"]
    overall: float


class CreativeDirection(Reasoned):
    title: str
    hybrid_id: str
    brand_system: BrandSystem
    why_it_fits: list[str]
    scores: DirectionScores


class OriginalityReport(BaseModel):
    score: float
    components: dict[str, float]
    flags: list[dict[str, str]]
    requires_revision: bool
    trademark: dict[str, object]


class MutationNode(Reasoned):
    key: str
    mutation_type: str
    title: str
    concept: str
    status: ProductStatus
    customer_value: int = Field(ge=1, le=5)
    cost: int = Field(ge=1, le=5)
    complexity: int = Field(ge=1, le=5)
    differentiation: int = Field(ge=1, le=5)
    profit_potential: int = Field(ge=1, le=5)
    regulatory_risk: int = Field(ge=1, le=5)
    rank_score: float
    verification_needed: list[str] = Field(default_factory=list)


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    relation: str
    note: str = ""


class SidewaysItem(Reasoned):
    category: str
    text: str
    domain: str
    bridge: str


class SidewaysCombo(Reasoned):
    title: str
    customer_group: str
    recurring: str
    channel: str
    potential: float


class PersonaEvaluation(BaseModel):
    persona_id: str
    concept_id: int | None
    criteria: dict[str, float]
    weighted_score: float
    stance: Literal["support", "caution", "oppose", "neutral"]
    strengths: list[str]
    weaknesses: list[str]
    generic_elements: list[str]
    improvements: list[str]
    confidence: float
    method: Literal["heuristic", "llm"] = "heuristic"


class CampaignCell(Reasoned):
    identity: str
    platform: str
    target_audience: str
    creative_genre: str
    hook: str
    main_message: str
    visual_concept: str
    video_format: str
    call_to_action: str
    budget_recommendation_sek: float | None
    measurement: dict[str, str]
    flags: list[str] = Field(default_factory=list)


class CommercialOpportunity(Reasoned):
    module: str
    title: str
    description: str
    model: str
    effort: Literal["low", "medium", "high"]
    requires_approval: bool = False
    legal_notes: list[str] = Field(default_factory=list)
