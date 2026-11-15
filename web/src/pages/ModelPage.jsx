import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { Card, ErrorBox, Spinner, fmt, useAsync } from "../components/ui.jsx";

const NAMES = {
  majority_baseline: "Always guess “extinction”", logistic_regression: "Logistic regression",
  logistic_regression_balanced: "Logistic regression (balanced weights)", random_forest: "Random forest",
  mean_baseline: "Always guess the average", ridge: "Ridge regression",
};
const axis = { tick: { fill: "#94a3b8", fontSize: 11 } };
const tip = { contentStyle: { background: "#121a2b", border: "1px solid #24304a", fontSize: 12 } };

export default function ModelPage() {
  const { data, error, loading } = useAsync(() => api.model(), []);
  if (loading) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const ex = data.extinction, bt = data.burn_time, st = data.stress_tests;
  const exSel = ex.candidates[ex.selected_model], btSel = bt.candidates[bt.selected_model];
  const calib = exSel.calibration.map((c) => ({ predicted: c.predicted_mean, observed: c.observed_rate, n: c.n }));
  const avp = data.out_of_fold.burn_time.map((r) => ({ actual: r.actual_s, predicted: r.predicted_s, fuel: r.fuel }));
  const maxT = Math.max(...avp.map((p) => Math.max(p.actual, p.predicted)));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-white">Model Accuracy</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Both models were tested on NASA FLEX tests they never saw (5-fold cross-validation, repeat burns kept together).
          Scope: liquid fuel droplets in the tested gas mixtures only.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Big label="Extinction: balanced accuracy" value={fmt(exSel.balanced_accuracy)} sub="0.50 = guessing" />
        <Big label="Extinction: probability error (Brier)" value={fmt(exSel.brier_score)} sub={`${fmt(ex.candidates.majority_baseline.brier_score)} for quoting the average`} />
        <Big label="Burn time: R²" value={fmt(btSel.r2)} sub={`typical error ${fmt(btSel.mae_s)} s`} />
        <Big label="Burn time: 90% range hit rate" value={`${Math.round(btSel.interval_coverage * 100)}%`} sub="target 90%" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Are the extinction percentages honest?" subtitle="Each dot groups ~40 tests: what the model said vs how often the flame really went out. On the diagonal = honest.">
          <div className="h-72">
            <ResponsiveContainer>
              <LineChart data={calib} margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
                <CartesianGrid stroke="#24304a" strokeDasharray="3 3" />
                <XAxis type="number" dataKey="predicted" domain={[0.5, 1]} {...axis} tickFormatter={(v) => `${Math.round(v * 100)}%`}
                  label={{ value: "Model said", position: "bottom", fill: "#94a3b8", fontSize: 12 }} />
                <YAxis domain={[0.5, 1]} {...axis} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                <Tooltip {...tip} formatter={(v) => `${Math.round(v * 100)}%`} />
                <ReferenceLine segment={[{ x: 0.5, y: 0.5 }, { x: 1, y: 1 }]} stroke="#64748b" strokeDasharray="4 4" />
                <Line dataKey="observed" name="Really went out" stroke="#a78bfa" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Burn time: predicted vs actual" subtitle="Each dot is a NASA test predicted by a model that never saw it.">
          <div className="h-72">
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
                <CartesianGrid stroke="#24304a" strokeDasharray="3 3" />
                <XAxis type="number" dataKey="actual" name="Actual" unit=" s" domain={[0, Math.ceil(maxT)]} {...axis}
                  label={{ value: "Actual burn time (s)", position: "bottom", fill: "#94a3b8", fontSize: 12 }} />
                <YAxis type="number" dataKey="predicted" name="Predicted" unit=" s" domain={[0, Math.ceil(maxT)]} {...axis} />
                <Tooltip {...tip} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: maxT, y: maxT }]} stroke="#64748b" strokeDasharray="4 4" />
                <Scatter name="Methanol" data={avp.filter((p) => p.fuel === "Methanol")} fill="#38bdf8" isAnimationActive={false} />
                <Scatter name="Heptane" data={avp.filter((p) => p.fuel === "Heptane")} fill="#ff7a1a" isAnimationActive={false} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Extinction models compared" subtitle={`Selected: ${NAMES[ex.selected_model]} · ${ex.selection_rule}`}>
          <Table rows={Object.entries(ex.candidates).map(([k, v]) => [NAMES[k] || k, fmt(v.balanced_accuracy), fmt(v.roc_auc), fmt(v.brier_score)])}
            head={["Model", "Balanced acc.", "AUC", "Brier"]} selected={NAMES[ex.selected_model]} />
        </Card>
        <Card title="Burn-time models compared" subtitle={`Selected: ${NAMES[bt.selected_model]}`}>
          <Table rows={Object.entries(bt.candidates).map(([k, v]) => [NAMES[k] || k, fmt(v.r2), `${fmt(v.mae_s)} s`, `${Math.round(v.interval_coverage * 100)}%`])}
            head={["Model", "R²", "Typical error", "90% range hit"]} selected={NAMES[bt.selected_model]} />
        </Card>
      </div>

      {st && (
        <Card title="Stress tests" subtitle="Extra checks beyond the main validation">
          <ul className="grid gap-2 text-sm text-slate-300 md:grid-cols-2">
            <li>20 different test splits: balanced accuracy {fmt(st.extinction_stability_20_shuffles.min)}–{fmt(st.extinction_stability_20_shuffles.max)}; burn-time R² {fmt(st.burn_time_stability_20_shuffles.r2_min)}–{fmt(st.burn_time_stability_20_shuffles.r2_max)}</li>
            <li>Shuffled labels: AUC drops from {fmt(st.extinction_permutation_test.real_auc)} to {fmt(st.extinction_permutation_test.shuffled_auc_mean)} (p = {fmt(st.extinction_permutation_test.p_value)})</li>
            <li>Beats a fuel-only shortcut (AUC {fmt(st.extinction_vs_fuel_only.full_model_auc)} vs {fmt(st.extinction_vs_fuel_only.fuel_only_auc)})</li>
            <li>Beats the textbook d² burning law (R² {fmt(st.burn_time_vs_d2_law.rf_r2)} vs {fmt(st.burn_time_vs_d2_law.d2_law_r2)})</li>
            <li>Per fuel (extinction AUC): heptane {fmt(st.extinction_per_fuel.Heptane.auc)}, methanol {fmt(st.extinction_per_fuel.Methanol.auc)} (only {st.extinction_per_fuel.Methanol.completions} methanol completions)</li>
            <li className="text-amber-200">Unseen gas mixtures are weak: with every CO₂ test held out, AUC {fmt(st.extinction_new_atmosphere.all_co2_tests.auc)}; burn-time R² with helium held out {fmt(st.burn_time_new_atmosphere.all_helium_tests.r2)}</li>
          </ul>
        </Card>
      )}

      <Card title="What these models cannot do">
        <ul className="list-inside list-disc text-sm text-slate-300">
          {data.unsupported_claims.map((c) => <li key={c}>{c}</li>)}
        </ul>
      </Card>
    </div>
  );
}

function Big({ label, value, sub }) {
  return (
    <Card>
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-1 text-3xl font-semibold text-white">{value}</div>
      <div className="text-xs text-slate-500">{sub}</div>
    </Card>
  );
}

function Table({ head, rows, selected }) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-slate-400"><tr>{head.map((h) => <th key={h} className="p-1">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r[0]} className={`border-t border-line ${r[0] === selected ? "text-white" : "text-slate-400"}`}>
          {r.map((c, i) => <td key={i} className="p-1">{i === 0 && r[0] === selected ? `★ ${c}` : c}</td>)}
        </tr>
      ))}</tbody>
    </table>
  );
}
