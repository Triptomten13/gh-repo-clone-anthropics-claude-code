"""Database models for the Rocky commerce intelligence platform.

Conventions:
* Every record that can originate from sample/demo data carries ``is_demo`` so the
  UI can label it and it can never be confused with real market data.
* Agent outputs carry an ``epistemic`` field: verified | estimate | assumption | hypothesis.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
