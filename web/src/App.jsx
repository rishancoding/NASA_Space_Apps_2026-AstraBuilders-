import { Component, lazy, Suspense, useEffect, useState } from "react";

class PageBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-700">
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
  { id: "advisor", label: "Material Advisor", description: "Compare materials" },
  { id: "predictor", label: "Atmosphere Predictor", description: "Explore a flame" },
  { id: "explorer", label: "NASA Data Explorer", description: "Browse experiments" },
  { id: "model", label: "Model Accuracy", description: "Understand the models" },
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
    <div className="app-shell">
      <a className="skip-link" href="#workspace" onClick={(e) => { e.preventDefault(); document.getElementById("workspace").focus(); }}>Skip to workspace</a>
      <header className="app-topbar">
        <a href="#advisor" className="app-brand" aria-label="Flame in Freefall home">flame in freefall<span>by AstraBuilders</span></a>
        <nav aria-label="Main navigation" className="app-navigation">
          {PAGES.map((p) => <button key={p.id} aria-current={page === p.id ? "page" : undefined} onClick={() => setPage(p.id)} className="nav-tab">{{advisor:"Materials",predictor:"Predictor",explorer:"NASA data",model:"Model accuracy"}[p.id]}</button>)}
        </nav>
        <button aria-expanded={chatOpen} onClick={() => setChatOpen((o) => !o)} className="primary-button"><Icon name="chat" className="h-4 w-4" /><span>{chatOpen ? "Close chat" : "Ask a question"}</span></button>
      </header>
      <div className={`app-content ${chatOpen ? "assistant-open" : ""}`}>
      <main id="workspace" tabIndex={-1}>
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
        <footer className="app-footer">
          <span>AstraBuilders · NASA PSI data</span>
          <details><summary>About the data</summary><p>Explore NASA measurements, team-verified outcomes, model estimates and Earth-gravity references.</p></details>
        </footer>
      </main>
      </div>

      <PageBoundary><ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} context={chatContext} /></PageBoundary>
      <PageBoundary><ExperimentDrawer id={experimentId} onClose={() => setExperimentId(null)} openExperiment={setExperimentId} /></PageBoundary>
    </div>
  );
}
