"""Read-only functions the research assistant may call.

Every number in the assistant's answer must come from a result returned here.
Curated tools cover the common questions; `query_database` runs a single
read-only SELECT on the SQLite copy of data/clean/ for everything else, so any
arithmetic happens in SQL, not in the LLM. Predictions always carry a
reliability review (firesafe/reliability.py), and `run_tool` attaches a
`provenance` block (datasets, investigations, URLs) to every result.
"""
from __future__ import annotations

import json
import math
from dataclasses import fields

import numpy as np
import pandas as pd

from . import advisor, db, evidence, predictor, reliability
from .data import (PSI_URL, UNRESOLVED, catalog, ground, material_profile, materials, publications, saffire,
                   solid_training, solids, test_airflow_values)


def _clean(obj):
    """JSON-safe: NaN -> None, numpy scalars -> Python."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(obj) else round(float(obj), 4)
    return obj


def list_materials() -> dict:
    return {"materials": [{"material": m, "tests": material_profile(m)["tests"],
                           "saffire_samples": material_profile(m)["saffire_samples"]} for m in materials()],
            "note": "Solid materials burned in orbit (BASS PSI-26, BASS-II PSI-25, Saffire PSI-98/99/100). "
                    f"{int((solids()['material'] == UNRESOLVED).sum())} tests have an unresolved material."}


def material_summary(material: str) -> dict:
    if material not in materials():
        return {"error": f"Unknown material. Choose one of: {', '.join(materials())}"}
    prof = material_profile(material)
    prof["saffire"] = saffire(material)
    prof["citations"] = [{"label": f"{r} investigation record", "url": PSI_URL.format(r)} for r in prof["investigations"]]
    return prof


def find_tests(material: str | None = None, source_record: str | None = None, oxygen_min: float | None = None,
               oxygen_max: float | None = None, airflow_min: float | None = None, airflow_max: float | None = None,
               outcome_group: str | None = None, limit: int = 15) -> dict:
    s = solids()
    if material:
        s = s[s["material"] == material]
    if source_record:
        s = s[s["source_record"] == source_record]
    if oxygen_min is not None:
        s = s[s["oxygen_pct"] >= oxygen_min]
    if oxygen_max is not None:
        s = s[s["oxygen_pct"] <= oxygen_max]
    flows = test_airflow_values()
    if airflow_min is not None or airflow_max is not None:
        lo, hi = airflow_min if airflow_min is not None else -1, airflow_max if airflow_max is not None else 1e9
        s = s[[any(lo <= v <= hi for v in flows.get(e, [])) for e in s["experiment_id"]]]
    if outcome_group:
        s = s[s["outcome_group"] == outcome_group]
    rows = [{"experiment_id": r.experiment_id, "investigation": r.investigation_name, "source_record": r.source_record,
             "test_id": r.test_id, "material": r.material, "material_raw": r.material_raw,
             "geometry": r.sample_geometry, "oxygen_pct": r.oxygen_pct,
             "airflow_readings_cm_s": flows.get(r.experiment_id, []), "pressure_kpa": r.pressure_kpa,
             "outcome": r.outcome, "outcome_group": r.outcome_group, "notes": r.notes[:300],
             "source_url": r.source_url, "locator": f"{r.source_file} row {r.source_row}"}
            for r in s.head(max(1, min(int(limit), 40))).itertuples()]
    return {"matching_tests": int(len(s)), "returned": len(rows),
            "outcome_counts": s["outcome_group"].value_counts().to_dict(),
            "oxygen_pct_range": [s["oxygen_pct"].min(), s["oxygen_pct"].max()] if len(s) else None,
            "tests": rows,
            "outcome_groups_available": sorted(solids()["outcome_group"].unique().tolist())}


def condition_trends(material: str | None = None) -> dict:
    """Observed outcomes binned by oxygen and by airflow, from the 47 verified-condition stages
    plus the test-level outcomes of all 250 tests (by initial oxygen)."""
    d = solid_training()
    if material:
        d = d[d["material"] == material]
    out: dict = {"material": material or "all solid materials"}
    if len(d):
        d = d.assign(oxygen_bin=pd.cut(d["oxygen_initial_pct"], [0, 16, 18, 20, 21.5, 23, 30]).astype(str),
                     airflow_bin=pd.cut(d["airflow_cm_s"], [0, 2.5, 5.5, 10.5, 15.5, 40]).astype(str))
        for col in ("oxygen_bin", "airflow_bin"):
            g = d.groupby(col, observed=True)["sustained_flame_binary"].agg(["count", "sum"])
            out[f"stages_by_{col}"] = [{"bin": k, "stages": int(r["count"]), "sustained": int(r["sum"])}
                                       for k, r in g.iterrows()]
    s = solids()
    if material:
        s = s[s["material"] == material]
    s = s.dropna(subset=["oxygen_pct"]).assign(
        oxygen_bin=lambda t: pd.cut(t["oxygen_pct"], [0, 16, 18, 20, 21.5, 23, 30]).astype(str))
    tab = pd.crosstab(s["oxygen_bin"], s["outcome_group"])
    out["tests_by_oxygen_bin"] = {k: {c: int(v) for c, v in row.items() if v} for k, row in tab.iterrows()}
    out["caveat"] = ("Stages are the 47 conditions with exact oxygen/airflow and an AI-reviewed label. Bins mix "
                     "materials, shapes and test scenarios, so they show where tests were run, not a controlled trend.")
    return out


def predict_sustained_burning(material: str, oxygen_pct: float, airflow_cm_s: float,
                              scenario: str = "ongoing_burn_trial", pressure_kpa: float | None = None,
                              mission: str = "Space station (microgravity)") -> dict:
    res = predictor.predict_solid(material, oxygen_pct, airflow_cm_s, scenario, pressure_kpa,
                                  advisor.MISSIONS.get(mission, "microgravity"))
    if res["probability"] is not None:
        res["predicted_outcome"] = "flame stays lit" if res["probability"] >= 0.5 else "flame goes out"
    res["reliability"] = reliability.review("solid", res, material)
    res["note"] = ("Exploratory: material identity carries most of the signal; oxygen and airflow add little with "
                   "47 labelled stages. Compare model_statistics.simpler_model.")
    return res


def predict_droplet_extinction(fuel: str, pressure_kpa: float, oxygen_pct: float, co2_fraction: float = 0.0,
                               helium_fraction: float = 0.0, droplet_diameter_mm: float = 3.0) -> dict:
    res = predictor.predict_flex(fuel, pressure_kpa, oxygen_pct, co2_fraction, helium_fraction, droplet_diameter_mm)
    res["meaning"] = "Probability the droplet flame extinguishes before the fuel is consumed (FLEX, PSI-69)."
    if res["probability"] is not None:
        res["predicted_outcome"] = "extinguishes early" if res["probability"] >= 0.5 else "burns to completion"
    res["reliability"] = reliability.review("flex", res, fuel)
    return res


SWEEP_VARS = {"solid": ("oxygen_pct", "airflow_cm_s"),
              "flex": ("pressure_kpa", "oxygen_pct", "co2_fraction", "helium_fraction", "droplet_diameter_mm")}
SWEEP_DEFAULTS = {"oxygen_pct": 21.0, "airflow_cm_s": 10.0, "pressure_kpa": 101.3, "co2_fraction": 0.0,
                  "helium_fraction": 0.0, "droplet_diameter_mm": 3.0}


def prediction_sweep(model: str, vary: str, start: float, stop: float, steps: int = 9, material: str | None = None,
                     fuel: str | None = None, scenario: str = "ongoing_burn_trial", oxygen_pct: float | None = None,
                     airflow_cm_s: float | None = None, pressure_kpa: float | None = None,
                     co2_fraction: float | None = None, helium_fraction: float | None = None,
                     droplet_diameter_mm: float | None = None) -> dict:
    """Predict at evenly spaced values of one input, holding the others fixed."""
    if model not in SWEEP_VARS:
        return {"error": "model must be 'solid' or 'flex'"}
    if vary not in SWEEP_VARS[model]:
        return {"error": f"For the {model} model, vary one of: {', '.join(SWEEP_VARS[model])}"}
    group = material if model == "solid" else fuel
    if not group:
        return {"error": "Give material (solid model) or fuel (flex model)."}
    steps = max(2, min(int(steps), 25))
    given = dict(oxygen_pct=oxygen_pct, airflow_cm_s=airflow_cm_s, pressure_kpa=pressure_kpa,
                 co2_fraction=co2_fraction, helium_fraction=helium_fraction, droplet_diameter_mm=droplet_diameter_mm)
    base = {k: (v if v is not None else SWEEP_DEFAULTS[k]) for k, v in given.items()}
    points = []
    for i in range(steps):
        x = start + (stop - start) * i / (steps - 1)
        a = {**base, vary: x}
        if model == "solid":
            r = predictor.predict_solid(material, a["oxygen_pct"], a["airflow_cm_s"], scenario, pressure_kpa)
        else:
            r = predictor.predict_flex(fuel, a["pressure_kpa"], a["oxygen_pct"], a["co2_fraction"],
                                       a["helium_fraction"], a["droplet_diameter_mm"])
        if r["probability"] is None:
            return {"error": "; ".join(r["warnings"])}
        rev = reliability.review(model, r, group)
        points.append({vary: round(x, 4), "probability": r["probability"], "rating": rev["rating"],
                       "in_tested_range": not r["warnings"], "warnings": r["warnings"]})
    fixed = {k: base[k] for k in SWEEP_VARS[model] if k != vary}
    probs = [pt["probability"] for pt in points]
    return {"model": model, "material" if model == "solid" else "fuel": group, "varied": vary, "held_fixed": fixed,
            **({"scenario": scenario} if model == "solid" else {}),
            "points": points, "probability_range": [min(probs), max(probs)],
            "points_in_tested_range": sum(pt["in_tested_range"] for pt in points),
            "model_statistics": reliability.model_statistics(model),
            "meaning": reliability.TARGET[model],
            "note": "A flat curve can mean the model learned little from this input, not that it has no physical "
                    "effect. Points outside the tested range are extrapolations."}


def describe_database(table: str | None = None) -> dict:
    """Tables in the SQLite database, or one table's columns, units, provenance and sample rows."""
    meta = db.table_meta()
    if not table:
        return {"tables": [{k: m[k] for k in ("table_name", "kind", "row_count", "source_file", "grain",
                                               "source_records")} for m in meta.values()],
                "note": "Curated tables use NULL for missing values. src_* tables are the original NASA tables, "
                        "all TEXT, verbatim. Join tables to investigation_catalog on source_record."}
    if table not in meta:
        return {"error": f"Unknown table. Known: {', '.join(meta)}"}
    m = dict(meta[table])
    m["sample_rows"] = db.run_select(f'SELECT * FROM "{table}" LIMIT 3')["rows"]
    return m


