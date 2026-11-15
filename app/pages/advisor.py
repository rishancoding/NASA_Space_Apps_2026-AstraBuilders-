import pandas as pd
import streamlit as st

import ui
from firesafe import agent, predictor
from firesafe.advisor import GEOMETRIES, MISSIONS, PRIORITIES, Scenario, advise, summary_text
from firesafe.data import materials

ui.init_page("Material Advisor",
             "Evaluate a spacecraft material against NASA's microgravity fire experiments, or find tested "
             "candidates from your mission conditions.")

mode_label = st.segmented_control("Workflow", ["Analyze a material", "Find a material"],
                                  default="Find a material", label_visibility="collapsed")
mode = "analyze" if mode_label == "Analyze a material" else "discover"

left, right = st.columns([1, 2.2], gap="large")

with left:
    with st.form("scenario"):
        st.subheader("Scenario")
        mission = st.selectbox("Mission", list(MISSIONS))
        material = None
        if mode == "analyze":
            material = st.selectbox("Material to evaluate", materials(),
                                    index=materials().index("PMMA"),
                                    help="Only materials NASA burned in orbit are listed. Untested materials "
                                         "cannot be evaluated from PSI data.")
        st.markdown("**Environment**")
        oxygen = st.slider("Oxygen (% by volume)", 10.0, 35.0, 21.0, 0.1)
        airflow = st.slider("Airflow speed (cm/s)", 0.0, 40.0, 10.0, 0.5,
                            help="ISS cabin ventilation is typically 5-20 cm/s.")
        pressure = st.number_input("Cabin pressure (kPa)", 10.0, 120.0, 101.3, 0.1)
        st.markdown("**Component**")
        purpose = st.text_input("Purpose", placeholder="e.g. cable insulation, crew clothing, panel cover")
        geometry = st.selectbox("Shape", GEOMETRIES)
        thickness = st.number_input("Thickness or diameter (mm, 0 = not specified)", 0.0, 100.0, 0.0, 0.1)
        priority = st.radio("Priority", list(PRIORITIES), format_func=PRIORITIES.get)
        with st.expander("Constraints and filters"):
            max_thick = st.number_input("Maximum available thickness (mm, 0 = none)", 0.0, 100.0, 0.0, 0.1)
            max_mass = st.number_input("Maximum mass (kg, 0 = none)", 0.0, 1000.0, 0.0)
            budget = st.number_input("Budget (USD, 0 = none)", 0.0, 1e7, 0.0, 100.0)
            other = st.text_input("Other required property", placeholder="e.g. tensile strength > 50 MPa")
            req_geom = st.checkbox("Only materials tested in my shape")
            req_near = st.checkbox("Only materials with tests near my oxygen level")
        submitted = st.form_submit_button("Run advisor", type="primary", width="stretch")

if submitted or "advisor_result" not in st.session_state:
    sc = Scenario(mode=mode, mission=mission, oxygen_pct=oxygen, pressure_kpa=pressure, airflow_cm_s=airflow,
                  material=material, purpose=purpose, geometry=geometry, thickness_mm=thickness or None,
                  max_thickness_mm=max_thick or None, max_mass_kg=max_mass or None, budget=budget or None,
                  other_requirements=other, priority=priority, require_geometry=req_geom,
                  require_nearby_tests=req_near)
    st.session_state.advisor_result = advise(sc)
    st.session_state.pop("advisor_explanation", None)

res = st.session_state.advisor_result
sc = res["scenario"]


