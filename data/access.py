"""Dependency-free readers shared by the later dashboard, agent and model code.

No predictions or safety rankings are supplied by the data package. Candidate
training rows have AI-reviewed labels; see annotations/README.md for limitations.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

CLEAN = Path(__file__).resolve().parent / "clean"
NUMERIC = {
    "thickness_mm", "diameter_mm", "width_mm", "oxygen_pct", "oxygen_final_pct",
    "airflow_cm_s", "pressure_kpa", "co2_initial_pct", "co2_final_pct", "burned_binary",
}


def _csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_catalog() -> list[dict]:
    return _csv(CLEAN / "investigation_catalog.csv")


def query_experiments(**filters) -> list[dict]:
    """Return solid observations, with typed numeric nulls and exact filters.

    Example: query_experiments(material='PMMA', source_record='PSI-25').
    Airflow sequences remain in airflow_raw; missing numbers become None.
    """
    rows = _csv(CLEAN / "solid_combustion_model.csv")
    unknown = set(filters) - set(rows[0])
    if unknown:
        raise ValueError(f"Unknown experiment filters: {sorted(unknown)}")
    for row in rows:
        for key in NUMERIC:
            row[key] = float(row[key]) if row[key] else None
        row["training_eligible"] = row["training_eligible"] == "true"
        row["quality_flags"] = row["quality_flags"].split("|") if row["quality_flags"] else []
    return [row for row in rows if all(row[key] == value for key, value in filters.items())]


def load_source_tables(source_record: str) -> list[dict]:
    """Return every selected source table and its original NASA columns.

    Includes NASA note/calibration rows where present. Consumers must not assume
    every source-table row is an experiment or that all records share a schema.
    """
    index = json.loads((CLEAN / "table_index.json").read_text())
    matches = [entry for entry in index if entry["source_record"] == source_record]
    if not matches:
        raise ValueError(f"No experimental tables for {source_record}")
    return [{**entry, "rows": _csv(CLEAN / entry["file"])} for entry in matches]


def load_evidence(source_record: str | None = None) -> list[dict]:
    with (CLEAN / "evidence_chunks.jsonl").open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return [row for row in rows if source_record is None or row["source_record"] == source_record]


def load_quality_report() -> dict:
    return json.loads((CLEAN / "quality_report.json").read_text())


def load_training_candidates(dataset: str = "solids") -> list[dict]:
    """Return the curated candidates; use the documented feature whitelist.

    Values remain CSV strings. These rows are observations with AI annotation,
    not validated model outputs. Do not concatenate the two physical datasets.
    """
    files = {"solids": "solid_stage_training.csv", "flex": "flex_training.csv"}
    if dataset not in files:
        raise ValueError("dataset must be 'solids' or 'flex'")
    return _csv(CLEAN / files[dataset])
