"""Database models for the Rocky commerce intelligence platform.

Conventions:
* Every record that can originate from sample/demo data carries ``is_demo`` so the
  UI can label it and it can never be confused with real market data.
* Agent outputs carry an ``epistemic`` field: verified | estimate | assumption | hypothesis.
"""
from __future__ import annotations

import enum
from datetime import datetime, UTC
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql.expression import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class TaskStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    blocked = "blocked"  # cannot run: missing credentials, permissions, kill switch...
    cancelled = "cancelled"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"


class Epistemic(str, enum.Enum):
    verified = "verified"
    estimate = "estimate"
    assumption = "assumption"
    hypothesis = "hypothesis"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="operator")  # admin | operator | viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    # bumped on password reset / role change / disable → every previously issued token stops working
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    division: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    permission_level: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active | suspended
    model_tier: Mapped[str] = mapped_column(String(16), default="standard")
    daily_token_budget: Mapped[int] = mapped_column(Integer, default=200_000)
    tokens_today: Mapped[int] = mapped_column(Integer, default=0)
    tokens_total: Mapped[int] = mapped_column(Integer, default=0)
    cost_total_usd: Mapped[float] = mapped_column(Float, default=0.0)
    budget_day: Mapped[str] = mapped_column(String(10), default="")
    tasks_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0)
    tasks_blocked: Mapped[int] = mapped_column(Integer, default=0)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.queued.value, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    timeout_s: Mapped[int] = mapped_column(Integer, default=120)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    requested_by: Mapped[str] = mapped_column(String(64), default="system")
    depends_on: Mapped[list[int]] = mapped_column(JSON, default=list)  # task ids that must finish first
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentMessage(Base):
    """Structured message on the central bus (spec section 20)."""

    __tablename__ = "agent_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="finding")
    summary: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[Any]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    epistemic: Mapped[str] = mapped_column(String(16), default=Epistemic.estimate.value)
    recommendations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    financial_impact_sek: Mapped[float | None] = mapped_column(Float, nullable=True)
    risks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    required_approvals: Mapped[list[Any]] = mapped_column(JSON, default=list)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(64), default="")
    country: Mapped[str] = mapped_column(String(64), default="")
    eu_based: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-5
    years_active: Mapped[float | None] = mapped_column(Float, nullable=True)
    moq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_delivery_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1
    dispute_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1
    offers_private_label: Mapped[bool] = mapped_column(Boolean, default=False)
    offers_custom_packaging: Mapped[bool] = mapped_column(Boolean, default=False)
    has_product_documentation: Mapped[bool] = mapped_column(Boolean, default=False)
    reliability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    certifications: Mapped[list[str]] = mapped_column(JSON, default=list)  # documents actually received, e.g. "EN 15194 test report"
    warranty_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spare_parts_available: Mapped[bool] = mapped_column(Boolean, default=False)
    qc_process: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(128), default="", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    image_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_platform: Mapped[str] = mapped_column(String(64), default="manual")
    source_url: Mapped[str] = mapped_column(String(1024), default="")
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    supplier_location: Mapped[str] = mapped_column(String(64), default="")
    currency: Mapped[str] = mapped_column(String(3), default="SEK")
    wholesale_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    shipping_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    retail_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # incl. VAT
    competitor_prices: Mapped[list[float]] = mapped_column(JSON, default=list)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Signals 0-100 (None = unknown, never silently defaulted)
    purchase_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    engagement_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    competitor_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    competition_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)  # -1..1
    review_complaint_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    return_risk: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    marketing_potential: Mapped[float | None] = mapped_column(Float, nullable=True)
    customization_potential: Mapped[float | None] = mapped_column(Float, nullable=True)
    differentiation_potential: Mapped[float | None] = mapped_column(Float, nullable=True)
    scalability: Mapped[float | None] = mapped_column(Float, nullable=True)
    platforms_seen: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Derived
    gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    opportunity_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    score_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score_adjustments: Mapped[list[Any]] = mapped_column(JSON, default=list)
    compliance_status: Mapped[str] = mapped_column(String(32), default="unreviewed")
    compliance_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="discovered")  # discovered|investigating|validated|launched|discontinued|rejected
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    supplier: Mapped[Supplier | None] = relationship()


