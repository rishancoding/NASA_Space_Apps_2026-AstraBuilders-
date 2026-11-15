// Combustion Predictor: estimates only inside what NASA tested, plus a short "How reliable" tab.
import { useState } from "react";
import { fs } from "../api.js";
import { EstimateCurve } from "../components/charts.jsx";
import { Callout, Caption, Card, ErrorBox, Label, Metric, Note, PageHeader, Radio, Select, Slider, Spinner, Toggle, fmt,
  useAsync, useDebounced } from "../components/ui.jsx";

const EXPERIMENT = { "PSI-25": "BASS-II", "PSI-26": "BASS", "PSI-69": "FLEX" };
const SCENARIO = { ignition_trial: "Freshly lit", ongoing_burn_trial: "Already burning" };
const MIX = { air: "Oxygen + nitrogen", co2: "With carbon dioxide (CO₂)", helium: "With helium" };
const pct = (p) => `${Math.round(p * 100)}%`;
const tenths = (p) => (p * 10).toFixed(1).replace(/\.0$/, "");
const snap = (x) => Math.round(x * 1e6) / 1e6; // drop float noise like 14.000000000000002
const lo = (r, d = 1) => Math.ceil(snap(r[0] * 10 ** d)) / 10 ** d;
const hi = (r, d = 1) => Math.floor(snap(r[1] * 10 ** d)) / 10 ** d;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const mid = (r, d = 1) => Math.round(((r[0] + r[1]) / 2) * 10 ** d) / 10 ** d;

function diff(mine, theirs, unit) {
  const gap = theirs - mine;
  return Math.abs(gap) < 0.05 ? "the same" : `${Math.abs(gap).toFixed(1)} ${unit} ${gap > 0 ? "higher" : "lower"}`;
}

export default function Predictor({ fsOptions }) {
  const [tab, setTab] = useState("solid");
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Machine-learning estimate" title="Combustion Predictor"
        caption="Will a flame keep burning in space? Models trained on NASA's station tests answer, only for conditions NASA tested.">
        <Toggle value={tab} onChange={setTab} options={[{ value: "solid", label: "Solid materials" }, { value: "flex", label: "Fuel droplets" }, { value: "trust", label: "How reliable?" }]} />
      </PageHeader>
      {tab === "solid" && <Solid o={fsOptions} />}
      {tab === "flex" && <Droplet o={fsOptions} />}
      {tab === "trust" && <Trust r={fsOptions.reliability} />}
    </div>
  );
}

function Score({ r }) {
  return <Note>Right on {tenths(r.accuracy)} of 10 NASA tests it never saw (always guessing the usual result: {tenths(r.baseline_accuracy)} of 10).</Note>;
}

function Solid({ o }) {
  const sm = o.solid;
  const start = sm.materials.includes("PMMA") ? "PMMA" : sm.materials[0];
  const [mat, setMat] = useState(start);
  const [proto, setProto] = useState(sm.protocols_by_material[start][0]);
  const rng = sm.ranges[mat];
  const [oxy, setOxy] = useState(clamp(21, lo(rng.oxygen_pct), hi(rng.oxygen_pct)));
  const [air, setAir] = useState(clamp(10, lo(rng.airflow_cm_s), hi(rng.airflow_cm_s)));
  const [vary, setVary] = useState("oxygen");
  const body = useDebounced({ material: mat, protocol: proto, oxygen_pct: oxy, airflow_cm_s: air, vary }, 150);
  const r = useAsync(() => fs.predictSolid(body), [JSON.stringify(body)]);
  const chooseMat = (m) => {
    const g = sm.ranges[m];
    setMat(m); setProto(sm.protocols_by_material[m][0]);
    setOxy(clamp(oxy, lo(g.oxygen_pct), hi(g.oxygen_pct))); setAir(clamp(air, lo(g.airflow_cm_s), hi(g.airflow_cm_s)));
  };
  const protos = sm.protocols_by_material[mat];
  const fixedOxy = hi(rng.oxygen_pct) - lo(rng.oxygen_pct) < 0.2;

  return (
    <div className="predictor-layout">
      <Card className="h-fit space-y-4">
        <Select label="Material" value={mat} onChange={chooseMat} options={sm.materials} />
        {protos.length > 1
          ? <Radio label="Flame" value={proto} onChange={setProto} options={protos.map((p) => ({ value: p, label: SCENARIO[p] }))} />
          : <Note>NASA only tested {mat} {proto === "ignition_trial" ? "as a freshly lit flame" : "while already burning"}.</Note>}
        {fixedOxy ? <Note>Oxygen: {fmt(oxy)}% (the only level tested).</Note>
          : <Slider label="Oxygen" unit="%" value={oxy} min={lo(rng.oxygen_pct)} max={hi(rng.oxygen_pct)} step={0.1} onChange={setOxy} />}
        <Slider label="Airflow" unit="cm/s" value={air} min={lo(rng.airflow_cm_s)} max={hi(rng.airflow_cm_s)} step={0.5} onChange={setAir} />
        <Note>Sliders show only what NASA tested for {mat}.</Note>
      </Card>

      <div className="min-w-0 space-y-4">
        <ErrorBox error={r.error} />
        {!r.data && r.loading && <Spinner label="Running the model…" />}
        {r.data && <>
          <Card>
            <Metric label="Chance the flame keeps burning" value={pct(r.data.probability)} />
            <Score r={o.reliability.solid} />
          </Card>
          <Card className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Label>How the estimate changes</Label>
              <Toggle value={vary} onChange={setVary} options={[{ value: "oxygen", label: "Oxygen" }, { value: "airflow", label: "Airflow" }]} />
            </div>
            {r.data.vary === vary && <EstimateCurve curve={r.data.curve} runs={r.data.runs}
              current={vary === "oxygen" ? oxy : air} xLabel={vary === "oxygen" ? "Oxygen (%)" : "Airflow (cm/s)"} />}
            <Note>Line: estimate. Dotted line: your setting. Dots: real NASA tests.</Note>
          </Card>
          <Label>Closest NASA tests</Label>
          <div className="space-y-2">{r.data.nearest.slice(0, 3).map((n) => <SolidRun key={n.stage_id} n={n} est={r.data} />)}</div>
        </>}
      </div>
    </div>
  );
}

