"""Loads the curated NASA PSI tables in data/clean/ as pandas DataFrames.

The CSVs are the database: they are read once and cached. Numeric blanks stay
NaN (missing), never zero. Nothing here edits or invents values.
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from . import CLEAN

PSI_URL = "https://psi.nasa.gov/physci/repo/data/investigations/{}"

# Solid materials burned in BASS/BASS-II with a resolved identity.
UNRESOLVED = "Unresolved material"

# Test-level outcome categories (from data/scripts/label_data.py), grouped for display.
OUTCOME_GROUPS = {
    "burn_observed": "sustained burn",
    "fuel_exhaustion": "sustained burn",
    "burn_then_extinguished": "burned, then went out",
    "partial_extinction": "burned, then went out",
    "transient_or_not_sustained": "brief flame, not sustained",
    "no_ignition_observed": "no ignition",
    "suppression_extinction": "suppressed (agent/N2)",
    "hardware_failure": "not usable",
    "insufficient_evidence": "not usable",
}

# Earth-gravity ground-test families that correspond to a PSI material name.
GROUND_FAMILY = {"PMMA": "PMMA", "Ultem (PEI)": "PEI"}


def _read(name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(CLEAN / name, keep_default_na=True, **kw)


@lru_cache(maxsize=None)
def solids() -> pd.DataFrame:
    """250 BASS/BASS-II tests, one row per test, with project-team-verified outcome labels."""
    df = _read("solid_combustion_model.csv", dtype={"test_id": str, "sample_id": str})
    df["outcome_group"] = df["outcome"].map(OUTCOME_GROUPS).fillna("not usable")
    df["material_raw"] = df["material_raw"].fillna("")
    df["notes"] = df["notes"].fillna("")
    return df


@lru_cache(maxsize=None)
def airflow_readings() -> pd.DataFrame:
    """Every airflow value recorded for a test (tests often changed flow mid-burn)."""
    return _read("airflow_readings.csv")


@lru_cache(maxsize=None)
def test_airflow_values() -> dict[str, list[float]]:
    """experiment_id -> all exact airflow readings (cm/s) recorded during that test."""
    r = airflow_readings()
    r = r[r["reading_status"] == "exact_display"].dropna(subset=["airflow_display_cm_s"])
    out: dict[str, list[float]] = {}
    for eid, v in zip(r["experiment_id"], r["airflow_display_cm_s"]):
        out.setdefault(eid, []).append(float(v))
    return out


@lru_cache(maxsize=None)
def stages() -> pd.DataFrame:
    """395 condition stages split from the tests (one flow setting each)."""
    return _read("solid_stage_observations.csv", dtype={"test_id": str})


@lru_cache(maxsize=None)
def solid_training() -> pd.DataFrame:
    """47 stages with exact conditions and a sustained-flame label: the solid model's training set."""
    return _read("solid_stage_training.csv", dtype={"test_id": str})


@lru_cache(maxsize=None)
def flex_training() -> pd.DataFrame:
    """202 screened FLEX droplet tests: recorded Extinction (1) vs Completion (0)."""
    return _read("flex_training.csv")


@lru_cache(maxsize=None)
def flex_all() -> pd.DataFrame:
    return _read("flex_labeled.csv")


@lru_cache(maxsize=None)
def catalog() -> pd.DataFrame:
    return _read("investigation_catalog.csv", dtype=str).fillna("")


@lru_cache(maxsize=None)
def ground() -> pd.DataFrame:
    """70 Earth-gravity ULOI/MOC oxygen thresholds (NTRS 20110008636). Comparison only."""
    return _read("ground_thresholds.csv")


@lru_cache(maxsize=None)
def publications() -> pd.DataFrame:
    return _read("publications.csv", dtype=str).fillna("")


@lru_cache(maxsize=None)
def table_index() -> list[dict]:
    return json.loads((CLEAN / "table_index.json").read_text())


