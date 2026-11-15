"""Exploratory full-dataset CV stress tests for FLEX model candidates.

These experiments do not audit the frozen split-conformal burn-time pipeline
or calibrate its intervals. Its independent audit is in train_flex.py/metrics.json.

Checks:
 1. Stability: grouped CV repeated with 20 different shuffles.
 2. Permutation test: is the score better than the same model trained on shuffled labels?
 3. Shortcut baselines: fuel-only (extinction) and diameter-only physics fit (burn time, d² law).
 4. Per-fuel scores.
 5. Calibration: do displayed probabilities match observed frequencies?
 6. Learning curve: would more rows help?
 7. New-atmosphere generalisation: hold out every CO2 or helium test at once.
 8. Sensitivity: add back the 5 rows excluded only for data-quality screening.
 9. Physics direction: does the model respond to inputs in physically sensible ways?

Writes model/artifacts/evaluation.json. Run: .venv/Scripts/python model/evaluate_models.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, mean_absolute_error, r2_score, roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ARTIFACTS, CLEAN, FEATURES, GROUP, NUMERIC, SEED, load_flex_training, preprocessor, to_jsonable  # noqa: E402

RNG = np.random.default_rng(SEED)
THR = joblib.load(ARTIFACTS / "extinction_model.joblib")["threshold"]  # deployed decision threshold


def lr(weight=None):  # deployed model: unweighted logistic regression
    return Pipeline([("prep", preprocessor()), ("model", LogisticRegression(class_weight=weight, max_iter=2000))])


def rf_reg():
    return Pipeline([("prep", preprocessor()), ("model", RandomForestRegressor(n_estimators=300, max_depth=6, min_samples_leaf=3, random_state=SEED))])


def oof_proba(model, X, y, g, seed=SEED, folds=None):
    folds = folds or list(StratifiedGroupKFold(5, shuffle=True, random_state=seed).split(X, y, g))
    p = np.zeros(len(y))
    for tr, te in folds:
        p[te] = clone(model).fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    return p


def oof_reg(model, X, y, g, seed=SEED):
    # GroupKFold has no shuffle; shuffle groups manually for repeated runs.
    uniq = np.unique(g)
    perm = np.random.default_rng(seed).permutation(len(uniq))
    fold_of = {grp: perm[i] % 5 for i, grp in enumerate(uniq)}
    f = np.array([fold_of[x] for x in g])
    p = np.zeros(len(y))
    for k in range(5):
        tr, te = f != k, f == k
        p[te] = clone(model).fit(X[tr], y[tr]).predict(X[te])
    return p


def best_threshold_bacc(y, p):
    ts = np.linspace(0.05, 0.95, 91)
    s = [balanced_accuracy_score(y, (p >= t).astype(int)) for t in ts]
    return float(ts[int(np.argmax(s))]), float(max(s))


def calibration_table(y, p, bins=5):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -0.01, 1.01
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p > lo) & (p <= hi)
        if m.sum():
            out.append({"predicted_mean": float(p[m].mean()), "observed_rate": float(y[m].mean()), "n": int(m.sum())})
    return out


def main():
    df = load_flex_training()
    X, g = df[FEATURES], df[GROUP].to_numpy()
    y = df["extinction_binary"].astype(int).to_numpy()
    rep = {}

    # 1. stability
    baccs, aucs = [], []
    for s in range(20):
        p = oof_proba(lr(), X, y, g, seed=s)
        baccs.append(balanced_accuracy_score(y, (p >= THR).astype(int)))
        aucs.append(roc_auc_score(y, p))
    rep["extinction_stability_20_shuffles"] = {"balanced_accuracy_mean": np.mean(baccs), "min": np.min(baccs), "max": np.max(baccs),
                                               "roc_auc_mean": np.mean(aucs), "roc_auc_min": np.min(aucs)}

    # 2. permutation test
    real = roc_auc_score(y, oof_proba(lr(), X, y, g))
    null = [roc_auc_score(yp, oof_proba(lr(), X, yp, g)) for yp in (RNG.permutation(y) for _ in range(200))]
    rep["extinction_permutation_test"] = {"real_auc": real, "shuffled_auc_mean": np.mean(null), "shuffled_auc_95th": np.percentile(null, 95),
                                          "p_value": (1 + sum(n >= real for n in null)) / (1 + len(null))}

    # 3. shortcut baseline: fuel only
    fuel_only = lr()
    Xf = X.copy()
    for c in NUMERIC:
        Xf[c] = 0.0
    pf = oof_proba(fuel_only, Xf, y, g)
    p_bal = oof_proba(lr(), X, y, g)
    rep["extinction_vs_fuel_only"] = {"full_model_bacc": balanced_accuracy_score(y, (p_bal >= THR).astype(int)), "full_model_auc": roc_auc_score(y, p_bal),
                                      "fuel_only_bacc": balanced_accuracy_score(y, (pf >= THR).astype(int)), "fuel_only_auc": roc_auc_score(y, pf)}

    # 4. per fuel
    rep["extinction_per_fuel"] = {}
    for fuel in ["Methanol", "Heptane"]:
        m = (df["fuel"] == fuel).to_numpy()
        rep["extinction_per_fuel"][fuel] = {"rows": int(m.sum()), "completions": int((y[m] == 0).sum()),
                                            "bacc": balanced_accuracy_score(y[m], (p_bal[m] >= THR).astype(int)),
                                            "auc": roc_auc_score(y[m], p_bal[m]) if len(set(y[m])) == 2 else None}

    # 5. calibration of balanced vs unweighted vs calibrated probabilities
    p_unw = oof_proba(lr(None), X, y, g)
    p_bal = oof_proba(lr("balanced"), X, y, g)
    cal = CalibratedClassifierCV(lr("balanced"), method="sigmoid", cv=3)
    p_cal = oof_proba(cal, X, y, g)
    t_unw, b_unw = best_threshold_bacc(y, p_unw)
    rep["extinction_calibration"] = {
        "observed_extinction_rate": float(y.mean()),
        "balanced_weights_old_model": {"brier": brier_score_loss(y, p_bal), "mean_prob": float(p_bal.mean()), "table": calibration_table(y, p_bal)},
        "unweighted": {"brier": brier_score_loss(y, p_unw), "mean_prob": float(p_unw.mean()), "auc": roc_auc_score(y, p_unw),
                       "table": calibration_table(y, p_unw)},
        "sigmoid_calibrated": {"brier": brier_score_loss(y, p_cal), "mean_prob": float(p_cal.mean()), "auc": roc_auc_score(y, p_cal),
                               "table": calibration_table(y, p_cal)},
        "prior_only_brier": brier_score_loss(y, np.full(len(y), y.mean())),
        "note": "Threshold-tuning on out-of-fold scores is optimistic; reported for reference only.",
        "unweighted_best_threshold": {"threshold": t_unw, "bacc": b_unw},
    }

    # 6. learning curve (repeat each fraction 10 times, test on held-out folds)
    lc = []
    for frac in [0.3, 0.5, 0.7, 0.85, 1.0]:
        scores = []
        for s in range(10):
            folds = list(StratifiedGroupKFold(5, shuffle=True, random_state=s).split(X, y, g))
            p = np.full(len(y), np.nan)
            for tr, te in folds:
                rng = np.random.default_rng(s)
                sub = rng.choice(tr, max(20, int(len(tr) * frac)), replace=False)
                if len(set(y[sub])) < 2:
                    continue
                p[te] = clone(lr()).fit(X.iloc[sub], y[sub]).predict_proba(X.iloc[te])[:, 1]
            ok = ~np.isnan(p)
            scores.append(roc_auc_score(y[ok], p[ok]))
        lc.append({"fraction_of_training_rows": frac, "roc_auc_mean": np.mean(scores), "roc_auc_sd": np.std(scores)})
    rep["extinction_learning_curve"] = lc

    # 7. new atmospheres: hold out all CO2-diluted or all helium tests
    rep["extinction_new_atmosphere"] = {}
    for name, mask in [("all_co2_tests", df["co2_fraction"] > 0), ("all_helium_tests", df["helium_fraction"] > 0)]:
        m = mask.to_numpy()
        model = clone(lr()).fit(X[~m], y[~m])
        p = model.predict_proba(X[m])[:, 1]
        rep["extinction_new_atmosphere"][name] = {"held_out_rows": int(m.sum()), "completions": int((y[m] == 0).sum()),
                                                  "bacc": balanced_accuracy_score(y[m], (p >= THR).astype(int)) if len(set(y[m])) == 2 else None,
                                                  "auc": roc_auc_score(y[m], p) if len(set(y[m])) == 2 else None,
                                                  "accuracy": float(((p >= THR).astype(int) == y[m]).mean())}

    # 8. sensitivity: add back the quality-screened rows (sum 0.98 gas, zero pressure) that still have an ending + features
    lab = pd.read_csv(CLEAN / "flex_labeled.csv")
    for c in NUMERIC + ["extinction_binary", "burn_time_s"]:
        lab[c] = pd.to_numeric(lab[c], errors="coerce")
    extra = lab[(lab["training_eligible"].astype(str).str.lower() != "true") & lab["extinction_binary"].notna()
                & lab[FEATURES].notna().all(axis=1) & (lab["pressure_kpa"] > 0)]
    big = pd.concat([df, extra[df.columns.intersection(extra.columns)]], ignore_index=True)
    yb = big["extinction_binary"].astype(int).to_numpy()
    pb = oof_proba(lr(), big[FEATURES], yb, big[GROUP].to_numpy())
    rep["extinction_with_screened_rows"] = {"added_rows": len(extra), "rows": len(big),
                                            "bacc": balanced_accuracy_score(yb, (pb >= THR).astype(int)), "auc": roc_auc_score(yb, pb)}

    # 9. physics direction (extinction): bigger droplets should favour radiative extinction in FLEX
    model = clone(lr()).fit(X, y)
    def sweep(feat, fuel):
        base = df[df["fuel"] == fuel][FEATURES].median(numeric_only=True).to_dict()
        lo, hi = df[df["fuel"] == fuel][feat].quantile([0.1, 0.9])
        out = []
        for v in (lo, hi):
            row = {**base, "fuel": fuel, feat: v}
            out.append(float(model.predict_proba(pd.DataFrame([row])[FEATURES])[0, 1]))
        return {"low_value": float(lo), "high_value": float(hi), "p_low": out[0], "p_high": out[1]}
    rep["extinction_directions"] = {f"{feat}|{fuel}": sweep(feat, fuel) for feat in NUMERIC for fuel in ["Methanol", "Heptane"]}

    # ---------------- burn time
    d = df[df["burn_time_s"].notna()].reset_index(drop=True)
    Xb, gb = d[FEATURES], d[GROUP].to_numpy()
    yb_s = d["burn_time_s"].to_numpy()
    ylog = np.log1p(yb_s)
    r2s, maes = [], []
    for s in range(20):
        p = np.expm1(oof_reg(rf_reg(), Xb, ylog, gb, seed=s))
        r2s.append(r2_score(yb_s, p)); maes.append(mean_absolute_error(yb_s, p))
    rep["burn_time_stability_20_shuffles"] = {"r2_mean": np.mean(r2s), "r2_min": np.min(r2s), "r2_max": np.max(r2s), "mae_mean_s": np.mean(maes)}

    # d² law physics baseline: burn_time ≈ k_fuel * D0²  (log t = a_fuel + 2 log D)
    phys_X = pd.DataFrame({"logD": np.log(d["droplet_diameter_mm"]), "meth": (d["fuel"] == "Methanol").astype(float)})
    p_phys = np.expm1(0) + np.exp(oof_reg(LinearRegression(), phys_X, np.log(yb_s), gb)) - 0  # predicted seconds
    p_full = np.expm1(oof_reg(rf_reg(), Xb, ylog, gb))
    rep["burn_time_vs_d2_law"] = {"rf_r2": r2_score(yb_s, p_full), "rf_mae_s": mean_absolute_error(yb_s, p_full),
                                  "d2_law_r2": r2_score(yb_s, p_phys), "d2_law_mae_s": mean_absolute_error(yb_s, p_phys)}
    rep["burn_time_per_fuel"] = {fuel: {"rows": int((d["fuel"] == fuel).sum()),
                                        "r2": r2_score(yb_s[(d["fuel"] == fuel).to_numpy()], p_full[(d["fuel"] == fuel).to_numpy()]),
                                        "mae_s": mean_absolute_error(yb_s[(d["fuel"] == fuel).to_numpy()], p_full[(d["fuel"] == fuel).to_numpy()])}
                                 for fuel in ["Methanol", "Heptane"]}
    rep["burn_time_new_atmosphere"] = {}
    for name, mask in [("all_co2_tests", d["co2_fraction"] > 0), ("all_helium_tests", d["helium_fraction"] > 0)]:
        m = mask.to_numpy()
        p = np.expm1(clone(rf_reg()).fit(Xb[~m], ylog[~m]).predict(Xb[m]))
        rep["burn_time_new_atmosphere"][name] = {"held_out_rows": int(m.sum()), "r2": r2_score(yb_s[m], p), "mae_s": mean_absolute_error(yb_s[m], p)}

    (ARTIFACTS / "evaluation.json").write_text(json.dumps(to_jsonable(rep), indent=2) + "\n")
    print(json.dumps(to_jsonable(rep), indent=1))


if __name__ == "__main__":
    main()
