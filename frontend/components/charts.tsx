"use client";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from "recharts";

const AXIS = { stroke: "#3d3c38", tick: { fill: "#8c8b84", fontSize: 11 }, tickLine: false };
const TOOLTIP = {
  contentStyle: { background: "#222220", border: "1px solid #3d3c38", borderRadius: 6, fontSize: 12, color: "#f0efec" },
  labelStyle: { color: "#c3c2b7" },
  cursor: { stroke: "#5a5852", strokeWidth: 1 },
};
const kSek = (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v.toFixed(0)}`);

/** Daily revenue vs profit — same unit (SEK), one axis. Legend + direct end labels. */
export function RevenueProfitChart({ data }: { data: { date: string; revenue: number; profit: number }[] }) {
  const last = data[data.length - 1];
  return (
    <div>
      <div className="mb-2 flex gap-4 text-[11.5px] text-ink-2">
        <span className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-4 bg-series-1" />Revenue (SEK/day)</span>
        <span className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-4 bg-series-3" />Profit after recorded costs (SEK/day)</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 8, right: 64, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#2e2d2a" vertical={false} />
          <XAxis dataKey="date" {...AXIS} tickFormatter={(d: string) => d.slice(5)} minTickGap={24} />
          <YAxis {...AXIS} width={44} tickFormatter={kSek} />
          <Tooltip {...TOOLTIP} formatter={(v) => `${Number(v).toLocaleString("sv-SE")} kr`} />
          <Line type="monotone" dataKey="revenue" name="Revenue" stroke="#3987e5" strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: "#1a1a19", strokeWidth: 2 }}
            label={(p: any) => p.index === data.length - 1 ? <text x={p.x + 6} y={p.y} dy={4} fill="#c3c2b7" fontSize={11}>{kSek(last.revenue)} rev</text> : <g />} />
          <Line type="monotone" dataKey="profit" name="Profit" stroke="#199e70" strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: "#1a1a19", strokeWidth: 2 }}
            label={(p: any) => p.index === data.length - 1 ? <text x={p.x + 6} y={p.y} dy={4} fill="#c3c2b7" fontSize={11}>{kSek(last.profit)} profit</text> : <g />} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Horizontal bars, single series: velocity score 0–100 per trend. */
export function VelocityBars({ data }: { data: { keyword: string; velocity_score: number; stage: string }[] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(120, data.length * 30 + 20)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 36, bottom: 0, left: 0 }} barCategoryGap={6}>
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis type="category" dataKey="keyword" {...AXIS} width={110} axisLine={false} />
        <Tooltip {...TOOLTIP} cursor={{ fill: "#2e2d2a55" }} formatter={(v, _n, p: any) => [`${v} · ${p.payload.stage}`, "Velocity"]} />
        <Bar dataKey="velocity_score" radius={[0, 4, 4, 0]} barSize={14}
          label={{ position: "right", fill: "#c3c2b7", fontSize: 11 }}>
          {data.map((d, i) => <Cell key={i} fill="#3987e5" fillOpacity={d.stage === "declining" ? 0.45 : 1} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Score components: weighted contribution per component (single series). */
export function ScoreComponents({ components }: { components: Record<string, { score: number; weight: number; weighted: number; coverage: number }> }) {
  const data = Object.entries(components).filter(([k]) => !k.startsWith("_")).map(([k, v]) => ({ name: k.replaceAll("_", " "), ...v }));
  return (
    <ResponsiveContainer width="100%" height={data.length * 28 + 10}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 44, bottom: 0, left: 0 }}>
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis type="category" dataKey="name" {...AXIS} width={150} axisLine={false} />
        <Tooltip {...TOOLTIP} cursor={{ fill: "#2e2d2a55" }}
          formatter={(v, _n, p: any) => [`${v} (weight ${(p.payload.weight * 100).toFixed(0)}%, data coverage ${(p.payload.coverage * 100).toFixed(0)}%)`, "Component score"]} />
        <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={12} label={{ position: "right", fill: "#c3c2b7", fontSize: 11 }}>
          {data.map((d, i) => <Cell key={i} fill="#a78bfa" fillOpacity={0.35 + 0.65 * d.coverage} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
