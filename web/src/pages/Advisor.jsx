import { useState } from "react";
import { api } from "../api.js";
import { Card, CoverageBadge, ErrorBox, Select, Slider, Spinner, Toggle, TrustBadge, Value, Warning, fmt, useAsync } from "../components/ui.jsx";

const TRIAL_LABELS = { ignition_trial: "Starting a flame", ongoing_burn_trial: "Keeping a flame burning" };

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
  const [submitted, setSubmitted] = useState(null);
  const current = submitted && JSON.stringify(form) === JSON.stringify(submitted);
  const res = useAsync(() => submitted ? api.advisor({ ...submitted, material: submitted.mode === "analyze" ? submitted.material : null }) : Promise.resolve(null), [submitted]);

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
          {form.mode === "analyze" && (
            <Select label="Material to analyze" value={form.material} onChange={set("material")}
              options={solids.materials.map((m) => ({ value: m.name, label: `${m.name} (${m.tests} tests)` }))} />
          )}
          <Slider label="Initial oxygen" unit="%" value={form.oxygen_pct} min={solids.oxygen_pct.min} max={solids.oxygen_pct.max} step={0.1} onChange={set("oxygen_pct")} />
          <Slider label="Airflow" unit="cm/s" value={form.airflow_cm_s} min={0} max={solids.airflow_cm_s.max} step={0.5} onChange={set("airflow_cm_s")} />
          <Select label="Trial type" value={form.protocol} onChange={set("protocol")} options={options.protocols.map((p) => ({ ...p, label: TRIAL_LABELS[p.value] || p.label }))} />
          <p className="text-xs leading-relaxed text-gray-500">{form.protocol === "ignition_trial" ? "After an ignition attempt, did the flame sustain?" : "Once burning, did the flame continue under these conditions?"}</p>
          <details className="border-t border-line pt-4"><summary>More options</summary><div className="space-y-4">
          <Select label="Sample shape" value={form.geometry} onChange={set("geometry")} allowEmpty="All shapes" options={solids.geometries} />
          <label className="block text-xs">
            <span className="text-gray-700">Maximum thickness (mm)</span>
            <input type="number" min={0} step={0.1} value={form.max_thickness_mm ?? ""} placeholder="mm"
              onChange={(e) => set("max_thickness_mm")(e.target.value === "" ? null : Number(e.target.value))}
              className="mt-1 w-full rounded-md border border-line bg-ink px-2 py-1.5 text-sm text-gray-900" />
          </label>
          <Select label="Mission" value={form.mission} onChange={set("mission")} options={options.missions} />
          <p className="text-[11px] leading-relaxed text-gray-500">Pressure is fixed for solid tests. Partial-gravity behavior is unknown in this dataset.</p>
          </div></details>
          <button className="primary-button w-full" onClick={() => setSubmitted({ ...form })} disabled={current && res.loading}>View observations ↗</button>
          <p className="text-xs text-gray-500">Choose your settings, then view matching outcomes. Changing settings hides previous results.</p>
        </Card>

        {/* ---------------- results */}
        <div className="advisor-results space-y-4" aria-live="polite">
          {!current && <div className="results-empty"><span className="home-kicker">Your conditions → NASA observations</span><h2>What happened to the flame?</h2><p>Set oxygen, airflow and trial type, then choose <b>View observations</b>. You’ll see sustained and not-sustained flame events, with source notes and evidence gaps.</p><span>No outcomes have been calculated for these settings yet.</span></div>}
          {current && res.loading && <Spinner />}
          {current && <ErrorBox error={res.error} />}
          {current && res.data && (
            <>
              {res.data.warnings.filter((w) => w.code !== "initial_oxygen").map((w) => <Warning key={w.code}>{w.message}</Warning>)}
              <div className="submitted-context">Initial oxygen {submitted.oxygen_pct}% · airflow {submitted.airflow_cm_s} cm/s · {TRIAL_LABELS[submitted.protocol]}</div>
              <p className="text-xs text-gray-500">Initial oxygen is a proxy; oxygen at the flame event is unknown. Observation durations vary.</p>
              <div className="ranking-explanation"><h2>How materials are ordered</h2><p>{res.data.rank_basis}</p><details><summary>See the calculation</summary><p>{res.data.ranking.method}</p></details><p className="ranking-limit">Flame outcomes are shown for context but do not determine this order. A material appearing first is not necessarily safer.</p></div>
              <div className="results-toolbar">
                <h2 title={res.data.rank_basis}>Material matches <span className="ml-1 text-gray-400">{res.data.candidates.length}</span></h2>
                <button onClick={() => askChat({ page: "material_advisor", inputs: res.data.inputs,
                  ranking: res.data.candidates.map((c) => ({ rank: c.rank, material: c.material, evidence: c.evidence, events: c.condition_linked_events_nearby })) })}
                  className="text-xs text-indigo-600 hover:underline">
                  Explain this evidence order ↗
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
      title={<span className="flex items-center gap-2"><span className="rank">{c.rank === null ? "Unranked" : `#${c.rank}`}</span> {c.material}
        {c.is_selected && <span className="rounded bg-flame/20 px-1.5 text-[10px] text-flame">your material</span>}</span>}
      right={<CoverageBadge coverage={c.evidence.coverage} />}>
      <p className="rank-explanation">{c.pinned_selected ? "Your selected material is pinned here; " : ""}<b>{c.rank === null ? "Not ranked:" : `Why #${c.rank}:`}</b> {c.rank_reason}</p>
      <div className="outcome-heading">{TRIAL_LABELS[ev.protocol]}</div>
      {ev.events > 0 ? <><div className="candidate-stats outcome-stats">
        <Stat n={ev.sustained_flame} label="flame sustained" />
        <Stat n={ev.not_sustained} label="did not sustain" />
      </div><p className="outcome-context">Out of {ev.events} reviewed {ev.protocol === "ignition_trial" ? "ignition" : "already-burning"} events near your conditions. These are event counts, not a material safety rate.</p></> : <p className="outcome-unknown">No reviewed flame events match this trial type and these conditions. The outcome remains unknown here.</p>}
      <p className="evidence-context">Context: {c.evidence.nearby_tests} nearby whole tests · {c.evidence.total_tests} recorded for this material</p>

      <div className="candidate-body mt-4 space-y-3 text-xs">
        <details className="border-t border-line pt-3"><summary>Test details</summary><div className="space-y-3 leading-relaxed text-gray-500">
        <div className="mb-2 font-medium">Whole-test outcomes (may span several airflow stages)</div>
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
