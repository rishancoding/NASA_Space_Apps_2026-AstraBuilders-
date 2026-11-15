"""Offline end-to-end assistant/tool checks; no provider calls or keys required."""
import json
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from api import agent, core
from api.main import app

client = TestClient(app)


def test_tool_catalogue_and_status_do_not_advertise_a_provider_without_a_key(monkeypatch):
    for key in ["DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CHAT_PROVIDER", "deepseek")
    assert client.get("/api/health").json()["chat_configured"] is False
    assert {t["name"] for t in client.get("/api/tools").json()["tools"]} == set(agent._DISPATCH)


def test_real_data_tools_provide_evidence_and_decline_unsupported_claims():
    text, error, citations = agent.run_tool("search_evidence", {"q": "BASS flame spread", "k": 2})
    results = json.loads(text)["results"]
    assert not error and results and citations
    assert all(r["source_record"] and r["locator"] for r in results)
    text, error, _ = agent.run_tool("advisor", {"oxygen_pct": 21, "mission": "moon_base"})
    assert not error and any(w["code"] == "partial_gravity" for w in json.loads(text)["warnings"])
    text, error, _ = agent.run_tool("predict_extinction", {"fuel": "Methanol", "oxygen_pct": 34,
        "pressure_kpa": 309.26789803, "helium_fraction": .45, "droplet_diameter_mm": 4.53})
    assert not error and json.loads(text)["available"] is False
    assert "probability_extinction" not in json.loads(text)


def test_bad_tool_arguments_return_a_recoverable_tool_error():
    for tool, args in [("unknown_tool", {}), ("advisor", {"nonexistent": 1}),
                       ("predict_extinction", {"fuel": "Methanol", "oxygen_pct": 21, "pressure_kpa": 101.3,
                                               "co2_fraction": .7, "helium_fraction": .45})]:
        text, error, _ = agent.run_tool(tool, args)
        assert error and "error" in json.loads(text)


def test_multi_tool_loop_preserves_citations_and_recovers_from_invalid_json():
    calls = [NS(id="bad", function=NS(name="advisor", arguments="[1]")),
             NS(id="evidence", function=NS(name="search_evidence", arguments=json.dumps({"q": "BASS flame spread", "k": 2})))]
    fake = MagicMock()
    fake.chat.completions.create.side_effect = [
        NS(choices=[NS(message=NS(content="", tool_calls=calls), finish_reason="tool_calls")]),
        NS(choices=[NS(message=NS(content="Evidence found [PSI-26].", tool_calls=[]), finish_reason="stop")])]
    r = agent._chat_deepseek([{"role": "user", "content": "Show the source."}], client=fake)
    assert r["tool_calls"][0]["error"] and not r["tool_calls"][1]["error"]
    assert r["citations"] and all(c["url"].startswith("https://") for c in r["citations"])
    messages = fake.chat.completions.create.call_args.kwargs["messages"]
    assert {m["tool_call_id"] for m in messages if m["role"] == "tool"} == {"bad", "evidence"}


@pytest.mark.parametrize("code,exception", [(401, openai.AuthenticationError), (429, openai.RateLimitError), (503, openai.APIStatusError)])
def test_provider_failures_are_clear_503_responses_without_private_diagnostics(monkeypatch, code, exception):
    monkeypatch.setattr('api.main.reserve_chat', lambda request: None)
    fake = MagicMock()
    response = httpx.Response(code, request=httpx.Request("POST", "https://example.com"))
    fake.chat.completions.create.side_effect = exception("private diagnostic", response=response, body=None)
    monkeypatch.setattr(agent, "provider", lambda: "deepseek")
    monkeypatch.setattr(agent, "_deepseek_client", lambda: fake)
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Show NASA evidence"}]})
    assert r.status_code == 503 and "private diagnostic" not in r.text


def test_interactive_docs_assets_are_local_and_unchanged():
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "static" / "swagger-ui"
    manifest = json.loads((root / "manifest.json").read_text())
    html = client.get("/docs").text
    assert 'src="/api/docs-assets/swagger-ui-bundle.js"' in html
    assert 'href="/api/docs-assets/swagger-ui.css"' in html
    assert '"validatorUrl": null' in html
    for name, expected in manifest["sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    for name in ["swagger-ui-bundle.js", "swagger-ui.css", "favicon-32x32.png"]:
        response = client.get("/api/docs-assets/" + name)
        assert response.status_code == 200 and response.content
    assert "/api/tools" in client.get("/openapi.json").json()["paths"]
