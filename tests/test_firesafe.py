"""Backend checks for the FireSafe app (no network, no API key needed).

Run:  .venv/bin/python -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import csv  # noqa: E402
import sqlite3  # noqa: E402
import tempfile  # noqa: E402

from firesafe import CLEAN, advisor, agent, db, evidence, predictor, reliability, tools  # noqa: E402
from firesafe.data import materials, saffire, solids, solid_training  # noqa: E402


class AdvisorTests(unittest.TestCase):
    def test_discover_ranks_every_tested_material_once(self):
        res = advisor.advise(advisor.Scenario())
        names = [c["material"] for c in res["candidates"] + res["excluded"]]
        self.assertEqual(sorted(names), sorted(materials()))
        self.assertEqual([c["rank"] for c in res["candidates"]], list(range(1, len(res["candidates"]) + 1)))

    def test_analyze_keeps_selected_material_out_of_ranking(self):
        res = advisor.advise(advisor.Scenario(mode="analyze", material="PMMA"))
        self.assertEqual([c["material"] for c in res["selected"]], ["PMMA"])
        self.assertNotIn("PMMA", [c["material"] for c in res["candidates"]])

    def test_partial_gravity_and_mass_are_never_assessed(self):
        res = advisor.advise(advisor.Scenario(mission="Mars habitat (3/8 g)", max_mass_kg=2, budget=100))
        self.assertTrue({"Gravity", "Max mass", "Budget"} <= set(res["unassessable_constraints"]))
        for c in res["candidates"]:
            if c["prediction"]:
                self.assertTrue(any("gravity" in w.lower() for w in c["prediction"]["warnings"]))

    def test_no_supported_claim_across_different_test_scenarios(self):
        res = advisor.advise(advisor.Scenario(priority="sustained"))
        by = {c["material"]: c for c in res["candidates"]}
        for comp in res["comparisons"]:
            if comp["supported"]:
                self.assertEqual(by[comp["higher"]]["prediction_scenario"], by[comp["lower"]]["prediction_scenario"])

    def test_filters_exclude_untested_shape(self):
        res = advisor.advise(advisor.Scenario(geometry="candle", require_geometry=True))
        self.assertIn("PMMA", [c["material"] for c in res["excluded"]])

    def test_blank_saffire_material_is_not_attributed(self):
        self.assertTrue(all(r["material"] for r in saffire("SIBAL (cotton/fiberglass)")))
        self.assertIn(None, [r["material"] for r in saffire()])


class PredictorTests(unittest.TestCase):
    def test_metrics_are_out_of_fold_and_include_baseline(self):
        m = predictor.metrics()
        self.assertEqual(m["solid"]["n_observations"], 47)
        self.assertEqual(len(m["solid"]["oof"]), 47)
        self.assertTrue(m["solid"]["comparison"][0]["model"].startswith("Constant baseline"))

    def test_out_of_range_inputs_are_flagged(self):
        r = predictor.predict_solid("PMMA", 35, 80, pressure_kpa=56.5, gravity="lunar")
        self.assertFalse(r["supported"])
        self.assertGreaterEqual(len(r["warnings"]), 4)
        self.assertFalse(predictor.predict_solid("Silicone", 21, 10)["supported"])

    def test_probabilities_are_valid(self):
        for mat in predictor.solid_materials():
            row = solid_training().query("material == @mat").iloc[0]
            result = predictor.predict_solid(mat, float(row["oxygen_initial_pct"]), float(row["airflow_cm_s"]), row["protocol"])
            self.assertTrue(result["supported"])
            self.assertTrue(0 <= result["probability"] <= 1)
        self.assertIsNone(predictor.predict_solid("PMMA", 35, 80)["probability"])
        self.assertTrue(0 <= predictor.predict_flex("Heptane", 101, 21, 0, 0, 3)["probability"] <= 1)


class ToolAndEvidenceTests(unittest.TestCase):
    def test_every_tool_runs_and_serialises(self):
        ctx = advisor.advise(advisor.Scenario())
        args = {"material_summary": {"material": "Nomex"}, "find_tests": {"material": "PMMA", "limit": 3},
                "predict_sustained_burning": {"material": "PMMA", "oxygen_pct": 21, "airflow_cm_s": 10},
                "predict_droplet_extinction": {"fuel": "Methanol", "pressure_kpa": 101, "oxygen_pct": 21},
                "search_nasa_documents": {"query": "flame spread"}, "get_investigation": {"source_record": "PSI-25"},
                "run_material_advisor": {"oxygen_pct": 22},
                "prediction_sweep": {"model": "flex", "vary": "oxygen_pct", "start": 14, "stop": 30, "fuel": "Heptane",
                                     "pressure_kpa": 101},
                "describe_database": {"table": "flex_labeled"},
                "query_database": {"sql": "SELECT source_record, COUNT(*) AS n FROM solid_combustion_model GROUP BY 1"}}
        for t in tools.TOOLS:
            out = tools.run_tool(t["name"], args.get(t["name"], {}), ctx)
            self.assertNotIn("error", out, t["name"])
            self.assertIn("provenance", out, t["name"])
            json.loads(tools.to_json(out))

    def test_unknown_arguments_are_rejected(self):
        self.assertIn("error", tools.run_tool("find_tests", {"sql": "drop table"}))

    def test_find_tests_counts_match_table(self):
        out = tools.find_tests(material="PMMA", limit=1)
        self.assertEqual(out["matching_tests"], int((solids()["material"] == "PMMA").sum()))

    def test_plan_chunks_are_labelled(self):
        hits = evidence.search("test matrix planned tests", k=20)
        for h in hits:
            if h["kind"] == "experiment_plan_text":
                self.assertIn("PLAN", h["kind_label"])


def _csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.ensure()
        cls.con = sqlite3.connect(f"file:{db.DB_PATH}?mode=ro", uri=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_curated_tables_match_csvs_cell_for_cell(self):
        """Blank -> NULL (never 0), recorded zeros stay 0, numbers and text unchanged, same row order."""
        for table, (file, _, _) in db.CURATED.items():
            header, rows = _csv(CLEAN / file)
            got = self.con.execute(f'SELECT {", ".join(db._q(c) for c in header)} FROM "{table}" '
                                   "ORDER BY rowid").fetchall()
            self.assertEqual(len(got), len(rows), table)
            for raw, row in zip(rows, got):
                for col, v, g in zip(header, raw, row):
                    if v == "":
                        self.assertIsNone(g, f"{table}.{col}")
                    elif isinstance(g, (int, float)) and v.lower() not in ("true", "false"):
                        self.assertEqual(float(v), float(g), f"{table}.{col}")
                    elif v.lower() in ("true", "false"):
                        self.assertEqual(g, int(v.lower() == "true"), f"{table}.{col}")
                    else:
                        self.assertEqual(v, g, f"{table}.{col}")

    def test_zero_airflow_is_zero_not_null(self):
        header, rows = _csv(CLEAN / "solid_combustion_model.csv")
        i = header.index("airflow_cm_s")
        zeros, blanks = sum(r[i] != "" and float(r[i]) == 0 for r in rows), sum(r[i] == "" for r in rows)
        q = "SELECT SUM(airflow_cm_s = 0), SUM(airflow_cm_s IS NULL) FROM solid_combustion_model"
        self.assertEqual(self.con.execute(q).fetchone(), (zeros, blanks))

    def test_nasa_source_tables_are_verbatim(self):
        for e in db._source_tables():
            header, rows = _csv(CLEAN / e["file"])
            got = self.con.execute(f'SELECT * FROM "{e["table"]}" ORDER BY rowid').fetchall()
            self.assertEqual(len(got), e["row_count"], e["table"])
            for n, (raw, row) in enumerate(zip(rows, got)):
                self.assertEqual(row[0], n + 2)              # _source_row = CSV line, header = 1
                self.assertEqual(list(row[1:]), raw + [""] * (len(header) - len(raw)), e["table"])

    def test_every_table_has_provenance_metadata(self):
        for name, m in db.table_meta().items():
            self.assertTrue(m["source_file"] and m["grain"], name)
            if name not in ("investigation_catalog", "excluded_rows") and m["row_count"]:
                self.assertTrue(m["source_records"], name)

    def test_stale_database_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            path = db.build(Path(d) / "t.sqlite")
            self.assertTrue(db._current(path))
            con = sqlite3.connect(path)
            con.execute("UPDATE _meta SET value = 'old' WHERE key = 'fingerprint'")
            con.commit()
            con.close()
            self.assertFalse(db._current(path))

    def test_only_reads_are_allowed(self):
        before = self.con.execute("SELECT COUNT(*) FROM flex_labeled").fetchone()
        for sql in ["DELETE FROM flex_labeled", "DROP TABLE flex_labeled", "SELECT 1; DELETE FROM flex_labeled",
                    "WITH a AS (SELECT 1) DELETE FROM flex_labeled", "PRAGMA writable_schema = 1",
                    "ATTACH DATABASE ':memory:' AS x", "SELECT load_extension('x')",
                    "SELECT COUNT(*) FROM flex_labeled a, flex_labeled b, flex_labeled c, flex_labeled d"]:
            self.assertIn("error", tools.query_database(sql), sql)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM flex_labeled").fetchone(), before)

    def test_query_provenance_is_row_level_when_source_record_selected(self):
        out = tools.run_tool("query_database", {"sql": "SELECT source_record, COUNT(*) n FROM solid_combustion_model "
                                                       "WHERE source_record = 'PSI-25' GROUP BY 1"})
        prov = out["provenance"]
        self.assertEqual([i["source_record"] for i in prov["investigations"]], ["PSI-25"])
        self.assertIn("returned rows", prov["investigation_basis"])
        self.assertEqual(prov["datasets"][0]["file"], "data/clean/solid_combustion_model.csv")
        self.assertIn("SELECT", prov["sql"])
        out = tools.run_tool("query_database", {"sql": "SELECT COUNT(*) FROM solid_combustion_model"})
        self.assertEqual({i["source_record"] for i in out["provenance"]["investigations"]}, {"PSI-25", "PSI-26"})
        self.assertIn("tables used", out["provenance"]["investigation_basis"])

    def test_truncation_is_flagged(self):
        out = tools.query_database("SELECT * FROM airflow_readings", limit=5)
        self.assertEqual(out["returned"], 5)
        self.assertTrue(out["truncated"])


class ReliabilityTests(unittest.TestCase):
    def test_every_prediction_has_a_review_with_baselines(self):
        for name, args in [("predict_sustained_burning", {"material": "PMMA", "oxygen_pct": 21, "airflow_cm_s": 10}),
                           ("predict_droplet_extinction", {"fuel": "Heptane", "pressure_kpa": 101, "oxygen_pct": 21})]:
            out = tools.run_tool(name, args)
            rev = out["reliability"]
            self.assertIn(rev["rating"], ("low", "moderate", "higher"))
            self.assertEqual(len(rev["checks"]), 5)
            stats = rev["model_statistics"]
            self.assertTrue(stats["constant_baseline_out_of_fold"]["log_loss"])
            self.assertTrue(stats["simpler_model"]["log_loss"])
            self.assertTrue(out["nearest"])
            self.assertTrue(out["provenance"]["models"])

    def test_out_of_range_is_low_and_unknown_is_not_applicable(self):
        out = tools.predict_sustained_burning("PMMA", 35, 80)
        self.assertEqual(out["reliability"]["rating"], "low")
        self.assertFalse(out["reliability"]["checks"][0]["passed"])
        self.assertEqual(tools.predict_sustained_burning("Silicone", 21, 10)["reliability"]["rating"], "not applicable")

    def test_solid_model_is_never_rated_higher(self):
        for mat in predictor.solid_materials():
            for o2 in (16, 19, 21):
                rev = reliability.review("solid", predictor.predict_solid(mat, o2, 10), mat)
                self.assertNotEqual(rev["rating"], "higher")

    def test_sweep(self):
        out = tools.prediction_sweep("solid", "oxygen_pct", 15, 30, steps=4, material="PMMA")
        self.assertEqual(len(out["points"]), 4)
        self.assertFalse(out["points"][-1]["in_tested_range"])
        self.assertIn("error", tools.prediction_sweep("solid", "pressure_kpa", 50, 100, material="PMMA"))
        self.assertIn("error", tools.prediction_sweep("flex", "oxygen_pct", 15, 30))


class AgentLoopTests(unittest.TestCase):
    def test_system_prompt_requires_sources_and_reliability_and_has_schema(self):
        s = agent.system_prompt()
        for needle in ("**Sources**", "**Prediction reliability**", "solid_combustion_model", "src_psi_69_flex"):
            self.assertIn(needle, s)

    def test_tool_round_trip_with_fake_client(self):
        tool_turn = SimpleNamespace(stop_reason="tool_use", content=[
            SimpleNamespace(type="text", text="Looking."),
            SimpleNamespace(type="tool_use", id="tu_1", name="material_summary", input={"material": "Nomex"})])
        final = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="**Answer** ok")])
        fake = mock.MagicMock()
        fake.messages.create.side_effect = [tool_turn, final]
        msgs = [{"role": "user", "content": "Tell me about Nomex"}]
        with mock.patch.object(agent, "_client", return_value=fake):
            out = agent.ask(msgs)
        self.assertEqual(out["text"], "**Answer** ok")
        self.assertEqual(out["tool_calls"][0][0], "material_summary")
        # history: user, assistant(tool_use), user(tool_result), assistant(final)
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user", "assistant"])
        self.assertEqual(msgs[2]["content"][0]["tool_use_id"], "tu_1")
        kw = fake.messages.create.call_args.kwargs
        self.assertEqual(kw["model"], "deepseek-v4-pro")


if __name__ == "__main__":
    unittest.main()
