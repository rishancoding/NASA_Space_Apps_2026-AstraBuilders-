"""Regressions for unsupported forecasts, review metadata and chat recovery."""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx

from firesafe import ROOT, agent, predictor, tools


class ForecastBoundaryTests(unittest.TestCase):
    def test_unsupported_solid_inputs_do_not_reach_chat_as_percentages(self):
        for inputs in ({"oxygen_pct": 35, "airflow_cm_s": 80},
                       {"oxygen_pct": 21, "airflow_cm_s": 10, "pressure_kpa": 0.6},
                       {"oxygen_pct": 21, "airflow_cm_s": 10, "mission": "Mars habitat (3/8 g)"}):
            with self.subTest(inputs=inputs):
                result = tools.predict_sustained_burning("PMMA", **inputs)
                self.assertFalse(result["supported"])
                self.assertIsNone(result["probability"])
                self.assertNotIn("predicted_outcome", result)
                self.assertEqual(result["reliability"]["rating"], "low")

    def test_unknown_setting_is_not_silently_treated_as_microgravity(self):
        result = tools.predict_sustained_burning("PMMA", 21, 10, mission="Invented setting")
        self.assertIn("error", result)

    def test_supported_prediction_preserves_model_value(self):
        expected = predictor.predict_solid("PMMA", 21, 10)
        actual = tools.predict_sustained_burning("PMMA", 21, 10)
        self.assertEqual(actual["probability"], expected["probability"])
        self.assertTrue(actual["supported"])

    def test_unsupported_droplets_and_sweep_points_are_withheld(self):
        result = tools.predict_droplet_extinction("Heptane", 0.6, 21)
        self.assertIsNone(result["probability"])
        sweep = tools.prediction_sweep("solid", "oxygen_pct", 21, 35, steps=3, material="PMMA")
        self.assertIsNotNone(sweep["points"][0]["probability"])
        self.assertIsNone(sweep["points"][-1]["probability"])
        self.assertEqual(sweep["probability_range"], [sweep["points"][0]["probability"]] * 2)

    def test_advisor_chat_does_not_leak_out_of_domain_probabilities(self):
        result = tools.run_material_advisor(oxygen_pct=35, airflow_cm_s=80)
        for row in result["ranked_candidates"] + result["excluded"]:
            self.assertIsNone(row["model_probability_sustained"])

    def test_observed_materials_are_not_all_advertised_as_predictable(self):
        materials = {m["material"]: m for m in tools.list_materials()["materials"]}
        self.assertTrue(materials["PMMA"]["supports_burn_prediction"])
        self.assertFalse(materials["Silicone"]["supports_burn_prediction"])


class ReviewMetadataTests(unittest.TestCase):
    def test_team_verification_is_consistent_in_prompt_schema_and_metrics(self):
        for text in (agent.system_prompt(), json.dumps(tools.model_performance("solid")),
                     (ROOT / "data/clean/labeling_report.json").read_text()):
            self.assertNotIn("no human sign-off", text)
            self.assertNotIn("AI-reviewed", text)
        self.assertIn("project team", agent.SYSTEM_RULES)
        self.assertIn("Project-team-verified", tools.model_performance("solid")["label_provenance"])

    def test_generated_status_matches_verified_annotations(self):
        import csv
        for name, field in (("solid_stage_training.csv", "review_status"),
                            ("solid_combustion_model.csv", "label_status")):
            with (ROOT / "data/clean" / name).open(encoding="utf-8", newline="") as f:
                statuses = {row[field] for row in csv.DictReader(f)}
            self.assertLessEqual(statuses, {"team_verified", "reviewed_unresolved"})


class ConversationRecoveryTests(unittest.TestCase):
    def test_provider_failure_hides_diagnostics_and_cleans_partial_tool_chain(self):
        tool_turn = SimpleNamespace(stop_reason="tool_use", content=[
            SimpleNamespace(type="tool_use", id="tu_1", name="list_materials", input={})])
        response = httpx.Response(503, request=httpx.Request("POST", "https://example.com"))
        failure = anthropic.APIStatusError("internal provider diagnostic", response=response, body=None)
        final = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Recovered.")])
        client = mock.MagicMock()
        client.messages.create.side_effect = [tool_turn, failure, final]
        messages = [{"role": "user", "content": "Compare materials"}]
        with mock.patch.object(agent, "_client", return_value=client):
            result = agent.ask(messages)
            self.assertNotIn("diagnostic", result["text"])
            self.assertNotIn("503", result["text"])
            self.assertEqual(result["tool_calls"], [])
            self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
            messages.append({"role": "user", "content": "Try again"})
            self.assertEqual(agent.ask(messages)["text"], "Recovered.")

    def test_tool_limit_leaves_a_valid_history_and_plain_language_response(self):
        tool_turn = SimpleNamespace(stop_reason="tool_use", content=[
            SimpleNamespace(type="tool_use", id="tu_1", name="list_materials", input={})])
        client = mock.MagicMock()
        client.messages.create.return_value = tool_turn
        messages = [{"role": "user", "content": "Compare materials"}]
        with mock.patch.object(agent, "_client", return_value=client), mock.patch.object(agent, "MAX_TOOL_ROUNDS", 1):
            result = agent.ask(messages)
        self.assertEqual(result["stop_reason"], "tool_limit")
        self.assertNotIn("tool", result["text"])
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])


if __name__ == "__main__":
    unittest.main()
