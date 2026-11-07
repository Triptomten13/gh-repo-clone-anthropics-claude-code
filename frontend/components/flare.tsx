"use client";
import { useMemo } from "react";
import { useApi } from "@/lib/hooks";
import { svgSrc } from "@/lib/flare";
import { DemoBadge } from "./ui";

export function ProductPicker({ value, onChange, filter }: { value: number | null; onChange: (id: number) => void; filter?: (p: any) => boolean }) {
  const prods = useApi<any[]>("/api/products?sort=opportunity_score");
  const list = (prods.data ?? []).filter(filter ?? (() => true));
  return (
    <select value={value ?? ""} onChange={(e) => onChange(Number(e.target.value))} className="min-w-72">
      <option value="">select a product…</option>
      {list.map((p) => <option key={p.id} value={p.id}>{p.name}{p.is_demo ? " · DEMO" : ""}{p.opportunity_score != null ? ` · ${p.opportunity_score.toFixed(0)}` : ""}</option>)}
    </select>
  );
}

export function Swatches({ colors, size = 18 }: { colors: string[]; size?: number }) {
  return (
    <span className="inline-flex overflow-hidden rounded border border-line-strong">
      {colors.map((c, i) => <span key={i} title={c} style={{ background: c, width: size, height: size }} />)}
    </span>
  );
}

/** Generated SVG assets are rendered through <img> so any markup can never execute. */
export function SvgAsset({ svg, alt, className = "" }: { svg: string; alt: string; className?: string }) {
  return <img src={svgSrc(svg)} alt={alt} className={`rounded border border-line bg-black/20 ${className}`} />;
}

const KIND_COLOR: Record<string, string> = {
  existing: "#a78bfa", product: "#a78bfa", base: "#a78bfa", domain: "#3987e5", module: "#199e70", document: "#22d3ee",
};

/** Radial relationship graph: centre node, first ring = direct relations, second ring = their children. */
export function GraphView({ nodes, edges, height = 420 }: { nodes: { key: string; label: string; kind: string; data?: any }[]; edges: { source: string; target: string; relation: string }[]; height?: number }) {
  const layout = useMemo(() => {
    if (!nodes.length) return { pos: {} as Record<string, [number, number]>, w: 800 };
    const w = 860, cx = w / 2, cy = height / 2;
    const centre = nodes.find((n) => n.key === "base" || n.key === "product") ?? nodes[0];
    const first = edges.filter((e) => e.source === centre.key).map((e) => e.target);
    const second = nodes.filter((n) => n.key !== centre.key && !first.includes(n.key)).map((n) => n.key);
    const pos: Record<string, [number, number]> = { [centre.key]: [cx, cy] };
    const single = nodes.length - 1 === first.length;  // star graph: use the whole canvas
    const rx = single ? w / 2 - 110 : 150, ry = single ? height / 2 - 40 : height / 2 - 70;
    first.forEach((k, i) => { const a = (2 * Math.PI * i) / Math.max(1, first.length) - Math.PI / 2; pos[k] = [cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]; });
    second.forEach((k, i) => {
      const parent = edges.find((e) => e.target === k)?.source;
      const base = parent && pos[parent] ? Math.atan2(pos[parent][1] - cy, pos[parent][0] - cx) : (2 * Math.PI * i) / Math.max(1, second.length);
      const sib = edges.filter((e) => e.source === parent).map((e) => e.target).filter((x) => second.includes(x));
      const j = sib.indexOf(k), off = (j - (sib.length - 1) / 2) * 0.32;
      pos[k] = [cx + Math.cos(base + off) * 330, cy + Math.sin(base + off) * (height / 2 - 24)];
    });
    return { pos, w };
  }, [nodes, edges, height]);
  if (!nodes.length) return null;
  const color = (n: any) => KIND_COLOR[n.kind] ?? "#c3c2b7";
  return (
    <svg viewBox={`0 0 ${layout.w} ${height}`} className="w-full" role="img" aria-label="relationship graph">
      {edges.map((e, i) => {
        const a = layout.pos[e.source], b = layout.pos[e.target];
        if (!a || !b) return null;
        return <g key={i}><line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#3d3c38" strokeWidth={1.2} />
          <title>{`${e.source} → ${e.target}: ${e.relation}`}</title></g>;
      })}
      {nodes.map((n) => {
        const p = layout.pos[n.key];
        if (!p) return null;
        const isCentre = n.key === "base" || n.key === "product";
        return (
          <g key={n.key}>
            <circle cx={p[0]} cy={p[1]} r={isCentre ? 11 : 7} fill={color(n)} stroke="#1a1a19" strokeWidth={2} />
            <text x={p[0]} y={p[1] + (isCentre ? 26 : 19)} textAnchor="middle" fontSize={10.5} fill="#c3c2b7">
              {n.label.length > 34 ? n.label.slice(0, 32) + "…" : n.label}
            </text>
            <title>{`${n.label} (${n.kind})${n.data?.status ? ` — ${n.data.status}` : ""}`}</title>
          </g>
        );
      })}
    </svg>
  );
}

export function ConceptCard({ c, selected, onSelect, onOpen }: { c: any; selected?: boolean; onSelect?: () => void; onOpen?: () => void }) {
  const orig = c.originality?.score;
  const flags = (c.originality?.flags ?? []).filter((f: any) => f.severity === "block");
  return (
    <div className={`rounded-lg border p-3 ${selected ? "border-violet" : "border-line"} bg-bg/50`}>
      <div className="flex items-start justify-between gap-2">
        <button onClick={onOpen} className="text-left">
          <div className="text-[14px] font-semibold hover:text-violet">{c.name}<span className="ml-1.5 text-[11px] font-normal text-ink-3">v{c.version}</span></div>
          <div className="text-[12px] text-ink-3">{c.tagline}</div>
        </button>
        {onSelect && <input type="checkbox" aria-label="compare" checked={!!selected} onChange={onSelect} />}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-ink-3">
        <Swatches colors={c.direction?.color_palette ?? []} size={14} />
        <span>{c.primary_genre?.replaceAll("_", " ")} × {c.secondary_genre?.replaceAll("_", " ")}</span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
        <span className={`rounded border px-1.5 py-px ${orig >= 70 ? "border-good/40 text-[#5fd35f]" : orig >= 55 ? "border-warning/40 text-warning" : "border-critical/50 text-[#f08a8a]"}`}>originality {orig?.toFixed?.(0) ?? "—"}</span>
        <span className="rounded border border-line-strong px-1.5 py-px text-ink-2">{c.status}</span>
        <span className="text-ink-3">by {c.author_persona}</span>
        {flags.length > 0 && <span className="text-[#f08a8a]">{flags.length} blocking flag(s)</span>}
        <DemoBadge show={false} />
      </div>
    </div>
  );
}