class TrendObservation(Base):
    __tablename__ = "trend_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(255), index=True)
    platform: Mapped[str] = mapped_column(String(64), index=True)
    metric: Mapped[str] = mapped_column(String(64))  # search_interest | mentions | views | sales_rank_inv ...
    value: Mapped[float] = mapped_column(Float)
    region: Mapped[str] = mapped_column(String(8), default="SE")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_ref: Mapped[str] = mapped_column(String(1024), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Trend(Base):
    __tablename__ = "trends"
    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    stage: Mapped[str] = mapped_column(String(32))
    velocity_score: Mapped[float] = mapped_column(Float)
    growth_rate: Mapped[float] = mapped_column(Float)  # weekly log-growth
    acceleration: Mapped[float] = mapped_column(Float)
    platforms: Mapped[list[str]] = mapped_column(JSON, default=list)
    observations: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    business_models: Mapped[list[Any]] = mapped_column(JSON, default=list)
    transformations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    economics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    pricing: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    product: Mapped[Product] = relationship()


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    hypothesis: Mapped[str] = mapped_column(Text)
    variant_a: Mapped[str] = mapped_column(Text, default="")
    variant_b: Mapped[str] = mapped_column(Text, default="")
    success_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"min_roas": 2.0, ...}
    predicted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actual: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    budget_sek: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft|pending_approval|running|completed|abandoned
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)  # scale|iterate|abandon
    lessons: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(32), default="shopify")
    brand: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="planning")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LedgerEntry(Base):
    """Single source of truth for financials. Dashboards aggregate from here only."""

    __tablename__ = "ledger_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    customer_ref: Mapped[str] = mapped_column(String(64), default="")  # pseudonymous first-party id, never raw PII
    channel: Mapped[str] = mapped_column(String(64), default="direct")
    kind: Mapped[str] = mapped_column(String(32), index=True)  # revenue|cogs|shipping|fees|ad_spend|refund|chargeback|opex|tax
    amount: Mapped[float] = mapped_column(Float)  # positive numbers; sign derived from kind
    currency: Mapped[str] = mapped_column(String(3), default="SEK")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reference: Mapped[str] = mapped_column(String(255), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    amount_sek: Mapped[float | None] = mapped_column(Float, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=ApprovalStatus.pending.value, index=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(255), default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))  # experiment:12, decision, ...
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemState(Base):
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# =====================================================================================
# ROCKY FLARE — creative intelligence layer
# =====================================================================================
class Persona(Base):
    """Editable agent personality. Deliberately has NO permission or budget fields:
    personalities shape judgement, never authority."""

    __tablename__ = "personas"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(128))
    division: Mapped[str] = mapped_column(String(64), index=True)
    personality: Mapped[str] = mapped_column(Text, default="")
    expertise: Mapped[list[str]] = mapped_column(JSON, default=list)
    creative_tendencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    research_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_philosophy: Mapped[str] = mapped_column(Text, default="")
    communication_style: Mapped[str] = mapped_column(String(64), default="systematic")
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    known_biases: Mapped[list[str]] = mapped_column(JSON, default=list)
    creative_specialization: Mapped[str] = mapped_column(String(255), default="")
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    genre_affinities: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    evaluation_lens: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    naming_style: Mapped[str] = mapped_column(String(32), default="minimal")
    novelty_appetite: Mapped[float] = mapped_column(Float, default=0.5)  # 0 conservative .. 1 experimental
    risk_tolerance: Mapped[float] = mapped_column(Float, default=0.5)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PersonaVersion(Base):
    __tablename__ = "persona_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    changed_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersonaMemory(Base):
    """What a persona learned: calibration points (its score vs. realised outcome) and lessons."""

    __tablename__ = "persona_memory"
    id: Mapped[int] = mapped_column(primary_key=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # calibration | lesson | win
    concept_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomGenre(Base):
    """Hybrid or user-defined genres discovered by the fusion engine."""

    __tablename__ = "custom_genres"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    components: Mapped[list[str]] = mapped_column(JSON, default=list)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    origin: Mapped[str] = mapped_column(String(64), default="fusion")  # fusion | user | preset
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="concept")  # concept | approved | live | retired
    concept_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    genre_dna: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    audience: Mapped[str] = mapped_column(Text, default="")
    segments: Mapped[list[str]] = mapped_column(JSON, default=list)
    positioning: Mapped[str] = mapped_column(Text, default="")
    marketing_strategy: Mapped[str] = mapped_column(Text, default="")
    website: Mapped[str] = mapped_column(String(255), default="")
    social_strategy: Mapped[str] = mapped_column(Text, default="")
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    trademark_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | clear | conflict (set by a human)
    trademark_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BrandConcept(Base):
    __tablename__ = "brand_concepts"
    id: Mapped[int] = mapped_column(primary_key=True)
    lineage_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    author_persona: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(128))
    tagline: Mapped[str] = mapped_column(String(255), default="")
    primary_genre: Mapped[str] = mapped_column(String(96), default="")
    secondary_genre: Mapped[str] = mapped_column(String(96), default="")
    hybrid: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    direction: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # the 11 brand-system fields
    audience: Mapped[str] = mapped_column(Text, default="")
    usp: Mapped[str] = mapped_column(Text, default="")
    story: Mapped[str] = mapped_column(Text, default="")
    positioning: Mapped[str] = mapped_column(String(32), default="mid")
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    originality: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    panel_scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft|needs_revision|shortlisted|approved|rejected
    source: Mapped[str] = mapped_column(String(16), default="engine")  # engine | llm | human
    epistemic: Mapped[str] = mapped_column(String(16), default="hypothesis")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CreativeAsset(Base):
    __tablename__ = "creative_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    lineage_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    concept_id: Mapped[int | None] = mapped_column(ForeignKey("brand_concepts.id"), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(64), default="procedural_svg")
    mime: Mapped[str] = mapped_column(String(64), default="image/svg+xml")
    content: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    concept_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    identity: Mapped[str] = mapped_column(String(48), index=True)
    genre: Mapped[str] = mapped_column(String(96), default="")
    platform: Mapped[str] = mapped_column(String(32), default="")
    audience: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    visual_concept: Mapped[str] = mapped_column(Text, default="")
    video_format: Mapped[str] = mapped_column(String(64), default="")
    cta: Mapped[str] = mapped_column(String(128), default="")
    budget_recommendation_sek: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft | pending_approval | running | completed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CampaignPerformance(Base):
    """Actual results (from ad platforms or manual entry). Learning only ever uses these rows."""

    __tablename__ = "campaign_performance"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    engagements: Mapped[int] = mapped_column(Integer, default=0)  # likes + comments + shares
    spend: Mapped[float] = mapped_column(Float, default=0.0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    contribution: Mapped[float | None] = mapped_column(Float, nullable=True)  # after COGS/fees/returns, before ad spend
    source: Mapped[str] = mapped_column(String(64), default="manual")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class CollaborationSession(Base):
    __tablename__ = "collaboration_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # discussion | panel | council | competition
    topic: Mapped[str] = mapped_column(String(255))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    concept_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    members: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="open")
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CollaborationTurn(Base):
    __tablename__ = "collaboration_turns"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("collaboration_sessions.id"), index=True)
    persona_id: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seat: Mapped[str] = mapped_column(String(64), default="")
    stance: Mapped[str] = mapped_column(String(16), default="neutral")  # propose|support|caution|oppose|decide|neutral
    message: Mapped[str] = mapped_column(Text, default="")
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[Any]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    method: Mapped[str] = mapped_column(String(16), default="heuristic")  # heuristic | llm
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GraphNode(Base):
    """Shared relationship graph: mutation graphs, cross-industry graphs, product ecosystems."""

    __tablename__ = "graph_nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    graph: Mapped[str] = mapped_column(String(96), index=True)
    key: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(48))
    label: Mapped[str] = mapped_column(String(255))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    graph: Mapped[str] = mapped_column(String(96), index=True)
    source: Mapped[str] = mapped_column(String(128))
    target: Mapped[str] = mapped_column(String(128))
    relation: Mapped[str] = mapped_column(String(48))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class CompatibilityRecord(Base):
    """Product ↔ vehicle/mount compatibility. Default is 'unverified' — never assumed."""

    __tablename__ = "compatibility_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    target: Mapped[str] = mapped_column(String(255))  # e.g. "Handlebar Ø22.2 mm" or a specific scooter model
    target_kind: Mapped[str] = mapped_column(String(32), default="vehicle_model")  # vehicle_model | mount_standard
    status: Mapped[str] = mapped_column(String(32), default="unverified")  # unverified | supplier_claimed | verified | incompatible
    evidence: Mapped[str] = mapped_column(Text, default="")
    verified_by: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# =====================================================================================