function SolidRun({ n, est }) {
  const went = n.sustained_flame ? "kept burning" : "went out";
  const agrees = (est.probability >= 0.5) === Boolean(n.sustained_flame);
  return (
    <details className="expander"><summary>{EXPERIMENT[n.source_record] || n.source_record} test {n.test_id}: {went}</summary>
      <p className="text-sm text-gray-700">At {n.oxygen_pct.toFixed(1)}% oxygen and {fmt(n.airflow_cm_s)} cm/s the flame {went}. Crew note: "{n.evidence_quote}"</p>
      <Note className="mt-2">Oxygen {diff(est.oxygen_pct, n.oxygen_pct, "points")}, airflow {diff(est.airflow_cm_s, n.airflow_cm_s, "cm/s")}. {agrees ? "Agrees with" : "Differs from"} the estimate. <a href={n.source_url} target="_blank" rel="noreferrer">NASA record</a></Note>
    </details>
  );
}

function initial(m) {
  return { oxygen_pct: clamp(21, lo(m.oxygen_pct), hi(m.oxygen_pct)), droplet_diameter_mm: mid(m.droplet_diameter_mm, 2),
    pressure_kpa: clamp(101, lo(m.pressure_kpa, 0), hi(m.pressure_kpa, 0)), co2: Math.round(m.co2_fraction[0] * 100), he: Math.round(m.helium_fraction[0] * 100) };
}

function Droplet({ o }) {
  const fuels = o.flex.fuels;
  const [fuel, setFuel] = useState(fuels[0]);
  const [mix, setMix] = useState("air");
  const m = o.flex.mixtures[fuel][mix];
  const [v, setV] = useState(() => initial(o.flex.mixtures[fuels[0]].air));
  const set = (k) => (x) => setV((s) => ({ ...s, [k]: x }));
  const choose = (f, x) => {
    const mx = o.flex.mixtures[f][x] ? x : "air";
    const g = o.flex.mixtures[f][mx];
    setFuel(f); setMix(mx);
    setV((s) => ({ oxygen_pct: clamp(s.oxygen_pct, lo(g.oxygen_pct), hi(g.oxygen_pct)),
      droplet_diameter_mm: clamp(s.droplet_diameter_mm, lo(g.droplet_diameter_mm, 2), hi(g.droplet_diameter_mm, 2)),
      pressure_kpa: clamp(s.pressure_kpa, lo(g.pressure_kpa, 0), hi(g.pressure_kpa, 0)),
      co2: mx === "co2" ? clamp(s.co2 || 20, Math.round(g.co2_fraction[0] * 100), Math.round(g.co2_fraction[1] * 100)) : 0,
      he: mx === "helium" ? clamp(s.he || 20, Math.round(g.helium_fraction[0] * 100), Math.round(g.helium_fraction[1] * 100)) : 0 }));
  };
  const body = useDebounced({ fuel, oxygen_pct: v.oxygen_pct, droplet_diameter_mm: v.droplet_diameter_mm,
    co2_fraction: v.co2 / 100, helium_fraction: v.he / 100, pressure_kpa: v.pressure_kpa }, 150);
  const r = useAsync(() => fs.predictFlex(body), [JSON.stringify(body)]);
  return (
    <div className="predictor-layout">
      <Card className="h-fit space-y-4">
        <Toggle value={fuel} onChange={(f) => choose(f, mix)} options={fuels.map((f) => ({ value: f, label: f }))} />
        <Select label="Gas around the drop" value={mix} onChange={(x) => choose(fuel, x)}
          options={Object.keys(o.flex.mixtures[fuel]).map((x) => ({ value: x, label: MIX[x] || x }))} />
        <Slider label="Oxygen" unit="%" value={v.oxygen_pct} min={lo(m.oxygen_pct)} max={hi(m.oxygen_pct)} step={0.5} onChange={set("oxygen_pct")} />
        {mix === "co2" && <Slider label="Carbon dioxide (CO₂)" unit="%" value={v.co2} min={Math.round(m.co2_fraction[0] * 100)} max={Math.round(m.co2_fraction[1] * 100)} step={1} onChange={set("co2")} />}
        {mix === "helium" && <Slider label="Helium" unit="%" value={v.he} min={Math.round(m.helium_fraction[0] * 100)} max={Math.round(m.helium_fraction[1] * 100)} step={1} onChange={set("he")} />}
        <Slider label="Drop size" unit="mm" value={v.droplet_diameter_mm} min={lo(m.droplet_diameter_mm, 2)} max={hi(m.droplet_diameter_mm, 2)} step={0.05} onChange={set("droplet_diameter_mm")} />
        <Slider label="Pressure" unit="kPa" value={v.pressure_kpa} min={lo(m.pressure_kpa, 0)} max={hi(m.pressure_kpa, 0)} step={1} onChange={set("pressure_kpa")} hint="Sea level is about 101 kPa." />
        <Note>Sliders show only what NASA tested for {fuel.toLowerCase()} in this gas.</Note>
      </Card>
      <div className="min-w-0 space-y-4">
        <ErrorBox error={r.error} />
        {!r.data && r.loading && <Spinner label="Running the model…" />}
        {r.data && <>
          <Card>
            <Metric label="Chance the flame goes out before the fuel is used up" value={pct(r.data.probability)} />
            <Score r={o.reliability.flex} />
          </Card>
          <Label>Closest NASA tests</Label>
          <div className="space-y-2">{r.data.nearest.slice(0, 3).map((n) => <DropletRun key={n.experiment_id} n={n} est={r.data} />)}</div>
        </>}
      </div>
    </div>
  );
}

