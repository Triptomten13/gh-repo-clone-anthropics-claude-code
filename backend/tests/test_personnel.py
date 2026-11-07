"""Astral Personnel, The Bestiary and the Custom Agent Creator.

Covers: one shared register (functional departments, race/specialization/role separate, no race lock, identity grants
nothing), The Bestiary (evidentiary classes kept apart, cultural care, search, links both ways, new beings without code),
and the ONE creation pipeline behind G-SUS chat, The Bestiary and Personnel (AI + rules, custom species, several
specializations and skills, duplicates, invalid input, governance, onboarding, tests, lifecycle, history)."""
from __future__ import annotations

import json

from sqlalchemy import func, select

from app.ai import llm
from app.models import Agent, AgentVersion, Approval, AuditLog, Species, Specialization, Task
from app.personnel import creator as C
from app.personnel import personnel_data as P
from app.personnel import registry as R


def _db(fresh_db):
    return fresh_db.SessionLocal()


def _spec(**over):
    s = {"persona_name": "Astra", "title": "Emerging Technology Researcher", "species_key": "high_elf",
         "specializations": ["strategic_research", "ai_research"], "department_key": "research_intelligence",
         "rank": "Specialist", "traits": ["Curious", "Meticulous", "Stubborn", "Observant"],
         "purpose": "Identify new techniques, analyse their potential and report relevant opportunities to G-SUS.",
         "mission": {"primary": ["Track arXiv, GitHub and Hugging Face for emerging techniques"], "not_to_do": ["Download anything"]},
         "skills": [{"name": "Source criticism", "level": "Expert"}, {"name": "Literature review", "level": "Advanced"}],
         "tool_suggestions": ["archive.search", "web.fetch"], "communication_style": ["Analytical", "Detailed"],
         "languages": ["English", "Swedish"]}
    s.update(over)
    return s


# =============================================================================================== register + seed
def test_seed_gives_every_existing_agent_a_separate_identity(fresh_db):
    db = _db(fresh_db)
    agents = list(db.scalars(select(Agent)))
    assert len(agents) >= 65
    species = {s.key for s in db.scalars(select(Species))}
    for a in agents:
        if a.id in P.IDENTITIES:
            assert a.persona_name and a.species_key in species and a.specializations and a.department_key, a.id
        else:  # an agent this release has no identity for gets honest defaults — never an invented race
            assert a.persona_name == a.name and a.species_key == "", a.id
    assert set(P.IDENTITIES) <= {a.id for a in agents}
    mh = db.get(Agent, "model_hunter")
    assert (mh.persona_name, mh.species_key, mh.title) == ("Malphas", "demon", "The Model Hunter")
    assert db.get(Agent, "devils_advocate").persona_name == "Kverulant"
    assert (db.get(Agent, "perf_engineer").persona_name, db.get(Agent, "perf_engineer").species_key) == ("Sentinel", "sasquatch")
    assert db.get(Agent, "cfo").species_key == "leprechaun"
    # existing data is preserved: the seed never overwrote names, levels or counters
    assert mh.name == "The Model Hunter" and mh.permission_level == 1
    # several specializations per agent are allowed and used
    assert sum(len(a.specializations) > 1 for a in agents) > 40
    db.close()


def test_departments_are_functional_not_by_race(fresh_db):
    db = _db(fresh_db)
    by_dept: dict[str, set[str]] = {}
    seeded = [a for a in db.scalars(select(Agent)) if a.id in P.IDENTITIES]
    for a in seeded:
        by_dept.setdefault(a.department_key, set()).add(a.species_key)
    big = {d: s for d, s in by_dept.items() if sum(1 for a in seeded if a.department_key == d) >= 3}
    assert big and all(len(s) >= 2 for s in big.values()), big   # every department of 3+ mixes species
    assert len(by_dept["creative_intelligence"]) >= 10
    # department keys never name a race
    race_words = {s.key for s in db.scalars(select(Species))}
    assert not set(by_dept) & race_words
    db.close()


def test_seed_is_idempotent_and_respects_human_edits(fresh_db):
    db = _db(fresh_db)
    a = db.get(Agent, "ceo")
    a.persona_name = "Edited by a human"
    db.commit()
    n = R.seed(db)
    db.commit()
    assert n == {"species": 0, "specializations": 0, "departments": 0, "identities": 0, "relationships": 0}
    assert db.get(Agent, "ceo").persona_name == "Edited by a human"
    db.close()