def query_database(sql: str, limit: int = 100) -> dict:
    try:
        res = db.run_select(sql, limit)
    except db.QueryError as e:
        return {"error": str(e), "sql": sql}
    meta = db.table_meta()
    res["sql"] = sql
    res["table_notes"] = {t: meta[t]["caveats"] for t in res["tables_used"] if t in meta and meta[t]["caveats"]}
    if res["truncated"]:
        res["note"] = (f"Only the first {res['returned']} rows are shown. Use COUNT(*) or GROUP BY for totals "
                       "rather than counting returned rows.")
    return res


def run_material_advisor(**kw) -> dict:
    names = {f.name for f in fields(advisor.Scenario)}
    sc = advisor.Scenario(**{k: v for k, v in kw.items() if k in names and v is not None})
    return _compact_advice(advisor.advise(sc))


def _compact_advice(res: dict) -> dict:
    """Trim the advisor output to what the LLM needs (full tests lists are long)."""
    def slim(c):
        return {"material": c["material"], "rank": c["rank"], "is_selected": c["is_selected"],
                "evidence_strength": c["evidence_strength"], "match": c["match"],
                "comparable_tests": len(c["comparable_tests"]),
                "comparable_outcomes": pd.Series([t["outcome_group"] for t in c["comparable_tests"]]).value_counts()
                .to_dict() if c["comparable_tests"] else {},
                "example_tests": [{k: t[k] for k in ("investigation", "test_id", "material_raw", "oxygen_pct",
                                                     "airflow_readings_cm_s", "outcome_group", "notes", "locator")}
                                  for t in c["comparable_tests"][:3]],
                "stage_evidence": c["stage_evidence"],
                "model_probability_sustained": c["prediction"]["probability"] if c["prediction"] else None,
                "model_scenario": c["prediction_scenario"], "sort_basis": c["sort_basis"],
                "checks": c["checks"], "concerns": c["concerns"], "saffire": c["saffire"],
                "earth_ground_thresholds": c["ground"][:4], "excluded_reason": c["excluded_reason"],
                "citations": c["citations"][:6]}
    return {"scenario": res["scenario"], "priority": res["priority_label"],
            "your_material": [slim(c) for c in res["selected"]],
            "ranked_candidates": [slim(c) for c in res["candidates"]],
            "excluded": [slim(c) for c in res["excluded"]], "comparisons": res["comparisons"],
            "unassessable_constraints": res["unassessable_constraints"], "disclaimer": res["disclaimer"]}