# AI CORE — call tracing
# =====================================================================================
class LLMCall(Base):
    """One row per provider attempt (including failed/fallback attempts). Source of truth for AI cost and latency."""

    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    purpose: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(96))
    tier: Mapped[str] = mapped_column(String(16), default="")
    status: Mapped[str] = mapped_column(String(24))  # ok | refused | unavailable | error | not_configured | circuit_open
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    # DAEMON cost intelligence
    workflow: Mapped[str] = mapped_column(String(64), default="", server_default="")
    project: Mapped[str] = mapped_column(String(64), default="", server_default="")
    profile: Mapped[str] = mapped_column(String(16), default="", server_default="")
    locality: Mapped[str] = mapped_column(String(16), default="", server_default="")  # local | lan | external | cache
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    saved_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")  # actual saving (cache hit = original cost)
    energy_wh: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")  # ESTIMATE for local inference
    prompt_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # provider-side prompt-cache reads


# =====================================================================================
# THE ARCHIVE — knowledge, provenance, memory
# =====================================================================================
EVIDENCE_CLASSES = ("historical_fact", "primary_source", "religious_interpretation", "philosophical_theory", "scholarly_hypothesis",
                    "speculative", "fiction_canon", "unclassified")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(512), default="")
    source_url: Mapped[str] = mapped_column(String(1024), default="")
    author: Mapped[str] = mapped_column(String(255), default="")
    created_date: Mapped[str] = mapped_column(String(64), default="")  # free text: historical dates ("c. 600 BCE") are not ISO dates
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    doc_type: Mapped[str] = mapped_column(String(24), index=True)
    mime: Mapped[str] = mapped_column(String(128), default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_class: Mapped[str] = mapped_column(String(32), default="unclassified", index=True)
    status: Mapped[str] = mapped_column(String(16), default="processing", index=True)  # processing | ready | failed | duplicate
    error: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    simhash: Mapped[str] = mapped_column(String(16), default="")
    duplicate_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    lineage_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str] = mapped_column(String(512), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    injection_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    start_char: Mapped[int] = mapped_column(Integer, default=0)
    end_char: Mapped[int] = mapped_column(Integer, default=0)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(64), default="")
    injection_risk: Mapped[bool] = mapped_column(Boolean, default=False)