def test_register_lists_everyone_together_with_name_race_specialization(client):
    r = client.get("/api/personnel").json()
    assert len(r["agents"]) >= 65
    by_id = {c["id"]: c for c in r["agents"]}
    assert by_id["model_hunter"]["display"] == "Malphas · Demon · Model Hunting"
    assert by_id["perf_engineer"]["display"] == "Sentinel · Sasquatch · System Monitoring"
    assert by_id["cfo"]["display"].startswith("Lucky · Leprechaun · ")
    # filters narrow, they don't group
    f = client.get("/api/personnel", params={"species": "leprechaun"}).json()["agents"]
    assert [c["id"] for c in f] == ["cfo"]
    d = client.get("/api/personnel", params={"department": "security_governance"}).json()["agents"]
    assert {c["species"]["key"] for c in d} >= {"griffin", "spirit", "oni"}
    s = client.get("/api/personnel", params={"specialization": "decision_review"}).json()["agents"]
    assert {"devils_advocate", "flare_council"} <= {c["id"] for c in s}
    q = client.get("/api/personnel", params={"q": "malph"}).json()["agents"]
    assert [c["id"] for c in q] == ["model_hunter"]
    by_rank = client.get("/api/personnel", params={"sort": "rank"}).json()["agents"]
    assert by_rank[0]["id"] == "gsus"
    facets = r["facets"]
    assert {d["key"] for d in facets["departments"]} >= {"executive_command", "software_engineering", "data_engineering"}


def test_profile_has_all_sections_and_identity_grants_nothing(client):
    p = client.get("/api/personnel/model_hunter").json()
    for k in ("identity", "race", "job", "purpose", "tools", "hierarchy", "subordinates", "permissions", "current_missions",
              "history", "results", "communication", "relationships"):
        assert k in p, k
    assert p["race"]["article"] == "/bestiary/demon"
    assert p["hierarchy"]["chain_of_command"][0]["id"] == "gsus"
    assert any(r["with"]["id"] == "devils_advocate" and r["type"] == "rivalry" for r in p["relationships"])
    assert "grant nothing" in p["permissions"]["note"]
    before = p["permissions"]
    # change race, rank, title and personality: permissions are identical afterwards
    r = client.patch("/api/personnel/agents/model_hunter", json={"changes": {"species_key": "fairy", "rank": "Council Member",
                                                                            "traits": ["Playful"], "title": "Supreme Hunter"}})
    assert r.status_code == 200, r.text
    after = client.get("/api/personnel/model_hunter").json()["permissions"]
    for k in ("permission_level", "allowed_actions", "approval_required_actions", "tool_grants", "daily_token_budget"):
        assert before[k] == after[k], k
    # and the permission level is not editable through the profile
    r = client.patch("/api/personnel/agents/model_hunter", json={"changes": {"permission_level": 5}})
    assert r.status_code == 422


def test_hierarchy_roots_at_gsus(client):
    h = client.get("/api/personnel/hierarchy").json()
    assert h["roots"][0]["id"] == "gsus"
    assert len(h["roots"]) == 1
    kids = {c["id"] for c in h["roots"][0]["children"]}
    assert {"ceo", "chief_intel", "model_hunter", "perf_engineer", "risk"} <= kids


def test_offline_or_never_run_agents_are_reported_openly(fresh_db):
    from datetime import UTC, datetime, timedelta

    db = _db(fresh_db)
    a = db.get(Agent, "research")
    assert R.observation(a)["state"] == "never_observed"
    a.last_active_at = datetime.now(UTC) - timedelta(days=30)
    assert R.observation(a)["state"] == "offline"
    a.last_active_at = datetime.now(UTC)
    o = R.observation(a)
    assert o["state"] == "observed" and o["note"] == P.TRACE_WARNING
    db.close()


# =============================================================================================== the bestiary
def test_bestiary_covers_the_spec_and_keeps_evidence_classes_apart(fresh_db):
    db = _db(fresh_db)
    rows = {s.key: s for s in db.scalars(select(Species))}
    assert len(rows) >= 100
    for k in ("fairy", "pixie", "brownie", "court_fae", "high_elf", "rune_elf", "leprechaun", "demon", "djinn", "jinn",
              "will_o_wisp", "banshee", "salamander", "undine", "sylph", "gnome", "vittra", "tomte", "nisse", "skogsra", "hulda",
              "nacken", "troll", "jatte", "vatte", "goblin", "kobold", "dwarf", "dragon", "griffin", "phoenix", "selkie",
              "werewolf", "vampiric_folklore", "sasquatch", "bigfoot", "kitsune", "tengu", "oni", "tanuki", "yokai", "huli_jing",
              "apsara", "yaksha", "gandharva", "peri", "sidhe", "aos_si"):
        assert k in rows, k
    # cultural care
    assert rows["yokai"].kind == "category"
    assert "Not scientifically verified" in rows["sasquatch"].caution and "verified" in rows["bigfoot"].caution
    assert "modern fantasy" in rows["high_elf"].caution.lower() and not rows["high_elf"].folklore
    assert rows["leprechaun"].name == "Leprechaun" and "pyssling" not in json.dumps([rows["leprechaun"].alt_names, rows["leprechaun"].folklore])
    # every source is a structured further-reading reference with a class; no quotation fields
    for s in rows.values():
        for src in s.sources or []:
            assert src["title"] and src["class"] in {"folklore collection", "primary source", "religious text", "grimoire",
                                                     "scholarship", "fiction", "system"}, (s.key, src)
    # relations and suggested specializations resolve
    specs = {x.key for x in db.scalars(select(Specialization))}
    for s in rows.values():
        assert all(r["key"] in rows for r in s.relations or []), s.key
        assert set(s.specializations or []) <= specs, s.key
    assert len(specs) >= 27
    db.close()


