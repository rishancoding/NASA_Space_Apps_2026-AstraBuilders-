"""Trains, evaluates, saves and serves the two combustion classifiers.

* Solid model: does a flame stay lit at one oxygen/airflow stage? Trained on the
  47 stages in solid_stage_training.csv (`sustained_flame_binary`).
* FLEX model: does a fuel droplet's flame extinguish before the fuel is used up?
  Trained on the 207 tests in flex_training.csv (`extinction_binary`).

Both are cross-validated with groups (repeat burns of one sample stay in the same
fold) and compared against a constant baseline and simpler models, so the app
can show honestly how much the conditions add.
"""
from __future__ import annotations

import json
import warnings
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, brier_score_loss, confusion_matrix,
                             log_loss, precision_recall_fscore_support, roc_auc_score)
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut, cross_val_predict
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from . import MODEL_DIR
from .data import flex_training, solid_training

SOLID_PATH = MODEL_DIR / "solid_model.joblib"
FLEX_PATH = MODEL_DIR / "flex_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"

PROTOCOLS = {
    "ignition_trial": "Fresh ignition (can it light and keep burning?)",
    "ongoing_burn_trial": "Already burning (does it keep burning at this flow?)",
}


def airflow_features(x):
    """log(1+airflow) and its square, so the model can bend at low and high flow."""
    a = np.log1p(np.asarray(x, dtype=float))
    return np.column_stack([a, a ** 2])


def _solid_X(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "oxygen_pct": df["oxygen_initial_pct"].astype(float),
        "airflow_cm_s": df["airflow_cm_s"].astype(float),
        "material": df["material"].astype(str),
        "protocol": df["protocol"].astype(str),
    })


def _solid_pipeline(features: str, kind: str = "lr") -> Pipeline:
    parts = []
    if features in ("full", "conditions"):
        parts += [("oxy", StandardScaler(), ["oxygen_pct"]),
                  ("air", make_pipeline(FunctionTransformer(airflow_features), StandardScaler()), ["airflow_cm_s"])]
    cats = {"full": ["material", "protocol"], "material": ["material"], "conditions": []}[features]
    if cats:
        parts.append(("cat", OneHotEncoder(handle_unknown="ignore"), cats))
    est = (LogisticRegression(C=1.0, max_iter=5000) if kind == "lr"
           else RandomForestClassifier(n_estimators=400, min_samples_leaf=3, random_state=0))
    return Pipeline([("prep", ColumnTransformer(parts)), ("model", est)])


FLEX_NUM = ["pressure_kpa", "oxygen_pct", "co2_fraction", "helium_fraction", "droplet_diameter_mm"]


def _flex_X(df: pd.DataFrame) -> pd.DataFrame:
    return df[["fuel"] + FLEX_NUM].copy()


def _flex_pipeline(kind: str, with_conditions: bool = True) -> Pipeline:
    parts = [("fuel", OneHotEncoder(handle_unknown="ignore"), ["fuel"])]
    if with_conditions:
        parts.append(("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), FLEX_NUM))
    est = (LogisticRegression(max_iter=5000) if kind == "lr"
           else RandomForestClassifier(n_estimators=400, min_samples_leaf=3, random_state=0))
    return Pipeline([("prep", ColumnTransformer(parts)), ("model", est)])


def _scores(y, p) -> dict:
    pred = (p >= 0.5).astype(int)
    prec, rec, f1, sup = precision_recall_fscore_support(y, pred, labels=[0, 1], zero_division=0)
    return {
        "log_loss": round(float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1])), 3),
        "brier": round(float(brier_score_loss(y, p)), 3),
        "roc_auc": round(float(roc_auc_score(y, p)), 3) if len(set(y)) > 1 else None,
        "accuracy": round(float(accuracy_score(y, pred)), 3),
        "balanced_accuracy": round(float(balanced_accuracy_score(y, pred)), 3),
        "precision": [round(float(v), 3) for v in prec],
        "recall": [round(float(v), 3) for v in rec],
        "f1": [round(float(v), 3) for v in f1],
        "support": [int(v) for v in sup],
        "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
    }


