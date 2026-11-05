"""Rocky Flare engines: genres, fusion, originality, mutation, sideways, field, campaigns, learning, personas."""
from datetime import datetime, timedelta, UTC
from types import SimpleNamespace as NS

from app.engines import compliance
from app.flare import campaigns as C
from app.flare import commercial as CM
from app.flare import creative, field, learning, personalization, sideways
from app.flare import genres as G
from app.flare import mutation as M
from app.flare import originality as O
from app.flare import personas as PS
from app.flare.taxonomy import GENRES, profile_product


def scooter_profile():
    return profile_product("Waterproof roll-top handlebar bag for e-scooter", "mobility", ["commuter", "winter"], retail=449,
                           competitor_prices=[299, 399, 449, 499])


def test_taxonomy_complete_and_pillar_d_present():
    required = {"scandi_minimal", "industrial", "streetwear", "underground", "luxury", "cyberpunk", "retro_futurism", "vintage_americana",
                "western", "japanese", "brutalism", "organic_botanical", "psychedelic", "gothic", "dark_academia", "techno_occult",
                "sport_performance", "outdoor_adventure", "tactical_utility", "pop_playful", "minimal_premium", "experimental_art",
                "future_tech", "nostalgic_retro", "diy_maker", "artisan"}
    assert required <= set(GENRES)
    assert {g.id for g in GENRES.values() if g.pillar == "D"} >= {"biblical_heritage", "mesopotamian", "illuminated_manuscript", "alchemy_hermetic",
                                                                   "celestial_cartography", "secret_archive", "surveillance_dystopia"}


def test_genre_matching_is_product_driven():
    m = {x.genre_id: x.score for x in G.match_genres(scooter_profile())}
    assert m["urban_commuter"] > m["luxury"] and m["urban_commuter"] > m["pop_playful"]
    pet = profile_product("Dog collar", "pet", ["pet"])
    pm = {x.genre_id: x for x in G.match_genres(pet)}
    assert any("family or pet" in r for r in pm["techno_occult"].reasoning)  # occult codes penalised for pets


def test_learned_adjustment_changes_ranking():
    base = G.match_genres(scooter_profile())
    target = base[5].genre_id
    boosted = G.match_genres(scooter_profile(), learned={target: 10})
    assert [x.genre_id for x in boosted].index(target) < 5


def test_directions_at_least_five_distinct_with_all_fields():
    dirs = G.creative_directions(scooter_profile(), n=5)
    assert len(dirs) >= 5
    assert len({d.hybrid_id.split("+")[0] for d in dirs}) == len(dirs)  # distinct primary genres
    bs = dirs[0].brand_system.model_dump()
    assert all(bs[k] for k in ("primary_genre", "secondary_genre", "visual_direction", "color_palette", "typography", "materials_textures",
                               "photography_style", "packaging_style", "website_language", "social_identity", "advertising_direction"))
    assert dirs[0].why_it_fits and dirs[0].scores.overall > 0


def test_fusion_hybrid_fields_and_novelty_and_clash():
    h = G.fuse(GENRES["tactical_utility"], GENRES["illuminated_manuscript"], scooter_profile())
    for k in ("name", "concept", "philosophy", "target_audience", "palette", "typography", "materials", "surface_treatments",
              "graphic_language", "product_applications", "packaging_direction", "photography_direction", "marketing_identity"):
        assert getattr(h, k)
    assert h.novel is True
    assert G.fuse(GENRES["tactical_utility"], GENRES["illuminated_manuscript"], usage={h.id: 3}).novel is False
    clash = G.fuse(GENRES["pop_playful"], GENRES["gothic"])
    assert clash.compatibility < 0.3 and any("clash" in r for r in clash.reasoning)
    presets = G.preset_hybrids()
    assert {p.name for p in presets} >= {"Eden Survival", "Northern Sentinel", "Black Mirror EDC"}


