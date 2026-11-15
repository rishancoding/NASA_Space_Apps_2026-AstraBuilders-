"""Train and validate the two FLEX droplet models.

1. Extinction classifier: recorded Extinction (1) vs Completion (0), the target
   defined in model/model_spec.json.
2. Burn-time regressor: recorded burn time in seconds for the same screened
   rows. This is a second, separate exploratory model added after the spec;
   it shares the spec's features, groups and leakage rules.

Validation follows the spec: 5 outer StratifiedGroupKFold folds (seed 42),
groups = split_group, preprocessing fit inside each training fold, majority /
mean baselines. Each model has a promotion gate; if it fails, the API reports
the prediction as unavailable instead of showing a number.

Run from the repo root:  .venv/Scripts/python model/train_flex.py
"""
from __future__ import annotations

import json
import sys

import joblib
import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (balanced_accuracy_score, brier_score_loss, confusion_matrix, f1_score,
                             log_loss, mean_absolute_error, precision_recall_fscore_support, r2_score,
                             roc_auc_score)
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import ARTIFACTS, FEATURES, GROUP, SEED, SPEC, load_flex_training, preprocessor, to_jsonable  # noqa: E402

N_BOOT = 1000
N_ENSEMBLE = 25
CONFORMAL_LEVEL = 0.9


def classifier_candidates():
    # The displayed number is a probability, so candidates are judged on probability accuracy (Brier) as well as
    # balanced accuracy. Balanced class weights rank well but understate extinction (~0.63 mean vs 0.87 observed),
    # so the unweighted logistic regression is included and usually wins on Brier.
    return {
        "majority_baseline": Pipeline([("prep", preprocessor()), ("model", DummyClassifier(strategy="prior"))]),
        "logistic_regression": Pipeline([("prep", preprocessor()), ("model", LogisticRegression(max_iter=2000, C=1.0))]),
        "logistic_regression_balanced": Pipeline([("prep", preprocessor()), ("model", LogisticRegression(
            class_weight="balanced", max_iter=2000, C=1.0))]),
        "random_forest": Pipeline([("prep", preprocessor()), ("model", RandomForestClassifier(
            n_estimators=300, max_depth=4, min_samples_leaf=3, random_state=SEED))]),
    }


def tuned_threshold(model, X, y, groups, seed=SEED):
    """Pick the decision threshold that maximises balanced accuracy using inner grouped CV on training rows only."""
    inner = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=seed)
    p = np.zeros(len(y))
    for tr, te in inner.split(X, y, groups):
        p[te] = clone(model).fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    ts = np.linspace(0.05, 0.95, 91)
    scores = [balanced_accuracy_score(y, (p >= t).astype(int)) for t in ts]
    return float(ts[int(np.argmax(scores))])


def calibration_table(y, p, bins=5):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -0.01, 1.01
    return [{"predicted_mean": float(p[m].mean()), "observed_rate": float(y[m].mean()), "n": int(m.sum())}
            for lo, hi in zip(edges[:-1], edges[1:]) if (m := (p > lo) & (p <= hi)).sum()]


def regressor_candidates():
    return {
        "mean_baseline": Pipeline([("prep", preprocessor()), ("model", DummyRegressor())]),
        "ridge": Pipeline([("prep", preprocessor()), ("model", Ridge(alpha=1.0))]),
        "random_forest": Pipeline([("prep", preprocessor()), ("model", RandomForestRegressor(
            n_estimators=300, max_depth=6, min_samples_leaf=3, random_state=SEED))]),
    }


def bootstrap_ci(y, pred, metric, rng):
    n, scores = len(y), []
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2 and metric is balanced_accuracy_score:
            continue
        scores.append(metric(y[idx], pred[idx]))
    return [float(np.percentile(scores, 2.5)), float(np.percentile(scores, 97.5))]


def group_bootstrap_ensemble(model, X, y, groups, rng, n=N_ENSEMBLE, need_both_classes=False):
    """Refit the model on group-level bootstrap resamples to show model spread."""
    uniq = np.unique(groups)
    members = []
    while len(members) < n:
        picked = rng.choice(uniq, len(uniq), replace=True)
        idx = np.concatenate([np.flatnonzero(groups == g) for g in picked])
        if need_both_classes and len(np.unique(y[idx])) < 2:
            continue
        members.append(clone(model).fit(X.iloc[idx], y[idx]))
    return members


