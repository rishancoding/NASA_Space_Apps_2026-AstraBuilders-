import { Icon } from "../components/ui.jsx";

const TOOLS = [
  { id: "advisor", title: "Material Advisor", text: "Choose oxygen, airflow and a trial type. See whether flames sustained in comparable NASA observations, with the notes behind each outcome.", action: "Compare observations", tag: "Observed evidence" },
  { id: "predictor", title: "Atmosphere Predictor", text: "Choose a fuel and gas mixture, then adjust supported conditions. Comparable NASA evidence is matched automatically. Request an extinction estimate and recorded burn time within supported coverage.", action: "Set up an estimate", tag: "Model estimates · liquid droplets" },
  { id: "explorer", title: "NASA Data Explorer", text: "Browse investigations, filter experiments, compare individual tests and search the original report passages.", action: "Browse NASA evidence", tag: "Measurements & source notes" },
  { id: "model", title: "Model Accuracy", text: "Understand how the models were evaluated, how their intervals performed, and where the evidence cannot support an answer.", action: "Review model limits", tag: "Validation & uncertainty" },
];
export default function Home({ navigate, askChat }) {
  return <div className="home-page">
    <section className="home-hero">
      <span className="home-kicker">NASA combustion research, made approachable</span>
      <h1>Understand fire.<br />Explore the evidence.</h1>
      <p>What sustained a flame? What didn’t? Start with a question, choose your conditions, and trace every result back to NASA’s microgravity research.</p>
      <button className="primary-button" onClick={() => navigate("advisor")}>Choose your conditions <span aria-hidden="true">↗</span></button>
      <span className="home-caption">Your settings first. Results when you ask for them.</span>
    </section>
    <section aria-labelledby="tool-heading">
      <div className="home-section-heading"><div><span className="eyebrow">Your research workspace</span><h2 id="tool-heading">Choose a tool.</h2></div><p>Observations and estimates stay clearly separated.</p></div>
      <div className="home-tool-grid">
        {TOOLS.map((tool) => <button key={tool.id} className="home-tool" onClick={() => navigate(tool.id)}>
          <div className="home-tool-top"><Icon name={tool.id} /><span>{tool.tag}</span></div>
          <h3>{tool.title}</h3><p>{tool.text}</p><span className="home-tool-action">{tool.action} ↗</span>
        </button>)}
        <button className="home-tool" onClick={() => askChat({ page: "home" })}><div className="home-tool-top"><Icon name="chat" /><span>Optional AI assistance</span></div><h3>Research Assistant</h3><p>Ask questions about NASA findings and your selected conditions. Generated answers use data tools and citations; a provider connection is required.</p><span className="home-tool-action">Open the assistant ↗</span></button>
      </div>
    </section>
    <section className="home-reading" aria-labelledby="reading-heading"><div><span className="eyebrow">How to read your results</span><h2 id="reading-heading">Outcomes before totals.</h2><p>Material results highlight sustained and not-sustained flame events for the trial type you select. Test counts provide context, not a safety score.</p></div><div className="home-reading-notes"><p><b>Observed</b> — NASA notes and team-verified interpretations.</p><p><b>Estimated</b> — exploratory FLEX predictions, with uncertainty.</p><p><b>Unknown</b> — missing evidence stays unresolved. Moon/Mars behaviour is not established here.</p></div></section>
  </div>;
}
