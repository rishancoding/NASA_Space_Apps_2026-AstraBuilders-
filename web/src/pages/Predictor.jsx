import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { Card, CoverageBadge, ErrorBox, Select, Slider, Spinner, Toggle, Value, Warning, fmt, useAsync, useDebounced } from "../components/ui.jsx";

export default function Predictor({ options, openExperiment, askChat }) {
  const flex = options.flex;
  const [fuel, setFuel] = useState(flex.fuels[0]);
  const [vals, setVals] = useState(() => Object.fromEntries(flex.fields.map((f) => [f.name, f.default])));
  const [vary, setVary] = useState("oxygen_pct");
  const [model, setModel] = useState("extinction");
  const body = useDebounced({ fuel, ...vals }, 180);
  const key = JSON.stringify(body);

  const ext = useAsync(() => api.predictExtinction(body), [key]);
  const burn = useAsync(() => api.predictBurnTime(body), [key]);
  const curve = useAsync(() => api.whatIf({ ...body, model, vary, points: 40 }), [key, model, vary]);
  const fieldErrors = Object.fromEntries((ext.error?.errors || []).filter((e) => e.field).map((e) => [e.field, e.message]));
  const nitrogen = 1 - (vals.oxygen_pct || 0) / 100 - (vals.co2_fraction || 0) - (vals.helium_fraction || 0);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-white">Atmosphere Predictor</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          How does the cabin atmosphere change whether a liquid fuel flame goes out on its own, and how long it burns?
          Trained on NASA's FLEX droplet experiments on the ISS (PSI-69). Liquid droplets only — not solid materials.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <Card title="Atmosphere and fuel" className="h-fit space-y-4">
          <Select label="Fuel" value={fuel} onChange={(v) => setFuel(v || flex.fuels[0])} options={flex.fuels} />
          {flex.fields.map((f) => {
            const [lo, hi] = f.tested_range_by_fuel[fuel];
            return (
              <Slider key={f.name} label={f.label} unit={f.unit === "mole fraction" ? "frac" : f.unit} value={vals[f.name]}
                min={f.min} max={f.max} step={f.step} onChange={(v) => setVals((s) => ({ ...s, [f.name]: v }))}
                hint={`Tested for ${fuel}: ${fmt(lo)}–${fmt(hi)}`} error={fieldErrors[f.name]} />
            );
          })}
          <div className={`text-xs ${nitrogen < 0 ? "text-red-300" : "text-slate-400"}`}>Nitrogen (the remainder): {fmt(Math.max(nitrogen, 0))}</div>
        </Card>

        <div className="space-y-4">
          <ErrorBox error={ext.error} />
          <div className="grid gap-4 md:grid-cols-2">
            <ResultCard title="Chance the flame goes out early" r={ext.data} valueKey="probability_extinction"
              extra={ext.data?.compared_with_typical && <div className="text-xs text-slate-300">{ext.data.compared_with_typical.label}</div>} />
            <ResultCard title="How long it burns" r={burn.data} valueKey="burn_time_s" />
          </div>
          {[...(ext.data?.warnings || [])].map((w, i) => <Warning key={i}>{w.message}</Warning>)}

          <Card title="What if one input changes?" subtitle="The line is the model; dots are real NASA tests (which differ in other inputs too). Grey areas are untested."
            right={<div className="flex flex-wrap gap-2">
              <Toggle value={model} onChange={setModel} options={[{ value: "extinction", label: "Extinction" }, { value: "burn_time", label: "Burn time" }]} />
              <select value={vary} onChange={(e) => setVary(e.target.value)} className="rounded-md border border-line bg-ink px-2 text-sm text-slate-100">
                {flex.fields.map((f) => <option key={f.name} value={f.name}>{f.label}</option>)}
              </select>
            </div>}>
            {curve.loading && !curve.data && <Spinner />}
            <ErrorBox error={curve.error} />
            {curve.data && <WhatIfChart d={curve.data} current={vals[vary]} />}
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            {ext.data?.available && <Factors f={ext.data.factors} title="What drives the extinction estimate" />}
            {ext.data && <Nearest n={ext.data.nearest_tests} openExperiment={openExperiment} />}
          </div>
          <button onClick={() => askChat({ page: "atmosphere_predictor", inputs: body, extinction: ext.data?.probability_extinction, burn_time: burn.data?.burn_time_s })}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-slate-300 hover:border-flame hover:text-white">
            Ask the assistant to explain this result
          </button>
        </div>
      </div>
    </div>
  );
}