def search_nasa_documents(query: str, source_record: str | None = None, k: int = 5) -> dict:
    hits = evidence.search(query, k=max(1, min(int(k), 8)), source_record=source_record)
    return {"results": hits, "note": "Chunks marked 'Experiment PLAN' describe proposed tests and must not be "
                                     "cited as observed results. PDF text may flatten tables."}


def list_investigations() -> dict:
    c = catalog()
    return {"investigations": [{"source_record": r.source_record, "name": r.investigation_name,
                                "title": r.official_title, "fuel_phase": r.fuel_phase, "role": r.role, "url": r.url}
                               for r in c.itertuples()]}


def get_investigation(source_record: str) -> dict:
    c = catalog()
    row = c[c["source_record"] == source_record]
    if row.empty:
        return {"error": f"Unknown source_record. Known: {', '.join(c['source_record'])}"}
    r = row.iloc[0].to_dict()
    for k in ("objective", "approach", "primary_materials"):
        r[k] = r[k][:1500]
    pubs = publications()
    r["publications"] = pubs[pubs["source_record"] == source_record].head(8).to_dict("records")
    return r


def saffire_results(material: str | None = None) -> dict:
    return {"samples": saffire(material),
            "note": "Saffire I-III (PSI-98/99/100): large samples burned in uncrewed Cygnus vehicles. "
                    "Values are quoted as NASA published them; blank-material rows are not attributed."}


