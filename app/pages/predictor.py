import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from firesafe import predictor
from firesafe.advisor import MISSIONS
from firesafe.data import solid_training

ui.init_page("Combustion Predictor",
             "Estimate a combustion outcome from conditions NASA actually tested. Inputs outside the training data "
             "are flagged, not extrapolated.")

m = predictor.metrics()
solid_tab, flex_tab = st.tabs(["Solid materials: sustained burning", "Fuel droplets (FLEX): early extinction"])

with solid_tab:
    sm = m["solid"]
    dep = next(c for c in sm["comparison"] if "[deployed]" in c["model"])
    st.caption(f"Logistic regression on {sm['n_observations']} verified-condition stages from BASS/BASS-II "
               f"(grouped CV ROC AUC {dep['roc_auc']}, log loss {dep['log_loss']} vs baseline "
               f"{sm['comparison'][0]['log_loss']}). Exploratory: most of the signal comes from the material itself.")
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
        st.caption(f"{mat} training data: {rng['n']} stages, O₂ {rng['oxygen_pct'][0]:.1f}-{rng['oxygen_pct'][1]:.1f}%, "
                   f"airflow {rng['airflow_cm_s'][0]:g}-{rng['airflow_cm_s'][1]:g} cm/s, "
                   f"scenarios: {', '.join(tested)}.")
    r = predictor.predict_solid(mat, oxy, air, proto, pres, MISSIONS[mission])
    with b:
        c1, c2 = st.columns(2)
        c1.metric("Chance the flame keeps burning", f"{r['probability']:.0%}")
        c2.metric("Within validated range", "Yes" if r["supported"] else "No")
        for w in r["warnings"]:
            st.warning(w, icon=":material/warning:")

        d = solid_training()
        d = d[d["material"] == mat]
        grid_o = np.linspace(10, 30, 81)
        grid_a = np.linspace(0.5, 40, 80)
        po = [predictor.predict_solid(mat, o, air, proto)["probability"] for o in grid_o]
        pa = [predictor.predict_solid(mat, oxy, x, proto)["probability"] for x in grid_a]

        def curve(x, y, xt, lo, hi, now, pts_x, title):
            fig = go.Figure()
            fig.add_vrect(x0=lo, x1=hi, fillcolor=ui.BLUE, opacity=0.08, line_width=0,
                          annotation_text="tested range", annotation_position="top left")
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=ui.BLUE, width=2), name="Model",
                                     hovertemplate=f"{xt} %{{x:.1f}}<br>P(sustained) %{{y:.0%}}<extra></extra>"))
            for lab, val, col, sym in (("Observed: stayed lit", 1, ui.BLUE, "circle"),
                                       ("Observed: went out", 0, ui.ORANGE, "diamond")):
                sub = pts_x[pts_x["y"] == val]
                fig.add_trace(go.Scatter(x=sub["x"], y=sub["y"] * 0.9 + 0.05, mode="markers", name=lab,
                                         marker=dict(color=col, symbol=sym, size=10,
                                                     line=dict(width=2, color="white")),
                                         customdata=sub[["q"]].values,
                                         hovertemplate="%{customdata[0]}<extra></extra>"))
            fig.add_vline(x=now, line_dash="dot", line_color=ui.MUTED)
            ui.layout(fig, height=320, title=title, xaxis_title=xt,
                      yaxis=dict(tickformat=".0%", range=[0, 1], title="P(sustained)"))
            return fig

        pts = pd.DataFrame({"y": d["sustained_flame_binary"], "q": d["evidence_quote"].fillna("")})
        st.plotly_chart(curve(grid_o, po, "Oxygen (%)", *rng["oxygen_pct"], oxy,
                              pts.assign(x=d["oxygen_initial_pct"].values),
                              f"{mat}: estimate vs oxygen at {air:g} cm/s"), width="stretch")
        st.plotly_chart(curve(grid_a, pa, "Airflow (cm/s)", *rng["airflow_cm_s"], air,
                              pts.assign(x=d["airflow_cm_s"].values),
                              f"{mat}: estimate vs airflow at {oxy:g}% O₂"), width="stretch")
        st.caption("Observed points are all of this material's training stages (any scenario), drawn at the top "
                   "(stayed lit) or bottom (went out). The flat curves show the limit of this data: with 47 stages "
                   "the model mostly learns each material's overall burn rate.")
        st.markdown("**Nearest real NASA stages**")
        st.dataframe(pd.DataFrame(r["nearest"]).drop(columns=["stage_id"]), hide_index=True,
                     width="stretch")

with flex_tab:
    fm = m["flex"]
    fdep = next(c for c in fm["comparison"] if "[deployed]" in c["model"])
    st.caption(f"{fm['model_type']} on {fm['n_observations']} FLEX tests (PSI-69), grouped 5-fold CV ROC AUC "
               f"{fdep['roc_auc']}, log loss {fdep['log_loss']} vs baseline {fm['comparison'][0]['log_loss']}. "
               "Here the conditions do carry signal.")
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
        st.metric("Chance the flame extinguishes before the fuel is used up", f"{fres['probability']:.0%}")
        for w in fres["warnings"]:
            st.warning(w, icon=":material/warning:")
        st.dataframe(pd.DataFrame(fr).drop(columns=["n"], errors="ignore").T.rename(columns={0: "min", 1: "max"}),
                     width="content")
        st.caption(f"Supported range for {fuel} ({fr['n']} tests). {fm['note']}")