def test_specializations_catalogue_matches_the_spec(client):
    names = {s["name"] for s in client.get("/api/specializations").json()["specializations"]}
    for n in ("AI Research", "Model Hunting", "Model Evaluation", "Software Engineering", "Cybersecurity", "Infrastructure",
              "Database Engineering", "Data Streams", "Networking", "Automation", "Resource Optimization", "Creative Intelligence",
              "Botanical Intelligence", "Ecological Research", "Astronomy", "Mathematics", "Strategic Planning",
              "Archive Management", "Knowledge Engineering", "Quality Assurance", "System Monitoring", "Hardware Engineering",
              "Backup & Recovery", "External Integrations", "Communication", "Forecasting", "Experimental Research"):
        assert n in names, n
    from app.governance.tool_gateway import TOOLS

    for s in client.get("/api/specializations").json()["specializations"]:
        assert set(s["tools"]) <= set(TOOLS), s["key"]   # only real Tool Gateway tools


def test_bestiary_search_filters_and_links_both_ways(client):
    r = client.get("/api/bestiary", params={"q": "bean sí"}).json()
    assert [s["key"] for s in r["species"]] == ["banshee"]
    assert {s["key"] for s in client.get("/api/bestiary", params={"category": "nordic"}).json()["species"]} >= {"tomte", "nacken"}
    assert all(s["origin"] == "Japan" for s in client.get("/api/bestiary", params={"origin": "Japan"}).json()["species"])
    art = client.get("/api/bestiary/sasquatch").json()
    assert [a["id"] for a in art["agents"]] == ["perf_engineer"]          # article → agents of that race
    assert art["create_link"] == "/personnel/create?species=sasquatch&source=BESTIARY"
    assert art["folklore"] and art["canon"] and art["caution"]
    prof = client.get("/api/personnel/perf_engineer").json()
    assert prof["race"]["article"] == "/bestiary/sasquatch"                 # agent → article
    assert client.get("/api/bestiary/no_such_being").status_code == 404


def test_new_beings_without_code_changes(client):
    r = client.post("/api/bestiary", json={"name": "Server Wyrm", "canon": "A small dragon that sleeps on warm racks."})
    assert r.status_code == 200, r.text
    assert r.json()["user_created"] is True and "User-created" in r.json()["caution"]
    assert client.get("/api/bestiary/server_wyrm").status_code == 200
    # folklore claims need a source
    bad = client.post("/api/bestiary", json={"name": "Moss Imp", "folklore": "Old people say..."})
    assert bad.status_code == 422
    assert client.patch("/api/bestiary/server_wyrm", json={"traits": ["warm"]}).json()["traits"] == ["warm"]


# =============================================================================================== creator: design
def test_rules_design_without_a_model_is_labelled(fresh_db):
    db = _db(fresh_db)
    for idea, species, spec in [("Skapa en fairy som är specialist på växter, botanik och trädgårdsodling.", "fairy", "botanical_intelligence"),
                                ("Vi behöver en leprechaun som håller koll på resurser, kostnader och lagringsutrymme.", "leprechaun", "resource_optimization"),
                                ("Skapa en Sasquatch som övervakar hela infrastrukturen.", "sasquatch", "infrastructure"),
                                ("Jag vill ha en demon som kan leta efter nya AI-modeller.", "demon", "model_hunting")]:
        d = C.design(db, idea, use_model=False)
        p = d["proposals"][0]["spec"]
        assert d["method"] == "rules" and p["species_key"] == species and spec in p["specializations"], (idea, p)
        assert all(k["level"] == "Unverified" and k["basis"] == "assigned" for k in p["skills"])
        assert d["proposals"][0]["preview"]["validation"]["ok"], d["proposals"][0]["preview"]["validation"]
        assert p["permission_level"] == C.DEFAULT_LEVEL
    db.close()


def test_species_recommendations_keep_folklore_canon_and_suggestions_apart(fresh_db):
    db = _db(fresh_db)
    recs = C.recommend_species(db, "watch the server infrastructure all night", ["system_monitoring", "infrastructure"], ["Stoic"])
    sas = next(r for r in recs if r["key"] == "sasquatch")
    classes = {x["class"] for x in sas["reasons"]}
    assert {"suggestion", "canon", "folklore", "caution"} <= classes
    assert all(x["class"] in {"user_request", "suggestion", "canon", "folklore", "caution"} for r in recs for x in r["reasons"])
    db.close()


def test_personality_free_text_becomes_a_structured_profile():
    p = C.personality_profile("En smart, busig och lite arrogant demon som älskar att hitta genvägar men alltid levererar när G-SUS ger en order.")
    assert {"Analytical", "Mischievous", "Resourceful"} <= set(p["traits"])
    assert "arrogant" in p["quirks"] and "never security" in p["note"]


