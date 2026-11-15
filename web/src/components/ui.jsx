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
  nasa_measured: ["NASA measured", "bg-sky-500/15 text-indigo-600 ring-sky-500/30"],
  ai_label: ["Team-verified label", "bg-amber-500/15 text-amber-800 ring-amber-500/30"],
  model_estimate: ["Model estimate", "bg-violet-500/15 text-violet-700 ring-violet-500/30"],
  earth_reference: ["Earth 1g", "bg-emerald-500/15 text-emerald-700 ring-emerald-500/30"],
  no_data: ["No data", "bg-slate-500/15 text-gray-500 ring-slate-500/30"],
};
export const TrustContext = { labels: {} };

export function TrustBadge({ trust }) {
  if (!trust) return null;
  const [label, cls] = TRUST_STYLE[trust] || [trust, TRUST_STYLE.no_data[1]];
  return (
    <span title={TrustContext.labels[trust] || label}
      className={`trust-badge inline-flex items-center px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${cls}`}>
      {label}
    </span>
  );
}

/** Renders the backend's {value, unit, trust, range, note, source} objects. */
export function Value({ v, big = false, showTrust = true }) {
  if (!v) return <span className="text-gray-500">—</span>;
  const main = v.value != null ? fmt(v.value, v.unit) + unitText(v.unit)
    : v.range ? `${fmt(v.range[0], v.unit)}–${fmt(v.range[1], v.unit)}${unitText(v.unit)}` : "—";
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-2 gap-y-1" title={v.note || ""}>
      <span className={big ? "text-3xl font-semibold text-gray-900" : "font-medium text-gray-900"}>{main}</span>
      {v.value != null && v.range && (
        <span className="text-xs text-gray-500">range {fmt(v.range[0], v.unit)}–{fmt(v.range[1], v.unit)}{unitText(v.unit)}</span>
      )}
      {showTrust && <TrustBadge trust={v.trust} />}
    </span>
  );
}

// ---------------------------------------------------------------- layout

