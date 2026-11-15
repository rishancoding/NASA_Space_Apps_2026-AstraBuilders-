import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from firesafe import agent

ui.init_page("Research Assistant",
             "Ask anything about NASA's fire experiments in space. Answers come from NASA's own data, with sources "
             "and what the data can't tell you.", eyebrow="Ask the data")

ss = st.session_state
ss.setdefault("chat_api", [])      # exact API message history (assistant content blocks kept as returned)
ss.setdefault("chat_view", [])     # what the page renders: {"role", "text", "calls"}
online = agent.has_credentials()
ctx = ss.get("advisor_result")

if not online:
    st.warning("No DeepSeek API key found (set DEEPSEEK_API_KEY). You'll get the most relevant NASA passages "
               "without a written answer.", icon=":material/key_off:")

SUGGESTED = [
    "How does oxygen level affect how fast flames spread in space?",
    "Compare how PMMA and Nomex burn.",
    "Would a heptane droplet flame go out early at 16% oxygen?",
    "What don't we know yet about fire safety on the Moon?",
]
if ctx:
    st.info(f"Linked to your Material Advisor results ({ctx['scenario']['oxygen_pct']:g}% oxygen, "
            f"{ctx['scenario']['airflow_cm_s']:g} cm/s airflow).", icon=":material/link:")
    pairs = [f"Is {x['higher']} really safer than {x['lower']} in my conditions?"
             for x in ctx.get("comparisons", [])][:3]
    SUGGESTED = pairs + ["Which of my requirements couldn't be checked?"] + SUGGESTED[:4 - len(pairs)]


STEP = {"find_tests": "Finding matching NASA tests", "material_summary": "Summarising a material",
        "condition_trends": "Looking at trends", "search_nasa_documents": "Reading NASA reports",
        "query_database": "Querying NASA's data", "describe_database": "Checking what data exists",
        "predict_sustained_burning": "Running the burn model", "predict_droplet_extinction": "Running the droplet model",
        "prediction_sweep": "Running the model across a range", "get_current_advisor_results": "Reading your advisor results"}


def charts_for(calls) -> None:
    for i, (name, args, out) in enumerate(calls):
        if name == "find_tests" and out.get("tests"):
            fig = ui.tests_scatter(out["tests"], title=f"The NASA tests behind this answer ({out['returned']})")
            if fig:
                st.plotly_chart(fig, width="stretch", key=f"c{id(calls)}{i}")
        elif name == "condition_trends" and out.get("stages_by_oxygen_bin"):
            df = pd.DataFrame(out["stages_by_oxygen_bin"])
            df["share"] = df["sustained"] / df["stages"]
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
                      f"{out['probability']:.0%} chance it keeps burning")
            ui.note(f"Model estimate. Trust: {out['reliability']['rating']}.")
        elif name == "predict_droplet_extinction" and out.get("probability") is not None:
            st.metric(f"{out['fuel']} droplet at {out['oxygen_pct']:g}% oxygen, {out['pressure_kpa']:g} kPa",
                      f"{out['probability']:.0%} chance it goes out early")
            ui.note(f"Model estimate. Trust: {out['reliability']['rating']}.")
        elif name == "prediction_sweep" and out.get("points"):
            df = pd.DataFrame(out["points"])
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
            ui.note("Hollow points are outside what NASA tested, so trust them less.")
        elif name == "query_database" and out.get("rows"):
            st.dataframe(pd.DataFrame(out["rows"]), width="stretch", hide_index=True)
            ui.note(f"{out['returned']} matching records from NASA's data"
                    f"{' (first ones only)' if out['truncated'] else ''}.")


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
        if it["label"] not in seen:
            seen.add(it["label"])
            out.append(it)
    return out[:12]


def render(msg) -> None:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        if msg.get("calls"):
            charts_for(msg["calls"])
            srcs = sources_for(msg["calls"])
            if srcs:
                with st.expander(f"NASA sources ({len(srcs)})"):
                    ui.citations(srcs, header="")


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
        status = st.status("Looking through NASA's data...", expanded=False)
        if online:
            ss.chat_api.append({"role": "user", "content": question})
            out = agent.ask(ss.chat_api, ctx, on_tool=lambda n, a: status.write(STEP.get(n, "Checking the data")))
        else:
            out = agent.offline_answer(question)
        status.update(label="Done", state="complete")
    ss.chat_view.append({"role": "assistant", "text": out["text"], "calls": out["tool_calls"]})
    st.rerun()

if ss.chat_view and st.button("Clear conversation", icon=":material/delete:"):
    ss.chat_api, ss.chat_view = [], []
    st.rerun()