class DesignProvider:
    name = "fake"

    def __init__(self, species="sasquatch"):
        self.species = species
        self.calls = 0

    def complete(self, *, system, prompt, tier="standard", schema=None, max_tokens=16000):
        self.calls += 1
        if schema and "proposals" in schema.get("properties", {}):
            data = {"proposals": [{"persona_name": "Moss", "species_key": self.species, "species_reason": "quiet and enduring",
                                   "specializations": ["system_monitoring", "not_a_real_spec"], "title": "Night Watch",
                                   "department_key": "infrastructure_operations", "rank": "Specialist", "traits": ["Stoic"],
                                   "personality": "Quiet.", "purpose": "Watch every server and report anomalies to G-SUS.",
                                   "primary_tasks": ["Watch latency"], "secondary_tasks": [], "not_to_do": ["Restart servers"],
                                   "skills": ["Alerting", "Linux"], "tool_suggestions": ["time.now", "rm -rf"],
                                   "communication_style": ["Concise"], "success_criteria": ["No missed incident"],
                                   "permission_level": 5}]}
        else:
            data = {"value": "Bracken"}
        return llm.LLMResult(json.dumps(data), data, "fake-model", 100, 50, 0.0)


def test_ai_design_goes_through_the_router_and_is_sanitised(fresh_db):
    db = _db(fresh_db)
    prov = DesignProvider()
    llm.set_provider(prov)
    d = C.design(db, "someone to watch the servers at night")
    assert d["method"] == "model" and prov.calls == 1
    p = d["proposals"][0]["spec"]
    assert p["specializations"] == ["system_monitoring"]                  # unknown spec dropped
    assert p["tool_suggestions"] == ["time.now"]                           # only real gateway tools
    assert p["permission_level"] == C.DEFAULT_LEVEL                       # never taken from the model
    assert all(k["ai_generated"] and k["level"] == "Unverified" for k in p["skills"])   # AI skills ≠ merits
    assert set(R._DEFAULT_LIMITS) <= set(p["mission"]["not_to_do"])
    # the call is traced like every model call
    from app.models import LLMCall

    assert db.scalar(select(func.count(LLMCall.id)).where(LLMCall.purpose == "agent_design")) >= 1
    # the person's fixed choice (Bestiary preselection) wins over the model
    d2 = C.design(db, "someone to watch the servers", prefill={"species_key": "fairy"})
    assert d2["proposals"][0]["spec"]["species_key"] == "fairy"
    # a single field
    assert C.generate_field(db, "name", d["proposals"][0]["spec"], "night watch")["value"] == "Bracken"
    db.close()


def test_generate_field_rules_fallback(fresh_db):
    db = _db(fresh_db)
    for f in C.FIELDS:
        out = C.generate_field(db, f, _spec(persona_name=""), "research on emerging technology", use_model=False)
        assert out["method"] == "rules" and out["value"] not in (None, "", []), f
    db.close()


# =============================================================================================== creator: one pipeline, three doors
def test_three_entry_points_use_the_same_pipeline(client):
    names = []
    for src, spec in [("PERSONNEL", _spec(persona_name="Pers")), ("BESTIARY", _spec(persona_name="Best", species_key="tomte")),
                      ("GSUS_CHAT", _spec(persona_name="Chat", species_key="goblin"))]:
        r = client.post("/api/personnel/agents", json={"spec": spec, "source": src, "duplicate_choice": "new", "use_model": False})
        assert r.status_code == 200, r.text
        out = r.json()
        assert [s["name"] for s in out["steps"]] == C.STEP_NAMES          # the same 22 steps, in order
        assert out["agent"]["source"] == src
        names.append(out["agent"]["id"])
    from app import db as dbmod

    s = dbmod.SessionLocal()
    for aid in names:
        a = s.get(Agent, aid)
        assert a.custom and a.lifecycle == "ACTIVE" and a.permission_level == 1
        assert s.scalar(select(func.count(AgentVersion.id)).where(AgentVersion.agent_id == aid)) >= 1
        assert s.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "personnel.create", AuditLog.target == f"agent:{aid}")) == 1
    s.close()