function DropletRun({ n, est }) {
  const went = n.extinguished ? "went out early" : "burned to the end";
  const extra = [["co2_fraction", "CO₂"], ["helium_fraction", "helium"]].filter(([k]) => n[k] > 0).map(([k, g]) => `${Math.round(n[k] * 100)}% ${g}`);
  const agrees = (est.probability >= 0.5) === Boolean(n.extinguished);
  return (
    <details className="expander"><summary>FLEX test {n.test_id}: {went}</summary>
      <p className="text-sm text-gray-700">A {n.droplet_diameter_mm.toFixed(1)} mm drop at {Math.round(n.oxygen_pct)}% oxygen{extra.length ? ` with ${extra.join(" and ")}` : ""}, {Math.round(n.pressure_kpa)} kPa: it {went}.</p>
      <Note className="mt-2">{agrees ? "Agrees with" : "Differs from"} the estimate. <a href={n.source_url} target="_blank" rel="noreferrer">NASA record</a></Note>
    </details>
  );
}

function Trust({ r }) {
  const s = r.solid, f = r.flex;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card className="space-y-4">
        <h3 className="trust-title">Solid materials</h3>
        <Callout kind="warning">A rough guide. Knowing only the material predicts about as well.</Callout>
        <div className="trust-stats">
          <Metric label="This model" value={`${tenths(s.accuracy)} / 10`} />
          <Metric label="Material only" value={`${tenths(s.material_only_accuracy)} / 10`} />
          <Metric label="Always guess “keeps burning”" value={`${tenths(s.baseline_accuracy)} / 10`} />
        </div>
        <Note>How many of 10 NASA tests each approach got right, scored only on tests it never saw.</Note>
        <ul className="limitations">
          <li>Learned from {s.n} closely measured runs on {s.groups} samples, so one test can shift it.</li>
          <li>Oxygen and airflow change the answer only a little so far.</li>
          <li>Only five materials, all tested at normal air pressure in orbit.</li>
        </ul>
      </Card>
      <Card className="space-y-4">
        <h3 className="trust-title">Fuel droplets</h3>
        <Callout kind="info">Useful. Oxygen, pressure and added gases clearly change its answer.</Callout>
        <div className="trust-stats">
          <Metric label="This model" value={`${tenths(f.accuracy)} / 10`} />
          <Metric label="Always guess “goes out early”" value={`${tenths(f.baseline_accuracy)} / 10`} />
          <Metric label="Spots drops that burn to the end" value={pct(f.rare_recall)} />
        </div>
        <Note>Most drops went out early, so always guessing that already scores high. The last number shows how often it catches the rarer case.</Note>
        <ul className="limitations">
          <li>Learned from {f.n} NASA droplet tests of heptane and methanol.</li>
          <li>Describes fuel drops, not solid materials. The Material Advisor doesn't use it.</li>
        </ul>
      </Card>
    </div>
  );
}
