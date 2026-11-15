// Research Assistant: same structure and wording as app/pages/assistant.py.
import { useEffect, useRef, useState } from "react";
import { fs } from "../api.js";
import { SweepChart, TestsScatter, TrendBars, plottable } from "../components/charts.jsx";
import { Callout, Caption, Card, ErrorBox, Markdown, Metric, Note, PageHeader } from "../components/ui.jsx";
import { Citations } from "./Advisor.jsx";

const BASE_SUGGESTED = ["What happens when oxygen increases?", "Compare how PMMA and Nomex burn.",
  "Which materials have the most test data?", "Why do some flames go out?"];

function binLabel(b) {
  const m = String(b).match(/[[(]\s*([\d.]+)\s*,\s*([\d.]+)\s*[\])]/);
  if (!m) return String(b);
  const lo = +m[1], hi = +m[2];
  return lo === 0 ? `under ${hi}%` : `${lo}-${hi}%`;
}

const CHART_TOOLS = new Set(["find_tests", "condition_trends", "predict_sustained_burning", "predict_droplet_extinction", "prediction_sweep"]);

function Charts({ calls }) {
  const usable = (calls || []).filter(({ name, result: o }) => CHART_TOOLS.has(name) && (o.tests?.length || o.stages_by_oxygen_bin?.length
    || o.probability != null || (o.points || []).some((p) => p.probability != null)));
  if (!usable.length) return null;
  return (
    <details className="expander"><summary>Charts</summary><div className="space-y-5">
      {usable.map(({ name, result: o }, i) => {
        if (name === "find_tests" && plottable(o.tests)) return <TestsScatter key={i} tests={o.tests} title={`The NASA tests behind this answer (${o.returned})`} />;
        if (name === "condition_trends") return <TrendBars key={i} title={`How often ${o.material} kept burning, by oxygen level`}
          rows={o.stages_by_oxygen_bin.map((b) => ({ bin: binLabel(b.bin), share: b.sustained / b.stages, text: `${b.sustained}/${b.stages}` }))} />;
        if (name === "predict_sustained_burning") return <Metric key={i} label={`${o.material} at ${o.oxygen_pct}% oxygen, ${o.airflow_cm_s} cm/s`}
          value={`${Math.round(o.probability * 100)}% chance it keeps burning`} help={`Model estimate. Confidence: ${o.reliability?.rating}.`} />;
        if (name === "predict_droplet_extinction") return <Metric key={i} label={`${o.fuel} droplet at ${o.oxygen_pct}% oxygen, ${o.pressure_kpa} kPa`}
          value={`${Math.round(o.probability * 100)}% chance it goes out early`} help={`Model estimate. Confidence: ${o.reliability?.rating}.`} />;
        if (name === "prediction_sweep") {
          const pts = o.points.filter((p) => p.probability != null);
          return <div key={i}><SweepChart points={pts} xKey={o.varied} title={`${o.material || o.fuel}: how the estimate changes with ${o.varied.split("_")[0]}`} />
            {o.points_in_tested_range < o.points.length && <Note>Estimates are shown only for tested conditions.</Note>}</div>;
        }
        return null;
      })}
    </div></details>
  );
}

function sourcesFor(calls) {
  const items = [];
  const walk = (o) => {
    if (Array.isArray(o)) return o.forEach(walk);
    if (!o || typeof o !== "object") return;
    const url = o.source_url || o.url;
    if (url && String(url).startsWith("http")) {
      const name = o.investigation || o.name || o.label || "";
      const rec = o.source_record || "";
      let label = name && rec && !name.includes(rec) ? `${name} (${rec})` : name || rec || url;
      if (o.title && o.title !== name) label = `${name}: ${o.title} (${rec})`;
      items.push({ label: String(label).slice(0, 120), url });
    }
    Object.values(o).forEach(walk);
  };
  (calls || []).forEach((c) => walk(c.result));
  const seen = new Set();
  return items.filter((x) => !seen.has(x.url) && seen.add(x.url)).slice(0, 3);
}

const SECTIONS = ["Answer", "Evidence", "What it means", "Prediction reliability", "Sources", "In short"];
const HEADING = new RegExp(`^(?:#{1,4}[ \\t]+)?\\*\\*(${SECTIONS.join("|")})\\*\\*[ \\t]*[:\\-–—]?[ \\t]*|^#{1,4}[ \\t]+(${SECTIONS.join("|")})[ \\t]*:?[ \\t]*$`, "gmi");

