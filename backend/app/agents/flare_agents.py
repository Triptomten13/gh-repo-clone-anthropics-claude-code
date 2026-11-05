"""Rocky Flare agents. All of them run through the central orchestrator, so they
inherit budgets, kill switch, suspension, audit, dedupe and depth limits.

* FlareEngineAgent    – creative engines (directions, mutations, think-sideways, field analysis, campaigns, assets, revisions)
* CouncilAgent        – panels, councils, creative competitions and discussions (spawns persona tasks, then synthesises)
* PersonaAgent        – one per editable persona; evaluates, authors concepts, takes discussion turns
* CreativeAnalystAgent – learns from real campaign performance; updates persona calibration memory
* CommercialAgent     – the eight commercial-intelligence modules
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from ..flare import assets as A
from ..flare import campaigns as C
from ..flare import commercial as CM
from ..flare import creative, field
from ..flare import genres as G
from ..flare import mutation as M
from ..flare import personalization, personas, sideways
from ..flare import service as S
from ..flare.schemas import PersonaEvaluation
from ..flare.taxonomy import GENRES
from ..models import (Brand, BrandConcept, Campaign, CampaignPerformance, CollaborationSession, CollaborationTurn, CreativeAsset, Experiment,
                      Opportunity, Persona, PersonaMemory, Product, Supplier, Task)
from .base import AgentContext, AgentOutput, BaseAgent, Blocked


def _persona(ctx: AgentContext, pid: str) -> dict[str, Any]:
    p = ctx.db.get(Persona, pid)
    if p is None:
        raise Blocked(f"persona {pid} not found")
    if not p.active:
        raise Blocked(f"persona {pid} is inactive")
    return S.persona_dict(p)


def _ctx(ctx: AgentContext, pid: int | None) -> dict[str, Any]:
    if pid is None:
        raise Blocked("product_id required")
    try:
        return S.build_context(ctx.db, pid)
    except LookupError as e:
        raise Blocked(str(e)) from e


def _session(ctx: AgentContext, sid: int) -> CollaborationSession:
    s = ctx.db.get(CollaborationSession, sid)
    if s is None:
        raise Blocked(f"session {sid} not found")
    return s


# =====================================================================================
class FlareEngineAgent(BaseAgent):
    id, name, division = "flare_engine", "Rocky Flare Creative Engine", "creative_studio"
    description = "Genre intelligence, creative directions, mutation graphs, think-sideways, field analysis, campaign matrices, assets, revisions."
    level, tier = 2, "standard"
    task_types = ("flare.directions", "flare.mutate", "flare.sideways", "flare.field_analysis", "flare.campaign_matrix", "flare.assets",
                  "flare.revise", "flare.ecosystem")

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        return getattr(self, "_" + task.type.split(".", 1)[1])(ctx, task)

    def _directions(self, ctx: AgentContext, task: Task) -> AgentOutput:
        c = _ctx(ctx, task.payload.get("product_id"))
        n = max(5, int(task.payload.get("n", 5)))
        dirs = G.creative_directions(c["profile"], n=n, learned=c["learned"], usage=c["usage"])
        matches = G.match_genres(c["profile"], c["learned"], top=10)
        return AgentOutput(summary=f"{len(dirs)} creative directions for '{c['product']['name']}'",
                           result={"directions": [d.model_dump() for d in dirs], "genre_matches": [m.model_dump() for m in matches],
                                   "profile": {"tags": c["profile"].tags, "tier": c["profile"].tier, "category_typical": list(c["profile"].category_typical)}},
                           epistemic="hypothesis", confidence=0.5)

    def _mutate(self, ctx: AgentContext, task: Task) -> AgentOutput:
        c = _ctx(ctx, task.payload.get("product_id"))
        p = c["product_row"]
        nodes, edges = M.mutate(p.name, p.category, p.tags, p.supplier, p.retail_price, c["profile"].tags)
        S.save_graph(ctx.db, f"mutation:{p.id}",
                     [{"key": n.key, "kind": n.mutation_type, "label": n.title if n.key == "base" else n.mutation_type.replace("_", " "),
                       "data": n.model_dump()} for n in nodes],
                     [e.model_dump() for e in edges])
        return AgentOutput(summary=f"'{p.name}': {len(nodes) - 1} mutations; top: {nodes[0].title}",
                           result={"nodes": [n.model_dump() for n in nodes], "edges": [e.model_dump() for e in edges], "innovation": c["innovation"]},
                           epistemic="hypothesis", confidence=0.45,
                           risks=[f"{n.title}: regulatory risk {n.regulatory_risk}/5" for n in nodes if n.regulatory_risk >= 4])

    def _sideways(self, ctx: AgentContext, task: Task) -> AgentOutput:
        pid = task.payload.get("product_id")
        q = task.payload.get("question") or ""
        challenge = next((x for x in sideways.CHALLENGES if x["id"] == task.payload.get("challenge_id")), None)
        if challenge:
            return self._challenge(ctx, challenge, pid)
        c = _ctx(ctx, pid)
        p = c["product_row"]
        mode = sideways.classify_question(q) if q else "full"
        res = sideways.think_sideways(p.name, c["text"], set(p.tags or []) | set(c["profile"].tags), p.net_margin)
        extra: dict[str, Any] = {"mode": mode}
        if mode in ("identities", "premium"):
            dirs = G.creative_directions(c["profile"], n=8, learned=c["learned"], usage=c["usage"])
            if mode == "premium":
                dirs = [d for d in dirs if d.scores.expected_positioning == "premium"] or dirs
            extra["identities"] = [d.model_dump() for d in G.most_distinct(dirs, 3)]
        if mode == "ecosystem":
            prods = ctx.db.scalars(select(Product)).all()
            extra["ecosystems"] = [field.build_ecosystem(t, prods) for t in field.recommend_ecosystems(c["text"])]
        if mode == "unused_model":
            from ..engines import business_models as BM

            bm = BM.evaluate(BM.traits_from_product(p))
            common = {"dropshipping", "traditional_ecommerce", "affiliate_marketing", "print_on_demand"}
            extra["uncommon_models"] = [m for m in bm["all"] if m["model"] not in common][:5]
        if mode == "audience":
            extra["audience_monetization"] = [o.model_dump() for o in CM.analyse("audience_monetization", p.name, c["text"], p.tags)]
        nodes = [{"key": "product", "kind": "product", "label": p.name}] + [
            {"key": f"domain:{d['domain']}", "kind": "domain", "label": d["domain"].replace("_", " "), "data": d} for d in res["domains"]]
        for e in res["graph_edges"]:
            if e["target"] not in {n["key"] for n in nodes}:
                dom, cat = e["target"].split(":", 1)
                item = next((i for i in res["items"] if i["domain"] == dom and i["category"] == sideways.CATEGORY_LABELS.get(cat)), None)
                nodes.append({"key": e["target"], "kind": cat, "label": (item or {}).get("text", e["target"])})
        S.save_graph(ctx.db, f"sideways:{p.id}", nodes, res["graph_edges"])
        if q and task.payload.get("use_llm"):
            res["llm"] = self._llm_sideways(ctx, p, q, res)
        return AgentOutput(summary=f"Think Sideways for '{p.name}' ({mode}): {len(res['domains'])} cross-industry domains",
                           result={**res, **extra, "question": q}, epistemic="hypothesis", confidence=0.4,
                           recommendations=[c_["title"] for c_ in res["high_potential"]])

    def _llm_sideways(self, ctx: AgentContext, p: Product, q: str, res: dict[str, Any]) -> dict[str, Any]:
        persona = _persona(ctx, "the_visionary")
        schema = {"type": "object", "additionalProperties": False, "required": ["ideas"], "properties": {"ideas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["title", "description", "bridge", "how_to_validate"],
            "properties": {k: {"type": "string"} for k in ("title", "description", "bridge", "how_to_validate")}}}}}
        r = ctx.llm(personas.system_prompt(persona) + " " + self.SYSTEM_RULES,
                    f"Product: {p.name}. Question: {q}\nFacts: traits={res['traits']}, domains={[d['domain'] for d in res['domains']]}.\n"
                    "Give 5 unexpected, legitimate ideas. Each must name its bridge and how to validate demand.", schema=schema)
        return {"ideas": r.data["ideas"], "epistemic": "hypothesis", "method": "llm"}

    def _challenge(self, ctx: AgentContext, ch: dict[str, str], pid: int | None) -> AgentOutput:
        kind, arg = ch["engine"].split(":", 1)
        prods = ctx.db.scalars(select(Product)).all()
        result: dict[str, Any] = {"challenge": ch}
        if kind == "ecosystem":
            parts = arg.split("+")
            result["ecosystems"] = [field.build_ecosystem(parts[0], prods)]
            if "nordic" in parts:
                result["ecosystems"].append(field.build_ecosystem("nordic_survival", prods))
                result["segments"] = [field.SEGMENTS["nordic_winter_commuters"] | {"id": "nordic_winter_commuters"}]
        elif kind == "fusion":
            gs = [GENRES[g] for g in arg.split("+")]
            result["hybrid"] = G.fuse(gs[0], gs[1], extras=gs[2:], usage=S.usage_counts(ctx.db)).model_dump()
            S.record_hybrid(ctx.db, result["hybrid"])
        elif kind == "innovation":
            cands = [p for p in prods if field.classify_pillars(f"{p.name} {p.category} {' '.join(p.tags or [])}").get("B_survival")][:5]
            result["candidates"] = [{"product": p.name, "product_id": p.id, "modular": [i for i in M.innovation_lab(p.name) if i["key"] == arg]} for p in cands]
            if not cands:
                result["note"] = "no survival products in the database yet — import or research some first"
        elif kind == "bridge":
            want = set(arg.split(","))
            result["products"] = [{"product_id": p.id, "name": p.name, "traits": sorted(set(sideways.product_traits(p.name + ' ' + p.description)) & want)}
                                  for p in prods if len(set(sideways.product_traits(p.name + " " + p.description)) & want) >= 2]
        elif kind == "commercial":
            target = ctx.db.get(Product, pid) if pid else None
            result["opportunities"] = [o.model_dump() for o in CM.analyse(arg, target.name if target else "EDC gear", target.description if target else "edc community", target.tags if target else [])]
        elif kind == "mutation":
            result["candidates"] = [{"product_id": p.id, "product": p.name, "mutation": next(n.model_dump() for n in M.mutate(p.name, p.category, p.tags, p.supplier)[0] if n.key == arg)}
                                    for p in prods[:10]]
        return AgentOutput(summary=f"Challenge: {ch['text']}", result=result, epistemic="hypothesis", confidence=0.4)

    def _field_analysis(self, ctx: AgentContext, task: Task) -> AgentOutput:
        c = _ctx(ctx, task.payload.get("product_id"))
        p = c["product_row"]
        sups = ctx.db.scalars(select(Supplier)).all()
        prods = ctx.db.scalars(select(Product)).all()
        result = {"pillars": field.classify_pillars(c["text"]), "segments": c["segments"], "innovation": c["innovation"],
                  "ecosystems": [field.build_ecosystem(t, prods) for t in field.recommend_ecosystems(c["text"])],
                  "mobility_class": c["product"]["mobility_class"], "compliance_status": c["product"]["compliance_status"],
                  "sourcing": field.sourcing_assessment(c["text"], sups),
                  "personalization": personalization.offer(p.name, p.tags or [], bool(p.supplier and p.supplier.offers_custom_packaging)),
                  "compatibility_note": "No compatibility is assumed: record verified fitment per model in the compatibility matrix."}
        risks = c["product"]["compliance_restrictions"] + c["product"]["compliance_blockers"]
        return AgentOutput(summary=f"Field analysis '{p.name}': pillars {', '.join(result['pillars']) or 'none'}; {len(c['segments'])} segments",
                           result=result, risks=risks, epistemic="hypothesis", confidence=0.45)

    def _ecosystem(self, ctx: AgentContext, task: Task) -> AgentOutput:
        prods = ctx.db.scalars(select(Product)).all()
        tpl = task.payload.get("template") or "edc_modular"
        if tpl not in field.ECOSYSTEMS:
            raise Blocked(f"unknown ecosystem template {tpl}")
        eco = field.build_ecosystem(tpl, prods)
        S.save_graph(ctx.db, f"ecosystem:{tpl}", [{"key": m["id"], "kind": "module", "label": m["label"], "data": m} for m in eco["modules"]], eco["edges"])
        return AgentOutput(summary=f"{eco['label']}: coverage {eco['coverage']:.0%}", result=eco, epistemic="estimate", confidence=0.5)

    def _campaign_matrix(self, ctx: AgentContext, task: Task) -> AgentOutput:
        ctx.check("campaign.draft")
        c = _ctx(ctx, task.payload.get("product_id"))
        concept = ctx.db.get(BrandConcept, task.payload["concept_id"]) if task.payload.get("concept_id") else None
        genre_ids = [concept.primary_genre, concept.secondary_genre] if concept else \
            G.creative_directions(c["profile"], n=1, learned=c["learned"])[0].hybrid_id.split("+")
        seg = c["segments"][0] if c["segments"] else None
        audience = concept.audience if concept else (seg["label"] if seg else GENRES[genre_ids[0]].audience)
        problem = seg["problems"][0] if seg else "gear that fails when conditions turn"
        cells = C.testing_matrix(c["product"]["name"], genre_ids, audience, problem, c["break_even_cac"], c["learned_identity"])
        brand_id = concept.brand_id if concept else None
        ids = []
        for cell in cells:
            row = Campaign(brand_id=brand_id, product_id=c["product"]["id"], concept_id=concept.id if concept else None,
                           name=f"{(concept.name if concept else c['product']['name'])} · {C.IDENTITIES[cell.identity]['label']} · {cell.platform}",
                           identity=cell.identity, genre="+".join(genre_ids), platform=cell.platform, audience=cell.target_audience, hook=cell.hook,
                           message=cell.main_message, visual_concept=cell.visual_concept, video_format=cell.video_format, cta=cell.call_to_action,
                           budget_recommendation_sek=cell.budget_recommendation_sek, measurement=cell.measurement, flags=cell.flags)
            ctx.db.add(row)
            ctx.db.flush()
            ids.append(row.id)
        risks = [] if c["break_even_cac"] else ["no CFO economics: budget recommendation unavailable — run cfo.economics"]
        return AgentOutput(summary=f"{len(cells)} campaign cells drafted (launching any requires LEVEL 5 approval)",
                           result={"campaign_ids": ids, "cells": [x.model_dump() for x in cells]}, risks=risks, epistemic="hypothesis", confidence=0.4)

    def _assets(self, ctx: AgentContext, task: Task) -> AgentOutput:
        ctx.check("asset.generate")
        concept = ctx.db.get(BrandConcept, task.payload.get("concept_id"))
        if concept is None:
            raise Blocked("concept not found")
        kinds = task.payload.get("kinds") or [*A.VISUAL_KINDS, *A.BRIEF_KINDS]
        provider = task.payload.get("provider", "procedural_svg")
        orn, geo = A.ornament_for([concept.primary_genre, concept.secondary_genre])
        prod = ctx.db.get(Product, concept.product_id) if concept.product_id else None
        spec = {"name": concept.name, "tagline": concept.tagline, "palette": (concept.direction or {}).get("color_palette", []),
                "typography": (concept.direction or {}).get("typography", {}), "direction": concept.direction, "ornament": orn, "geometry": geo,
                "product": prod.name if prod else ""}
        made = []
        for kind in kinds:
            prev = ctx.db.scalars(select(CreativeAsset).where(CreativeAsset.concept_id == concept.id, CreativeAsset.kind == kind)
                                  .order_by(CreativeAsset.version.desc())).first()
            variation = (prev.version if prev else 0) + int(task.payload.get("variation_offset", 0))
            try:
                out = A.generate(kind, spec, provider, variation)
            except LookupError as e:
                raise Blocked(str(e)) from e
            row = CreativeAsset(concept_id=concept.id, brand_id=concept.brand_id, product_id=concept.product_id, kind=kind,
                                title=f"{concept.name} — {kind.replace('_', ' ')} v{(prev.version + 1) if prev else 1}",
                                prompt=json.dumps({k: v for k, v in spec.items() if k != "direction"})[:2000], provider=out["provider"],
                                mime=out["mime"], content=out["content"], params={"variation": variation},
                                tags=[concept.primary_genre, concept.secondary_genre, kind], version=(prev.version + 1) if prev else 1,
                                parent_id=prev.id if prev else None)
            ctx.db.add(row)
            ctx.db.flush()
            row.lineage_id = prev.lineage_id if prev else row.id
            made.append(row.id)
        return AgentOutput(summary=f"{len(made)} assets generated for '{concept.name}'", result={"asset_ids": made}, epistemic="verified", confidence=1.0)

    def _revise(self, ctx: AgentContext, task: Task) -> AgentOutput:
        ctx.check("concept.revise")
        old = ctx.db.get(BrandConcept, task.payload.get("concept_id"))
        if old is None:
            raise Blocked("concept not found")
        c = _ctx(ctx, old.product_id) if old.product_id else None
        d = S.concept_dict(old)
        d["hybrid"] = old.hybrid
        d["direction"] = old.direction
        d = creative.deterministic_revision(d, (old.originality or {}).get("flags", []), old.version, None)
        prof = c["profile"] if c else S.profile_product(old.name)
        d = creative.revise_until_clean(d, prof, (c or {}).get("product", {}), (c or {}).get("usage", {}))
        new = S.save_concept(ctx.db, d, old.product_id, old.author_persona, old.session_id, parent=old)
        return AgentOutput(summary=f"'{old.name}' v{old.version} → '{new.name}' v{new.version} (originality {new.originality.get('score')})",
                           result={"concept_id": new.id, "requires_revision": new.originality.get("requires_revision")}, epistemic="hypothesis", confidence=0.5)


# =====================================================================================
class CouncilAgent(BaseAgent):
    id, name, division = "flare_council", "Rocky Flare Council Chair", "executive"
    description = "Runs review panels, creative councils, creative competitions and structured discussions; records dissent, never forces consensus."
    level, tier = 2, "standard"
    task_types = ("flare.panel", "flare.council", "flare.competition", "flare.discussion", "flare.judge", "flare.synthesize")

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        return getattr(self, "_" + task.type.split(".", 1)[1])(ctx, task)

    def _new_session(self, ctx: AgentContext, kind: str, topic: str, pid: int | None, concept_ids: list[int], members: list[str]) -> CollaborationSession:
        s = CollaborationSession(kind=kind, topic=topic, product_id=pid, concept_ids=concept_ids, members=members)
        ctx.db.add(s)
        ctx.db.flush()
        return s

    def _members(self, ctx: AgentContext, ids: list[str]) -> list[Persona]:
        out = []
        for pid in ids:
            p = ctx.db.get(Persona, pid)
            if p is None:
                raise Blocked(f"unknown persona {pid}")
            if p.active:
                out.append(p)
        return out

    def _spawn_evaluations(self, ctx: AgentContext, s: CollaborationSession, members: list[Persona], seat_prefix: str = "") -> list[int]:
        return [ctx.spawn("persona.evaluate", {"session_id": s.id, "persona_id": m.id, "seat": seat_prefix + m.id}, priority=30, agent_id=m.agent_id).id
                for m in members]

    def _ensure_concepts(self, ctx: AgentContext, pid: int, n: int = 3) -> list[int]:
        existing = ctx.db.scalars(select(BrandConcept).where(BrandConcept.product_id == pid, BrandConcept.status.in_(("draft", "shortlisted")))
                                  .order_by(BrandConcept.id.desc())).all()
        if len(existing) >= n:
            return [c.id for c in existing[:n]]
        c = _ctx(ctx, pid)
        engine = _persona(ctx, "flare_engine")
        ids = [x.id for x in existing]
        for i in range(n - len(ids)):
            concept = creative.author_concept({**engine, "genre_affinities": {}}, c["product"], c["profile"], c["segments"], c["innovation"],
                                              c["learned"], c["usage"], seed=f"council{i}", pick=len(ids))
            ids.append(S.save_concept(ctx.db, concept, pid, "flare_engine").id)
        return ids

    def _panel(self, ctx: AgentContext, task: Task) -> AgentOutput:
        cids = task.payload.get("concept_ids") or []
        pid = task.payload.get("product_id")
        if not cids and pid:
            cids = self._ensure_concepts(ctx, pid)
        if not cids:
            raise Blocked("panel needs concept_ids or a product_id")
        members = self._members(ctx, task.payload.get("members") or personas.DEFAULT_PANEL)
        s = self._new_session(ctx, "panel", task.payload.get("topic") or "Creative review panel", pid, cids, [m.id for m in members])
        deps = self._spawn_evaluations(ctx, s, members)
        ctx.spawn("flare.synthesize", {"session_id": s.id}, priority=80, depends_on=deps)
        return AgentOutput(summary=f"Review panel #{s.id}: {len(members)} members on {len(cids)} concepts", result={"session_id": s.id},
                           epistemic="verified", confidence=1.0)

    def _council(self, ctx: AgentContext, task: Task) -> AgentOutput:
        pid = task.payload.get("product_id")
        if pid is None:
            raise Blocked("council needs a product_id")
        cids = task.payload.get("concept_ids") or self._ensure_concepts(ctx, pid)
        members = self._members(ctx, task.payload.get("members") or personas.DEFAULT_COUNCIL)
        s = self._new_session(ctx, "council", task.payload.get("topic") or "Creative council", pid, cids, [m.id for m in members])
        deps = self._spawn_evaluations(ctx, s, members)
        ctx.spawn("flare.synthesize", {"session_id": s.id}, priority=80, depends_on=deps)
        return AgentOutput(summary=f"Creative council #{s.id}: {len(members)} members", result={"session_id": s.id}, epistemic="verified", confidence=1.0)

    def _competition(self, ctx: AgentContext, task: Task) -> AgentOutput:
        pid = task.payload.get("product_id")
        if pid is None:
            raise Blocked("competition needs a product_id")
        comps = self._members(ctx, task.payload.get("competitors") or personas.DEFAULT_COMPETITORS)
        judges = task.payload.get("judges") or personas.DEFAULT_PANEL
        s = self._new_session(ctx, "competition", task.payload.get("topic") or "Creative competition", pid, [], [m.id for m in comps])
        deps = [ctx.spawn("persona.concept", {"session_id": s.id, "persona_id": m.id, "product_id": pid}, priority=25, agent_id=m.agent_id).id
                for m in comps]
        ctx.spawn("flare.judge", {"session_id": s.id, "judges": judges}, priority=60, depends_on=deps)
        return AgentOutput(summary=f"Creative competition #{s.id}: {len(comps)} independent creatives", result={"session_id": s.id},
                           epistemic="verified", confidence=1.0)

    def _judge(self, ctx: AgentContext, task: Task) -> AgentOutput:
        s = _session(ctx, task.payload["session_id"])
        s.concept_ids = [c.id for c in ctx.db.scalars(select(BrandConcept).where(BrandConcept.session_id == s.id)).all()]
        if not s.concept_ids:
            raise Blocked("no concepts were submitted")
        judges = self._members(ctx, task.payload.get("judges") or personas.DEFAULT_PANEL)
        deps = self._spawn_evaluations(ctx, s, judges, seat_prefix="judge:")
        ctx.spawn("flare.synthesize", {"session_id": s.id}, priority=80, depends_on=deps)
        return AgentOutput(summary=f"Judging {len(s.concept_ids)} concepts with {len(judges)} judges", result={"session_id": s.id},
                           epistemic="verified", confidence=1.0)

    def _discussion(self, ctx: AgentContext, task: Task) -> AgentOutput:
        pid = task.payload.get("product_id")
        if pid is None:
            raise Blocked("discussion needs a product_id")
        seats = personas.DISCUSSION_SEATS
        s = self._new_session(ctx, "discussion", task.payload.get("topic") or "Opportunity discussion", pid, [], [p for p, _ in seats])
        prev: list[int] = []
        for i, (persona_id, seat) in enumerate(seats):
            p = ctx.db.get(Persona, persona_id)
            t = ctx.spawn("persona.turn", {"session_id": s.id, "persona_id": persona_id, "seat": seat}, priority=20 + i,
                          agent_id=p.agent_id, depends_on=prev)
            prev = [t.id]
        ctx.spawn("flare.synthesize", {"session_id": s.id}, priority=80, depends_on=prev)
        return AgentOutput(summary=f"Discussion #{s.id} opened with {len(seats)} seats", result={"session_id": s.id}, epistemic="verified", confidence=1.0)

    # ---------------------------------------------------------------- synthesis (no forced consensus)
    def _synthesize(self, ctx: AgentContext, task: Task) -> AgentOutput:
        s = _session(ctx, task.payload["session_id"])
        turns = ctx.db.scalars(select(CollaborationTurn).where(CollaborationTurn.session_id == s.id)).all()
        absent = sorted(set(s.members) - {t.persona_id for t in turns}) if s.kind != "competition" else []
        if s.kind == "discussion":
            decision = next((t for t in turns if t.seat == "ceo"), None)
            dissent = [{"persona": t.persona_id, "stance": t.stance, "message": t.message} for t in turns if t.stance in ("oppose", "caution")]
            s.decision = {"outcome": (decision.scores or {}).get("outcome") if decision else "no decision", "decided_by": "the_ceo" if decision else None,
                          "evidence": decision.evidence if decision else [], "dissent": dissent, "absent": absent}
        else:
            per: dict[int, list[CollaborationTurn]] = {}
            for t in turns:
                cid = (t.scores or {}).get("concept_id")
                if cid is not None and t.stance != "propose":
                    per.setdefault(cid, []).append(t)
            ranking = []
            for cid, ts in per.items():
                vals = [t.scores["weighted_score"] for t in ts]
                stances = Counter(t.stance for t in ts)
                sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                c = ctx.db.get(BrandConcept, cid)
                split = sd > 12 or (stances["support"] and stances["oppose"])
                ranking.append({"concept_id": cid, "name": c.name if c else str(cid), "author": c.author_persona if c else None,
                                "mean": round(statistics.mean(vals), 1), "stdev": round(sd, 1), "min": min(vals), "max": max(vals),
                                "stances": dict(stances), "consensus": "split" if split else "aligned",
                                "dissent": [{"persona": t.persona_id, "stance": t.stance, "score": t.scores["weighted_score"],
                                             "why": "; ".join((t.scores.get("weaknesses") or [])[:2])} for t in ts if t.stance == "oppose"],
                                "originality_ok": not (c.originality or {}).get("requires_revision", True) if c else False})
                if c:
                    c.panel_scores = {**(c.panel_scores or {}), **{t.persona_id: t.scores["weighted_score"] for t in ts}}
            ranking.sort(key=lambda r: r["mean"], reverse=True)
            winner = next((r for r in ranking if r["originality_ok"]), None)
            if winner:
                wc = ctx.db.get(BrandConcept, winner["concept_id"])
                if wc.status == "draft":
                    wc.status = "shortlisted"
                if s.kind == "competition" and wc.author_persona:
                    ctx.db.add(PersonaMemory(persona_id=wc.author_persona, kind="win", concept_id=wc.id,
                                             note=f"won competition #{s.id} with mean {winner['mean']}"))
            s.decision = {"ranking": ranking, "shortlisted": winner["concept_id"] if winner else None, "absent": absent,
                          "note": "All concepts are kept. Shortlisting is not approval — a human approves brands."}
            if s.kind == "council":
                s.decision["council"] = self._council_outputs(ctx, s, turns, ranking)
        s.status, s.concluded_at = "concluded", datetime.now(timezone.utc)
        return AgentOutput(summary=f"{s.kind.capitalize()} #{s.id} concluded", result={"session_id": s.id, "decision": s.decision},
                           epistemic="estimate", confidence=0.6,
                           risks=[f"split verdict on '{r['name']}'" for r in s.decision.get("ranking", []) if r["consensus"] == "split"])

    def _council_outputs(self, ctx: AgentContext, s: CollaborationSession, turns: list[CollaborationTurn], ranking: list[dict]) -> dict[str, Any]:
        c = _ctx(ctx, s.product_id)
        creative_seats = {"creative_director", "ancient_symbolism_ad", "tactical_design_director"}
        creative_scores: dict[int, list[float]] = {}
        for t in turns:
            if t.persona_id in creative_seats and (t.scores or {}).get("concept_id") is not None:
                creative_scores.setdefault(t.scores["concept_id"], []).append(t.scores["weighted_score"])
        best_creative = max(creative_scores, key=lambda k: statistics.mean(creative_scores[k])) if creative_scores else None
        opp = ctx.db.scalars(select(Opportunity).where(Opportunity.product_id == s.product_id).order_by(Opportunity.id.desc())).first()
        sub = CM.analyse("subscription_intel", c["product"]["name"], c["text"], c["product"]["tags"])
        func = c["innovation"][0] if c["innovation"] else None
        tech = [f"{i['question']} → verify: {i['verification']}" for i in c["innovation"][:3]]
        if c["product"]["mobility_class"] in ("vehicle", "electrical_system", "vehicle_safety_affecting"):
            tech.insert(0, f"mobility class '{c['product']['mobility_class']}': fitment and electrical/mechanical safety must be verified per model")
        reg = c["product"]["compliance_blockers"] + c["product"]["compliance_restrictions"]
        for r in ranking:
            bc = ctx.db.get(BrandConcept, r["concept_id"])
            reg += [f"{bc.name}: {f['detail']}" for f in (bc.originality or {}).get("flags", []) if f["severity"] in ("block", "review")][:3]
        budget = C.test_budget(c["break_even_cac"])
        return {
            "best_functional_design": func,
            "best_creative_direction": next((r for r in ranking if r["concept_id"] == best_creative), None),
            "best_brand_opportunity": next((r for r in ranking if r["originality_ok"]), None),
            "best_monetization_strategy": {"business_models": (opp.business_models if opp else [])[:2], "recurring": sub[0].model_dump()},
            "main_technical_risks": tech, "main_regulatory_risks": reg[:8],
            "recommended_next_experiment": {
                "type": "smoke test: landing page + capped paid test" if budget else "organic smoke test (no economics yet)",
                "budget_sek": budget, "success_metric": "≥20 orders at CAC ≤ break-even CAC, or pre-order sign-ups at a stated price",
                "requires_approval": bool(budget), "note": "Paid tests need a LEVEL 5 approval; nothing launches automatically."},
        }


# =====================================================================================
class PersonaAgent(BaseAgent):
    """One instance per editable persona. Reads its personality from the DB on every task."""

    level, tier = 2, "standard"
    task_types = ()  # addressed by agent_id (persona.evaluate / persona.concept / persona.turn)

    def __init__(self, persona_seed: dict[str, Any]) -> None:
        self.persona_id = persona_seed["id"]
        self.id = persona_seed["agent_id"]
        self.name = persona_seed["name"]
        self.division = persona_seed["division"]
        self.description = f"{persona_seed['role']}: {persona_seed['personality']}"

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        return persona_handle(ctx, task, task.payload.get("persona_id") or self.persona_id)


def persona_handle(ctx: AgentContext, task: Task, persona_id: str) -> AgentOutput:
    """Shared persona behaviour — also used by existing agents (CEO, CFO, Risk, …) that carry a persona."""
    p = _persona(ctx, persona_id)
    if p["agent_id"] != ctx.agent_row.id:
        raise Blocked(f"persona {persona_id} belongs to agent {p['agent_id']}, not {ctx.agent_row.id}")
    s = _session(ctx, task.payload["session_id"])
    ctx.check({"persona.evaluate": "opportunity.generate", "persona.concept": "brand.draft"}.get(task.type, "opportunity.generate"))
    if task.type == "persona.evaluate":
        c = _ctx(ctx, s.product_id) if s.product_id else {"product": {}, "innovation": []}
        evals = []
        for cid in s.concept_ids or []:
            bc = ctx.db.get(BrandConcept, cid)
            if bc is None:
                continue
            cd = S.concept_dict(bc)
            ev = personas.evaluate(p, {"concept": cd, "originality": cd["originality"], "product": c["product"], "innovation": c["innovation"]})
            ev = PersonaEvaluation(**ev).model_dump()
            msg = personas.voice(p, _eval_message(ev, bc.name))
            ctx.db.add(CollaborationTurn(session_id=s.id, persona_id=p["id"], task_id=task.id, seat=task.payload.get("seat", p["id"]),
                                         stance=ev["stance"], message=msg, scores={**ev, "concept_id": cid}, confidence=ev["confidence"],
                                         evidence=[{"criteria": ev["criteria"]}]))
            evals.append(ev)
        return AgentOutput(summary=f"{p['name']} evaluated {len(evals)} concepts", result={"evaluations": evals}, epistemic="estimate",
                           confidence=0.5, findings=[f"{e['concept_id']}: {e['weighted_score']} ({e['stance']})" for e in evals])
    if task.type == "persona.concept":
        c = _ctx(ctx, task.payload.get("product_id") or s.product_id)
        concept = creative.author_concept(p, c["product"], c["profile"], c["segments"], c["innovation"], c["learned"], c["usage"], seed=f"s{s.id}")
        source = "engine"
        if task.payload.get("use_llm"):
            concept = _llm_voice(ctx, p, concept, c)
            source = "llm"
        row = S.save_concept(ctx.db, concept, c["product"]["id"], p["id"], session_id=s.id, source=source)
        ctx.db.add(CollaborationTurn(session_id=s.id, persona_id=p["id"], task_id=task.id, seat="competitor", stance="propose",
                                     message=personas.voice(p, f"My concept: {row.name} — {row.tagline} ({GENRES[row.primary_genre].name} × "
                                                               f"{GENRES[row.secondary_genre].name}). Originality {row.originality.get('score')}."),
                                     scores={"concept_id": row.id, "originality": row.originality.get("score")}, confidence=0.5))
        return AgentOutput(summary=f"{p['name']} proposed '{row.name}'", result={"concept_id": row.id, "revisions": concept.get("revision_history")},
                           epistemic="hypothesis", confidence=0.45)
    if task.type == "persona.turn":
        return _discussion_turn(ctx, task, p, s)
    raise Blocked(f"unsupported persona task {task.type}")


CONCEPT_COPY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["name", "tagline", "story", "usp", "audience"],
                       "properties": {k: {"type": "string"} for k in ("name", "tagline", "story", "usp", "audience")}}


def _llm_voice(ctx: AgentContext, p: dict[str, Any], concept: dict[str, Any], c: dict[str, Any]) -> dict[str, Any]:
    """The persona rewrites the concept's copy in its own voice. Genres, palette and scores stay engine-computed;
    the result still has to pass the anti-generic gate."""
    facts = {"product": c["product"]["name"], "genres": [GENRES[concept["primary_genre"]].name, GENRES[concept["secondary_genre"]].name],
             "direction": concept["direction"].get("visual_direction"), "segment": c["segments"][0] if c["segments"] else None,
             "proposed_improvement": concept["usp"], "draft": {k: concept[k] for k in ("name", "tagline", "story", "usp", "audience")}}
    r = ctx.llm(personas.system_prompt(p, ctx.agent_row.model_tier),
                "Rewrite this brand concept's copy in your voice. Keep proposed improvements labelled as proposals; no claims we "
                f"cannot test; no buzzwords.\nFACTS: {json.dumps(facts, default=str)}", schema=CONCEPT_COPY_SCHEMA)
    out = {**concept, **{k: r.data[k] for k in CONCEPT_COPY_SCHEMA["required"]}}
    out["hybrid"] = {**concept["hybrid"], "name": out["name"]}
    return creative.revise_until_clean(out, c["profile"], c["product"], c["usage"], p)


def _eval_message(ev: dict[str, Any], name: str) -> str:
    parts = [f"'{name}' scores {ev['weighted_score']:.0f} from my seat ({ev['stance']})."]
    if ev["strengths"]:
        parts.append("Strong: " + ", ".join(ev["strengths"]) + ".")
    if ev["weaknesses"]:
        parts.append("Weak: " + ", ".join(ev["weaknesses"]) + ".")
    if ev["generic_elements"]:
        parts.append("Generic: " + "; ".join(ev["generic_elements"][:2]) + ".")
    if ev["improvements"]:
        parts.append("Fix: " + ev["improvements"][0] + ".")
    return " ".join(parts)


def _discussion_turn(ctx: AgentContext, task: Task, p: dict[str, Any], s: CollaborationSession) -> AgentOutput:
    c = _ctx(ctx, s.product_id)
    prod = c["product"]
    seat = task.payload["seat"]
    prior = ctx.db.scalars(select(CollaborationTurn).where(CollaborationTurn.session_id == s.id).order_by(CollaborationTurn.id)).all()
    stance, msg, evidence, scores = "neutral", "", [], {}
    if seat == "scout":
        tv, plats = prod.get("trend_velocity"), prod.get("platforms_seen")
        if tv is not None:
            msg = f"Interest signal for '{prod['name']}': trend velocity {tv:.0f}/100 on {', '.join(plats) or 'unknown platforms'}."
            stance = "propose" if tv >= 60 else "neutral"
        else:
            msg = f"I have no trend observations for '{prod['name']}' yet — this is a hunch until we collect data."
        if prod.get("purchase_signal") is None and prod.get("engagement_signal") is not None:
            msg += " Note: the demand signal is engagement, not purchases."
        evidence = [{"trend_velocity": tv, "platforms": plats, "purchase_signal": prod.get("purchase_signal")}]
    elif seat == "visionary":
        ctx.check("brand.draft")
        ids = []
        for i in range(3):  # three different directions, authored like any competition concept
            concept = creative.author_concept(p, prod, c["profile"], c["segments"], c["innovation"], c["learned"], c["usage"],
                                              seed=f"d{s.id}", pick=i)
            ids.append(S.save_concept(ctx.db, concept, prod["id"], p["id"], session_id=s.id).id)
        s.concept_ids = ids
        saved = [ctx.db.get(BrandConcept, i) for i in ids]
        msg = "We could take this three ways: " + "; ".join(
            f"{x.name} ({GENRES[x.primary_genre].name} × {GENRES[x.secondary_genre].name})" for x in saved) + "."
        stance, evidence = "propose", [{"concept_ids": ids}]
    elif seat == "architect":
        concepts = [ctx.db.get(BrandConcept, i) for i in s.concept_ids]
        families = {cc.id: {GENRES[cc.primary_genre].family, GENRES[cc.secondary_genre].family} for cc in concepts if cc}
        pairs = [(a, b) for a in concepts for b in concepts if a and b and a.id < b.id and families[a.id] & families[b.id]]
        sup = c["product_row"].supplier
        if pairs:
            a, b = pairs[0]
            msg = (f"'{a.name}' and '{b.name}' can share one storefront stack, one fulfilment flow"
                   + (f" and supplier {sup.name}" if sup else "") + " — they differ in identity, not infrastructure.")
            stance = "support"
        else:
            msg = "These concepts need different infrastructure; pick one to avoid running parallel stacks."
            stance = "caution"
        brands = ctx.db.scalars(select(Brand)).all()
        if brands:
            msg += f" Check fit with existing brands ({', '.join(b.name for b in brands[:3])}) before creating a new one."
        evidence = [{"shared_pairs": [(a.id, b.id) for a, b in pairs]}]
    elif seat == "accountant":
        econ = c["economics"]
        sc = (econ.get("pricing") or {}).get("scenarios") or {}
        if not sc:
            msg, stance = "There are no verified cost inputs. Until wholesale and shipping costs are recorded, every margin is fiction.", "oppose"
        else:
            prem, std = sc.get("premium", {}), sc.get("standard", {})
            better = "premium" if (prem.get("contribution_margin") or 0) > (std.get("contribution_margin") or 0) else "standard"
            msg = (f"Standard {std.get('price')} kr → {std.get('contribution_margin')} kr contribution; premium {prem.get('price')} kr → "
                   f"{prem.get('contribution_margin')} kr. The {better} version has the better estimated contribution, but it needs validation — "
                   f"break-even CAC is {c['break_even_cac']} kr.")
            stance = "support" if (std.get("contribution_margin") or 0) > 0 else "oppose"
            scores = {"premium_contribution": prem.get("contribution_margin"), "standard_contribution": std.get("contribution_margin")}
        evidence = [{"scenarios": {k: v.get("contribution_margin") for k, v in sc.items()}}]
    elif seat == "devils_advocate":
        issues = []
        if prod.get("purchase_signal") is None:
            issues.append("demand is not backed by purchase data" + (" — only engagement" if prod.get("engagement_signal") is not None else ""))
        if (prod.get("score_confidence") or 0) < 0.5:
            issues.append(f"opportunity score rests on thin data (coverage {prod.get('score_confidence')})")
        if prod.get("compliance_status") in ("blocked", "restricted"):
            issues.append(f"compliance is '{prod['compliance_status']}': " + "; ".join((prod.get("compliance_blockers") or prod.get("compliance_restrictions"))[:2]))
        for i in s.concept_ids:
            bc = ctx.db.get(BrandConcept, i)
            if bc and (bc.originality or {}).get("requires_revision"):
                issues.append(f"'{bc.name}' still fails the anti-generic gate")
        sens = {f["code"] for i in s.concept_ids for f in ((ctx.db.get(BrandConcept, i).originality or {}).get("flags", []))
                if f["severity"] == "review"}
        if sens:
            issues.append("sensitivity reviews pending: " + ", ".join(sorted(sens)))
        stance = "oppose" if len(issues) >= 2 else "caution" if issues else "support"
        msg = ("Before anyone gets excited: " + "; ".join(issues) + ".") if issues else "I tried to break it and couldn't — that's rare."
        evidence, scores = [{"issues": issues}], {"serious_issues": len(issues)}
    elif seat == "creative_director":
        concepts = [ctx.db.get(BrandConcept, i) for i in s.concept_ids if ctx.db.get(BrandConcept, i)]
        if concepts:
            vis = max(concepts, key=lambda x: (x.evaluation or {}).get("visual_recognition", 0))
            vid = max(concepts, key=lambda x: (x.evaluation or {}).get("marketing_potential", 0))
            msg = (f"'{vis.name}' is the visually strongest ({(vis.evaluation or {}).get('visual_recognition')}); "
                   f"'{vid.name}' has the better short-form video potential ({(vid.evaluation or {}).get('marketing_potential')}).")
            stance = "support"
            evidence = [{"visual": vis.id, "video": vid.id}]
        else:
            msg, stance = "Nothing to direct yet.", "caution"
    elif seat == "ceo":
        da = next((t for t in prior if t.seat == "devils_advocate"), None)
        acc = next((t for t in prior if t.seat == "accountant"), None)
        serious = (da.scores or {}).get("serious_issues", 0) if da else 0
        if prod.get("compliance_status") == "blocked":
            outcome, msg = "reject", "Rejected: compliance blockers must be resolved first."
        elif acc and acc.stance == "oppose":
            outcome, msg = "iterate", "Not yet: get verified costs and a positive contribution before any test."
        elif serious >= 2:
            outcome, msg = "iterate", "Iterate: gather purchase evidence and fix the flagged issues, then come back."
        else:
            outcome = "approve_validation_experiment"
            ctx.check("experiment.create")
            best = ctx.db.get(BrandConcept, s.concept_ids[0]) if s.concept_ids else None
            exp = Experiment(name=f"Validation: {best.name if best else prod['name']}", hypothesis=(
                f"Buyers will pay for '{prod['name']}' as '{best.name if best else prod['name']}' at a positive contribution."),
                success_metrics={"min_roas": 2.0, "min_contribution_margin": 0, "min_orders": 20, "kill_roas": 1.0},
                predicted={}, budget_sek=0, status="draft")
            ctx.db.add(exp)
            ctx.db.flush()
            msg = (f"Approve a limited validation experiment (#{exp.id}, draft, no budget). Any paid spend needs a LEVEL 5 approval.")
            evidence = [{"experiment_id": exp.id}]
        stance, scores = "decide", {"outcome": outcome}
        evidence += [{"dissent": [t.persona_id for t in prior if t.stance in ("oppose", "caution")]}]
    else:
        raise Blocked(f"unknown seat {seat}")
    ctx.db.add(CollaborationTurn(session_id=s.id, persona_id=p["id"], task_id=task.id, seat=seat, stance=stance,
                                 message=personas.voice(p, msg), scores=scores, evidence=evidence, confidence=0.6))
    return AgentOutput(summary=f"{p['name']} ({seat}): {stance}", result={"stance": stance, "message": msg}, epistemic="estimate", confidence=0.6)


# =====================================================================================
class CreativeAnalystAgent(BaseAgent):
    id, name, division = "p_creative_analyst", "Creative Analyst", "creative_studio"
    description = "Learns from actual campaign performance: ranks by contribution, updates Style DNA and persona calibration."
    level, tier = 1, "standard"
    task_types = ("flare.campaign_analysis",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        camps = ctx.db.scalars(select(Campaign)).all()
        if task.payload.get("brand_id"):
            camps = [c for c in camps if c.brand_id == task.payload["brand_id"]]
        perf = ctx.db.scalars(select(CampaignPerformance)).all()
        res = C.analyse(camps, perf)
        updated = 0
        for row in res["campaigns"]:
            camp = next(c for c in camps if c.id == row["campaign_id"])
            if not camp.concept_id or row["profit_per_100_spend"] is None:
                continue
            bc = ctx.db.get(BrandConcept, camp.concept_id)
            for pid, score in (bc.panel_scores or {}).items() if bc else []:
                ctx.db.query(PersonaMemory).filter(PersonaMemory.persona_id == pid, PersonaMemory.concept_id == bc.id,
                                                   PersonaMemory.kind == "calibration").delete()
                ctx.db.add(PersonaMemory(persona_id=pid, kind="calibration", concept_id=bc.id, predicted=score, actual=row["profit_per_100_spend"],
                                         note=f"campaign {camp.id}: {row['profit_per_100_spend']} profit per 100 kr spend"))
                updated += 1
        dna = S.learned(ctx.db)
        return AgentOutput(summary=f"Analysed {len(res['campaigns'])} campaigns; {updated} calibration points; {res['insight'] or 'no divergence'}",
                           result={**res, "style_dna": dna}, epistemic="verified" if res["campaigns"] else "estimate", confidence=0.8,
                           recommendations=[res["insight"]] if res["insight"] else [])


class CommercialAgent(BaseAgent):
    level, tier = 1, "standard"

    def __init__(self, module: str) -> None:
        seed = personas.SEED_BY_ID[module]
        self.module = module
        self.id, self.name, self.division = seed["agent_id"], seed["name"], "commercial"
        self.description = seed["personality"]
        self.task_types = (f"flare.commercial.{module}",)

    def handle(self, ctx: AgentContext, task: Task) -> AgentOutput:
        pid = task.payload.get("product_id")
        p = ctx.db.get(Product, pid) if pid else None
        name = p.name if p else task.payload.get("name", "niche")
        text = f"{p.category} {' '.join(p.tags or [])} {p.description}" if p else task.payload.get("text", "")
        ops = CM.analyse(self.module, name, text, p.tags if p else [], p.retail_price if p else None, task.payload)
        return AgentOutput(summary=f"{self.name}: {len(ops)} findings for '{name}'", result={"opportunities": [o.model_dump() for o in ops]},
                           recommendations=[o.title for o in ops], epistemic="hypothesis", confidence=0.4,
                           required_approvals=[{"action": "acquisition.offer", "note": "human approval before any offer"}] if self.module == "acquisition" and ops and ops[0].requires_approval else [])


EXISTING_AGENT_PERSONA = {s["agent_id"]: s["id"] for s in personas.SEED if not s["agent_id"].startswith("p_")
                          and s["agent_id"] not in ("flare_engine", "flare_council")}


def flare_agents() -> list[BaseAgent]:
    special = {"p_creative_analyst", *(personas.SEED_BY_ID[m]["agent_id"] for m in CM.MODULES)}
    out: list[BaseAgent] = [FlareEngineAgent(), CouncilAgent(), CreativeAnalystAgent(), *(CommercialAgent(m) for m in CM.MODULES)]
    out += [PersonaAgent(s) for s in personas.SEED if s["agent_id"].startswith("p_") and s["agent_id"] not in special]
    return out
