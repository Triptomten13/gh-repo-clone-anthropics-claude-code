"""Genre taxonomy (Rocky Flare §3A, Field Ops pillar D).

Each genre is structured data, not a prompt: palette, type, materials, surfaces,
graphic language, channel fit, price-tier fit, functional affinities, production
cost, scalability, recognisability and a naming vocabulary. The matching and
fusion engines compute over these attributes.

family:
  structural – form & material language (minimalism, industrial, tactical …)
  cultural   – subculture & era codes (streetwear, retro, cyberpunk …)
  nature     – landscape & material-of-nature codes (botanical, Nordic outdoor …)
  narrative  – story worlds (biblical, ancient, esoteric, archive …) — pillar D
"""
from __future__ import annotations

from dataclasses import dataclass, field

FUNCTION_TAGS = ("tool", "outdoor", "survival", "tech", "mobility", "home", "kitchen", "apparel", "beauty", "wellness",
                 "pet", "kids", "gift", "hobby", "garden", "fitness", "office", "travel", "edc", "lighting", "storage",
                 "food", "music", "photo", "winter", "emergency")


@dataclass(frozen=True)
class Genre:
    id: str
    name: str
    family: str
    description: str
    palette: tuple[str, ...]
    display_type: str
    text_type: str
    materials: tuple[str, ...]
    surfaces: tuple[str, ...]
    graphic_language: str
    photography: str
    packaging: str
    web: str
    social: str
    advertising: str
    tiers: dict[str, float]  # budget / mid / premium fit 0..1
    affinity: dict[str, float]  # function tag -> 0..1
    audience: str
    video_fit: float  # short-form video suitability 0..1
    production_cost: int  # 1 cheap .. 5 expensive
    scalability: int  # 1..5
    recognition: int  # 1..5 visual distinctiveness
    vocab: tuple[str, ...]  # naming roots
    nouns: tuple[str, ...] = ()  # naming nouns (structural genres)
    sensitivity: tuple[str, ...] = ()  # religious | conspiracy | occult | cultural_heritage
    clashes: tuple[str, ...] = ()
    pillar: str = ""


def _t(b: float, m: float, p: float) -> dict[str, float]:
    return {"budget": b, "mid": m, "premium": p}


