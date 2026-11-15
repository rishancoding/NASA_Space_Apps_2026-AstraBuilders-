import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { ErrorBox, Spinner, useAsync } from "./ui.jsx";

const STARTERS = [
  "What happens when oxygen increases?",
  "Compare PMMA and Nomex.",
];

/** Docked research-assistant chat. Sends the whole conversation each time (the API is stateless). */
export default function ChatPanel({ open, onClose, context }) {
  const health = useAsync(() => open ? api.health() : Promise.resolve(null), [open]);
  const enabled = health.data?.chat_configured === true;
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
    if (!q || busy || !enabled) return;
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
    <aside id="research-assistant" aria-label="Research assistant" className="assistant-panel fixed inset-y-0 right-0 z-30 flex w-full max-w-[420px] flex-col border-l border-line">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <div className="font-medium text-gray-900">Ask the assistant</div>
        </div>
        <button aria-label="Close research assistant" onClick={onClose} className="panel-close">✕</button>
      </div>

      <div className="scroll-region flex-1 space-y-3 overflow-y-auto p-4 text-sm">
        {health.loading && <Spinner label="Checking assistant availability…" />}
        <ErrorBox error={health.error} />
        {health.data && !enabled && <div role="status" className="rounded-xl border border-line bg-ink p-3 text-gray-700">
          <p className="font-medium">AI chat is off on this computer.</p>
          <p className="mt-1 text-xs">NASA data and model estimates still work. A provider key is needed to enable generated answers.</p>
        </div>}
        {context && <div className="rounded-md bg-ink px-2 py-1 text-[11px] text-gray-500">Using context from: {context.page?.replaceAll("_", " ")}</div>}
        {enabled && messages.length === 0 && (
          <div className="space-y-2">
            <div className="text-xs text-gray-500">Try asking:</div>
            {STARTERS.map((s) => (
              <button key={s} onClick={() => send(s)} className="block w-full rounded-lg border border-line px-3 py-2 text-left text-xs text-gray-700 hover:border-flame hover:text-gray-900">{s}</button>
            ))}
          </div>
        )}
        {messages.map((m, i) => {
          if (m.role === "assistant") a += 1;
          const info = m.role === "assistant" ? meta[a] : null;
          return (
            <div key={i} className={m.role === "user" ? "ml-8 rounded-lg bg-flame/15 p-3 text-gray-900" : "mr-4 rounded-lg bg-ink p-3 text-gray-800"}>
              <div className="whitespace-pre-wrap">{m.content}</div>
              {info?.citations?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 border-t border-line pt-2">
                  {info.citations.slice(0, 8).map((c, j) => (
                    <a key={j} href={c.url} target="_blank" rel="noreferrer" className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] text-indigo-600 hover:underline">{c.record}</a>
                  ))}
                </div>
              )}
              {info?.tool_calls?.length > 0 && (
                <details className="mt-1 text-[10px] text-gray-500">
                  <summary className="cursor-pointer">Sources checked</summary>
                  <p className="mt-1">NASA records and model results used for this answer.</p>
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
        <input disabled={!enabled || busy} aria-label="Message the assistant" value={text} onChange={(e) => setText(e.target.value)} placeholder={enabled ? "What's on your mind?" : "AI chat is not configured"}
          className="flex-1 rounded-md border border-line bg-ink px-3 py-2 text-sm text-gray-900" />
        <button disabled={!enabled || busy || !text.trim()} className="primary-button">Send</button>
      </form>
    </aside>
  );
}
