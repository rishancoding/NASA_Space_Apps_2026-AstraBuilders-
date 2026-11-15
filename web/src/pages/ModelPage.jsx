import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { Card, ErrorBox, Spinner, fmt, useAsync } from "../components/ui.jsx";

const NAMES = {
  majority_baseline: "Always guess “extinction”", logistic_regression: "Logistic regression",
  logistic_regression_balanced: "Logistic regression (balanced weights)", random_forest: "Random forest", logistic_regression_interactions: "Logistic regression with interactions",
  mean_baseline: "Always guess the average", ridge: "Ridge regression",
};
const axis = { tick: { fill: "#6b7280", fontSize: 11 } };
const tip = { contentStyle: { background: "#ffffff", border: "1px solid #e5e7eb", fontSize: 12 } };

export default function ModelPage() {
  const { data, error, loading } = useAsync(() => api.model(), []);
  if (loading) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const ex = data.extinction, bt = data.burn_time, st = data.stress_tests;
  const exSel = ex.candidates[ex.selected_model], btSel = bt.audit;
  const calib = exSel.calibration.map((c) => ({ predicted: c.predicted_mean, observed: c.observed_rate, n: c.n }));
  const avp = data.out_of_fold.burn_time.map((r) => ({ actual: r.actual_s, predicted: r.predicted_s, fuel: r.fuel }));
  const maxT = Math.max(...avp.map((p) => Math.max(p.actual, p.predicted)));

  return (
    <div className="space-y-5">
      <div className="page-heading">
        <h1>How well does it predict?</h1>
        <p className="mt-1 max-w-3xl text-sm text-gray-500">
          How well the models match recorded fuel-droplet tests.
        </p>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Big label="Flame-out prediction score" value={`${Math.round(exSel.balanced_accuracy * 100)}%`} sub="Balanced accuracy · 50% is guessing" />
        <Big label="Typical burn-time error" value={`${fmt(btSel.mae_s)} s`} sub="Measured on independent test groups" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Predictions vs. recorded outcomes" subtitle="Closer to the diagonal is better.">
          <div className="h-72">
            <ResponsiveContainer>
              <LineChart data={calib} margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis type="number" dataKey="predicted" domain={[0.5, 1]} {...axis} tickFormatter={(v) => `${Math.round(v * 100)}%`}
                  label={{ value: "Model said", position: "bottom", fill: "#6b7280", fontSize: 12 }} />
                <YAxis domain={[0.5, 1]} {...axis} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                <Tooltip {...tip} formatter={(v) => `${Math.round(v * 100)}%`} />
                <ReferenceLine segment={[{ x: 0.5, y: 0.5 }, { x: 1, y: 1 }]} stroke="#64748b" strokeDasharray="4 4" />
                <Line dataKey="observed" name="Really went out" stroke="#4f46e5" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Estimated vs. actual burn time" subtitle="Each dot is an independent test.">
          <div className="h-72">
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis type="number" dataKey="actual" name="Actual" unit=" s" domain={[0, Math.ceil(maxT)]} {...axis}
                  label={{ value: "Actual burn time (s)", position: "bottom", fill: "#6b7280", fontSize: 12 }} />
                <YAxis type="number" dataKey="predicted" name="Predicted" unit=" s" domain={[0, Math.ceil(maxT)]} {...axis} />
                <Tooltip {...tip} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: maxT, y: maxT }]} stroke="#64748b" strokeDasharray="4 4" />
                <Scatter name="Methanol" data={avp.filter((p) => p.fuel === "Methanol")} fill="#818cf8" isAnimationActive={false} />
                <Scatter name="Heptane" data={avp.filter((p) => p.fuel === "Heptane")} fill="#f59e0b" isAnimationActive={false} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <details className="technical-details"><summary>Model comparisons & technical results</summary><div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        <Big label="Probability error (Brier)" value={fmt(exSel.brier_score)} sub={`${fmt(ex.candidates.majority_baseline.brier_score)} for quoting the average`} />
        <Big label="Burn-time interval coverage" value={`${Math.round(btSel.interval_coverage * 100)}%`} sub={`nominal target 90% · ${btSel.groups} audit groups · R² ${fmt(btSel.r2)}`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Extinction models compared" subtitle={`Selected: ${NAMES[ex.selected_model]} · ${ex.selection_rule}`}>
          <Table rows={Object.entries(ex.candidates).map(([k, v]) => [NAMES[k] || k, fmt(v.balanced_accuracy), fmt(v.roc_auc), fmt(v.brier_score)])}
            head={["Model", "Balanced acc.", "AUC", "Brier"]} selected={NAMES[ex.selected_model]} />
        </Card>
        <Card title="Burn-time candidate selection" subtitle={`Grouped CV on ${bt.partitions.fit.rows} fitting rows only. Selected: ${NAMES[bt.selected_model]}`}>
          <Table rows={Object.entries(bt.candidates).map(([k, v]) => [NAMES[k] || k, fmt(v.r2), `${fmt(v.mae_s)} s`, "—"])}
            head={["Model", "CV R²", "CV error", "Interval audit"]} selected={NAMES[bt.selected_model]} />
        </Card>
      </div>

      {st && (
        <Card title="Historical candidate stress tests" subtitle="Full-dataset CV experiments from the earlier model run. These do not measure the frozen burn-time pipeline or validate its new intervals.">
          <ul className="grid gap-2 text-sm text-gray-700 md:grid-cols-2">
            <li>20 different test splits: balanced accuracy {fmt(st.extinction_stability_20_shuffles.min)}–{fmt(st.extinction_stability_20_shuffles.max)}; burn-time R² {fmt(st.burn_time_stability_20_shuffles.r2_min)}–{fmt(st.burn_time_stability_20_shuffles.r2_max)}</li>
            <li>Shuffled labels: AUC drops from {fmt(st.extinction_permutation_test.real_auc)} to {fmt(st.extinction_permutation_test.shuffled_auc_mean)} (p = {fmt(st.extinction_permutation_test.p_value)})</li>
            <li>Beats a fuel-only shortcut (AUC {fmt(st.extinction_vs_fuel_only.full_model_auc)} vs {fmt(st.extinction_vs_fuel_only.fuel_only_auc)})</li>
            <li>Beats the textbook d² burning law (R² {fmt(st.burn_time_vs_d2_law.rf_r2)} vs {fmt(st.burn_time_vs_d2_law.d2_law_r2)})</li>
            <li>Per fuel (extinction AUC): heptane {fmt(st.extinction_per_fuel.Heptane.auc)}, methanol {fmt(st.extinction_per_fuel.Methanol.auc)} (only {st.extinction_per_fuel.Methanol.completions} methanol completions)</li>
            <li className="text-amber-800">Unseen gas mixtures are weak: with every CO₂ test held out, AUC {fmt(st.extinction_new_atmosphere.all_co2_tests.auc)}; burn-time R² with helium held out {fmt(st.burn_time_new_atmosphere.all_helium_tests.r2)}</li>
          </ul>
        </Card>
      )}

      <Card title="Burn-time interval audit" subtitle="Separate sample groups at every step; the deployed pipeline is not refitted after calibration.">
        <div className="grid gap-4 text-sm sm:grid-cols-3">{[["Fit & select", bt.partitions.fit], ["Calibrate interval", bt.partitions.calibration], ["Independent audit", bt.partitions.audit]].map(([label, p]) => <div key={label} className="rounded-xl border border-line bg-ink/60 p-3"><div className="eyebrow">{label}</div><div className="mt-2 text-gray-900">{p.rows} rows / {p.groups.length} groups</div></div>)}</div>
        <p className="mt-4 text-xs leading-relaxed text-gray-500">{bt.uncertainty_method}. Coverage is marginal under exchangeable sample groups, not guaranteed for each atmosphere or fuel. Independent audit R²: {fmt(btSel.r2)} (95% group-bootstrap interval {fmt(btSel.r2_95ci[0])}–{fmt(btSel.r2_95ci[1])}).</p>
      </Card>
      <Card title="What these models cannot do">
        <ul className="list-inside list-disc text-sm text-gray-700">
          {data.unsupported_claims.map((c) => <li key={c}>{c}</li>)}
        </ul>
      </Card>
      </div></details>
    </div>
  );
}

function Big({ label, value, sub }) {
  return (
    <Card>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="mt-1 text-3xl font-semibold text-gray-900">{value}</div>
      <div className="text-xs text-gray-500">{sub}</div>
    </Card>
  );
}

function Table({ head, rows, selected }) {
  return (
    <div className="scroll-region overflow-x-auto"><table className="w-full text-left text-xs">
      <thead className="text-gray-500"><tr>{head.map((h) => <th key={h} className="p-1">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r[0]} className={`border-t border-line ${r[0] === selected ? "text-gray-900" : "text-gray-500"}`}>
          {r.map((c, i) => <td key={i} className="p-1">{i === 0 && r[0] === selected ? `★ ${c}` : c}</td>)}
        </tr>
      ))}</tbody>
    </table></div>
  );
}