GENRES: dict[str, Genre] = {g.id: g for g in [
    # ------------------------------------------------------------------ structural
    Genre("scandi_minimal", "Scandinavian minimalism", "structural", "Calm, functional, honest materials and generous whitespace.",
          ("#f2efe9", "#d9d4c7", "#8a8f86", "#2f3330", "#c8a27a"), "Grotesk, light weights", "Humanist sans",
          ("oiled oak", "wool felt", "powder-coated steel", "linen"), ("matte", "brushed", "raw wood grain"),
          "Thin rules, generous margins, one accent colour", "Daylight interiors, soft shadows, single object focus",
          "Uncoated board, blind emboss, minimal ink", "Whitespace-led, large product imagery, restrained motion",
          "Quiet grid, process shots, materials close-ups", "Product-in-use calm, no hype",
          _t(.3, .8, .9), {"home": .9, "kitchen": .8, "office": .8, "gift": .6, "wellness": .7, "pet": .6, "storage": .7, "lighting": .7},
          "design-conscious urban adults valuing longevity", .45, 2, 5, 2, ("Lund", "Ljus", "Ved", "Saga", "Fjäll", "Ro"), ("Studio", "Form", "Works")),
    Genre("industrial", "Industrial design", "structural", "Exposed construction, utility, engineering honesty.",
          ("#2b2b2b", "#5c5f62", "#a7a9ac", "#d4762c", "#e8e4dc"), "Condensed grotesk, all caps", "Mono / DIN-style",
          ("raw steel", "cast aluminium", "waxed canvas", "rubber"), ("blasted", "riveted", "stencilled"),
          "Stencil numerals, part numbers, spec plates", "Workshop light, hard shadows, hands at work",
          "Kraft board, stamped labels, spec stickers", "Spec-sheet layouts, data tables, technical callouts",
          "Build process, torture tests, specs", "Function demos, durability proof with real tests",
          _t(.6, .8, .6), {"tool": 1, "edc": .8, "storage": .8, "lighting": .7, "mobility": .6, "office": .5, "home": .5},
          "makers, tradespeople, utility-minded buyers", .7, 2, 5, 4, ("Forge", "Anvil", "Rivet", "Gauge", "Torque"), ("Works", "Supply", "Co.", "Foundry")),
    Genre("brutalism", "Brutalism", "structural", "Raw, blocky, confrontational honesty.",
          ("#bdbab3", "#7a7873", "#1c1c1c", "#ff4a1c"), "Heavy grotesk, oversized", "Monospace",
          ("concrete", "raw ply", "cast resin"), ("board-marked", "unfinished"),
          "Massive type, hard blocks, no decoration", "Flat frontal light, monolithic compositions",
          "Unbleached board, oversized type wraps", "Raw HTML aesthetic, hard edges, system fonts",
          "Bold typographic posts", "Statement-led, anti-polish",
          _t(.5, .7, .6), {"home": .7, "office": .6, "apparel": .5, "storage": .5}, "architecture and design enthusiasts", .55, 2, 3, 5,
          ("Monolith", "Block", "Slab", "Plinth"), ("Studio", "Office")),
    Genre("tactical_utility", "Tactical utility", "structural", "Modularity, load-bearing function, field-ready organisation.",
          ("#3b3f32", "#6b6a4c", "#1e1f1c", "#c2b280", "#8c7a5b"), "Stencil / condensed sans", "Technical mono",
          ("1000D nylon", "hypalon", "aluminium hardware", "laser-cut laminate"), ("ripstop", "PU-coated", "laser-cut slots"),
          "Grid webbing patterns, module codes, unit markings", "Overcast field light, flat-lay loadouts, gear in use",
          "Rugged sleeves, module ID labels, reusable pouches", "Configurator-led, module diagrams, spec tables",
          "Loadout flat-lays, configuration videos", "Configuration demos, load and weather tests",
          _t(.6, .9, .7), {"edc": 1, "outdoor": .8, "survival": .9, "storage": .8, "mobility": .6, "travel": .6, "tool": .7, "lighting": .6, "emergency": .8},
          "EDC users, outdoor professionals, commuters wanting organisation", .8, 3, 5, 4,
          ("Sentinel", "Vanguard", "Bastion", "Outpost", "Cache"), ("Systems", "Division", "Supply", "Equipment", "Kit")),
    Genre("sport_performance", "Sport performance", "structural", "Speed, data, engineered performance.",
          ("#0d0d0d", "#f5f5f5", "#d7ff3a", "#3a6bff"), "Italic grotesk", "Clean sans",
          ("knit mesh", "TPU", "carbon-look composites"), ("bonded seams", "gloss/matte contrast"),
          "Speed lines, data overlays, numerals", "High shutter action, motion blur", "Window boxes, performance claims backed by tests",
          "Performance stats, comparison tables", "Training content, athlete POV", "Performance proof with measured data",
          _t(.5, .8, .7), {"fitness": 1, "mobility": .6, "outdoor": .6, "apparel": .7, "wellness": .5}, "active people tracking progress", .85, 3, 5, 3,
          ("Apex", "Stride", "Pulse", "Velo"), ("Lab", "Performance")),
    Genre("luxury", "Luxury", "structural", "Rarity, craft, restraint and ritual.",
          ("#0f0f0f", "#f4efe6", "#b08d57", "#5a1e1e"), "High-contrast serif", "Refined serif",
          ("full-grain leather", "brass", "silk", "heavy stock"), ("hot-foil", "deboss", "hand-finished edges"),
          "Monograms, crests, generous spacing", "Chiaroscuro still-life, macro craft details", "Rigid boxes, foil, tissue, unboxing ritual",
          "Editorial, slow reveal, few products", "Craft stories, limited releases", "Desire and craftsmanship, never discount-led",
          _t(0, .3, 1), {"gift": .9, "beauty": .8, "apparel": .7, "home": .6, "edc": .5, "pet": .5}, "high-income gift and self-reward buyers", .5, 5, 2, 4,
          ("Aurum", "Regent", "Maison", "Atelier"), ("Maison", "Atelier", "House")),
    Genre("minimal_premium", "Minimalist premium", "structural", "Apple-grade reduction: precision, few details, perfect finish.",
          ("#ffffff", "#e6e6e6", "#1a1a1a", "#9aa5ad"), "Geometric sans", "Neutral sans",
          ("anodised aluminium", "silicone", "glass"), ("bead-blasted", "soft-touch"), "Single icon, precise alignment",
          "Seamless backdrops, precise reflections", "Tight-fit sleeves, magnetic closures", "Big hero, minimal copy, scroll storytelling",
          "Clean product loops", "Feature reveals, precision", _t(.2, .7, .9), {"tech": 1, "office": .8, "edc": .6, "home": .6, "travel": .6},
          "professionals buying quality tech accessories", .6, 4, 4, 2, ("Lumen", "Axis", "Plane", "Unit"), ("Labs", "Design")),
    Genre("future_tech", "Futuristic consumer technology", "structural", "Clean future: soft light, sensors, interfaces.",
          ("#0b1020", "#e8ecf5", "#5ee1ff", "#7b61ff"), "Wide extended sans", "Sans",
          ("polycarbonate", "frosted acrylic", "LED light guides"), ("soft glow", "frosted"), "UI overlays, light trails, glyphs",
          "Dark studio, rim light, glowing elements", "Holographic foil accents, clean trays", "Dark mode, animated UI, specs as visuals",
          "Feature reels, UI demos", "Capability demos (honest, no CGI-only claims)", _t(.3, .7, .8),
          {"tech": 1, "mobility": .7, "lighting": .8, "home": .5, "fitness": .4}, "early adopters", .8, 4, 4, 3,
          ("Nova", "Flux", "Ion", "Vector"), ("Labs", "Systems")),
    Genre("artisan", "Artisan craftsmanship", "structural", "Handmade, provenance, maker's mark.",
          ("#efe6d8", "#b5835a", "#6b4a2f", "#2e2a24", "#7d8b6a"), "Old-style serif", "Book serif",
          ("vegetable-tanned leather", "ash wood", "stoneware", "waxed thread"), ("hand-stitched", "patina", "tool marks"),
          "Maker's stamps, hand-lettering, batch numbers", "Workshop natural light, hands, process", "Hand-stamped kraft, twine, batch cards",
          "Maker stories, process pages", "Process videos, maker portraits", "Provenance and craft (only true claims)",
          _t(.2, .7, .9), {"kitchen": .8, "home": .8, "gift": .9, "edc": .6, "outdoor": .5, "food": .7, "pet": .5}, "buyers who value provenance", .6, 4, 2, 3,
          ("Hearth", "Grain", "Kiln", "Thread"), ("Workshop", "Makers", "Craft")),
    # ------------------------------------------------------------------ cultural
    Genre("streetwear", "Streetwear", "cultural", "Drops, graphics, community codes.",
          ("#111111", "#f0f0f0", "#ff3b30", "#ffd60a"), "Heavy display / graffiti-adjacent", "Grotesk",
          ("heavyweight cotton", "nylon", "rubber patches"), ("puff print", "embroidery"), "Bold logos, stickers, drop numbers",
          "Street flash photography, crews", "Branded mailers, stickers", "Drop countdowns, lookbooks", "Creator collabs, drops",
          "Hype with authenticity (no fake scarcity)", _t(.6, .8, .5), {"apparel": 1, "edc": .6, "mobility": .5, "music": .5},
          "15–30 urban trend followers", .9, 2, 4, 4, ("Block", "Raw", "Static", "Crew"), ("Supply", "Club")),
    Genre("underground", "Underground culture", "cultural", "DIY scenes, zines, raw authenticity.",
          ("#0a0a0a", "#e3e1da", "#9b1c1c", "#4c4c4c"), "Photocopied / distressed type", "Typewriter",
          ("recycled paper", "screenprint", "patches"), ("xerox grain", "distressed"), "Collage, cut-and-paste, xerox textures",
          "Flash, grain, candid scenes", "Zine inserts, screenprinted bags", "Raw, zine-like layouts", "Scene documentation",
          "Insider language, community-first", _t(.7, .6, .2), {"apparel": .7, "music": .8, "hobby": .6, "edc": .5},
          "subculture participants", .8, 1, 2, 4, ("Static", "Basement", "Signal", "Noise"), ("Collective", "Records", "Supply")),
    Genre("pop_playful", "Playful pop culture", "cultural", "Colour, humour, character.",
          ("#ff5fa2", "#ffd23f", "#3bceac", "#3a86ff", "#fdfdfd"), "Rounded bold display", "Rounded sans",
          ("ABS", "silicone", "printed cotton"), ("glossy", "candy colours"), "Characters, stickers, bouncy shapes",
          "Bright flat backdrops, stop-motion", "Colour-blocked boxes, surprise inserts", "Animated, playful micro-interactions",
          "Memes (original), characters", "Humour, self-aware", _t(.9, .7, .2), {"kids": .9, "gift": .8, "pet": .8, "hobby": .7, "kitchen": .5},
          "young adults and families", .95, 2, 4, 4, ("Pop", "Bop", "Fizz", "Doodle"), ("Club", "Co.")),
    Genre("retro_futurism", "Retro futurism", "cultural", "Yesterday's tomorrow: chrome, rockets, optimism.",
          ("#1b1f3b", "#f2c14e", "#f78154", "#4d9078", "#e8e1d5"), "Streamline display", "Geometric sans",
          ("chrome", "bakelite-look", "enamel"), ("chrome", "enamel"), "Atomic shapes, starbursts, orbit lines",
          "Saturated set design, period props", "Tin boxes, illustrated labels", "Poster-style, illustrated", "Illustrated loops",
          "Nostalgic optimism", _t(.4, .8, .6), {"home": .6, "kitchen": .6, "gift": .7, "tech": .5, "music": .6},
          "nostalgia-driven design fans", .75, 3, 3, 5, ("Orbit", "Atomic", "Comet", "Rocket"), ("Co.", "Works")),
    Genre("vintage_americana", "Vintage Americana", "cultural", "Workwear heritage, roadside signage, enamel badges.",
          ("#1f2e45", "#b23a2f", "#e8dcc4", "#c99b3b"), "Slab serif / script", "Serif",
          ("selvedge denim", "enamel", "tin", "leather patches"), ("faded", "chain-stitch"), "Badges, banners, pennants",
          "Warm film tones, roadside scenes", "Tin cans, kraft, badges", "Heritage storytelling", "Road-trip stories",
          "Heritage pride (no false 'since 18xx' claims)", _t(.5, .8, .6), {"apparel": .8, "outdoor": .6, "tool": .6, "food": .6, "edc": .5},
          "heritage and workwear fans", .6, 3, 4, 4, ("Route", "Union", "Liberty", "Mesa"), ("Mercantile", "Goods", "Co.")),
    Genre("western", "Western", "cultural", "Frontier ruggedness, leather, horizon.",
          ("#5b3a29", "#c8a37a", "#2a2a2a", "#e9e2d0", "#a0522d"), "Wood-type serif", "Serif",
          ("tooled leather", "rawhide", "brass conchos"), ("tooled", "sun-faded"), "Wood type, rope borders, brands",
          "Golden hour, open land", "Leather tags, branded wood", "Wanted-poster typography", "Ranch & road stories",
          "Self-reliance", _t(.4, .8, .6), {"outdoor": .7, "apparel": .7, "edc": .5, "food": .5, "tool": .5}, "outdoor lifestyle buyers", .65, 3, 3, 4,
          ("Mesa", "Ranger", "Drifter", "Spur"), ("Outfitters", "Trading Co.")),
    Genre("japanese", "Japanese design", "cultural", "Ma (negative space), craft, wabi-sabi imperfection.",
          ("#f3efe7", "#2b2b2b", "#b4442f", "#6f7d5c", "#d9c7a7"), "Brush-inspired or refined serif", "Clean sans",
          ("hinoki-style wood", "washi paper", "cast iron", "ceramic"), ("wabi-sabi", "indigo dye"), "Asymmetry, seals, negative space",
          "Soft natural light, seasonal props", "Furoshiki-style wraps, washi labels", "Quiet, asymmetric layouts", "Seasonal rituals",
          "Ritual and care (avoid cultural pastiche)", _t(.3, .7, .9), {"kitchen": .9, "home": .8, "wellness": .7, "gift": .7, "garden": .6},
          "craft and ritual-minded buyers", .5, 3, 3, 4, ("Kumo", "Mori", "Kaze", "Hara"), ("Studio", "Goods"), ("cultural_heritage",)),
    Genre("cyberpunk", "Cyberpunk", "cultural", "High tech, low life: neon, glitch, dense cities.",
          ("#0a0014", "#ff2a6d", "#05d9e8", "#d1f7ff", "#ff9e00"), "Glitch / wide display", "Mono",
          ("reflective TPU", "black nylon", "LED trims"), ("neon edge", "glitch print"), "HUD frames, kanji-free glyph systems, warnings",
          "Night city, neon reflections, rain", "Black mailers, UV ink", "Dark, glitchy, terminal UI", "Night reels",
          "Edgy, futuristic", _t(.6, .8, .5), {"tech": .9, "edc": .7, "apparel": .7, "mobility": .7, "lighting": .8},
          "gamers and urban tech enthusiasts", .9, 3, 4, 5, ("Neon", "Ghost", "Circuit", "Null"), ("Systems", "Net", "Supply")),
    Genre("nostalgic_retro", "Nostalgic retro", "cultural", "80s/90s memory: cassettes, arcades, VHS.",
          ("#2d1e2f", "#f15bb5", "#fee440", "#00bbf9", "#9b5de5"), "Chrome / pixel display", "Sans",
          ("plastic", "cassette-shell", "printed tin"), ("VHS scanlines", "gloss"), "Pixel art, gradients, tape labels",
          "Flash on film, CRT glow", "Cassette-style cases", "Retro OS windows", "Throwback edits", "Nostalgia", _t(.8, .7, .3),
          {"music": .8, "gift": .8, "tech": .6, "hobby": .7, "kids": .5}, "millennial nostalgia buyers", .9, 2, 3, 4,
          ("Rewind", "Arcade", "Tape", "Pixel"), ("Club", "Co.")),
    Genre("diy_maker", "DIY & maker culture", "cultural", "Open, hackable, learn-by-building.",
          ("#f4f1ea", "#2d3142", "#ef8354", "#4f5d75"), "Hand-drawn / mono", "Mono",
          ("plywood", "3D-print PLA", "perfboard", "zip ties"), ("visible screws", "laser-etched"), "Blueprints, assembly diagrams, exploded views",
          "Bench shots, step-by-step", "Flat-pack with diagrams", "Tutorial-first, open docs", "Build logs, community remixes",
          "Empowerment, learn & repair", _t(.8, .8, .3), {"hobby": 1, "tool": .8, "tech": .7, "kids": .5, "garden": .5, "edc": .5},
          "makers, repairers, tinkerers", .85, 1, 5, 3, ("Bench", "Kit", "Hack", "Build"), ("Workshop", "Lab", "Kits")),
    Genre("psychedelic", "Psychedelic", "cultural", "Saturated colour, fluid forms, altered perception (visual only).",
          ("#ff6b35", "#f7c59f", "#004e89", "#9c27b0", "#1a936f"), "Melting display", "Rounded sans",
          ("printed fabric", "UV inks"), ("marbled", "liquid gradients"), "Fluid patterns, op-art, kaleidoscopes",
          "Coloured gels, double exposure", "Holographic or marbled prints", "Immersive colour fields", "Visual loops",
          "Sensory, striking (no drug references)", _t(.6, .8, .5), {"apparel": .7, "music": .8, "home": .5, "gift": .6, "garden": .4},
          "festival and art audiences", .9, 3, 3, 5, ("Prism", "Bloom", "Haze", "Spiral"), ("Studio", "Collective")),
    Genre("gothic", "Gothic", "cultural", "Dark romance, arches, black lace and silver.",
          ("#0b0b0d", "#3c1f2b", "#8b0000", "#c0c0c0"), "Blackletter", "Serif",
          ("black velvet", "silver", "wrought iron"), ("filigree", "aged silver"), "Arches, filigree, blackletter",
          "Candlelight, deep shadow", "Black boxes, wax seals", "Dark editorial", "Moody reels", "Romantic darkness",
          _t(.4, .8, .7), {"apparel": .8, "home": .6, "gift": .7, "beauty": .6}, "alternative fashion buyers", .7, 3, 3, 5,
          ("Raven", "Vesper", "Nocturne", "Crypt"), ("House", "Atelier")),
    Genre("dark_academia", "Dark academia", "cultural", "Libraries, tweed, candlelit study.",
          ("#2e2a24", "#5c4033", "#8b7d6b", "#d8c8a8", "#3b4a3f"), "Old-style serif", "Book serif",
          ("tweed", "leather", "brass", "aged paper"), ("foxed paper", "worn leather"), "Library stamps, Latin mottos, ex libris",
          "Window light, books, ink", "Book-like boxes, ex libris labels", "Editorial, footnotes", "Study aesthetics",
          "Intellectual romance", _t(.4, .8, .8), {"office": .8, "gift": .8, "apparel": .6, "home": .6, "hobby": .5}, "students and readers", .7, 3, 3, 4,
          ("Scriptor", "Lector", "Folio", "Codex"), ("& Co.", "Society", "Library")),
    Genre("experimental_art", "Experimental art", "cultural", "Gallery-grade weirdness: rules broken on purpose.",
          ("#f2f2f2", "#000000", "#ff00a8", "#00ffa3"), "Variable / distorted type", "Mono",
          ("acrylic", "risograph prints", "unexpected composites"), ("riso grain", "glitch"), "Generative patterns, broken grids",
          "Conceptual set pieces", "Art-object packaging, numbered editions", "Non-standard layouts (accessibility kept)", "Art drops",
          "Provocative, conceptual", _t(.3, .6, .8), {"home": .6, "apparel": .6, "gift": .6, "music": .6}, "art collectors and creatives", .8, 4, 2, 5,
          ("Void", "Glitch", "Index", "Proto"), ("Studio", "Editions")),
    Genre("urban_commuter", "Urban commuter", "cultural", "City movement: weatherproof, reflective, efficient.",
          ("#1f2326", "#e9eef0", "#f2c94c", "#56ccf2", "#9aa0a6"), "Wayfinding sans", "Sans",
          ("TPU-coated nylon", "reflective tape", "magnetic buckles"), ("roll-top", "reflective piping"), "Transit-map lines, wayfinding icons",
          "Rain-wet streets, dusk, motion", "Roll-top sleeves, transit-style labels", "Route-like navigation, quick configurators",
          "Commute POV clips", "Practical everyday reliability", _t(.5, .9, .6), {"mobility": 1, "travel": .8, "edc": .7, "storage": .7, "lighting": .7, "apparel": .5, "winter": .6},
          "bike, e-bike and e-scooter commuters", .85, 3, 5, 3, ("Transit", "Route", "Metro", "Loop"), ("Commute", "Mobility", "Supply")),
    # ------------------------------------------------------------------ nature
    Genre("organic_botanical", "Organic & botanical", "nature", "Living materials, plants, softness.",
          ("#e9edc9", "#a3b18a", "#588157", "#3a5a40", "#dad7cd"), "Soft serif", "Humanist sans",
          ("recycled paper", "cork", "bamboo", "cotton"), ("pressed leaves", "seed paper"), "Leaf forms, hand-drawn botanicals",
          "Greenhouse light, plants", "Plantable / compostable packaging (only if certified)", "Soft, nature-led", "Growing timelapses",
          "Calm care (no greenwashing)", _t(.6, .8, .6), {"garden": 1, "wellness": .8, "home": .7, "kitchen": .6, "beauty": .7, "pet": .5},
          "plant and wellness enthusiasts", .7, 2, 4, 2, ("Fern", "Moss", "Root", "Seed", "Linden"), ("Botanics", "Garden", "Co.")),
    Genre("outdoor_adventure", "Outdoor adventure", "nature", "Trails, summits and weather.",
          ("#2f4f4f", "#e07a5f", "#f4f1de", "#3d405b", "#81b29a"), "Rugged sans", "Sans",
          ("ripstop", "merino", "aluminium"), ("topo lines", "weathered"), "Topographic lines, trail markers",
          "Landscape scale, golden hour, real use", "Recycled mailers, trail-map inserts", "Adventure stories, spec tables",
          "Trip reels, gear tests", "Exploration (honest test data)", _t(.5, .8, .7),
          {"outdoor": 1, "survival": .7, "travel": .8, "fitness": .6, "apparel": .6, "lighting": .6, "edc": .5},
          "hikers, campers, travellers", .85, 3, 5, 2, ("Ridge", "Summit", "Trail", "Cairn"), ("Outfitters", "Gear", "Expeditions")),
    Genre("nordic_survival", "Nordic survival", "nature", "Cold, dark, wet — and prepared for it.",
          ("#1d2731", "#e5e9ec", "#c1440e", "#5b7065", "#a9b4c2"), "Condensed sans", "Sans",
          ("wool", "waxed cotton", "reflective trims", "birch"), ("frost-matte", "reflective"), "Snow-camouflage patterns, bearings, northern grids",
          "Blue-hour, snow, headlamp light", "Weatherproof pouches, reusable tins", "Season-aware guides, kit builders",
          "Winter readiness, real conditions", "Preparedness without fear-mongering", _t(.4, .9, .7),
          {"winter": 1, "survival": .9, "outdoor": .9, "emergency": .9, "mobility": .6, "lighting": .8, "apparel": .6},
          "Nordic residents, winter commuters, cabin owners", .75, 3, 4, 4, ("Norr", "Vinter", "Fjäll", "Polar", "Is"), ("Utrustning", "Fieldworks", "Supply")),
    Genre("expedition_nomad", "Nomadic expedition tech", "nature", "Portable electronics meets expedition kit.",
          ("#2b2d2f", "#d6cfc4", "#e0a458", "#4b6858"), "Wide sans", "Mono",
          ("ripstop", "aluminium", "silicone", "solar fabric"), ("anodised", "ripstop"), "Coordinates, battery icons, modular grids",
          "Remote landscapes with devices", "Modular hard cases", "Kit configurators", "Off-grid workdays",
          "Freedom to work anywhere", _t(.4, .8, .8), {"tech": .9, "travel": 1, "outdoor": .8, "edc": .7, "survival": .5},
          "digital nomads, overlanders", .8, 3, 4, 3, ("Nomad", "Atlas", "Meridian", "Waypoint"), ("Tech", "Division", "Systems")),
    # ------------------------------------------------------------------ narrative (pillar D)
    Genre("biblical_heritage", "Biblical heritage", "narrative", "Gardens, journeys, shepherds and arks — understated, respectful.",
          ("#e8dfc8", "#7a6a4f", "#3e5641", "#b08d57", "#2a2622"), "Inscriptional serif", "Book serif",
          ("parchment-look paper", "olive wood", "linen", "brass"), ("aged parchment", "debossed"), "Ancient maps of the Levant, olive branches, ark & shepherd motifs",
          "Warm desert light, natural materials", "Linen-wrapped, scroll-like inserts", "Map-led storytelling",
          "Parables as story frames", "Meaning and stewardship (respectful, no sacred-symbol commerce gimmicks)", _t(.3, .7, .8),
          {"outdoor": .7, "survival": .7, "gift": .8, "garden": .7, "edc": .5, "travel": .6},
          "faith-curious and heritage-minded buyers", .55, 3, 3, 4, ("Eden", "Exodus", "Ark", "Shepherd", "Jordan", "Canaan"), (),
          ("religious",), (), "D"),
    Genre("mesopotamian", "Ancient Mesopotamia", "narrative", "Babylon's ziggurats, cuneiform, lapis and gold.",
          ("#1c2541", "#2b59c3", "#d4a017", "#c2a878", "#1b1b1b"), "Wedge-inspired display", "Serif",
          ("dark bronze", "lapis-blue enamel", "fired clay"), ("glazed brick", "stamped clay"), "Cuneiform-like strokes, stepped ziggurat forms, glazed-brick lions",
          "Low-key light, gold accents", "Stepped boxes, clay-texture labels", "Monumental, stepped layouts", "Lore drops",
          "Monumental strength", _t(.3, .7, .8), {"edc": .7, "tool": .6, "gift": .6, "outdoor": .5, "home": .5},
          "history-minded gear buyers", .65, 3, 3, 5, ("Babylon", "Ur", "Ishtar", "Ziggurat", "Akkad"), (), ("cultural_heritage",), (), "D"),
    Genre("ancient_egypt", "Ancient Egypt", "narrative", "Geometry of pyramids, gold, lapis, hieroglyphic order.",
          ("#d4a017", "#1f3a93", "#e8d5a3", "#0f0f0f"), "Inscriptional display", "Serif",
          ("gold leaf", "faience-look ceramic", "linen"), ("gilded", "carved"), "Registers, cartouche frames, eye-of-horus-free geometric motifs",
          "Hard sun, deep shadow", "Gilded boxes, cartouche labels", "Register-based layouts", "Myth-inspired stories",
          "Timeless order", _t(.3, .7, .8), {"gift": .7, "home": .6, "beauty": .6, "edc": .4}, "history enthusiasts", .6, 4, 3, 5,
          ("Kemet", "Sol", "Nile", "Obelisk"), (), ("cultural_heritage",), (), "D"),
    Genre("classical", "Classical antiquity (Rome & Greece)", "narrative", "Marble, columns, laurels, order.",
          ("#f2f0ea", "#c9c5bb", "#6e6658", "#b08d57", "#7c2d12"), "Roman capitals", "Serif",
          ("marble-look stone", "bronze", "terracotta"), ("chiselled", "patinated bronze"), "Roman numerals, meanders, laurels",
          "Sculptural light", "Columned boxes, embossed laurels", "Monumental capitals", "Philosophy quotes (correctly attributed)",
          "Endurance and virtue", _t(.4, .7, .8), {"fitness": .7, "gift": .6, "home": .6, "edc": .5, "office": .5},
          "stoic-philosophy and fitness audiences", .7, 3, 4, 4, ("Legio", "Aurelius", "Atlas", "Kairos", "Stoa"), (), (), (), "D"),
    Genre("norse_myth", "Nordic mythology", "narrative", "Runes, knotwork, longships and winter gods.",
          ("#1f2a30", "#7d8a8c", "#b7a57a", "#7f1d1d", "#e6e2d6"), "Rune-inspired display", "Sans",
          ("iron", "birch", "wool", "horn-look composites"), ("forged", "carved knotwork"), "Knotwork, runic borders (no extremist symbols)",
          "Fjords, fog, firelight", "Wood & iron, runic seals", "Saga-led storytelling", "Saga shorts",
          "Endurance and kinship (avoid symbols co-opted by extremists)", _t(.4, .8, .7),
          {"outdoor": .8, "survival": .8, "winter": .8, "edc": .6, "apparel": .6, "kitchen": .4},
          "Nordic heritage and outdoor fans", .75, 3, 4, 5, ("Ask", "Yggdra", "Fenrir", "Mjöd", "Varg"), (), ("cultural_heritage",), (), "D"),
    Genre("illuminated_manuscript", "Illuminated manuscripts", "narrative", "Monastic libraries, gilded initials, marginalia.",
          ("#efe3c8", "#7b1e1e", "#1e3a5f", "#c9a227", "#2b2b2b"), "Uncial / gothic initials", "Book serif",
          ("vellum-look paper", "gold ink", "leather bindings"), ("gilded initials", "foxing"), "Drop caps, marginalia creatures, rubrication",
          "Candlelit desks, macro of pages", "Book-bound boxes, wax seals", "Folio-style long reads", "Page-turn reels",
          "Knowledge as treasure", _t(.3, .7, .9), {"gift": .8, "office": .7, "hobby": .7, "edc": .6, "home": .5},
          "readers, collectors, journaling fans", .6, 4, 3, 5, ("Codex", "Folio", "Scriptorium", "Vellum", "Marginalia"), (), (), (), "D"),
    Genre("alchemy_hermetic", "Alchemy & Hermetic philosophy", "narrative", "Transmutation diagrams, symbols, laboratory glass.",
          ("#141414", "#c9a227", "#5e3b1f", "#e9dcc0", "#2f4f4f"), "Engraved serif", "Serif",
          ("brass", "smoked glass", "aged paper"), ("engraved", "acid-etched"), "Planetary glyphs, transmutation diagrams, alchemical tables",
          "Laboratory still-life, warm tungsten", "Apothecary bottles, engraved labels", "Diagrammatic layouts", "Process-as-ritual",
          "Transformation", _t(.3, .7, .8), {"kitchen": .5, "beauty": .6, "gift": .7, "hobby": .7, "edc": .6, "tool": .5},
          "esoteric-design fans, makers", .7, 3, 3, 5, ("Aether", "Mercurius", "Opus", "Sol", "Azoth"), (), ("occult",), (), "D"),
    Genre("celestial_cartography", "Celestial cartography", "narrative", "Astrolabes, star charts, ancient maps.",
          ("#0e1b2b", "#e8dcc0", "#b08d57", "#5c7a8a"), "Engraved capitals", "Serif",
          ("brass", "map paper", "navy canvas"), ("engraved lines", "aged map"), "Star charts, compass roses, graticules, astrolabe rings",
          "Night sky, brass instruments", "Map-wrapped boxes, compass-rose seals", "Map-based navigation", "Star-and-map shorts",
          "Navigation and wonder", _t(.4, .8, .8), {"outdoor": .8, "travel": .9, "edc": .7, "gift": .7, "survival": .6, "mobility": .5},
          "explorers, navigators, travellers", .7, 3, 4, 4, ("Meridian", "Polaris", "Astrolabe", "Sextant", "Zenith"), (), (), (), "D"),
    Genre("sacred_geometry", "Sacred geometry", "narrative", "Historical geometric systems: circles, ratios, rosettes.",
          ("#101010", "#d9b44a", "#f2ead3", "#4a3f35"), "Geometric serif", "Sans",
          ("brass", "laser-etched wood"), ("etched lines", "gold-on-black"), "Compass constructions, rosettes, golden-ratio grids",
          "Top-down symmetrical compositions", "Etched boxes", "Grid-perfect layouts", "Construction animations", "Harmony and order",
          _t(.4, .8, .7), {"home": .6, "edc": .6, "gift": .6, "wellness": .6, "tech": .5}, "design-and-meaning seekers", .8, 2, 5, 4,
          ("Vesica", "Phi", "Rosette", "Axis"), (), (), (), "D"),
    Genre("botanical_illustration", "Symbolic botanical illustration", "narrative", "Herbaria, engraved plates, Latin names.",
          ("#f1ead8", "#5f7a4f", "#8c3b2e", "#2f2a23"), "Engraved serif", "Book serif",
          ("cotton paper", "pressed flora"), ("copperplate engraving", "hand-tinted"), "Engraved plant plates, Latin labels, specimen tags",
          "Herbarium flat-lays", "Specimen-tag labels, seed-packet formats", "Plate-based catalogue", "Specimen reels", "Curiosity and care",
          _t(.5, .8, .7), {"garden": 1, "outdoor": .7, "survival": .6, "kitchen": .6, "wellness": .6, "gift": .7},
          "gardeners, foragers, naturalists", .65, 2, 4, 4, ("Herbarium", "Flora", "Specimen", "Linnaea", "Botanica"), (), (), (), "D"),
    Genre("archaeological", "Archaeological artifact", "narrative", "Field notes, finds trays, catalogue numbers.",
          ("#d6c7a1", "#8b7355", "#3f3a33", "#a85a32"), "Typewriter / stencil", "Mono",
          ("canvas", "clay", "aged brass", "field-note paper"), ("dusty", "catalogue-stamped"), "Find numbers, grid squares, sketches",
          "Excavation light, finds trays", "Finds bags, catalogue labels", "Catalogue/specimen pages", "Field-dig stories", "Discovery",
          _t(.5, .8, .7), {"outdoor": .7, "edc": .7, "hobby": .7, "tool": .6, "storage": .6}, "explorers, collectors", .65, 2, 4, 4,
          ("Strata", "Relic", "Trowel", "Cache"), (), (), (), "D"),
    Genre("secret_archive", "Secret archive (fictional)", "narrative", "Redacted files, dossiers, stamped classifications — clearly fictional.",
          ("#e6dfcf", "#1c1c1c", "#9e1b1b", "#55594a", "#c2b49a"), "Typewriter + stencil", "Mono",
          ("manila card", "canvas", "black anodised metal"), ("redaction bars", "rubber stamps"), "Redacted lines, file numbers, fictional stamps (no real agency seals)",
          "Desk-lamp noir, dossier flat-lays", "Dossier folders, fictional case files", "File-browser UI, case numbers", "Unboxing as case file",
          "Mystery and intrigue as fiction", _t(.5, .8, .7), {"edc": .9, "storage": .8, "office": .6, "tool": .5, "survival": .5, "gift": .6},
          "mystery and EDC enthusiasts", .8, 2, 4, 5, ("Archivum", "Dossier", "Cipher", "Ledger", "Redact"), (), ("conspiracy",), (), "D"),
    Genre("surveillance_dystopia", "Surveillance dystopia (fictional)", "narrative", "Screens, monitors, analog tech, control-room noir.",
          ("#050505", "#1e1e1e", "#e3e3e3", "#d7263d", "#32cd32"), "Terminal mono", "Mono",
          ("black anodised metal", "smoked acrylic", "rubber"), ("scanlines", "matte black"), "Monitor frames, scanlines, warning labels",
          "CRT glow, black rooms", "Black mailers, warning tape", "Terminal-style UI (readable)", "Analog-tech edits",
          "Privacy-conscious independence", _t(.5, .8, .6), {"tech": .8, "edc": .8, "storage": .5, "apparel": .5},
          "privacy-minded tech users", .85, 3, 4, 5, ("Mirror", "Signal", "Static", "Blackout", "Grid"), (), ("conspiracy",), (), "D"),
    Genre("lost_civilization", "Lost civilisation (fictional)", "narrative", "Ruins, glyph systems, expedition logs.",
          ("#2d3a2e", "#c8b88a", "#7b5e3b", "#e4dccf"), "Glyph-inspired display", "Serif",
          ("stone-look resin", "jute", "brass"), ("eroded", "moss-stained"), "Invented glyph systems, ruin silhouettes",
          "Jungle mist, torchlight", "Expedition crates", "Map & log storytelling", "Expedition series", "Wonder (presented as fiction)",
          _t(.5, .8, .6), {"outdoor": .7, "hobby": .6, "gift": .6, "edc": .5}, "adventure-story fans", .75, 3, 3, 4,
          ("Atlantis", "Aztlan", "Lemuria", "Ruin"), (), ("conspiracy",), (), "D"),
    Genre("techno_occult", "Techno occult", "narrative", "Circuits meet sigils: occult geometry rendered as technology.",
          ("#0b0b0b", "#9ef01a", "#c9a227", "#5a189a"), "Engraved + mono hybrid", "Mono",
          ("PCB-look laminates", "black metal", "brass inlay"), ("etched traces", "gold-on-black"), "Sigil-like circuit traces, glyph matrices",
          "Dark macro, glowing traces", "Black boxes with etched sigils", "Dark ritual-tech UI", "Glitch-sigil loops",
          "Mystery and craft (fictional symbolism)", _t(.3, .7, .7), {"tech": .8, "edc": .7, "apparel": .6, "music": .6},
          "alt-tech and design audiences", .85, 3, 3, 5, ("Sigil", "Daemon", "Hex", "Oracle"), (), ("occult",), (), "D"),
]}

