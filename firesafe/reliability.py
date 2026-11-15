"""Statistics and a reliability review for every model prediction.

All figures come from model/metrics.json (grouped cross-validation, written by
model/train.py) and the training CSVs, never from the LLM. The review has two parts:

* model_statistics: how the deployed model scored out-of-fold against the constant
  baseline and the simpler model (material-only / fuel-only). Same for every prediction.
* checks: whether THIS prediction is inside the tested conditions, has enough
  training examples, and falls where the model's out-of-fold probabilities matched
  observed outcome rates.

The rating summarises the checks. It describes how far the data supports the
estimate; it is not a safety certification.
"""
from __future__ import annotations

from . import predictor

SIMPLER = {"solid": "Material only (logistic)", "flex": "Fuel only (logistic)"}
TARGET = {"solid": "flame stays lit at this stage (sustained burning)",
          "flex": "droplet flame extinguishes before the fuel is consumed"}
TRAINING_TABLE = {"solid": "solid_stage_training", "flex": "flex_training"}
MODEL_FILE = {"solid": "model/solid_model.joblib", "flex": "model/flex_model.joblib"}
GROUP_KEY = {"solid": "material", "flex": "fuel"}

MIN_EXAMPLES = 10          # training rows for this material / fuel
BASELINE_GAIN = 0.10       # deployed log loss must be >= 10% below the constant baseline
CAL_WIDTH = 0.10           # out-of-fold predictions within +/-0.10 of this probability
CAL_MIN_N = 8
CAL_MAX_GAP = 0.15         # |mean predicted - observed rate| allowed in that neighbourhood


def _row(m: dict, name: str) -> dict:
    return next(c for c in m["comparison"] if c["model"].startswith(name))


def model_statistics(kind: str) -> dict:
    """Out-of-fold performance of the deployed model next to the baselines it must beat."""
    m = predictor.metrics()[kind]
    dep = next(c for c in m["comparison"] if "[deployed]" in c["model"])
    base, simple = m["comparison"][0], _row(m, SIMPLER[kind])
    keep = ("roc_auc", "log_loss", "brier", "accuracy", "balanced_accuracy")
    return {
        "model": dep["model"].replace(" [deployed]", ""),
        "predicts": TARGET[kind],
        "model_file": MODEL_FILE[kind],
        "trained_on": f"{TRAINING_TABLE[kind]} ({m['n_observations']} rows, {m['n_groups']} validation groups, "
                      f"class counts {m['class_counts']})",
        "validation": m["validation"],
        "deployed_out_of_fold": {k: dep[k] for k in keep},
        "constant_baseline_out_of_fold": {k: base[k] for k in keep},
        "simpler_model": {"model": simple["model"], **{k: simple[k] for k in keep}},
        "log_loss_improvement_vs_baseline_pct": round(100 * (1 - dep["log_loss"] / base["log_loss"]), 1),
        "metric_notes": "Out-of-fold = each row scored by a model that never saw its group. Lower log loss / "
                        "Brier is better; ROC AUC 0.5 = no discrimination, 1.0 = perfect.",
        **({"label_provenance": m["label_provenance"]} if "label_provenance" in m else {}),
    }


def _calibration(kind: str, p: float, group: str | None) -> dict:
    """Observed outcome rate among out-of-fold predictions close to p (same material/fuel when possible)."""
    oof = predictor.metrics()[kind]["oof"]
    near = [r for r in oof if abs(r["predicted"] - p) <= CAL_WIDTH]
    same = [r for r in near if r.get(GROUP_KEY[kind]) == group]
    pool, basis = (same, f"same {GROUP_KEY[kind]}") if len(same) >= CAL_MIN_N else (near, "all training rows")
    if not pool:
        return {"n": 0, "basis": basis, "window": f"predicted {p - CAL_WIDTH:.2f}-{p + CAL_WIDTH:.2f}"}
    obs = sum(r["actual"] for r in pool) / len(pool)
    mean = sum(r["predicted"] for r in pool) / len(pool)
    return {"n": len(pool), "basis": basis, "window": f"predicted {max(0, p - CAL_WIDTH):.2f}-{min(1, p + CAL_WIDTH):.2f}",
            "mean_predicted": round(mean, 3), "observed_rate": round(obs, 3), "gap": round(abs(obs - mean), 3)}


