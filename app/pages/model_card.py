import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from firesafe import predictor

ui.init_page("Model Performance",
             "How often each model gets it right on NASA tests it never saw, compared with simpler guesses.",
             eyebrow="How far to trust the predictor")

m = predictor.metrics()
PLAIN = {
    "solid": "Rough guide only. It beats a blind guess, but knowing just the material does about as well, so oxygen "
             "and airflow add little so far.",
    "flex": "Useful. It clearly beats a blind guess, and oxygen, pressure and added gases really do change its answer.",
}
for key, title in (("solid", "Solid materials: does the flame keep burning?"),
                   ("flex", "Fuel droplets: does the flame go out early?")):
    mm = m[key]
    st.subheader(title)
    st.info(PLAIN[key], icon=":material/lightbulb:")
    dep = next(c for c in mm["comparison"] if "[deployed]" in c["model"])
    base = mm["comparison"][0]
    c = st.columns(5)
    c[0].metric("NASA runs", mm["n_observations"])
    c[1].metric("Separate samples", mm["n_groups"])
    c[2].metric("No / yes outcomes", f"{mm['class_counts']['0']} / {mm['class_counts']['1']}")
    c[3].metric("ROC AUC", dep["roc_auc"], f"{dep['roc_auc'] - 0.5:+.2f} vs chance")
    c[4].metric("Log loss", dep["log_loss"], f"{dep['log_loss'] - base['log_loss']:+.3f} vs baseline",
                delta_color="inverse")
    st.markdown(f"**Target:** {mm['target']}  \n**Model:** {mm['model_type']}  \n**Validation:** {mm['validation']}. "
                f"{mm['training_testing']}.")

    comp = pd.DataFrame(mm["comparison"])
    for col in ("precision", "recall", "f1"):
        comp[f"{col} (class 0)"] = comp[col].str[0]
        comp[f"{col} (class 1)"] = comp[col].str[1]
    st.dataframe(comp[["model", "log_loss", "brier", "roc_auc", "accuracy", "balanced_accuracy",
                       "precision (class 0)", "recall (class 0)", "f1 (class 0)",
                       "precision (class 1)", "recall (class 1)", "f1 (class 1)"]],
                 hide_index=True, width="stretch")
    ui.note("Each model is scored only on tests it didn't train on. Lower log loss is better; ROC AUC of 0.5 is "
            "a coin flip and 1.0 is perfect. Class 0 = " + ("flame went out" if key == "solid" else
                                                            "burned to completion") + ".")

    oof = pd.DataFrame(mm["oof"])
    l, r = st.columns(2)
    with l:
        fig = go.Figure()
        rng = np.random.default_rng(0)
        for val, lab, col, sym in ((1, "Actually yes", ui.BURN, "circle"), (0, "Actually no", ui.OUT, "diamond")):
            sub = oof[oof["actual"] == val]
            fig.add_trace(go.Scatter(
                x=sub["predicted"], y=val + rng.uniform(-0.15, 0.15, len(sub)), mode="markers", name=lab,
                marker=dict(color=col, symbol=sym, size=10, line=dict(width=2, color=ui.CARD)),
                customdata=sub.iloc[:, 0:2].values,
                hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>predicted %{x:.0%}<extra></extra>"))
        fig.add_vline(x=0.5, line_dash="dot", line_color=ui.MUTED)
        ui.layout(fig, title="Predicted vs what happened", xaxis=dict(tickformat=".0%", range=[0, 1],
                  title="Predicted chance of yes"),
                  yaxis=dict(tickvals=[0, 1], ticktext=["No", "Yes"], title=None))
        st.plotly_chart(fig, width="stretch", key=f"oof_{key}")
        ui.note("Good models put the 'yes' row to the right and the 'no' row to the left.")
    with r:
        bins = pd.cut(oof["predicted"], [0, 0.2, 0.4, 0.6, 0.8, 1.0], include_lowest=True)
        cal = oof.groupby(bins, observed=True).agg(pred=("predicted", "mean"), obs=("actual", "mean"),
                                                   n=("actual", "size")).reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration",
                                 line=dict(color=ui.MUTED, dash="dot", width=2), hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=cal["pred"], y=cal["obs"], mode="lines+markers", name="Model",
                                 line=dict(color=ui.INK, width=2), marker=dict(size=10),
                                 customdata=cal[["n"]].values,
                                 hovertemplate="predicted %{x:.0%}<br>observed %{y:.0%}<br>n=%{customdata[0]}"
                                               "<extra></extra>"))
        ui.layout(fig, title="Do the percentages mean what they say?", xaxis=dict(tickformat=".0%", range=[0, 1],
                  title="Predicted"), yaxis=dict(tickformat=".0%", range=[0, 1], title="Actually happened"))
        st.plotly_chart(fig, width="stretch", key=f"cal_{key}")
        ui.note("Points on the dotted line mean a predicted 70% really happens about 70% of the time.")
    cm = dep["confusion_matrix"]
    st.markdown(f"**Confusion matrix (deployed, threshold 0.5):** actual 0 → predicted 0: {cm[0][0]}, "
                f"predicted 1: {cm[0][1]}; actual 1 → predicted 0: {cm[1][0]}, predicted 1: {cm[1][1]}.")

    with st.expander("Conditions NASA tested (the model's safe range)"):
        st.dataframe(pd.DataFrame(mm["ranges"]).T, width="stretch")
    ui.label("Limitations")
    if key == "solid":
        mat_only = next(c for c in mm["comparison"] if c["model"].startswith("Material only"))
        st.markdown(f"""
- **Small data.** {mm['n_observations']} stages from {mm['n_groups']} physical samples; one test can change the result
  noticeably. Treat estimates as exploratory.
- **Material carries most of the signal.** A material-only model scores log loss {mat_only['log_loss']} against
  {dep['log_loss']} for the deployed one, and conditions alone do worse than a constant guess. Oxygen and airflow are
  kept in so the estimate responds to them, but their effect is weakly constrained.
- **Confounding.** Nomex and Ultem were only tested as fresh ignitions; Japan wax only while already burning; most
  materials were tested over narrow oxygen ranges.
- **Labels** ({mm['label_provenance']}). The other 348 stages were excluded because conditions were approximate,
  flow was changed mid-stage, or the ending was not intrinsic (fuel ran out, hardware failure, suppression).
- **Not covered:** pressure (all solid tests ~1 atm or unrecorded), partial gravity, untested materials, thickness.
""")
    else:
        st.markdown(f"""
- **Different physics.** Droplet flames, not solid materials; this model is a separate fallback and is not used by
  the Material Advisor.
- **Imbalance.** {mm['class_counts']['1']} of {mm['n_observations']} tests extinguished, so accuracy is high even for a
  constant guess; use log loss, AUC and the class-0 recall instead.
- {mm['note']}
""")
    st.divider()
