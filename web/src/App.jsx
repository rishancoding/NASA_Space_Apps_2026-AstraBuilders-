import { Component, lazy, Suspense, useEffect, useState } from "react";

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
import { ErrorBox, Icon, Spinner, TrustContext, useAsync } from "./components/ui.jsx";
const Advisor = lazy(() => import("./pages/Advisor.jsx"));
const Predictor = lazy(() => import("./pages/Predictor.jsx"));
const Explorer = lazy(() => import("./pages/Explorer.jsx"));
const ModelPage = lazy(() => import("./pages/ModelPage.jsx"));
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
  return [page, (p) => { location.hash = p; window.scrollTo({ top: 0 }); }];
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
      <a className="skip-link" href="#workspace" onClick={(e) => { e.preventDefault(); document.getElementById("workspace").focus(); }}>Skip to workspace</a>
      <header className="sticky top-0 z-20 border-b border-line bg-ink/95 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-7">
          <a href="#advisor" className="flex items-center gap-3" aria-label="Flame in Freefall home">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-300/30 bg-cyan-300/5 text-cyan-200"><Icon name="predictor" className="h-7 w-7" /></div>
            <div><div className="text-base font-semibold tracking-tight text-white">FLAME <span className="font-normal text-slate-400">IN</span> FREEFALL</div><div className="eyebrow text-[9px]">AstraBuilders / Combustion research</div></div>
          </a>
          <button aria-expanded={chatOpen} onClick={() => setChatOpen((o) => !o)} className="primary-button"><Icon name="chat" /><span>{chatOpen ? "Close assistant" : "Research assistant"}</span></button>
        </div>
        <nav aria-label="Main navigation" className="mx-auto flex max-w-[1440px] gap-1 overflow-x-auto px-4 pb-2 sm:px-7">
          {PAGES.map((p) => <button key={p.id} aria-current={page === p.id ? "page" : undefined} onClick={() => setPage(p.id)} className="nav-tab"><Icon name={p.id} className="h-4 w-4" />{p.label}</button>)}
        </nav>
      </header>
      <main id="workspace" tabIndex={-1} className={`mx-auto max-w-[1440px] px-4 py-6 sm:px-7 ${chatOpen ? "lg:pr-[450px]" : ""}`}>
        <section aria-label="Dataset overview" className="console-hero mb-7 flex flex-wrap items-center justify-between gap-6 rounded-2xl border border-line p-5 sm:p-7">
          <div><div className="eyebrow mb-2">NASA PSI / Evidence workspace</div><div className="text-xl font-medium tracking-tight text-white sm:text-2xl">Explore the science. Know the limits.</div><p className="mt-2 max-w-xl text-sm text-slate-400">Trace observations to NASA sources and explore estimates where comparable tests exist.</p></div>
          <div className="flex gap-5 sm:gap-8">
            <div className="console-metric"><strong>{options.data?.dataset_counts.psi_records ?? "—"}</strong><span>PSI records</span></div>
            <div className="console-metric"><strong>{options.data?.dataset_counts.recorded_tests ?? "—"}</strong><span>recorded tests</span></div>
            <div className="console-metric"><strong>{options.data?.dataset_counts.screened_flex ?? "—"}</strong><span>screened FLEX rows</span></div>
          </div>
        </section>
        {options.loading && <Spinner label="Connecting to the API…" />}
        <ErrorBox error={options.error} />
        {options.data && (
          <PageBoundary key={page}>
            <Suspense fallback={<Spinner label="Opening workspace…" />}>
            {page === "advisor" && <Advisor {...shared} />}
            {page === "predictor" && <Predictor {...shared} />}
            {page === "explorer" && <Explorer {...shared} />}
            {page === "model" && <ModelPage {...shared} />}
            </Suspense>
          </PageBoundary>
        )}
        <footer className="mt-10 border-t border-line pt-5 text-xs leading-relaxed text-slate-400">
          Data: NASA Physical Sciences Informatics (PSI). Every number is labeled as NASA-measured, AI-read, model estimate,
          Earth-gravity reference or no data. This tool compares evidence; it does not certify material safety.
        </footer>
      </main>

      <PageBoundary><ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} context={chatContext} /></PageBoundary>
      <PageBoundary><ExperimentDrawer id={experimentId} onClose={() => setExperimentId(null)} openExperiment={setExperimentId} /></PageBoundary>
    </div>
  );
}
