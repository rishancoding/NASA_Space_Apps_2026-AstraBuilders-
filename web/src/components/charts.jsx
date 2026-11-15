// Recharts versions of the Streamlit app's Plotly charts (app/ui.py), drawn in this UI's palette.
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { fmt } from "./ui.jsx";

export const INK = "#243d5b", MUTED = "#7a8a9e", LINE = "#e7eaf0";
// Outcome hues (secondary encoding: marker shape).
export const BURN = "#d9772b", OUT = "#3276e8", NOLIGHT = "#1d8a68";

const CLASSES = [["Kept burning", BURN, "circle"], ["Lit, then went out", OUT, "diamond"], ["Never lit", NOLIGHT, "cross"]];
export const OUTCOME_CLASS = {
  "sustained burn": CLASSES[0], "burned, then went out": CLASSES[1], "brief flame, not sustained": CLASSES[1],
  "suppressed (agent/N2)": CLASSES[1], "no ignition": CLASSES[2],
};

export const pct = (v) => `${Math.round(v * 100)}%`;
const axis = { tick: { fill: MUTED, fontSize: 11 }, stroke: LINE };
const axisLabel = (value, position = "bottom") => ({ value, position, fill: MUTED, fontSize: 12, offset: position === "bottom" ? 0 : 10 });
const legend = { verticalAlign: "bottom", wrapperStyle: { fontSize: 12, color: MUTED, paddingTop: 12 } };

function TipBox({ children }) {
  return <div className="chart-tip">{children}</div>;
}
const tipFrom = (render) => ({ active, payload }) => (active && payload?.length ? <TipBox>{render(payload[0].payload)}</TipBox> : null);

/** True when at least one test can be placed on the oxygen/airflow scatter. */
export const plottable = (tests) => (tests || []).some((t) => OUTCOME_CLASS[t.outcome_group] && t.oxygen_pct != null && (t.airflow_readings_cm_s || []).length);