def source_table(file: str) -> pd.DataFrame:
    """An original NASA table exactly as published (all cells kept as text)."""
    return pd.read_csv(CLEAN / file, dtype=str, keep_default_na=False)


@lru_cache(maxsize=None)
def evidence_chunks() -> list[dict]:
    with (CLEAN / "evidence_chunks.jsonl").open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=None)
def quality_report() -> dict:
    return json.loads((CLEAN / "quality_report.json").read_text())


@lru_cache(maxsize=None)
def labeling_report() -> dict:
    return json.loads((CLEAN / "labeling_report.json").read_text())


# Saffire large-scale microgravity burns (PSI-98/99/100). Transcribed row by row
# from data/clean/source_tables; values are quoted as NASA wrote them. Rows with a
# blank Material cell are kept with material=None and are never attributed.
SAFFIRE = [
    {"source_record": "PSI-98", "sample": "S1", "material": "SIBAL (cotton/fiberglass)", "material_raw": "SIBAL Fabric",
     "thickness": "0.37 cm", "airflow_cm_s": 20, "oxygen": "21.5 - 21.7", "flow_direction": "concurrent",
     "burn_time": "420 s", "burn_length": "", "spread_rate": "", "result": "burned (420 s)"},
    {"source_record": "PSI-98", "sample": "S2", "material": "SIBAL (cotton/fiberglass)", "material_raw": "SIBAL Fabric",
     "thickness": "0.37 cm", "airflow_cm_s": 20, "oxygen": "~ 21.5", "flow_direction": "opposed",
     "burn_time": "70 s", "burn_length": "", "spread_rate": "", "result": "burned (70 s)"},
    {"source_record": "PSI-99", "sample": "2-1", "material": "Silicone", "material_raw": "Silicone",
     "thickness": "0.27 mm", "airflow_cm_s": 20, "oxygen": "~ 21.5", "flow_direction": "concurrent",
     "burn_time": "Insignificant", "burn_length": "~ 0", "spread_rate": "n/a", "result": "no significant burn"},
    {"source_record": "PSI-99", "sample": "2-2", "material": "Silicone", "material_raw": "Silicone",
     "thickness": "0.61 mm", "airflow_cm_s": 20, "oxygen": "~ 22.1", "flow_direction": "concurrent",
     "burn_time": "Insignificant", "burn_length": "~ 0", "spread_rate": "n/a", "result": "no significant burn"},
    {"source_record": "PSI-99", "sample": "2-3", "material": "Silicone", "material_raw": "Silicone",
     "thickness": "1.03 mm", "airflow_cm_s": 20, "oxygen": "~ 22.1", "flow_direction": "concurrent",
     "burn_time": "Insignificant", "burn_length": "~ 0", "spread_rate": "n/a", "result": "no significant burn"},
    {"source_record": "PSI-99", "sample": "2-4", "material": "Silicone", "material_raw": "Silicone",
     "thickness": "037 mm (as published)", "airflow_cm_s": 20, "oxygen": "~ 22.1", "flow_direction": "opposed",
     "burn_time": "Insignificant", "burn_length": "~ 0", "spread_rate": "n/a", "result": "no significant burn"},
    {"source_record": "PSI-99", "sample": "2-5", "material": "SIBAL (cotton/fiberglass)", "material_raw": "Cotton-Fiberglass (SIBAL)",
     "thickness": "037 mm (as published)", "airflow_cm_s": 20, "oxygen": "~ 22.1", "flow_direction": "concurrent",
     "burn_time": "145 s", "burn_length": "29 cm", "spread_rate": "2.1 mm/s", "result": "burned full length"},
    {"source_record": "PSI-99", "sample": "2-6", "material": None, "material_raw": "(blank in NASA table)",
     "thickness": "037 mm (as published)", "airflow_cm_s": 20, "oxygen": "~ 22.1", "flow_direction": "concurrent",
     "burn_time": "115 s", "burn_length": "29 cm", "spread_rate": "2.6 mm/s", "result": "burned full length"},
    {"source_record": "PSI-99", "sample": "2-7", "material": "PMMA", "material_raw": "PMMA & Nomex",
     "thickness": "0.85 and 0.37 mm", "airflow_cm_s": 20, "oxygen": "~ 22.1", "flow_direction": "concurrent",
     "burn_time": "140 s", "burn_length": "5 cm & 0", "spread_rate": "n/a (Nomex)",
     "result": "PMMA fully consumed; Nomex not ignited (NASA note 2)"},
    {"source_record": "PSI-99", "sample": "2-7", "material": "Nomex", "material_raw": "PMMA & Nomex",
     "thickness": "0.85 and 0.37 mm (shared cell)", "airflow_cm_s": 20, "oxygen": "~ 22.1", "flow_direction": "concurrent",
     "burn_time": "", "burn_length": "0", "spread_rate": "n/a",
     "result": "not ignited next to burning PMMA (NASA note 2)"},
    {"source_record": "PSI-99", "sample": "2-8", "material": "PMMA", "material_raw": "PMMA",
     "thickness": "See Fig. 5", "airflow_cm_s": 20, "oxygen": "22.1 to 22.0", "flow_direction": "concurrent",
     "burn_time": "600 s", "burn_length": "~ 10 cm", "spread_rate": "anchored flame, regression 0.01-0.04 mm/s",
     "result": "burned 600 s, flame anchored at base"},
    {"source_record": "PSI-100", "sample": "S1", "material": "SIBAL (cotton/fiberglass)", "material_raw": "SIBAL Fabric",
     "thickness": ".33 cm", "airflow_cm_s": 30, "oxygen": "", "flow_direction": "concurrent",
     "burn_time": "", "burn_length": "", "spread_rate": "", "result": "outcome not in table"},
    {"source_record": "PSI-100", "sample": "S2", "material": "SIBAL (cotton/fiberglass)", "material_raw": "SIBAL Fabric",
     "thickness": ".33 cm", "airflow_cm_s": 30, "oxygen": "", "flow_direction": "opposed",
     "burn_time": "", "burn_length": "", "spread_rate": "", "result": "outcome not in table"},
]
for _row in SAFFIRE:
    _row["source_url"] = PSI_URL.format(_row["source_record"])


