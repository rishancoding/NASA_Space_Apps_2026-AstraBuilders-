import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from firesafe import predictor

ui.init_page("Model Performance",
             "How well each predictor does on data it never saw, compared with simpler models and a constant guess.")

m = predictor.metrics()
for key, title in (("solid", "Solid materials: sustained burning"), ("flex", "FLEX droplets: early extinction")):
    mm = m[key]
    st.header(title)
    dep = next(c for c in mm["comparison"] if "[deployed]" in c["model"])
    base = mm["comparison"][0]
    c = st.columns(5)
    c[0].metric("Observations", mm["n_observations"])
    c[1].metric("Independent groups", mm["n_groups"])
    c[2].metric("Classes (0 / 1)", f"{mm['class_counts']['0']} / {mm['class_counts']['1']}")
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
    st.caption("All rows are out-of-fold (grouped cross-validation). Lower log loss and Brier are better. "
               "Classification metrics use a 0.5 threshold. Class 0 = "
               + ("flame went out" if key == "solid" else "burned to completion") + ".")

    oof = pd.DataFrame(mm["oof"])
    l, r = st.columns(2)
    with l:
        fig = go.Figure()
        rng = np.random.default_rng(0)
        for val, lab, col, sym in ((1, "Actually 1", ui.BLUE, "circle"), (0, "Actually 0", ui.ORANGE, "diamond")):
            sub = oof[oof["actual"] == val]
            fig.add_trace(go.Scatter(
                x=sub["predicted"], y=val + rng.uniform(-0.15, 0.15, len(sub)), mode="markers", name=lab,
                marker=dict(color=col, symbol=sym, size=9, line=dict(width=2, color="white")),
                customdata=sub.iloc[:, 0:2].values,
                hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>predicted %{x:.0%}<extra></extra>"))
        fig.add_vline(x=0.5, line_dash="dot", line_color=ui.MUTED)
        ui.layout(fig, title="Actual vs predicted (out-of-fold)", xaxis=dict(tickformat=".0%", range=[0, 1],
                  title="Predicted probability of class 1"),
                  yaxis=dict(tickvals=[0, 1], ticktext=["Actual 0", "Actual 1"], title=None))
        st.plotly_chart(fig, width="stretch", key=f"oof_{key}")
    with r:
        bins = pd.cut(oof["predicted"], [0, 0.2, 0.4, 0.6, 0.8, 1.0], include_lowest=True)
        cal = oof.groupby(bins, observed=True).agg(pred=("predicted", "mean"), obs=("actual", "mean"),
                                                   n=("actual", "size")).reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration",
                                 line=dict(color=ui.MUTED, dash="dot", width=2), hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=cal["pred"], y=cal["obs"], mode="lines+markers", name="Model",
                                 line=dict(color=ui.BLUE, width=2), marker=dict(size=10),
                                 customdata=cal[["n"]].values,
                                 hovertemplate="predicted %{x:.0%}<br>observed %{y:.0%}<br>n=%{customdata[0]}"
                                               "<extra></extra>"))
        ui.layout(fig, title="Calibration (out-of-fold)", xaxis=dict(tickformat=".0%", range=[0, 1],
                  title="Mean predicted"), yaxis=dict(tickformat=".0%", range=[0, 1], title="Observed rate"))
        st.plotly_chart(fig, width="stretch", key=f"cal_{key}")
    cm = dep["confusion_matrix"]
    st.markdown(f"**Confusion matrix (deployed, threshold 0.5):** actual 0 → predicted 0: {cm[0][0]}, "
                f"predicted 1: {cm[0][1]}; actual 1 → predicted 0: {cm[1][0]}, predicted 1: {cm[1][1]}.")

    st.subheader("Supported input range")
    st.dataframe(pd.DataFrame(mm["ranges"]).T, width="stretch")
    st.subheader("Limitations")
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
