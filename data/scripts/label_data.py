#!/usr/bin/env python3
"""Apply evidence-linked AI reviews and build conservative training candidates.

Works offline on the committed clean CSVs. Outcomes are curated by experiment
ID in data/annotations, not inferred by a substring classifier. No model is fit.
"""
from __future__ import annotations

import csv
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data/clean"
ANNOTATIONS = ROOT / "data/annotations"
EVIDENCE_FIELDS = ["experiment_id", "notes", "airflow_raw", "fan_display_raw", "oxygen_pct", "oxygen_final_pct", "material_raw"]
REVIEW_COLUMNS = ["experiment_id", "test_id", "source_record", "source_url", "source_locator", "notes",
                  "target_name", "target_value", "condition_airflow_cm_s", "condition_oxygen_pct",
                  "condition_pressure_kpa", "evidence_note", "reviewer", "review_status"]
FLEX_INITIAL_FIELDS = ["fuel", "pressure_kpa", "oxygen_pct", "nitrogen_fraction", "co2_fraction", "helium_fraction", "droplet_diameter_mm"]
# Conservative screening rule, not a statement about instrument accuracy.
FLEX_COMPOSITION_TOLERANCE = .01


def flex_initial_problems(row):
    problems, values = [], {}
    for field in FLEX_INITIAL_FIELDS:
        if row.get(field, "") == "":
            problems.append("missing_initial_feature:" + field)
        elif field != "fuel":
            value = number(row[field])
            if value is None or not math.isfinite(value):
                problems.append("invalid_initial_number:" + field)
            else:
                values[field] = value
    for field in ["pressure_kpa", "droplet_diameter_mm"]:
        if field in values and values[field] <= 0:
            problems.append("nonpositive_initial_feature:" + field)
    if "oxygen_pct" in values and not 0 < values["oxygen_pct"] <= 100:
        problems.append("invalid_initial_oxygen")
    for field in ["nitrogen_fraction", "co2_fraction", "helium_fraction"]:
        if field in values and not 0 <= values[field] <= 1:
            problems.append("invalid_initial_fraction:" + field)
    components = ["oxygen_pct", "nitrogen_fraction", "co2_fraction", "helium_fraction"]
    if all(k in values for k in components):
        total = values["oxygen_pct"] / 100 + sum(values[k] for k in components[1:])
        if abs(total - 1) > FLEX_COMPOSITION_TOLERANCE + 1e-9:
            problems.append("initial_gas_fractions_do_not_sum_to_one")
    return problems


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, columns=None):
    columns = columns or list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def source_hash(row):
    return hashlib.sha256(json.dumps({k: row[k] for k in EVIDENCE_FIELDS}, sort_keys=True).encode()).hexdigest()


def number(value):
    return float(value) if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", str(value).strip()) else None


def airflow_readings(raw):
    """Split only unambiguous measured-air lists; never fan controls or prose.

    The list order is recorded order, not reconstructed timestamps. A range or
    inequality has bounds and no point estimate. Mixed-unit text is preserved.
    """
    raw = raw.strip()
    token = r"(?:[<>~]?\s*(?:\d+(?:\.\d*)?|\.\d+)(?:\s*-\s*(?:\d+(?:\.\d*)?|\.\d+))?)"
    if not raw:
        return [("", "", "missing")]
    if not re.fullmatch(token + r"(?:[\s,]+" + token + r")*\s*,?", raw):
        return [(raw, "", "unresolved_text_or_mixed_units")]
    result = []
    for match in re.finditer(token, raw):
        value = match.group().strip()
        numeric = number(value)
        result.append((value, numeric if numeric is not None else "", "exact_display" if numeric is not None else "bound_or_range"))
    return result


def validation_group(row):
    # Conservative grouping across BASS/BASS-II and modified ('m') samples.
    # Potentially groups unrelated samples together rather than leaking repeats.
    sample = re.sub(r"m$", "", row["sample_id"].lower())
    return "BASS-family:sample:" + sample


