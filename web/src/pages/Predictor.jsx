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
      <div className="page-heading flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-semibold tracking-tight text-gray-900">Atmosphere Predictor</h1>
          <p className="mt-2 text-sm text-gray-500">Explore fuel droplets in microgravity.</p></div>
        <span className="rounded-md border border-indigo-200 bg-indigo-50 px-2 py-1 text-[11px] text-indigo-700">Model estimates</span>
      </div>
      <div className="grid items-start gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card title="Your conditions" className="space-y-5">
          <Toggle value={vals.fuel} onChange={(fuel) => choose(initialScenario(flex, fuel))} options={flex.fuels.map((f) => ({ value: f, label: f }))} />
          <Select label="Gas mixture" value={anchor.gas_family} onChange={(family) => choose(initialScenario(flex, vals.fuel, family))} options={families} />
          <Select label="Starting NASA test" value={anchor.experiment_id} onChange={(id) => choose(scenarios.find((s) => s.experiment_id === id))}
            options={scenarios.map((s) => ({ value: s.experiment_id, label: `Test ${s.test_id} · ${fmt(s.inputs.oxygen_pct)}% O₂ · ${fmt(s.inputs.pressure_kpa)} kPa` }))} />
          <div className="border-t border-line pt-4">
            <div className="mb-3 flex items-center justify-between"><span className="eyebrow">Fine-tune nearby</span><button className="text-xs text-indigo-700 hover:underline" onClick={() => setVals({ ...anchor.inputs })}>Reset to test</button></div>
            <div className="space-y-4" aria-busy={controls.loading}>
              {flex.fields.filter((f) => (f.unit !== "mole fraction" || vals[f.name] > 0) && (controls.loading || (controls.data?.fields.find((c) => c.name === f.name)?.values || []).length > 1)).map((f) => <SupportedControl key={f.name} field={f} value={vals[f.name]} settings={controls.data?.fields.find((c) => c.name === f.name)?.values || []}
                disabled={controls.loading || pending} onChange={(v) => setVals((s) => ({ ...s, [f.name]: v }))} />)}
            </div>
          </div>
          <ErrorBox error={controls.error} />
          <details className="border-t border-line pt-3"><summary>Mixture & fixed settings</summary><div className="space-y-3 text-xs text-gray-500">
            <div className="flex flex-wrap justify-between gap-2 font-mono text-indigo-700"><span>N₂ {fmt(nitrogen * 100)}%</span><span>CO₂ {fmt(vals.co2_fraction * 100)}%</span><span>He {fmt(vals.helium_fraction * 100)}%</span></div>
            {!controls.loading && flex.fields.filter((f) => (f.unit !== "mole fraction" || vals[f.name] > 0) && (controls.data?.fields.find((c) => c.name === f.name)?.values || []).length <= 1).map((f) => <div key={f.name} className="flex justify-between gap-2"><span>{f.label.replace(" fraction", "")}</span><span>{fmt(f.unit === "mole fraction" ? vals[f.name] * 100 : vals[f.name])} {f.unit === "mole fraction" ? "%" : f.unit}</span></div>)}
            <p>Only settings with at least three nearby screened sample groups are selectable. Nearby tests do not guarantee accuracy.</p>
          </div></details>
          <button className="primary-button w-full" onClick={() => openExperiment(anchor.experiment_id)}>Inspect starting NASA test ↗</button>
        </Card>
        <div className="min-w-0 space-y-4">
          <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-panel/60 px-4 py-3 text-xs">
            <span className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${support?.supported ? "bg-indigo-500" : "bg-amber-300"}`} />{controls.loading ? "Checking nearby evidence…" : support?.supported ? `${support.nearby_groups} nearby NASA sample groups` : "Coverage check unavailable"}</span>
            <span className="text-gray-500">Same fuel · same gas family</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <ResultCard title="Recorded Extinction probability" r={ext.data} error={ext.error} loading={ext.loading || pending} valueKey="probability_extinction"
              extra={ext.data?.compared_with_typical && <div className="text-xs text-gray-700">{ext.data.compared_with_typical.label}</div>} />
            <ResultCard title="Estimated recorded burn time" r={burn.data} error={burn.error} loading={burn.loading || pending} valueKey="burn_time_s" />
          </div>
          {(ext.data?.warnings || []).map((w, i) => <Warning key={i}>{w.message}</Warning>)}
          <Card title="Change one condition" subtitle="Model estimates and recorded NASA tests."
            right={<div className="flex flex-wrap gap-2">
              <Toggle value={model} onChange={setModel} options={[{ value: "extinction", label: "Extinction" }, { value: "burn_time", label: "Burn time" }]} />
              <select aria-label="Condition to vary" value={vary} onChange={(e) => setVary(e.target.value)} className="rounded-md border border-line bg-ink px-2 text-sm text-gray-900">
                {flex.fields.map((f) => <option key={f.name} value={f.name}>{f.label}</option>)}
              </select>
            </div>}>
            {(curve.loading || pending) && <Spinner label="Checking supported curve…" />}
            <ErrorBox error={curve.error} />
            {!pending && curve.data && <WhatIfChart d={curve.data} current={vals[vary]} />}
            <details className="mt-3 border-t border-line pt-3"><summary>About this chart</summary><p className="text-xs leading-relaxed text-gray-500">The line is an estimate; dots are screened NASA observations with other inputs that may differ. Gaps indicate unsupported combinations.{model === "extinction" && " Recorded outcomes appear at 100% for extinction and 0% for completion."}</p></details>
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
    <div className="flex items-center justify-between gap-3 text-xs"><span className="text-gray-700">{field.label.replace(" fraction", "")}</span><output className="rounded-md border border-line bg-ink/80 px-2 py-1 font-mono text-indigo-700">{display(value)} <span className="text-gray-500">{unit}</span></output></div>
    <input aria-label={field.label} aria-valuetext={`${display(value)} ${unit}`} type="range" min={0} max={Math.max(1, settings.length - 1)} step={1} value={index}
      style={{ "--range-fill": `${index / Math.max(1, settings.length - 1) * 100}%` }}
      disabled={disabled || fixed} onChange={(e) => onChange(settings[Number(e.target.value)])} className="mt-1 w-full disabled:opacity-30" />
    <div className="flex justify-between text-[10px] text-gray-500">{fixed ? <span>{disabled ? "Checking settings…" : "Fixed for this gas mixture / nearby coverage"}</span> : <><span>{display(settings[0])} {unit}</span><span>{display(settings.at(-1))} {unit}</span></>}</div>
  </div>;
}

function ResultCard({ title, r, valueKey, extra, loading, error }) {
  return <Card title={title} className="result-number border-t-indigo-200/35">
    {loading ? <div className="py-5"><Spinner label="Updating estimate…" /></div> : error ? <ErrorBox error={error} /> : r?.available ? (
      <div className="space-y-3"><Value v={r[valueKey]} big />{extra}<details><summary>Estimate details</summary><p className="text-xs leading-relaxed text-gray-500">{r[valueKey].note}</p></details></div>
    ) : <div className="space-y-2 text-sm"><div className="text-amber-800">Estimate unavailable</div><p className="text-gray-700">{r?.reason || "Select a supported NASA starting test."}</p><p className="text-xs text-gray-500">Use the real tests below to review available evidence.</p></div>}
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
          <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
          <XAxis type="number" dataKey="x" domain={[Math.min(...xs), Math.max(...xs)]} tick={{ fill: "#6b7280", fontSize: 11 }}
            tickFormatter={(v) => fmt(v)} label={{ value: `${d.label}${d.unit ? ` (${d.unit})` : ""}`, position: "bottom", fill: "#6b7280", fontSize: 12 }} allowDuplicatedCategory={false} />
          <YAxis domain={isProb ? [0, 1] : ["auto", "auto"]} tick={{ fill: "#6b7280", fontSize: 11 }}
            tickFormatter={(v) => (isProb ? `${Math.round(v * 100)}%` : fmt(v))} />
          <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", fontSize: 12 }}
            formatter={(v, name) => (Array.isArray(v) ? `${fmt(v[0], d.y_unit)}–${fmt(v[1], d.y_unit)}` : isProb ? fmt(v, "probability") : fmt(v)) + (name === "real" ? "" : "")}
            labelFormatter={(v) => `${d.label}: ${fmt(v)}`} />
          <Legend verticalAlign="top" height={24} wrapperStyle={{ fontSize: 12 }} />
          <ReferenceArea x1={Math.min(...xs)} x2={lo} fill="#64748b" fillOpacity={0.12} />
          <ReferenceArea x1={hi} x2={Math.max(...xs)} fill="#64748b" fillOpacity={0.12} />
          <Area data={data} dataKey="band" name="model range" stroke="none" fill="#4f46e5" fillOpacity={0.2} connectNulls={false} isAnimationActive={false} />
          <Line data={data} dataKey="y" name={d.y_label} stroke="#4f46e5" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
          <Scatter data={real} dataKey="real" name="NASA tests" fill="#818cf8" fillOpacity={0.6} isAnimationActive={false} />
          {current != null && <ReferenceLine x={current} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: "you", fill: "#f59e0b", fontSize: 11 }} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Factors({ f, title }) {
  const max = Math.max(...f.items.map((i) => Math.abs(i.effect)), 1);
  return (
    <Card title={title} subtitle={f.method}>
      <p className="mb-3 text-xs text-gray-500">Model sensitivity, not a causal effect. Unsupported comparisons are omitted.</p>
      <ul className="space-y-2 text-xs">
        {f.items.map((i) => (
          <li key={i.feature}>
            <div className="flex justify-between text-gray-700">
              <span>{i.label}: {fmt(i.your_value)} <span className="text-gray-500">(typical {fmt(i.typical_value)})</span></span>
              <span className={i.effect > 0 ? "text-indigo-700" : "text-violet-700"}>{i.effect > 0 ? "+" : ""}{fmt(i.effect)} pts</span>
            </div>
            <div className="mt-1 h-1.5 rounded bg-ink">
              <div className={`h-1.5 rounded ${i.effect > 0 ? "bg-indigo-500/70" : "bg-violet-400/70"}`} style={{ width: `${(Math.abs(i.effect) / max) * 100}%` }} />
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
            <button onClick={() => openExperiment(m.experiment_id)} className="w-full rounded px-1.5 py-1 text-left hover:bg-gray-50">
              <span className="text-indigo-600">FLEX test {m.test_id}</span>
              <span className="text-gray-500"> · {fmt(m.oxygen_pct.value)}% O₂ · {fmt(m.pressure_kpa.value)} kPa · {fmt(m.droplet_diameter_mm.value)} mm · {m.outcome.label}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
