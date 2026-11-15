import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from firesafe import agent

ui.init_page("Research Assistant")

ss = st.session_state
ss.setdefault("chat_api", [])      # exact API message history (assistant content blocks kept as returned)
ss.setdefault("chat_view", [])     # what the page renders: {"role", "text", "calls"}
online = agent.has_credentials()
ctx = ss.get("advisor_result")

if not online:
    st.info("Search mode: answers will show matching reports.", icon=":material/search:")

SUGGESTED = [
    "What happens when oxygen increases?",
    "Compare how PMMA and Nomex burn.",
    "Which materials have the most test data?",
    "Why do some flames go out?",
]
if ctx:
    st.caption(f"Using your comparison · {ctx['scenario']['oxygen_pct']:g}% oxygen · "
               f"{ctx['scenario']['airflow_cm_s']:g} cm/s airflow")
    pairs = [f"How do {x['higher']} and {x['lower']} compare?"
             for x in ctx.get("comparisons", [])][:3]
    SUGGESTED = (pairs + ["Explain my comparison results."] + SUGGESTED)[:4]


STEP = {"find_tests": "Finding matching NASA tests", "material_summary": "Summarising a material",
        "condition_trends": "Looking at trends", "search_nasa_documents": "Reading NASA reports",
        "query_database": "Querying NASA's data", "describe_database": "Checking what data exists",
        "predict_sustained_burning": "Running the burn model", "predict_droplet_extinction": "Running the droplet model",
        "prediction_sweep": "Running the model across a range", "get_current_advisor_results": "Reading your advisor results"}


def bin_label(b) -> str:
    """'(16.0, 18.0]' -> '16-18%'; a bin starting at 0 -> 'under 16%'."""
    m = re.match(r"[\[(]\s*([\d.]+)\s*,\s*([\d.]+)\s*[\])]", str(b))
    if not m:
        return str(b)
    lo, hi = float(m.group(1)), float(m.group(2))
    return f"under {hi:g}%" if lo == 0 else f"{lo:g}-{hi:g}%"


def charts_for(calls) -> None:
    for i, (name, args, out) in enumerate(calls):
        if name == "find_tests" and out.get("tests"):
            fig = ui.tests_scatter(out["tests"], title=f"The NASA tests behind this answer ({out['returned']})")
            if fig:
                st.plotly_chart(fig, width="stretch", key=f"c{id(calls)}{i}")
        elif name == "condition_trends" and out.get("stages_by_oxygen_bin"):
            df = pd.DataFrame(out["stages_by_oxygen_bin"])
            df["share"] = df["sustained"] / df["stages"]
            df["bin"] = [bin_label(b) for b in df["bin"]]
            fig = go.Figure(go.Bar(x=df["bin"], y=df["share"], marker=dict(color=ui.BURN, cornerradius=4),
                                   text=[f"{s}/{n}" for s, n in zip(df["sustained"], df["stages"])],
                                   textposition="outside", cliponaxis=False,
                                   hovertemplate="Oxygen %{x}%<br>Kept burning: %{text} runs<extra></extra>"))
            ui.layout(fig, title=f"How often {out['material']} kept burning, by oxygen level",
                      yaxis=dict(tickformat=".0%", range=[0, 1.15], title=None),
                      xaxis_title="Oxygen (%)", showlegend=False)
            st.plotly_chart(fig, width="stretch", key=f"t{id(calls)}{i}")
        elif name == "predict_sustained_burning" and out.get("probability") is not None:
            st.metric(f"{out['material']} at {out['oxygen_pct']:g}% oxygen, {out['airflow_cm_s']:g} cm/s",
                      f"{out['probability']:.0%} chance it keeps burning",
                      help=f"Model estimate. Confidence: {out['reliability']['rating']}.")
        elif name == "predict_droplet_extinction" and out.get("probability") is not None:
            st.metric(f"{out['fuel']} droplet at {out['oxygen_pct']:g}% oxygen, {out['pressure_kpa']:g} kPa",
                      f"{out['probability']:.0%} chance it goes out early",
                      help=f"Model estimate. Confidence: {out['reliability']['rating']}.")
        elif name == "prediction_sweep" and out.get("points"):
            df = pd.DataFrame([p for p in out["points"] if p.get("probability") is not None])
            if df.empty:
                continue
            fig = go.Figure(go.Scatter(
                x=df[out["varied"]], y=df["probability"], mode="lines+markers",
                line=dict(color=ui.INK, width=2),
                marker=dict(size=9, symbol=["circle" if r else "circle-open" for r in df["in_tested_range"]]),
                hovertemplate="%{x}<br>p = %{y:.0%}<extra></extra>"))
            who = out.get("material") or out.get("fuel")
            ui.layout(fig, title=f"{who}: how the estimate changes with {out['varied'].split('_')[0]}",
                      yaxis=dict(tickformat=".0%", range=[0, 1.05], title=None), xaxis_title=out["varied"].split("_")[0].capitalize(),
                      showlegend=False)
            st.plotly_chart(fig, width="stretch", key=f"w{id(calls)}{i}")
            if out["points_in_tested_range"] < len(out["points"]):
                ui.note("Estimates are shown only for tested conditions.")


