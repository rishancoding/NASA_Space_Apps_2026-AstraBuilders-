// Material Advisor: rank NASA-tested materials for your cabin conditions (structure follows app/pages/advisor.py).
import { useEffect, useState } from "react";
import { fs } from "../api.js";
import { plottable, ProbabilityBars, TestsScatter } from "../components/charts.jsx";
import { Badge, Caption, Card, DataTable, ErrorBox, Label, Markdown, Metric, Note, PageHeader, Radio, Select, Slider,
  Spinner, TextInput, Toggle } from "../components/ui.jsx";

const STRENGTH_BADGE = { strong: ["Lots of NASA tests", "green"], moderate: ["Some NASA tests", "blue"],
  weak: ["Few NASA tests", "orange"], none: ["No nearby tests", "gray"] };
const PRIORITY_LABEL = { sustained: "Least likely to keep burning", ignition: "Least likely to catch fire",
  spread: "Slowest flame spread", evidence: "Most NASA test data" };
const CHECK_ICON = { meets: ["✓", "check-meets"], fails: ["✗", "check-fails"], "cannot assess": ["?", "check-unknown"], "outside data": ["!", "check-outside"] };
const CHECK_NAME = { Oxygen: "Oxygen level", Airflow: "Airflow", Shape: "Shape", "Max thickness": "Thickness limit" };
const OUTCOME_WORDS = { "sustained burn": "kept burning", "burned, then went out": "went out",
  "brief flame, not sustained": "went out", "suppressed (agent/N2)": "went out", "no ignition": "never lit" };
const SHAPES = { any: "Any shape", fabric: "Fabric", film: "Film", sheet: "Sheet", slab: "Slab", rod: "Rod", sphere: "Sphere", candle: "Candle" };

function testsLine(tests) {
  if (!tests.length) return "No NASA tests near your oxygen level.";
  const counts = {};
  for (const t of tests) { const w = OUTCOME_WORDS[t.outcome_group] || "unclear"; counts[w] = (counts[w] || 0) + 1; }
  const parts = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([w, n]) => `${n} ${w}`).join(", ");
  return `${tests.length} NASA test${tests.length !== 1 ? "s" : ""} nearby: ${parts}.`;
}

const clamp = (v, [lo, hi]) => Math.min(hi, Math.max(lo, v));
const round = (v, d = 1) => Math.round(v * 10 ** d) / 10 ** d;

