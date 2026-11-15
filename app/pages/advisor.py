import pandas as pd
import streamlit as st

import ui
from firesafe import agent, predictor
from firesafe.advisor import GEOMETRIES, MISSIONS, PRIORITIES, Scenario, advise, summary_text
from firesafe.data import materials

ui.init_page("Material Advisor",
             "Check a spacecraft material against NASA's fires in orbit, or find tested materials that fit your "
             "mission.", eyebrow="NASA microgravity fire data")

mode_label = st.segmented_control("Workflow", ["Analyze a material", "Find a material"],
                                  default="Find a material", label_visibility="collapsed")
mode = "analyze" if mode_label == "Analyze a material" else "discover"

left, right = st.columns([1, 2.2], gap="large")

with left:
    with st.form("scenario"):
        ui.label("Your scenario")
        mission = st.selectbox("Mission", list(MISSIONS))
        material = None
        if mode == "analyze":
            material = st.selectbox("Material to evaluate", materials(),
                                    index=materials().index("PMMA"),
                                    help="Only materials NASA burned in orbit are listed. Untested materials "
                                         "cannot be evaluated from PSI data.")
        ui.label("Environment")
        oxygen = st.slider("Oxygen (% by volume)", 10.0, 35.0, 21.0, 0.1)
        airflow = st.slider("Airflow speed (cm/s)", 0.0, 40.0, 10.0, 0.5,
                            help="ISS cabin ventilation is typically 5-20 cm/s.")
        pressure = st.number_input("Cabin pressure (kPa)", 10.0, 120.0, 101.3, 0.1)
        ui.label("Component")
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


OUTCOME_WORDS = {"sustained burn": "kept burning", "burned, then went out": "went out",
                 "brief flame, not sustained": "went out", "suppressed (agent/N2)": "went out",
                 "no ignition": "never lit"}


def tests_line(tests: list[dict]) -> str:
    """'7 NASA tests near your conditions: 5 kept burning, 2 went out.'"""
    if not tests:
        return "No NASA tests near your oxygen level."
    counts = pd.Series([OUTCOME_WORDS.get(t["outcome_group"], "unclear") for t in tests]).value_counts()
    parts = ", ".join(f"{n} {w}" for w, n in counts.items())
    return f"{len(tests)} NASA test{'s' if len(tests) != 1 else ''} near your oxygen level: {parts}."


def candidate_card(c: dict) -> None:
    label, color = ui.STRENGTH_BADGE[c["evidence_strength"]]
    head = "Your material" if c["is_selected"] else (f"#{c['rank']}" if c["rank"] else "Filtered out")
    with st.container(border=True):
        a, b = st.columns([3, 1])
        with a:
            ui.label(head)
            st.markdown(f"#### {c['material']}")
            st.badge(label, color=color)
            st.markdown(tests_line(c["comparable_tests"]))
            if c.get("excluded_reason"):
                st.caption(f"Filtered out: {c['excluded_reason']}.")
        with b:
            p = c["prediction"]["probability"] if c.get("prediction") else None
            st.metric("Burn chance", f"{p:.0%}" if p is not None else "n/a",
                      help="Model estimate of the chance a flame keeps burning in your conditions. "
                           "See Model Performance for how reliable it is.")
        with st.expander("Details and sources"):
            t1, t2, t3, t4 = st.tabs(["Tests", "Your requirements", "Concerns", "Sources"])
            with t1:
                for proto, v in c["stage_evidence"].items():
                    st.markdown(f"- {predictor.PROTOCOLS[proto]}: flame stayed lit in "
                                f"**{v['sustained']} of {v['n']}** carefully measured runs.")
                if c["saffire"]:
                    st.markdown("**Large-scale burns (Saffire)**")
                    st.dataframe(pd.DataFrame(c["saffire"])[["source_record", "sample", "oxygen", "spread_rate",
                                                             "result"]], hide_index=True)
                if c["ground"]:
                    g = pd.DataFrame(c["ground"])
                    st.markdown(f"**On Earth** (for comparison): stops burning below about "
                                f"{g['moc_oxygen_pct'].min():g}-{g['moc_oxygen_pct'].max():g}% oxygen.")
                if c["comparable_tests"]:
                    t = pd.DataFrame(c["comparable_tests"])
                    t["result"] = t["outcome_group"].map(OUTCOME_WORDS).fillna("unclear")
                    st.dataframe(t[["investigation", "test_id", "oxygen_pct", "airflow_raw", "result", "notes"]],
                                 hide_index=True, height=220,
                                 column_config={"investigation": "Experiment", "test_id": "Test",
                                                "oxygen_pct": "Oxygen %", "airflow_raw": "Airflow (cm/s)",
                                                "notes": "Crew notes"})
            with t2:
                ui.checks_table(c["checks"])
            with t3:
                for x in c["concerns"] or ["None recorded."]:
                    st.markdown(f"- {x}")
            with t4:
                ui.citations(c["citations"], header="")