def _cv(pipe_fn, X, y, groups, cv) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return cross_val_predict(pipe_fn(), X, y, groups=groups, cv=cv, method="predict_proba")[:, 1]


def _ranges(df: pd.DataFrame, by: str, cols: list[str]) -> dict:
    out = {}
    for key, g in df.groupby(by):
        out[str(key)] = {c: [float(g[c].min()), float(g[c].max())] for c in cols if g[c].notna().any()}
        out[str(key)]["n"] = int(len(g))
    return out


def train_all() -> dict:
    """Fit both models, write model/*.joblib and model/metrics.json, return the metrics."""
    MODEL_DIR.mkdir(exist_ok=True)
    metrics: dict = {}

    # ---- Solids -------------------------------------------------------------
    d = solid_training()
    X, y, g = _solid_X(d), d["sustained_flame_binary"].astype(int).values, d["validation_group"].values
    cv = LeaveOneGroupOut()
    candidates = {
        "Constant baseline (always predicts the training burn rate)": None,
        "Conditions only: oxygen + airflow (logistic)": lambda: _solid_pipeline("conditions"),
        "Material only (logistic)": lambda: _solid_pipeline("material"),
        "Material + scenario + oxygen + airflow (logistic) [deployed]": lambda: _solid_pipeline("full"),
        "Material + scenario + oxygen + airflow (random forest)": lambda: _solid_pipeline("full", "rf"),
    }
    comparison, oof = [], None
    for name, fn in candidates.items():
        p = np.full(len(y), y.mean()) if fn is None else _cv(fn, X, y, g, cv)
        comparison.append({"model": name, **_scores(y, p)})
        if "[deployed]" in name:
            oof = p
    final = _solid_pipeline("full").fit(X, y)
    joblib.dump(final, SOLID_PATH)
    metrics["solid"] = {
        "target": "sustained_flame_binary: 1 = flame stayed lit at this stage, 0 = it went out / did not sustain",
        "model_type": "Logistic regression (scikit-learn), one-hot material and scenario, scaled oxygen and log-airflow terms",
        "n_observations": int(len(y)),
        "class_counts": {"0": int((y == 0).sum()), "1": int((y == 1).sum())},
        "n_groups": int(len(set(g))),
        "validation": "Leave-one-group-out: each fold holds out every stage of one physical sample (validation_group)",
        "training_testing": f"Every stage is scored by a model that never saw its sample ({len(set(g))} folds; "
                            f"each fold trains on the other ~{len(y) - 1} stages)",
        "comparison": comparison,
        "deployed": "Material + scenario + oxygen + airflow (logistic) [deployed]",
        "oof": [{"stage_id": s, "material": m, "actual": int(a), "predicted": round(float(p), 3),
                 "oxygen_pct": float(o), "airflow_cm_s": float(f), "protocol": pr}
                for s, m, a, p, o, f, pr in zip(d["stage_id"], d["material"], y, oof, X["oxygen_pct"],
                                                X["airflow_cm_s"], d["protocol"])],
        "ranges": _ranges(X.assign(protocol=d["protocol"]), "material", ["oxygen_pct", "airflow_cm_s"]),
        "protocols_by_material": {m: sorted(gr["protocol"].unique().tolist()) for m, gr in d.groupby("material")},
        "pressure_kpa_range": [float(d["pressure_kpa"].min()), float(d["pressure_kpa"].max())]
        if d["pressure_kpa"].notna().any() else None,
        "label_provenance": "Project-team-verified labels from crew/report notes",
    }

    # ---- FLEX droplets ------------------------------------------------------
    f = flex_training()
    FX, fy, fg = _flex_X(f), f["extinction_binary"].astype(int).values, f["split_group"].values
    fcv = GroupKFold(n_splits=5)
    fcands = {
        "Constant baseline": None,
        "Fuel only (logistic)": lambda: _flex_pipeline("lr", with_conditions=False),
        "Fuel + conditions (logistic)": lambda: _flex_pipeline("lr"),
        "Fuel + conditions (random forest)": lambda: _flex_pipeline("rf"),
    }
    fcomp, fprobs = [], {}
    for name, fn in fcands.items():
        p = np.full(len(fy), fy.mean()) if fn is None else _cv(fn, FX, fy, fg, fcv)
        fcomp.append({"model": name, **_scores(fy, p)})
        fprobs[name] = p
    # Pre-declared rule: deploy whichever condition-aware model has the lower grouped-CV log loss.
    best = min(["Fuel + conditions (logistic)", "Fuel + conditions (random forest)"],
               key=lambda n: next(c["log_loss"] for c in fcomp if c["model"] == n))
    for c in fcomp:
        if c["model"] == best:
            c["model"] += " [deployed]"
    joblib.dump(_flex_pipeline("rf" if "forest" in best else "lr").fit(FX, fy), FLEX_PATH)
    valid_p = f[f["pressure_kpa"] > 0]
    metrics["flex"] = {
        "target": "extinction_binary: 1 = flame extinguished before the droplet was consumed, 0 = burned to completion",
        "model_type": best.replace(" [deployed]", ""),
        "n_observations": int(len(fy)),
        "class_counts": {"0": int((fy == 0).sum()), "1": int((fy == 1).sum())},
        "n_groups": int(len(set(fg))),
        "validation": "5-fold GroupKFold on split_group (FLEX source identifier)",
        "training_testing": "5 folds: each trains on ~80% of the tests and scores the held-out ~20%",
        "comparison": fcomp,
        "deployed": best + " [deployed]",
        "oof": [{"experiment_id": e, "fuel": fu, "actual": int(a), "predicted": round(float(p), 3)}
                for e, fu, a, p in zip(f["experiment_id"], f["fuel"], fy, fprobs[best])],
        "ranges": _ranges(valid_p, "fuel", FLEX_NUM),
        "note": f"{int((f['pressure_kpa'] <= 0).sum())} test(s) list 0 kPa ambient pressure in the NASA table; "
                "they are kept for training but excluded from the supported-range check.",
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=1))
    load_models.cache_clear()
    return metrics