/** Oxygen vs first recorded airflow, one marker per test, coloured and shaped by outcome; star = your conditions. */
export function TestsScatter({ tests, oxygen, airflow, height = 380, title }) {
  const rows = (tests || []).flatMap((t) => {
    const cls = OUTCOME_CLASS[t.outcome_group];
    const flows = t.airflow_readings_cm_s || [];
    if (!cls || t.oxygen_pct == null || !flows.length) return [];
    return [{ ...t, cls: cls[0], x: t.oxygen_pct, y: flows[0], flows: flows.map((v) => fmt(v)).join(", ") }];
  });
  if (!rows.length) return null;
  return (
    <div>
      {title && <div className="chart-title">{title}</div>}
      <div style={{ height }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 10, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid stroke={LINE} />
            <XAxis type="number" dataKey="x" name="Oxygen" domain={["auto", "auto"]} {...axis} tickFormatter={(v) => fmt(v)} label={axisLabel("Oxygen (%)")} />
            <YAxis type="number" dataKey="y" name="Airflow" domain={[0, "auto"]} {...axis} label={{ ...axisLabel("Airflow (cm/s)", "insideLeft"), angle: -90 }} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} content={tipFrom((p) => p.you
              ? <><b>Your conditions</b><br />Oxygen {fmt(p.x)}%<br />{fmt(p.y)} cm/s</>
              : <><b>{p.investigation} test {p.test_id}</b><br />{p.material_raw}<br />Oxygen {fmt(p.x)}%<br />Airflow {p.flows} cm/s<br />Result: {p.outcome}</>)} />
            <Legend {...legend} />
            {CLASSES.map(([label, color, shape]) => {
              const sub = rows.filter((r) => r.cls === label);
              return sub.length ? <Scatter key={label} name={`${label} (${sub.length})`} data={sub} fill={color} shape={shape} isAnimationActive={false} /> : null;
            })}
            {oxygen != null && airflow != null && (
              <Scatter name="Your conditions" data={[{ x: oxygen, y: airflow, you: true }]} fill={INK} shape="star" legendType="star" isAnimationActive={false}
                size={260} />
            )}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Horizontal bars: model chance the flame keeps burning per material (your material highlighted). */
export function ProbabilityBars({ candidates }) {
  const rows = candidates.filter((c) => c.prediction?.probability != null).map((c) => ({
    material: c.material + (c.is_selected ? " (yours)" : ""), p: c.prediction.probability,
    strength: c.evidence_strength, mine: c.is_selected,
  }));
  if (!rows.length) return null;
  return (
    <div style={{ height: 50 + 40 * rows.length }}>
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 44, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={LINE} horizontal={false} />
          <XAxis type="number" domain={[0, 1]} {...axis} tickFormatter={pct} />
          <YAxis type="category" dataKey="material" width={170} {...axis} tick={{ fill: INK, fontSize: 12 }} />
          <Tooltip cursor={{ fill: "#eef3f9" }} content={tipFrom((p) => <><b>{p.material}</b><br />Chance it keeps burning: {pct(p.p)}<br />Evidence: {p.strength}</>)} />
          <Bar dataKey="p" radius={4} isAnimationActive={false}>
            {rows.map((r) => <Cell key={r.material} fill={r.mine ? BURN : "#5c86bd"} />)}
            <LabelList dataKey="p" position="right" formatter={pct} style={{ fill: INK, fontSize: 12 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Estimate across the tested range of one input, your setting, and the real NASA tests (top = kept burning). */
export function EstimateCurve({ curve, current, runs, xLabel, yesLabel = "NASA test: kept burning", noLabel = "NASA test: went out" }) {
  const xs = curve.map((p) => p.x);
  const yes = runs.filter((r) => r.kept_burning === 1).map((r) => ({ ...r, y: 0.95 }));
  const no = runs.filter((r) => r.kept_burning === 0).map((r) => ({ ...r, y: 0.05 }));
  return (
    <div style={{ height: 400 }}>
      <ResponsiveContainer>
        <ComposedChart margin={{ top: 18, right: 16, bottom: 22, left: 4 }}>
          <CartesianGrid stroke={LINE} />
          <XAxis type="number" dataKey="x" domain={[Math.min(...xs), Math.max(...xs)]} {...axis} tickFormatter={(v) => fmt(v)} label={axisLabel(xLabel)} allowDuplicatedCategory={false} />
          <YAxis type="number" domain={[0, 1]} {...axis} tickFormatter={pct} />
          <Tooltip content={tipFrom((p) => p.quote != null ? <>{p.quote || "NASA run"}<br />{xLabel} {fmt(p.x)}</> : <>{xLabel} {fmt(p.x)}<br />Chance it keeps burning: {pct(p.y)}</>)} />
          <Legend {...legend} />
          <Line data={curve} dataKey="y" name="Estimate" stroke={INK} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Scatter data={yes} dataKey="y" name={yesLabel} fill={BURN} shape="circle" isAnimationActive={false} />
          <Scatter data={no} dataKey="y" name={noLabel} fill={OUT} shape="diamond" isAnimationActive={false} />
          {current != null && <ReferenceLine x={current} stroke={MUTED} strokeDasharray="3 3" />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Research assistant: share of stages that kept burning per oxygen bin. */
export function TrendBars({ rows, title }) {
  return (
    <div>
      <div className="chart-title">{title}</div>
      <div style={{ height: 320 }}>
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 24, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid stroke={LINE} vertical={false} />
            <XAxis dataKey="bin" {...axis} label={axisLabel("Oxygen (%)")} />
            <YAxis domain={[0, 1]} {...axis} tickFormatter={pct} />
            <Tooltip cursor={{ fill: "#eef3f9" }} content={tipFrom((p) => <>Oxygen {p.bin}<br />Kept burning: {p.text} runs</>)} />
            <Bar dataKey="share" fill={BURN} radius={4} isAnimationActive={false}>
              <LabelList dataKey="text" position="top" style={{ fill: INK, fontSize: 12 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Research assistant: prediction sweep line (open markers = outside the tested range). */
export function SweepChart({ points, xKey, title }) {
  const xName = xKey.split("_")[0];
  return (
    <div>
      <div className="chart-title">{title}</div>
      <div style={{ height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={points} margin={{ top: 10, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid stroke={LINE} />
            <XAxis type="number" dataKey={xKey} domain={["auto", "auto"]} {...axis} label={axisLabel(xName[0].toUpperCase() + xName.slice(1))} />
            <YAxis domain={[0, 1]} {...axis} tickFormatter={pct} />
            <Tooltip content={tipFrom((p) => <>{fmt(p[xKey])}<br />p = {pct(p.probability)}</>)} />
            <Line dataKey="probability" stroke={INK} strokeWidth={2} isAnimationActive={false}
              dot={(d) => <circle key={d.index} cx={d.cx} cy={d.cy} r={5} stroke={INK} strokeWidth={2} fill={d.payload.in_tested_range ? INK : "#fff"} />} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
