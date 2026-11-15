import { useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, Select, SourceLink, Spinner, Toggle, TrustBadge, Value, useAsync, useDebounced } from "../components/ui.jsx";

export default function Explorer({ options, openExperiment }) {
  const [tab, setTab] = useState("investigations");
  const [record, setRecord] = useState(null);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">NASA Data Explorer</h1>
          <p className="mt-1 text-sm text-slate-400">The 19 NASA PSI combustion investigations, every test row, and the report text behind them.</p>
        </div>
        <Toggle value={tab} onChange={setTab} options={[
          { value: "investigations", label: "Investigations" }, { value: "tests", label: "Tests" }, { value: "search", label: "Search reports" }]} />
      </div>
      {tab === "investigations" && <Investigations onTests={(r) => { setRecord(r); setTab("tests"); }} />}
      {tab === "tests" && <Tests options={options} record={record} setRecord={setRecord} openExperiment={openExperiment} />}
      {tab === "search" && <Search />}
    </div>
  );
}

const PHASES = { solid: "Solid", liquid_droplet: "Liquid droplet", gas: "Gas flame", smoke_aerosol: "Smoke / dust" };

function Investigations({ onTests }) {
  const [phase, setPhase] = useState(null);
  const [open, setOpen] = useState(null);
  const list = useAsync(() => api.investigations({ fuel_phase: phase }), [phase]);
  const detail = useAsync(() => (open ? api.investigation(open) : Promise.resolve(null)), [open]);
  return (
    <div className="space-y-4">
      <div className="w-56"><Select label="Fuel type" value={phase} onChange={setPhase} allowEmpty="All"
        options={Object.entries(PHASES).map(([value, label]) => ({ value, label }))} /></div>
      <ErrorBox error={list.error} />
      {list.loading && <Spinner />}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {list.data?.map((i) => (
          <Card key={i.source_record} title={`${i.name} · ${i.source_record}`} subtitle={i.title}>
            <div className="mb-2 text-[11px] uppercase tracking-wide text-flame">{PHASES[i.fuel_phase] || i.fuel_phase}{i.role === "earth_comparison" ? " · Earth gravity" : ""}</div>
            <p className="line-clamp-4 text-xs text-slate-300">{i.summary}</p>
            <div className="mt-3 flex flex-wrap gap-x-3 text-[11px] text-slate-400">
              {i.counts.solid_tests > 0 && <span>{i.counts.solid_tests} solid tests</span>}
              {i.counts.flex_tests > 0 && <span>{i.counts.flex_tests} droplet tests</span>}
              <span>{i.counts.tables} tables</span><span>{i.counts.evidence_passages} passages</span><span>{i.counts.publications} papers</span>
            </div>
            <div className="mt-3 flex gap-3 text-xs">
              <button className="text-sky-300 hover:underline" onClick={() => setOpen(open === i.source_record ? null : i.source_record)}>
                {open === i.source_record ? "Hide details" : "Details"}</button>
              {(i.counts.solid_tests > 0 || i.counts.flex_tests > 0) && <button className="text-sky-300 hover:underline" onClick={() => onTests(i.source_record)}>View tests</button>}
              <SourceLink url={i.url} />
            </div>
            {open === i.source_record && detail.data && (
              <div className="mt-3 space-y-2 border-t border-line pt-3 text-xs text-slate-300">
                <div><b className="text-slate-200">Objective.</b> {detail.data.objective}</div>
                <div><b className="text-slate-200">Approach.</b> {detail.data.approach}</div>
                {detail.data.measured_variables && <div><b className="text-slate-200">Measured.</b> {detail.data.measured_variables}</div>}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}

function Tests({ options, record, setRecord, openExperiment }) {
  const [dataset, setDataset] = useState(record === "PSI-69" ? "flex" : "solid");
  const [f, setF] = useState({ material: null, fuel: null, outcome: null, q: "" });
  const [page, setPage] = useState(1);
  const [picked, setPicked] = useState([]);
  const q = useDebounced(f, 250);
  const params = { dataset, source_record: record, ...q, page, page_size: 20 };
  const res = useAsync(() => api.experiments(params), [JSON.stringify(params)]);
  const cmp = useAsync(() => (picked.length === 2 ? api.compare(picked[0], picked[1]) : Promise.resolve(null)), [picked.join("|")]);
  const set = (k) => (v) => { setF((s) => ({ ...s, [k]: v })); setPage(1); };
  const pages = res.data ? Math.max(1, Math.ceil(res.data.total / 20)) : 1;
  const togglePick = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p.slice(-1), id]));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Toggle value={dataset} onChange={(v) => { setDataset(v); setRecord(null); setPage(1); setPicked([]); setF({ material: null, fuel: null, outcome: null, q: "" }); }}
          options={[{ value: "solid", label: "Solid materials" }, { value: "flex", label: "Fuel droplets" }]} />
        {record && <button onClick={() => setRecord(null)} className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">{record} ✕</button>}
        <div className="w-48">{dataset === "solid"
          ? <Select label="Material" value={f.material} onChange={set("material")} allowEmpty="Any" options={options.solids.materials.map((m) => m.name)} />
          : <Select label="Fuel" value={f.fuel} onChange={set("fuel")} allowEmpty="Any" options={options.flex.fuels} />}</div>
        <div className="w-56">{dataset === "solid"
          ? <Select label="Outcome" value={f.outcome} onChange={set("outcome")} allowEmpty="Any" options={options.solids.outcomes} />
          : <Select label="Outcome" value={f.outcome} onChange={set("outcome")} allowEmpty="Any" options={["Extinction", "Completion", "Disruption"]} />}</div>
        {dataset === "solid" && (
          <label className="block text-xs"><span className="text-slate-300">Search crew notes</span>
            <input value={f.q} onChange={(e) => set("q")(e.target.value)} placeholder="e.g. soot"
              className="mt-1 w-48 rounded-md border border-line bg-ink px-2 py-1.5 text-sm text-slate-100" /></label>
        )}
      </div>
      <ErrorBox error={res.error} />
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-xs">
          <thead className="bg-panel text-slate-400">
            <tr>
              <th className="p-2">Compare</th><th className="p-2">Test</th>
              <th className="p-2">{dataset === "solid" ? "Material" : "Fuel"}</th><th className="p-2">O₂</th>
              <th className="p-2">{dataset === "solid" ? "Airflow" : "Pressure"}</th>
              {dataset === "flex" && <th className="p-2">Droplet</th>}
              <th className="p-2">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {res.data?.items.map((r) => (
              <tr key={r.experiment_id} onClick={() => openExperiment(r.experiment_id)} className="cursor-pointer border-t border-line hover:bg-white/5">
                <td className="p-2" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={picked.includes(r.experiment_id)} onChange={() => togglePick(r.experiment_id)} /></td>
                <td className="p-2 text-sky-300">{r.investigation} {r.test_id}<div className="text-[10px] text-slate-500">{r.date}</div></td>
                <td className="p-2 text-slate-200">{r.material || r.fuel}{r.geometry ? <span className="text-slate-500"> · {r.geometry}</span> : null}</td>
                <td className="p-2"><Value v={r.oxygen_pct} showTrust={false} /></td>
                <td className="p-2">{dataset === "solid" ? (r.airflow_raw || "—") : <Value v={r.pressure_kpa} showTrust={false} />}</td>
                {dataset === "flex" && <td className="p-2"><Value v={r.droplet_diameter_mm} showTrust={false} /></td>}
                <td className="p-2"><span className="text-slate-200">{r.outcome.label}</span> <TrustBadge trust={r.outcome.trust} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {res.loading && <div className="p-3"><Spinner /></div>}
      </div>
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>{res.data?.total ?? 0} tests · click a row for details · tick two to compare</span>
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded border border-line px-2 py-1 disabled:opacity-40">Prev</button>
          <span>Page {page} of {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded border border-line px-2 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
      {cmp.data && <Compare c={cmp.data} onClose={() => setPicked([])} />}
    </div>
  );
}

function Compare({ c, onClose }) {
  const show = (v) => (v && typeof v === "object" && "value" in v ? <Value v={v} showTrust={false} /> : v && typeof v === "object" ? v.label ?? JSON.stringify(v.value ?? "") : String(v ?? "—"));
  return (
    <Card title="Side-by-side comparison" subtitle={c.note} right={<button onClick={onClose} className="text-xs text-slate-400 hover:text-white">Clear</button>}>
      <table className="w-full text-xs">
        <thead className="text-slate-400"><tr><th className="p-1 text-left">Field</th><th className="p-1 text-left">{c.a.investigation} {c.a.test_id}</th><th className="p-1 text-left">{c.b.investigation} {c.b.test_id}</th></tr></thead>
        <tbody>
          {c.fields.filter((r) => !["experiment_id", "dataset", "url", "source_record"].includes(r.field)).map((r) => (
            <tr key={r.field} className={`border-t border-line ${r.different ? "bg-flame/5" : ""}`}>
              <td className="p-1 text-slate-400">{r.field.replaceAll("_", " ")}</td><td className="p-1">{show(r.a)}</td><td className="p-1">{show(r.b)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Search() {
  const [text, setText] = useState("");
  const q = useDebounced(text.trim(), 300);
  const res = useAsync(() => (q ? api.search(q, { k: 10 }) : Promise.resolve(null)), [q]);
  return (
    <div className="space-y-4">
      <input autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Search NASA reports, e.g. “opposed flow flame spread”"
        className="w-full rounded-lg border border-line bg-panel px-4 py-3 text-sm text-slate-100" />
      {res.loading && q && <Spinner />}
      <ErrorBox error={res.error} />
      {res.data?.results.length === 0 && <div className="text-sm text-slate-400">No passages found.</div>}
      <div className="space-y-3">
        {res.data?.results.map((r) => (
          <Card key={r.chunk_id} title={`${r.investigation} · ${r.source_record}`} subtitle={`${r.source_file} · ${r.locator}`}
            right={<SourceLink url={r.url} />}>
            {r.caution && <div className="mb-2 text-xs text-amber-300">⚠ {r.caution}</div>}
            <p className="text-sm text-slate-300">{r.snippet}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