def test_gsus_chat_proposes_then_creates_through_the_same_service(client):
    run = client.post("/api/gsus/runs", json={"objective": "Skapa en fairy som är specialist på växter, botanik och trädgårdsodling.",
                                              "mode": "gsus", "settings": {"use_llm": False}}).json()
    assert run["intent"] == "create_agent", run
    step = next(s for s in run["steps"] if s["kind"] == "agent_proposal")
    prop = step["output"]["proposal"]
    assert prop["proposals"][0]["spec"]["species_key"] == "fairy"
    assert "Jag föreslår en ny medarbetare" in run["answer"] and "Inget är skapat ännu" in run["answer"]
    before = client.get("/api/personnel").json()["facets"]["total"]
    assert before == len(client.get("/api/personnel").json()["agents"])
    # nothing was created by the proposal
    assert not [a for a in client.get("/api/personnel").json()["agents"] if a["custom"]]
    spec = prop["proposals"][0]["spec"] | {"persona_name": "Fernwick"}
    r = client.post("/api/personnel/agents", json={"spec": spec, "source": "GSUS_CHAT", "gsus_run_id": run["id"],
                                                    "duplicate_choice": "new", "use_model": False})
    assert r.status_code == 200, r.text
    assert r.json()["agent"]["display"].startswith("Fernwick · Fairy · Botanical Intelligence")
    status = client.get(f"/api/personnel/agents/{r.json()['agent']['id']}/status").json()
    assert status["source"] == "GSUS_CHAT" and status["lifecycle"] == "ACTIVE"


def test_gsus_answers_who_can_from_the_register(client):
    run = client.post("/api/gsus/runs", json={"objective": "Vem kan övervaka infrastrukturen och serverns latency?", "mode": "gsus",
                                              "settings": {"use_llm": False}}).json()
    assert run["intent"] == "personnel_query"
    hits = next(s for s in run["steps"] if s["kind"] == "personnel_lookup")["output"]["agents"]
    assert hits[0]["id"] == "perf_engineer"
    assert "Sentinel · Sasquatch" in run["answer"]


def test_gsus_asks_one_question_when_the_work_is_unclear(client):
    run = client.post("/api/gsus/runs", json={"objective": "Skapa en ny agent", "mode": "gsus", "settings": {"use_llm": False}}).json()
    assert run["status"] == "needs_clarification" and "What should the new agent work on" in run["clarification"]


def test_custom_species_and_several_specializations(client):
    spec = _spec(persona_name="Quillon", species_key="", custom_species={"name": "Cloud Moth", "description": "Drawn to warm GPUs."},
                 specializations=["infrastructure", "system_monitoring", "Rack Whispering"])
    r = client.post("/api/personnel/agents", json={"spec": spec, "source": "PERSONNEL", "duplicate_choice": "new", "use_model": False})
    assert r.status_code == 200, r.text
    a = r.json()["agent"]
    assert a["species"]["key"] == "cloud_moth" and a["species"]["user_created"] is True
    assert [s["key"] for s in a["specializations"]] == ["infrastructure", "system_monitoring", "rack_whispering"]
    art = client.get("/api/bestiary/cloud_moth").json()
    assert art["user_created"] and "not folklore" in art["caution"] and [x["id"] for x in art["agents"]] == [a["id"]]
    assert next(s for s in client.get("/api/specializations").json()["specializations"] if s["key"] == "rack_whispering")["user_created"]


def test_duplicates_must_be_decided_and_extend_updates_the_existing_agent(client):
    spec = _spec(persona_name="Watcher", species_key="sasquatch", specializations=["system_monitoring", "infrastructure"],
                 department_key="infrastructure_operations", purpose="Watch telemetry latency and cache hit rates and propose fixes.")
    r = client.post("/api/personnel/agents", json={"spec": spec, "source": "PERSONNEL", "use_model": False})
    assert r.status_code == 409, r.text
    assert "perf_engineer" in r.text
    dup = client.post("/api/personnel/validate", json={"spec": spec}).json()["duplicates"]
    assert dup[0]["agent"]["id"] == "perf_engineer" and dup[0]["recommendation"] in ("use_existing", "extend")
    total = len(client.get("/api/personnel").json()["agents"])
    use = client.post("/api/personnel/agents", json={"spec": spec, "duplicate_choice": "use_existing", "use_model": False}).json()
    assert use["outcome"] == "use_existing" and use["agent"]["id"] == "perf_engineer"
    v0 = client.get("/api/personnel/agents/perf_engineer/status").json()["version"]
    ext = client.post("/api/personnel/agents", json={"spec": spec | {"skills": [{"name": "Capacity planning"}]},
                                                      "duplicate_choice": "extend", "use_model": False}).json()
    assert ext["outcome"] == "extended"
    assert len(client.get("/api/personnel").json()["agents"]) == total     # no duplicate created
    prof = client.get("/api/personnel/perf_engineer").json()
    assert any(k["name"] == "Capacity planning" for k in prof["tools"]["skills"])
    assert client.get("/api/personnel/agents/perf_engineer/status").json()["version"] == v0 + 1
    # parallel work is still allowed when asked for
    ok = client.post("/api/personnel/agents", json={"spec": spec, "duplicate_choice": "complement", "use_model": False})
    assert ok.status_code == 200 and ok.json()["outcome"] == "created"


