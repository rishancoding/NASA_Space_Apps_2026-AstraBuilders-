import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { ErrorBox, Spinner } from "./ui.jsx";

const STARTERS = [
  "How does oxygen concentration affect flame spread in microgravity?",
  "Which NASA experiments investigated airflow and solid-fuel flammability?",
  "What gaps exist in our understanding of fire safety on the Moon?",
  "Compare how PMMA and Nomex behaved in the BASS tests.",
];

/** Docked research-assistant chat. Sends the whole conversation each time (the API is stateless). */
export default function ChatPanel({ open, onClose, context }) {
  const [messages, setMessages] = useState([]);
  const [meta, setMeta] = useState([]); // per assistant message: {citations, tool_calls}
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const end = useRef(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" }); // braces: newer browsers return a Promise here
  }, [messages, busy]);

  async function send(content) {
    const q = (content ?? text).trim();
    if (!q || busy) return;
    const next = [...messages, { role: "user", content: q }];
    setMessages(next); setText(""); setBusy(true); setError(null);
    try {
      const r = await api.chat(next, context);
      setMessages([...next, { role: "assistant", content: r.answer || "(no answer)" }]);
      setMeta((m) => [...m, { citations: r.citations, tool_calls: r.tool_calls, model: r.model }]);
    } catch (e) {
      setError(e); setMessages(messages);
      setText(q);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;
  let a = -1;
  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[420px] flex-col border-l border-line bg-panel pt-14 lg:pt-[57px]">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <div className="font-semibold text-white">Research assistant</div>
          <div className="text-[11px] text-slate-400">Answers from NASA PSI data and the trained models, with citations.</div>
        </div>
        <button onClick={onClose} className="rounded-md px-2 py-1 text-slate-400 hover:bg-white/10 hover:text-white">✕</button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4 text-sm">
        {context && <div className="rounded-md bg-ink px-2 py-1 text-[11px] text-slate-400">Using context from: {context.page?.replaceAll("_", " ")}</div>}
        {messages.length === 0 && (
          <div className="space-y-2">
            <div className="text-xs text-slate-400">Try asking:</div>
            {STARTERS.map((s) => (
              <button key={s} onClick={() => send(s)} className="block w-full rounded-lg border border-line px-3 py-2 text-left text-xs text-slate-300 hover:border-flame hover:text-white">{s}</button>
            ))}
          </div>
        )}
        {messages.map((m, i) => {
          if (m.role === "assistant") a += 1;
          const info = m.role === "assistant" ? meta[a] : null;
          return (
            <div key={i} className={m.role === "user" ? "ml-8 rounded-lg bg-flame/15 p-3 text-slate-100" : "mr-4 rounded-lg bg-ink p-3 text-slate-200"}>
              <div className="whitespace-pre-wrap">{m.content}</div>
              {info?.citations?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 border-t border-line pt-2">
                  {info.citations.slice(0, 8).map((c, j) => (
                    <a key={j} href={c.url} target="_blank" rel="noreferrer" className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] text-sky-300 hover:underline">{c.record}</a>
                  ))}
                </div>
              )}
              {info?.tool_calls?.length > 0 && (
                <details className="mt-1 text-[10px] text-slate-500">
                  <summary className="cursor-pointer">Looked up: {info.tool_calls.map((t) => t.tool).join(", ")}</summary>
                  <pre className="mt-1 whitespace-pre-wrap">{JSON.stringify(info.tool_calls, null, 1)}</pre>
                </details>
              )}
            </div>
          );
        })}
        {busy && <Spinner label="Looking through NASA data…" />}
        <ErrorBox error={error} />
        <div ref={end} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2 border-t border-line p-3">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about NASA combustion data…"
          className="flex-1 rounded-md border border-line bg-ink px-3 py-2 text-sm text-slate-100" />
        <button disabled={busy || !text.trim()} className="rounded-md bg-flame px-3 text-sm font-medium text-white disabled:opacity-50">Send</button>
      </form>
    </aside>
  );
}