@lru_cache(maxsize=None)
def load_models():
    if not (SOLID_PATH.exists() and FLEX_PATH.exists() and METRICS_PATH.exists()):
        train_all()
    return joblib.load(SOLID_PATH), joblib.load(FLEX_PATH), json.loads(METRICS_PATH.read_text())


def metrics() -> dict:
    return load_models()[2]


def solid_materials() -> list[str]:
    return sorted(metrics()["solid"]["ranges"])


def predict_solid(material: str, oxygen_pct: float, airflow_cm_s: float,
                  protocol: str = "ongoing_burn_trial", pressure_kpa: float | None = None,
                  gravity: str = "microgravity") -> dict:
    """Sustained-flame probability plus every reason the input is outside the training data."""
    model, _, m = load_models()
    sm = m["solid"]
    warnings_: list[str] = []
    rng = sm["ranges"].get(material)
    if rng is None:
        return {"supported": False, "probability": None, "material": material,
                "warnings": [f"{material} is not in the solid model's training data "
                             f"(trained on: {', '.join(sorted(sm['ranges']))})."], "nearest": []}
    lo, hi = rng["oxygen_pct"]
    if not lo - 0.5 <= oxygen_pct <= hi + 0.5:
        warnings_.append(f"Oxygen {oxygen_pct:g}% is outside the {lo:.1f}-{hi:.1f}% tested for {material}.")
    lo, hi = rng["airflow_cm_s"]
    if not lo <= airflow_cm_s <= hi:
        warnings_.append(f"Airflow {airflow_cm_s:g} cm/s is outside the {lo:g}-{hi:g} cm/s tested for {material}.")
    if protocol not in sm["protocols_by_material"].get(material, []):
        warnings_.append(f"{material} was only tested as: "
                         f"{', '.join(PROTOCOLS[p] for p in sm['protocols_by_material'][material])}.")
    if pressure_kpa is not None and not 95 <= pressure_kpa <= 105:
        warnings_.append(f"Pressure {pressure_kpa:g} kPa: the solid tests ran near 1 atm (about 98-101 kPa where "
                         "recorded; BASS-II recorded none). Pressure is not a model input.")
    if gravity != "microgravity":
        warnings_.append("Only microgravity (ISS) data exists. Lunar/Martian gravity was never tested; "
                         "this estimate does not apply there.")
    X = pd.DataFrame([{"oxygen_pct": oxygen_pct, "airflow_cm_s": airflow_cm_s,
                       "material": material, "protocol": protocol}])
    p = float(model.predict_proba(X)[0, 1])
    d = solid_training()
    near = d[d["material"] == material].assign(
        distance=lambda t: ((t["oxygen_initial_pct"] - oxygen_pct) / 2.0) ** 2
        + ((np.log1p(t["airflow_cm_s"]) - np.log1p(airflow_cm_s)) / 0.5) ** 2
    ).nsmallest(5, "distance")
    nearest = [{"stage_id": r.stage_id, "source_record": r.source_record, "test_id": r.test_id,
                "material_raw": r.material_raw, "oxygen_pct": r.oxygen_initial_pct, "airflow_cm_s": r.airflow_cm_s,
                "scenario": r.protocol, "sustained_flame": int(r.sustained_flame_binary),
                "evidence_quote": r.evidence_quote, "source_url": r.source_url,
                "locator": f"{r.source_file} row {r.source_row}"} for r in near.itertuples()]
    return {"supported": not warnings_, "probability": round(p, 3), "material": material,
            "oxygen_pct": oxygen_pct, "airflow_cm_s": airflow_cm_s, "scenario": protocol,
            "warnings": warnings_, "nearest": nearest, "n_training_stages_for_material": rng["n"]}