# Category-typical aesthetics (what competitors usually look like) — used for differentiation scoring.
CATEGORY_TYPICAL: dict[str, tuple[str, ...]] = {
    "outdoor": ("outdoor_adventure", "tactical_utility"), "survival": ("tactical_utility", "outdoor_adventure"),
    "tech": ("minimal_premium", "future_tech"), "mobility": ("urban_commuter", "sport_performance"),
    "home": ("scandi_minimal", "organic_botanical"), "kitchen": ("scandi_minimal", "artisan"), "beauty": ("minimal_premium", "luxury"),
    "wellness": ("organic_botanical", "scandi_minimal"), "pet": ("pop_playful", "scandi_minimal"), "kids": ("pop_playful",),
    "garden": ("organic_botanical",), "fitness": ("sport_performance",), "apparel": ("streetwear", "minimal_premium"),
    "edc": ("tactical_utility", "industrial"), "office": ("minimal_premium", "scandi_minimal"), "gift": ("luxury", "pop_playful"),
    "tool": ("industrial",), "lighting": ("minimal_premium", "industrial"), "travel": ("minimal_premium", "outdoor_adventure"),
    "winter": ("outdoor_adventure",), "emergency": ("tactical_utility",), "hobby": ("diy_maker",), "storage": ("industrial", "scandi_minimal"),
}