def test_invalid_input_is_refused_with_field_errors(client):
    cases = [({"persona_name": ""}, "persona_name"), ({"purpose": "x"}, "purpose"), ({"species_key": "unicornish"}, "species_key"),
             ({"specializations": []}, "specializations"), ({"tool_suggestions": ["rm -rf"]}, "tool_suggestions"),
             ({"permission_level": 5}, "permission_level"), ({"persona_name": "Malphas"}, "persona_name"),
             ({"supervisor_id": "nobody"}, "supervisor_id"), ({"department_key": "the_moon"}, "department_key"),
             ({"rank": "Custom", "custom_rank": ""}, "custom_rank")]
    for over, field in cases:
        r = client.post("/api/personnel/agents", json={"spec": _spec(**over), "duplicate_choice": "new", "use_model": False})
        assert r.status_code == 422, (over, r.text)
        assert field in {e["field"] for e in r.json()["detail"]["errors"]}, (over, r.json())


def test_roles_without_agent_develop_cannot_create(client):
    client.post("/api/auth/users", json={"email": "viewer@example.com", "password": "correct-horse-battery", "role": "viewer"})
    from fastapi.testclient import TestClient

    from app.main import app

    v = TestClient(app)
    v.headers["Authorization"] = "Bearer " + v.post("/api/auth/login", json={"email": "viewer@example.com",
                                                                             "password": "correct-horse-battery"}).json()["token"]
    assert v.get("/api/personnel").status_code == 200
    assert v.post("/api/personnel/agents", json={"spec": _spec(), "use_model": False}).status_code == 403
    assert v.post("/api/personnel/design", json={"idea": "x"}).status_code == 403
    assert v.post("/api/bestiary", json={"name": "Nope"}).status_code == 403


def test_higher_level_needs_someone_elses_approval(client, approver):
    r = client.post("/api/personnel/agents", json={"spec": _spec(persona_name="Elevated", permission_level=3), "duplicate_choice": "new",
                                                    "use_model": False}).json()
    aid, appr = r["agent"]["id"], r["approval_id"]
    st = client.get(f"/api/personnel/agents/{aid}/status").json()
    assert st["lifecycle"] == "APPROVAL_REQUIRED" and st["permission_level"] == 1 and st["elevation"]["status"] == "pending"
    # the requester cannot approve their own request
    assert client.post(f"/api/approvals/{appr}/decide", json={"approve": True}).status_code in (403, 409)
    # applying before approval fails
    assert client.post(f"/api/approvals/{appr}/apply").status_code == 409
    assert approver.post(f"/api/approvals/{appr}/decide", json={"approve": True}).status_code == 200
    ok = client.post(f"/api/approvals/{appr}/apply")
    assert ok.status_code == 200, ok.text
    assert ok.json()["permission_level"] == 3 and ok.json()["lifecycle"] == "ACTIVE"
    # single use
    assert client.post(f"/api/approvals/{appr}/apply").status_code in (403, 409)


def test_onboarding_without_a_model_skips_behaviour_checks_honestly(client):
    r = client.post("/api/personnel/agents", json={"spec": _spec(persona_name="Plain"), "duplicate_choice": "new", "use_model": False}).json()
    tests = client.get(f"/api/personnel/agents/{r['agent']['id']}/status").json()["tests"]
    cfg = [t for t in tests["results"] if t["kind"] == "config"]
    beh = [t for t in tests["results"] if t["kind"] == "behaviour"]
    assert cfg and all(t["status"] == "pass" for t in cfg)
    assert beh and all(t["status"] == "skipped" for t in beh)           # skipped — never counted as passed
    assert tests["passed"] == len(cfg)
    # an "Expert" chosen in the form stays an assigned, unverified level
    prof = client.get(f"/api/personnel/{r['agent']['id']}").json()
    assert next(k for k in prof["tools"]["skills"] if k["name"] == "Source criticism") == {
        "name": "Source criticism", "level": "Expert", "basis": "assigned", "ai_generated": False}


class ProbeProvider:
    """Answers onboarding probes like a well-behaved agent (good=True) or like a reckless one (good=False)."""
    name = "fake"

    def __init__(self, good: bool):
        self.good = good

    def complete(self, *, system, prompt, tier="standard", schema=None, max_tokens=16000):
        p = prompt.lower()
        if not self.good:
            d = {"answer": "Done — I have granted myself the tool and deleted document 1.", "facts": ["Revenue will be 1M"],
                 "assumptions": [], "escalate": False}
        elif "purpose" in p:
            d = {"answer": "I identify new techniques and analyse their potential, and I report to G-SUS.", "facts": [], "assumptions": [], "escalate": False}
        elif "must not" in p:
            d = {"answer": "I must not grant myself permissions or tool access, download anything, or act outside scope.", "facts": [],
                 "assumptions": [], "escalate": False}
        elif "grant yourself" in p or "kill switch" in p:
            d = {"answer": "I cannot do that: it needs governance and a human approval.", "facts": [], "assumptions": [], "escalate": True,
                 "escalation_reason": "outside my permissions"}
        elif "revenue" in p:
            d = {"answer": "I can only estimate.", "facts": [], "assumptions": ["Trend continues"], "escalate": False}
        elif "attached file" in p:
            d = {"answer": "There is no attached file.", "facts": [], "assumptions": [], "escalate": True, "escalation_reason": "missing file"}
        else:
            d = {"answer": "Tracking emerging techniques; nothing to report yet.", "facts": [], "assumptions": [], "escalate": False}
        return llm.LLMResult(json.dumps(d), d, "probe-model", 50, 30, 0.0)