def test_anti_generic_filter():
    bad = O.score_concept({"name": "EcoPro Smart Hub", "tagline": "Elevate your commute and unlock the ultimate experience",
                           "story": "Cutting-edge game-changer.", "audience": "everyone", "usp": "best quality", "palette": ["#ffffff", "#000000", "#1e90ff"]})
    codes = {f["code"] for f in bad.flags}
    assert {"generic_name", "ai_phrases", "no_target_customer", "empty_description", "unsubstantiated_claim", "predictable_palette"} <= codes
    assert bad.requires_revision
    good = O.score_concept({"name": "Cipher Fieldworks", "tagline": "Built for the dark half of the year.",
                            "story": "Cipher Fieldworks rebuilds the commuter bag around dossier aesthetics on top of tactical construction in "
                                     "1000D nylon and hypalon, for e-scooter commuters who ride through Nordic winter darkness every day.",
                            "audience": "e-scooter commuters in Nordic cities riding year-round", "usp": "Modular roll-top with reflective piping",
                            "palette": ["#e6dfcf", "#1c1c1c", "#9e1b1b", "#3b3f32"], "primary_genre": "tactical_utility", "secondary_genre": "secret_archive"},
                           ["mobility"], novel_hybrid=True)
    assert not good.requires_revision and good.score > bad.score


def test_trademark_agency_religious_and_fiction_checks():
    assert O.trademark_prescreen("Black Mirror EDC")["status"] == "known_conflict"
    assert O.trademark_prescreen("Cipher Fieldworks")["status"] == "unscreened"
    assert any(f["code"] == "real_organisation" for f in O.check_name("CIA Field Kit"))
    assert not O.check_name("Från Norr")  # Swedish 'från' is not an agency
    r = O.score_concept({"name": "G-SUS Mobility", "story": "x " * 20, "audience": "commuters in Stockholm", "usp": "modular mount"})
    codes = {f["code"] for f in r.flags}
    assert "trademark_conflict" in codes and "religious_reference" in codes
    t = O.check_text("The truth they don't want you to know about your commute", "tagline")
    assert any(f["code"] == "conspiracy_as_fact" for f in t)


def test_compliance_mobility_classes_and_prohibited_mods():
    assert compliance.assess("Roll-top bag for e-scooter").mobility_class == "ordinary_accessory"
    assert compliance.assess("Rear bike light rechargeable").mobility_class == "vehicle_safety_affecting"
    assert compliance.assess("E-scooter charger 42V").mobility_class == "electrical_system"
    assert compliance.assess("E-scooter 350W").status == "restricted"
    assert compliance.assess("E-scooter speed unlock dongle").status == "blocked"
    assert compliance.assess("Phone mount", marketing_copy="universal fit for all scooters").status == "blocked"
    assert compliance.assess("Bushcraft knife").status == "restricted"  # tool with rules, not prohibited
    assert compliance.assess("Ferro rod fire starter").categories == ["fire_and_fuel"]


def test_mutation_engine_statuses_graph_and_ranking():
    sup = NS(offers_custom_packaging=True, offers_private_label=False)
    nodes, edges = M.mutate("Waterproof pannier bag", "mobility", ["commuter"], sup, 449, {"mobility": 1, "storage": .75})
    types = {n.mutation_type for n in nodes}
    assert {"functional", "material", "visual", "personalization", "bundle", "audience", "digital", "premium", "budget", "professional",
            "lifestyle", "seasonal", "community", "service"} <= types
    assert "subscription" not in types  # not forced onto a one-time purchase
    statuses = {n.mutation_type: n.status for n in nodes}
    assert statuses["existing"] == "existing_product" and statuses["material"] == "supplier_customization"
    assert statuses["digital"] == "original_concept" and statuses["functional"] == "proposed_modification"
    assert any(e.relation == "price_ladder" for e in edges) and len(edges) >= len(nodes) - 1
    assert nodes[0].rank_score >= nodes[-1].rank_score
    filt, _ = M.mutate("Water filter bottle", "outdoor", [], None)
    assert "subscription" in {n.mutation_type for n in filt}


def test_innovation_lab_has_verification_steps():
    lab = M.innovation_lab("Headlamp", {"lighting": 1, "outdoor": .75})
    assert len(lab) >= 13 and all(i["verification"] for i in lab)
    wp = next(i for i in lab if i["key"] == "waterproof")
    assert "IEC 60529" in wp["verification"] and wp["status"] == "proposed_design"


def test_think_sideways_five_per_category_with_bridges():
    r = sideways.think_sideways("Rechargeable LED headlamp", "portable compact light with battery, weatherproof", {"lighting"})
    cats = {}
    for i in r["items"]:
        cats.setdefault(i["category"], []).append(i)
    assert set(cats) == set(sideways.CATEGORY_LABELS.values())
    assert all(len(v) == 5 for v in cats.values())
    assert all(i["bridge"] for i in r["items"]) and len(r["high_potential"]) == 3
    assert sideways.classify_question("Give this product three radically different identities") == "identities"
    assert sideways.classify_question("Find ways to monetize the audience rather than the product") == "audience"