# Typical palettes per category: the "predictable" combinations the anti-generic filter checks against.
PREDICTABLE_PALETTES: dict[str, tuple[tuple[str, ...], ...]] = {
    "generic": (("#ffffff", "#000000", "#1e90ff"), ("#0a2540", "#ffffff", "#d4af37"), ("#000000", "#ffd700", "#ffffff")),
    "outdoor": (("#2e4d2c", "#8b5a2b", "#ff7f00"),), "tech": (("#ffffff", "#0066ff", "#111111"),),
    "wellness": (("#e8efe5", "#9caf88", "#f5f0e6"),), "kids": (("#ff0000", "#ffff00", "#0000ff"),),
}

# Reference hybrids supplied in the Field Operations brief (presets; names are starting points only).
PRESET_HYBRIDS: list[dict] = [
    {"id": "eden_survival", "name": "Eden Survival", "components": ["nordic_survival", "botanical_illustration", "biblical_heritage", "outdoor_adventure"]},
    {"id": "babylon_tactical", "name": "Babylon Tactical", "components": ["industrial", "mesopotamian", "tactical_utility"]},
    {"id": "archivum_field_gear", "name": "Archivum Field Gear", "components": ["tactical_utility", "illuminated_manuscript", "secret_archive"]},
    {"id": "gsus_mobility", "name": "G-SUS Mobility", "components": ["urban_commuter", "celestial_cartography", "biblical_heritage", "luxury"]},
    {"id": "northern_sentinel", "name": "Northern Sentinel", "components": ["nordic_survival", "industrial", "scandi_minimal"]},
    {"id": "black_mirror_edc", "name": "Black Mirror EDC", "components": ["streetwear", "cyberpunk", "surveillance_dystopia", "techno_occult"]},
    {"id": "apocalyptic_commuter", "name": "Apocalyptic Commuter", "components": ["urban_commuter", "nordic_survival", "surveillance_dystopia"]},
    {"id": "shepherds_kit", "name": "The Shepherd's Kit", "components": ["outdoor_adventure", "celestial_cartography", "biblical_heritage"]},
    {"id": "archive_of_eden", "name": "Archive of Eden", "components": ["botanical_illustration", "illuminated_manuscript", "future_tech", "organic_botanical"]},
    {"id": "nomadic_tech", "name": "Nomadic Tech", "components": ["expedition_nomad", "tactical_utility", "future_tech"]},
]

