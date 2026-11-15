import pandas as pd
import streamlit as st

import ui
from firesafe import evidence
from firesafe.data import catalog, ground, publications, solids, source_table, table_index, test_airflow_values

ui.init_page("NASA Data Explorer",
             "Every NASA experiment behind this app, with its goals, tests and original data tables.",
             eyebrow="19 NASA investigations")

tabs = st.tabs(["Investigations", "Solid combustion tests", "Original NASA tables", "Document search",
                "Earth ground tests"])
idx = pd.DataFrame(table_index())

with tabs[0]:
    cat = catalog()
    a, b = st.columns([2, 1])
    q = a.text_input("Search investigations", placeholder="e.g. flame spread, droplet, smoke, PMMA")
    phases = b.multiselect("Fuel type", sorted(cat["fuel_phase"].unique()))
    view = cat
    if q:
        mask = view.apply(lambda r: q.lower() in " ".join(map(str, r.values)).lower(), axis=1)
        view = view[mask]
    if phases:
        view = view[view["fuel_phase"].isin(phases)]
    st.caption(f"{len(view)} of {len(cat)} records")
    pubs = publications()
    for r in view.itertuples():
        with st.expander(f"**{r.investigation_name}** · {r.official_title} ({r.source_record}) · {r.fuel_phase}"):
            st.markdown(f"[Open the NASA record]({r.url})" + (f" · DOI {r.doi}" if r.doi else "")
                        + (f" · License {r.license}" if r.license else "") + f" · Role in this app: `{r.role}`")
            st.markdown(f"**Objective.** {r.objective}")
            if r.approach:
                st.markdown(f"**Approach.** {r.approach}")
            if r.primary_materials:
                st.markdown(f"**Materials / fuels.** {r.primary_materials.replace(' | ', ', ')[:800]}")
            if r.measured_variables:
                st.markdown(f"**Measured variables.** {r.measured_variables.replace(' | ', ', ')}")
            t = idx[idx["source_record"] == r.source_record]
            if len(t):
                st.markdown("**Available data tables**")
                st.dataframe(t[["file", "row_count", "role"]], hide_index=True, width="stretch")
            p = pubs[pubs["source_record"] == r.source_record]
            if len(p):
                st.markdown(f"**Publications ({len(p)})**")
                st.dataframe(p[["title", "authors", "doi", "url"]].head(15), hide_index=True,
                             width="stretch", column_config={"url": st.column_config.LinkColumn()})

with tabs[1]:
    s = solids()
    f1, f2, f3, f4 = st.columns(4)
    mats = f1.multiselect("Material", sorted(s["material"].unique()))
    recs = f2.multiselect("Investigation", sorted(s["investigation_name"].unique()))
    outs = f3.multiselect("Outcome", sorted(s["outcome_group"].unique()))
    o2 = f4.slider("Oxygen range (%)", 10.0, 45.0, (10.0, 45.0), 0.5)
    v = s[s["oxygen_pct"].between(*o2) | s["oxygen_pct"].isna()]
    if mats:
        v = v[v["material"].isin(mats)]
    if recs:
        v = v[v["investigation_name"].isin(recs)]
    if outs:
        v = v[v["outcome_group"].isin(outs)]
    st.caption(f"{len(v)} of {len(s)} tests. Outcome labels were read from crew and report notes and verified by the project team.")
    flows = test_airflow_values()
    fig = ui.tests_scatter([{**r, "airflow_readings_cm_s": flows.get(r["experiment_id"], []),
                             "investigation": r["investigation_name"]} for r in v.to_dict("records")],
                           height=420)
    if fig:
        st.plotly_chart(fig, width="stretch")
        ui.note("Each mark is one test, placed by its oxygen level and airflow and colored by what the flame did.")
    st.dataframe(v[["investigation_name", "test_id", "test_date", "material", "material_raw", "sample_geometry",
                    "thickness_mm", "diameter_mm", "oxygen_pct", "airflow_raw", "pressure_kpa", "flow_direction",
                    "outcome", "notes", "quality_flags", "source_file", "source_row", "source_url"]],
                 hide_index=True, width="stretch", height=420,
                 column_config={"source_url": st.column_config.LinkColumn("NASA record")})
    st.download_button("Download filtered tests (CSV)", v.to_csv(index=False), "psi_solid_tests.csv", "text/csv")

with tabs[2]:
    choice = st.selectbox("Table", idx["file"], format_func=lambda f: f.split("/")[-1])
    meta = idx[idx["file"] == choice].iloc[0]
    st.caption(f"{meta['source_record']} · {meta['row_count']} rows · original encoding {meta['original_encoding']} · "
               "values exactly as NASA published them (notes, approximations and typos kept).")
    st.dataframe(source_table(choice), hide_index=True, width="stretch", height=460)

with tabs[3]:
    q = st.text_input("Search NASA documents", "flame spread opposed flow oxygen")
    k = st.slider("Results", 3, 15, 6)
    for h in evidence.search(q, k=k):
        with st.container(border=True):
            st.markdown(f"**{h['investigation']} ({h['source_record']})** · {h['kind_label']} · "
                        f"{h['source_file']}, {h['locator']} · [record]({h['source_url']})")
            if h["kind"] == "experiment_plan_text":
                st.caption("Plan text: describes proposed tests, not results.")
            st.write(h["text"][:1200])

with tabs[4]:
    g = ground()
    st.info("Earth-gravity oxygen thresholds from NASA White Sands tests (NTRS 20110008636), outside PSI. ULOI and MOC "
            "are different thresholds from the ISS burn outcomes: use for comparison only.", icon=":material/public:")
    fam = st.multiselect("Material family", sorted(g["material"].unique()))
    gv = g[g["material"].isin(fam)] if fam else g
    st.dataframe(gv.drop(columns=["source_record", "role", "gravity_regime"]), hide_index=True,
                 width="stretch", column_config={"source_url": st.column_config.LinkColumn()})
