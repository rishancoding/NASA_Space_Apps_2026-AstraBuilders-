"""Core functions shared by the HTTP API and the chat agent.

Every function here returns plain JSON-ready dicts. Numbers that reach the UI
are wrapped by `val()` so each one carries its unit, source and a trust label:

    nasa_measured   value recorded in a NASA PSI table or report
    ai_label        outcome interpreted from NASA notes by AI review (no human sign-off)
    model_estimate  output of a model trained in model/train_flex.py
    earth_reference Earth-gravity ground test (NTRS), comparison only
    no_data         nothing in the data supports a value here

Rules carried over from data/DATA_HANDOFF.md and docs/MODEL_SCOPE.md:
- The models are FLEX droplet models only. Nothing here predicts solid
  materials, ignition, Moon/Mars behaviour or spacecraft safety.
- The material advisor ranks by evidence relevance, never by a safety score.
- Inputs outside the tested range get no model number.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
ARTIFACTS = ROOT / "model" / "artifacts"
SPEC = json.loads((ROOT / "model" / "model_spec.json").read_text())

FLEX_NUMERIC = ["pressure_kpa", "oxygen_pct", "co2_fraction", "helium_fraction", "droplet_diameter_mm"]
FLEX_FEATURES = ["fuel"] + FLEX_NUMERIC
FLEX_LABELS = {
    "fuel": ("Fuel", None), "pressure_kpa": ("Pressure", "kPa"), "oxygen_pct": ("Oxygen", "%"),
    "co2_fraction": ("CO₂ fraction", "mole fraction"), "helium_fraction": ("Helium fraction", "mole fraction"),
    "droplet_diameter_mm": ("Droplet diameter", "mm"),
}
FLEX_STEPS = {"pressure_kpa": 1, "oxygen_pct": 0.5, "co2_fraction": 0.01, "helium_fraction": 0.01, "droplet_diameter_mm": 0.05}

OUTCOME_TEXT = {
    "burn_observed": "Flame observed",
    "burn_then_extinguished": "Burned, then went out",
    "transient_or_not_sustained": "Brief flame, not sustained",
    "fuel_exhaustion": "Burned until fuel ran out",
    "insufficient_evidence": "Unclear from the notes",
    "no_ignition_observed": "Did not ignite",
    "hardware_failure": "Hardware failure",
    "partial_extinction": "Partly went out",
    "suppression_extinction": "Put out by suppressant",
    "Extinction": "Flame went out (extinction)",
    "Completion": "Droplet burned completely",
    "Disruption": "Test disrupted (no clean ending)",
}
GROUND_FAMILY = {"PMMA": "PMMA", "Ultem (PEI)": "PEI"}
TRUST = {
    "nasa_measured": "Recorded in a NASA PSI table or report",
    "ai_label": "Interpreted from NASA crew/report notes by AI review; no human sign-off",
    "model_estimate": "Estimated by a model trained on NASA FLEX data; see the Model page",
    "earth_reference": "Earth-gravity ground test (NTRS 20110008636); comparison only",
    "no_data": "No NASA data supports a value here",
}
MISSIONS = {
    "space_station": {"label": "Space station (microgravity)", "gravity_g": 0.0},
    "moon_base": {"label": "Moon base (0.17 g)", "gravity_g": 0.166},
    "mars_habitat": {"label": "Mars habitat (0.38 g)", "gravity_g": 0.38},
}


class InputError(ValueError):
    """Bad user input. `errors` is a list of {field, message} for the UI."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]
        super().__init__("; ".join(e["message"] for e in self.errors))


def val(value, unit=None, trust="nasa_measured", source=None, low=None, high=None, note=None):
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    has_data = value is not None or low is not None or high is not None
    out = {"value": _round(value), "unit": unit, "trust": trust if has_data else "no_data"}
    if low is not None or high is not None:
        out["range"] = [_round(low), _round(high)]
    if source:
        out["source"] = source
    if note:
        out["note"] = note
    return out


def _round(x, nd=4):
    if isinstance(x, (np.floating, float)):
        return round(float(x), nd)
    if isinstance(x, np.integer):
        return int(x)
    return x


