"""Shared Streamlit helpers: charts, citation lists, badges."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

# Categorical slots 1-3 (validated all-pairs, light/dark) plus a muted neutral.
BLUE, ORANGE, AQUA, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"

# Outcome groups collapsed to three display classes (secondary encoding: marker symbol).
OUTCOME_CLASS = {
    "sustained burn": ("Flame sustained", BLUE, "circle"),
    "burned, then went out": ("Burned, then went out", ORANGE, "diamond"),
    "brief flame, not sustained": ("Brief flame, not sustained", ORANGE, "diamond"),
    "suppressed (agent/N2)": ("Burned, then went out", ORANGE, "diamond"),
    "no ignition": ("No ignition", AQUA, "x"),
}
STRENGTH_BADGE = {"strong": ("Strong evidence", "green"), "moderate": ("Moderate evidence", "blue"),
                  "weak": ("Weak evidence", "orange"), "none": ("No comparable evidence", "gray")}
CHECK_ICON = {"meets": ":material/check_circle:", "fails": ":material/cancel:",
              "cannot assess": ":material/help:", "outside data": ":material/warning:"}


def layout(fig: go.Figure, height: int = 360, **kw) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=-0.2), hoverlabel=dict(namelength=-1), **kw)
    fig.update_xaxes(showgrid=True, gridwidth=1, zeroline=False)
    fig.update_yaxes(showgrid=True, gridwidth=1, zeroline=False)
    return fig


def tests_scatter(tests: list[dict], oxygen: float | None = None, airflow: float | None = None,
                  title: str = "") -> go.Figure | None:
    """Oxygen vs first recorded airflow, one marker per test, coloured+shaped by outcome."""
    rows = []
    for t in tests:
        cls = OUTCOME_CLASS.get(t.get("outcome_group"))
        flows = t.get("airflow_readings_cm_s") or []
        if not cls or t.get("oxygen_pct") is None or not flows:
            continue
        rows.append({**t, "cls": cls[0], "airflow": flows[0],
                     "flows": ", ".join(f"{v:g}" for v in flows)})
    if not rows:
        return None
    df = pd.DataFrame(rows)
    fig = go.Figure()
    for label, color, symbol in dict.fromkeys(OUTCOME_CLASS.values()):
        sub = df[df["cls"] == label]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["oxygen_pct"], y=sub["airflow"], mode="markers", name=label,
            marker=dict(color=color, symbol=symbol, size=10, line=dict(width=2, color="rgba(255,255,255,0.9)")),
            customdata=sub[["investigation", "test_id", "material_raw", "flows", "outcome"]].values,
            hovertemplate="<b>%{customdata[0]} test %{customdata[1]}</b><br>%{customdata[2]}<br>"
                          "O₂ %{x:.1f}%<br>Airflow readings: %{customdata[3]} cm/s<br>"
                          "Outcome: %{customdata[4]}<extra></extra>"))
    if oxygen is not None and airflow is not None:
        fig.add_trace(go.Scatter(x=[oxygen], y=[airflow], mode="markers", name="Your conditions",
                                 marker=dict(symbol="star", size=18, color="#0b0b0b",
                                             line=dict(width=2, color="#ffffff")),
                                 hovertemplate="Your conditions<br>O₂ %{x}%<br>%{y} cm/s<extra></extra>"))
    layout(fig, title=title, xaxis_title="Initial oxygen (% by volume)",
           yaxis_title="First recorded airflow (cm/s)")
    return fig


def probability_bars(cands: list[dict]) -> go.Figure | None:
    rows = [(c["material"] + (" (yours)" if c.get("is_selected") else ""), c["prediction"]["probability"],
             c["evidence_strength"], c.get("prediction_scenario"))
            for c in cands if c.get("prediction") and c["prediction"].get("probability") is not None]
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["material", "p", "strength", "scenario"])[::-1]
    fig = go.Figure(go.Bar(
        x=df["p"], y=df["material"], orientation="h", marker=dict(color=BLUE, cornerradius=4),
        text=[f"{v:.0%}" for v in df["p"]], textposition="outside", cliponaxis=False,
        customdata=df[["strength", "scenario"]].values,
        hovertemplate="<b>%{y}</b><br>Estimated chance of sustained burning: %{x:.0%}<br>"
                      "Evidence: %{customdata[0]}<br>Scenario: %{customdata[1]}<extra></extra>"))
    layout(fig, height=60 + 42 * len(df), title="Model estimate: chance the flame keeps burning",
           xaxis=dict(range=[0, 1.12], tickformat=".0%", title=None), showlegend=False)
    return fig


def citations(items: list[dict], header: str = "Sources") -> None:
    seen, lines = set(), []
    for c in items:
        key = (c.get("label"), c.get("url"))
        if key in seen or not c.get("url"):
            continue
        seen.add(key)
        lines.append(f"- [{c['label']}]({c['url']})")
    if lines:
        st.markdown((f"**{header}**\n" if header else "") + "\n".join(lines))


def checks_table(checks: list[dict]) -> None:
    for ch in checks:
        st.markdown(f"{CHECK_ICON.get(ch['status'], '')} **{ch['name']}** - _{ch['status']}_: {ch['detail']}")


def init_page(title: str, caption: str | None = None) -> None:
    st.title(title)
    if caption:
        st.caption(caption)
