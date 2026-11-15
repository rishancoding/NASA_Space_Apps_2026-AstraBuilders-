"""Test partition isolation and the deployed calibration procedure, without retraining forests."""
import joblib
import numpy as np
import pytest
from model import train_flex as training


def test_repeat_groups_stay_together_in_three_partitions():
    df = training.load_flex_training().dropna(subset=["burn_time_s"]).reset_index(drop=True)
    partitions = training.regression_partitions(df)
    group_sets = [set(df.iloc[idx][training.GROUP]) for idx in partitions]
    assert sum(map(len, partitions)) == len(df)
    assert not group_sets[0] & group_sets[1]
    assert not group_sets[0] & group_sets[2]
    assert not group_sets[1] & group_sets[2]


def test_finite_sample_quantile_and_group_maximum():
    groups = np.array([str(i) for i in range(10)] + ["0"])
    residuals = np.r_[np.arange(10), 20]
    assert training.conformal_quantile(residuals, groups) == 20
    with pytest.raises(ValueError):
        training.conformal_quantile(np.array([1., 2.]), np.array(["a", "b"]))


def test_audit_and_calibration_labels_cannot_change_the_fitted_pipeline(tmp_path, monkeypatch):
    df = training.load_flex_training().dropna(subset=["burn_time_s"]).reset_index(drop=True)
    fit, cal, audit = training.regression_partitions(df)
    candidates = training.regressor_candidates()
    monkeypatch.setattr(training, "regressor_candidates", lambda: {k: candidates[k] for k in ["mean_baseline", "ridge"]})
    monkeypatch.setattr(training, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(training, "N_BOOT", 10)
    training.train_regressor(df, np.random.default_rng(42))
    original = joblib.load(tmp_path / "burn_time_model.joblib")
    expected = original["model"].predict(df[training.FEATURES])
    mutated = df.copy()
    mutated.loc[audit, "burn_time_s"] *= 10
    training.train_regressor(mutated, np.random.default_rng(42))
    changed_audit = joblib.load(tmp_path / "burn_time_model.joblib")
    np.testing.assert_allclose(changed_audit["model"].predict(df[training.FEATURES]), expected)
    assert changed_audit["conformal_q_log"] == original["conformal_q_log"]
    mutated.loc[cal, "burn_time_s"] *= 10
    training.train_regressor(mutated, np.random.default_rng(42))
    changed_cal = joblib.load(tmp_path / "burn_time_model.joblib")
    np.testing.assert_allclose(changed_cal["model"].predict(df[training.FEATURES]), expected)
    assert changed_cal["conformal_q_log"] != original["conformal_q_log"]
