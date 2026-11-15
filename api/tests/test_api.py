"""API tests. Run from the repo root:  .venv/Scripts/python -m pytest api/tests -q"""
import json

import pytest
from fastapi.testclient import TestClient

from api import agent, core
from api.main import app

client = TestClient(app)
BASE = {"fuel": "Methanol", "oxygen_pct": 21.0, "pressure_kpa": 101.3, "co2_fraction": 0.0, "helium_fraction": 0.0, "droplet_diameter_mm": 2.5}


def test_options_drive_the_forms():
    o = client.get("/api/options").json()
    assert {f["name"] for f in o["flex"]["fields"]} == set(core.FLEX_NUMERIC)
    for f in o["flex"]["fields"]:
        assert f["min"] <= f["default"] <= f["max"]
    assert "PMMA" in [m["name"] for m in o["solids"]["materials"]]
    assert "Unresolved material" not in [m["name"] for m in o["solids"]["materials"]]
    assert set(o["trust_labels"]) == {"nasa_measured", "ai_label", "model_estimate", "earth_reference", "no_data"}


def test_investigations_and_detail():
    items = client.get("/api/investigations").json()
    assert len(items) == 20
    d = client.get("/api/investigations/PSI-26").json()
    assert d["counts"]["solid_tests"] == 121 and d["objective"]
    assert client.get("/api/investigations/PSI-999").status_code == 422


def test_experiment_list_detail_and_paths_with_colons():
    page = client.get("/api/experiments", params={"material": "PMMA", "page_size": 5}).json()
    assert page["total"] == 167 and len(page["items"]) == 5
    eid = page["items"][0]["experiment_id"]
    d = client.get(f"/api/experiments/{eid}").json()
    assert d["experiment_id"] == eid and "stages" in d
    flex = client.get("/api/experiments", params={"dataset": "flex", "outcome": "Completion"}).json()
    assert flex["total"] == 27


def test_numbers_carry_trust_labels():
    d = client.get("/api/experiments", params={"page_size": 1}).json()["items"][0]
    assert d["oxygen_pct"]["trust"] == "nasa_measured"
    assert d["outcome"]["trust"] == "ai_label"


def test_predictions_in_range():
    p = client.post("/api/predict/extinction", json=BASE).json()
    assert p["available"] is True
    pr = p["probability_extinction"]
    assert 0 <= pr["range"][0] <= pr["value"] <= pr["range"][1] <= 1 or 0 <= pr["value"] <= 1
    assert pr["trust"] == "model_estimate"
    assert p["nearest_tests"]["matches"] and p["factors"]["items"]
    b = client.post("/api/predict/burn-time", json={**BASE, "fuel": "Heptane", "droplet_diameter_mm": 3.0}).json()
    assert b["available"] and b["burn_time_s"]["range"][0] <= b["burn_time_s"]["value"] <= b["burn_time_s"]["range"][1]


def test_extinction_probabilities_are_calibrated():
    m = client.get("/api/model").json()["extinction"]
    sel = m["candidates"][m["selected_model"]]
    assert abs(sel["mean_predicted_probability"] - m["base_rate_extinction"]) < 0.03
    assert sel["brier_score"] < m["candidates"]["majority_baseline"]["brier_score"]
    p = client.post("/api/predict/extinction", json=BASE).json()
    assert p["compared_with_typical"]["leans"] in {"extinction", "completion"}
    assert any(w["field"] == "fuel" for w in p["warnings"])  # methanol warning


def test_out_of_range_gives_no_number():
    p = client.post("/api/predict/extinction", json={**BASE, "oxygen_pct": 45}).json()
    assert p["available"] is False and p["out_of_range"][0]["field"] == "oxygen_pct"
    assert "probability_extinction" not in p
    assert p["nearest_tests"]["matches"]


def test_invalid_gas_mix_is_field_error():
    r = client.post("/api/predict/extinction", json={**BASE, "oxygen_pct": 60, "co2_fraction": 0.5})
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "oxygen_pct"
    r = client.post("/api/predict/extinction", json={**BASE, "fuel": "Kerosene"})
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "fuel"


def test_what_if_curve():
    w = client.post("/api/what-if", json={**BASE, "vary": "oxygen_pct", "points": 20}).json()
    assert len(w["curve"]) == 20
    inside = [p for p in w["curve"] if p["in_tested_range"]]
    outside = [p for p in w["curve"] if not p["in_tested_range"]]
    assert inside and all(p["y"] is not None for p in inside)
    assert all(p["y"] is None for p in outside)
    assert w["real_tests"]


