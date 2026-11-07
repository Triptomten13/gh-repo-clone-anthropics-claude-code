"""Concrete agents. Each agent is small: it gathers inputs, calls a tested engine
(or an LLM for creative work) and returns a structured AgentOutput."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, UTC

from sqlalchemy import select

from ..engines import business_models, compliance, economics, experiments, finance, pricing, scoring, transformation, trends
from ..integrations import registry as connectors
from ..models import (Experiment, LedgerEntry, Lesson, Opportunity, Product, Supplier, Task, Trend,
                      TrendObservation)
from ..governance.core import get_state
from .base import AgentContext, AgentOutput, BaseAgent, Blocked


def _product(ctx: AgentContext, task: Task) -> Product:
    pid = task.payload.get("product_id")
    p = ctx.db.get(Product, pid) if pid is not None else None
    if p is None:
        raise Blocked(f"product {pid} not found")
    return p


# =============================================================== EXECUTIVE
class CEOAgent(BaseAgent):
    id, name, division = "ceo", "CEO Agent", "executive"
    description = "Sets priorities, runs the opportunity pipeline, weekly portfolio review, requests launch approvals."
    level, tier = 3, "deep"
    task_types = ("ceo.evaluate_product", "ceo.weekly_review", "ceo.evaluate_pipeline")

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        if task.type == "ceo.evaluate_product":
            p = _product(ctx, task)
            # Revision key: unchanged products reuse recent results (dedupe); edited products or an
            # explicit user refresh produce a new key so every step is recomputed.
            rev = task.payload.get("refresh") or (p.updated_at.isoformat() if p.updated_at else "")
            base = {"product_id": p.id, "rev": rev}
            spawned = [
                ctx.spawn("risk.assess", base, priority=10).id,
                ctx.spawn("cfo.economics", base, priority=20).id,
                ctx.spawn("product.score", base, priority=30).id,
                ctx.spawn("opportunity.generate", base, priority=40).id,
                ctx.spawn("flare.mutate", base, priority=45).id,  # every evaluated product enters the Mutation Engine
            ]
            pid = p.id
            return AgentOutput(summary=f"Opportunity pipeline started for product {pid}", result={"spawned": spawned},
                               epistemic="verified", confidence=1.0)
        if task.type == "ceo.evaluate_pipeline":
            ids = ctx.db.scalars(select(Product.id).where(Product.status.in_(("discovered", "investigating")))).all()
            limit = int(task.payload.get("limit", 25))
            spawned = [ctx.spawn("ceo.evaluate_product", {"product_id": i}, priority=5).id for i in ids[:limit]]
            return AgentOutput(summary=f"Queued evaluation for {len(spawned)} products", result={"spawned": spawned},
                               epistemic="verified", confidence=1.0)
        return self._weekly_review(ctx)

    def _weekly_review(self, ctx: AgentContext) -> AgentOutput:
        prods = ctx.db.scalars(select(Product).where(Product.opportunity_score.is_not(None))
                               .order_by(Product.opportunity_score.desc())).all()
        ranking = [{"product_id": p.id, "name": p.name, "score": p.opportunity_score, "confidence": p.score_confidence,
                    "compliance": p.compliance_status, "status": p.status} for p in prods]
        approvals, recs, risks = [], [], []
        for p in prods[:10]:
            if (p.opportunity_score or 0) >= 65 and (p.score_confidence or 0) >= 0.6 and p.status in ("discovered", "investigating", "validated"):
                if p.compliance_status != "approved":
                    recs.append(f"'{p.name}' scores {p.opportunity_score} but compliance is '{p.compliance_status}': human compliance review needed first")
                    continue
                approvals.append(ctx.request_approval(
                    "product.launch", f"Launch experiment: {p.name}",
                    f"Score {p.opportunity_score} (confidence {p.score_confidence}). Net margin {p.net_margin}. "
                    "Approve to start a limited, budget-capped market test.", {"product_id": p.id}))
            elif (p.opportunity_score or 0) < 35 and p.status == "launched":
                recs.append(f"Consider discontinuing '{p.name}' (score {p.opportunity_score})")
        low_conf = [p.name for p in prods if (p.score_confidence or 0) < 0.4]
        if low_conf:
            risks.append(f"{len(low_conf)} products scored with low data coverage; treat rankings as provisional")
        return AgentOutput(summary=f"Weekly review: {len(ranking)} scored products, {len(approvals)} launch approvals requested",
                           result={"ranking": ranking[:25]}, recommendations=recs, risks=risks,
                           required_approvals=approvals, epistemic="estimate", confidence=0.7)


class ChiefIntelligenceAgent(BaseAgent):
    id, name, division = "chief_intel", "Chief Intelligence Agent", "executive"
    description = "Coordinates research agents, builds trends from multi-source observations, links trends to products."
    level, tier = 1, "standard"
    task_types = ("intel.scan_market", "trend.analyze")

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        if task.type == "intel.scan_market":
            keywords = task.payload.get("keywords") or get_state(ctx.db, "watchlist").get("keywords", [])
            if not keywords:
                raise Blocked("no keywords: add keywords to the watchlist")
            spawned, skipped = [], []
            for c in connectors.research_connectors():
                if c.configured():
                    spawned.append(ctx.spawn("research.collect", {"connector": c.id, "keywords": keywords}, priority=20).id)
                else:
                    skipped.append({"connector": c.id, "state": c.status()["state"]})
            ctx.spawn("trend.analyze", {"keywords": keywords}, priority=60)
            return AgentOutput(summary=f"Market scan: {len(spawned)} research tasks queued, {len(skipped)} sources unavailable",
                               result={"spawned": spawned, "unavailable_sources": skipped}, epistemic="verified", confidence=1.0,
                               risks=[] if spawned else ["No research connector configured; only imported data will be analysed"])
        return self._analyze(ctx, task)

    def _analyze(self, ctx: AgentContext, task: Task) -> AgentOutput:
        q = select(TrendObservation)
        kws = task.payload.get("keywords")
        if kws:
            q = q.where(TrendObservation.keyword.in_(kws))
        rows = ctx.db.scalars(q).all()
        grouped: dict[str, list[trends.Obs]] = defaultdict(list)
        demo: dict[str, bool] = defaultdict(bool)
        for r in rows:
            # one series per platform+metric so units are never mixed
            grouped[r.keyword].append(trends.Obs(f"{r.platform}:{r.metric}", r.value, r.observed_at if r.observed_at.tzinfo else r.observed_at.replace(tzinfo=UTC)))
            demo[r.keyword] |= r.is_demo
        results = []
        for kw, obs in grouped.items():
            a = trends.analyze(kw, obs)
            t = ctx.db.scalars(select(Trend).where(Trend.keyword == kw)).first() or Trend(keyword=kw)
            t.stage, t.velocity_score, t.growth_rate, t.acceleration = a.stage, a.velocity_score, a.growth_rate, a.acceleration
            t.platforms = sorted({p.split(":")[0] for p in a.platforms})
            t.observations, t.confidence, t.is_demo = a.observations, a.confidence, demo[kw]
            ctx.db.add(t)
            # link to products whose name or tags mention the keyword
            for p in ctx.db.scalars(select(Product)).all():
                if kw.lower() in p.name.lower() or kw.lower() in {x.lower() for x in p.tags or []}:
                    p.trend_velocity = a.velocity_score
                    p.platforms_seen = sorted(set(p.platforms_seen or []) | set(t.platforms))
            results.append({"keyword": kw, "stage": a.stage, "velocity": a.velocity_score, "platforms": t.platforms,
                            "cross_platform_growth": a.cross_platform_growth, "confidence": a.confidence, "notes": a.notes})
        results.sort(key=lambda r: r["velocity"], reverse=True)
        multi = [r["keyword"] for r in results if r["cross_platform_growth"] >= 2]
        return AgentOutput(summary=f"Analysed {len(results)} trends; {len(multi)} growing on multiple platforms",
                           result={"trends": results}, findings=results[:10],
                           recommendations=[f"Prioritise '{k}': independent growth on several platforms" for k in multi],
                           epistemic="estimate", confidence=0.6)


class CFOAgent(BaseAgent):
    id, name, division = "cfo", "CFO Agent", "executive"
    description = "Unit economics, VAT, fees, returns, pricing scenarios, capital allocation."
    level, tier = 1, "standard"
    task_types = ("cfo.economics", "finance.capital_allocation")

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        if task.type == "finance.capital_allocation":
            return self._capital(ctx, task)
        p = _product(ctx, task)
        a = task.payload.get("assumptions", {})
        retail = p.retail_price
        if retail is None and p.competitor_prices:
            cp = sorted(p.competitor_prices)
            retail = cp[len(cp) // 2]
        if p.wholesale_price is None or retail is None:
            raise Blocked(f"'{p.name}': wholesale price and a retail or competitor price are required for economics")
        non_eu = not (p.supplier and p.supplier.eu_based)
        c = economics.CostInputs(
            retail_price_incl_vat=retail, unit_cost=p.wholesale_price, inbound_shipping=p.shipping_cost or 0.0,
            packaging=a.get("packaging", 8.0), fulfillment=a.get("fulfillment", 0.0 if non_eu else 15.0),
            import_duty_rate=a.get("import_duty_rate", 0.04 if non_eu else 0.0),
            customs_handling=a.get("customs_handling", 0.0), vat_rate=a.get("vat_rate", 0.25),
            payment_fee_pct=a.get("payment_fee_pct", 0.029), payment_fee_fixed=a.get("payment_fee_fixed", 1.8),
            marketplace_fee_pct=a.get("marketplace_fee_pct", 0.0),
            return_rate=p.return_risk if p.return_risk is not None else a.get("return_rate", 0.08),
            return_cost_per_return=a.get("return_cost_per_return", 69.0 if non_eu else 49.0),
            cac=a.get("cac", 0.0))
        econ = economics.compute(c)
        sc = pricing.scenarios(c, p.competitor_prices, p.currency)
        p.gross_margin = econ.gross_margin
        # Net margin used for scoring = contribution after an assumed CAC of 30% of price unless provided.
        assumed_cac = a.get("cac", round(retail * 0.30, 2))
        net = economics.compute(economics.CostInputs(**{**c.__dict__, "cac": assumed_cac}))
        p.net_margin = net.contribution_margin_pct
        risks = []
        if net.contribution_margin <= 0:
            risks.append("negative contribution after assumed acquisition cost")
        if (p.delivery_days or 0) > 12:
            risks.append(f"{p.delivery_days:.0f}-day delivery: higher dispute and return risk")
        return AgentOutput(
            summary=f"'{p.name}': contribution {econ.contribution_margin} {p.currency}/order before ads; "
                    f"{net.contribution_margin_pct:.0%} after assumed CAC {assumed_cac}",
            result={"economics": econ.as_dict(), "economics_with_cac": net.as_dict(), "pricing": sc,
                    "assumed_cac": assumed_cac},
            financial_impact_sek=net.contribution_margin, risks=risks, epistemic="estimate", confidence=0.65,
            evidence=[{"assumptions": econ.assumptions}])

    def _capital(self, ctx: AgentContext, task: Task) -> AgentOutput:
        available = float(task.payload.get("available_sek", 0))
        entries = ctx.db.scalars(select(LedgerEntry)).all()
        per: dict[int, dict[str, float]] = defaultdict(lambda: {"revenue": 0.0, "costs": 0.0, "ads": 0.0})
        for e in entries:
            if e.product_id is None:
                continue
            if e.kind == "revenue":
                per[e.product_id]["revenue"] += e.amount
            elif e.kind != "opex":
                per[e.product_id]["costs"] += e.amount
                if e.kind == "ad_spend":
                    per[e.product_id]["ads"] += e.amount
        perf = []
        for pid, v in per.items():
            p = ctx.db.get(Product, pid)
            perf.append({"product_id": pid, "name": p.name if p else str(pid), "contribution_margin": v["revenue"] - v["costs"],
                         "roas": v["revenue"] / v["ads"] if v["ads"] else None})
        rec = finance.capital_allocation(available, perf)
        return AgentOutput(summary="Capital allocation recommendation" if rec.get("available") else rec.get("reason", ""),
                           result=rec, epistemic="estimate", confidence=0.5,
                           recommendations=[f"Discontinue candidate: {n}" for n in rec.get("discontinue_candidates", [])])


class RiskAgent(BaseAgent):
    id, name, division = "risk", "Chief Risk Agent", "executive"
    description = "Compliance checklists (SE/EU), prohibited goods, health claims. Can block launches."
    level, tier = 3, "standard"
    task_types = ("risk.assess",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        p = _product(ctx, task)
        if p.compliance_status == "approved" and not task.payload.get("reassess"):
            return AgentOutput(summary=f"'{p.name}' already human-approved; skipped", result={"status": "approved"},
                               epistemic="verified", confidence=1.0)
        non_eu = not (p.supplier and p.supplier.eu_based)
        rep = compliance.assess(p.name, p.description, p.category, p.tags, task.payload.get("marketing_copy", ""),
                                non_eu_supplier=non_eu, affiliate=bool(task.payload.get("affiliate")))
        p.compliance_status = rep.status
        p.compliance_report = rep.as_dict()
        ctx.audit("compliance.assessed", f"product:{p.id}", status=rep.status, blockers=rep.blockers)
        return AgentOutput(summary=f"'{p.name}': compliance {rep.status} ({len(rep.blockers)} blockers, {len(rep.restrictions)} restrictions, {len(rep.checklist)} checklist items)",
                           result=rep.as_dict(), risks=rep.blockers + rep.restrictions + rep.warnings, epistemic="estimate", confidence=0.7,
                           recommendations=["Human compliance review required before any launch"])


# =============================================================== RESEARCH
class PlatformResearchAgent(BaseAgent):
    """One research agent class serves every platform connector (TikTok, Amazon, Etsy, ...)."""

    id, name, division = "research", "Market Research Division", "research"
    description = "Collects signals and product candidates through official platform APIs; one connector per platform."
    level, tier = 0, "fast"
    task_types = ("research.collect",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        ctx.check("market.research")
        c = connectors.get(task.payload["connector"])
        c.require()
        signals_n, products_n, errors = 0, 0, []
        for kw in task.payload.get("keywords", []):
            try:
                if "signals" in c.capabilities:
                    for s in c.search_signals(kw):
                        ctx.db.add(TrendObservation(keyword=kw, platform=s.platform, metric=s.metric, value=s.value,
                                                    region=s.region, observed_at=s.observed_at, source_ref=s.source_ref))
                        signals_n += 1
                if "products" in c.capabilities:
                    for pc in c.search_products(kw, limit=int(task.payload.get("limit", 10))):
                        exists = ctx.db.scalars(select(Product).where(Product.source_url == pc.source_url)).first() if pc.source_url else None
                        if exists:
                            continue
                        ctx.db.add(Product(name=pc.name[:255], category=pc.category, description=pc.description,
                                           source_platform=pc.platform, source_url=pc.source_url,
                                           competitor_prices=[pc.price] if pc.price else [], currency=pc.currency or "SEK",
                                           tags=[kw]))
                        products_n += 1
            except Exception as e:  # noqa: BLE001 - per-keyword isolation
                errors.append(f"{kw}: {type(e).__name__}: {e}")
        if errors and not (signals_n or products_n):
            raise RuntimeError("; ".join(errors))
        return AgentOutput(summary=f"{c.name}: {signals_n} signals, {products_n} new product candidates",
                           result={"signals": signals_n, "products": products_n, "errors": errors},
                           epistemic="verified", confidence=0.9)


# =============================================================== OPPORTUNITY
class ProductAnalystAgent(BaseAgent):
    id, name, division = "product_analyst", "Product Intelligence Agent", "opportunity"
    description = "Computes the weighted opportunity score with confidence and data coverage."
    level, tier = 1, "fast"
    task_types = ("product.score",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        p = _product(ctx, task)
        rel = None
        if p.supplier:
            rel, _ = scoring.supplier_reliability_score(p.supplier)
            p.supplier.reliability_score = rel
        r = scoring.compute_score(scoring.input_from_product(p, rel), p.score_adjustments)
        p.opportunity_score, p.score_confidence, p.score_breakdown = r.score, r.confidence, r.as_dict()
        if p.status == "discovered":
            p.status = "investigating"
        return AgentOutput(summary=f"'{p.name}' scored {r.score} (confidence {r.confidence})", result=r.as_dict(),
                           risks=r.flags, epistemic="estimate", confidence=r.confidence)


class TransformationLabAgent(BaseAgent):
    id, name, division = "transformation_lab", "Product Transformation Lab", "opportunity"
    description = "Turns a product into business concepts: transformations, business models, revenue multipliers."
    level, tier = 2, "deep"
    task_types = ("opportunity.generate",)

    SCHEMA = {
        "type": "object", "additionalProperties": False, "required": ["ideas"],
        "properties": {"ideas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["family", "title", "concept", "value_driver", "effort"],
            "properties": {"family": {"type": "string", "enum": list(transformation.FAMILIES)}, "title": {"type": "string"},
                           "concept": {"type": "string"}, "value_driver": {"type": "string"},
                           "effort": {"type": "string", "enum": ["low", "medium", "high"]}}}}},
    }

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        p = _product(ctx, task)
        complaints = task.payload.get("complaints") or (p.compliance_report or {}).get("complaints", [])
        ideas = transformation.generate(p.name, p.category, complaints, p.tags)
        enriched = False
        if task.payload.get("enrich"):
            res = ctx.llm(self.SYSTEM_RULES + " You are the Product Transformation Lab.",
                          f"Product: {p.name}\nCategory: {p.category}\nDescription: {p.description}\nKnown complaints: {complaints}\n"
                          "Propose 5 additional, non-obvious, legitimate business transformations.", schema=self.SCHEMA)
            for i in res.data["ideas"]:
                ideas.append({**i, "epistemic": "hypothesis", "source": "llm"})
            enriched = True
        heavy = (p.compliance_status == "blocked") or bool((p.compliance_report or {}).get("categories"))
        bm = business_models.evaluate(business_models.traits_from_product(p, compliance_heavy=heavy))
        econ_task = ctx.db.scalars(select(Task).where(Task.type == "cfo.economics", Task.status == "succeeded")
                                   .order_by(Task.id.desc())).all()
        econ = next((t.result for t in econ_task if t.payload.get("product_id") == p.id), {}) or {}
        opp = Opportunity(product_id=p.id, title=f"{p.name} opportunity", business_models=bm["recommended"],
                          transformations=ideas, economics=econ.get("economics", {}), pricing=econ.get("pricing", {}))
        ctx.db.add(opp)
        ctx.db.flush()
        return AgentOutput(summary=f"'{p.name}': {len(ideas)} transformations; top models: "
                                   + ", ".join(m["model"] for m in bm["recommended"]),
                           result={"opportunity_id": opp.id, "business_models": bm["recommended"], "transformations": ideas,
                                   "revenue_multipliers": transformation.revenue_multiplication_questions(p.name),
                                   "llm_enriched": enriched},
                           epistemic="hypothesis", confidence=0.5)


class SupplierAgent(BaseAgent):
    id, name, division = "supplier_intel", "Supplier Intelligence Agent", "opportunity"
    description = "Supplier reliability scoring and professional inquiry drafts (never sends or orders without approval)."
    level, tier = 2, "standard"
    task_types = ("supplier.evaluate", "supplier.inquiry_draft")

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        s = ctx.db.get(Supplier, task.payload.get("supplier_id"))
        if s is None:
            raise Blocked("supplier not found")
        if task.type == "supplier.evaluate":
            score, cov = scoring.supplier_reliability_score(s)
            s.reliability_score = score
            return AgentOutput(summary=f"{s.name}: reliability {score} (coverage {cov})", result={"score": score, "coverage": cov},
                               epistemic="estimate", confidence=cov,
                               risks=[] if score is None or score >= 60 else ["low reliability: request samples before any commitment"])
        ctx.check("supplier.inquiry_draft")
        p = ctx.db.get(Product, task.payload.get("product_id")) if task.payload.get("product_id") else None
        asks = task.payload.get("asks") or ["samples", "wholesale price tiers and MOQ", "custom packaging / private label options",
                                            "CE / test reports and technical documentation", "shipping terms to Sweden", "return / defect policy"]
        from ..config import get_settings

        company = task.payload.get("company") or get_settings().company_name
        body = (f"Subject: Wholesale inquiry – {p.name if p else 'your product range'}\n\n"
                f"Dear {s.name} team,\n\nWe are a Sweden-based e-commerce company evaluating "
                f"{'the product ' + repr(p.name) if p else 'products from your catalogue'} for the EU market.\n"
                "Could you please share:\n" + "\n".join(f"  - {a}" for a in asks) +
                "\n\nAs we sell in the EU, we need documentation demonstrating conformity with applicable EU product-safety rules "
                "(e.g. GPSR, CE where relevant, REACH).\n\nKind regards,\n" + company)
        approval = ctx.request_approval("supplier.send_inquiry", f"Send inquiry to {s.name}", body, {"supplier_id": s.id})
        return AgentOutput(summary=f"Inquiry drafted for {s.name}; sending requires approval", result={"draft": body},
                           required_approvals=[approval], epistemic="verified", confidence=1.0)


# =============================================================== BRAND & MARKETING (LLM)
class BrandStudioAgent(BaseAgent):
    id, name, division = "brand_studio", "Brand Creation Studio", "brand"
    description = "Generates multiple brand concepts. Trademark/domain checks are mandatory before recommendation."
    level, tier = 2, "deep"
    task_types = ("brand.generate",)
    SCHEMA = {
        "type": "object", "additionalProperties": False, "required": ["concepts"],
        "properties": {"concepts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "positioning", "usp", "voice", "palette", "typography", "slogans", "personas", "story", "packaging"],
            "properties": {"name": {"type": "string"}, "positioning": {"type": "string"}, "usp": {"type": "string"},
                           "voice": {"type": "string"}, "palette": {"type": "array", "items": {"type": "string"}},
                           "typography": {"type": "string"}, "slogans": {"type": "array", "items": {"type": "string"}},
                           "personas": {"type": "array", "items": {"type": "string"}}, "story": {"type": "string"},
                           "packaging": {"type": "string"}}}}},
    }

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        ctx.check("brand.draft")
        p = _product(ctx, task)
        res = ctx.llm(self.SYSTEM_RULES + " You are a senior brand strategist for Nordic e-commerce brands.",
                      f"Create 3 distinct brand concepts for: {p.name} ({p.category}). {p.description}\n"
                      "Names must be original, pronounceable in Swedish and English, and not resemble existing brands.",
                      schema=self.SCHEMA)
        concepts = [{**c, "trademark_check": "pending", "domain_check": "pending"} for c in res.data["concepts"]]
        return AgentOutput(summary=f"{len(concepts)} brand concepts for '{p.name}'", result={"concepts": concepts},
                           risks=["Trademark (EUIPO/PRV) and domain availability not yet verified; required before use"],
                           epistemic="hypothesis", confidence=0.5)


class ContentAgent(BaseAgent):
    id, name, division = "content", "Content & Creative Director Agent", "marketing"
    description = "Drafts scripts, ad copy, SEO articles and emails across creative angles. Drafts only; publishing is approval-gated."
    level, tier = 2, "standard"
    task_types = ("content.generate",)
    ANGLES = ("problem_solution", "demonstration", "curiosity", "educational", "before_after", "humor", "comparison", "unboxing")

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        ctx.check("content.draft")
        p = _product(ctx, task)
        channel = task.payload.get("channel", "tiktok")
        angles = task.payload.get("angles") or list(self.ANGLES[:4])
        schema = {"type": "object", "additionalProperties": False, "required": ["pieces"],
                  "properties": {"pieces": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                 "required": ["angle", "hook", "body", "cta", "claims_to_verify"],
                                 "properties": {"angle": {"type": "string"}, "hook": {"type": "string"}, "body": {"type": "string"},
                                                "cta": {"type": "string"}, "claims_to_verify": {"type": "array", "items": {"type": "string"}}}}}}}
        res = ctx.llm(self.SYSTEM_RULES + " You write high-performing, honest short-form marketing.",
                      f"Channel: {channel}. Product: {p.name}. {p.description}\nAngles: {', '.join(angles)}.\n"
                      "One piece per angle. List any factual claim that must be verified before publishing.", schema=schema)
        pieces = res.data["pieces"]
        claims = " ".join(x["hook"] + " " + x["body"] for x in pieces)
        rep = compliance.assess(p.name, "", p.category, [], marketing_copy=claims)
        claim_flags = [b for b in rep.blockers if "claim" in b or "prohibited" in b]
        return AgentOutput(summary=f"{len(pieces)} {channel} drafts for '{p.name}'", result={"pieces": pieces, "compliance_flags": claim_flags},
                           risks=claim_flags, epistemic="hypothesis", confidence=0.5)


class AdvertisingAgent(BaseAgent):
    id, name, division = "advertising", "Advertising Agent", "marketing"
    description = "Plans paid campaigns and expected CPM/CPC/CTR/CAC/ROAS. Cannot spend money."
    level, tier = 2, "fast"
    task_types = ("ads.plan",)
    # Planning assumptions per platform (estimates; replace with own account data when available)
    BENCH = {"meta": (90.0, 0.012, 0.02), "tiktok": (70.0, 0.010, 0.015), "google_search": (None, 0.04, 0.035), "pinterest": (60.0, 0.006, 0.012)}

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        p = _product(ctx, task)
        econ_t = [t for t in ctx.db.scalars(select(Task).where(Task.type == "cfo.economics", Task.status == "succeeded")).all()
                  if t.payload.get("product_id") == p.id]
        if not econ_t:
            raise Blocked("run cfo.economics for this product first")
        econ = econ_t[-1].result["economics"]
        price = econ["assumptions"]["retail_price_incl_vat"]
        plans = {}
        for platform, (cpm, ctr, cvr) in self.BENCH.items():
            o = task.payload.get(platform, {})
            cpm = o.get("cpm", cpm if cpm is not None else 300.0)
            plans[platform] = economics.ad_funnel(cpm, o.get("ctr", ctr), o.get("cvr", cvr), price, econ["contribution_before_ads"])
        viable = [k for k, v in plans.items() if v["profitable"]]
        return AgentOutput(summary=f"'{p.name}': ads profitable on {len(viable)}/{len(plans)} channels under planning assumptions",
                           result={"plans": plans, "break_even_cac": econ["break_even_cac"]}, epistemic="assumption", confidence=0.35,
                           risks=["Benchmarks are planning assumptions, not measured performance"],
                           recommendations=[f"Test on {k} with a capped budget" for k in viable])


# =============================================================== COMMERCE
class StoreBuilderAgent(BaseAgent):
    id, name, division = "store_builder", "Store Generator Agent", "commerce"
    description = "Creates DRAFT listings in connected stores; requests approval to publish."
    level, tier = 3, "fast"
    task_types = ("store.draft_listing",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        ctx.check("store.create_draft_listing")
        p = _product(ctx, task)
        if p.compliance_status != "approved":
            raise Blocked(f"'{p.name}' compliance status is '{p.compliance_status}'; human approval required before listing")
        shop = connectors.get("shopify")
        draft = shop.create_draft_product(task.payload.get("title", p.name), task.payload.get("description_html", p.description), p.tags)
        appr = ctx.request_approval("store.publish_listing", f"Publish '{p.name}' on Shopify", "Draft created; review in Shopify admin.",
                                    {"product_id": p.id, "shopify_id": draft.get("id")})
        return AgentOutput(summary=f"Draft listing created for '{p.name}'", result={"shopify": draft}, required_approvals=[appr],
                           epistemic="verified", confidence=1.0)


# =============================================================== OPERATIONS
class ExperimentAgent(BaseAgent):
    id, name, division = "experiments", "Experimentation Agent", "operations"
    description = "Evaluates experiments against pre-registered success metrics; scale / iterate / abandon; records lessons."
    level, tier = 3, "fast"
    task_types = ("experiment.evaluate",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        e = ctx.db.get(Experiment, task.payload.get("experiment_id"))
        if e is None:
            raise Blocked("experiment not found")
        if not e.actual:
            raise Blocked("no actual results recorded yet")
        d = experiments.decide(e.success_metrics, e.actual)
        err = experiments.prediction_error(e.predicted, e.actual)
        ab = None
        a = e.actual
        if all(k in a for k in ("conv_a", "n_a", "conv_b", "n_b")):
            ab = experiments.two_proportion_z(a["conv_a"], a["n_a"], a["conv_b"], a["n_b"])
        if d["decision"] in ("scale", "abandon", "iterate"):
            e.decision = d["decision"]
            e.status = "completed" if d["decision"] != "abandon" else "abandoned"
            e.completed_at = datetime.now(UTC)
            lesson = f"Experiment '{e.name}': {d['decision']} — {'; '.join(d['reasons'])}. Prediction MAPE: {err['mape']}"
            e.lessons = lesson
            ctx.db.add(Lesson(source=f"experiment:{e.id}", text=lesson, tags=[d["decision"]]))
        return AgentOutput(summary=f"Experiment '{e.name}': {d['decision']}", result={"decision": d, "prediction_error": err, "ab_test": ab},
                           epistemic="verified", confidence=0.8)


class SelfImprovementAgent(BaseAgent):
    id, name, division = "self_improvement", "Self-Improvement Agent", "operations"
    description = "Measures prediction accuracy and agent performance; proposes (never applies) improvements."
    level, tier = 1, "standard"
    task_types = ("system.self_evaluate",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        from ..models import Agent

        exps = ctx.db.scalars(select(Experiment).where(Experiment.status.in_(("completed", "abandoned")))).all()
        errs = [experiments.prediction_error(e.predicted, e.actual)["mape"] for e in exps]
        errs = [x for x in errs if x is not None]
        agents = ctx.db.scalars(select(Agent)).all()
        perf = []
        for a in agents:
            n = a.tasks_succeeded + a.tasks_failed + a.tasks_blocked
            perf.append({"agent": a.id, "tasks": n, "success_rate": round(a.tasks_succeeded / n, 3) if n else None,
                         "failure_rate": round(a.tasks_failed / n, 3) if n else None, "cost_usd": round(a.cost_total_usd, 4)})
        proposals = [f"Investigate failures of agent '{p['agent']}' (failure rate {p['failure_rate']})"
                     for p in perf if p["failure_rate"] and p["failure_rate"] > 0.2]
        mape = round(sum(errs) / len(errs), 4) if errs else None
        if mape is not None and mape > 0.5:
            proposals.append("Forecasts miss by >50% on average: widen uncertainty and recalibrate CTR/CVR planning assumptions")
        return AgentOutput(summary=f"Self-evaluation: {len(exps)} finished experiments, forecast MAPE {mape}",
                           result={"forecast_mape": mape, "experiments": len(exps), "agent_performance": perf, "proposals": proposals},
                           recommendations=proposals, epistemic="verified", confidence=0.9,
                           risks=["Proposals require human review; agents cannot modify their own permissions or limits"])


ALL_AGENTS: list[BaseAgent] = [
    CEOAgent(), ChiefIntelligenceAgent(), CFOAgent(), RiskAgent(), PlatformResearchAgent(), ProductAnalystAgent(),
    TransformationLabAgent(), SupplierAgent(), BrandStudioAgent(), ContentAgent(), AdvertisingAgent(),
    StoreBuilderAgent(), ExperimentAgent(), SelfImprovementAgent(),
]


def build_orchestrator():
    from .flare_agents import flare_agents
    from .orchestrator import orchestrator
    from .autonomy_agents import DevilsAdvocateAgent, ModelHunterAgent
    from .creative_agent import CreativeDirectorAgent
    from .perf_agent import PerformanceEngineerAgent

    for a in [*ALL_AGENTS, *flare_agents(), PerformanceEngineerAgent(), CreativeDirectorAgent(), ModelHunterAgent(), DevilsAdvocateAgent()]:
        if a.id not in orchestrator.agents:
            orchestrator.register(a)
    return orchestrator
