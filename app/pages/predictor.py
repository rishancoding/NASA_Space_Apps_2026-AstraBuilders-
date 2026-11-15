import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from firesafe import predictor
from firesafe.advisor import MISSIONS
from firesafe.data import solid_training

ui.init_page("Combustion Predictor",
             "Estimate whether a flame keeps burning, using models trained on NASA's tests in orbit. Settings NASA "
             "never tested are flagged, not guessed.", eyebrow="Machine-learning estimate")

m = predictor.metrics()
solid_tab, flex_tab = st.tabs(["Solid materials", "Fuel droplets"])

with solid_tab:
    sm = m["solid"]
    dep = next(c for c in sm["comparison"] if "[deployed]" in c["model"])
    st.caption(f"Trained on {sm['n_observations']} carefully measured NASA runs. Rough guide only: the material "
               "matters far more to this model than oxygen or airflow.")
    a, b = st.columns([1, 2], gap="large")
    with a:
        mat = st.selectbox("Material", predictor.solid_materials(), index=predictor.solid_materials().index("PMMA"))
        tested = sm["protocols_by_material"][mat]
        proto = st.radio("Scenario", list(predictor.PROTOCOLS), format_func=predictor.PROTOCOLS.get,
                         index=list(predictor.PROTOCOLS).index(tested[0]))
        rng = sm["ranges"][mat]
        oxy = st.slider("Oxygen (%)", 10.0, 30.0, float(np.clip(21.0, 10, 30)), 0.1)
        air = st.slider("Airflow (cm/s)", 0.5, 40.0, 10.0, 0.5)
        pres = st.slider("Pressure (kPa)", 30.0, 110.0, 101.3, 0.1,
                         help="Not a model input: shown so the out-of-range check can flag it.")
        mission = st.selectbox("Mission", list(MISSIONS))
        st.caption(f"NASA tested {mat} {rng['n']} times at {rng['oxygen_pct'][0]:.0f}-{rng['oxygen_pct'][1]:.0f}% "
                   f"oxygen and {rng['airflow_cm_s'][0]:g}-{rng['airflow_cm_s'][1]:g} cm/s airflow.")
    r = predictor.predict_solid(mat, oxy, air, proto, pres, MISSIONS[mission])
    with b:
        c1, c2 = st.columns(2)
        c1.metric("Chance it keeps burning", f"{r['probability']:.0%}")
        c2.metric("Inside what NASA tested", "Yes" if r["supported"] else "No")
        for w in r["warnings"]:
            st.warning(w, icon=":material/warning:")

        d = solid_training()
        d = d[d["material"] == mat]
        ui.label("How the estimate changes")
        axis = st.segmented_control("Vary", ["Oxygen", "Airflow"], default="Oxygen",
                                    label_visibility="collapsed", key="pred_axis") or "Oxygen"
        if axis == "Oxygen":
            grid = np.linspace(10, 30, 81)
            ys = [predictor.predict_solid(mat, o, air, proto)["probability"] for o in grid]
            lo, hi, now, xs, xt = *rng["oxygen_pct"], oxy, d["oxygen_initial_pct"].values, "Oxygen (%)"
        else:
            grid = np.linspace(0.5, 40, 80)
            ys = [predictor.predict_solid(mat, oxy, x, proto)["probability"] for x in grid]
            lo, hi, now, xs, xt = *rng["airflow_cm_s"], air, d["airflow_cm_s"].values, "Airflow (cm/s)"
        fig = go.Figure()
        fig.add_vrect(x0=lo, x1=hi, fillcolor=ui.ACCENT, opacity=0.12, line_width=0,
                      annotation_text="NASA tested here", annotation_position="top left",
                      annotation_font_color=ui.MUTED)
        fig.add_trace(go.Scatter(x=grid, y=ys, mode="lines", line=dict(color=ui.INK, width=2), name="Estimate",
                                 hovertemplate=f"{xt} %{{x:.1f}}<br>Chance it keeps burning %{{y:.0%}}<extra></extra>"))
        pts = pd.DataFrame({"x": xs, "y": d["sustained_flame_binary"].values, "q": d["evidence_quote"].fillna("").values})
        for lab, val, col, sym in (("NASA run: kept burning", 1, ui.BURN, "circle"),
                                   ("NASA run: went out", 0, ui.OUT, "diamond")):
            sub = pts[pts["y"] == val]
            fig.add_trace(go.Scatter(x=sub["x"], y=sub["y"] * 0.9 + 0.05, mode="markers", name=lab,
                                     marker=dict(color=col, symbol=sym, size=11, line=dict(width=2, color=ui.CARD)),
                                     customdata=sub[["q"]].values, hovertemplate="%{customdata[0]}<extra></extra>"))
        fig.add_vline(x=now, line_dash="dot", line_color=ui.MUTED)
        ui.layout(fig, height=400, xaxis_title=xt, yaxis=dict(tickformat=".0%", range=[0, 1], title=None))
        st.plotly_chart(fig, width="stretch")
        ui.note(f"The line is the model's estimate as {axis.lower()} changes; the dotted line is your setting. "
                "Dots are real NASA runs (top: kept burning, bottom: went out).")
        ui.label("Closest real NASA runs")
        st.dataframe(pd.DataFrame(r["nearest"]).drop(columns=["stage_id"]), hide_index=True,
                     width="stretch")

with flex_tab:
    fm = m["flex"]
    fdep = next(c for c in fm["comparison"] if "[deployed]" in c["model"])
    st.caption(f"Trained on {fm['n_observations']} NASA FLEX droplet tests. Here oxygen, pressure and the "
               "added gases clearly change the result.")
    a, b = st.columns([1, 2], gap="large")
    with a:
        fuel = st.selectbox("Fuel", sorted(fm["ranges"]))
        fr = fm["ranges"][fuel]
        fp = st.slider("Pressure (kPa)", 10.0, 320.0, 101.3, 0.5)
        fo = st.slider("Oxygen (%)", 10.0, 40.0, 21.0, 0.5)
        fc = st.slider("CO₂ mole fraction", 0.0, 0.7, 0.0, 0.01)
        fh = st.slider("Helium mole fraction", 0.0, 0.5, 0.0, 0.01)
        fd = st.slider("Initial droplet diameter (mm)", 1.0, 5.0, 3.0, 0.05)
    fres = predictor.predict_flex(fuel, fp, fo, fc, fh, fd)
    with b:
        st.metric("Chance the flame goes out before the fuel runs out", f"{fres['probability']:.0%}")
        for w in fres["warnings"]:
            st.warning(w, icon=":material/warning:")
        st.dataframe(pd.DataFrame(fr).drop(columns=["n"], errors="ignore").T.rename(columns={0: "min", 1: "max"}),
                     width="content")
        ui.note(f"Range NASA tested for {fuel} ({fr['n']} tests). Settings outside it are flagged above.")
