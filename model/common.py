"""Shared paths, feature lists and data loading for the FLEX models.

Only scikit-learn built-ins are used inside saved pipelines, so the joblib
files load in any process without custom functions (the old burn_model.joblib
needed `airflow_ushape` in __main__ and could not be loaded elsewhere).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
SPEC = json.loads((Path(__file__).resolve().parent / "model_spec.json").read_text())

CATEGORICAL = ["fuel"]
NUMERIC = ["pressure_kpa", "oxygen_pct", "co2_fraction", "helium_fraction", "droplet_diameter_mm"]
FEATURES = CATEGORICAL + NUMERIC
assert FEATURES == SPEC["features"], "feature list drifted from model_spec.json"

GROUP = SPEC["group_column"]
SEED = SPEC["validation_plan"]["seed"]


def load_flex_training() -> pd.DataFrame:
    df = pd.read_csv(CLEAN / "flex_training.csv")
    for col in NUMERIC + ["burn_time_s", "extinction_binary"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[FEATURES].isna().any().any():
        raise ValueError("flex_training.csv has missing model features; rerun label_data.py")
    return df


def preprocessor():
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    return ColumnTransformer([
        ("fuel", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", StandardScaler(), NUMERIC),
    ])


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if not np.isfinite(obj) else round(float(obj), 6)
    if isinstance(obj, float):
        return None if not np.isfinite(obj) else round(obj, 6)
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    return obj