def train_classifier(df, rng):
    X, y, groups = df[FEATURES], df["extinction_binary"].astype(int).to_numpy(), df[GROUP].to_numpy()
    cv = StratifiedGroupKFold(n_splits=SPEC["validation_plan"]["outer_folds"], shuffle=True, random_state=SEED)
    folds = list(cv.split(X, y, groups))
    fold_checks = []
    for i, (tr, te) in enumerate(folds):
        assert not set(groups[tr]) & set(groups[te]), "group leakage across folds"
        fold_checks.append({"fold": i, "test_rows": len(te), "test_completion": int((y[te] == 0).sum()),
                            "test_extinction": int((y[te] == 1).sum())})
        assert len(np.unique(y[te])) == 2, f"fold {i} lacks a class"

    results, oof_by_model = {}, {}
    for name, model in classifier_candidates().items():
        prob, pred = np.zeros(len(y)), np.zeros(len(y), dtype=int)
        thresholds = []
        for tr, te in folds:
            fitted = clone(model).fit(X.iloc[tr], y[tr])
            prob[te] = fitted.predict_proba(X.iloc[te])[:, 1]
            t = 0.5 if name == "majority_baseline" else tuned_threshold(model, X.iloc[tr], y[tr], groups[tr])
            thresholds.append(t)
            pred[te] = (prob[te] >= t).astype(int)
        p, r, f, s = precision_recall_fscore_support(y, pred, labels=[0, 1], zero_division=0)
        results[name] = {
            "decision_thresholds_per_fold": thresholds,
            "calibration": calibration_table(y, prob) if name != "majority_baseline" else None,
            "mean_predicted_probability": float(prob.mean()),
            "balanced_accuracy": balanced_accuracy_score(y, pred),
            "balanced_accuracy_95ci": bootstrap_ci(y, pred, balanced_accuracy_score, rng),
            "macro_f1": f1_score(y, pred, average="macro", zero_division=0),
            "raw_accuracy": float((pred == y).mean()),
            "per_class": {"Completion": {"precision": p[0], "recall": r[0], "f1": f[0], "support": s[0]},
                          "Extinction": {"precision": p[1], "recall": r[1], "f1": f[1], "support": s[1]}},
            "confusion_matrix": {"labels": ["Completion", "Extinction"], "rows_actual_cols_predicted":
                                 confusion_matrix(y, pred, labels=[0, 1])},
            "roc_auc": roc_auc_score(y, prob) if name != "majority_baseline" else 0.5,
            "brier_score": brier_score_loss(y, prob),
            "log_loss": log_loss(y, np.clip(prob, 1e-6, 1 - 1e-6)),
        }
        oof_by_model[name] = prob

    base = results["majority_baseline"]
    contenders = {k: v for k, v in results.items() if k != "majority_baseline" and v["balanced_accuracy_95ci"][0] > 0.5}
    # Among models that clearly beat guessing, show the one whose probabilities are most accurate.
    selected = min(contenders, key=lambda k: contenders[k]["brier_score"]) if contenders else "logistic_regression"
    sel = results[selected]
    enabled = bool(contenders) and sel["balanced_accuracy"] >= base["balanced_accuracy"] + 0.1 and sel["brier_score"] < base["brier_score"]
    gate = ("passed: balanced accuracy (95% CI above 0.5, at least 0.10 above guessing) and Brier score better than the base rate"
            if enabled else "failed: not clearly better than the base rate; predictions disabled")

    final = clone(candidates_selected := classifier_candidates()[selected]).fit(X, y)
    threshold = tuned_threshold(candidates_selected, X, y, groups)
    ensemble = group_bootstrap_ensemble(candidates_selected, X, y, groups, rng, need_both_classes=True)
    joblib.dump({"model": final, "ensemble": ensemble, "features": FEATURES, "selected": selected,
                 "enabled": enabled, "threshold": threshold, "base_rate": float(y.mean())},
                ARTIFACTS / "extinction_model.joblib", compress=3)

    oof = [{"experiment_id": e, "fuel": fu, "actual": int(a), "predicted_probability": round(float(pp), 4)}
           for e, fu, a, pp in zip(df["experiment_id"], df["fuel"], y, oof_by_model[selected])]
    return {
        "task": "binary_classification", "target": SPEC["target"], "target_meaning": SPEC["target_meaning"],
        "classes": SPEC["classes"], "rows": len(y), "groups": int(len(np.unique(groups))),
        "class_counts": {"Extinction": int(y.sum()), "Completion": int((y == 0).sum())},
        "validation": "5-fold StratifiedGroupKFold by split_group, seed 42, out-of-fold predictions; decision threshold "
                      "tuned by inner grouped CV on each training fold only",
        "folds": fold_checks, "candidates": results, "selected_model": selected,
        "selection_rule": "lowest Brier score among models whose balanced-accuracy 95% CI is above 0.5",
        "decision_threshold": threshold, "base_rate_extinction": float(y.mean()),
        "prediction_enabled": enabled, "promotion_gate": gate,
        "uncertainty_method": f"spread of {N_ENSEMBLE} models refit on group bootstrap resamples (10th-90th percentile)",
        "notes": ["Displayed probabilities are unweighted, so they track observed extinction rates (see calibration).",
                  "Extinction is the usual ending (87%). The decision threshold marks conditions that lean toward completion "
                  "compared with typical tests.",
                  "Always predicting Extinction gives about 87% raw accuracy; use balanced accuracy and Brier score."],
    }, oof


