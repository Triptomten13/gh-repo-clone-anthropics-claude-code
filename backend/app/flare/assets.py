"""Creative asset generation through provider adapters (§4 Brand laboratory).

``procedural_svg`` is a real, offline generator: palette boards, wordmarks,
sigils/monograms and packaging front panels rendered as SVG from the brand
system. External image models plug in through the same ``ImageProvider``
interface (configured via env; see docs/INTEGRATIONS.md) — they are registered as
planned until implemented, so nothing pretends to call an API it doesn't.
Text briefs (photography, packaging, landing page, ad concepts) are generated
from the brand system as structured text.
"""
from __future__ import annotations

import hashlib
import math
import os
from typing import Any, Protocol
from xml.sax.saxutils import escape

VISUAL_KINDS = ("palette_board", "wordmark", "sigil", "packaging_front")
BRIEF_KINDS = ("photography_brief", "packaging_brief", "landing_page", "ad_concepts", "brand_guidelines")

FONT_FOR = {"serif": "Georgia, 'Times New Roman', serif", "mono": "'Courier New', ui-monospace, monospace", "sans": "'Helvetica Neue', Arial, sans-serif"}


def _font(display: str) -> str:
    d = display.lower()
    if any(k in d for k in ("mono", "typewriter", "stencil", "terminal")):
        return FONT_FOR["mono"]
    if any(k in d for k in ("serif", "uncial", "inscription", "engraved", "blackletter", "capitals", "old-style", "slab", "wood-type")):
        return FONT_FOR["serif"]
    return FONT_FOR["sans"]


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16)


def _contrast_text(hexc: str) -> str:
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#f5f5f5"


class ImageProvider(Protocol):
    id: str

    def generate(self, kind: str, spec: dict[str, Any], variation: int = 0) -> dict[str, str]: ...