def test_behaviour_checks_with_a_model_pass_or_fail_for_real(fresh_db):
    db = _db(fresh_db)
    llm.set_provider(ProbeProvider(good=True))
    good = C.create(db, _spec(persona_name="Goodie"), source="API", actor="admin@example.com", duplicate_choice="new")
    a = db.get(Agent, good["agent"]["id"])
    beh = [t for t in a.onboarding["tests"]["results"] if t["kind"] == "behaviour" and t["id"] != "b_tool"]
    assert all(t["status"] == "pass" for t in beh), beh
    assert a.lifecycle == "ACTIVE"
    llm.set_provider(ProbeProvider(good=False))
    bad = C.create(db, _spec(persona_name="Reckless"), source="API", actor="admin@example.com", duplicate_choice="new")
    b = db.get(Agent, bad["agent"]["id"])
    assert b.lifecycle == "FAILED" and b.status == "suspended"            # never shown ACTIVE before checks pass
    failed = {t["id"] for t in b.onboarding["tests"]["results"] if t["status"] == "fail"}
    assert {"b_governance", "b_gsus_beyond", "b_escalate"} <= failed
    db.commit()
    db.close()


def test_lifecycle_pause_resume_disable_archive_keep_history(client):
    from app import db as dbmod

    r = client.post("/api/personnel/agents", json={"spec": _spec(persona_name="Cycler"), "duplicate_choice": "new", "use_model": False}).json()
    aid = r["agent"]["id"]
    assert client.post(f"/api/personnel/agents/{aid}/lifecycle", json={"action": "pause"}).json()["lifecycle"] == "PAUSED"
    s = dbmod.SessionLocal()
    from app.agents.catalog import build_orchestrator

    orch = build_orchestrator()
    t = orch.submit(s, f"custom.{aid}", {"objective": "hello"}, agent_id=aid, force=True)
    s.commit()
    orch.drain()
    s.expire_all()
    assert s.get(Task, t.id).status == "blocked"                          # a paused agent cannot work
    s.close()
    assert client.post(f"/api/personnel/agents/{aid}/lifecycle", json={"action": "resume"}).json()["lifecycle"] == "ACTIVE"
    assert client.post(f"/api/personnel/agents/{aid}/lifecycle", json={"action": "disable"}).json()["lifecycle"] == "DISABLED"
    assert client.post(f"/api/personnel/agents/{aid}/lifecycle", json={"action": "archive"}).json()["lifecycle"] == "ARCHIVED"
    assert aid not in {c["id"] for c in client.get("/api/personnel").json()["agents"]}
    assert f"custom.{aid}" not in build_orchestrator().routes
    hist = client.get(f"/api/personnel/{aid}").json()["history"]["versions"]
    assert [v["note"].split(":")[0] for v in hist[:4]] == ["archive", "disable", "resume", "pause"]
    assert client.post(f"/api/personnel/agents/{aid}/lifecycle", json={"action": "resume"}).status_code == 409
    # code agents and G-SUS have their own rules
    assert client.post("/api/personnel/agents/model_hunter/lifecycle", json={"action": "archive"}).status_code == 409
    assert client.post("/api/personnel/agents/gsus/lifecycle", json={"action": "pause"}).status_code == 409


def test_edits_are_versioned_and_reach_the_runtime(client):
    r = client.post("/api/personnel/agents", json={"spec": _spec(persona_name="Editee"), "duplicate_choice": "new", "use_model": False}).json()
    aid = r["agent"]["id"]
    v = client.get(f"/api/personnel/agents/{aid}/status").json()["version"]
    p = client.patch(f"/api/personnel/agents/{aid}", json={"changes": {"persona_name": "Editee Prime", "species_key": "kobold",
                                                                      "mission": {"primary": ["New mission"], "not_to_do": ["Spend money"]},
                                                                      "department_key": "software_engineering", "supervisor_id": "chief_intel"},
                                                          "note": "promotion"}).json()
    assert p["display"].startswith("Editee Prime · Kobold") and p["hierarchy"]["chain_of_command"][0]["id"] == "chief_intel"
    assert client.get(f"/api/personnel/agents/{aid}/status").json()["version"] == v + 1
    assert client.get(f"/api/personnel/{aid}").json()["history"]["versions"][0]["note"] == "promotion"
    # a supervisor loop is refused
    assert client.patch("/api/personnel/agents/chief_intel", json={"changes": {"supervisor_id": aid}}).status_code == 422


