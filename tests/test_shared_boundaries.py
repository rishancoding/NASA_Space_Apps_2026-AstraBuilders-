"""The archived app must not bypass the official data-domain checks."""
import pytest
import sys
from streamlit.testing.v1 import AppTest
from api import core
from firesafe import predictor, tools, ROOT

sys.path.insert(0, str(ROOT / "app"))

BASE = dict(fuel="Methanol", pressure_kpa=101.3, oxygen_pct=21.,
            co2_fraction=0., helium_fraction=0., droplet_diameter_mm=2.5)


@pytest.mark.parametrize("changes", [
    {"co2_fraction": .7, "helium_fraction": .45},  # impossible mixture
    {"oxygen_pct": 34., "pressure_kpa": 309.26789803, "helium_fraction": .45, "droplet_diameter_mm": 4.53},
    {"pressure_kpa": 0.}, {"droplet_diameter_mm": -1.}, {"co2_fraction": float("nan")},
])
def test_no_streamlit_number_for_invalid_or_unsupported_combinations(changes):
    inputs = {**BASE, **changes}
    r = predictor.predict_flex(**inputs)
    assert not r["supported"] and r["probability"] is None and r["warnings"]
    result = tools.predict_droplet_extinction(**inputs)
    assert result["probability"] is None and "predicted_outcome" not in result
    try:
        _, _, reason = core.check_flex_domain(inputs)
    except core.InputError:
        pass
    else:
        assert reason is not None


def test_supported_domain_is_preserved_and_repeat_sweeps_have_gaps():
    assert predictor.predict_flex(**BASE)["supported"]
    r = tools.prediction_sweep("flex", "pressure_kpa", 0, 101.3, steps=3, fuel="Methanol", droplet_diameter_mm=2.5)
    assert len(r["points"]) == 3
    assert r["points"][0]["probability"] is None
    assert r["points"][-1]["probability"] is not None


def test_archived_predictor_does_not_crash_when_probability_is_withheld():
    app = AppTest.from_file(str(ROOT / "app/pages/predictor.py")).run(timeout=30)
    next(box for box in app.selectbox if box.label == "Mission").select("Moon base (1/6 g)")
    next(slider for slider in app.slider if slider.label == "CO₂ in the air (%)").set_value(70.)
    next(slider for slider in app.slider if slider.label == "Helium in the air (%)").set_value(45.)
    app.run(timeout=30)
    assert not app.exception
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Chance it keeps burning"] == "Unavailable"
    assert metrics["Probability of recorded Extinction"] == "Unavailable"