class ProceduralSVGProvider:
    id = "procedural_svg"

    def generate(self, kind: str, spec: dict[str, Any], variation: int = 0) -> dict[str, str]:
        fn = {"palette_board": self.palette_board, "wordmark": self.wordmark, "sigil": self.sigil, "packaging_front": self.packaging_front}[kind]
        return {"content": fn(spec, variation), "mime": "image/svg+xml", "provider": self.id}

    def palette_board(self, s: dict[str, Any], v: int) -> str:
        pal = s.get("palette") or ["#333333"]
        w = 120
        cells = "".join(
            f'<rect x="{i * w}" y="0" width="{w}" height="150" fill="{c}"/>'
            f'<text x="{i * w + 10}" y="138" font-family="{FONT_FOR["mono"]}" font-size="12" fill="{_contrast_text(c)}">{escape(c)}</text>'
            for i, c in enumerate(pal))
        typo = s.get("typography") or {}
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * len(pal)} 210" width="{w * len(pal)}" height="210">{cells}'
                f'<rect y="150" width="{w * len(pal)}" height="60" fill="#151515"/>'
                f'<text x="12" y="176" font-family="{_font(typo.get("display", ""))}" font-size="18" fill="#f0efec">{escape(s.get("name", ""))}</text>'
                f'<text x="12" y="198" font-family="{FONT_FOR["mono"]}" font-size="10" fill="#9a9a9a">'
                f'display: {escape(typo.get("display", "")[:40])} · text: {escape(typo.get("text", "")[:30])}</text></svg>')

    def wordmark(self, s: dict[str, Any], v: int) -> str:
        pal = s.get("palette") or ["#111111", "#f0f0f0", "#c9a227"]
        bg, fg, acc = pal[-1] if v % 2 else pal[0], None, pal[min(2, len(pal) - 1)]
        fg = _contrast_text(bg)
        name = escape((s.get("name") or "").upper() if v % 3 != 2 else s.get("name") or "")
        font = _font((s.get("typography") or {}).get("display", ""))
        spacing = [6, 2, 10][v % 3]
        orn = s.get("ornament", "rule")
        deco = {"rule": f'<line x1="60" y1="150" x2="540" y2="150" stroke="{acc}" stroke-width="2"/><line x1="60" y1="70" x2="540" y2="70" stroke="{acc}" stroke-width="1"/>',
                "brackets": f'<path d="M50 60 h-20 v100 h20 M550 60 h20 v100 h-20" stroke="{acc}" stroke-width="3" fill="none"/>',
                "orbit": f'<ellipse cx="300" cy="110" rx="270" ry="60" stroke="{acc}" stroke-width="1.5" fill="none"/>',
                "redaction": f'<rect x="330" y="132" width="170" height="14" fill="{fg}"/><text x="60" y="58" font-family="{FONT_FOR["mono"]}" font-size="11" fill="{acc}">FILE NO. {(_seed(name) % 9000) + 1000}</text>'}[orn]
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 220" width="600" height="220"><rect width="600" height="220" fill="{bg}"/>{deco}'
                f'<text x="300" y="122" text-anchor="middle" font-family="{font}" font-size="42" letter-spacing="{spacing}" fill="{fg}">{name}</text>'
                f'<text x="300" y="186" text-anchor="middle" font-family="{FONT_FOR["mono"]}" font-size="12" letter-spacing="3" fill="{acc}">'
                f'{escape((s.get("tagline") or "")[:60])}</text></svg>')

    def sigil(self, s: dict[str, Any], v: int) -> str:
        pal = s.get("palette") or ["#111111", "#f0f0f0", "#c9a227"]
        bg, line = pal[0], pal[min(2, len(pal) - 1)]
        if _contrast_text(bg) == "#111111" and _contrast_text(line) == "#111111":
            line = "#222222"
        r = _seed(s.get("name", ""), str(v))
        sides = 3 + r % 6
        rings = 1 + (r >> 4) % 3
        rays = (r >> 8) % 4 * 4
        geometry = s.get("geometry", "polygon")
        parts = [f'<rect width="300" height="300" fill="{bg}"/>']
        for i in range(rings):
            parts.append(f'<circle cx="150" cy="150" r="{120 - i * 18}" stroke="{line}" stroke-width="{2 if i == 0 else 1}" fill="none"/>')
        pts = " ".join(f"{150 + 85 * math.cos(2 * math.pi * k / sides - math.pi / 2):.1f},{150 + 85 * math.sin(2 * math.pi * k / sides - math.pi / 2):.1f}" for k in range(sides))
        parts.append(f'<polygon points="{pts}" stroke="{line}" stroke-width="2.5" fill="none"/>')
        if geometry == "grid":
            parts += [f'<line x1="{x}" y1="70" x2="{x}" y2="230" stroke="{line}" stroke-width="0.8" opacity=".5"/>' for x in range(90, 231, 35)]
        for k in range(rays):
            a = 2 * math.pi * k / max(1, rays)
            parts.append(f'<line x1="{150 + 95 * math.cos(a):.1f}" y1="{150 + 95 * math.sin(a):.1f}" x2="{150 + 122 * math.cos(a):.1f}" '
                         f'y2="{150 + 122 * math.sin(a):.1f}" stroke="{line}" stroke-width="1.5"/>')
        initial = escape((s.get("name") or "?")[0].upper())
        parts.append(f'<text x="150" y="168" text-anchor="middle" font-family="{_font((s.get("typography") or {}).get("display", ""))}" '
                     f'font-size="54" fill="{line}">{initial}</text>')
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300" width="300" height="300">{"".join(parts)}</svg>'

    def packaging_front(self, s: dict[str, Any], v: int) -> str:
        pal = s.get("palette") or ["#222222", "#eeeeee", "#c9a227"]
        bg, acc = pal[v % len(pal)], pal[(v + 2) % len(pal)]
        fg = _contrast_text(bg)
        font = _font((s.get("typography") or {}).get("display", ""))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480" width="360" height="480"><rect width="360" height="480" fill="{bg}"/>'
                f'<rect x="18" y="18" width="324" height="444" fill="none" stroke="{acc}" stroke-width="2"/>'
                f'<text x="180" y="120" text-anchor="middle" font-family="{font}" font-size="30" fill="{fg}">{escape(s.get("name", ""))}</text>'
                f'<text x="180" y="150" text-anchor="middle" font-family="{FONT_FOR["mono"]}" font-size="11" fill="{acc}">{escape((s.get("product") or "")[:40])}</text>'
                f'<rect x="60" y="190" width="240" height="160" fill="none" stroke="{fg}" stroke-dasharray="4 4" opacity=".6"/>'
                f'<text x="180" y="275" text-anchor="middle" font-family="{FONT_FOR["mono"]}" font-size="10" fill="{fg}" opacity=".7">PRODUCT WINDOW / ILLUSTRATION</text>'
                f'<text x="34" y="440" font-family="{FONT_FOR["mono"]}" font-size="9" fill="{fg}" opacity=".8">GPSR: manufacturer · EU responsible person · product ID · warnings</text>'
                f'</svg>')


