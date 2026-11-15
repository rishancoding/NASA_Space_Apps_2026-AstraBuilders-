"""The /api/fs routes the React UI uses: same numbers as firesafe, and no estimates outside NASA's tested range."""
import json

from fastapi.testclient import TestClient

from api import firesafe_api
from api.main import app
from firesafe import predictor
from firesafe.advisor import Scenario, advise

client = TestClient(app)


def test_options_expose_tested_ranges_and_plain_scores():
    o = client.get("/api/fs/options").json()
    assert "missions" not in o
    assert o["solid"]["advisor_ranges"]["oxygen_pct"][0] >= 14
    assert set(o["flex"]["mixtures"]["Heptane"]) == {"air", "co2", "helium"}
    assert o["reliability"]["solid"]["material_only_accuracy"] > o["reliability"]["solid"]["baseline_accuracy"]


def test_advisor_lists_only_materials_with_an_estimate():
    r = client.post("/api/fs/advisor", json={}).json()
    shown = [c["material"] for c in r["selected"] + r["candidates"] + r["excluded"]]
    assert "Paraffin wax" not in shown and "Silicone" not in shown
    assert all(c["prediction"]["supported"] for c in r["candidates"])
    assert [c["rank"] for c in r["candidates"]] == list(range(1, len(r["candidates"]) + 1))
    direct = {c["material"]: c for c in advise(Scenario())["candidates"]}
    assert r["candidates"][0]["prediction"]["probability"] == direct[r["candidates"][0]["material"]]["prediction"]["probability"]
    json.dumps(r, allow_nan=False)


def test_advisor_names_materials_untested_at_low_oxygen():
    r = client.post("/api/fs/advisor", json={"oxygen_pct": 16}).json()
    assert "Nomex" in r["not_tested_here"]
    assert "Nomex" not in [c["material"] for c in r["candidates"]]


def test_solid_prediction_inside_range_only():
    r = client.post("/api/fs/predict/solid", json={"material": "PMMA", "oxygen_pct": 21, "airflow_cm_s": 10}).json()
    assert r["probability"] == predictor.predict_solid("PMMA", 21, 10, "ongoing_burn_trial")["probability"]
    lo, hi = predictor.metrics()["solid"]["ranges"]["PMMA"]["oxygen_pct"]
    assert lo <= min(p["x"] for p in r["curve"]) and max(p["x"] for p in r["curve"]) <= hi
    bad = client.post("/api/fs/predict/solid", json={"material": "PMMA", "oxygen_pct": 30, "airflow_cm_s": 10})
    assert bad.status_code == 422
    assert client.post("/api/fs/predict/solid", json={"material": "Nomex", "protocol": "ongoing_burn_trial",
                                                     "oxygen_pct": 21.5, "airflow_cm_s": 10}).status_code == 422


def test_flex_prediction_rejects_untested_mixtures():
    ok = client.post("/api/fs/predict/flex", json={"fuel": "Heptane", "oxygen_pct": 21, "droplet_diameter_mm": 3,
                                                   "pressure_kpa": 101}).json()
    assert 0 <= ok["probability"] <= 1
    both = {"fuel": "Heptane", "oxygen_pct": 21, "droplet_diameter_mm": 3, "pressure_kpa": 101,
            "co2_fraction": 0.2, "helium_fraction": 0.2}
    assert client.post("/api/fs/predict/flex", json=both).status_code == 422
    high = {"fuel": "Heptane", "oxygen_pct": 30, "droplet_diameter_mm": 3, "pressure_kpa": 101, "co2_fraction": 0.2}
    assert client.post("/api/fs/predict/flex", json=high).status_code == 422   # CO2 was only tested up to 24% oxygen


def test_explorer_routes():
    cat = client.get("/api/fs/catalog").json()
    assert len(cat) == 19 and all(c["summary"] for c in cat)
    assert len(client.get("/api/fs/solids").json()) == 250
    flex = client.get("/api/fs/flex").json()
    assert len(flex) == 274 and {"Went out early", "Burned to the end"} <= {r["result"] for r in flex}


def test_chat_offline_falls_back_to_passages(monkeypatch):
    monkeypatch.setattr(firesafe_api.agent, "has_credentials", lambda: False)
    r = client.post("/api/fs/chat", json={"message": "flame spread in low oxygen"}).json()
    assert r["offline"] and r["session_id"] and r["tool_calls"][0]["name"] == "search_nasa_documents"