def test_field_pillars_segments_ecosystems_sourcing():
    assert "C_e_mobility" in field.classify_pillars("e-bike pannier bag")
    assert "B_survival" in field.classify_pillars("emergency radio with solar charging")
    segs = field.match_segments("e-scooter phone mount for winter commuting")
    assert segs[0]["id"] in ("escooter_owners", "nordic_winter_commuters", "urban_commuters") and segs[0]["epistemic"] == "hypothesis"
    p = NS(id=1, name="Roll-top dry bag", category="", tags=[], is_demo=False)
    eco = field.build_ecosystem("edc_modular", [p])
    assert any(m["status"] == "covered" for m in eco["modules"]) and "unverified" in eco["note"]
    se = NS(id=1, name="Nordic", country="SE", eu_based=True, reliability_score=70, certifications=["EN 15194 test report"], spare_parts_available=True,
            warranty_months=24, qc_process="AQL", is_demo=False)
    cn = NS(id=2, name="Far", country="CN", eu_based=False, reliability_score=80, certifications=[], spare_parts_available=False,
            warranty_months=6, qc_process="", is_demo=False)
    rows = field.sourcing_assessment("e-bike conversion kit hub motor", [cn, se])
    assert rows[0]["name"] == "Nordic" and rows[1]["documents_missing"] and rows[0]["safety_critical"]


def test_personas_measurably_differ_and_lens_edit_changes_score():
    ctx = {"concept": {"id": 1, "evaluation": {"audience_relevance": 70, "production_cost": 40, "brand_scalability": 80, "marketing_potential": 85,
                                              "visual_recognition": 90}},
           "originality": {"score": 82, "components": {"creative_coherence": 70}, "flags": []},
           "product": {"net_margin": 0.05, "purchase_signal": None, "engagement_signal": 80, "score_confidence": 0.4, "compliance_status": "restricted"}}
    cd = PS.evaluate(PS.SEED_BY_ID["creative_director"], ctx)
    acc = PS.evaluate(PS.SEED_BY_ID["the_accountant"], ctx)
    da = PS.evaluate(PS.SEED_BY_ID["devils_advocate"], ctx)
    assert cd["weighted_score"] > acc["weighted_score"] and cd["weighted_score"] > da["weighted_score"]
    assert da["stance"] in ("oppose", "caution")
    edited = {**PS.SEED_BY_ID["the_accountant"], "evaluation_lens": {"visual_recognition": 1.0}}
    assert PS.evaluate(edited, ctx)["weighted_score"] > acc["weighted_score"]
    assert "Show me the money" in PS.voice(PS.SEED_BY_ID["the_accountant"], "x")
    assert len([p for p in PS.SEED if p["division"] == "field_ops"]) >= 20


def test_persona_concepts_differ_and_pass_gate():
    prof = scooter_profile()
    prod = {"name": "Waterproof roll-top handlebar bag for e-scooter", "net_margin": 0.2}
    segs = field.match_segments("e-scooter commuter bag winter")
    inn = M.innovation_lab(prod["name"], prof.tags)
    a = creative.author_concept(PS.SEED_BY_ID["the_visionary"], prod, prof, segs, inn)
    b = creative.author_concept(PS.SEED_BY_ID["the_accountant"], prod, prof, segs, inn)
    assert (a["primary_genre"], a["secondary_genre"]) != (b["primary_genre"], b["secondary_genre"])
    for c in (a, b):
        assert c["status"] == "draft", c["originality"]["flags"]
        assert len(c["direction"]["color_palette"]) >= 3


