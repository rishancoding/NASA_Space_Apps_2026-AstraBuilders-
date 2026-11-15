"""Shared Streamlit helpers: page header, styles, charts, citation lists, badges."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

# Ink and surfaces (match .streamlit/config.toml).
INK, MUTED, LINE, CARD, ACCENT = "#1e1d1a", "#66635d", "#ddd9cf", "#faf9f6", "#f0a208"
# Outcome hues, validated together on the page surface (light mode, all pairs, CVD-safe with marker shapes).
BURN, OUT, NOLIGHT = "#c06a00", "#2f6db5", "#1d8a68"

# Outcome groups collapsed to three display classes (secondary encoding: marker symbol).
OUTCOME_CLASS = {
    "sustained burn": ("Kept burning", BURN, "circle"),
    "burned, then went out": ("Lit, then went out", OUT, "diamond"),
    "brief flame, not sustained": ("Lit, then went out", OUT, "diamond"),
    "suppressed (agent/N2)": ("Lit, then went out", OUT, "diamond"),
    "no ignition": ("Never lit", NOLIGHT, "x"),
}
STRENGTH_BADGE = {"strong": ("Strong evidence", "green"), "moderate": ("Some evidence", "blue"),
                  "weak": ("Thin evidence", "orange"), "none": ("No nearby tests", "gray")}
CHECK_ICON = {"meets": ":material/check_circle:", "fails": ":material/cancel:",
              "cannot assess": ":material/help:", "outside data": ":material/warning:"}

CSS = f"""
<style>
h1 {{ letter-spacing: -0.035em; font-size: 2.6rem !important; line-height: 1.1 !important; }}
h2, h3, h4 {{ letter-spacing: -0.02em; }}
.fs-eyebrow {{ display: inline-block; background: {ACCENT}; color: {INK}; font-family: 'Geist Mono', monospace;
  font-size: 0.72rem; padding: 2px 8px; border-radius: 8px; margin-bottom: 0.4rem; }}
.fs-sub {{ color: {MUTED}; font-size: 1.05rem; max-width: 40rem; line-height: 1.55; margin: -0.4rem 0 1rem 0; }}
.fs-label {{ font-family: 'Geist Mono', monospace; font-size: 0.68rem; letter-spacing: 0.12em;
  text-transform: uppercase; color: {MUTED}; margin: 0.2rem 0 0.35rem 0; }}
.fs-note {{ color: {MUTED}; font-size: 0.86rem; line-height: 1.5; margin-top: -0.3rem; }}
.fs-note a {{ color: {INK}; text-decoration: underline; text-decoration-color: {LINE}; }}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ background: {CARD}; }}
[data-testid="stMetricLabel"] p {{ font-family: 'Geist Mono', monospace; font-size: 0.7rem !important;
  letter-spacing: 0.1em; text-transform: uppercase; color: {MUTED}; }}
[data-testid="stMetricValue"] {{ font-weight: 600; letter-spacing: -0.02em; }}
[data-testid="stSidebar"] {{ border-right: 1px solid {LINE}; }}
.fs-tldr {{ background: {CARD}; border: 1px solid {LINE}; border-left: 4px solid {ACCENT}; border-radius: 10px;
  padding: 0.7rem 1rem 0.8rem 1rem; font-size: 1.02rem; line-height: 1.5; margin: 0.4rem 0 0.2rem 0; }}
.fs-tldr .fs-label {{ margin-top: 0; }}
</style>
"""


def init_page(title: str, caption: str | None = None, eyebrow: str | None = None) -> None:
    st.html(CSS)
    if eyebrow:
        st.html(f'<span class="fs-eyebrow">{eyebrow}</span>')
    st.title(title)
    if caption:
        st.html(f'<p class="fs-sub">{caption}</p>')


def label(text: str) -> None:
    """Small uppercase mono section label (like 'LATEST RESULTS IN')."""
    st.html(f'<div class="fs-label">{text}</div>')


def note(text: str) -> None:
    """One short plain-language line under a chart saying what it shows."""
    st.html(f'<p class="fs-note">{text}</p>')


def layout(fig: go.Figure, height: int = 380, **kw) -> go.Figure:
    title = kw.pop("title", None)
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=44 if title else 12, b=8),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Geist, sans-serif", color=INK, size=13),
                      title=dict(text=title, x=0, xanchor="left", font=dict(size=15)) if title else None,
                      legend=dict(orientation="h", y=-0.18, x=0, font=dict(color=MUTED)),
                      hoverlabel=dict(namelength=-1, bgcolor=CARD, bordercolor=LINE, font=dict(color=INK)), **kw)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor=LINE, zeroline=False, linecolor=LINE,
                     tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor=LINE, zeroline=False, linecolor=LINE,
                     tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    return fig


def tests_scatter(tests: list[dict], oxygen: float | None = None, airflow: float | None = None,
                  title: str = "", height: int = 380) -> go.Figure | None:
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
    for label_, color, symbol in dict.fromkeys(OUTCOME_CLASS.values()):
        sub = df[df["cls"] == label_]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["oxygen_pct"], y=sub["airflow"], mode="markers", name=f"{label_} ({len(sub)})",
            marker=dict(color=color, symbol=symbol, size=11, line=dict(width=2, color=CARD)),
            customdata=sub[["investigation", "test_id", "material_raw", "flows", "outcome"]].values,
            hovertemplate="<b>%{customdata[0]} test %{customdata[1]}</b><br>%{customdata[2]}<br>"
                          "Oxygen %{x:.1f}%<br>Airflow %{customdata[3]} cm/s<br>"
                          "Result: %{customdata[4]}<extra></extra>"))
    if oxygen is not None and airflow is not None:
        fig.add_trace(go.Scatter(x=[oxygen], y=[airflow], mode="markers", name="Your conditions",
                                 marker=dict(symbol="star", size=20, color=INK, line=dict(width=2, color=CARD)),
                                 hovertemplate="Your conditions<br>Oxygen %{x}%<br>%{y} cm/s<extra></extra>"))
    layout(fig, height=height, title=title, xaxis_title="Oxygen (%)", yaxis_title="Airflow (cm/s)")
    return fig


def probability_bars(cands: list[dict]) -> go.Figure | None:
    rows = [(c["material"] + (" (yours)" if c.get("is_selected") else ""), c["prediction"]["probability"],
             c["evidence_strength"], bool(c.get("is_selected")))
            for c in cands if c.get("prediction") and c["prediction"].get("probability") is not None]
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["material", "p", "strength", "mine"])[::-1]
    fig = go.Figure(go.Bar(
        x=df["p"], y=df["material"], orientation="h",
        marker=dict(color=[BURN if m else INK for m in df["mine"]], cornerradius=4),
        text=[f"{v:.0%}" for v in df["p"]], textposition="outside", cliponaxis=False,
        customdata=df[["strength"]].values,
        hovertemplate="<b>%{y}</b><br>Chance it keeps burning: %{x:.0%}<br>Evidence: %{customdata[0]}"
                      "<extra></extra>"))
    layout(fig, height=50 + 40 * len(df), xaxis=dict(range=[0, 1.12], tickformat=".0%", title=None),
           showlegend=False)
    fig.update_yaxes(showgrid=False)
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
