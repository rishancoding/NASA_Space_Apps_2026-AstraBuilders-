import { Component, useEffect, useState } from "react";

class PageBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200">
        This page hit an error: {String(this.state.error.message)}{" "}
        <button className="underline" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
import { api } from "./api.js";
import { ErrorBox, Spinner, TrustContext, useAsync } from "./components/ui.jsx";
import Advisor from "./pages/Advisor.jsx";
import Predictor from "./pages/Predictor.jsx";
import Explorer from "./pages/Explorer.jsx";
import ModelPage from "./pages/ModelPage.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import ExperimentDrawer from "./components/ExperimentDrawer.jsx";

const PAGES = [
  { id: "advisor", label: "Material Advisor" },
  { id: "predictor", label: "Atmosphere Predictor" },
  { id: "explorer", label: "NASA Data Explorer" },
  { id: "model", label: "Model Accuracy" },
];

function usePage() {
  const read = () => (PAGES.some((p) => p.id === location.hash.slice(1)) ? location.hash.slice(1) : "advisor");
  const [page, setPage] = useState(read);
  useEffect(() => {
    const on = () => setPage(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [page, (p) => (location.hash = p)];
}

export default function App() {
  const [page, setPage] = usePage();
  const [chatOpen, setChatOpen] = useState(false);
  const [chatContext, setChatContext] = useState(null);
  const [experimentId, setExperimentId] = useState(null);
  const options = useAsync(() => api.options(), []);
  if (options.data) TrustContext.labels = options.data.trust_labels;

  const shared = { options: options.data, openExperiment: setExperimentId, setChatContext,
    askChat: (ctx) => { setChatContext(ctx); setChatOpen(true); } };

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-ink/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-xl">🔥</span>
            <span className="font-semibold text-white">Flame in Freefall</span>
          </div>
          <nav className="flex flex-wrap gap-1">
            {PAGES.map((p) => (
              <button key={p.id} onClick={() => setPage(p.id)}
                className={`rounded-md px-3 py-1.5 text-sm ${page === p.id ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"}`}>
                {p.label}
              </button>
            ))}
          </nav>
          <button onClick={() => setChatOpen((o) => !o)}
            className="ml-auto rounded-md bg-flame px-3 py-1.5 text-sm font-medium text-white hover:brightness-110">
            {chatOpen ? "Close assistant" : "Ask the research assistant"}
          </button>
        </div>
      </header>

      <main className={`mx-auto max-w-7xl px-4 py-6 transition-[padding] ${chatOpen ? "lg:pr-[420px]" : ""}`}>
        {options.loading && <Spinner label="Connecting to the API…" />}
        <ErrorBox error={options.error} />
        {options.data && (
          <PageBoundary key={page}>
            {page === "advisor" && <Advisor {...shared} />}
            {page === "predictor" && <Predictor {...shared} />}
            {page === "explorer" && <Explorer {...shared} />}
            {page === "model" && <ModelPage {...shared} />}
          </PageBoundary>
        )}
        <footer className="mt-10 border-t border-line pt-4 text-xs text-slate-500">
          Data: NASA Physical Sciences Informatics (PSI). Every number is labeled as NASA-measured, AI-read, model estimate,
          Earth-gravity reference or no data. This tool compares evidence; it does not certify material safety.
        </footer>
      </main>

      <PageBoundary><ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} context={chatContext} /></PageBoundary>
      <PageBoundary><ExperimentDrawer id={experimentId} onClose={() => setExperimentId(null)} openExperiment={setExperimentId} /></PageBoundary>
    </div>
  );
}