def predict_flex(fuel: str, pressure_kpa: float, oxygen_pct: float, co2_fraction: float,
                 helium_fraction: float, droplet_diameter_mm: float) -> dict:
    _, model, m = load_models()
    rng = m["flex"]["ranges"].get(fuel)
    if rng is None:
        return {"probability": None, "warnings": [f"{fuel} is not a FLEX training fuel."]}
    vals = dict(pressure_kpa=pressure_kpa, oxygen_pct=oxygen_pct, co2_fraction=co2_fraction,
                helium_fraction=helium_fraction, droplet_diameter_mm=droplet_diameter_mm)
    w = [f"{k} = {v:g} is outside the {rng[k][0]:g}-{rng[k][1]:g} tested for {fuel}."
         for k, v in vals.items() if k in rng and not rng[k][0] <= v <= rng[k][1]]
    p = float(model.predict_proba(pd.DataFrame([{"fuel": fuel, **vals}]))[0, 1])
    d = flex_training()
    d = d[d["fuel"] == fuel]
    dist = sum(((d[k] - v) / (d[k].std() or 1)) ** 2 for k, v in vals.items() if d[k].notna().any()).fillna(1e9)
    nearest = [{"experiment_id": r.experiment_id, "source_record": r.source_record, "test_id": r.test_id,
                "fuel": r.fuel, **{k: getattr(r, k) for k in FLEX_NUM}, "extinguished": int(r.extinction_binary),
                "source_url": r.source_url, "locator": f"{r.source_file} row {r.source_row}"}
               for r in d.assign(distance=dist).nsmallest(5, "distance").itertuples()]
    return {"probability": round(p, 3), "warnings": w, "supported": not w, "fuel": fuel, **vals,
            "nearest": nearest, "n_training_tests_for_fuel": rng["n"]}