def candidate_reasons(row, event, review):
    reasons = []
    if event["airflow_cm_s"] == "":
        reasons.append("stage_airspeed_not_resolved")
    elif float(event["airflow_cm_s"]) <= 0:
        reasons.append("zero_display_or_forced_flow_off_not_ambient_no_burn")
    if event["airflow_qualifier"] != "exact":
        reasons.append("approximate_or_bounded_airspeed")
    if event["sustained_flame_binary"] == "":
        reasons.append("no_stage_sustained_flame_label")
    if event["protocol"] == "ignition":
        reasons.append("ignition_alone_does_not_establish_sustained_burning")
    if row["material"] == "Unresolved material":
        reasons.append("unresolved_material")
    if number(row["oxygen_pct"]) is None:
        reasons.append("missing_initial_oxygen")
    final = number(row["oxygen_final_pct"])
    if final is not None and abs(final - float(row["oxygen_pct"])) > .5:
        reasons.append("oxygen_changed_or_sensor_value_suspect")
    if review["context_flags"]:
        reasons.extend(review["context_flags"])
    # Prefill followed by a stated, calculated atmosphere is distinct from
    # injecting nitrogen while a flame burns. Ambiguous intervention is excluded.
    if re.search(r"\b(?:GN2|N2|nitrogen)\b", row["notes"], re.I) and row["test_id"] not in {"98"}:
        reasons.append("nitrogen_intervention_needs_condition_review")
    if event["event_cause"] in {"fuel_exhaustion", "flow_off", "nitrogen_or_suppression"}:
        reasons.append("nonintrinsic_terminal_event")
    return sorted(set(reasons))


