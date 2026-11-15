import { useState } from "react";
import { api } from "../api.js";
import { Card, CoverageBadge, ErrorBox, Select, Slider, Spinner, Toggle, TrustBadge, Value, Warning, fmt, useAsync, useDebounced } from "../components/ui.jsx";

const STATUS = {
  met: ["✓ met", "text-emerald-300"],
  failed: ["✗ failed", "text-red-300"],
  cannot_check: ["? can't check", "text-slate-400"],
};

export default function Advisor({ options, openExperiment, askChat }) {
  const solids = options.solids;
  const [form, setForm] = useState({
    mode: "discover", oxygen_pct: 21, airflow_cm_s: 10, material: solids.materials[0].name,
    mission: "space_station", pressure_kpa: 101.3, max_thickness_mm: null, priority: "evidence_strength",
  });
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const q = useDebounced(form, 250);
  const res = useAsync(() => api.advisor({ ...q, material: q.mode === "analyze" ? q.material : null }), [JSON.stringify(q)]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Material Advisor</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Enter your habitat's conditions and see what NASA actually observed when materials burned in orbit near them.
          </p>
        </div>
        <Toggle value={form.mode} onChange={set("mode")}
          options={[{ value: "discover", label: "Find a material" }, { value: "analyze", label: "Analyze a material" }]} />
      </div>

      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        {/* ---------------- inputs */}
        <Card title="Your conditions" className="h-fit space-y-4">
          <div className="flex flex-wrap gap-2">
            {options.presets.map((p) => (
              <button key={p.id} title={p.note}
                onClick={() => setForm((f) => ({ ...f, oxygen_pct: p.oxygen_pct, airflow_cm_s: p.airflow_cm_s, pressure_kpa: p.pressure_kpa }))}
                className="rounded-full border border-line px-2.5 py-1 text-xs text-slate-300 hover:border-flame hover:text-white">
                {p.label}
              </button>
            ))}
          </div>
          {form.mode === "analyze" && (
            <Select label="Material to analyze" value={form.material} onChange={set("material")}
              options={solids.materials.map((m) => ({ value: m.name, label: `${m.name} (${m.tests} tests)` }))} />
          )}
          <Slider label="Oxygen" unit="%" value={form.oxygen_pct} min={10} max={40} step={0.5} onChange={set("oxygen_pct")}
            hint={`Solid tests in orbit: ${solids.oxygen_pct.min}–${solids.oxygen_pct.max}%`} />
          <Slider label="Airflow" unit="cm/s" value={form.airflow_cm_s} min={0} max={solids.airflow_cm_s.max} step={0.5} onChange={set("airflow_cm_s")} />
          <Slider label="Cabin pressure" unit="kPa" value={form.pressure_kpa} min={30} max={110} step={0.5} onChange={set("pressure_kpa")}
            hint="Shown for context: solid tests did not vary pressure." />
          <Select label="Mission" value={form.mission} onChange={set("mission")} options={options.missions} />
          <label className="block text-xs">
            <span className="text-slate-300">Max sample thickness (optional)</span>
            <input type="number" min={0} step={0.1} value={form.max_thickness_mm ?? ""} placeholder="mm"
              onChange={(e) => set("max_thickness_mm")(e.target.value === "" ? null : Number(e.target.value))}
              className="mt-1 w-full rounded-md border border-line bg-ink px-2 py-1.5 text-sm text-slate-100" />
          </label>
          <Select label="Rank by" value={form.priority} onChange={set("priority")} options={options.priorities} />
        </Card>

        {/* ---------------- results */}
        <div className="space-y-4">
          {res.loading && !res.data && <Spinner />}
          <ErrorBox error={res.error} />
          {res.data && (
            <>
              {res.data.warnings.map((w) => <Warning key={w.code}>{w.message}</Warning>)}
              <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400">
                <span><b className="text-slate-300">Ranked by:</b> {res.data.rank_basis}</span>
                <button onClick={() => askChat({ page: "material_advisor", inputs: res.data.inputs,
                  ranking: res.data.candidates.map((c) => ({ rank: c.rank, material: c.material, evidence: c.evidence, events: c.condition_linked_events_nearby })) })}
                  className="rounded-md border border-line px-2.5 py-1 text-slate-300 hover:border-flame hover:text-white">
                  Ask the assistant about this ranking
                </button>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                {res.data.candidates.map((c) => <CandidateCard key={c.material} c={c} openExperiment={openExperiment} />)}
              </div>
              <p className="text-xs text-slate-500">{res.data.not_a_safety_rating}</p>
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
    <Card className={c.is_selected ? "ring-2 ring-flame" : ""}
      title={<span className="flex items-center gap-2"><span className="text-slate-500">#{c.rank}</span> {c.material}
        {c.is_selected && <span className="rounded bg-flame/20 px-1.5 text-[10px] text-flame">your material</span>}</span>}
      right={<CoverageBadge coverage={c.evidence.coverage} />}>
      <div className="grid grid-cols-3 gap-2 text-center">
        <Stat n={c.evidence.close_tests} label="close tests" />
        <Stat n={c.evidence.nearby_tests} label="nearby tests" />
        <Stat n={c.evidence.total_tests} label="tests total" />
      </div>

      <div className="mt-3 space-y-2 text-xs">
        <div>
          <div className="mb-1 flex items-center gap-2 text-slate-400">What happened in nearby tests <TrustBadge trust="ai_label" /></div>
          {outcomes.length ? (
            <div className="flex flex-wrap gap-1.5">
              {outcomes.map(([k, n]) => <span key={k} className="rounded bg-ink px-2 py-0.5 text-slate-200">{k}: {n}</span>)}
            </div>
          ) : <div className="text-slate-500">No NASA test near these conditions.</div>}
        </div>
        {ev.events > 0 && (
          <div className="text-slate-300">
            Flame results tied to a specific airflow: <b className="text-white">{ev.sustained_flame}</b> sustained, <b className="text-white">{ev.not_sustained}</b> not sustained
          </div>
        )}
        {c.earth_reference?.earth_tests?.length > 0 && (
          <div className="text-slate-300">
            Earth-gravity oxygen limit (lowest ULOI): <Value v={c.earth_reference.earth_tests.reduce((a, b) => (b.uloi_oxygen_pct.value < a.uloi_oxygen_pct.value ? b : a)).uloi_oxygen_pct} />
          </div>
        )}
        <ul className="space-y-0.5">
          {c.constraint_checks.map((ch, i) => (
            <li key={i} title={ch.reason}><span className={STATUS[ch.status][1]}>{STATUS[ch.status][0]}</span> <span className="text-slate-400">{ch.constraint.replaceAll("_", " ")}: {ch.reason}</span></li>
          ))}
        </ul>
        {c.concerns.length > 0 && (
          <ul className="list-inside list-disc text-amber-200/80">{c.concerns.map((x) => <li key={x}>{x}</li>)}</ul>
        )}
      </div>

      <div className="mt-3 border-t border-line pt-2">
        <div className="mb-1 text-xs text-slate-400">Closest NASA tests</div>
        <ul className="space-y-1">
          {c.top_tests.map((t) => (
            <li key={t.experiment_id}>
              <button onClick={() => openExperiment(t.experiment_id)} className="w-full rounded px-1.5 py-1 text-left text-xs hover:bg-white/5">
                <span className="text-sky-300">{t.investigation} test {t.test_id}</span>
                <span className="text-slate-400"> · {fmt(t.oxygen_pct.value)}% O₂ · {t.airflow_raw ? `${t.airflow_raw} cm/s` : "airflow n/a"} · {t.outcome.label}</span>
                <span className="text-slate-500"> · distance {t.distance}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

function Stat({ n, label }) {
  return (
    <div className="rounded-lg bg-ink py-2">
      <div className="text-lg font-semibold text-white">{n}</div>
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
    </div>
  );
}