def saffire(material: str | None = None) -> list[dict]:
    rows = [r for r in SAFFIRE if r["material"] is not None or material is None]
    return [r for r in rows if material is None or r["material"] == material]


def materials() -> list[str]:
    """Resolved solid materials tested in orbit (BASS, BASS-II, Saffire)."""
    names = set(solids()["material"]) - {UNRESOLVED}
    names |= {r["material"] for r in SAFFIRE if r["material"]}
    return sorted(names)


def material_profile(material: str) -> dict:
    """Counts and condition ranges for one material, computed from the tables."""
    s = solids()
    rows = s[s["material"] == material]
    oxy = rows["oxygen_pct"].dropna()
    air = [v for eid in rows["experiment_id"] for v in test_airflow_values().get(eid, [])]
    pres = rows["pressure_kpa"].dropna()
    dims = {}
    for col in ("thickness_mm", "diameter_mm", "width_mm"):
        v = rows[col].dropna()
        if len(v):
            dims[col] = [float(v.min()), float(v.max())]
    return {
        "material": material,
        "tests": int(len(rows)),
        "investigations": sorted(rows["source_record"].unique().tolist()),
        "outcomes": rows["outcome_group"].value_counts().to_dict(),
        "oxygen_pct_range": [float(oxy.min()), float(oxy.max())] if len(oxy) else None,
        "airflow_cm_s_range": [min(air), max(air)] if air else None,
        "pressure_kpa_range": [float(pres.min()), float(pres.max())] if len(pres) else None,
        "geometries": sorted(rows["sample_geometry"].dropna().unique().tolist()),
        "variants": sorted(rows["material_raw"].unique().tolist())[:12],
        "dimensions_mm": dims,
        "saffire_samples": len(saffire(material)),
        "ground_family": GROUND_FAMILY.get(material),
    }