def test_campaign_matrix_and_analyst_ranks_contribution_not_likes():
    cells = C.testing_matrix("Roll-top bag", ["tactical_utility", "secret_archive"], "e-scooter commuters", "rain and darkness", 180.0)
    assert len(cells) >= 6 and all(c.budget_recommendation_sek == 3600 for c in cells)
    assert all("contribution" in c.measurement["primary"] for c in cells)
    camps = [NS(id=1, name="Viral", identity="funny_self_aware", genre="pop_playful", platform="tiktok"),
             NS(id=2, name="Spec", identity="technical_professional", genre="industrial", platform="youtube_shorts")]
    perf = [NS(campaign_id=1, impressions=100000, clicks=3000, engagements=9000, spend=3000, orders=10, revenue=4490, contribution=1700),
            NS(campaign_id=2, impressions=20000, clicks=600, engagements=300, spend=1500, orders=18, revenue=8082, contribution=3200)]
    res = C.analyse(camps, perf)
    assert res["campaigns"][0]["name"] == "Spec" and res["engagement_ranking"][0] == 1 and res["insight"]


def test_style_dna_learns_from_results_and_feeds_matrix():
    camps = [NS(id=1, identity="technical_professional", genre="industrial", platform="youtube_shorts"),
             NS(id=2, identity="funny_self_aware", genre="pop_playful", platform="tiktok")]
    now = datetime.now(UTC)
    perf = [NS(campaign_id=1, spend=1000, contribution=2500, engagements=10, period_start=now) for _ in range(4)] + \
           [NS(campaign_id=2, spend=1000, contribution=300, engagements=900, period_start=now) for _ in range(4)]
    dna = learning.style_dna(camps, perf, [])
    assert dna["identity"]["technical_professional"] > 0 > dna["identity"]["funny_self_aware"]
    assert dna["genre"]["industrial"] > 0 and dna["status"] == "learning"
    cells = C.testing_matrix("x", ["pop_playful"], "a", "b", None, learned_identity=dna["identity"], n_identities=8)
    order = [c.identity for c in cells]
    assert order.index("technical_professional") < len(order) - 1
    assert learning.style_dna([], [], [])["status"] == "insufficient evidence"
    early = [NS(campaign_id=1, spend=100, contribution=50, period_start=now - timedelta(days=90)) for _ in range(2)]
    late = [NS(campaign_id=1, spend=100, contribution=400, period_start=now) for _ in range(2)]
    evo = learning.genre_evolution(early + late, camps, [])
    assert evo["performance_trends"][0]["direction"] == "emerging"


def test_commercial_modules_never_force_subscriptions():
    no = CM.analyse("subscription_intel", "Steel bottle opener", "bottle opener", [])
    assert no[0].model == "none"
    yes = CM.analyse("subscription_intel", "Water filter", "filter cartridges", [])
    assert yes[0].model == "subscription_commerce"
    acq = CM.analyse("acquisition", "x", "", payload={"candidates": [{"name": "Blog", "annual_profit": 100000, "asking_price": 600000,
                                                                     "single_channel_share": 0.9}]})
    assert acq[0].requires_approval and any("6.0×" in r for r in acq[0].reasoning)
    assert all(len(CM.analyse(m, "Headlamp", "emergency light battery outdoor", [], payload={"owns_ip": True})) >= 1 for m in CM.MODULES)


def test_personalization_privacy_guard():
    ok = personalization.offer("Roll-top bag", ["giftable"], True)
    assert ok["validation"]["valid"] and ok["status"] == "supplier_customization"
    bad = personalization.validate_fields([{"name": "inferred_religion", "source": "social_media", "purpose": "target"},
                                           {"name": "price_by_profile", "source": "customer_input", "purpose": "x"}])
    assert not bad["valid"] and len(bad["errors"]) >= 3


def test_support_bar_depends_on_risk_tolerance():
    ctx = {"concept": {"id": 1, "evaluation": {"audience_relevance": 75, "production_cost": 70, "brand_scalability": 80, "marketing_potential": 75,
                                              "visual_recognition": 85}},
           "originality": {"score": 80, "components": {"creative_coherence": 85}, "flags": []},
           "product": {"net_margin": 0.2, "purchase_signal": 60, "score_confidence": 0.8, "compliance_status": "needs_review"}}
    same = {**PS.SEED_BY_ID["devils_advocate"], "evaluation_lens": PS.LENSES["executive"]}
    bold = {**same, "risk_tolerance": 0.7, "novelty_appetite": 0.2}
    da, vis = PS.evaluate(same, ctx), PS.evaluate(bold, ctx)
    assert abs(da["weighted_score"] - vis["weighted_score"]) < 5  # nearly the same score…
    assert da["stance"] != "support" and vis["stance"] == "support"  # …but the sceptic holds a higher bar