# Family complementarity for fusion (structural+narrative is the strongest pairing).
FAMILY_COMPLEMENT = {
    frozenset({"structural", "narrative"}): 1.0, frozenset({"structural", "cultural"}): .8, frozenset({"nature", "narrative"}): .9,
    frozenset({"structural", "nature"}): .75, frozenset({"cultural", "narrative"}): .7, frozenset({"cultural", "nature"}): .6,
    frozenset({"structural"}): .45, frozenset({"cultural"}): .4, frozenset({"nature"}): .4, frozenset({"narrative"}): .5,
}
# Pairs that fight each other visually or semantically.
CLASHES = {frozenset(p) for p in [
    ("pop_playful", "gothic"), ("pop_playful", "surveillance_dystopia"), ("luxury", "underground"), ("luxury", "diy_maker"),
    ("scandi_minimal", "psychedelic"), ("minimal_premium", "experimental_art"), ("biblical_heritage", "techno_occult"),
    ("biblical_heritage", "alchemy_hermetic"), ("biblical_heritage", "gothic"), ("pop_playful", "biblical_heritage"),
    ("brutalism", "luxury"), ("japanese", "western"),
]}

KEYWORDS: dict[str, tuple[str, ...]] = {
    "tool": ("tool", "multi-tool", "multitool", "wrench", "screwdriver", "pliers", "repair", "kit"),
    "outdoor": ("outdoor", "camp", "camping", "hike", "hiking", "trail", "tarp", "tent", "bushcraft", "shelter"),
    "survival": ("survival", "bushcraft", "prepared", "preparedness", "emergency", "fire start", "ferro", "paracord", "filter"),
    "emergency": ("emergency", "first aid", "first-aid", "blanket", "radio", "preparedness", "72h", "kris"),
    "winter": ("winter", "cold", "snow", "ice", "thermal", "insulated", "vinter", "heated", "glove"),
    "tech": ("usb", "smart", "bluetooth", "charger", "power bank", "solar", "gps", "led", "electronic", "app"),
    "mobility": ("scooter", "e-scooter", "e-bike", "ebike", "bicycle", "bike", "cycling", "pannier", "handlebar", "commut", "elcykel", "elsparkcykel"),
    "home": ("home", "decor", "living", "furniture", "shelf"), "kitchen": ("kitchen", "coffee", "mug", "cook", "baking", "sourdough", "pour-over"),
    "apparel": ("shirt", "hoodie", "jacket", "apparel", "clothing", "sock", "cap", "glove"), "beauty": ("skincare", "cosmetic", "beauty", "serum"),
    "wellness": ("sleep", "yoga", "wellness", "relax", "meditation"), "pet": ("dog", "cat", "pet", "leash"), "kids": ("kid", "toy", "child", "baby"),
    "gift": ("gift", "personalised", "personalized", "giftable", "engraved"), "hobby": ("hobby", "craft", "diy", "maker", "sourdough", "educational"),
    "garden": ("garden", "plant", "seed", "grow", "botanical"), "fitness": ("fitness", "gym", "workout", "training"),
    "office": ("desk", "office", "notebook", "pen"), "travel": ("travel", "luggage", "passport", "organiser", "organizer"),
    "edc": ("edc", "everyday carry", "wallet", "pouch", "organizer", "organiser", "keychain", "flashlight", "multitool", "multi-tool"),
    "lighting": ("lamp", "light", "led", "flashlight", "headlamp", "lantern"), "storage": ("bag", "pouch", "case", "box", "storage", "organiser", "organizer", "pannier", "backpack", "container"),
    "food": ("food", "snack", "tea", "coffee", "ration"), "music": ("music", "audio", "speaker", "vinyl"), "photo": ("camera", "photo", "drone", "tripod"),
}