with right:
    if res["gravity"] != "microgravity":
        st.error("NASA has no fire tests in Moon or Mars gravity. These results come from orbit and may not hold "
                 "there.", icon=":material/public_off:")
    if not 95 <= sc["pressure_kpa"] <= 105:
        st.warning(f"NASA ran these tests near normal air pressure (~101 kPa). We can't say how "
                   f"{sc['pressure_kpa']:g} kPa changes things.", icon=":material/compress:")

    allc = res["selected"] + res["candidates"]
    tabs = st.tabs(["Ranked materials", "Charts"])
    with tabs[0]:
        st.caption("A starting point for research, not a safety certification. Materials are only called safer "
                   "than one another when the tests clearly support it.")
        for c in res["selected"]:
            candidate_card(c)
        if res["selected"] and res["candidates"]:
            ui.label("Alternatives worth a look")
        for c in res["candidates"]:
            candidate_card(c)
        if res["excluded"]:
            with st.expander(f"{len(res['excluded'])} filtered out by your requirements"):
                for c in res["excluded"]:
                    candidate_card(c)
        if res["unassessable_constraints"]:
            st.caption("NASA's data can't check: " + ", ".join(res["unassessable_constraints"]).lower() + ".")
    with tabs[1]:
        fig = ui.probability_bars(allc)
        if fig:
            ui.label("Chance the flame keeps burning")
            st.plotly_chart(fig, width="stretch")
            ui.note("Model estimate for each material in your conditions. Lower is better. Small gaps between "
                    "materials don't mean much.")
        with_tests = [c["material"] for c in allc if c["comparable_tests"]]
        if with_tests:
            ui.label("NASA tests near your conditions")
            pick = st.segmented_control("Material", with_tests, default=with_tests[0],
                                        label_visibility="collapsed", key="adv_chart_pick") or with_tests[0]
            c = next(x for x in allc if x["material"] == pick)
            f = ui.tests_scatter(c["comparable_tests"], sc["oxygen_pct"], sc["airflow_cm_s"], height=440)
            if f:
                st.plotly_chart(f, width="stretch", key="adv_scatter")
                ui.note(f"Each mark is one {pick} test NASA ran in orbit. The star is your conditions; nearby "
                        "marks are the most relevant evidence.")
            else:
                st.caption("These tests don't have a recorded airflow to plot.")

st.divider()
ui.label("Explanation")
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
                                  "Explain my Material Advisor results simply: why the top materials ranked where "
                                  "they did, whether any one is clearly safer, and which of my requirements could "
                                  "not be checked. Use get_current_advisor_results first."}], res)
            st.session_state.advisor_explanation = out["text"]
            st.rerun()
    else:
        st.caption("Set DEEPSEEK_API_KEY to get an AI explanation. The summary at left is computed directly.")
    if st.button("Ask a follow-up question", width="stretch"):
        st.switch_page("pages/assistant.py")
