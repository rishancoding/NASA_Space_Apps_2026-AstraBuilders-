import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { Card, CoverageBadge, ErrorBox, Select, Slider, Spinner, Toggle, Value, Warning, fmt, useAsync, useDebounced } from "../components/ui.jsx";

function initialScenario(flex, fuel, family = "Oxygen + nitrogen") {
  return flex.scenarios.find((s) => s.inputs.fuel === fuel && s.gas_family === family)
    || flex.scenarios.find((s) => s.inputs.fuel === fuel);
}

export default function Predictor({ options, openExperiment, askChat }) {
  const flex = options.flex;
  const first = initialScenario(flex, flex.fuels[0]);
  const [anchor, setAnchor] = useState(first);
  const [vals, setVals] = useState(first.inputs);
  const [vary, setVary] = useState("oxygen_pct");
  const [model, setModel] = useState("extinction");
  const rawKey = JSON.stringify(vals);
  const body = useDebounced(vals, 180);
  const key = JSON.stringify(body);
  const pending = rawKey !== key;
  const controls = useAsync(() => api.predictionControls(vals), [rawKey]);
  const ext = useAsync(() => api.predictExtinction(body), [key]);
  const burn = useAsync(() => api.predictBurnTime(body), [key]);
  const curve = useAsync(() => api.whatIf({ ...body, model, vary, points: 40 }), [key, model, vary]);
  const families = [...new Set(flex.scenarios.filter((s) => s.inputs.fuel === vals.fuel).map((s) => s.gas_family))];
  const scenarios = flex.scenarios.filter((s) => s.inputs.fuel === vals.fuel && s.gas_family === anchor.gas_family);
  const choose = (s) => { setAnchor(s); setVals({ ...s.inputs }); };
  const nitrogen = 1 - vals.oxygen_pct / 100 - vals.co2_fraction - vals.helium_fraction;
  const support = controls.data?.support;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><div className="eyebrow mb-2">02 / Explore a supported estimate</div><h1 className="text-2xl font-semibold tracking-tight text-white">Atmosphere Predictor</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">Start with a real FLEX test, then adjust nearby conditions. Liquid fuel droplets in microgravity only.</p></div>
        <span className="rounded-full border border-violet-400/30 bg-violet-400/10 px-3 py-1.5 text-xs text-violet-200">Exploratory model · PSI-69</span>
      </div>
      <div className="grid items-start gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card title="Build your scenario" subtitle="Settings adapt to the current fuel and gas mixture." className="space-y-5">
          <Toggle value={vals.fuel} onChange={(fuel) => choose(initialScenario(flex, fuel))} options={flex.fuels.map((f) => ({ value: f, label: f }))} />
          <Select label="Gas mixture" value={anchor.gas_family} onChange={(family) => choose(initialScenario(flex, vals.fuel, family))} options={families} />
          <Select label="Starting NASA test" value={anchor.experiment_id} onChange={(id) => choose(scenarios.find((s) => s.experiment_id === id))}
            options={scenarios.map((s) => ({ value: s.experiment_id, label: `Test ${s.test_id} · ${fmt(s.inputs.oxygen_pct)}% O₂ · ${fmt(s.inputs.pressure_kpa)} kPa` }))} />
          <div className="border-t border-line pt-4">
            <div className="mb-3 flex items-center justify-between"><span className="eyebrow">Fine-tune nearby</span><button className="text-xs text-cyan-200 hover:underline" onClick={() => setVals({ ...anchor.inputs })}>Reset to test</button></div>
            <div className="space-y-4" aria-busy={controls.loading}>
              {flex.fields.filter((f) => f.unit !== "mole fraction" || vals[f.name] > 0).map((f) => <SupportedControl key={f.name} field={f} value={vals[f.name]} settings={controls.data?.fields.find((c) => c.name === f.name)?.values || []}
                disabled={controls.loading || pending} onChange={(v) => setVals((s) => ({ ...s, [f.name]: v }))} />)}
            </div>
          </div>
          <ErrorBox error={controls.error} />
          <div className="rounded-xl border border-cyan-300/15 bg-cyan-300/5 p-3 text-xs leading-relaxed text-slate-300">
            <div className="flex flex-wrap justify-between gap-2 font-mono text-cyan-100"><span>N₂ {fmt(nitrogen * 100)}%</span><span>CO₂ {fmt(vals.co2_fraction * 100)}%</span><span>He {fmt(vals.helium_fraction * 100)}%</span></div>
            <p className="mt-1 text-slate-400">Only settings with at least three nearby screened sample groups are selectable. Nearby tests do not guarantee accuracy.</p>
          </div>
          <button className="primary-button w-full" onClick={() => openExperiment(anchor.experiment_id)}>Inspect starting NASA test ↗</button>
        </Card>
        <div className="min-w-0 space-y-4">
          <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-panel/60 px-4 py-3 text-xs">
            <span className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${support?.supported ? "bg-cyan-300" : "bg-amber-300"}`} />{controls.loading ? "Checking nearby evidence…" : support?.supported ? `${support.nearby_groups} nearby NASA sample groups` : "Coverage check unavailable"}</span>
            <span className="text-slate-400">Same fuel · same gas family</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <ResultCard title="Recorded Extinction probability" r={ext.data} error={ext.error} loading={ext.loading || pending} valueKey="probability_extinction"
              extra={ext.data?.compared_with_typical && <div className="text-xs text-slate-300">{ext.data.compared_with_typical.label}</div>} />
            <ResultCard title="Estimated recorded burn time" r={burn.data} error={burn.error} loading={burn.loading || pending} valueKey="burn_time_s" />
          </div>
          {(ext.data?.warnings || []).map((w, i) => <Warning key={i}>{w.message}</Warning>)}
          <Card title="Change one condition" subtitle="The line is an estimate; dots are screened NASA observations with other inputs that may differ. Gaps indicate unsupported combinations."
            right={<div className="flex flex-wrap gap-2">
              <Toggle value={model} onChange={setModel} options={[{ value: "extinction", label: "Extinction" }, { value: "burn_time", label: "Burn time" }]} />
              <select aria-label="Condition to vary" value={vary} onChange={(e) => setVary(e.target.value)} className="rounded-md border border-line bg-ink px-2 text-sm text-slate-100">
                {flex.fields.map((f) => <option key={f.name} value={f.name}>{f.label}</option>)}
              </select>
            </div>}>
            {(curve.loading || pending) && <Spinner label="Checking supported curve…" />}
            <ErrorBox error={curve.error} />
            {!pending && curve.data && <WhatIfChart d={curve.data} current={vals[vary]} />}
          </Card>
          <div className="grid gap-4 xl:grid-cols-2">
            {!pending && ext.data?.available && <Factors f={ext.data.factors} title="How inputs affect the estimate" />}
            {!pending && ext.data && <Nearest n={ext.data.nearest_tests} openExperiment={openExperiment} />}
          </div>
          <button disabled={pending || ext.loading} onClick={() => askChat({ page: "atmosphere_predictor", inputs: body, extinction: ext.data, burn_time: burn.data })} className="primary-button">Explain these results with the assistant ↗</button>
        </div>
      </div>
    </div>
  );
}

function SupportedControl({ field, value, settings, disabled, onChange }) {
  const fraction = field.unit === "mole fraction";
  const unit = fraction ? "%" : field.unit;
  const display = (v) => fmt(fraction ? v * 100 : v);
  const index = settings.reduce((best, v, i) => Math.abs(v - value) < Math.abs(settings[best] - value) ? i : best, 0);
  const fixed = settings.length <= 1;
  return <div>
    <div className="flex items-center justify-between gap-3 text-xs"><span className="text-slate-300">{field.label.replace(" fraction", "")}</span><output className="rounded-md border border-line bg-ink/80 px-2 py-1 font-mono text-cyan-100">{display(value)} <span className="text-slate-400">{unit}</span></output></div>
    <input aria-label={field.label} aria-valuetext={`${display(value)} ${unit}`} type="range" min={0} max={Math.max(1, settings.length - 1)} step={1} value={index}
      disabled={disabled || fixed} onChange={(e) => onChange(settings[Number(e.target.value)])} className="mt-1 w-full disabled:opacity-30" />
    <div className="flex justify-between text-[10px] text-slate-400">{fixed ? <span>{disabled ? "Checking settings…" : "Fixed for this gas mixture / nearby coverage"}</span> : <><span>{display(settings[0])} {unit}</span><span>{display(settings.at(-1))} {unit}</span></>}</div>
  </div>;
}

function ResultCard({ title, r, valueKey, extra, loading, error }) {
  return <Card title={title} className="result-number border-t-cyan-300/35">
    {loading ? <div className="py-5"><Spinner label="Updating estimate…" /></div> : error ? <ErrorBox error={error} /> : r?.available ? (
      <div className="space-y-3"><Value v={r[valueKey]} big />{extra}<div className="text-xs leading-relaxed text-slate-400">{r[valueKey].note}</div></div>
    ) : <div className="space-y-2 text-sm"><div className="text-amber-200">Estimate unavailable</div><p className="text-slate-300">{r?.reason || "Select a supported NASA starting test."}</p><p className="text-xs text-slate-400">Use the real tests below to review available evidence.</p></div>}
  </Card>;
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
          <Area data={data} dataKey="band" name="model range" stroke="none" fill="#66dce8" fillOpacity={0.2} connectNulls={false} isAnimationActive={false} />
          <Line data={data} dataKey="y" name={d.y_label} stroke="#66dce8" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
          <Scatter data={real} dataKey="real" name={isProb ? "NASA tests (1 = Extinction, 0 = Completion)" : "NASA tests"} fill="#38bdf8" fillOpacity={0.6} isAnimationActive={false} />
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
      <p className="mb-3 text-xs text-slate-400">Model sensitivity, not a causal effect. Unsupported comparisons are omitted.</p>
      <ul className="space-y-2 text-xs">
        {f.items.map((i) => (
          <li key={i.feature}>
            <div className="flex justify-between text-slate-300">
              <span>{i.label}: {fmt(i.your_value)} <span className="text-slate-500">(typical {fmt(i.typical_value)})</span></span>
              <span className={i.effect > 0 ? "text-cyan-200" : "text-violet-200"}>{i.effect > 0 ? "+" : ""}{fmt(i.effect)} pts</span>
            </div>
            <div className="mt-1 h-1.5 rounded bg-ink">
              <div className={`h-1.5 rounded ${i.effect > 0 ? "bg-cyan-300/70" : "bg-violet-400/70"}`} style={{ width: `${(Math.abs(i.effect) / max) * 100}%` }} />
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