def train_regressor(df, rng):
    df = df[df["burn_time_s"].notna()].reset_index(drop=True)
    X, groups = df[FEATURES], df[GROUP].to_numpy()
    y_s = df["burn_time_s"].to_numpy()
    y = np.log1p(y_s)  # burn times are skewed (0.3-39 s); model in log space
    folds = list(GroupKFold(n_splits=5).split(X, y, groups))

    results, oof_by_model = {}, {}
    for name, model in regressor_candidates().items():
        pred = np.zeros(len(y))
        for tr, te in folds:
            pred[te] = clone(model).fit(X.iloc[tr], y[tr]).predict(X.iloc[te])
        pred_s = np.expm1(pred)
        # Honest conformal coverage: each fold's interval width comes only from other folds' residuals.
        covered, widths = [], []
        for k, (tr, te) in enumerate(folds):
            other = np.concatenate([f[1] for j, f in enumerate(folds) if j != k])
            res = np.abs(y[other] - pred[other])
            q = np.quantile(res, min(1.0, CONFORMAL_LEVEL * (1 + 1 / len(res))))
            lo, hi = np.expm1(pred[te] - q), np.expm1(pred[te] + q)
            covered += list((y_s[te] >= lo) & (y_s[te] <= hi))
            widths += list(hi - lo)
        results[name] = {
            "mae_s": mean_absolute_error(y_s, pred_s),
            "r2": r2_score(y_s, pred_s),
            "r2_log_space": r2_score(y, pred),
            "r2_95ci": bootstrap_ci(y_s, pred_s, r2_score, rng),
            "interval_coverage": float(np.mean(covered)),
            "median_interval_width_s": float(np.median(widths)),
        }
        oof_by_model[name] = pred

    contenders = {k: v for k, v in results.items() if k != "mean_baseline"}
    selected = max(contenders, key=lambda k: contenders[k]["r2"])
    enabled = results[selected]["r2_95ci"][0] > 0.2
    gate = ("passed: lower 95% bound of R² is above 0.2" if enabled
            else "failed: R² is not reliably above 0.2; predictions disabled")
    residuals = np.abs(y - oof_by_model[selected])
    q = float(np.quantile(residuals, min(1.0, CONFORMAL_LEVEL * (1 + 1 / len(residuals)))))
    final = clone(regressor_candidates()[selected]).fit(X, y)
    joblib.dump({"model": final, "features": FEATURES, "selected": selected, "enabled": enabled,
                 "target_transform": "log1p", "conformal_q_log": q, "conformal_level": CONFORMAL_LEVEL},
                ARTIFACTS / "burn_time_model.joblib", compress=3)

    oof = [{"experiment_id": e, "fuel": fu, "actual_s": float(a), "predicted_s": round(float(np.expm1(p)), 3)}
           for e, fu, a, p in zip(df["experiment_id"], df["fuel"], y_s, oof_by_model[selected])]
    return {
        "task": "regression", "target": "burn_time_s", "target_meaning":
            "Recorded FLEX burn time in seconds, among the same screened Extinction/Completion rows",
        "rows": len(y), "groups": int(len(np.unique(groups))),
        "validation": "5-fold GroupKFold by split_group, out-of-fold predictions; model fit on log1p(seconds)",
        "candidates": results, "selected_model": selected, "prediction_enabled": enabled, "promotion_gate": gate,
        "uncertainty_method": f"split-conformal {int(CONFORMAL_LEVEL * 100)}% interval from out-of-fold log residuals",
        "notes": ["Added after model_spec.json as a separate exploratory model; same features and leakage rules.",
                  "Burn time ends at either extinction or completion, so it is not a pure burning-rate measure."],
    }, oof


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    df = load_flex_training()
    clf_metrics, clf_oof = train_classifier(df, rng)
    reg_metrics, reg_oof = train_regressor(df, rng)
    domains = SPEC["domains_by_fuel"]
    metrics = {"trained_with": {"scikit_learn": sklearn.__version__, "python": sys.version.split()[0]},
               "dataset": SPEC["dataset"], "source_record": SPEC["source_record"], "source_url": SPEC["source_url"],
               "features": FEATURES, "units": SPEC["units"], "domains_by_fuel": domains,
               "unsupported_claims": SPEC["unsupported_claims"],
               "extinction": clf_metrics, "burn_time": reg_metrics}
    (ARTIFACTS / "metrics.json").write_text(json.dumps(to_jsonable(metrics), indent=2) + "\n")
    (ARTIFACTS / "oof_predictions.json").write_text(json.dumps(to_jsonable(
        {"extinction": clf_oof, "burn_time": reg_oof})) + "\n")

    for label, m, key in [("Extinction classifier", clf_metrics, "balanced_accuracy"), ("Burn-time regressor", reg_metrics, "r2")]:
        print(f"\n{label}: selected {m['selected_model']} | enabled={m['prediction_enabled']}")
        for name, r in m["candidates"].items():
            extra = f"  CI {np.round(r.get('balanced_accuracy_95ci', r.get('r2_95ci')), 3)}"
            print(f"  {name:22s} {key}={r[key]:.3f}{extra}" + (f"  MAE={r['mae_s']:.2f}s cover={r['interval_coverage']:.2f}" if 'mae_s' in r else f"  F1={r['macro_f1']:.3f} AUC={r['roc_auc']:.3f}"))
        print("  gate:", m["promotion_gate"])


if __name__ == "__main__":
    main()