function splitSections(text) {
  const marks = [...text.matchAll(HEADING)];
  if (!marks.length) return null;
  const out = {};
  const lead = text.slice(0, marks[0].index).trim();
  marks.forEach((m, i) => {
    const name = SECTIONS.find((x) => x.toLowerCase() === (m[1] || m[2]).toLowerCase());
    const end = i + 1 < marks.length ? marks[i + 1].index : text.length;
    out[name] = `${out[name] || ""}\n\n${text.slice(m.index + m[0].length, end)}`.trim();
  });
  if (lead) out.Answer = `${lead}\n\n${out.Answer || ""}`.trim();
  return out;
}

function AnswerView({ text, calls }) {
  const parts = splitSections(text);
  const srcs = sourcesFor(calls);
  if (!parts) return <div className="space-y-3"><Markdown text={text} /><Charts calls={calls} />
    {srcs.length > 0 && <details className="expander"><summary>Sources</summary><Citations items={srcs} /></details>}</div>;
  const details = [["Evidence", "NASA tests"], ["What it means", "What it means"], ["Prediction reliability", "How sure is the estimate?"]].filter(([n]) => parts[n]);
  return (
    <div className="space-y-3">
      <Markdown text={parts.Answer || parts["In short"] || ""} />
      <Charts calls={calls} />
      {details.length > 0 && <details className="expander"><summary>More detail</summary><div className="space-y-3">
        {details.map(([n, label]) => <div key={n}><b>{label}</b><Markdown text={parts[n]} /></div>)}</div></details>}
      {(parts.Sources || srcs.length > 0) && <details className="expander"><summary>Sources</summary>
        {parts.Sources ? <Markdown text={parts.Sources} /> : <Citations items={srcs} />}</details>}
    </div>
  );
}

export default function Assistant({ fsOptions, advisor, chat, setChat }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const end = useRef(null);
  const online = fsOptions.assistant_online;
  const ctx = advisor.result;
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [chat.view.length, busy]);

  let suggested = BASE_SUGGESTED;
  if (ctx) {
    const pairs = (ctx.comparisons || []).slice(0, 3).map((x) => `How do ${x.higher} and ${x.lower} compare?`);
    suggested = [...pairs, "Explain my Material Advisor results.", ...BASE_SUGGESTED].slice(0, 4);
  }

  async function send(q) {
    q = (q ?? text).trim();
    if (!q || busy) return;
    setChat((c) => ({ ...c, view: [...c.view, { role: "user", text: q }] }));
    setText(""); setBusy(true); setError(null);
    try {
      const out = await fs.chat(q, chat.sessionId, ctx);
      const failed = ["error", "tool_limit"].includes(out.stop_reason);
      setChat((c) => ({ sessionId: out.session_id, view: [...c.view, { role: "assistant", text: out.text, calls: out.tool_calls, failed }] }));
    } catch (e) {
      setError(e);
      setChat((c) => ({ ...c, view: c.view.slice(0, -1) }));
      setText(q);
    } finally { setBusy(false); }
  }
  async function clear() {
    if (chat.sessionId) fs.clearChat(chat.sessionId).catch(() => {});
    setChat({ sessionId: null, view: [] });
  }

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Ask in plain English" title="Research Assistant" caption="Answers come from NASA's fire test data, with sources." />
      <div className="assistant-page space-y-4">
        {!online && <Callout kind="info">The AI is offline, so answers show the most relevant NASA report passages.</Callout>}
        {ctx && <Caption>Using your Material Advisor results · {ctx.scenario.oxygen_pct}% oxygen · {ctx.scenario.airflow_cm_s} cm/s airflow</Caption>}

        <div className="space-y-4">
          {chat.view.map((m, i) => (
            <div key={i} className={`chat-message chat-${m.role}`}>
              <div className="chat-avatar" aria-hidden="true">{m.role === "user" ? "You" : "AI"}</div>
              <div className="chat-body">{m.role === "assistant" ? <AnswerView text={m.text} calls={m.calls} /> : <Markdown text={m.text} />}</div>
            </div>
          ))}
          {busy && <div className="chat-message chat-assistant"><div className="chat-avatar" aria-hidden="true">AI</div>
            <div className="chat-body chat-status"><span className="status-dot" /> Working on your answer...</div></div>}
          <ErrorBox error={error} />
        </div>

        {!chat.view.length && !busy && (
          <div className="grid gap-3 sm:grid-cols-2">
            {suggested.map((q) => <button key={q} className="suggestion" onClick={() => send(q)}>{q}</button>)}
          </div>
        )}
        {chat.view.length > 0 && <button className="secondary-button" onClick={clear}>Clear conversation</button>}
        <div ref={end} />
      </div>
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <Card className="flex gap-2 !p-2">
          <input aria-label="Ask about NASA's fire experiments" value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Ask about NASA's fire experiments..." className="flex-1 !border-0 !bg-transparent px-3 py-2 text-sm text-gray-900 !shadow-none" />
          <button disabled={busy || !text.trim()} className="primary-button">Send</button>
        </Card>
      </form>
    </div>
  );
}