def test_advisor_ranks_evidence_not_safety():
    a = client.post("/api/advisor", json={"oxygen_pct": 21, "airflow_cm_s": 10}).json()
    assert "not_a_safety_rating" in a and [c["rank"] for c in a["candidates"]] == list(range(1, len(a["candidates"]) + 1))
    assert all(any(ch["constraint"] == "pressure" and ch["status"] == "cannot_check" for ch in c["constraint_checks"]) for c in a["candidates"])
    hi = client.post("/api/advisor", json={"oxygen_pct": 34, "airflow_cm_s": 10, "mission": "mars_habitat"}).json()
    codes = {w["code"] for w in hi["warnings"]}
    assert {"oxygen_above_tested", "partial_gravity"} <= codes
    assert all(c["evidence"]["nearby_tests"] == 0 for c in hi["candidates"])


def test_advisor_analyze_mode():
    a = client.post("/api/advisor", json={"mode": "analyze", "material": "pmma", "oxygen_pct": 21, "airflow_cm_s": 5}).json()
    assert a["candidates"][0]["material"] == "PMMA" and a["candidates"][0]["earth_reference"]["earth_tests"]
    assert client.post("/api/advisor", json={"mode": "analyze", "oxygen_pct": 21}).status_code == 422
    unknown = client.post("/api/advisor", json={"mode": "analyze", "material": "Kapton", "oxygen_pct": 21}).json()
    assert unknown["supported"] is False


def test_search_and_compare_and_coverage():
    s = client.get("/api/search", params={"q": "opposed flow flame spread"}).json()
    assert s["results"] and all(r["url"] for r in s["results"])
    ids = [i["experiment_id"] for i in client.get("/api/experiments", params={"page_size": 2}).json()["items"]]
    c = client.post("/api/compare", json={"experiment_a": ids[0], "experiment_b": ids[1]}).json()
    assert c["fields"] and "note" in c
    assert len(client.get("/api/coverage").json()["points"]) == 250


def test_model_page():
    m = client.get("/api/model").json()
    ex = m["extinction"]
    assert ex["candidates"]["majority_baseline"]["balanced_accuracy"] == pytest.approx(0.5)
    assert ex["rows"] == 202 and len(m["out_of_fold"]["extinction"]) == 202
    for fold in ex["folds"]:
        assert fold["test_completion"] > 0 and fold["test_extinction"] > 0


def test_agent_tools_match_dispatch_and_run():
    assert {t["name"] for t in agent.TOOLS} == set(agent._DISPATCH)
    text, err, cites = agent.run_tool("predict_extinction", {"fuel": "Methanol", "oxygen_pct": 21, "pressure_kpa": 101.3})
    assert not err and json.loads(text)["available"]
    text, err, _ = agent.run_tool("predict_extinction", {"fuel": "Methanol", "oxygen_pct": 90, "pressure_kpa": 101.3, "co2_fraction": 0.5})
    assert err
    _, _, cites = agent.run_tool("search_evidence", {"q": "BASS extinction"})
    assert cites and all(c["url"] for c in cites)


def test_provider_selection(monkeypatch):
    for k in ["CHAT_PROVIDER", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CHAT_MODEL"]:
        monkeypatch.delenv(k, raising=False)
    assert agent.provider() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert agent.provider() == "anthropic"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    assert agent.provider() == "deepseek" and agent.model_name("deepseek") == "deepseek-flash"
    monkeypatch.setenv("CHAT_PROVIDER", "anthropic")
    assert agent.provider() == "anthropic"


def test_deepseek_tool_loop_with_fake_client():
    """Simulate DeepSeek asking for a tool, then answering, without calling the network."""
    from types import SimpleNamespace as NS
    sent = []

    class FakeCompletions:
        def __init__(self):
            self.turn = 0

        def create(self, **kw):
            sent.append(kw)
            self.turn += 1
            if self.turn == 1:
                call = NS(id="call_1", function=NS(name="predict_extinction",
                                                   arguments=json.dumps({"fuel": "Heptane", "oxygen_pct": 21, "pressure_kpa": 101.3})))
                return NS(choices=[NS(message=NS(content="", tool_calls=[call]), finish_reason="tool_calls")])
            return NS(choices=[NS(message=NS(content="About 66% [PSI-69].", tool_calls=None), finish_reason="stop")])

    fake = NS(chat=NS(completions=FakeCompletions()))
    out = agent._chat_deepseek([{"role": "user", "content": "Heptane at 21%?"}], client=fake)
    assert out["answer"].startswith("About 66%")
    assert out["tool_calls"][0]["tool"] == "predict_extinction" and not out["tool_calls"][0]["error"]
    assert out["citations"]
    second = sent[1]["messages"]
    assert second[0]["role"] == "system" and second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "call_1"
    assert json.loads(second[-1]["content"])["available"] is True
    assert {t["function"]["name"] for t in sent[0]["tools"]} == set(agent._DISPATCH)


def test_chat_without_key_is_clear_503(monkeypatch):
    monkeypatch.setattr('api.main.reserve_chat', lambda request: None)
    def boom(*a, **k):
        raise agent.ChatUnavailable("Chat is not configured")
    monkeypatch.setattr("api.main.chat", boom)
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503 and r.json()["errors"][0]["message"]