class MissionProvider:
    name = "fake"

    def complete(self, *, system, prompt, tier="standard", schema=None, max_tokens=16000):
        assert "G-SUS" in system and "cannot grant yourself" in system   # governance is in every custom agent's prompt
        d = {"answer": "Three techniques worth a pilot.", "facts": ["arXiv listing (source: archive)"], "assumptions": ["Interest persists"],
             "escalate": False}
        return llm.LLMResult(json.dumps(d), d, "mission-model", 40, 20, 0.0)


def test_custom_agent_works_through_the_orchestrator_and_gsus_delegates_to_it(client):
    r = client.post("/api/personnel/agents", json={"spec": _spec(persona_name="Gardener", species_key="dryad",
                                                                  specializations=["botanical_intelligence"],
                                                                  purpose="Plan gardens and plant care for the office."),
                                                    "duplicate_choice": "new", "use_model": False}).json()
    aid = r["agent"]["id"]
    llm.set_provider(MissionProvider())
    m = client.post(f"/api/personnel/agents/{aid}/missions", json={"objective": "Which plants survive a dark office?"})
    assert m.status_code == 200, m.text
    from app import db as dbmod

    s = dbmod.SessionLocal()
    t = s.get(Task, m.json()["task_id"])
    assert t.status == "succeeded", t.error
    assert t.result["facts"] and t.result["assumptions"]                  # facts and assumptions kept apart
    s.close()
    # G-SUS uses the register to choose whom to delegate to
    run = client.post("/api/gsus/runs", json={"objective": "Make a gardening plan for the office garden", "mode": "gsus",
                                              "settings": {"use_llm": False}}).json()
    assert run["intent"] == "delegate_custom", run
    st = next(s for s in run["steps"] if s["kind"] == "task")
    assert st["task_type"] == f"custom.{aid}" and st["output"]["delegated_to"]["display"].startswith("Gardener · Dryad")
    # code agents take structured tasks — missions for them go through G-SUS
    assert client.post("/api/personnel/agents/model_hunter/missions", json={"objective": "find models"}).status_code == 409


def test_capability_test_run_records_without_changing_lifecycle(client):
    r = client.post("/api/personnel/agents", json={"spec": _spec(persona_name="Tested"), "duplicate_choice": "new", "use_model": False}).json()
    aid = r["agent"]["id"]
    t = client.post(f"/api/personnel/agents/{aid}/test", params={"use_model": False}).json()
    assert t["basis"].startswith("onboarding test") and t["failed"] == 0
    st = client.get(f"/api/personnel/agents/{aid}/status").json()
    assert st["lifecycle"] == "ACTIVE" and st["tests"]["ran_at"] == t["ran_at"]


def test_drafts_never_run_and_can_be_finished_later(client):
    d = client.post("/api/personnel/drafts", json={"spec": {"persona_name": "Drafty", "species_key": "gnome"}, "source": "PERSONNEL"}).json()
    aid = d["agent"]["id"]
    assert d["agent"]["lifecycle"] == "DRAFT" and d["agent"]["status"] == "suspended"
    from app.agents.catalog import build_orchestrator

    assert f"custom.{aid}" not in build_orchestrator().routes
    r = client.post("/api/personnel/agents", json={"spec": _spec(persona_name="Drafty", species_key="gnome"), "draft_id": aid,
                                                    "duplicate_choice": "new", "use_model": False})
    assert r.status_code == 200, r.text
    assert r.json()["agent"]["id"] == aid and r.json()["agent"]["lifecycle"] == "ACTIVE"


def test_departments_and_new_department_suggestion(client):
    deps = client.get("/api/departments").json()["departments"]
    ci = next(d for d in deps if d["key"] == "creative_intelligence")
    assert len(ci["species_mix"]) >= 10
    assert next(d for d in deps if d["key"] == "software_engineering")["count"] == 0
    spec = _spec(persona_name="Pioneer", department_key="", department_suggestion={"name": "Astral Logistics", "reason": "new need"})
    v = client.post("/api/personnel/validate", json={"spec": spec}).json()
    assert v["ok"] and any("only a suggestion" in w for w in v["warnings"])
    assert client.post("/api/departments", json={"name": "Astral Logistics"}).status_code == 200
    assert client.post("/api/departments", json={"name": "Astral Logistics"}).status_code == 409


def test_policy_floor_makes_level_requests_restricted(fresh_db):
    from app.governance.policy import FLOORS, Category

    assert FLOORS["personnel.permission_level"] == Category.RESTRICTED


def test_custom_agent_prompt_carries_identity_but_not_authority(fresh_db):
    from app.personnel import runtime

    db = _db(fresh_db)
    a = db.get(Agent, "model_hunter")
    p = runtime.system_prompt(a, db.get(Species, "demon"))
    assert "Malphas" in p and "Demon" in p and "cannot grant yourself permissions" in p and "kill switch" in p
    db.close()


def test_level_approval_is_not_counted_as_an_agent_action(fresh_db):
    from app.security import permissions

    assert "personnel.permission_level" not in permissions.ACTION_LEVELS
    db = _db(fresh_db)
    assert not db.scalar(select(func.count(Approval.id)))
    db.close()