class DocumentRelation(Base):
    __tablename__ = "document_relations"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    relation: Mapped[str] = mapped_column(String(32))  # cites | interprets | compares | duplicates | version_of | related | contradicts
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(255), default="")


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="concept")  # person | place | text | symbol | event | concept | organization | civilization
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    count: Mapped[int] = mapped_column(Integer, default=1)


class Annotation(Base):
    """Interpretations live here, separate from the source text they interpret."""

    __tablename__ = "annotations"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32), default="note")  # note | interpretation | source_comparison | correction
    text: Mapped[str] = mapped_column(Text)
    evidence_class: Mapped[str] = mapped_column(String(32), default="unclassified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


MEMORY_SCOPES = ("user_preference", "project", "long_term", "session", "agent_working", "creative_canon", "external_retrieved")


class MemoryItem(Base):
    __tablename__ = "memory_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    key: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(255), default="user")
    agent_id: Mapped[str] = mapped_column(String(64), default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# =====================================================================================
# ARCHIVUM SCIENTIAE VETITAE — canon tools (structure only; content is imported, never invented)
# =====================================================================================
class CanonWork(Base):
    __tablename__ = "canon_works"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | canon | retired


class CanonChapter(Base):
    __tablename__ = "canon_chapters"
    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("canon_works.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CanonAssertion(Base):
    """A structured statement (subject — predicate — object) with its evidentiary class.
    Lore is 'fiction_canon'; it is never mixed with historical claims."""

    __tablename__ = "canon_assertions"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), index=True)
    predicate: Mapped[str] = mapped_column(String(128), index=True)
    object: Mapped[str] = mapped_column(Text)
    evidence_class: Mapped[str] = mapped_column(String(32), default="fiction_canon")
    chapter_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | retired
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CanonVersion(Base):
    __tablename__ = "canon_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(255))
    date_text: Mapped[str] = mapped_column(String(64))  # as stated by the source, e.g. "c. 587 BCE"
    sort_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # negative = BCE; None = undated
    evidence_class: Mapped[str] = mapped_column(String(32), default="unclassified")
    description: Mapped[str] = mapped_column(Text, default="")
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chapter_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_note: Mapped[str] = mapped_column(Text, default="")


# =====================================================================================
# G-SUS — head orchestrator runs
# =====================================================================================
class GsusRun(Base):
    __tablename__ = "gsus_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    objective: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(24), default="gsus")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="planning", index=True)
    # planning | running | waiting_for_approval | needs_clarification | completed | failed | cancelled
    intent: Mapped[str] = mapped_column(String(48), default="")
    plan_method: Mapped[str] = mapped_column(String(16), default="heuristic")
    clarification: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    answer_method: Mapped[str] = mapped_column(String(16), default="")
    citations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    contradictions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    verification: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GsusStep(Base):
    __tablename__ = "gsus_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("gsus_runs.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(24))  # task | retrieval | approval_gate | synthesis
    task_type: Mapped[str] = mapped_column(String(64), default="")
    agent_hint: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    depends_on: Mapped[list[int]] = mapped_column(JSON, default=list)  # step ordinals
    status: Mapped[str] = mapped_column(String(24), default="pending")
    # pending | running | waiting_for_approval | completed | failed | blocked | cancelled
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# =====================================================================================
# DAEMON CORE — sovereign AI infrastructure & cost intelligence
# =====================================================================================
class LocalModel(Base):
    """A model in the local library. Weights live on disk (MODELS_DIR), never in git or the DB.
    `license` is copied from the source's own metadata at install time; commercial use is only
    marked permitted for known permissive licenses — anything else needs human review."""

    __tablename__ = "local_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    family: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(16), default="chat")  # chat | embedding
    fmt: Mapped[str] = mapped_column(String(16), default="gguf")
    quantization: Mapped[str] = mapped_column(String(16), default="")
    parameters: Mapped[str] = mapped_column(String(16), default="")
    source: Mapped[str] = mapped_column(String(32), default="huggingface")  # huggingface | local_file
    source_repo: Mapped[str] = mapped_column(String(255), default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    source_revision: Mapped[str] = mapped_column(String(64), default="")
    license: Mapped[str] = mapped_column(String(64), default="unknown")
    license_evidence: Mapped[str] = mapped_column(Text, default="")
    license_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    commercial_use: Mapped[str] = mapped_column(String(24), default="review_required")  # permitted | review_required
    sha256_expected: Mapped[str] = mapped_column(String(64), default="")
    sha256_actual: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    file_path: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="available")  # available|downloading|installed|failed|removed
    progress_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    context_length: Mapped[int] = mapped_column(Integer, default=4096)
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    installed_by: Mapped[str] = mapped_column(String(255), default="")
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderRecord(Base):
    """Provider registry. Facts carry a source URL and a verification date; unknown stays unknown."""

    __tablename__ = "provider_records"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(24))  # local_runtime | api | model_hub
    website: Mapped[str] = mapped_column(String(255), default="")
    docs_url: Mapped[str] = mapped_column(String(255), default="")
    pricing_url: Mapped[str] = mapped_column(String(255), default="")
    terms_url: Mapped[str] = mapped_column(String(255), default="")
    privacy_url: Mapped[str] = mapped_column(String(255), default="")
    models: Mapped[list[str]] = mapped_column(JSON, default=list)
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # free_tier, rate_limits, token_limits, commercial, geo, registration
    adapter: Mapped[bool] = mapped_column(Boolean, default=False)  # an integration exists in this codebase
    status: Mapped[str] = mapped_column(String(24), default="unverified")  # operational|unverified|paused|not_integrated
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProviderCredential(Base):
    """Owner-authorised API credential. The secret is Fernet-encrypted at rest and never returned by the API."""

    __tablename__ = "provider_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    secret_enc: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | disabled | revoked
    attestation: Mapped[str] = mapped_column(Text, default="")
    authorized_by: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResponseCache(Base):
    __tablename__ = "response_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(48), default="")
    model: Mapped[str] = mapped_column(String(96), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[Any] = mapped_column(JSON, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    original_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(96), index=True)
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    variables: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(255), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(48))
    model: Mapped[str] = mapped_column(String(96))
    suite: Mapped[str] = mapped_column(String(48), default="daemon-core-v1")
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | completed | failed
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OptimizationProposal(Base):
    __tablename__ = "optimization_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_saving_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, default="")
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed | approved | rejected
    decided_by: Mapped[str] = mapped_column(String(255), default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelWorker(Base):
    """A registered inference worker (OpenAI-compatible endpoint, e.g. llama.cpp server or vLLM) on another machine."""

    __tablename__ = "model_workers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    base_url: Mapped[str] = mapped_column(String(255))
    models: Mapped[list[str]] = mapped_column(JSON, default=list)
    locality: Mapped[str] = mapped_column(String(16), default="lan")  # local | lan | external
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # healthy | unreachable | unknown
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrainingDataset(Base):
    """Fine-tuning lab dataset. Private user data needs explicit consent; nothing trains without a feasibility pass."""

    __tablename__ = "training_datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, default=1)
    purpose: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    contains_private_data: Mapped[bool] = mapped_column(Boolean, default=False)
    consent: Mapped[str] = mapped_column(String(24), default="none")  # none | explicit
    consent_by: Mapped[str] = mapped_column(String(255), default="")
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="registered")  # registered | blocked_no_consent
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
