import { useEffect, useId, useRef, useState } from "react";

// ---------------------------------------------------------------- hooks

/** Run an async function when deps change; returns {data, error, loading}. Ignores stale responses. */
export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const seq = useRef(0);
  useEffect(() => {
    const id = ++seq.current;
    setState({ data: null, loading: true, error: null });
    fn()
      .then((data) => id === seq.current && setState({ data, error: null, loading: false }))
      .catch((error) => id === seq.current && setState({ data: null, error, loading: false }));
    return () => { seq.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function useDebounced(value, ms = 200) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// ---------------------------------------------------------------- formatting

export function fmt(x, unit) {
  if (x == null) return "—";
  if (unit === "probability") return `${Math.round(x * 100)}%`;
  const abs = Math.abs(x);
  const s = abs >= 100 ? x.toFixed(0) : abs >= 10 ? x.toFixed(1) : abs >= 1 ? x.toFixed(2) : x.toFixed(3);
  return String(Number(s));
}

const UNIT_SUFFIX = { probability: "", "%": "%", "mole fraction": "" };
export const unitText = (u) => (u in UNIT_SUFFIX ? UNIT_SUFFIX[u] : u ? ` ${u}` : "");

// ---------------------------------------------------------------- trust labels

const TRUST_STYLE = {
  nasa_measured: ["NASA measured", "bg-sky-500/15 text-sky-300 ring-sky-500/30"],
  ai_label: ["AI-read label", "bg-amber-500/15 text-amber-300 ring-amber-500/30"],
  model_estimate: ["Model estimate", "bg-violet-500/15 text-violet-300 ring-violet-500/30"],
  earth_reference: ["Earth 1g", "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30"],
  no_data: ["No data", "bg-slate-500/15 text-slate-400 ring-slate-500/30"],
};
export const TrustContext = { labels: {} };

export function TrustBadge({ trust }) {
  if (!trust) return null;
  const [label, cls] = TRUST_STYLE[trust] || [trust, TRUST_STYLE.no_data[1]];
  return (
    <span title={TrustContext.labels[trust] || label}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${cls}`}>
      {label}
    </span>
  );
}

/** Renders the backend's {value, unit, trust, range, note, source} objects. */
export function Value({ v, big = false, showTrust = true }) {
  if (!v) return <span className="text-slate-500">—</span>;
  const main = v.value != null ? fmt(v.value, v.unit) + unitText(v.unit)
    : v.range ? `${fmt(v.range[0], v.unit)}–${fmt(v.range[1], v.unit)}${unitText(v.unit)}` : "—";
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-2 gap-y-1" title={v.note || ""}>
      <span className={big ? "text-3xl font-semibold text-white" : "font-medium text-slate-100"}>{main}</span>
      {v.value != null && v.range && (
        <span className="text-xs text-slate-400">range {fmt(v.range[0], v.unit)}–{fmt(v.range[1], v.unit)}{unitText(v.unit)}</span>
      )}
      {showTrust && <TrustBadge trust={v.trust} />}
    </span>
  );
}

// ---------------------------------------------------------------- layout

export function Card({ title, subtitle, children, className = "", right }) {
  return (
    <section className={`surface-card rounded-2xl border border-line p-5 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h3 className="text-sm font-semibold text-white">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
      {error.errors?.length ? error.errors.map((e, i) => (
        <div key={i}>{e.field ? <b className="mr-1">{e.field}:</b> : null}{e.message}</div>
      )) : String(error.message || error)}
    </div>
  );
}

export function Warning({ children }) {
  return <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">{children}</div>;
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div role="status" className="flex items-center gap-2 text-sm text-slate-400">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" />
      {label}
    </div>
  );
}

export function CoverageBadge({ coverage }) {
  if (!coverage) return null;
  const cls = { close: "bg-emerald-500/15 text-emerald-300", partial: "bg-amber-500/15 text-amber-300", none: "bg-red-500/15 text-red-300" }[coverage.level];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`} title={coverage.label}>{coverage.label}</span>;
}

// ---------------------------------------------------------------- inputs

export function Slider({ label, unit, value, min, max, step, onChange, hint, error }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-slate-300">{label}</span>
        <span className="flex items-center gap-1">
          <input type="number" value={value ?? ""} step={step} min={min} max={max}
            onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
            className="w-20 rounded border border-line bg-ink px-1.5 py-0.5 text-right text-slate-100" />
          <span className="w-10 text-slate-400">{unit}</span>
        </span>
      </div>
      <input aria-label={`${label} slider`} type="range" className="mt-1 w-full" min={min} max={max} step={step} value={value ?? min}
        onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <div className="text-[11px] text-slate-500">{hint}</div>}
      {error && <div className="text-[11px] text-red-300">{error}</div>}
    </label>
  );
}

export function Select({ label, value, onChange, options, allowEmpty }) {
  const id = useId();
  return (
    <div className="block text-xs">
      <label htmlFor={id} className="text-slate-300">{label}</label>
      <select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}
        className="mt-1 w-full rounded-md border border-line bg-ink px-2 py-1.5 text-sm text-slate-100">
        {allowEmpty && <option value="">{allowEmpty}</option>}
        {options.map((o) => (
          <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? o}</option>
        ))}
      </select>
    </div>
  );
}

export function Toggle({ value, onChange, options }) {
  return (
    <div className="inline-flex max-w-full flex-wrap rounded-xl border border-line bg-ink/60 p-1">
      {options.map((o) => (
        <button key={o.value} aria-pressed={value === o.value} onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1.5 text-sm transition ${value === o.value ? "bg-flame text-white" : "text-slate-300 hover:text-white"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Icon({ name, className = "h-5 w-5" }) {
  const paths = {
    advisor: <><path d="m12 3 8 4v6c0 4-8 8-8 8s-8-4-8-8V7z"/><path d="m8 12 3 3 5-6"/></>,
    predictor: <><path d="M3 12h4l3-8 4 16 3-8h4"/></>,
    explorer: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6m-3-3v6"/></>,
    model: <><path d="M4 3v17h17M8 16v-5m5 5V7m5 9V4"/></>,
    chat: <><path d="M20 14a3 3 0 0 1-3 3H8l-5 4V6a3 3 0 0 1 3-3h11a3 3 0 0 1 3 3zM7 8h9M7 12h6"/></>,
  };
  return <svg aria-hidden="true" className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{paths[name] || paths.predictor}</svg>;
}

export function SourceLink({ url, children }) {
  if (!url) return children || null;
  return <a href={url} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline">{children || "NASA source ↗"}</a>;
}
