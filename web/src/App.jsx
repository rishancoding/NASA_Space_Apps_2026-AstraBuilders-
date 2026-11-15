import { Component, lazy, Suspense, useEffect, useState } from "react";
import { fs } from "./api.js";
import { ErrorBox, Icon, Spinner, useAsync } from "./components/ui.jsx";

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

const Advisor = lazy(() => import("./pages/Advisor.jsx"));
const Assistant = lazy(() => import("./pages/Assistant.jsx"));
const Predictor = lazy(() => import("./pages/Predictor.jsx"));
const Explorer = lazy(() => import("./pages/Explorer.jsx"));

// Same pages and order as the Streamlit app (app/main.py); model scores live in the Combustion Predictor.
const PAGES = [
  { id: "advisor", label: "Material Advisor", icon: "advisor" },
  { id: "assistant", label: "Research Assistant", icon: "chat" },
  { id: "predictor", label: "Combustion Predictor", icon: "predictor" },
  { id: "explorer", label: "NASA Data Explorer", icon: "explorer" },
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
  const [page, goTo] = usePage();
  const options = useAsync(() => fs.options(), []);
  // Shared across pages like Streamlit's session_state: the assistant reads the advisor result.
  const [advisor, setAdvisor] = useState({ form: null, result: null, explanation: null });
  const [chat, setChat] = useState({ sessionId: null, view: [] });
  const shared = { fsOptions: options.data, advisor, setAdvisor, chat, setChat, goTo };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace" onClick={(e) => { e.preventDefault(); document.getElementById("workspace").focus(); }}>Skip to workspace</a>
      <header className="app-topbar">
        <a href="#advisor" className="app-brand" aria-label="FireSafe home">FireSafe<span>How things burn in space · AstraBuilders</span></a>
        <nav aria-label="Main navigation" className="app-navigation">
          {PAGES.map((p) => (
            <button key={p.id} aria-current={page === p.id ? "page" : undefined} onClick={() => goTo(p.id)} className="nav-tab">
              <Icon name={p.icon} className="h-4 w-4" /><span>{p.label}</span>
            </button>
          ))}
        </nav>
      </header>
      <div className="app-content">
        <main id="workspace" tabIndex={-1}>
          {options.loading && <Spinner label="Connecting to the API…" />}
          <ErrorBox error={options.error} />
          {options.data && (
            <PageBoundary key={page}>
              <Suspense fallback={<Spinner label="Opening page…" />}>
                {page === "advisor" && <Advisor {...shared} />}
                {page === "assistant" && <Assistant {...shared} />}
                {page === "predictor" && <Predictor {...shared} />}
                {page === "explorer" && <Explorer {...shared} />}
              </Suspense>
            </PageBoundary>
          )}
          <footer className="app-footer">
            <span><b>FireSafe</b> · AstraBuilders · NASA Space Apps 2026</span>
            <p>Every number comes from NASA's space station fire tests or a model trained on them. The AI only explains them.</p>
          </footer>
        </main>
      </div>
    </div>
  );
}