def earth_ground_thresholds(material_family: str | None = None) -> dict:
    g = ground()
    if material_family:
        g = g[g["material"].str.upper() == material_family.upper()]
    return {"rows": g.head(30).to_dict("records"), "families": sorted(ground()["material"].unique().tolist()),
            "note": "Earth-gravity ULOI/MOC oxygen thresholds from NTRS 20110008636 (not PSI). Different "
                    "quantity from the ISS burn outcomes; comparison only."}


def model_performance(model: str = "solid") -> dict:
    m = dict(predictor.metrics()[model])
    m.pop("oof", None)
    return m


def get_current_advisor_results(_context: dict | None = None) -> dict:
    if not _context:
        return {"error": "The engineer has not run the Material Advisor in this session."}
    return _compact_advice(_context)


TOOLS = [
    {"name": "list_materials", "description": "List the solid materials NASA burned in orbit, with test counts.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "material_summary",
     "description": "Counts, outcome mix, tested oxygen/airflow/pressure ranges, shapes, variants and Saffire samples "
                    "for one solid material.",
     "input_schema": {"type": "object", "properties": {"material": {"type": "string"}}, "required": ["material"]}},
    {"name": "find_tests",
     "description": "Find individual BASS/BASS-II solid combustion tests by material, investigation, oxygen range, "
                    "airflow range and outcome group. Returns counts, outcome mix and test rows with crew notes and "
                    "source locators. Use for any question about specific experiments or observed results.",
     "input_schema": {"type": "object", "properties": {
         "material": {"type": "string"}, "source_record": {"type": "string", "description": "e.g. PSI-25"},
         "oxygen_min": {"type": "number"}, "oxygen_max": {"type": "number"},
         "airflow_min": {"type": "number", "description": "cm/s"}, "airflow_max": {"type": "number"},
         "outcome_group": {"type": "string", "enum": ["sustained burn", "burned, then went out",
                                                      "brief flame, not sustained", "no ignition",
                                                      "suppressed (agent/N2)", "not usable"]},
         "limit": {"type": "integer", "description": "max rows, default 15"}}}},
    {"name": "condition_trends",
     "description": "Observed sustained-flame counts binned by oxygen and by airflow, and test outcomes by oxygen "
                    "bin. Use for 'how does oxygen/airflow affect...' questions.",
     "input_schema": {"type": "object", "properties": {"material": {"type": "string"}}}},
    {"name": "predict_sustained_burning",
     "description": "Trained model's probability that a solid material's flame stays lit at an oxygen/airflow "
                    "condition, with out-of-range warnings and the nearest real NASA stages.",
     "input_schema": {"type": "object", "properties": {
         "material": {"type": "string"}, "oxygen_pct": {"type": "number"}, "airflow_cm_s": {"type": "number"},
         "scenario": {"type": "string", "enum": ["ongoing_burn_trial", "ignition_trial"]},
         "pressure_kpa": {"type": "number"},
         "mission": {"type": "string", "enum": list(advisor.MISSIONS)}},
         "required": ["material", "oxygen_pct", "airflow_cm_s"]}},
    {"name": "predict_droplet_extinction",
     "description": "FLEX droplet model (methanol/heptane): probability a droplet flame extinguishes early.",
     "input_schema": {"type": "object", "properties": {
         "fuel": {"type": "string", "enum": ["Methanol", "Heptane"]}, "pressure_kpa": {"type": "number"},
         "oxygen_pct": {"type": "number"}, "co2_fraction": {"type": "number"},
         "helium_fraction": {"type": "number"}, "droplet_diameter_mm": {"type": "number"}},
         "required": ["fuel", "pressure_kpa", "oxygen_pct"]}},
    {"name": "run_material_advisor",
     "description": "Run the Material Advisor for a scenario: ranks PSI-tested materials by priority and evidence, "
                    "with constraint checks, concerns, comparisons and citations.",
     "input_schema": {"type": "object", "properties": {
         "mode": {"type": "string", "enum": ["analyze", "discover"]}, "material": {"type": "string"},
         "mission": {"type": "string", "enum": list(advisor.MISSIONS)},
         "oxygen_pct": {"type": "number"}, "pressure_kpa": {"type": "number"}, "airflow_cm_s": {"type": "number"},
         "geometry": {"type": "string", "enum": advisor.GEOMETRIES}, "thickness_mm": {"type": "number"},
         "max_thickness_mm": {"type": "number"},
         "priority": {"type": "string", "enum": list(advisor.PRIORITIES)}}}},
    {"name": "get_current_advisor_results",
     "description": "The Material Advisor results currently on the engineer's dashboard. Use when they ask about "
                    "'my results', 'this ranking', or why a material ranked where it did.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "search_nasa_documents",
     "description": "Keyword search over NASA PSI metadata, science documents and reports (757 passages). Returns "
                    "passages with source locators. Use for mechanisms, background and published findings.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "source_record": {"type": "string"}, "k": {"type": "integer"}},
         "required": ["query"]}},
    {"name": "list_investigations", "description": "All 19 PSI investigations plus the NTRS ground report.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_investigation", "description": "Objective, approach, materials, variables and publications of one "
                                                 "investigation.",
     "input_schema": {"type": "object", "properties": {"source_record": {"type": "string"}},
                      "required": ["source_record"]}},
    {"name": "saffire_results", "description": "Saffire large-scale burn samples, including the only curated "
                                               "flame-spread measurements.",
     "input_schema": {"type": "object", "properties": {"material": {"type": "string"}}}},
    {"name": "earth_ground_thresholds", "description": "Earth-gravity oxygen limits (ULOI/MOC) by material family.",
     "input_schema": {"type": "object", "properties": {"material_family": {"type": "string"}}}},
    {"name": "model_performance", "description": "Validation metrics and limitations of a predictor.",
     "input_schema": {"type": "object", "properties": {"model": {"type": "string", "enum": ["solid", "flex"]}}}},
    {"name": "prediction_sweep",
     "description": "Run a model at evenly spaced values of ONE input (e.g. oxygen 16-30%) with the others held "
                    "fixed. Use for 'how does X change the chance of...' questions. Each point has a probability, "
                    "an in-range flag and a reliability rating; model statistics are returned once.",
     "input_schema": {"type": "object", "properties": {
         "model": {"type": "string", "enum": ["solid", "flex"]},
         "vary": {"type": "string", "enum": ["oxygen_pct", "airflow_cm_s", "pressure_kpa", "co2_fraction",
                                             "helium_fraction", "droplet_diameter_mm"],
                  "description": "solid: oxygen_pct or airflow_cm_s; flex: any but airflow_cm_s"},
         "start": {"type": "number"}, "stop": {"type": "number"},
         "steps": {"type": "integer", "description": "2-25, default 9"},
         "material": {"type": "string", "description": "solid model"},
         "fuel": {"type": "string", "enum": ["Methanol", "Heptane"], "description": "flex model"},
         "scenario": {"type": "string", "enum": ["ongoing_burn_trial", "ignition_trial"]},
         "oxygen_pct": {"type": "number"}, "airflow_cm_s": {"type": "number"}, "pressure_kpa": {"type": "number"},
         "co2_fraction": {"type": "number"}, "helium_fraction": {"type": "number"},
         "droplet_diameter_mm": {"type": "number"}},
         "required": ["model", "vary", "start", "stop"]}},
    {"name": "describe_database",
     "description": "List the tables in the NASA SQLite database (no argument), or show one table's columns, "
                    "units, source file, investigations, caveats and 3 sample rows. Call before writing SQL "
                    "against a src_* (original NASA) table.",
     "input_schema": {"type": "object", "properties": {"table": {"type": "string"}}}},
    {"name": "query_database",
     "description": "Run ONE read-only SQLite SELECT over the curated NASA PSI tables and the original NASA "
                    "tables. Use when no curated tool answers the question (custom filters, counts, group-bys, "
                    "joins, FLEX tests, original NASA tables). Do all arithmetic here (COUNT, AVG, MIN/MAX), not "
                    "in your head. Always SELECT source_record (and source_file, source_row or source_url when "
                    "listing rows) so the result can be cited. Results are capped at 200 rows.",
     "input_schema": {"type": "object", "properties": {
         "sql": {"type": "string", "description": "A single SELECT or WITH ... SELECT statement"},
         "limit": {"type": "integer", "description": "max rows returned, default 100, max 200"}},
         "required": ["sql"]}},
]

