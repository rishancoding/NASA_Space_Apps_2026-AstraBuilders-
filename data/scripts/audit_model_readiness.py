#!/usr/bin/env python3
"""Step 2: descriptive data audit and one model specification; no model fitting."""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

from label_data import flex_initial_problems

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data/clean"
MODEL = ROOT / "model"
FLEX_FEATURES = ["fuel", "pressure_kpa", "oxygen_pct", "co2_fraction", "helium_fraction", "droplet_diameter_mm"]


def read(name):
    with (CLEAN / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def summarize(rows, target, group, features):
    report = {"rows": len(rows), "classes": dict(Counter(r[target] for r in rows)),
              "groups": len({r[group] for r in rows}), "fields": {}}
    for field in features:
        values = [r[field] for r in rows if r[field] != ""]
        entry = {"missing": len(rows) - len(values)}
        try:
            nums = list(map(float, values))
            entry.update(min=min(nums) if nums else None, max=max(nums) if nums else None)
        except ValueError:
            entry["counts"] = dict(Counter(values))
        report["fields"][field] = entry
    return report


def build_readiness():
    solids, flex = read("solid_stage_training.csv"), read("flex_training.csv")
    for row in flex:
        if flex_initial_problems(row) or row["test_end_raw"] not in {"Extinction", "Completion"}:
            raise ValueError("Rebuild labels before readiness audit: invalid FLEX candidate")
    solid_features = ["material", "protocol", "oxygen_initial_pct", "airflow_cm_s", "sample_geometry",
                      "thickness_mm", "diameter_mm", "width_mm", "pressure_kpa"]
    solid_report = summarize(solids, "sustained_flame_binary", "validation_group", solid_features)
    solid_report["by_protocol"] = {p: summarize([r for r in solids if r["protocol"] == p],
        "sustained_flame_binary", "validation_group", ["material"]) for p in sorted({r["protocol"] for r in solids})}
    solid_report["by_material"] = {m: dict(Counter(r["sustained_flame_binary"] for r in solids if r["material"] == m))
                                   for m in sorted({r["material"] for r in solids})}
    solid_report["decision"] = "retain_as_observed_evidence; do_not_train_the_original_generic_material_burn_predictor"
    solid_report["reasons"] = [
        "Ignition trials and ongoing-burn endpoints are different observation processes.",
        "Only three negative ongoing-burn observations remain; reported observation durations vary.",
        "The M9 negative describes extinction after 15 minutes at 14 cm/s; this is not failure to sustain for a common fixed duration.",
        "Actual oxygen at later stages is unknown; initial oxygen is a proxy.",
        "Most thickness and diameter values are missing; some materials have only one observed class.",
        "AI interpretation is disclosed, but no human scientific label review is recorded.",
    ]
    flex_report = summarize(flex, "extinction_binary", "split_group", FLEX_FEATURES)
    flex_report["by_fuel"] = {fuel: summarize([r for r in flex if r["fuel"] == fuel],
        "extinction_binary", "split_group", FLEX_FEATURES[1:]) for fuel in sorted({r["fuel"] for r in flex})}
    flex_report["decision"] = "selected_for_one_exploratory_model_in_step_3"
    flex_report["label_source"] = "NASA PSI-69 experimental table Test end; Extinction=1, Completion=0; no causal interpretation"
    flex_report["majority_class_reference_accuracy_not_model_evaluation"] = max(flex_report["classes"].values()) / len(flex)
    flex_report["majority_class_reference_balanced_accuracy_not_model_evaluation"] = .5
    excluded = [r for r in read("flex_labeled.csv") if r["training_eligible"] != "true"]
    flex_report["excluded_rows"] = [{"experiment_id": r["experiment_id"], "reason": r["exclusion_reasons"]} for r in excluded]
    report = {"audit_version": "1.0.0", "checked_on": "2026-11-14", "model_fitted": False,
              "provenance": "AI-assisted review and code by OpenAI Codex; descriptive counts computed in Python; no human scientific sign-off",
              "solid_candidates": solid_report, "flex_candidates": flex_report,
              "scope_decision": "Use the previously planned FLEX fallback for the one learned model; keep material comparison evidence-based.",
              "inputs_sha256": {name: hashlib.sha256((CLEAN / name).read_bytes()).hexdigest()
                                for name in ["solid_stage_training.csv", "flex_training.csv"]}}
    (CLEAN / "model_readiness.json").write_text(json.dumps(report, indent=2) + "\n")
    MODEL.mkdir(exist_ok=True)
    spec = {
        "spec_version": "1.0.0", "status": "scope_finalized; model_not_trained", "number_of_final_models": 1,
        "provenance": report["provenance"],
        "dataset": "data/clean/flex_training.csv", "dataset_sha256": report["inputs_sha256"]["flex_training.csv"],
        "source_record": "PSI-69", "source_url": "https://psi.nasa.gov/physci/repo/data/investigations/PSI-69",
        "task": "binary_classification", "target": "extinction_binary",
        "target_meaning": "Recorded Test end category Extinction versus Completion among non-disrupted, valid-feature FLEX observations",
        "classes": {"0": "Completion", "1": "Extinction"}, "training_rows": len(flex),
        "class_counts": flex_report["classes"], "group_column": "split_group",
        "features": FLEX_FEATURES, "fuel_categories": sorted({r["fuel"] for r in flex}),
        "units": {"pressure_kpa": "kPa", "oxygen_pct": "oxygen mole percent", "co2_fraction": "mole fraction",
                  "helium_fraction": "mole fraction", "droplet_diameter_mm": "mm"},
        "nitrogen_handling": "Use reported nitrogen for source-composition validation; omit it as a redundant model feature. For a user scenario it is the remaining fraction.",
        "domains_by_fuel": flex_report["by_fuel"],
        "domain_policy": "Observed per-fuel bounds are preliminary exclusion limits, not proof of joint support. Step 4 must also return comparable real tests and reject unsupported combinations.",
        "validation_rules": ["positive finite pressure and initial diameter", "finite oxygen in (0,100]",
            "gas fractions in [0,1]", "source gas-fraction sum within 0.01 of one (screening heuristic, not instrument accuracy)",
            "no Disruption labels", "no missing initial features", "do not repair, renormalize or default invalid source values"],
        "validation_plan": {"outer_folds": 5, "stratify_by": "extinction_binary", "group_by": "split_group", "seed": 42,
            "no_group_overlap": True, "require_both_classes_in_each_fold": True,
            "preprocessing": "fit categorical encoding and numeric transforms within training folds only",
            "tuning_and_calibration": "training folds only with inner grouped splits; no use of outer validation labels for model fitting",
            "primary_metric": "balanced_accuracy", "secondary_metrics": ["macro_f1", "per_class_precision_recall_f1", "confusion_matrix", "brier_score", "log_loss"],
            "baselines": ["majority-class classifier", "simple logistic regression"],
            "models_to_compare": ["logistic regression", "small random forest"],
            "promotion_gate": "Compare against baseline using out-of-fold results, report uncertainty and calibration; do not enable numerical predictions if evidence is inadequate"},
        "output_scope": "Experimental FLEX terminal-category estimate, conditional on comparable tests with either of the two selected endings",
        "unsupported_claims": ["solid-material burn probability or safety ranking", "ignition resistance", "causal suppressant effectiveness",
            "fire-extinguisher success", "flame spread rate", "Moon/Mars or partial-gravity prediction", "spacecraft certification"],
        "excluded_predictor_columns": ["test_id", "experiment_id", "split_group", "test_date", "test_end_raw", "burn_time_s",
            "extinction_diameter_mm", "burning_rate_raw", "extinction_binary", "training_eligible", "exclusion_reasons"],
        "solid_prediction_enabled": False, "pressure_prediction_scope": "FLEX droplet experiments only; no inferred pressure effect for BASS/BASS-II",
        "no_training_in_step_2": True,
    }
    (MODEL / "model_spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    quality = json.loads((CLEAN / "quality_report.json").read_text())
    quality["model_readiness"] = "Step 2 selected FLEX terminal-category scope; no model fitted; see model_readiness.json"
    (CLEAN / "quality_report.json").write_text(json.dumps(quality, indent=2) + "\n")
    contract = json.loads((CLEAN / "data_contract.json").read_text())
    contract["training_gate"] = "Use the selected FLEX scope and feature list in model/model_spec.json; solid-stage candidates remain exploratory evidence, not the selected predictor"
    contract["selected_model_spec"] = "model/model_spec.json"
    (CLEAN / "data_contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    print(json.dumps({"solid_rows": len(solids), "selected_dataset": spec["dataset"], "valid_flex_rows": len(flex),
                      "class_counts": spec["class_counts"], "groups": flex_report["groups"], "model_fitted": False}, indent=2))


if __name__ == "__main__":
    build_readiness()
