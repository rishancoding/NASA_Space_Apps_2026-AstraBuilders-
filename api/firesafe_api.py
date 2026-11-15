"""HTTP routes for the React UI's FireSafe pages (`/api/fs/...`).

They wrap the same `firesafe` backend as the Streamlit app, with the UI's rules applied here:
- Only microgravity at ~1 atm (all NASA solid tests); no Moon/Mars or pressure inputs.
- A model number is returned only for conditions NASA tested; otherwise it is withheld.
- The advisor lists only materials that have an estimate at your conditions.
"""
from __future__ import annotations

import json
import math
import threading
import uuid
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from firesafe import agent, predictor
from firesafe.advisor import GEOMETRIES, PRIORITIES, Scenario, advise
from firesafe.data import catalog, flex_all, flex_training, solid_training, solids, test_airflow_values

router = APIRouter(prefix="/api/fs", tags=["firesafe"])
SUMMARIES = json.loads((Path(__file__).with_name("investigation_summaries.json")).read_text())
KEPT_CHECKS = {"Oxygen", "Airflow", "Shape", "Max thickness"}   # the others are always "cannot assess" here


def clean(o):
    """Recursively turn numpy/pandas values into JSON-safe Python; NaN becomes None."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [clean(v) for v in o.tolist()]
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if o is pd.NaT:
        return None
    return o


def records(df: pd.DataFrame) -> list[dict]:
    return clean(df.astype(object).where(df.notna(), None).to_dict("records"))


def _span(ranges: dict, key: str) -> list[float]:
    return [min(r[key][0] for r in ranges.values()), max(r[key][1] for r in ranges.values())]


def _mixture(df: pd.DataFrame) -> pd.Series:
    return np.where(df["co2_fraction"] > 0, "co2", np.where(df["helium_fraction"] > 0, "helium", "air"))


def flex_mixtures() -> dict:
    """Tested ranges per fuel and gas mixture (CO2 and helium were never tested together)."""
    d = flex_training().assign(mix=lambda t: _mixture(t))
    out: dict = {}
    for (fuel, mix), g in d.groupby(["fuel", "mix"]):
        out.setdefault(fuel, {})[mix] = {
            k: [float(g[k].min()), float(g[k].max())]
            for k in ("oxygen_pct", "pressure_kpa", "droplet_diameter_mm", "co2_fraction", "helium_fraction")
        } | {"n": int(len(g))}
    return out


def reliability() -> dict:
    """Plain-language model scores on NASA tests each model never saw (from model/metrics.json)."""
    m = predictor.metrics()
    out = {}
    for k in ("solid", "flex"):
        comp = m[k]["comparison"]
        dep = next(c for c in comp if "[deployed]" in c["model"])
        rare = 0  # class 0 is the rarer outcome in both datasets (went out / burned to the end)
        out[k] = {"accuracy": dep["accuracy"], "baseline_accuracy": comp[0]["accuracy"],
                  "rare_recall": dep["recall"][rare], "n": m[k]["n_observations"], "groups": m[k]["n_groups"],
                  "auc": dep["roc_auc"]}
    mat = next(c for c in m["solid"]["comparison"] if c["model"].startswith("Material only"))
    out["solid"]["material_only_accuracy"] = mat["accuracy"]
    return out


# ------------------------------------------------------------------ options

@router.get("/options", summary="Choices and tested ranges for every form")
def options():
    sm = predictor.metrics()["solid"]
    return clean({
        "priorities": PRIORITIES, "geometries": GEOMETRIES, "protocols": predictor.PROTOCOLS,
        "solid": {"materials": predictor.solid_materials(), "ranges": sm["ranges"],
                  "protocols_by_material": sm["protocols_by_material"],
                  "advisor_ranges": {"oxygen_pct": _span(sm["ranges"], "oxygen_pct"),
                                     "airflow_cm_s": _span(sm["ranges"], "airflow_cm_s")}},
        "flex": {"fuels": sorted(predictor.metrics()["flex"]["ranges"]), "mixtures": flex_mixtures()},
        "reliability": reliability(),
        "assistant_online": agent.has_credentials(),
    })


# ------------------------------------------------------------------ advisor

class AdvisorBody(BaseModel):
    mode: Literal["analyze", "discover"] = "discover"
    oxygen_pct: float = Field(21.0, ge=10, le=35)
    airflow_cm_s: float = Field(10.0, ge=0, le=40)
    material: Optional[str] = None
    geometry: str = "any"
    max_thickness_mm: Optional[float] = None
    priority: str = "sustained"
    require_geometry: bool = False


def _has_estimate(c: dict) -> bool:
    p = c.get("prediction") or {}
    return p.get("probability") is not None and p.get("supported", False)


@router.post("/advisor", summary="Material Advisor: only materials with an estimate at these conditions")
def advisor_route(body: AdvisorBody):
    if body.priority not in PRIORITIES:
        raise HTTPException(422, f"Unknown priority {body.priority!r}")
    if body.geometry not in GEOMETRIES:
        raise HTTPException(422, f"Unknown shape {body.geometry!r}")
    if body.mode == "analyze" and body.material not in predictor.solid_materials():
        raise HTTPException(422, "Pick one of the listed materials.")
    res = advise(Scenario(mode=body.mode, oxygen_pct=body.oxygen_pct, airflow_cm_s=body.airflow_cm_s,
                          material=body.material if body.mode == "analyze" else None, geometry=body.geometry,
                          max_thickness_mm=body.max_thickness_mm or None, priority=body.priority,
                          require_geometry=body.require_geometry))
    model_mats = set(predictor.solid_materials())
    not_here = sorted(c["material"] for c in res["candidates"] + res["excluded"]
                      if c["material"] in model_mats and not _has_estimate(c))
    keep = lambda cs: [c for c in cs if _has_estimate(c)]  # noqa: E731
    res["selected"], res["candidates"], res["excluded"] = keep(res["selected"]), keep(res["candidates"]), keep(res["excluded"])
    for i, c in enumerate(res["candidates"], 1):
        c["rank"] = i
    for c in res["selected"] + res["candidates"] + res["excluded"]:
        c["checks"] = [ch for ch in c["checks"] if ch["name"] in KEPT_CHECKS]
        c["ground"] = []
    shown = {c["material"] for c in res["selected"] + res["candidates"]}
    res["comparisons"] = [x for x in res["comparisons"] if x["higher"] in shown and x["lower"] in shown]
    res["unassessable_constraints"] = []
    res["not_tested_here"] = not_here
    sup = [x for x in res["comparisons"] if x["supported"]]
    res["summary"] = ("NASA's tests clearly support " + "; ".join(f"{x['higher']} over {x['lower']}" for x in sup) + "."
                      if sup else "No material is clearly safer than the next one here. Use the list to decide what "
                                  "to test, not as a safety rating.")
    return clean(res)


class ExplainBody(BaseModel):
    result: dict


@router.post("/advisor/explain", summary="AI explanation of advisor results")
def advisor_explain(body: ExplainBody):
    if not agent.has_credentials():
        raise HTTPException(503, "The AI assistant is offline (no API key set).")
    out = agent.ask([{"role": "user", "content":
                      "In 3-4 short sentences, explain my Material Advisor results simply: why the top materials "
                      "ranked where they did and whether any one is clearly safer. Use get_current_advisor_results "
                      "first."}], body.result)
    return {"text": out["text"], "stop_reason": out.get("stop_reason")}


# ------------------------------------------------------------------ predictor

class SolidBody(BaseModel):
    material: str
    protocol: str = "ongoing_burn_trial"
    oxygen_pct: float
    airflow_cm_s: float
    vary: Literal["oxygen", "airflow"] = "oxygen"


@router.post("/predict/solid", summary="Solid sustained-burning estimate inside the tested range only")
def predict_solid(body: SolidBody):
    if body.material not in predictor.solid_materials():
        raise HTTPException(422, f"{body.material} is not in the solid model's training data.")
    sm = predictor.metrics()["solid"]
    if body.protocol not in sm["protocols_by_material"][body.material]:
        raise HTTPException(422, f"{body.material} was not tested in that scenario.")
    rng = sm["ranges"][body.material]
    r = predictor.predict_solid(body.material, body.oxygen_pct, body.airflow_cm_s, body.protocol)
    if r["warnings"]:
        raise HTTPException(422, "Outside what NASA tested: " + " ".join(r["warnings"]))
    d = solid_training()
    d = d[d["material"] == body.material]
    lo, hi = rng["oxygen_pct"] if body.vary == "oxygen" else rng["airflow_cm_s"]
    grid = np.linspace(lo, hi, 40) if hi > lo else np.array([lo])
    if body.vary == "oxygen":
        ys = [predictor.predict_solid(body.material, o, body.airflow_cm_s, body.protocol)["probability"] for o in grid]
        xs = d["oxygen_initial_pct"]
    else:
        ys = [predictor.predict_solid(body.material, body.oxygen_pct, a, body.protocol)["probability"] for a in grid]
        xs = d["airflow_cm_s"]
    runs = [{"x": x, "kept_burning": int(y), "quote": q or ""}
            for x, y, q in zip(xs, d["sustained_flame_binary"], d["evidence_quote"].fillna(""))]
    return clean({**r, "curve": [{"x": float(x), "y": y} for x, y in zip(grid, ys)], "runs": runs, "vary": body.vary})


class FlexBody(BaseModel):
    fuel: str
    oxygen_pct: float
    droplet_diameter_mm: float = Field(gt=0, le=10)
    co2_fraction: float = Field(0.0, ge=0, le=1)
    helium_fraction: float = Field(0.0, ge=0, le=1)
    pressure_kpa: float = Field(gt=0, le=400)


@router.post("/predict/flex", summary="FLEX droplet early-extinction estimate inside the tested range only")
def predict_flex(body: FlexBody):
    if body.co2_fraction > 0 and body.helium_fraction > 0:
        raise HTTPException(422, "NASA never tested CO₂ and helium together.")
    mix = "co2" if body.co2_fraction > 0 else "helium" if body.helium_fraction > 0 else "air"
    rng = flex_mixtures().get(body.fuel, {}).get(mix)
    if rng is None:
        raise HTTPException(422, "NASA did not test this fuel in that gas mixture.")
    vals = body.model_dump()
    outside = [k for k in ("oxygen_pct", "pressure_kpa", "droplet_diameter_mm", "co2_fraction", "helium_fraction")
               if not rng[k][0] - 1e-9 <= vals[k] <= rng[k][1] + 1e-9]
    if outside:
        raise HTTPException(422, "Outside what NASA tested: " + ", ".join(outside))
    r = predictor.predict_flex(body.fuel, body.pressure_kpa, body.oxygen_pct, body.co2_fraction,
                               body.helium_fraction, body.droplet_diameter_mm)
    return clean({**r, "tests_in_mixture": rng["n"]})


# ------------------------------------------------------------------ explorer

@router.get("/catalog", summary="The 19 NASA investigations with plain-language summaries")
def catalog_route():
    rows = records(catalog()[["source_record", "investigation_name", "official_title", "fuel_phase", "role", "url"]])
    return [{**r, "summary": SUMMARIES.get(r["source_record"], "")} for r in rows if r["role"] != "earth_comparison"]


SOLID_COLUMNS = ["experiment_id", "investigation_name", "test_id", "test_date", "material", "material_raw",
                 "sample_geometry", "thickness_mm", "oxygen_pct", "airflow_raw", "outcome_group", "notes", "source_url"]


@router.get("/solids", summary="All 250 solid-material tests (data/clean/solid_combustion_model.csv)")
def solids_route():
    flows = test_airflow_values()
    rows = records(solids()[SOLID_COLUMNS])
    for r in rows:
        r["airflow_readings_cm_s"] = clean(flows.get(r["experiment_id"], []))
        r["investigation"] = r["investigation_name"]
    return rows


FLEX_RESULT = {"Extinction": "Went out early", "Completion": "Burned to the end", "Disruption": "Drop broke apart"}


@router.get("/flex", summary="All 274 FLEX droplet tests (data/clean/flex_labeled.csv)")
def flex_route():
    d = flex_all()
    d = d.assign(result=d["test_end_raw"].map(FLEX_RESULT).fillna(d["test_end_raw"]),
                 co2_pct=d["co2_fraction"] * 100, helium_pct=d["helium_fraction"] * 100)
    return records(d[["experiment_id", "test_id", "test_date", "fuel", "oxygen_pct", "co2_pct", "helium_pct",
                      "pressure_kpa", "droplet_diameter_mm", "burn_time_s", "result", "source_url"]])


# ------------------------------------------------------------------ research assistant

_SESSIONS: dict[str, list] = {}   # session id -> exact API message history (content blocks kept as returned)
_LOCK = threading.Lock()


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = None
    advisor_result: Optional[dict] = None


@router.post("/chat", summary="Research assistant turn (server keeps the history per session)")
def chat(body: ChatBody):
    sid = body.session_id or uuid.uuid4().hex
    if not agent.has_credentials():
        out = agent.offline_answer(body.message)
        return clean({"session_id": sid, "text": out["text"], "offline": True, "stop_reason": "offline",
                      "tool_calls": [{"name": n, "args": a, "result": r} for n, a, r in out["tool_calls"]]})
    with _LOCK:
        history = _SESSIONS.setdefault(sid, [])
    history.append({"role": "user", "content": body.message})
    out = agent.ask(history, body.advisor_result)
    return clean({"session_id": sid, "text": out["text"], "offline": False, "stop_reason": out.get("stop_reason"),
                  "tool_calls": [{"name": n, "args": a, "result": r} for n, a, r in out["tool_calls"]]})


@router.delete("/chat/{session_id}", summary="Forget a conversation")
def clear_chat(session_id: str):
    with _LOCK:
        _SESSIONS.pop(session_id, None)
    return {"cleared": True}
