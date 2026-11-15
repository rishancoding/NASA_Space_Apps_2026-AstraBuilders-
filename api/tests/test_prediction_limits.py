"""Regression tests for evidence limits shared by the UI, API and agent."""
import numpy as np
import pytest
from fastapi.testclient import TestClient
from api import core
from api.main import app

client = TestClient(app)
UNSUPPORTED = dict(fuel="Methanol", oxygen_pct=34, pressure_kpa=309.26789803,
                   co2_fraction=0, helium_fraction=.45, droplet_diameter_mm=4.53)


@pytest.mark.parametrize("endpoint,number", [("extinction", "probability_extinction"), ("burn-time", "burn_time_s")])
def test_joint_extrapolation_returns_evidence_without_an_estimate(endpoint, number):
    assert not core._validate_flex(UNSUPPORTED)["_outside"]  # individually inside the published bounds
    r = client.post(f"/api/predict/{endpoint}", json=UNSUPPORTED)
    assert r.status_code == 200
    data = r.json()
    assert not data["available"] and number not in data
    assert not data["nearest_tests"]["support"]["supported"]
    assert data["nearest_tests"]["matches"]


def test_repeat_burns_cannot_supply_three_independent_neighbours(monkeypatch):
    p = core._validate_flex(UNSUPPORTED)
    vector = np.array([p[f] for f in core.FLEX_NUMERIC])
    monkeypatch.setattr(core, "_flex_reference", lambda *a: (None, np.array([vector] * 3), np.array(["one-sample"] * 3), np.ones(5)))
    support = core._flex_support(p)
    assert support["nearby_groups"] == 1 and not support["supported"]


def test_each_fuel_and_mixture_has_supported_starting_tests_and_controls():
    scenarios = core.flex_scenarios()
    seen = set()
    for s in scenarios:
        assert core._flex_support(s["inputs"])["supported"]
        key = (s["inputs"]["fuel"], s["gas_family"])
        if key in seen:
            continue
        seen.add(key)
        controls = client.post("/api/predict/controls", json=s["inputs"])
        assert controls.status_code == 200
        for field in controls.json()["fields"]:
            assert field["values"]
            for value in field["values"]:  # includes discontinuities and fractional gas settings
                p = core._validate_flex({**s["inputs"], field["name"]: value})
                assert not p["_outside"] and core._flex_support(p)["supported"]
                assert core._gas_family(p) == s["gas_family"]
    assert len(seen) == 6


def test_what_if_does_not_fill_unsupported_gaps():
    data = client.post("/api/what-if", json={**UNSUPPORTED, "vary": "oxygen_pct", "points": 10}).json()
    assert any(not p["in_tested_range"] for p in data["curve"])
    assert all(p["y"] is None and p["low"] is None and p["high"] is None
               for p in data["curve"] if not p["in_tested_range"])


@pytest.mark.parametrize("protocol", ["ignition_trial", "ongoing_burn_trial"])
def test_advisor_geometry_protocol_and_source_events_agree(protocol):
    data = core.advisor(21, geometry="rod", protocol=protocol)
    source = {s["stage_id"]: s for s in core.stage_training()}
    for candidate in data["candidates"]:
        events = candidate["condition_linked_events_nearby"]
        assert events["protocol"] == protocol
        assert events["events"] == len(events["evidence"])
        assert all(source[e["stage_id"]]["sample_geometry"] == "rod"
                   and source[e["stage_id"]]["protocol"] == protocol for e in events["evidence"])
        assert all(t["geometry"] == "rod" for t in candidate["top_tests"])
    # Unknown or thicker dimensions cannot satisfy a numeric thickness constraint.
    filtered = core.advisor(21, geometry="rod", max_thickness_mm=0, protocol=protocol)
    assert all(not c["top_tests"] and c["condition_linked_events_nearby"]["events"] == 0 for c in filtered["candidates"])


def test_no_safety_rate_ranking_or_partial_gravity_bounds():
    assert client.post("/api/advisor", json={"oxygen_pct": 21, "priority": "fewest_sustained_flames"}).status_code == 422
    data = core.advisor(21, mission="moon_base")
    assert "unknown" in next(w["message"] for w in data["warnings"] if w["code"] == "partial_gravity").lower()
    assert "NASA recorded category" in core.OUTCOME_TEXT["Completion"]


def test_sequence_is_not_an_interpolated_airflow_interval():
    r = next(r for r in core.solids() if len(core.airflow_values().get(r["experiment_id"], [])) == 2
             and r["oxygen_pct"] is not None)
    a, b = sorted(core.airflow_values()[r["experiment_id"]])
    _, parts = core._solid_distance(r, r["oxygen_pct"], (a + b) / 2)
    assert parts["airflow_gap_cm_s"] > 0


@pytest.mark.parametrize("model", ["extinction", "burn_time"])
def test_batched_curve_matches_individual_supported_predictions(model):
    inputs = dict(fuel="Methanol", oxygen_pct=21., pressure_kpa=101.3,
                  co2_fraction=0., helium_fraction=0., droplet_diameter_mm=2.5)
    curve = core.what_if(model, "oxygen_pct", **inputs, points=9)
    fn = core.predict_extinction if model == "extinction" else core.predict_burn_time
    value_key = "probability_extinction" if model == "extinction" else "burn_time_s"
    compared = 0
    for point in curve["curve"]:
        if point["y"] is None:
            continue
        prediction = fn(**{**inputs, "oxygen_pct": point["x"]})
        assert prediction["available"]
        assert point["y"] == pytest.approx(prediction[value_key]["value"], abs=.001)
        compared += 1
    assert compared > 0