export default function Advisor({ fsOptions, advisor, setAdvisor, goTo }) {
  const sm = fsOptions.solid;
  const [form, setForm] = useState(advisor.form || { mode: "discover", material: "PMMA", oxygen_pct: 21, airflow_cm_s: 10,
    priority: "sustained", geometry: "any", max_thickness_mm: 0, require_geometry: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  // Sliders cover only what NASA tested: one material's range when analyzing it, all materials' range otherwise.
  const span = form.mode === "analyze" ? sm.ranges[form.material] : sm.advisor_ranges;
  const oxyRange = [round(span.oxygen_pct[0]), round(span.oxygen_pct[1])];
  const airRange = [round(span.airflow_cm_s[0]), round(span.airflow_cm_s[1])];
  const update = (patch) => setForm((f) => {
    const n = { ...f, ...patch };
    const s = n.mode === "analyze" ? sm.ranges[n.material] : sm.advisor_ranges;
    return { ...n, oxygen_pct: clamp(n.oxygen_pct, [round(s.oxygen_pct[0]), round(s.oxygen_pct[1])]),
      airflow_cm_s: clamp(n.airflow_cm_s, [round(s.airflow_cm_s[0]), round(s.airflow_cm_s[1])]) };
  });
  const set = (k) => (v) => update({ [k]: v });

  async function run(f = form) {
    setBusy(true); setError(null);
    try {
      const result = await fs.advisor({ ...f, material: f.mode === "analyze" ? f.material : null });
      setAdvisor({ form: f, result, explanation: null });
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  useEffect(() => { if (!advisor.result) run(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const res = advisor.result;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="NASA fire tests in orbit" title="Material Advisor"
        caption="See how spacecraft materials burned in NASA's space station fire tests, ranked for your cabin conditions.">
        <Toggle value={form.mode} onChange={set("mode")} options={[{ value: "discover", label: "Find a material" }, { value: "analyze", label: "Check one material" }]} />
      </PageHeader>

      <div className="advisor-layout">
        <form className="advisor-controls" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <Card className="space-y-4">
            <Label>Your cabin</Label>
            {form.mode === "analyze" && <Select label="Material" value={form.material} onChange={set("material")} options={sm.materials} />}
            <Slider label="Oxygen" unit="%" value={form.oxygen_pct} min={oxyRange[0]} max={oxyRange[1]} step={0.1} onChange={set("oxygen_pct")} hint="Earth air is 21%." />
            <Slider label="Airflow" unit="cm/s" value={form.airflow_cm_s} min={airRange[0]} max={airRange[1]} step={0.5} onChange={set("airflow_cm_s")} hint="Station fans: about 5–20 cm/s." />
            <Note>Sliders cover only conditions NASA tested.</Note>
            <Radio label="Rank by" value={form.priority} onChange={set("priority")}
              options={Object.keys(fsOptions.priorities).map((value) => ({ value, label: PRIORITY_LABEL[value] || fsOptions.priorities[value] }))} />
            <details className="border-t border-line pt-4"><summary>Shape and size</summary><div className="space-y-4">
              <Select label="Shape" value={form.geometry} onChange={set("geometry")} options={fsOptions.geometries.map((g) => ({ value: g, label: SHAPES[g] || g }))} />
              <label className="fs-check"><input type="checkbox" checked={form.require_geometry} onChange={(e) => set("require_geometry")(e.target.checked)} /> Only materials tested in this shape</label>
              <TextInput label="Thickest piece you can use (mm, 0 = no limit)" type="number" min={0} max={100} step={0.1} value={form.max_thickness_mm} onChange={set("max_thickness_mm")} />
            </div></details>
            <button type="submit" disabled={busy} className="primary-button w-full">{busy ? "Ranking…" : "Rank materials"}</button>
          </Card>
        </form>

        <div className="advisor-results space-y-4" aria-live="polite">
          <ErrorBox error={error} />
          {!res && busy && <Spinner label="Ranking materials…" />}
          {res && <Results res={res} />}
        </div>
      </div>

      {res && <Explanation advisor={advisor} setAdvisor={setAdvisor} online={fsOptions.assistant_online} goTo={goTo} />}
    </div>
  );
}

function Results({ res }) {
  const [tab, setTab] = useState("ranked");
  const sc = res.scenario;
  const all = [...res.selected, ...res.candidates];
  const withTests = all.filter((c) => plottable(c.comparable_tests)).map((c) => c.material);
  const [pick, setPick] = useState(null);
  const chosen = withTests.includes(pick) ? pick : withTests[0];
  const c = all.find((x) => x.material === chosen);
  if (!all.length) return <Card><p className="text-sm text-gray-700">No material was tested near these conditions. Try an oxygen level closer to 21%.</p></Card>;
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Toggle value={tab} onChange={setTab} options={[{ value: "ranked", label: "Ranking" }, { value: "charts", label: "Charts" }]} />
        <Caption>Not a safety certification.</Caption>
      </div>
      {tab === "ranked" ? (
        <div className="space-y-4">
          {res.selected.map((x) => <CandidateCard key={x.material} c={x} />)}
          {res.selected.length > 0 && res.candidates.length > 0 && <Label>Other materials</Label>}
          {res.candidates.map((x) => <CandidateCard key={x.material} c={x} />)}
          {res.not_tested_here?.length > 0 && <Caption>Not tested near these conditions: {res.not_tested_here.join(", ")}.</Caption>}
          {res.excluded.length > 0 && (
            <details className="expander"><summary>{res.excluded.length} hidden by your shape or size filters</summary>
              <div className="space-y-4">{res.excluded.map((x) => <CandidateCard key={x.material} c={x} />)}</div></details>
          )}
        </div>
      ) : (
        <Card className="space-y-4">
          <Label>Chance a flame keeps burning</Label>
          <ProbabilityBars candidates={all} />
          <Note>Lower is better. Small gaps don't mean much.</Note>
          {withTests.length > 0 && <>
            <Label className="pt-3">NASA tests near your conditions</Label>
            <Toggle value={chosen} onChange={setPick} options={withTests.map((m) => ({ value: m, label: m }))} />
            <TestsScatter tests={c.comparable_tests} oxygen={sc.oxygen_pct} airflow={sc.airflow_cm_s} height={420} />
            <Note>Each mark is one {chosen} test. The star is your cabin.</Note>
          </>}
        </Card>
      )}
    </>
  );
}

function CandidateCard({ c }) {
  const [label, color] = STRENGTH_BADGE[c.evidence_strength];
  const head = c.is_selected ? "Your material" : c.rank ? `#${c.rank}` : "Hidden";
  const p = c.prediction.probability;
  const [tab, setTab] = useState("tests");
  return (
    <Card className={`candidate-card ${c.is_selected ? "is-selected" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <Label>{head}</Label>
          <h3>{c.material}</h3>
          <Badge color={color}>{label}</Badge>
          <p className="text-sm text-gray-700">{testsLine(c.comparable_tests)}</p>
          {c.excluded_reason && <Caption>Hidden: {c.excluded_reason}.</Caption>}
        </div>
        <Metric label="Chance it keeps burning" value={`${Math.round(p * 100)}%`}
          help="Model estimate for a flame on this material at your oxygen and airflow." />
      </div>
      <details className="mt-4 border-t border-line pt-3"><summary>Tests and sources</summary>
        <div className="space-y-3">
          <Toggle value={tab} onChange={setTab} options={[{ value: "tests", label: "NASA tests" }, { value: "fit", label: "Fit" }, { value: "sources", label: "Sources" }]} />
          {tab === "tests" && <TestsTab c={c} />}
          {tab === "fit" && <ul className="space-y-1.5 text-sm">
            {c.checks.map((ch) => <li key={ch.name}><span className={`check-icon ${CHECK_ICON[ch.status]?.[1]}`}>{CHECK_ICON[ch.status]?.[0]}</span> <b>{CHECK_NAME[ch.name] || ch.name}:</b> {ch.detail}</li>)}
            {c.concerns.map((x) => <li key={x} className="text-amber-800">⚠ {x}</li>)}
          </ul>}
          {tab === "sources" && <Citations items={c.citations} />}
        </div>
      </details>
    </Card>
  );
}

function TestsTab({ c }) {
  return (
    <div className="space-y-3 text-sm">
      {Object.entries(c.stage_evidence).map(([proto, v]) => (
        <p key={proto}>{proto === "ignition_trial" ? "Freshly lit" : "Already burning"}: the flame stayed lit in <b>{v.sustained} of {v.n}</b> closely measured runs.</p>))}
      {c.comparable_tests.length > 0 && (
        <DataTable maxHeight={220} rows={c.comparable_tests.map((t) => ({ ...t, result: OUTCOME_WORDS[t.outcome_group] || "unclear" }))}
          columns={[{ key: "investigation", label: "Experiment" }, { key: "test_id", label: "Test" }, { key: "oxygen_pct", label: "Oxygen %" },
            { key: "airflow_raw", label: "Airflow (cm/s)" }, { key: "result", label: "Result" }, { key: "notes", label: "Crew notes" }]} />
      )}
      {c.saffire.length > 0 && <><b>Large fire tests (Saffire)</b>
        <DataTable maxHeight={180} rows={c.saffire} columns={[{ key: "source_record", label: "Experiment" }, { key: "sample", label: "Sample" },
          { key: "spread_rate", label: "Spread rate" }, { key: "result", label: "Result" }]} /></>}
    </div>
  );
}

export function Citations({ items }) {
  const seen = new Set();
  const list = (items || []).filter((x) => x.url && !seen.has(`${x.label}|${x.url}`) && seen.add(`${x.label}|${x.url}`));
  if (!list.length) return null;
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm">{list.map((x) => <li key={`${x.label}|${x.url}`}><a className="text-indigo-600 hover:underline" href={x.url} target="_blank" rel="noreferrer">{x.label}</a></li>)}</ul>
  );
}

function Explanation({ advisor, setAdvisor, online, goTo }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function explain() {
    setBusy(true); setError(null);
    try {
      const out = await fs.explain(advisor.result);
      setAdvisor((a) => ({ ...a, explanation: out.text }));
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return (
    <section className="explanation">
      <Label>In short</Label>
      <div className="explanation-grid">
        <Card><Markdown text={advisor.explanation || advisor.result.summary} /></Card>
        <div className="space-y-3">
          {online && <button className="primary-button w-full" disabled={busy} onClick={explain}>{busy ? "Reading the tests…" : "Explain with AI"}</button>}
          <button className="secondary-button w-full" onClick={() => goTo("assistant")}>Ask a follow-up question</button>
          <ErrorBox error={error} />
        </div>
      </div>
    </section>
  );
}
