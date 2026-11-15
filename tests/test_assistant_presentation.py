"""The chat answer stays readable even when tools return technical tables."""
import sys
import unittest

from streamlit.testing.v1 import AppTest

from firesafe import ROOT, tools

sys.path.insert(0, str(ROOT / "app"))


class AssistantPresentationTests(unittest.TestCase):
    def render(self, text, calls):
        app = AppTest.from_file(str(ROOT / "app/pages/assistant.py"))
        app.session_state["chat_view"] = [{"role": "assistant", "text": text, "calls": calls}]
        app.run(timeout=30)
        self.assertFalse(app.exception)
        return app

    def test_sql_results_do_not_automatically_render_internal_columns(self):
        app = self.render("**Answer**\nPMMA has the most tests.", [
            ("query_database", {}, {"rows": [{"source_record": "PSI-25", "burned_binary": 1}],
                                    "returned": 1, "truncated": False})])
        self.assertFalse(app.dataframe)
        self.assertNotIn("burned_binary", " ".join(x.value for x in app.markdown))

    def test_chart_and_evidence_are_collapsed_with_standalone_main_answer(self):
        result = tools.run_tool("predict_sustained_burning", {"material": "PMMA", "oxygen_pct": 21,
                                                              "airflow_cm_s": 10})
        app = self.render("**Answer**\nThe model estimates an 87% chance; confidence is low.\n\n"
                          "**Prediction reliability**\nOnly a small number of tests were available.",
                          [("predict_sustained_burning", {}, result)])
        expanders = {x.label: x for x in app.expander}
        self.assertEqual(set(expanders), {"Charts", "Answer details", "Sources"})
        self.assertTrue(all(not e.proto.expanded for e in expanders.values()))

    def test_unsupported_forecast_has_no_chart_or_percentage_metric(self):
        result = tools.run_tool("predict_sustained_burning", {"material": "PMMA", "oxygen_pct": 21,
                                                              "airflow_cm_s": 10, "pressure_kpa": 0.6})
        app = self.render("**Answer**\nThere are no matching low-pressure tests.",
                          [("predict_sustained_burning", {}, result)])
        self.assertNotIn("Charts", [x.label for x in app.expander])
        self.assertFalse(app.metric)


if __name__ == "__main__":
    unittest.main()