function ResultCard({ title, r, valueKey, extra }) {
  return (
    <Card title={title}>
      {!r ? <Spinner /> : r.available ? (
        <div className="space-y-2">
          <Value v={r[valueKey]} big />
          {extra}
          <div className="text-[11px] text-slate-500">{r[valueKey].note}</div>
        </div>
      ) : (
        <div className="space-y-2 text-sm">
          <div className="text-amber-200">No estimate: {r.reason}</div>
          {r.out_of_range?.map((o) => <div key={o.field} className="text-xs text-slate-400">{o.message}</div>)}
          <div className="text-xs text-slate-500">See the nearest real tests below instead.</div>
        </div>
      )}
    </Card>
  );
}

function WhatIfChart({ d, current }) {
  const isProb = d.y_unit === "probability";
  const data = useMemo(() => d.curve.map((p) => ({ x: p.x, y: p.y, band: p.low != null ? [p.low, p.high] : null })), [d]);
  const real = d.real_tests.map((t) => ({ x: t.x, real: isProb ? (t.y === 1 ? 1 : 0) : t.y, outcome: t.outcome }));
  const [lo, hi] = d.tested_range;
  const xs = d.curve.map((p) => p.x);
  return (
    <div className="h-80">
      <ResponsiveContainer>
        <ComposedChart margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
          <CartesianGrid stroke="#24304a" strokeDasharray="3 3" />
          <XAxis type="number" dataKey="x" domain={[Math.min(...xs), Math.max(...xs)]} tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickFormatter={(v) => fmt(v)} label={{ value: `${d.label}${d.unit ? ` (${d.unit})` : ""}`, position: "bottom", fill: "#94a3b8", fontSize: 12 }} allowDuplicatedCategory={false} />
          <YAxis domain={isProb ? [0, 1] : ["auto", "auto"]} tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickFormatter={(v) => (isProb ? `${Math.round(v * 100)}%` : fmt(v))} />
          <Tooltip contentStyle={{ background: "#121a2b", border: "1px solid #24304a", fontSize: 12 }}
            formatter={(v, name) => (Array.isArray(v) ? `${fmt(v[0], d.y_unit)}–${fmt(v[1], d.y_unit)}` : isProb ? fmt(v, "probability") : fmt(v)) + (name === "real" ? "" : "")}
            labelFormatter={(v) => `${d.label}: ${fmt(v)}`} />
          <Legend verticalAlign="top" height={24} wrapperStyle={{ fontSize: 12 }} />
          <ReferenceArea x1={Math.min(...xs)} x2={lo} fill="#64748b" fillOpacity={0.12} />
          <ReferenceArea x1={hi} x2={Math.max(...xs)} fill="#64748b" fillOpacity={0.12} />
          <Area data={data} dataKey="band" name="model range" stroke="none" fill="#a78bfa" fillOpacity={0.2} connectNulls={false} isAnimationActive={false} />
          <Line data={data} dataKey="y" name={d.y_label} stroke="#a78bfa" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
          <Scatter data={real} dataKey="real" name={isProb ? "NASA tests (1 = went out, 0 = burned out)" : "NASA tests"} fill="#38bdf8" fillOpacity={0.6} isAnimationActive={false} />
          {current != null && <ReferenceLine x={current} stroke="#ff7a1a" strokeDasharray="4 4" label={{ value: "you", fill: "#ff7a1a", fontSize: 11 }} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Factors({ f, title }) {
  const max = Math.max(...f.items.map((i) => Math.abs(i.effect)), 1);
  return (
    <Card title={title} subtitle={f.method}>
      <ul className="space-y-2 text-xs">
        {f.items.map((i) => (
          <li key={i.feature}>
            <div className="flex justify-between text-slate-300">
              <span>{i.label}: {fmt(i.your_value)} <span className="text-slate-500">(typical {fmt(i.typical_value)})</span></span>
              <span className={i.effect > 0 ? "text-red-300" : "text-emerald-300"}>{i.effect > 0 ? "+" : ""}{fmt(i.effect)} pts</span>
            </div>
            <div className="mt-1 h-1.5 rounded bg-ink">
              <div className={`h-1.5 rounded ${i.effect > 0 ? "bg-red-400/70" : "bg-emerald-400/70"}`} style={{ width: `${(Math.abs(i.effect) / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Nearest({ n, openExperiment }) {
  return (
    <Card title="Closest real NASA tests" right={<CoverageBadge coverage={n.coverage} />}>
      <ul className="space-y-1 text-xs">
        {n.matches.map((m) => (
          <li key={m.experiment_id}>
            <button onClick={() => openExperiment(m.experiment_id)} className="w-full rounded px-1.5 py-1 text-left hover:bg-white/5">
              <span className="text-sky-300">FLEX test {m.test_id}</span>
              <span className="text-slate-400"> · {fmt(m.oxygen_pct.value)}% O₂ · {fmt(m.pressure_kpa.value)} kPa · {fmt(m.droplet_diameter_mm.value)} mm · {m.outcome.label}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