def candidate_card(c: dict, expanded: bool) -> None:
    label, color = ui.STRENGTH_BADGE[c["evidence_strength"]]
    head = "Your material" if c["is_selected"] else (f"#{c['rank']}" if c["rank"] else "Excluded")
    with st.container(border=True):
        a, b = st.columns([3, 1])
        with a:
            st.markdown(f"#### {head} · {c['material']}")
            st.badge(label, color=color)
            st.caption(f"Ranked by: {c['sort_basis'] or '-'}")
            if c.get("excluded_reason"):
                st.warning(f"Filtered out: {c['excluded_reason']}.", icon=":material/filter_alt:")
        with b:
            p = c["prediction"]["probability"] if c.get("prediction") else None
            st.metric("Est. sustained burning", f"{p:.0%}" if p is not None else "n/a",
                      help="Model estimate for the scenario named under 'Ranked by'. See Model Performance.")
        with st.expander("Evidence, constraints and sources", expanded=expanded):
            t1, t2, t3, t4 = st.tabs(["Observed results", "Constraint checks", "Concerns", "Citations"])
            with t1:
                tests = c["comparable_tests"]
                close = sum(t["airflow_match"] for t in tests)
                st.markdown(f"**{len(tests)}** NASA tests within ±1.5 pp oxygen of your scenario, "
                            f"**{close}** also within your airflow range (match: _{c['match']}_).")
                if tests:
                    counts = pd.Series([t["outcome_group"] for t in tests]).value_counts()
                    st.dataframe(counts.rename("tests").to_frame(), width="content")
                for proto, v in c["stage_evidence"].items():
                    st.markdown(f"- Verified-condition stages ({predictor.PROTOCOLS[proto]}): flame stayed lit in "
                                f"**{v['sustained']} of {v['n']}**.")
                if c["saffire"]:
                    st.markdown("**Saffire large-scale burns** (flame-spread evidence)")
                    st.dataframe(pd.DataFrame(c["saffire"])[["source_record", "sample", "material_raw", "thickness",
                                                             "airflow_cm_s", "oxygen", "burn_length", "spread_rate",
                                                             "result"]], hide_index=True)
                if c["ground"]:
                    g = pd.DataFrame(c["ground"])
                    st.markdown(f"**Earth-gravity oxygen limits** (NTRS 20110008636, comparison only): ULOI "
                                f"{g['uloi_oxygen_pct'].min():g}-{g['uloi_oxygen_pct'].max():g}%, "
                                f"MOC {g['moc_oxygen_pct'].min():g}-{g['moc_oxygen_pct'].max():g}% across "
                                f"{len(g)} configurations.")
                if tests:
                    st.dataframe(pd.DataFrame(tests)[["investigation", "test_id", "material_raw", "oxygen_pct",
                                                      "airflow_raw", "outcome_group", "notes", "locator"]],
                                 hide_index=True, height=220)
            with t2:
                ui.checks_table(c["checks"])
            with t3:
                for x in c["concerns"] or ["None recorded."]:
                    st.markdown(f"- {x}")
            with t4:
                ui.citations(c["citations"], header="")


with right:
    if res["gravity"] != "microgravity":
        st.error("No partial-gravity fire data exists. Everything below is from microgravity (ISS/Cygnus) tests and "
                 "does not predict behaviour on the Moon or Mars.", icon=":material/public_off:")
    if not 95 <= sc["pressure_kpa"] <= 105:
        st.warning(f"{sc['pressure_kpa']:g} kPa is outside the ~98-101 kPa at which the solid tests ran (where "
                   "recorded). Pressure effects cannot be assessed.", icon=":material/compress:")
    st.info(res["disclaimer"], icon=":material/info:")

    allc = res["selected"] + res["candidates"]
    fig = ui.probability_bars(allc)
    top = [c for c in allc if c["comparable_tests"]][:4]
    tabs = st.tabs(["Ranked materials", "Comparison charts", "Pairwise comparisons"])
    with tabs[0]:
        for c in res["selected"]:
            candidate_card(c, expanded=True)
        if res["selected"]:
            st.markdown("##### Alternatives worth investigating")
        for c in res["candidates"]:
            candidate_card(c, expanded=False)
        if res["excluded"]:
            with st.expander(f"{len(res['excluded'])} material(s) filtered out"):
                for c in res["excluded"]:
                    candidate_card(c, expanded=False)
    with tabs[1]:
        if fig:
            st.plotly_chart(fig, width="stretch")
        st.caption("Below: every comparable NASA test near your oxygen level. Star = your conditions.")
        cols = st.columns(2)
        for i, c in enumerate(top):
            f = ui.tests_scatter(c["comparable_tests"], sc["oxygen_pct"], sc["airflow_cm_s"], title=c["material"])
            if f:
                cols[i % 2].plotly_chart(f, width="stretch", key=f"sc_{c['material']}")
    with tabs[2]:
        st.dataframe(pd.DataFrame(res["comparisons"]), hide_index=True, width="stretch")
        if res["unassessable_constraints"]:
            st.markdown("**Could not be checked with PSI data:** " + ", ".join(res["unassessable_constraints"]))

st.divider()
st.subheader("Explanation")
exp_col, ask_col = st.columns([3, 1])
with exp_col:
    if "advisor_explanation" in st.session_state:
        st.markdown(st.session_state.advisor_explanation)
    else:
        st.markdown(summary_text(res))
with ask_col:
    if agent.has_credentials():
        if st.button("Explain with AI", type="primary", width="stretch"):
            with st.spinner("Reading the evidence..."):
                out = agent.ask([{"role": "user", "content":
                                  "Explain my current Material Advisor results: why each material ranked where it "
                                  "did, which comparisons the evidence supports, and which of my constraints could "
                                  "not be checked. Use get_current_advisor_results first."}], res)
            st.session_state.advisor_explanation = out["text"]
            st.rerun()
    else:
        st.caption("Set DEEPSEEK_API_KEY to get an AI explanation. The summary at left is computed directly.")
    if st.button("Ask a follow-up question", width="stretch"):
        st.switch_page("pages/assistant.py")