export function Card({ title, subtitle, children, className = "", right }) {
  return (
    <section className={`surface-card rounded-lg border border-line p-5 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h3 className="text-sm font-semibold text-gray-900">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p>}
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
    <div role="alert" className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-700">
      {error.errors?.length ? error.errors.map((e, i) => (
        <div key={i}>{e.field ? <b className="mr-1">{e.field}:</b> : null}{e.message}</div>
      )) : String(error.message || error)}
    </div>
  );
}

export function Warning({ children }) {
  return <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-800">{children}</div>;
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div role="status" className="flex items-center gap-2 text-sm text-gray-500">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" />
      {label}
    </div>
  );
}

export function CoverageBadge({ coverage }) {
  if (!coverage) return null;
  const cls = { close: "bg-emerald-500/15 text-emerald-700", partial: "bg-amber-500/15 text-amber-800", none: "bg-red-500/15 text-red-700" }[coverage.level];
  const label = { close: "Close match", partial: "Partial match", none: "No close tests" }[coverage.level] || coverage.label;
  return <span className={`coverage-badge font-medium ${cls}`} title={coverage.label}>{label}</span>;
}

// ---------------------------------------------------------------- inputs

export function Slider({ label, unit, value, min, max, step, onChange, hint, error }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-gray-700">{label}</span>
        <span className="flex items-center gap-1">
          <input type="number" value={value ?? ""} step={step} min={min} max={max}
            onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
            aria-label={label} className="slider-value rounded border border-line px-1.5 py-0.5 text-right text-gray-900" />
          <span className="text-[11px] text-gray-500">{unit}</span>
        </span>
      </div>
      <input aria-label={`${label} slider`} type="range" className="mt-1 w-full" min={min} max={max} step={step} value={value ?? min}
        style={{ "--range-fill": `${Math.max(0, Math.min(100, ((value ?? min) - min) / (max - min || 1) * 100))}%` }}
        onChange={(e) => onChange(Number(e.target.value))} />
      <div className="range-limits"><span>{min}{unit === "%" ? "%" : ""}</span><span>{max}{unit === "%" ? "%" : ""}</span></div>
      {hint && <div className="text-[11px] text-gray-500">{hint}</div>}
      {error && <div className="text-[11px] text-red-700">{error}</div>}
    </label>
  );
}

export function Select({ label, value, onChange, options, allowEmpty }) {
  const id = useId();
  return (
    <div className="block text-xs">
      <label htmlFor={id} className="text-gray-700">{label}</label>
      <select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}
        className="mt-1 w-full rounded-md border border-line bg-ink px-2 py-1.5 text-sm text-gray-900">
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
    <div className="segmented-control">
      {options.map((o) => (
        <button key={o.value} aria-pressed={value === o.value} onClick={() => onChange(o.value)}>
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
  return <a href={url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{children || "NASA source ↗"}</a>;
}

// ---------------------------------------------------------------- Streamlit-style building blocks

/** Eyebrow pill, serif title and one-line caption (Streamlit's ui.init_page). */
export function PageHeader({ eyebrow, title, caption, children }) {
  return (
    <div className="page-heading">
      {eyebrow && <span className="page-eyebrow">{eyebrow}</span>}
      <h1>{title}</h1>
      {caption && <p className="page-caption">{caption}</p>}
      {children}
    </div>
  );
}

/** Small uppercase section label (ui.label). */
export const Label = ({ children, className = "" }) => <div className={`fs-label ${className}`}>{children}</div>;

/** One short plain-language line under a chart or control (ui.note). */
export const Note = ({ children, className = "" }) => <p className={`fs-note ${className}`}>{children}</p>;

export const Caption = ({ children, className = "" }) => <p className={`fs-caption ${className}`}>{children}</p>;

/** st.info / st.warning / st.error. */
export function Callout({ kind = "info", children }) {
  return <div role={kind === "error" ? "alert" : undefined} className={`callout callout-${kind}`}>{children}</div>;
}

/** st.metric: label, big value, optional delta (inverse = lower is better). */
export function Metric({ label, value, delta, inverse = false, help }) {
  const n = typeof delta === "string" ? parseFloat(delta) : delta;
  const good = n == null || Number.isNaN(n) ? null : inverse ? n < 0 : n > 0;
  return (
    <div className="metric" title={help}>
      <div className="metric-label">{label}{help && <span className="metric-help" aria-hidden="true">?</span>}</div>
      <div className="metric-value">{value}</div>
      {delta != null && <div className={`metric-delta ${good == null ? "" : good ? "is-good" : "is-bad"}`}>{n < 0 ? "▼" : "▲"} {delta}</div>}
    </div>
  );
}

/** st.badge with Streamlit colour names. */
export const Badge = ({ color = "gray", children }) => <span className={`fs-badge fs-badge-${color}`}>{children}</span>;

/** Radio list (st.radio). options: [{value, label}] */
export function Radio({ label, value, onChange, options }) {
  const name = useId();
  return (
    <fieldset className="fs-radio">
      <legend>{label}</legend>
      {options.map((o) => (
        <label key={o.value}><input type="radio" name={name} checked={value === o.value} onChange={() => onChange(o.value)} /> <span>{o.label}</span></label>
      ))}
    </fieldset>
  );
}

/** Chip multiselect (st.multiselect). Empty selection means "all". */
export function MultiSelect({ label, options, value, onChange }) {
  const toggle = (o) => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);
  return (
    <div className="fs-multiselect">
      <div className="fs-field-label">{label}{value.length > 0 && <button className="fs-clear" onClick={() => onChange([])}>clear</button>}</div>
      <div className="chips">
        {options.map((o) => <button key={o} type="button" aria-pressed={value.includes(o)} onClick={() => toggle(o)}>{o}</button>)}
      </div>
    </div>
  );
}

export function TextInput({ label, value, onChange, placeholder, type = "text", min, max, step }) {
  const id = useId();
  return (
    <div className="block text-xs">
      <label htmlFor={id} className="text-gray-700">{label}</label>
      <input id={id} type={type} value={value ?? ""} placeholder={placeholder} min={min} max={max} step={step}
        onChange={(e) => onChange(type === "number" ? (e.target.value === "" ? 0 : Number(e.target.value)) : e.target.value)}
        className="mt-1 w-full rounded-md border border-line px-2 py-1.5 text-sm text-gray-900" />
    </div>
  );
}

/** Scrollable table (st.dataframe). columns: [{key, label, link?, format?}] */
export function DataTable({ columns, rows, maxHeight = 420 }) {
  const show = (c, r) => {
    const v = r[c.key];
    if (c.format) return c.format(v, r);
    if (v == null || v === "") return <span className="text-gray-400">—</span>;
    if (c.link) return <a href={v} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{c.linkText || "open ↗"}</a>;
    if (typeof v === "number") return fmt(v);
    if (typeof v === "boolean") return v ? "Yes" : "No";
    return String(v);
  };
  return (
    <div role="region" aria-label="Data table" tabIndex={0} className="scroll-region data-table" style={{ maxHeight }}>
      <table>
        <thead><tr>{columns.map((c) => <th key={c.key}>{c.label ?? c.key}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{columns.map((c) => <td key={c.key} title={typeof r[c.key] === "string" && !c.link ? r[c.key] : undefined}>{show(c, r)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- markdown (no HTML injection: builds React elements)

function inline(text, keyBase = "") {
  const out = [];
  const re = /(\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)|`([^`]+)`|(?<![\w*])[_*]([^_*\n]+)[_*](?![\w*]))/g;
  let last = 0, m, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = `${keyBase}-${i++}`;
    if (m[2] != null) out.push(<strong key={k}>{inline(m[2], k)}</strong>);
    else if (m[3] != null) out.push(/^https?:\/\//.test(m[4]) ? <a key={k} href={m[4]} target="_blank" rel="noreferrer">{m[3]}</a> : m[3]);
    else if (m[5] != null) out.push(<code key={k}>{m[5]}</code>);
    else out.push(<em key={k}>{m[6]}</em>);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text, className = "" }) {
  const blocks = [];
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  let para = [], list = null, quote = [];
  const flushPara = () => { if (para.length) blocks.push(<p key={blocks.length}>{inline(para.join(" "), blocks.length)}</p>); para = []; };
  const flushList = () => { if (list) { const T = list.ordered ? "ol" : "ul"; blocks.push(<T key={blocks.length}>{list.items.map((it, j) => <li key={j}>{inline(it, `${blocks.length}-${j}`)}</li>)}</T>); } list = null; };
  const flushQuote = () => { if (quote.length) blocks.push(<blockquote key={blocks.length}>{inline(quote.join(" "), blocks.length)}</blockquote>); quote = []; };
  const flush = () => { flushPara(); flushList(); flushQuote(); };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    const li = line.match(/^\s*[-*•]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const q = line.match(/^>\s?(.*)$/);
    if (!line.trim()) { flush(); continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { flush(); blocks.push(<hr key={blocks.length} />); continue; }
    if (h) { flush(); blocks.push(<h4 key={blocks.length}>{inline(h[2], blocks.length)}</h4>); continue; }
    if (li || ol) {
      flushPara(); flushQuote();
      const ordered = !!ol && !li;
      if (!list || list.ordered !== ordered) { flushList(); list = { ordered, items: [] }; }
      list.items.push((li || ol)[1]); continue;
    }
    if (q) { flushPara(); flushList(); quote.push(q[1]); continue; }
    if (list && /^\s{2,}/.test(raw)) { list.items[list.items.length - 1] += " " + line.trim(); continue; }
    flushList(); flushQuote(); para.push(line.trim());
  }
  flush();
  return <div className={`markdown ${className}`}>{blocks}</div>;
}