def _group_record(kind: str, group: str) -> dict:
    rows = [r for r in predictor.metrics()[kind]["oof"] if r.get(GROUP_KEY[kind]) == group]
    if not rows:
        return {"n": 0}
    acc = sum(int((r["predicted"] >= 0.5) == bool(r["actual"])) for r in rows) / len(rows)
    return {"n": len(rows), "observed_rate": round(sum(r["actual"] for r in rows) / len(rows), 3),
            "mean_out_of_fold_prediction": round(sum(r["predicted"] for r in rows) / len(rows), 3),
            "out_of_fold_accuracy": round(acc, 3)}


def review(kind: str, pred: dict, group: str) -> dict:
    """Reliability review for one prediction returned by predictor.predict_solid / predict_flex."""
    stats = model_statistics(kind)
    p = pred.get("probability")
    if p is None:
        known = group in predictor.metrics()[kind]["ranges"]
        return {"rating": "low" if known else "not applicable", "reasons": pred.get("warnings", []),
                "checks": [{"check": "Inputs inside the tested conditions", "passed": False,
                            "detail": "; ".join(pred.get("warnings", [])) or "No supported estimate."}],
                "model_statistics": stats}
    m = predictor.metrics()[kind]
    n_group = m["ranges"].get(group, {}).get("n", 0)
    dep, base, simple = stats["deployed_out_of_fold"], stats["constant_baseline_out_of_fold"], stats["simpler_model"]
    cal = _calibration(kind, p, group)
    checks = [
        {"check": "Inputs inside the tested conditions", "passed": not pred.get("warnings"),
         "detail": "; ".join(pred.get("warnings", [])) or "All inputs within the training range for this "
                                                          f"{GROUP_KEY[kind]}."},
        {"check": "Model beats the constant baseline (grouped CV)",
         "passed": dep["log_loss"] <= base["log_loss"] * (1 - BASELINE_GAIN),
         "detail": f"log loss {dep['log_loss']} vs baseline {base['log_loss']} "
                   f"({stats['log_loss_improvement_vs_baseline_pct']}% better); ROC AUC {dep['roc_auc']}."},
        {"check": f"Conditions add skill over the {simple['model']}",
         "passed": dep["log_loss"] < simple["log_loss"],
         "detail": f"log loss {dep['log_loss']} vs {simple['log_loss']} without the conditions."},
        {"check": f"At least {MIN_EXAMPLES} training rows for this {GROUP_KEY[kind]}", "passed": n_group >= MIN_EXAMPLES,
         "detail": f"{n_group} training rows for {group}."},
        {"check": "Out-of-fold predictions near this value matched observed outcomes",
         "passed": cal["n"] >= CAL_MIN_N and cal.get("gap", 1) <= CAL_MAX_GAP,
         "detail": (f"{cal['n']} rows ({cal['basis']}) in {cal['window']}: mean predicted "
                    f"{cal['mean_predicted']}, observed rate {cal['observed_rate']}." if cal["n"]
                    else f"No out-of-fold predictions in {cal['window']}.")},
    ]
    failed = [c["check"] for c in checks if not c["passed"]]
    if not checks[0]["passed"]:
        rating = "low"
    else:
        rating = "higher" if not failed else "moderate" if len(failed) == 1 else "low"
    reasons = [f"Failed: {f}" for f in failed]
    if kind == "solid" and rating == "higher":
        rating = "moderate"
        reasons.append("Capped at moderate: the solid model is exploratory (47 AI-labelled stages).")
    return {
        "rating": rating,
        "rating_scale": "low / moderate / higher, relative to this NASA dataset; not a safety certification",
        "reasons": reasons or ["All checks passed."],
        "checks": checks,
        "local_calibration": cal,
        f"this_{GROUP_KEY[kind]}_in_training": _group_record(kind, group),
        "model_statistics": stats,
    }
