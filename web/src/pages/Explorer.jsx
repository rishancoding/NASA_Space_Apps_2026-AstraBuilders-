// NASA Data Explorer: the investigations and the cleaned test data (data/clean/) in plain terms.
import { useMemo, useState } from "react";
import { fs } from "../api.js";
import { TestsScatter } from "../components/charts.jsx";
import { Caption, Card, DataTable, ErrorBox, MultiSelect, Note, PageHeader, Spinner, Toggle, useAsync } from "../components/ui.jsx";

const TABS = [["investigations", "Investigations"], ["solids", "Solid material tests"], ["flex", "Fuel droplet tests"]];
const PHASE = { solid: "Solid materials", liquid_droplet: "Fuel droplets", gas: "Gas flames", smoke_aerosol: "Smoke and dust" };
const RESULT = { "sustained burn": "Kept burning", "burned, then went out": "Went out", "brief flame, not sustained": "Brief flame",
  "suppressed (agent/N2)": "Put out by gas", "no ignition": "Never lit", "not usable": "Unclear" };
const uniq = (xs) => [...new Set(xs.filter((x) => x != null && x !== ""))].sort();

export default function Explorer() {
  const [tab, setTab] = useState("investigations");
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="19 NASA investigations" title="NASA Data Explorer"
        caption="The NASA fire experiments behind this app, and every test result we use.">
        <Toggle value={tab} onChange={setTab} options={TABS.map(([value, label]) => ({ value, label }))} />
      </PageHeader>
      {tab === "investigations" && <Investigations />}
      {tab === "solids" && <SolidTests />}
      {tab === "flex" && <DropletTests />}
    </div>
  );
}

function Investigations() {
  const cat = useAsync(() => fs.catalog(), []);
  if (cat.loading) return <Spinner />;
  if (cat.error) return <ErrorBox error={cat.error} />;
  const groups = Object.keys(PHASE).map((k) => [k, cat.data.filter((r) => r.fuel_phase === k)]).filter(([, rows]) => rows.length);
  return (
    <div className="space-y-6">
      {groups.map(([phase, rows]) => (
        <section key={phase} className="space-y-2">
          <div className="fs-label">{PHASE[phase]}</div>
          {rows.map((r) => (
            <details key={r.source_record} className="expander">
              <summary><b>{r.investigation_name}</b></summary>
              <p className="text-sm leading-relaxed text-gray-700">{r.summary}</p>
              <a className="mt-3 inline-block text-sm text-indigo-600 hover:underline" href={r.url} target="_blank" rel="noreferrer">Open the NASA record ↗</a>
            </details>
          ))}
        </section>
      ))}
    </div>
  );
}

function toCsv(rows, cols) {
  const esc = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : String(v));
  return [cols.map((c) => c.label).join(","), ...rows.map((r) => cols.map((c) => esc(r[c.key])).join(","))].join("\n");
}

function download(rows, cols, name) {
  const url = URL.createObjectURL(new Blob([toCsv(rows, cols)], { type: "text/csv" }));
  Object.assign(document.createElement("a"), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}

const SOLID_COLS = [{ key: "investigation_name", label: "Experiment" }, { key: "test_id", label: "Test" }, { key: "test_date", label: "Date" },
  { key: "material", label: "Material" }, { key: "sample_geometry", label: "Shape" }, { key: "oxygen_pct", label: "Oxygen %" },
  { key: "airflow_raw", label: "Airflow (cm/s)" }, { key: "result", label: "Result" }, { key: "notes", label: "Crew notes" },
  { key: "source_url", label: "NASA record", link: true }];

function SolidTests() {
  const s = useAsync(() => fs.solids(), []);
  const [mats, setMats] = useState([]);
  const [recs, setRecs] = useState([]);
  const [outs, setOuts] = useState([]);
  const rows = useMemo(() => (s.data || []).map((r) => ({ ...r, result: RESULT[r.outcome_group] || r.outcome_group || "Unclear" })), [s.data]);
  const v = rows.filter((r) => (!mats.length || mats.includes(r.material)) && (!recs.length || recs.includes(r.investigation_name))
    && (!outs.length || outs.includes(r.result)));
  if (s.loading) return <Spinner />;
  if (s.error) return <ErrorBox error={s.error} />;
  return (
    <div className="space-y-4">
      <Card className="grid gap-5 md:grid-cols-3">
        <MultiSelect label="Material" options={uniq(rows.map((r) => r.material))} value={mats} onChange={setMats} />
        <MultiSelect label="Experiment" options={uniq(rows.map((r) => r.investigation_name))} value={recs} onChange={setRecs} />
        <MultiSelect label="Result" options={uniq(rows.map((r) => r.result))} value={outs} onChange={setOuts} />
      </Card>
      <Card>
        <TestsScatter tests={v} height={400} />
        <Note>Each mark is one test, placed by oxygen and airflow and colored by what the flame did.</Note>
      </Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Caption>{v.length} of {rows.length} tests on the space station. Results checked by our team against crew notes.</Caption>
        <button className="secondary-button" onClick={() => download(v, SOLID_COLS, "nasa_solid_tests.csv")}>Download CSV</button>
      </div>
      <DataTable rows={v} maxHeight={460} columns={SOLID_COLS} />
    </div>
  );
}

const FLEX_COLS = [{ key: "test_id", label: "Test" }, { key: "test_date", label: "Date" }, { key: "fuel", label: "Fuel" },
  { key: "oxygen_pct", label: "Oxygen %" }, { key: "co2_pct", label: "CO₂ %" }, { key: "helium_pct", label: "Helium %" },
  { key: "pressure_kpa", label: "Pressure (kPa)" }, { key: "droplet_diameter_mm", label: "Drop size (mm)" },
  { key: "burn_time_s", label: "Burn time (s)" }, { key: "result", label: "Result" }, { key: "source_url", label: "NASA record", link: true }];

function DropletTests() {
  const d = useAsync(() => fs.flex(), []);
  const [fuels, setFuels] = useState([]);
  const [outs, setOuts] = useState([]);
  if (d.loading) return <Spinner />;
  if (d.error) return <ErrorBox error={d.error} />;
  const v = d.data.filter((r) => (!fuels.length || fuels.includes(r.fuel)) && (!outs.length || outs.includes(r.result)));
  return (
    <div className="space-y-4">
      <Card className="grid gap-5 md:grid-cols-2">
        <MultiSelect label="Fuel" options={uniq(d.data.map((r) => r.fuel))} value={fuels} onChange={setFuels} />
        <MultiSelect label="Result" options={uniq(d.data.map((r) => r.result))} value={outs} onChange={setOuts} />
      </Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Caption>{v.length} of {d.data.length} FLEX tests: single fuel drops lit on the space station.</Caption>
        <button className="secondary-button" onClick={() => download(v, FLEX_COLS, "nasa_droplet_tests.csv")}>Download CSV</button>
      </div>
      <DataTable rows={v} maxHeight={520} columns={FLEX_COLS} />
    </div>
  );
}