@dataclass
class ProductProfile:
    tags: dict[str, float] = field(default_factory=dict)
    tier: str = "mid"
    marketing_potential: float = 50.0
    category_typical: tuple[str, ...] = ()


def profile_product(name: str, category: str = "", tags: list[str] | None = None, description: str = "",
                    retail: float | None = None, competitor_prices: list[float] | None = None,
                    marketing_potential: float | None = None) -> ProductProfile:
    text = " ".join([name, category, " ".join(tags or []), description]).lower()
    found: dict[str, float] = {}
    for tag, kws in KEYWORDS.items():
        hits = sum(1 for k in kws if k in text)
        if hits:
            found[tag] = min(1.0, 0.5 + 0.25 * hits)
    if category.lower() in FUNCTION_TAGS:
        found[category.lower()] = 1.0
    comp = sorted(p for p in (competitor_prices or []) if p)
    tier = "mid"
    if retail:
        if comp:
            med = comp[len(comp) // 2]
            tier = "premium" if retail > med * 1.25 else "budget" if retail < med * 0.85 else "mid"
        else:
            tier = "premium" if retail >= 800 else "budget" if retail <= 150 else "mid"
    typical: list[str] = []
    for t in sorted(found, key=found.get, reverse=True)[:3]:
        typical.extend(CATEGORY_TYPICAL.get(t, ()))
    return ProductProfile(tags=found or {"gift": 0.3}, tier=tier, marketing_potential=marketing_potential or 50.0,
                          category_typical=tuple(dict.fromkeys(typical)))