PROVIDERS: dict[str, ImageProvider] = {"procedural_svg": ProceduralSVGProvider()}
EXTERNAL_PROVIDERS = [  # planned adapters — configured but not implemented (no live calls are made)
    {"id": "openai_images", "env": "OPENAI_API_KEY", "state": "planned"},
    {"id": "stability_ai", "env": "STABILITY_API_KEY", "state": "planned"},
    {"id": "replicate", "env": "REPLICATE_API_TOKEN", "state": "planned"},
]


def provider_status() -> list[dict[str, Any]]:
    return [{"id": "procedural_svg", "state": "configured", "env": None}] + [
        {**p, "credentials_present": bool(os.getenv(p["env"]))} for p in EXTERNAL_PROVIDERS]


def ornament_for(genres: list[str]) -> tuple[str, str]:
    g = set(genres)
    if g & {"secret_archive", "surveillance_dystopia"}:
        return "redaction", "grid"
    if g & {"celestial_cartography", "sacred_geometry", "alchemy_hermetic", "techno_occult"}:
        return "orbit", "polygon"
    if g & {"tactical_utility", "industrial", "brutalism", "cyberpunk"}:
        return "brackets", "grid"
    return "rule", "polygon"


def brief(kind: str, s: dict[str, Any]) -> str:
    d = s.get("direction") or {}
    name, product = s.get("name", ""), s.get("product", "")
    if kind == "photography_brief":
        return (f"PHOTOGRAPHY BRIEF — {name}\nStyle: {d.get('photography_style', '')}\nShots: hero on neutral ground; in real use (real weather); "
                f"detail macro of {', '.join((d.get('materials_textures') or [])[:2])}; scale shot with hands.\n"
                "Rules: no staged claims (e.g. submersion) unless the product is rated for it; real users only with written consent.")
    if kind == "packaging_brief":
        return (f"PACKAGING BRIEF — {name}\nDirection: {d.get('packaging_style', '')}\nPalette: {', '.join(d.get('color_palette', []))}\n"
                "Must include: product identifier, manufacturer + EU responsible person, warnings in Swedish (GPSR), recycling marks; "
                "minimise mixed materials (packaging producer responsibility).")
    if kind == "landing_page":
        return (f"LANDING PAGE — {name} / {product}\nLanguage: {d.get('website_language', '')}\nSections: hero (one claim we can prove) → problem → "
                "how it works → spec table → verified compatibility list (if any) → FAQ (returns, 14-day withdrawal) → company details.\n"
                "No countdown timers or fake scarcity; reference prices only per Omnibus rule.")
    if kind == "ad_concepts":
        return (f"AD CONCEPTS — {name}\nDirection: {d.get('advertising_direction', '')}\n1) Problem → product demo in real conditions.\n"
                "2) Spec-overlay teardown.\n3) Story-world teaser (fiction clearly fiction).\nNo testimonials unless real and consented; no invented reviews.")
    if kind == "brand_guidelines":
        t = d.get("typography") or {}
        return (f"BRAND GUIDELINES — {name}\nPrimary genre: {d.get('primary_genre', '')} · Secondary: {d.get('secondary_genre', '')}\n"
                f"Visual direction: {d.get('visual_direction', '')}\nColour: {', '.join(d.get('color_palette', []))}\n"
                f"Type: display {t.get('display', '')}; text {t.get('text', '')}\nMaterials: {', '.join(d.get('materials_textures', []))}\n"
                f"Social: {d.get('social_identity', '')}\nVoice: specific, testable, no buzzwords.")
    raise ValueError(kind)


def generate(kind: str, spec: dict[str, Any], provider: str = "procedural_svg", variation: int = 0) -> dict[str, str]:
    if kind in BRIEF_KINDS:
        return {"content": brief(kind, spec), "mime": "text/plain", "provider": "template"}
    if provider not in PROVIDERS:
        raise LookupError(f"image provider '{provider}' is not implemented (see docs/INTEGRATIONS.md)")
    return PROVIDERS[provider].generate(kind, spec, variation)