_FUNCS = {f.__name__: f for f in (list_materials, material_summary, find_tests, condition_trends,
                                  predict_sustained_burning, predict_droplet_extinction, run_material_advisor,
                                  search_nasa_documents, list_investigations, get_investigation, saffire_results,
                                  earth_ground_thresholds, model_performance, prediction_sweep, describe_database,
                                  query_database)}

# Tables each curated tool reads (query_database reports its own from the SQL it ran).
TOOL_DATASETS = {
    "list_materials": ["solid_combustion_model", "saffire_samples"],
    "material_summary": ["solid_combustion_model", "airflow_readings", "saffire_samples"],
    "find_tests": ["solid_combustion_model", "airflow_readings"],
    "condition_trends": ["solid_stage_training", "solid_combustion_model"],
    "predict_sustained_burning": ["solid_stage_training"],
    "predict_droplet_extinction": ["flex_training"],
    "prediction_sweep": [],
    "run_material_advisor": ["solid_combustion_model", "airflow_readings", "solid_stage_training", "saffire_samples",
                             "ground_thresholds"],
    "get_current_advisor_results": ["solid_combustion_model", "airflow_readings", "solid_stage_training",
                                    "saffire_samples", "ground_thresholds"],
    "search_nasa_documents": [],
    "list_investigations": ["investigation_catalog"],
    "get_investigation": ["investigation_catalog", "publications"],
    "saffire_results": ["saffire_samples"],
    "earth_ground_thresholds": ["ground_thresholds"],
    "model_performance": [],
    "describe_database": [],
}
MODEL_ARTIFACTS = {"predict_sustained_burning": ["solid"], "predict_droplet_extinction": ["flex"],
                   "model_performance": None, "run_material_advisor": ["solid"],
                   "get_current_advisor_results": ["solid"]}
