import { api } from "../api.js";
import { ErrorBox, SourceLink, Spinner, TrustBadge, Value, useAsync } from "./ui.jsx";

const LABELS = {
  oxygen_pct: "Oxygen", oxygen_final_pct: "Oxygen at end", airflow_cm_s: "Airflow", pressure_kpa: "Pressure",
  burn_time_s: "Burn time", co2_fraction: "CO₂ fraction", helium_fraction: "Helium fraction", nitrogen_fraction: "Nitrogen fraction",
  droplet_diameter_mm: "Droplet diameter", extinction_diameter_mm: "Diameter at extinction",
};

/** Slide-over panel showing one NASA test in full. */
export default function ExperimentDrawer({ id, onClose }) {
  const { data, error, loading } = useAsync(() => (id ? api.experiment(id) : Promise.resolve(null)), [id]);
  if (!id) return null;
  const valueFields = data ? Object.entries(LABELS).filter(([k]) => data[k]) : [];

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <aside className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-panel p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-xs text-slate-400">{data?.investigation} · {data?.source_record}</div>
            <h2 className="text-lg font-semibold text-white">Test {data?.test_id ?? "…"} {data?.date ? `· ${data.date}` : ""}</h2>
            <div className="break-all text-[11px] text-slate-500">{id}</div>
          </div>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-slate-400 hover:bg-white/10 hover:text-white">✕</button>
        </div>
        {loading && <Spinner />}
        <ErrorBox error={error} />
        {data && (
          <div className="space-y-5 text-sm">
            <div className="rounded-lg bg-ink p-3">
              <div className="text-xs text-slate-400">Outcome</div>
              <div className="mt-1 flex items-center gap-2 font-medium text-white">
                {data.outcome?.label} <TrustBadge trust={data.outcome?.trust} />
              </div>
              <div className="mt-2 text-xs text-slate-400">
                {data.material ? <>Material: <span className="text-slate-200">{data.material}</span> ({data.material_raw}) · {data.geometry}</> : <>Fuel: <span className="text-slate-200">{data.fuel}</span></>}
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-3">
              {valueFields.map(([k, label]) => (
                <div key={k}><dt className="text-xs text-slate-400">{label}</dt><dd><Value v={data[k]} /></dd></div>
              ))}
              {data.dimensions && Object.entries(data.dimensions).filter(([, v]) => v.value != null).map(([k, v]) => (
                <div key={k}><dt className="text-xs text-slate-400">{k.replace("_mm", "").replace("_", " ")}</dt><dd><Value v={v} /></dd></div>
              ))}
            </dl>
            {data.airflow_raw && <div className="text-xs text-slate-400">Airflow as recorded: <span className="text-slate-200">{data.airflow_raw}</span></div>}

            {data.crew_notes && (
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Crew / report notes</h4>
                <p className="whitespace-pre-wrap rounded-lg bg-ink p-3 text-slate-200">{data.crew_notes}</p>
              </div>
            )}

            {data.stages?.length > 0 && (
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Flame events</h4>
                <ol className="space-y-2">
                  {data.stages.map((s) => (
                    <li key={s.order} className="rounded-lg bg-ink p-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-slate-200">{s.order}. {s.event.replaceAll("_", " ")}</span>
                        {s.airflow_cm_s?.value != null && <Value v={s.airflow_cm_s} showTrust={false} />}
                        {s.used_for_training && <span className="text-[10px] text-emerald-300">screened event</span>}
                      </div>
                      {s.evidence_quote && <div className="mt-1 text-xs italic text-slate-400">“{s.evidence_quote}”</div>}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {data.earth_reference?.length > 0 && (
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Earth-gravity limits for this material</h4>
                <ul className="space-y-1 text-xs">
                  {data.earth_reference.map((e, i) => (
                    <li key={i}>{e.configuration}: ULOI <Value v={e.uloi_oxygen_pct} showTrust={false} />, MOC <Value v={e.moc_oxygen_pct} showTrust={false} /></li>
                  ))}
                </ul>
              </div>
            )}

            {data.exclusion_reasons?.length > 0 && (
              <div className="text-xs text-slate-400">Not used for model training: {data.exclusion_reasons.join(", ").replaceAll("_", " ")}</div>
            )}

            <div className="border-t border-line pt-3 text-xs text-slate-400">
              <SourceLink url={data.source?.url || data.url} /> {data.source?.file && <>· {data.source.file} {data.source.locator}</>}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