def _num(s):
    try:
        x = float(s)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _csv(name):
    with (CLEAN / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _source(record, url=None, file=None, locator=None):
    return {k: v for k, v in {"record": record, "url": url, "file": file, "locator": locator}.items() if v}


# --------------------------------------------------------------------------- data

@lru_cache(maxsize=1)
def catalog():
    return {r["source_record"]: r for r in _csv("investigation_catalog.csv")}


@lru_cache(maxsize=1)
def evidence():
    text = (CLEAN / "evidence_chunks.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.split("\n") if line.strip()]  # not splitlines(): text holds U+2028


@lru_cache(maxsize=1)
def airflow_ranges():
    """Per solid test: min/max of exact anemometer readings (cm/s). Order is not time."""
    out = defaultdict(list)
    for r in _csv("airflow_readings.csv"):
        v = _num(r["airflow_display_cm_s"])
        if v is not None and r["reading_status"] == "exact_display":
            out[r["experiment_id"]].append(v)
    return {k: (min(v), max(v)) for k, v in out.items()}


@lru_cache(maxsize=1)
def solids():
    rows = _csv("solid_combustion_model.csv")
    ranges = airflow_ranges()
    for r in rows:
        for k in ["thickness_mm", "diameter_mm", "width_mm", "oxygen_pct", "oxygen_final_pct", "airflow_cm_s", "pressure_kpa"]:
            r[k] = _num(r[k])
        single = r["airflow_cm_s"]
        r["airflow_min"], r["airflow_max"] = ranges.get(r["experiment_id"], (single, single) if single is not None else (None, None))
        r["quality_flags"] = [f for f in r["quality_flags"].split("|") if f]
    return rows


@lru_cache(maxsize=1)
def solid_index():
    return {r["experiment_id"]: r for r in solids()}


@lru_cache(maxsize=1)
def stage_rows():
    rows = _csv("solid_stage_observations.csv")
    by_exp = defaultdict(list)
    for r in rows:
        by_exp[r["experiment_id"]].append(r)
    return by_exp


@lru_cache(maxsize=1)
def stage_training():
    rows = _csv("solid_stage_training.csv")
    for r in rows:
        r["oxygen_initial_pct"], r["airflow_cm_s"] = _num(r["oxygen_initial_pct"]), _num(r["airflow_cm_s"])
    return rows


@lru_cache(maxsize=1)
def flex_all():
    df = pd.read_csv(CLEAN / "flex_labeled.csv")
    for c in FLEX_NUMERIC + ["burn_time_s", "extinction_diameter_mm", "nitrogen_fraction"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@lru_cache(maxsize=1)
def flex_train():
    df = pd.read_csv(CLEAN / "flex_training.csv")
    for c in FLEX_NUMERIC + ["burn_time_s"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@lru_cache(maxsize=1)
def ground():
    rows = _csv("ground_thresholds.csv")
    for r in rows:
        for k in ["thickness_mm", "diameter_mm", "uloi_oxygen_pct", "moc_oxygen_pct", "pressure_kpa"]:
            r[k] = _num(r[k])
    return rows


@lru_cache(maxsize=1)
def publications():
    return _csv("publications.csv")


@lru_cache(maxsize=1)
def metrics():
    return json.loads((ARTIFACTS / "metrics.json").read_text())


@lru_cache(maxsize=1)
def oof():
    return json.loads((ARTIFACTS / "oof_predictions.json").read_text())


@lru_cache(maxsize=1)
def extinction_model():
    return joblib.load(ARTIFACTS / "extinction_model.joblib")


@lru_cache(maxsize=1)
def burn_time_model():
    return joblib.load(ARTIFACTS / "burn_time_model.joblib")


@lru_cache(maxsize=1)
def search_index():
    """TF-IDF + latent semantic analysis over the evidence chunks, built in memory (~1 s)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    chunks = evidence()
    texts = [f"{c['source_record']} {catalog().get(c['source_record'], {}).get('investigation_name', '')} {c['locator']} {c['text']}" for c in chunks]
    vec = TfidfVectorizer(stop_words="english", sublinear_tf=True, ngram_range=(1, 2), max_df=0.6)
    tfidf = vec.fit_transform(texts)
    # Truncated SVD via the small document Gram matrix (757 x 757): same result as sklearn's
    # TruncatedSVD but ~100x faster here, because documents are far fewer than terms.
    gram = (tfidf @ tfidf.T).toarray()
    w, u = np.linalg.eigh(gram)
    top = np.argsort(w)[::-1][:150]
    s = np.sqrt(np.clip(w[top], 1e-12, None))
    u = u[:, top]
    components = np.asarray(tfidf.T @ u) / s  # term -> concept projection (terms x 150)
    lsa = normalize(u * s)
    return vec, components, tfidf, lsa


# --------------------------------------------------------------------------- options

def get_options():
    """Everything a UI needs to build its forms: dropdowns, slider bounds, presets, labels."""
    domains = SPEC["domains_by_fuel"]
    flex_fields = []
    for f in FLEX_NUMERIC:
        lows = [d["fields"][f]["min"] for d in domains.values()]
        highs = [d["fields"][f]["max"] for d in domains.values()]
        med = float(flex_train()[f].median())
        flex_fields.append({
            "name": f, "label": FLEX_LABELS[f][0], "unit": FLEX_LABELS[f][1], "step": FLEX_STEPS[f],
            "min": _round(min(lows), 3), "max": _round(max(highs), 3), "default": _round(med, 3),
            "tested_range_by_fuel": {fuel: [_round(d["fields"][f]["min"], 3), _round(d["fields"][f]["max"], 3)] for fuel, d in domains.items()},
        })
    s = solids()
    mats = Counter(r["material"] for r in s if r["material"] != "Unresolved material")
    oxy = [r["oxygen_pct"] for r in s if r["oxygen_pct"] is not None]
    flows = [v for r in s for v in (r["airflow_min"], r["airflow_max"]) if v is not None]
    m = metrics()
    return {
        "flex": {
            "fuels": SPEC["fuel_categories"],
            "fields": flex_fields,
            "nitrogen": "Nitrogen is the remainder: 1 − oxygen/100 − CO₂ − helium. It must not be negative.",
            "predictions": {
                "extinction": {"enabled": m["extinction"]["prediction_enabled"], "reason": m["extinction"]["promotion_gate"]},
                "burn_time": {"enabled": m["burn_time"]["prediction_enabled"], "reason": m["burn_time"]["promotion_gate"]},
            },
        },
        "solids": {
            "materials": [{"name": k, "tests": v, "earth_reference": k in GROUND_FAMILY} for k, v in mats.most_common()],
            "geometries": sorted({r["sample_geometry"] for r in s if r["sample_geometry"] != "unknown"}),
            "flow_directions": sorted({r["flow_direction"] for r in s if r["flow_direction"]}),
            "outcomes": [{"value": k, "label": OUTCOME_TEXT[k]} for k in sorted({r["outcome"] for r in s})],
            "oxygen_pct": {"min": _round(min(oxy), 2), "max": _round(max(oxy), 2), "step": 0.1, "default": 21.0, "unit": "%"},
            "airflow_cm_s": {"min": 0, "max": _round(max(flows), 1), "step": 0.5, "default": 10.0, "unit": "cm/s"},
            "pressure_note": "Solid-fuel tests did not vary pressure (BASS ≈ 98 kPa; BASS-II not recorded). Pressure cannot be checked for solids.",
        },
        "missions": [{"value": k, **v} for k, v in MISSIONS.items()],
        "presets": [
            {"id": "iss_cabin", "label": "ISS-like cabin", "oxygen_pct": 21.0, "pressure_kpa": 101.3, "airflow_cm_s": 10.0,
             "note": "Typical sea-level-like cabin air; airflow is an example value."},
            {"id": "exploration_atmosphere", "label": "Exploration habitat (34% O₂, 56.5 kPa)", "oxygen_pct": 34.0, "pressure_kpa": 56.5, "airflow_cm_s": 10.0,
             "note": "Oxygen-enriched, reduced-pressure atmosphere studied for exploration habitats. Above every solid-fuel test in this data."},
            {"id": "low_flow", "label": "Stagnant corner (low airflow)", "oxygen_pct": 21.0, "pressure_kpa": 101.3, "airflow_cm_s": 1.0,
             "note": "Low ventilation, where microgravity flames can behave differently from Earth."},
        ],
        "priorities": [
            {"value": "evidence_strength", "label": "Most NASA evidence near my conditions"},
            {"value": "fewest_sustained_flames", "label": "Fewest sustained flames observed near my conditions"},
        ],
        "trust_labels": TRUST,
        "outcome_labels": OUTCOME_TEXT,
    }


# --------------------------------------------------------------------------- investigations

def list_investigations(fuel_phase=None, q=None):
    counts = Counter(r["source_record"] for r in solids())
    ev = Counter(c["source_record"] for c in evidence())
    pubs = Counter(p.get("source_record") for p in publications())
    tables = Counter(t["source_record"] for t in json.loads((CLEAN / "table_index.json").read_text()))
    out = []
    for rec, r in catalog().items():
        if fuel_phase and r["fuel_phase"] != fuel_phase:
            continue
        hay = " ".join([rec, r["investigation_name"], r["official_title"], r["objective"], r["primary_materials"]]).lower()
        if q and q.lower() not in hay:
            continue
        out.append({
            "source_record": rec, "name": r["investigation_name"], "title": r["official_title"],
            "fuel_phase": r["fuel_phase"], "role": r["role"], "url": r["url"],
            "summary": _first_sentences(r["objective"], 2), "primary_materials": r["primary_materials"],
            "counts": {"solid_tests": counts.get(rec, 0), "flex_tests": int((flex_all()["source_record"] == rec).sum()),
                       "tables": tables.get(rec, 0), "evidence_passages": ev.get(rec, 0), "publications": pubs.get(rec, 0)},
        })
    return out


def get_investigation(source_record):
    r = catalog().get(source_record)
    if not r:
        raise InputError({"field": "source_record", "message": f"Unknown investigation {source_record}"})
    summary = next(i for i in list_investigations() if i["source_record"] == source_record)
    tables = [t for t in json.loads((CLEAN / "table_index.json").read_text()) if t["source_record"] == source_record]
    return {
        **summary,
        "objective": r["objective"].strip(), "approach": r["approach"].strip(),
        "measured_variables": r["measured_variables"], "doi": r["doi"], "license": r["license"],
        "tables": [{"file": t.get("file"), "rows": t.get("row_count"), "columns": t.get("original_headers") or t.get("headers")} for t in tables],
        "publications": [{"title": p.get("title"), "year": p.get("year"), "doi": p.get("doi"), "url": p.get("url")}
                         for p in publications() if p.get("source_record") == source_record][:25],
    }


def _first_sentences(text, n):
    parts = re.split(r"(?<=[.!?])\s+", " ".join((text or "").split()))
    return " ".join(parts[:n])


# --------------------------------------------------------------------------- experiments

def _solid_summary(r):
    flow = None
    if r["airflow_min"] is not None:
        flow = val(r["airflow_min"] if r["airflow_min"] == r["airflow_max"] else None, "cm/s",
                   low=r["airflow_min"], high=r["airflow_max"], source=_source(r["source_record"], r["source_url"], r["source_file"]))
        if r["airflow_min"] != r["airflow_max"]:
            flow["note"] = "Several airflow settings during the test; outcomes are not matched to a setting"
    return {
        "experiment_id": r["experiment_id"], "dataset": "solid", "source_record": r["source_record"],
        "investigation": r["investigation_name"], "test_id": r["test_id"], "date": r["test_date"],
        "material": r["material"], "material_raw": r["material_raw"], "geometry": r["sample_geometry"],
        "flow_direction": r["flow_direction"] or None,
        "oxygen_pct": val(r["oxygen_pct"], "%"), "airflow_cm_s": flow or val(None, "cm/s", trust="no_data", note=r["airflow_raw"] or None),
        "airflow_raw": r["airflow_raw"],
        "outcome": {"value": r["outcome"], "label": OUTCOME_TEXT.get(r["outcome"], r["outcome"]), "trust": "ai_label"},
        "any_flame": {"value": {"1": True, "0": False}.get(r["burned_binary"]), "trust": "ai_label"},
        "url": r["source_url"],
    }


def _flex_summary(r):
    src = _source("PSI-69", r["source_url"], r["source_file"], f"row {r['source_row']}")
    return {
        "experiment_id": r["experiment_id"], "dataset": "flex", "source_record": "PSI-69", "investigation": "FLEX",
        "test_id": str(r["test_id"]), "date": r["test_date"], "fuel": r["fuel"],
        **{f: val(r[f], FLEX_LABELS[f][1], source=src) for f in FLEX_NUMERIC},
        "burn_time_s": val(r["burn_time_s"], "s", source=src),
        "outcome": {"value": r["test_end_raw"], "label": OUTCOME_TEXT[r["test_end_raw"]], "trust": "nasa_measured"},
        "url": r["source_url"],
    }


def list_experiments(dataset="solid", source_record=None, material=None, fuel=None, outcome=None, geometry=None,
                     oxygen_min=None, oxygen_max=None, airflow_min=None, airflow_max=None, q=None,
                     sort="test", page=1, page_size=25):
    page, page_size = max(1, int(page)), max(1, min(200, int(page_size)))
    if dataset == "solid":
        rows = solids()
        def keep(r):
            if source_record and r["source_record"] != source_record: return False
            if material and r["material"].lower() != material.lower(): return False
            if outcome and r["outcome"] != outcome: return False
            if geometry and r["sample_geometry"] != geometry: return False
            o = r["oxygen_pct"]
            if oxygen_min is not None and (o is None or o < oxygen_min): return False
            if oxygen_max is not None and (o is None or o > oxygen_max): return False
            lo, hi = r["airflow_min"], r["airflow_max"]
            if airflow_min is not None and (hi is None or hi < airflow_min): return False
            if airflow_max is not None and (lo is None or lo > airflow_max): return False
            if q and q.lower() not in f"{r['notes']} {r['material_raw']} {r['experiment_id']}".lower(): return False
            return True
        hits = [r for r in rows if keep(r)]
        keys = {"oxygen": lambda r: r["oxygen_pct"] or 0, "airflow": lambda r: r["airflow_max"] if r["airflow_max"] is not None else -1,
                "material": lambda r: r["material"], "date": lambda r: r["test_date"], "test": lambda r: (r["source_record"], r["test_date"])}
        hits.sort(key=keys.get(sort, keys["test"]))
        items = [_solid_summary(r) for r in hits[(page - 1) * page_size: page * page_size]]
    elif dataset == "flex":
        df = flex_all()
        if fuel: df = df[df["fuel"].str.lower() == fuel.lower()]
        if outcome: df = df[df["test_end_raw"] == outcome]
        if oxygen_min is not None: df = df[df["oxygen_pct"] >= oxygen_min]
        if oxygen_max is not None: df = df[df["oxygen_pct"] <= oxygen_max]
        if q: df = df[df["experiment_id"].str.contains(q, case=False, regex=False)]
        sort_col = {"oxygen": "oxygen_pct", "date": "test_date", "pressure": "pressure_kpa"}.get(sort, "test_id")
        df = df.sort_values(sort_col)
        hits = df
        items = [_flex_summary(r) for r in df.iloc[(page - 1) * page_size: page * page_size].to_dict("records")]
    else:
        raise InputError({"field": "dataset", "message": "dataset must be 'solid' or 'flex'"})
    return {"total": len(hits), "page": page, "page_size": page_size, "items": items}


def get_experiment(experiment_id):
    r = solid_index().get(experiment_id)
    if r:
        stages = [{
            "order": int(s["event_order"]), "event": s["event_state"], "cause": s["event_cause"] or None,
            "airflow_cm_s": val(_num(s["airflow_cm_s"]), "cm/s", note=s["airflow_qualifier"] or None),
            "sustained_flame": {"value": {"1": True, "0": False}.get(s["sustained_flame_binary"]), "trust": "ai_label"},
            "evidence_quote": s["evidence_quote"] or None, "used_for_training": s["training_eligible"] == "true",
            "exclusion_reasons": [e for e in s["exclusion_reasons"].split("|") if e],
        } for s in stage_rows().get(experiment_id, [])]
        src = _source(r["source_record"], r["source_url"], r["source_file"], f"row {r['source_row']}")
        return {
            **_solid_summary(r),
            "dimensions": {k: val(r[k], "mm", source=src) for k in ["thickness_mm", "diameter_mm", "width_mm"]},
            "oxygen_final_pct": val(r["oxygen_final_pct"], "%", source=src),
            "pressure_kpa": val(r["pressure_kpa"], "kPa", source=src) if r["pressure_kpa"] is not None
                            else val(None, "kPa", trust="no_data", note="Pressure not recorded for this test"),
            "fan_display_raw": r["fan_display_raw"] or None,
            "crew_notes": r["notes"] or None, "quality_flags": r["quality_flags"],
            "stages": stages, "source": {**src, "supplement": r["supplement_file"] or None, "supplement_locator": r["supplement_locator"] or None},
            "earth_reference": ground_comparison(r["material"])["earth_tests"] if r["material"] in GROUND_FAMILY else [],
        }
    df = flex_all()
    hit = df[df["experiment_id"] == experiment_id]
    if len(hit):
        f = hit.iloc[0].to_dict()
        src = _source("PSI-69", f["source_url"], f["source_file"], f"row {f['source_row']}")
        return {
            **_flex_summary(f),
            "nitrogen_fraction": val(f["nitrogen_fraction"], "mole fraction", source=src),
            "extinction_diameter_mm": val(f["extinction_diameter_mm"], "mm", source=src),
            "burning_rate_raw": None if pd.isna(f["burning_rate_raw"]) else str(f["burning_rate_raw"]),
            "burning_rate_note": f["burning_rate_unit_status"],
            "used_for_training": f["training_eligible"] is True or str(f["training_eligible"]).lower() == "true",
            "exclusion_reasons": [e for e in str(f["exclusion_reasons"] if not pd.isna(f["exclusion_reasons"]) else "").split("|") if e],
            "source": src,
        }
    raise InputError({"field": "experiment_id", "message": f"No experiment {experiment_id}"})


def compare_experiments(experiment_a, experiment_b):
    a, b = get_experiment(experiment_a), get_experiment(experiment_b)
    rows = []
    for key in sorted(set(a) | set(b)):
        if key in {"stages", "source", "earth_reference", "crew_notes", "quality_flags", "dimensions"}:
            continue
        va, vb = a.get(key), b.get(key)
        sa = va.get("value") if isinstance(va, dict) and "value" in va else va
        sb = vb.get("value") if isinstance(vb, dict) and "value" in vb else vb
        rows.append({"field": key, "a": va, "b": vb, "different": sa != sb})
    if a["dataset"] != b["dataset"]:
        note = "These come from different kinds of experiments (solid sample vs liquid droplet), so differences are not like-for-like."
    else:
        note = "Differences are shown as recorded. Several conditions usually differ at once, so no single cause can be assigned."
    return {"a": a, "b": b, "fields": rows, "differences": [r["field"] for r in rows if r["different"]], "note": note}


# --------------------------------------------------------------------------- similarity

def _coverage_label(d):
    if d is None:
        return {"level": "none", "label": "No comparable NASA test"}
    if d <= 1.0:
        return {"level": "close", "label": "NASA tested close to these conditions"}
    if d <= 2.5:
        return {"level": "partial", "label": "Nearest NASA tests are somewhat different"}
    return {"level": "none", "label": "No NASA test near these conditions"}


def _solid_distance(r, oxygen_pct, airflow_cm_s, oxygen_scale=1.5, flow_scale=4.0):
    """Distance in 'typical-difference' units: 1.5 oxygen points or 4 cm/s ≈ 1 unit."""
    if r["oxygen_pct"] is None:
        return None, {}
    d_o = (r["oxygen_pct"] - oxygen_pct) / oxygen_scale
    parts = {"oxygen_gap_pct": _round(r["oxygen_pct"] - oxygen_pct, 2)}
    if airflow_cm_s is None:
        return abs(d_o), parts
    lo, hi = r["airflow_min"], r["airflow_max"]
    if lo is None:
        d_f, parts["airflow_gap_cm_s"] = 2.0, None  # unknown airflow: fixed penalty
    else:
        gap = 0.0 if lo <= airflow_cm_s <= hi else min(abs(airflow_cm_s - lo), abs(airflow_cm_s - hi))
        d_f, parts["airflow_gap_cm_s"] = gap / flow_scale, _round(gap, 2)
    return math.hypot(d_o, d_f), parts


def find_similar_solid(oxygen_pct, airflow_cm_s=None, material=None, geometry=None, k=8):
    _check_range("oxygen_pct", oxygen_pct, 0, 100)
    if airflow_cm_s is not None:
        _check_range("airflow_cm_s", airflow_cm_s, 0, 1000)
    scored = []
    for r in solids():
        if material and r["material"].lower() != material.lower():
            continue
        if geometry and r["sample_geometry"] != geometry:
            continue
        d, parts = _solid_distance(r, oxygen_pct, airflow_cm_s)
        if d is not None:
            scored.append((d, parts, r))
    scored.sort(key=lambda t: t[0])
    top = scored[:k]
    best = top[0][0] if top else None
    return {
        "query": {"oxygen_pct": oxygen_pct, "airflow_cm_s": airflow_cm_s, "material": material, "geometry": geometry},
        "coverage": {**_coverage_label(best), "nearest_distance": _round(best, 3) if best is not None else None},
        "method": "Distance where 1 unit ≈ 1.5 oxygen points or 4 cm/s airflow outside the test's recorded airflow range. Tests with unknown airflow get a fixed penalty.",
        "matches": [{**_solid_summary(r), "distance": _round(d, 3), "similarity": _round(math.exp(-d), 3), "gaps": parts}
                    for d, parts, r in top],
    }


def _flex_scale():
    df = flex_train()
    return {f: float(df[f].std()) or 1.0 for f in FLEX_NUMERIC}


def find_similar_flex(fuel, oxygen_pct, pressure_kpa, co2_fraction=0.0, helium_fraction=0.0, droplet_diameter_mm=None, k=6):
    inputs = _validate_flex(dict(fuel=fuel, oxygen_pct=oxygen_pct, pressure_kpa=pressure_kpa, co2_fraction=co2_fraction,
                                 helium_fraction=helium_fraction, droplet_diameter_mm=droplet_diameter_mm), allow_out_of_range=True)
    return _flex_neighbours(inputs, k)


def _flex_neighbours(inputs, k=6):
    df = flex_all()
    df = df[(df["fuel"] == inputs["fuel"]) & df[FLEX_NUMERIC].notna().all(axis=1)]
    scale = _flex_scale()
    d = np.sqrt(sum(((df[f] - inputs[f]) / scale[f]) ** 2 for f in FLEX_NUMERIC))
    order = np.argsort(d.to_numpy())[:k]
    rows = df.iloc[order].to_dict("records")
    dist = d.to_numpy()[order]
    best = float(dist[0]) if len(dist) else None
    # FLEX distances are in standard deviations across 5 features, so loosen the labels.
    cov = _coverage_label(None if best is None else best / 1.5)
    return {
        "coverage": {**cov, "nearest_distance": _round(best, 3)},
        "method": "Euclidean distance in standard deviations of the FLEX training data, same fuel only.",
        "matches": [{**_flex_summary(r), "distance": _round(float(x), 3), "similarity": _round(math.exp(-float(x) / 1.5), 3)}
                    for r, x in zip(rows, dist)],
    }


# --------------------------------------------------------------------------- FLEX models

def _check_range(field, value, lo, hi):
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(value) or value < lo or value > hi:
        raise InputError({"field": field, "message": f"{field} must be a number between {lo} and {hi}"})


def _validate_flex(inputs, allow_out_of_range=False):
    errors, warnings = [], []
    fuel = inputs.get("fuel")
    fuels = {f.lower(): f for f in SPEC["fuel_categories"]}
    if not isinstance(fuel, str) or fuel.lower() not in fuels:
        raise InputError({"field": "fuel", "message": f"Fuel must be one of {SPEC['fuel_categories']}"})
    fuel = fuels[fuel.lower()]
    clean = {"fuel": fuel}
    for f in FLEX_NUMERIC:
        v = inputs.get(f)
        if v is None and f in ("co2_fraction", "helium_fraction"):
            v = 0.0
        if v is None and f == "droplet_diameter_mm":
            v = float(flex_train()[flex_train()["fuel"] == fuel][f].median())
            warnings.append({"field": f, "message": f"No droplet diameter given; used the typical tested value ({v:.2f} mm)."})
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            errors.append({"field": f, "message": f"{FLEX_LABELS[f][0]} must be a number"})
            continue
        clean[f] = float(v)
    if errors:
        raise InputError(errors)
    if not 0 < clean["oxygen_pct"] <= 100:
        errors.append({"field": "oxygen_pct", "message": "Oxygen must be between 0 and 100%"})
    for f in ("co2_fraction", "helium_fraction"):
        if not 0 <= clean[f] <= 1:
            errors.append({"field": f, "message": f"{FLEX_LABELS[f][0]} must be between 0 and 1"})
    if clean["pressure_kpa"] <= 0:
        errors.append({"field": "pressure_kpa", "message": "Pressure must be above 0 kPa"})
    if clean["droplet_diameter_mm"] <= 0:
        errors.append({"field": "droplet_diameter_mm", "message": "Droplet diameter must be above 0 mm"})
    n2 = 1 - clean["oxygen_pct"] / 100 - clean["co2_fraction"] - clean["helium_fraction"]
    if n2 < -1e-9:
        errors.append({"field": "oxygen_pct", "message": "Oxygen, CO₂ and helium add up to more than 100% of the gas"})
    if errors:
        raise InputError(errors)
    clean["nitrogen_fraction"] = round(max(0.0, n2), 6)
    dom = SPEC["domains_by_fuel"][fuel]["fields"]
    outside = []
    for f in FLEX_NUMERIC:
        lo, hi = dom[f]["min"], dom[f]["max"]
        if not lo - 1e-9 <= clean[f] <= hi + 1e-9:
            outside.append({"field": f, "message": f"{FLEX_LABELS[f][0]} {clean[f]:g} is outside the tested {fuel} range ({lo:.3g}–{hi:.3g} {FLEX_LABELS[f][1]})",
                            "tested_range": [_round(lo, 3), _round(hi, 3)]})
    clean["_outside"], clean["_warnings"] = outside, warnings
    return clean


def _frame(inputs):
    return pd.DataFrame([{f: inputs[f] for f in FLEX_FEATURES}])


def _unavailable(reason, inputs, neighbours, extra=None):
    return {"available": False, "reason": reason, "inputs": _public(inputs), "nearest_tests": neighbours, **(extra or {})}


def _public(inputs):
    return {k: v for k, v in inputs.items() if not k.startswith("_")}


def predict_extinction(fuel, oxygen_pct, pressure_kpa, co2_fraction=0.0, helium_fraction=0.0, droplet_diameter_mm=None):
    """Estimate the chance a FLEX-like droplet flame ends in Extinction rather than Completion."""
    inputs = _validate_flex(dict(fuel=fuel, oxygen_pct=oxygen_pct, pressure_kpa=pressure_kpa, co2_fraction=co2_fraction,
                                 helium_fraction=helium_fraction, droplet_diameter_mm=droplet_diameter_mm))
    neighbours = _flex_neighbours(inputs)
    art, m = extinction_model(), metrics()["extinction"]
    if not art["enabled"]:
        return _unavailable(m["promotion_gate"], inputs, neighbours)
    if inputs["_outside"]:
        return _unavailable("Inputs are outside the tested range, so no model number is shown.", inputs, neighbours,
                            {"out_of_range": inputs["_outside"]})
    X = _frame(inputs)
    p = float(art["model"].predict_proba(X)[0, 1])
    spread = np.array([e.predict_proba(X)[0, 1] for e in art["ensemble"]])
    lo, hi = np.percentile(spread, [10, 90])
    src = {"record": "PSI-69", "url": SPEC["source_url"], "model": m["selected_model"]}
    return {
        "available": True,
        "inputs": _public(inputs),
        "probability_extinction": val(p, "probability", trust="model_estimate", low=lo, high=hi, source=src,
                                      note="Range = spread across models refit on resampled NASA tests"),
        "compared_with_typical": {
            "leans": "extinction" if p >= art["threshold"] else "completion",
            "label": ("Typical for FLEX: the flame most likely goes out before the droplet is used up"
                      if p >= art["threshold"] else
                      "Leans toward burning to completion compared with typical FLEX tests"),
            "base_rate": _round(art.get("base_rate", 0.87)),
            "threshold": _round(art["threshold"]),
            "note": "Most FLEX flames (87%) ended in extinction. The threshold was tuned to separate the two endings as well as possible.",
        },
        "factors": _factors(inputs, lambda X_: float(art["model"].predict_proba(X_)[0, 1]), "probability points"),
        "nearest_tests": neighbours,
        "warnings": inputs["_warnings"] + ([{"field": None, "message": "Nearest NASA tests are not very close; treat this estimate with extra caution."}]
                                           if neighbours["coverage"]["level"] != "close" else [])
                    + ([{"field": "fuel", "message": "Only 8 methanol tests burned to completion, so within methanol the model separates the two endings weakly (held-out AUC ≈ 0.6). The overall rate is reliable; small differences are not."}]
                       if inputs["fuel"] == "Methanol" else []),
        "model": {"name": m["selected_model"], "balanced_accuracy": m["candidates"][m["selected_model"]]["balanced_accuracy"],
                  "roc_auc": m["candidates"][m["selected_model"]]["roc_auc"], "brier_score": m["candidates"][m["selected_model"]]["brier_score"],
                  "rows": m["rows"], "meaning": SPEC["target_meaning"]},
        "scope": "Liquid droplet (FLEX) flames only. Not a prediction for solid materials, ignition, or Moon/Mars gravity.",
    }


def predict_burn_time(fuel, oxygen_pct, pressure_kpa, co2_fraction=0.0, helium_fraction=0.0, droplet_diameter_mm=None):
    """Estimate how long a FLEX-like droplet flame burns, with a 90% range."""
    inputs = _validate_flex(dict(fuel=fuel, oxygen_pct=oxygen_pct, pressure_kpa=pressure_kpa, co2_fraction=co2_fraction,
                                 helium_fraction=helium_fraction, droplet_diameter_mm=droplet_diameter_mm))
    neighbours = _flex_neighbours(inputs)
    art, m = burn_time_model(), metrics()["burn_time"]
    if not art["enabled"]:
        return _unavailable(m["promotion_gate"], inputs, neighbours)
    if inputs["_outside"]:
        return _unavailable("Inputs are outside the tested range, so no model number is shown.", inputs, neighbours,
                            {"out_of_range": inputs["_outside"]})
    X = _frame(inputs)
    pred = float(art["model"].predict(X)[0])
    q = art["conformal_q_log"]
    seconds = float(np.expm1(pred))
    return {
        "available": True,
        "inputs": _public(inputs),
        "burn_time_s": val(seconds, "s", trust="model_estimate", low=max(0.0, float(np.expm1(pred - q))), high=float(np.expm1(pred + q)),
                           source={"record": "PSI-69", "url": SPEC["source_url"], "model": m["selected_model"]},
                           note=f"{int(art['conformal_level'] * 100)}% range from held-out errors (measured coverage {m['candidates'][m['selected_model']]['interval_coverage']:.0%})"),
        "factors": _factors(inputs, lambda X_: float(np.expm1(art["model"].predict(X_)[0])), "seconds"),
        "nearest_tests": neighbours,
        "warnings": inputs["_warnings"],
        "model": {"name": m["selected_model"], "r2": m["candidates"][m["selected_model"]]["r2"],
                  "mae_s": m["candidates"][m["selected_model"]]["mae_s"], "rows": m["rows"]},
        "scope": "Liquid droplet (FLEX) flames only. Burn time ends at extinction or full burn-out.",
    }


def _factors(inputs, f, unit):
    """How much each input moves the estimate compared with a typical NASA test of the same fuel."""
    df = flex_train()
    typical = df[df["fuel"] == inputs["fuel"]][FLEX_NUMERIC].median()
    base = f(_frame(inputs))
    out = []
    for feat in FLEX_NUMERIC:
        alt = dict(inputs)
        alt[feat] = float(typical[feat])
        delta = base - f(_frame(alt))
        if unit == "probability points":
            delta *= 100
        out.append({"feature": feat, "label": FLEX_LABELS[feat][0], "your_value": _round(inputs[feat], 4),
                    "typical_value": _round(float(typical[feat]), 4), "effect": _round(delta, 3), "effect_unit": unit})
    out.sort(key=lambda r: -abs(r["effect"]))
    return {"method": "Change in the estimate when this one input is set back to the typical tested value (median) for this fuel.",
            "items": out}


def what_if(model, vary, fuel, oxygen_pct, pressure_kpa, co2_fraction=0.0, helium_fraction=0.0, droplet_diameter_mm=None, points=30):
    """Sweep one input across its tested range and return a curve plus the real tests along that axis."""
    if model not in ("extinction", "burn_time"):
        raise InputError({"field": "model", "message": "model must be 'extinction' or 'burn_time'"})
    if vary not in FLEX_NUMERIC:
        raise InputError({"field": "vary", "message": f"vary must be one of {FLEX_NUMERIC}"})
    points = max(5, min(100, int(points)))
    base = _validate_flex(dict(fuel=fuel, oxygen_pct=oxygen_pct, pressure_kpa=pressure_kpa, co2_fraction=co2_fraction,
                               helium_fraction=helium_fraction, droplet_diameter_mm=droplet_diameter_mm), allow_out_of_range=True)
    dom = SPEC["domains_by_fuel"][base["fuel"]]["fields"][vary]
    lo, hi = dom["min"], dom["max"]
    pad = (hi - lo) * 0.15
    xs = np.linspace(max(0.0, lo - pad), hi + pad, points)
    art = extinction_model() if model == "extinction" else burn_time_model()
    curve = []
    for x in xs:
        p = dict(base)
        p[vary] = float(x)
        n2 = 1 - p["oxygen_pct"] / 100 - p["co2_fraction"] - p["helium_fraction"]
        dom_all = SPEC["domains_by_fuel"][base["fuel"]]["fields"]
        in_range = all(dom_all[f]["min"] - 1e-9 <= p[f] <= dom_all[f]["max"] + 1e-9 for f in FLEX_NUMERIC) and n2 >= -1e-9
        point = {"x": _round(float(x), 4), "in_tested_range": bool(in_range), "y": None, "low": None, "high": None}
        if in_range and art["enabled"]:
            X = _frame(p)
            if model == "extinction":
                ens = [e.predict_proba(X)[0, 1] for e in art["ensemble"]]
                point.update(y=_round(float(art["model"].predict_proba(X)[0, 1])), low=_round(float(np.percentile(ens, 10))),
                             high=_round(float(np.percentile(ens, 90))))
            else:
                y = float(art["model"].predict(X)[0])
                q = art["conformal_q_log"]
                point.update(y=_round(float(np.expm1(y))), low=_round(max(0.0, float(np.expm1(y - q)))), high=_round(float(np.expm1(y + q))))
        curve.append(point)
    df = flex_all()
    df = df[(df["fuel"] == base["fuel"]) & df[vary].notna() & df["test_end_raw"].isin(["Extinction", "Completion"])]
    real = [{"x": _round(float(r[vary]), 4), "y": (1 if r["test_end_raw"] == "Extinction" else 0) if model == "extinction" else _round(r["burn_time_s"]),
             "outcome": r["test_end_raw"], "experiment_id": r["experiment_id"]}
            for r in df.to_dict("records") if model == "extinction" or not pd.isna(r["burn_time_s"])]
    return {
        "model": model, "vary": vary, "label": FLEX_LABELS[vary][0], "unit": FLEX_LABELS[vary][1],
        "y_label": "Chance of extinction" if model == "extinction" else "Burn time (s)",
        "y_unit": "probability" if model == "extinction" else "s",
        "tested_range": [_round(lo, 4), _round(hi, 4)],
        "held_constant": {k: v for k, v in _public(base).items() if k != vary},
        "curve": curve, "real_tests": real,
        "note": "Only the chosen input changes; real tests along the axis differ in other inputs too. Points outside the tested range have no value.",
        "trust": "model_estimate",
    }


# --------------------------------------------------------------------------- advisor

def ground_comparison(material):
    fam = GROUND_FAMILY.get(material, material)
    rows = [g for g in ground() if g["material"].lower() == str(fam).lower()]
    s = [r for r in solids() if r["material"] == material]
    oxy = [r["oxygen_pct"] for r in s if r["oxygen_pct"] is not None]
    flamed = [r["oxygen_pct"] for r in s if r["burned_binary"] == "1" and r["oxygen_pct"] is not None]
    return {
        "material": material, "earth_family": fam,
        "earth_tests": [{"configuration": g["configuration"], "table": g["table_number"], "page": g["pdf_page"],
                         "thickness_mm": g["thickness_mm"],
                         "uloi_oxygen_pct": val(g["uloi_oxygen_pct"], "%", trust="earth_reference", source=_source(g["source_record"], g["source_url"], locator=f"Table {g['table_number']}, PDF p.{g['pdf_page']}")),
                         "moc_oxygen_pct": val(g["moc_oxygen_pct"], "%", trust="earth_reference", source=_source(g["source_record"], g["source_url"], locator=f"Table {g['table_number']}, PDF p.{g['pdf_page']}")),
                         "pressure_note": g["pressure_note"] or None} for g in rows],
        "microgravity": {
            "tests": len(s), "oxygen_tested_pct": [min(oxy), max(oxy)] if oxy else None,
            "lowest_oxygen_with_flame_pct": val(min(flamed) if flamed else None, "%", trust="ai_label",
                                                note="Any visible flame, including brief ignition"),
        },
        "note": "ULOI/MOC are Earth-gravity thresholds from different test methods and sample shapes. They are shown beside the orbital tests, not used to predict them.",
    }


def advisor(oxygen_pct, airflow_cm_s=None, mode="discover", material=None, mission="space_station", pressure_kpa=None,
            geometry=None, max_thickness_mm=None, constraints=None, priority="evidence_strength", per_material=3):
    """Material Advisor. Ranks PSI-tested materials by how much NASA evidence exists near the user's conditions.

    It never assigns a safety score. Constraints the data cannot check are returned as `cannot_check`.
    """
    if mode not in ("analyze", "discover"):
        raise InputError({"field": "mode", "message": "mode must be 'analyze' or 'discover'"})
    if mode == "analyze" and not material:
        raise InputError({"field": "material", "message": "Choose a material to analyze, or switch to discover mode"})
    if mission not in MISSIONS:
        raise InputError({"field": "mission", "message": f"mission must be one of {list(MISSIONS)}"})
    _check_range("oxygen_pct", oxygen_pct, 0, 100)
    known = {r["material"] for r in solids() if r["material"] != "Unresolved material"}
    if material and material not in known:
        match = next((m for m in known if m.lower() == material.lower()), None)
        if not match:
            return {"supported": False, "material": material,
                    "message": f"NASA PSI has no orbital burn tests for '{material}' in this data set.",
                    "tested_materials": sorted(known),
                    "earth_reference": [g for g in {r["material"] for r in ground()} if g.lower() in material.lower()]}
        material = match

    warnings = []
    oxy_all = [r["oxygen_pct"] for r in solids() if r["oxygen_pct"] is not None]
    if oxygen_pct > max(oxy_all) + 0.5:
        warnings.append({"code": "oxygen_above_tested", "message": f"{oxygen_pct:g}% oxygen is above every solid-fuel test in orbit (max {max(oxy_all):.1f}%). Every match below is an extrapolation gap, not a like-for-like test."})
    if oxygen_pct < min(oxy_all) - 0.5:
        warnings.append({"code": "oxygen_below_tested", "message": f"{oxygen_pct:g}% oxygen is below every solid-fuel test (min {min(oxy_all):.1f}%)."})
    if MISSIONS[mission]["gravity_g"] > 0:
        warnings.append({"code": "partial_gravity", "message": f"No NASA PSI data exists at {MISSIONS[mission]['label']}. Real behaviour lies somewhere between these microgravity tests and Earth-gravity tests; this tool cannot narrow it further."})

    checks_common = [
        {"constraint": "pressure", "status": "cannot_check",
         "reason": "Solid-fuel tests did not vary pressure (BASS ≈ 98 kPa, BASS-II not recorded)." + (f" Your {pressure_kpa:g} kPa cannot be compared." if pressure_kpa else "")},
    ]
    for c in (constraints or []):
        checks_common.append({"constraint": str(c), "status": "cannot_check", "reason": "No mass, strength, cost or similar property data is in the NASA combustion tables."})

    stage = stage_training()
    candidates = []
    for mat in sorted(known):
        sim = find_similar_solid(oxygen_pct, airflow_cm_s, material=mat, geometry=geometry, k=50)
        close = [m for m in sim["matches"] if m["distance"] <= 1.0]
        near = [m for m in sim["matches"] if m["distance"] <= 2.5]
        outcomes = Counter(m["outcome"]["label"] for m in near)
        st = [s for s in stage if s["material"] == mat and s["oxygen_initial_pct"] is not None and s["airflow_cm_s"] is not None
              and math.hypot((s["oxygen_initial_pct"] - oxygen_pct) / 1.5, 0 if airflow_cm_s is None else (s["airflow_cm_s"] - airflow_cm_s) / 4.0) <= 2.5]
        sustained = sum(s["sustained_flame_binary"] == "1" for s in st)
        thick = [r["thickness_mm"] for r in solids() if r["material"] == mat and r["thickness_mm"] is not None]
        checks = list(checks_common)
        if max_thickness_mm is not None:
            if not thick:
                checks.append({"constraint": "max_thickness_mm", "status": "cannot_check", "reason": "No sheet thickness recorded for this material's tests."})
            else:
                ok = [t for t in thick if t <= max_thickness_mm]
                checks.append({"constraint": "max_thickness_mm", "status": "met" if ok else "failed",
                               "reason": f"Tested thicknesses: {sorted(set(thick))} mm" + ("" if ok else f"; none at or below {max_thickness_mm:g} mm")})
        evidence_score = sum(m["similarity"] for m in near)
        candidates.append({
            "material": mat,
            "is_selected": mat == material,
            "evidence": {
                "score": _round(evidence_score, 3),
                "close_tests": len(close), "nearby_tests": len(near), "total_tests": sum(r["material"] == mat for r in solids()),
                "coverage": sim["coverage"],
            },
            "observed_outcomes_nearby": {"counts": dict(outcomes), "trust": "ai_label",
                                         "note": "Outcomes of the whole test, which often changed airflow during the burn."},
            "condition_linked_events_nearby": {
                "events": len(st), "sustained_flame": sustained, "not_sustained": len(st) - sustained, "trust": "ai_label",
                "note": "Events where the notes link a flame result to a specific airflow (from solid_stage_training.csv).",
            },
            "earth_reference": ground_comparison(mat) if mat in GROUND_FAMILY else None,
            "constraint_checks": checks,
            "top_tests": sim["matches"][:per_material],  # closest tests even when far; check each distance
            "concerns": _concerns(mat, near, st, thick),
        })

    if priority == "fewest_sustained_flames":
        key = lambda c: (-(c["condition_linked_events_nearby"]["events"] > 0),
                         c["condition_linked_events_nearby"]["sustained_flame"] / max(1, c["condition_linked_events_nearby"]["events"]),
                         -c["evidence"]["score"])
        rank_basis = "Share of condition-linked events with a sustained flame near your conditions (lowest first); materials with no such events go last."
    else:
        key = lambda c: -c["evidence"]["score"]
        rank_basis = "Amount and closeness of NASA tests near your conditions (most evidence first)."
    candidates.sort(key=key)
    if mode == "analyze":
        sel = next(c for c in candidates if c["is_selected"])
        others = [c for c in candidates if not c["is_selected"]]
        candidates = [sel] + others
    for i, c in enumerate(candidates, 1):
        c["rank"] = i

    return {
        "mode": mode, "inputs": {"oxygen_pct": oxygen_pct, "airflow_cm_s": airflow_cm_s, "material": material, "mission": mission,
                                 "pressure_kpa": pressure_kpa, "geometry": geometry, "max_thickness_mm": max_thickness_mm, "priority": priority},
        "rank_basis": rank_basis,
        "not_a_safety_rating": "This ranks NASA evidence, not material safety. Materials were tested in different shapes, sizes and airflow sequences, so no material is shown as definitively safer.",
        "warnings": warnings,
        "candidates": candidates,
    }


def _concerns(mat, near, stages, thick):
    out = []
    if not near:
        out.append("No NASA test of this material near these conditions.")
    if near and not stages:
        out.append("Nearby tests do not link a flame result to a specific airflow.")
    if stages and len({s["sustained_flame_binary"] for s in stages}) == 1:
        out.append("All nearby condition-linked events have the same result, so the boundary between burning and not burning is not captured here.")
    if not thick:
        out.append("Sample thickness not recorded, so size effects cannot be checked.")
    if len(near) < 3:
        out.append("Very few nearby tests; treat as anecdotal.")
    return out


# --------------------------------------------------------------------------- search

def search_evidence(q, source_record=None, k=5, include_plans=True):
    if not q or not q.strip():
        raise InputError({"field": "q", "message": "Enter a search query"})
    k = max(1, min(25, int(k)))
    vec, components, tfidf, lsa = search_index()
    qv = vec.transform([q])
    lexical = (tfidf @ qv.T).toarray().ravel()
    qn = np.asarray(qv @ components)
    norm = np.linalg.norm(qn)
    semantic = (lsa @ (qn / norm).ravel()) if norm > 0 else np.zeros(len(lexical))
    score = 0.6 * lexical + 0.4 * np.clip(semantic, 0, None)
    chunks = evidence()
    order = np.argsort(-score)
    out = []
    for i in order:
        c = chunks[i]
        if score[i] <= 0 or len(out) >= k:
            break
        if source_record and c["source_record"] != source_record:
            continue
        if not include_plans and c["kind"] == "experiment_plan_text":
            continue
        out.append({
            "chunk_id": c["chunk_id"], "score": _round(float(score[i]), 4), "source_record": c["source_record"],
            "investigation": catalog().get(c["source_record"], {}).get("investigation_name"),
            "kind": c["kind"], "source_file": c["source_file"], "locator": c["locator"], "url": c["source_url"],
            "text": c["text"], "snippet": _snippet(c["text"], q),
            "caution": "Describes a planned test, not an observed result" if c["kind"] == "experiment_plan_text" else None,
        })
    return {"query": q, "results": out,
            "method": "Keyword (TF-IDF) plus concept (latent semantic analysis) match over NASA metadata, reports and readmes."}


def _snippet(text, q, width=260):
    t = " ".join(text.split())
    words = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 2]
    pos = min([p for p in (t.lower().find(w) for w in words) if p >= 0], default=0)
    start = max(0, pos - width // 3)
    return ("…" if start else "") + t[start:start + width] + ("…" if start + width < len(t) else "")


# --------------------------------------------------------------------------- charts and model page

def coverage_points(dataset="solid", fuel=None):
    """Every real test as a point, for scatter charts of where NASA has data."""
    if dataset == "solid":
        return {"x": "oxygen_pct", "y": "airflow_cm_s", "points": [
            {"experiment_id": r["experiment_id"], "material": r["material"], "x": r["oxygen_pct"],
             "y_low": r["airflow_min"], "y_high": r["airflow_max"], "outcome": r["outcome"], "any_flame": r["burned_binary"] == "1"}
            for r in solids() if r["oxygen_pct"] is not None]}
    df = flex_all()
    if fuel:
        df = df[df["fuel"].str.lower() == fuel.lower()]
    return {"x": "oxygen_pct", "y": "pressure_kpa", "points": [
        {"experiment_id": r["experiment_id"], "fuel": r["fuel"], "x": _round(r["oxygen_pct"]), "y": _round(r["pressure_kpa"]),
         "outcome": r["test_end_raw"], "used_for_training": str(r["training_eligible"]).lower() == "true"}
        for r in df.to_dict("records")]}


@lru_cache(maxsize=1)
def evaluation():
    path = ARTIFACTS / "evaluation.json"
    return json.loads(path.read_text()) if path.exists() else None


def model_info():
    m = metrics()
    return {**m, "out_of_fold": oof(), "stress_tests": evaluation(),
            "how_to_read": {
                "balanced_accuracy": "Average of the hit rate on each outcome. 0.5 = guessing; 1.0 = perfect.",
                "r2": "Share of burn-time variation explained. 0 = no better than the average; 1 = perfect.",
                "out_of_fold": "Each test was predicted by a model that never saw it (or any repeat of its sample).",
            }}
