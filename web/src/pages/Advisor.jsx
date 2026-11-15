import { useState } from "react";
import { api } from "../api.js";
import { Card, CoverageBadge, ErrorBox, Select, Slider, Spinner, Toggle, TrustBadge, Value, Warning, fmt, useAsync, useDebounced } from "../components/ui.jsx";

const STATUS = {
  met: ["✓ met", "text-emerald-700"],
  failed: ["✗ failed", "text-red-700"],
  cannot_check: ["? can't check", "text-gray-500"],
};

export default function Advisor({ options, openExperiment, askChat }) {
  const solids = options.solids;
  const [form, setForm] = useState({
    mode: "discover", oxygen_pct: 21, airflow_cm_s: 10, material: solids.materials[0].name,
    mission: "space_station", pressure_kpa: 101.3, max_thickness_mm: null, priority: "evidence_strength", geometry: null, protocol: "ignition_trial",
  });
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const q = useDebounced(form, 250);
  const res = useAsync(() => api.advisor({ ...q, material: q.mode === "analyze" ? q.material : null }), [JSON.stringify(q)]);

  return (
    <div className="space-y-5">
      <div className="page-heading flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1>Compare materials.</h1>
          <p>See how they behaved in NASA's fire tests.</p>
        </div>
        <Toggle value={form.mode} onChange={set("mode")}
          options={[{ value: "discover", label: "Find materials" }, { value: "analyze", label: "Analyze a material" }]} />
      </div>

      <div className="advisor-layout">
        {/* ---------------- inputs */}
        <Card title="Your conditions" className="advisor-controls h-fit space-y-5">
          <div className="presets">
            {options.presets.filter((p) => p.oxygen_pct >= solids.oxygen_pct.min && p.oxygen_pct <= solids.oxygen_pct.max).map((p) => (
              <button key={p.id} title={p.note} aria-pressed={form.oxygen_pct === p.oxygen_pct && form.airflow_cm_s === p.airflow_cm_s && form.pressure_kpa === p.pressure_kpa}
                onClick={() => setForm((f) => ({ ...f, oxygen_pct: p.oxygen_pct, airflow_cm_s: p.airflow_cm_s, pressure_kpa: p.pressure_kpa }))}
                >
                {p.id === "iss_cabin" ? "Standard cabin" : p.label.replace("ISS-like cabin", "Standard cabin").replace("Stagnant corner (low airflow)", "Low airflow")}
              </button>
            ))}
          </div>
          {form.mode === "analyze" && (
            <Select label="Material to analyze" value={form.material} onChange={set("material")}
              options={solids.materials.map((m) => ({ value: m.name, label: `${m.name} (${m.tests} tests)` }))} />
          )}
          <Slider label="Oxygen" unit="%" value={form.oxygen_pct} min={solids.oxygen_pct.min} max={solids.oxygen_pct.max} step={0.1} onChange={set("oxygen_pct")} />
          <Slider label="Airflow" unit="cm/s" value={form.airflow_cm_s} min={0} max={solids.airflow_cm_s.max} step={0.5} onChange={set("airflow_cm_s")} />
          <details className="border-t border-line pt-4"><summary>More options</summary><div className="space-y-4">
          <Select label="Sample shape" value={form.geometry} onChange={set("geometry")} allowEmpty="All shapes" options={solids.geometries} />
          <Select label="Trial type" value={form.protocol} onChange={set("protocol")} options={options.protocols} />
          <label className="block text-xs">
            <span className="text-gray-700">Maximum thickness (mm)</span>
            <input type="number" min={0} step={0.1} value={form.max_thickness_mm ?? ""} placeholder="mm"
              onChange={(e) => set("max_thickness_mm")(e.target.value === "" ? null : Number(e.target.value))}
              className="mt-1 w-full rounded-md border border-line bg-ink px-2 py-1.5 text-sm text-gray-900" />
          </label>
          <Select label="Mission" value={form.mission} onChange={set("mission")} options={options.missions} />
          <p className="text-[11px] leading-relaxed text-gray-500">Pressure is fixed for solid tests. Partial-gravity behavior is unknown in this dataset.</p>
          </div></details>
        </Card>

        {/* ---------------- results */}
        <div className="advisor-results space-y-4" aria-live="polite">
          {res.loading && !res.data && <Spinner />}
          <ErrorBox error={res.error} />
          {res.data && (
            <>
              {res.data.warnings.filter((w) => w.code !== "initial_oxygen").map((w) => <Warning key={w.code}>{w.message}</Warning>)}
              <div className="results-toolbar">
                <h2 title={res.data.rank_basis}>Material matches <span className="ml-1 text-gray-400">{res.data.candidates.length}</span></h2>
                <button onClick={() => askChat({ page: "material_advisor", inputs: res.data.inputs,
                  ranking: res.data.candidates.map((c) => ({ rank: c.rank, material: c.material, evidence: c.evidence, events: c.condition_linked_events_nearby })) })}
                  className="text-xs text-indigo-600 hover:underline">
                  Explain ranking ↗
                </button>
              </div>
              <div className="candidate-grid">
                {res.data.candidates.map((c) => <CandidateCard key={c.material} c={c} openExperiment={openExperiment} />)}
              </div>
              <details><summary>How matches are ranked</summary><p className="mt-2 text-xs leading-relaxed text-gray-500">{res.data.rank_basis}. {res.data.not_a_safety_rating}</p></details>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function CandidateCard({ c, openExperiment }) {
  const ev = c.condition_linked_events_nearby;
  const outcomes = Object.entries(c.observed_outcomes_nearby.counts);
  return (
    <Card className={`candidate-card ${c.is_selected ? "ring-2 ring-flame" : ""}`}
      title={<span className="flex items-center gap-2"><span className="rank">#{c.rank}</span> {c.material}
        {c.is_selected && <span className="rounded bg-flame/20 px-1.5 text-[10px] text-flame">your material</span>}</span>}
      right={<CoverageBadge coverage={c.evidence.coverage} />}>
      <div className="candidate-stats">
        <Stat n={c.evidence.nearby_tests} label="nearby tests" />
        <Stat n={c.evidence.total_tests} label="tests total" />
      </div>

      <div className="candidate-body mt-4 space-y-3 text-xs">
        <div>
          <div className="mb-2 text-gray-500">Recorded outcomes</div>
          {outcomes.length ? (
            <div className="flex flex-wrap gap-1.5">
              {outcomes.slice(0, 2).map(([k, n]) => <span key={k} className="candidate-outcome">{n} {k.toLowerCase().replace('brief flame, not sustained', 'brief flames').replace('burned until fuel ran out', 'used up fuel').replace('did not ignite', 'did not light').replace('unclear from the notes', 'unclear')}</span>)}
              {outcomes.length > 2 && <span className="candidate-outcome">+{outcomes.length - 2} outcomes</span>}
            </div>
          ) : <div className="text-gray-500">No NASA test near these conditions.</div>}
          {outcomes.length > 0 && <div className="candidate-progress" aria-hidden="true">{outcomes.map(([k, n]) => <span key={k} style={{ flex: n }} />)}</div>}
        </div>
        {ev.events > 0 && (
          <div className="text-gray-700">
            <div className="mb-1 text-gray-500">{ev.protocol === "ignition_trial" ? "Starting a flame" : "Already-burning trials"}</div>
            <b className="text-gray-900">{ev.sustained_flame}</b> kept burning · <b className="text-gray-900">{ev.not_sustained}</b> did not
          </div>
        )}
        <details className="border-t border-line pt-3"><summary>Test details</summary><div className="space-y-3 leading-relaxed text-gray-500">
        <div>{outcomes.map(([k,n]) => <span key={k} className="mr-3">{k}: {n}</span>)}</div>
        <p>Whole-test outcomes may cover multiple airflow stages. Condition matching uses initial oxygen; oxygen at each event is unknown and observation durations vary.</p>
        {ev.events > 0 && <div><div className="mb-2 font-medium text-gray-700">Supporting events · {ev.events}</div><ul className="space-y-2">{ev.evidence.map((e) => <li key={e.stage_id} className="rounded-md bg-ink p-3"><p className="italic">“{e.quote}”</p><button className="mt-1 text-indigo-600 hover:underline" onClick={() => openExperiment(e.experiment_id)}>{e.geometry} · initial {fmt(e.oxygen_initial_pct)}% O₂ · {fmt(e.airflow_cm_s)} cm/s ↗</button></li>)}</ul></div>}
        {c.earth_reference?.earth_tests?.length > 0 && (
          <div className="text-gray-700">
            Earth-gravity oxygen limit (lowest ULOI): <Value v={c.earth_reference.earth_tests.reduce((a, b) => (b.uloi_oxygen_pct.value < a.uloi_oxygen_pct.value ? b : a)).uloi_oxygen_pct} />
          </div>
        )}
        <ul className="space-y-0.5">
          {c.constraint_checks.map((ch, i) => (
            <li key={i} title={ch.reason}><span className={STATUS[ch.status][1]}>{STATUS[ch.status][0]}</span> <span className="text-gray-500">{ch.constraint.replaceAll("_", " ")}: {ch.reason}</span></li>
          ))}
        </ul>
        {c.concerns.length > 0 && (
          <ul className="list-inside list-disc text-amber-800/80">{c.concerns.map((x) => <li key={x}>{x}</li>)}</ul>
        )}
        </div></details>
      </div>

      <details className="mt-3 border-t border-line pt-3">
        <summary>Closest NASA tests</summary>
        <ul className="space-y-1">
          {c.top_tests.map((t) => (
            <li key={t.experiment_id}>
              <button onClick={() => openExperiment(t.experiment_id)} className="w-full rounded px-1.5 py-1 text-left text-xs hover:bg-gray-50">
                <span className="text-indigo-600">{t.investigation} test {t.test_id}</span>
                <span className="text-gray-500"> · {fmt(t.oxygen_pct.value)}% O₂ · {t.airflow_raw ? `${t.airflow_raw} cm/s` : "airflow n/a"} · {t.outcome.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </details>
    </Card>
  );
}

function Stat({ n, label }) {
  return (
    <div className="candidate-stat">
      <b>{n}</b>
      <span>{label}</span>
    </div>
  );
}
