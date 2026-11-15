import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from firesafe import agent

ui.init_page("Research Assistant",
             "Ask about NASA microgravity combustion research. Answers are built from the PSI tables and documents, "
             "with citations and the gaps the data cannot cover.")

ss = st.session_state
ss.setdefault("chat_api", [])      # exact API message history (assistant content blocks kept as returned)
ss.setdefault("chat_view", [])     # what the page renders: {"role", "text", "calls"}
online = agent.has_credentials()
ctx = ss.get("advisor_result")

if not online:
    st.warning("No DeepSeek API key found (set DEEPSEEK_API_KEY). The assistant will return the most relevant NASA "
               "passages without summarising them.", icon=":material/key_off:")

SUGGESTED = [
    "How does oxygen concentration affect flame spread in microgravity?",
    "Compare the combustion behavior of PMMA and Nomex.",
    "How likely is a heptane droplet flame to go out early at 16% oxygen, and how reliable is that estimate?",
    "What gaps exist in our understanding of fire safety on the Moon?",
]
if ctx:
    first = (ctx["selected"] + ctx["candidates"])[:2]
    st.info("Connected to your Material Advisor results "
            f"({ctx['scenario']['oxygen_pct']:g}% O₂, {ctx['scenario']['airflow_cm_s']:g} cm/s).",
            icon=":material/link:")
    if len(first) == 2:
        SUGGESTED = [f"Why was {first[0]['material']} ranked above {first[1]['material']}?",
                     "Which of my constraints could not be checked?"] + SUGGESTED[:2]


def charts_for(calls) -> None:
    for i, (name, args, out) in enumerate(calls):
        if name == "find_tests" and out.get("tests"):
            fig = ui.tests_scatter(out["tests"], title=f"Tests returned ({out['returned']} of {out['matching_tests']})")
            if fig:
                st.plotly_chart(fig, width="stretch", key=f"c{id(calls)}{i}")
        elif name == "condition_trends" and out.get("stages_by_oxygen_bin"):
            df = pd.DataFrame(out["stages_by_oxygen_bin"])
            df["share"] = df["sustained"] / df["stages"]
            fig = go.Figure(go.Bar(x=df["bin"], y=df["share"], marker=dict(color=ui.BLUE, cornerradius=4),
                                   text=[f"{s}/{n}" for s, n in zip(df["sustained"], df["stages"])],
                                   textposition="outside", cliponaxis=False,
                                   hovertemplate="O₂ %{x}%<br>Flame stayed lit: %{text} stages<extra></extra>"))
            ui.layout(fig, title=f"Verified stages where the flame stayed lit, by oxygen ({out['material']})",
                      yaxis=dict(tickformat=".0%", range=[0, 1.15], title=None),
                      xaxis_title="Initial oxygen bin (%)", showlegend=False)
            st.plotly_chart(fig, width="stretch", key=f"t{id(calls)}{i}")
        elif name == "predict_sustained_burning" and out.get("probability") is not None:
            st.metric(f"Model estimate - {out['material']} at {out['oxygen_pct']:g}% O₂, {out['airflow_cm_s']:g} cm/s",
                      f"{out['probability']:.0%} chance of sustained burning")
            st.caption(f"Reliability: **{out['reliability']['rating']}** - {'; '.join(out['reliability']['reasons'])}")
        elif name == "predict_droplet_extinction" and out.get("probability") is not None:
            st.metric(f"Model estimate - {out['fuel']} droplet at {out['oxygen_pct']:g}% O₂, "
                      f"{out['pressure_kpa']:g} kPa", f"{out['probability']:.0%} chance of early extinction")
            st.caption(f"Reliability: **{out['reliability']['rating']}** - {'; '.join(out['reliability']['reasons'])}")
        elif name == "prediction_sweep" and out.get("points"):
            df = pd.DataFrame(out["points"])
            fig = go.Figure(go.Scatter(
                x=df[out["varied"]], y=df["probability"], mode="lines+markers",
                line=dict(color=ui.BLUE),
                marker=dict(size=9, symbol=["circle" if r else "circle-open" for r in df["in_tested_range"]]),
                hovertemplate="%{x}<br>p = %{y:.0%}<extra></extra>"))
            who = out.get("material") or out.get("fuel")
            ui.layout(fig, title=f"{who}: {out['meaning']} vs {out['varied']} (open markers = outside tested range)",
                      yaxis=dict(tickformat=".0%", range=[0, 1.05], title=None), xaxis_title=out["varied"],
                      showlegend=False)
            st.plotly_chart(fig, width="stretch", key=f"w{id(calls)}{i}")
        elif name == "query_database" and out.get("rows"):
            st.dataframe(pd.DataFrame(out["rows"]), width="stretch", hide_index=True)
            st.caption(f"{out['returned']} row(s){' (truncated)' if out['truncated'] else ''} from "
                       f"{', '.join(out['tables_used'])}")


def sources_for(calls) -> list[dict]:
    items = []

    def walk(o):
        if isinstance(o, dict):
            url = o.get("source_url") or o.get("url")
            if url and str(url).startswith("http"):
                label = " ".join(str(o[k]) for k in ("investigation", "source_record", "test_id", "sample",
                                                     "source_file", "locator", "label") if o.get(k))
                items.append({"label": label[:140] or url, "url": url})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for _, _, out in calls:
        walk(out)
    return items[:25]


def render(msg) -> None:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        if msg.get("calls"):
            charts_for(msg["calls"])
            srcs = sources_for(msg["calls"])
            if srcs:
                with st.expander(f"Sources ({len({s['url'] + s['label'] for s in srcs})})"):
                    ui.citations(srcs, header="")
            with st.expander("Tool calls (how this answer was built)"):
                for name, args, _ in msg["calls"]:
                    st.code(f"{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})", language="python")


for m in ss.chat_view:
    render(m)

clicked = None
if not ss.chat_view:
    cols = st.columns(2)
    for i, q in enumerate(SUGGESTED):
        if cols[i % 2].button(q, width="stretch", key=f"s{i}"):
            clicked = q

question = st.chat_input("Ask about NASA combustion experiments...") or clicked
if question:
    ss.chat_view.append({"role": "user", "text": question})
    render(ss.chat_view[-1])
    with st.chat_message("assistant"):
        status = st.status("Searching NASA data...", expanded=False)
        if online:
            ss.chat_api.append({"role": "user", "content": question})
            out = agent.ask(ss.chat_api, ctx, on_tool=lambda n, a: status.write(f"Calling `{n}`"))
        else:
            out = agent.offline_answer(question)
        status.update(label="Done", state="complete")
    ss.chat_view.append({"role": "assistant", "text": out["text"], "calls": out["tool_calls"]})
    st.rerun()

if ss.chat_view and st.button("Clear conversation", icon=":material/delete:"):
    ss.chat_api, ss.chat_view = [], []
    st.rerun()
