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
EXPERIMENT = {"PSI-25": "BASS-II", "PSI-26": "BASS", "PSI-69": "FLEX"}


def _diff(mine: float, theirs: float, unit: str) -> str:
    gap = theirs - mine
    return "the same" if abs(gap) < 0.05 else f"{abs(gap):.1f} {unit} {'higher' if gap > 0 else 'lower'}"


def solid_run(n: dict, est: dict) -> None:
    """One nearby NASA solid run as a dropdown: what happened, how close it is, whether it agrees."""
    went = "kept burning" if n["sustained_flame"] else "went out"
    exp = EXPERIMENT.get(n["source_record"], n["source_record"])
    with st.expander(f"{exp} test {n['test_id']}: {went}"):
        same = n["scenario"] == est["scenario"]
        agrees = (est["probability"] is not None and est["probability"] >= 0.5) == bool(n["sustained_flame"])
        st.markdown(
            f"NASA burned {' '.join(n['material_raw'].split())} at {n['oxygen_pct']:.1f}% oxygen and "
            f"{n['airflow_cm_s']:g} cm/s, and the flame {went}. Crew note: \"{n['evidence_quote']}\"")
        ui.note(f"Oxygen {_diff(est['oxygen_pct'], n['oxygen_pct'], 'points')}, airflow "
                f"{_diff(est['airflow_cm_s'], n['airflow_cm_s'], 'cm/s')}, "
                f"{'same' if same else 'different'} scenario. "
                f"{'No supported estimate' if est['probability'] is None else 'Agrees with the estimate' if agrees else 'Differs from the estimate'}. <a href='{n['source_url']}' target='_blank'>NASA record</a>")


def droplet_run(n: dict, est: dict) -> None:
    went = "was recorded as Extinction" if n["extinguished"] else "was recorded as Completion"
    with st.expander(f"FLEX test {n['test_id']}: {went}"):
        extra = [f"{n[k] * 100:.0f}% {g}" for k, g in (("co2_fraction", "CO₂"), ("helium_fraction", "helium"))
                 if n[k] and n[k] > 0]
        st.markdown(f"A {n['droplet_diameter_mm']:.1f} mm {n['fuel'].lower()} drop at {n['oxygen_pct']:.0f}% oxygen"
                    f"{' with ' + ' and '.join(extra) if extra else ''}, {n['pressure_kpa']:.0f} kPa: it {went}.")
        agrees = (est["probability"] is not None and est["probability"] >= 0.5) == bool(n["extinguished"])
        ui.note(f"Oxygen {_diff(est['oxygen_pct'], n['oxygen_pct'], 'points')}, droplet "
                f"{_diff(est['droplet_diameter_mm'], n['droplet_diameter_mm'], 'mm')}. "
                f"{'No supported estimate' if est['probability'] is None else 'Agrees with the estimate' if agrees else 'Differs from the estimate'}. <a href='{n['source_url']}' target='_blank'>NASA record</a>")


solid_tab, flex_tab = st.tabs(["Solid materials", "Fuel droplets"])

with solid_tab:
    sm = m["solid"]
    dep = next(c for c in sm["comparison"] if "[deployed]" in c["model"])
    st.caption(f"Rough guide from {sm['n_observations']} NASA runs.")
    a, b = st.columns([1, 2], gap="large")
    with a:
        mat = st.selectbox("Material", predictor.solid_materials(), index=predictor.solid_materials().index("PMMA"))
        ui.note("The biggest factor.")
        tested = sm["protocols_by_material"][mat]
        proto = st.radio("Scenario", list(predictor.PROTOCOLS), format_func=predictor.PROTOCOLS.get,
                         index=list(predictor.PROTOCOLS).index(tested[0]))
        ui.note("New spark, or a fire already going? Existing fires are harder to stop.")
        mission = st.selectbox("Mission", list(MISSIONS))
        ui.note("Only orbit was tested; Moon or Mars adds a warning.")
        rng = sm["ranges"][mat]
        with st.expander("Less important factors"):
            oxy = st.slider("Oxygen (%)", 10.0, 30.0, 21.0, 0.1)
            ui.note(f"Earth air is 21%. Small effect. Tested: {rng['oxygen_pct'][0]:.0f}-{rng['oxygen_pct'][1]:.0f}%.")
            air = st.slider("Airflow (cm/s)", 0.5, 40.0, 10.0, 0.5)
            ui.note(f"Ventilation speed. Almost no effect. Tested: {rng['airflow_cm_s'][0]:g}-"
                    f"{rng['airflow_cm_s'][1]:g} cm/s.")
    r = predictor.predict_solid(mat, oxy, air, proto, gravity=MISSIONS[mission])
    with b:
        c1, c2 = st.columns(2)
        c1.metric("Chance it keeps burning", f"{r['probability']:.0%}" if r['probability'] is not None else 'Unavailable')
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
        ui.note("Line: estimate. Dotted line: your setting. Dots: real NASA runs.")
        ui.label("Closest real NASA runs")
        for n in r["nearest"][:3]:
            solid_run(n, r)

with flex_tab:
    fm = m["flex"]
    fdep = next(c for c in fm["comparison"] if "[deployed]" in c["model"])
    st.caption(f"Based on {fm['n_observations']} NASA droplet tests.")
    a, b = st.columns([1, 2], gap="large")
    with a:
        fuel = st.selectbox("Fuel", sorted(fm["ranges"]))
        ui.note("Methanol nearly always went out early.")
        fr = fm["ranges"][fuel]
        fo = st.slider("Oxygen (%)", 10.0, 40.0, 21.0, 0.5)
        ui.note("More oxygen, less likely to go out early.")
        fd = st.slider("Droplet size (mm)", 1.0, 5.0, 3.0, 0.05)
        ui.note("Bigger drops go out early more often.")
        with st.expander("Less important factors"):
            fc = st.slider("CO₂ in the air (%)", 0.0, 70.0, 0.0, 1.0) / 100
            ui.note("Suppression gas. More makes going out likelier.")
            fh = st.slider("Helium in the air (%)", 0.0, 50.0, 0.0, 1.0) / 100
            ui.note("Cools the flame a little.")
            fp = st.slider("Pressure (kPa)", 10.0, 320.0, 101.3, 0.5)
            ui.note("Sea level is ~101 kPa. Small effect.")
    fres = predictor.predict_flex(fuel, fp, fo, fc, fh, fd)
    with b:
        st.metric("Probability of recorded Extinction", f"{fres['probability']:.0%}" if fres['probability'] is not None else 'Unavailable')
        for w in fres["warnings"]:
            st.warning(w, icon=":material/warning:")
        ui.label("Closest real NASA tests")
        for n in fres["nearest"][:3]:
            droplet_run(n, fres)