def optional_charts(calls) -> None:
    """Tool use is not a request to show every intermediate table and plot."""
    charts = {"find_tests", "condition_trends", "predict_sustained_burning",
              "predict_droplet_extinction", "prediction_sweep"}
    calls = [(name, args, out) for name, args, out in (calls or [])
             if name in charts and (out.get("tests") or out.get("stages_by_oxygen_bin")
                                    or out.get("probability") is not None
                                    or any(p.get("probability") is not None for p in out.get("points", [])))]
    if calls:
        with st.expander("Charts"):
            charts_for(calls)


def sources_for(calls) -> list[dict]:
    items = []

    def walk(o):
        if isinstance(o, dict):
            url = o.get("source_url") or o.get("url")
            if url and str(url).startswith("http"):
                name = o.get("investigation") or o.get("name") or o.get("label") or ""
                rec = o.get("source_record") or ""
                label = f"{name} ({rec})" if name and rec and rec not in name else (name or rec or url)
                if o.get("title") and o["title"] != name:
                    label = f"{name}: {o['title']} ({rec})"
                items.append({"label": str(label)[:120], "url": url})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for _, _, out in calls:
        walk(out)
    seen, out = set(), []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            out.append(it)
    return out[:3]


SECTIONS = ("Answer", "Evidence", "What it means", "Prediction reliability", "Sources", "In short")
HEADING = re.compile(r"^(?:#{1,4}[ \t]+)?\*\*(" + "|".join(SECTIONS) + r")\*\*[ \t]*[:\-–—]?[ \t]*|"
                     r"^#{1,4}[ \t]+(" + "|".join(SECTIONS) + r")[ \t]*:?[ \t]*$", re.M | re.I)


def split_sections(text: str) -> dict[str, str]:
    """{'Answer': ..., 'Evidence': ...} from the model's bold headings; {} if it didn't use them."""
    marks = list(HEADING.finditer(text))
    if not marks:
        return {}
    out = {}
    lead = text[:marks[0].start()].strip()
    for i, m in enumerate(marks):
        name = next(x for x in SECTIONS if x.lower() == (m.group(1) or m.group(2)).lower())
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[name] = (out.get(name, "") + "\n\n" + text[m.end():end]).strip()
    if lead:
        out["Answer"] = (lead + "\n\n" + out.get("Answer", "")).strip()
    return out


def render_answer(text: str, calls) -> None:
    parts = split_sections(text)
    if not parts:
        st.markdown(text)
        optional_charts(calls)
        srcs = sources_for(calls or [])
        if srcs:
            with st.expander("Sources"):
                ui.citations(srcs, header="")
        return
    if parts.get("Answer"):
        st.markdown(parts["Answer"])
    elif parts.get("In short"):
        st.markdown(parts["In short"])
    optional_charts(calls)
    if any(parts.get(name) for name in ("Evidence", "What it means", "Prediction reliability")):
        with st.expander("Answer details"):
            for name, label in (("Evidence", "Recorded tests"), ("What it means", "Explanation"),
                                ("Prediction reliability", "Estimate limits")):
                if parts.get(name):
                    st.markdown(f"**{label}**")
                    st.markdown(parts[name])
    srcs = sources_for(calls) if calls else []
    if parts.get("Sources") or srcs:
        with st.expander("Sources"):
            if parts.get("Sources"):
                st.markdown(parts["Sources"])
            else:
                ui.citations(srcs, header="")


def render(msg) -> None:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            render_answer(msg["text"], msg.get("calls"))
        else:
            st.markdown(msg["text"])


for m in ss.chat_view:
    render(m)

clicked = None
if not ss.chat_view:
    cols = st.columns(2)
    for i, q in enumerate(SUGGESTED):
        if cols[i % 2].button(q, width="stretch", key=f"s{i}"):
            clicked = q

question = st.chat_input("Ask about NASA's fire experiments...") or clicked
if question:
    ss.chat_view.append({"role": "user", "text": question})
    render(ss.chat_view[-1])
    with st.chat_message("assistant"):
        status = st.status("Working on your answer...", expanded=False)
        if online:
            ss.chat_api.append({"role": "user", "content": question})
            out = agent.ask(ss.chat_api, ctx, on_tool=lambda n, a: status.write(STEP.get(n, "Checking the data")))
        else:
            out = agent.offline_answer(question)
        failed = out.get("stop_reason") in ("error", "tool_limit")
        status.update(label="Try again" if failed else "Done", state="error" if failed else "complete")
    ss.chat_view.append({"role": "assistant", "text": out["text"], "calls": out["tool_calls"]})
    st.rerun()

if ss.chat_view and st.button("Clear conversation", icon=":material/delete:"):
    ss.chat_api, ss.chat_view = [], []
    st.rerun()