_RECORD_KEYS = ("source_record", "source_records", "investigations")


def _records_in(obj, found: set) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _RECORD_KEYS:
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, str):
                        found.add(x)
            elif k == "experiment_id" and isinstance(v, str):   # "<source_record>:<...>"
                found.add(v.split(":")[0])
            _records_in(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _records_in(v, found)


def provenance(name: str, args: dict, out: dict) -> dict:
    """Datasets, models, investigations and documents behind one tool result."""
    meta, invs = db.table_meta(), db.investigations()
    tables = list(out.get("tables_used") or TOOL_DATASETS.get(name, []))
    if name == "describe_database" and args.get("table"):
        tables = [args["table"]]
    models = MODEL_ARTIFACTS.get(name, [])
    if name == "prediction_sweep":
        models = [args.get("model")]
    elif name == "model_performance":
        models = [args.get("model", "solid")]
    tables += [reliability.TRAINING_TABLE[k] for k in models or [] if k in reliability.TRAINING_TABLE]
    tables = [t for t in dict.fromkeys(tables) if t in meta]

    found: set = set()
    _records_in(out, found)
    rows_level = bool(found & set(invs))
    if not rows_level:              # nothing row-level in the result: fall back to what the tables contain
        for t in tables:
            found |= set(meta[t]["source_records"])
    p = {
        "datasets": [{"table": t, "file": meta[t]["source_file"], "kind": meta[t]["kind"], "grain": meta[t]["grain"]}
                     for t in tables],
        "investigations": [invs[r] for r in sorted(found) if r in invs],
        "investigation_basis": "records present in the returned rows" if rows_level
        else "all records in the tables used (the result itself has no source_record)",
    }
    if models:
        p["models"] = [{"model": reliability.MODEL_FILE[k], "metrics": "model/metrics.json",
                        "trained_on": reliability.TRAINING_TABLE[k]} for k in models if k in reliability.MODEL_FILE]
    if name == "search_nasa_documents":
        p["datasets"] = [{"table": None, "file": "data/clean/evidence_chunks.jsonl", "kind": "documents",
                          "grain": "One passage of NASA PSI metadata, documents or reports"}]
        p["documents"] = [{k: h.get(k) for k in ("source_record", "source_file", "locator", "kind_label",
                                                  "source_url")} for h in out.get("results", [])]
    if name == "query_database":
        p["sql"] = args.get("sql")
    return p


def run_tool(name: str, args: dict, advisor_context: dict | None = None) -> dict:
    if name == "get_current_advisor_results":
        out = _clean(get_current_advisor_results(advisor_context))
        return out if "error" in out else {"provenance": _clean(provenance(name, args, out)), **out}
    fn = _FUNCS.get(name)
    if fn is None:
        return {"error": f"Unknown tool {name}"}
    allowed = TOOLS[[t["name"] for t in TOOLS].index(name)]["input_schema"]["properties"]
    unknown = set(args) - set(allowed)
    if unknown:
        return {"error": f"Unknown arguments: {sorted(unknown)}"}
    out = _clean(fn(**args))
    if "error" in out:
        return out
    # Provenance goes first so it survives if to_json has to truncate a long result.
    return {"provenance": _clean(provenance(name, args, out)), **out}


def to_json(result: dict) -> str:
    return json.dumps(result, default=str)[:60000]