def build_labels():
    rows = read_csv(CLEAN / "solid_combustion_model.csv")
    reviews = read_jsonl(ANNOTATIONS / "solid_test_reviews.jsonl")
    explicit = read_jsonl(ANNOTATIONS / "solid_stage_reviews.jsonl")
    byid = {row["experiment_id"]: row for row in rows}
    review_byid = {r["experiment_id"]: r for r in reviews}
    if len(review_byid) != len(reviews) or set(review_byid) != set(byid):
        raise ValueError("Reviews must cover every solid test exactly once")
    for review in reviews:
        if source_hash(byid[review["experiment_id"]]) != review["source_evidence_sha256"]:
            raise ValueError(f"Source changed since review: {review['experiment_id']}")
    for event in explicit:
        row = byid[event["experiment_id"]]
        if event["source_evidence_sha256"] != source_hash(row) or event["evidence_quote"] not in row[event["evidence_field"]]:
            raise ValueError(f"Invalid stage evidence: {event['experiment_id']}")

    stages, queue, readings = [], [], []
    for row in rows:
        review = review_byid[row["experiment_id"]]
        row.update(outcome=review["outcome"], burned_binary=review["any_flame_observed"],
                   label_status="ai_reviewed" if review["any_flame_observed"] != "" else "reviewed_unresolved",
                   training_eligible="false")
        queue.append({"experiment_id": row["experiment_id"], "test_id": row["test_id"],
                      "source_record": row["source_record"], "source_url": row["source_url"],
                      "source_locator": row["supplement_locator"], "notes": row["notes"],
                      "target_name": "any_flame_observed_in_test", "target_value": review["any_flame_observed"],
                      "condition_airflow_cm_s": "", "condition_oxygen_pct": "", "condition_pressure_kpa": "",
                      "evidence_note": review["review_comment"] + " Cause: " + review["extinction_cause"] +
                                       "; use solid_stage_observations.csv for condition-linked outcomes.",
                      "reviewer": review["reviewer"], "review_status": row["label_status"]})
        for order, (raw, value, status) in enumerate(airflow_readings(row["airflow_raw"]), 1):
            readings.append({"reading_id": f"{row['experiment_id']}:reading:{order}", "experiment_id": row["experiment_id"],
                             "recorded_order": order, "reading_raw": raw, "airflow_display_cm_s": value,
                             "reading_status": status, "outcome": "unassigned_no_time_alignment",
                             "source_field": "airflow_raw", "source_file": row["source_file"], "source_row": row["source_row"]})
        events = [dict(e) for e in explicit if e["experiment_id"] == row["experiment_id"]]
        generic = {"experiment_id": row["experiment_id"], "airflow_cm_s": "", "airflow_qualifier": "unresolved",
                   "protocol": "unresolved_stage", "flow_basis": "no_airflow_to_event_alignment",
                   "event_cause": review["extinction_cause"], "evidence_field": review["evidence_field"],
                   "evidence_quote": row[review["evidence_field"]], "reviewer": review["reviewer"],
                   "source_evidence_sha256": review["source_evidence_sha256"]}
        if not events:
            events.append({**generic, "sustained_flame_binary": "", "event_state": review["outcome"]})
        terminal = review["outcome"] in {"burn_then_extinguished", "suppression_extinction", "fuel_exhaustion"}
        if terminal and not any(e["sustained_flame_binary"] == 0 for e in events):
            events.append({**generic, "sustained_flame_binary": 0, "event_state": "terminal_extinction"})
        for order, event in enumerate(events, 1):
            reasons = candidate_reasons(row, event, review)
            stages.append({"stage_id": f"{row['experiment_id']}:event:{order}", "experiment_id": row["experiment_id"],
                "event_order": order, "source_record": row["source_record"], "test_id": row["test_id"],
                "material": row["material"], "material_raw": row["material_raw"], "sample_geometry": row["sample_geometry"],
                "thickness_mm": row["thickness_mm"], "diameter_mm": row["diameter_mm"], "width_mm": row["width_mm"],
                "oxygen_initial_pct": row["oxygen_pct"], "oxygen_final_pct": row["oxygen_final_pct"],
                "oxygen_at_stage_pct": "", "oxygen_basis": "initial_test_measurement_only; no interpolation",
                "pressure_kpa": row["pressure_kpa"], "airflow_cm_s": event["airflow_cm_s"],
                "airflow_qualifier": event["airflow_qualifier"], "airflow_basis": event["flow_basis"],
                "airflow_raw": row["airflow_raw"], "fan_display_raw": row["fan_display_raw"],
                "flow_direction": row["flow_direction"],
                "protocol": "ignition_trial" if event["protocol"] in {"ignition", "after_ignition", "ignition_attempt"} else "ongoing_burn_trial",
                "event_state": event.get("event_state", "sustained_burning" if event["sustained_flame_binary"] == 1 else "not_sustained_or_extinguished"),
                "event_cause": event["event_cause"], "sustained_flame_binary": event["sustained_flame_binary"],
                "training_eligible": "false" if reasons else "true", "exclusion_reasons": "|".join(reasons),
                "validation_group": validation_group(row), "source_file": row["source_file"],
                "source_row": row["source_row"], "source_url": row["source_url"],
                "supplement_file": row["supplement_file"], "supplement_locator": row["supplement_locator"],
                "evidence_field": event["evidence_field"], "evidence_quote": event["evidence_quote"],
                "reviewer": event["reviewer"], "review_status": "ai_reviewed; no human sign-off"})
    write_csv(CLEAN / "solid_combustion_model.csv", rows)
    write_csv(CLEAN / "label_review_queue.csv", queue, REVIEW_COLUMNS)
    write_csv(CLEAN / "airflow_readings.csv", readings)
    write_csv(CLEAN / "solid_stage_observations.csv", stages)
    candidates = [s for s in stages if s["training_eligible"] == "true"]
    write_csv(CLEAN / "solid_stage_training.csv", candidates, list(stages[0]))

    flex = read_csv(CLEAN / "flex_backup.csv")
    flex_labels = []
    features = FLEX_INITIAL_FIELDS
    for row in flex:
        end = row["test_end_raw"]
        if end not in {"Extinction", "Completion", "Disruption"}:
            raise ValueError(f"Unrecognized FLEX end result {end}")
        label = 1 if end == "Extinction" else 0 if end == "Completion" else ""
        reasons = (["disruption_censored_not_extinction_or_completion"] if end == "Disruption" else []) + flex_initial_problems(row)
        flex_labels.append({**row, "target_name": "terminal_extinction_vs_completion", "extinction_binary": label,
                            "training_eligible": "false" if reasons else "true", "exclusion_reasons": "|".join(reasons)})
    write_csv(CLEAN / "flex_labeled.csv", flex_labels)
    flex_candidates = [r for r in flex_labels if r["training_eligible"] == "true"]
    write_csv(CLEAN / "flex_training.csv", flex_candidates, list(flex_labels[0]))
    report = {"schema_version": "1.1.0", "review_method": "Individual AI review of all available test notes and control annotations; no human sign-off",
        "solid_tests_reviewed": len(rows), "test_outcomes": dict(Counter(r["outcome"] for r in rows)),
        "test_any_flame_labels": dict(Counter(str(r["burned_binary"]) for r in rows)),
        "explicit_flow_event_links": len(explicit), "stage_observations": len(stages),
        "airflow_readings": len(readings), "solid_training_candidates": len(candidates),
        "solid_candidate_class_counts": dict(Counter(str(s["sustained_flame_binary"]) for s in candidates)),
        "solid_candidate_validation_groups": len({s["validation_group"] for s in candidates}),
        "stage_exclusions": dict(Counter(reason for s in stages for reason in s["exclusion_reasons"].split("|") if reason)),
        "flex_training_candidates": len(flex_candidates), "flex_candidate_class_counts": dict(Counter(str(r["extinction_binary"]) for r in flex_candidates)),
        "flex_disruptions_excluded": sum(r["test_end_raw"] == "Disruption" for r in flex_labels),
        "flex_initial_quality_exclusions": dict(Counter(reason for r in flex_labels for reason in r["exclusion_reasons"].split("|") if reason and not reason.startswith("disruption_"))),
        "training_status": "Exploratory labeled candidates; no model fit or validated predictions. Labels retain source-specific observation horizons and AI review provenance.",
        "required_solid_features": ["material", "oxygen_initial_pct", "airflow_cm_s", "protocol"],
        "optional_solid_features": ["sample_geometry", "flow_direction", "thickness_mm", "diameter_mm", "width_mm"],
        "flex_features": [f for f in features if f != "nitrogen_fraction"],
        "flex_validation_fields": features,
        "forbidden_features": ["outcome", "burned_binary", "notes", "evidence_quote", "event_state", "event_cause", "review_status", "exclusion_reasons", "oxygen_final_pct", "co2_final_pct", "burn_time_s", "extinction_diameter_mm", "burning_rate_raw", "test_end_raw"],
    }
    (CLEAN / "labeling_report.json").write_text(json.dumps(report, indent=2) + "\n")
    quality = json.loads((CLEAN / "quality_report.json").read_text())
    quality.update(schema_version="1.1.0", solid_labeled_rows=sum(r["burned_binary"] != "" for r in rows),
                   solid_tests_reviewed=len(rows), training_eligible_rows=0,
                   solid_training_stage_rows=len(candidates), flex_training_rows=len(flex_candidates),
                   model_readiness="exploratory_stage_candidates_available; use stage table, not whole-test labels")
    quality["limitations"][0] = "Individual AI reviews supply any-flame test labels and conservative sustained-flame stage candidates. Extinction after burning is not a no-burn test label; no human sign-off is claimed."
    (CLEAN / "quality_report.json").write_text(json.dumps(quality, indent=2) + "\n")
    contract = json.loads((CLEAN / "data_contract.json").read_text())
    contract.update(schema_version="1.1.0", training_gate="Use solid_stage_training.csv or separate flex_training.csv; validate grouped splits and feature coverage before fitting",
                    cross_validation_group="validation_group in stage files; whole-test split_group retained for compatibility")
    contract["columns"]["burned_binary"]["use"] = "Any visible flame reported anywhere in test; not the sustained-flame stage target"
    contract["training_targets"] = {
        "solid_stage_training.csv": {"target": "sustained_flame_binary", "positive": "source-reported sustained/established flame at the selected event",
            "negative": "source-reported failure to sustain or extinction at the selected event", "group": "validation_group",
            "required_features": report["required_solid_features"], "optional_features": report["optional_solid_features"],
            "oxygen_caveat": "oxygen_initial_pct is not actual stage oxygen; oxygen_at_stage_pct remains unknown",
            "protocol": "ignition_trial versus ongoing_burn_trial; both categories contain both labels"},
        "flex_training.csv": {"target": "extinction_binary", "positive": "Extinction", "negative": "Completion",
            "censored": "Disruption", "group": "split_group", "features": report["flex_features"]},
    }
    contract["dataset_roles"].update({"solid_combustion_model.csv": "Reviewed whole-test observations; not independent condition labels",
        "solid_stage_observations.csv": "Evidence-linked events; includes unknown conditions and excluded endpoints",
        "solid_stage_training.csv": "Conservative sustained-flame stage candidates with measured airspeed; initial oxygen is a proxy, protocol is required",
        "airflow_readings.csv": "Instrument reading order only; no inferred outcome or reconstructed timestamp",
        "flex_training.csv": "Separate terminal-extinction classifier candidates; disruptions censored"})
    (CLEAN / "data_contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ["solid_tests_reviewed", "explicit_flow_event_links", "solid_training_candidates", "solid_candidate_class_counts", "flex_training_candidates", "flex_disruptions_excluded"]}, indent=2))


if __name__ == "__main__":
    build_labels()
