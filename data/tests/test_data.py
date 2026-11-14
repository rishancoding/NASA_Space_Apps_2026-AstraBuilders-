"""Source reconciliation and unit/label regression checks; no network required."""
import csv
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / "scripts"))
from data.access import load_catalog, query_experiments, load_source_tables, load_evidence, load_quality_report
from build_data import scalar, dimensions
from fetch_sources import RECORDS


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = query_experiments()

    def test_complete_source_scope(self):
        self.assertEqual({r["source_record"] for r in load_catalog()}, set(RECORDS) | {"NTRS-20110008636"})
        for record in RECORDS:
            self.assertTrue(load_evidence(record), record)
            for table in load_source_tables(record):
                self.assertEqual(len(table["rows"]), table["row_count"])
                # Exact source values, header order, and every CSV row survive.
                raw = ROOT / "raw" / record / Path(table["file"]).name
                if raw.exists():
                    with raw.open(encoding=table["original_encoding"], newline="") as f:
                        self.assertEqual(table["rows"], list(csv.DictReader(f)))

    def test_counts_and_primary_isolation(self):
        self.assertEqual(len(self.rows), 250)
        self.assertEqual(len(query_experiments(source_record="PSI-26")), 121)
        self.assertEqual(len(query_experiments(source_record="PSI-25")), 129)
        self.assertEqual({r["source_record"] for r in self.rows}, {"PSI-25", "PSI-26"})
        self.assertEqual(len({r["experiment_id"] for r in self.rows}), len(self.rows))

    def test_units_and_zero(self):
        row = query_experiments(source_record="PSI-26", as_run_test_id="1")[0]
        self.assertAlmostEqual(row["oxygen_pct"], 22.1)
        self.assertAlmostEqual(row["pressure_kpa"], 98.28525)
        row = query_experiments(source_record="PSI-25", test_id="B1")[0]
        self.assertEqual(row["oxygen_pct"], 22.2)
        self.assertEqual(row["airflow_cm_s"], 5)
        self.assertEqual(row["thickness_mm"], .1)
        row = query_experiments(source_record="PSI-25", test_id="O2")[0]
        self.assertEqual(row["airflow_cm_s"], 0)
        self.assertEqual(row["diameter_mm"], 6.35)
        self.assertIsNone(row["thickness_mm"])
        self.assertEqual(scalar(0), 0)
        self.assertEqual(dimensions("PMMA 2 cm", "unknown"), {"thickness_mm": "", "diameter_mm": "", "width_mm": ""})
        for value in ["<1", "5, 3", "5   3", "3-4", "1.2.3", "NaN", "none", "~5"]:
            self.assertEqual(scalar(value), "")

    def test_report_notes_and_noninvented_labels(self):
        row = query_experiments(source_record="PSI-25", test_id="B1")[0]
        self.assertIn("spread halfway", row["notes"])
        self.assertIn("extinguished", row["notes"])
        self.assertIn("PDF page 111", row["supplement_locator"])
        self.assertEqual(row["burned_binary"], 1)
        self.assertEqual(sum(bool(r["notes"]) for r in query_experiments(source_record="PSI-25")), 126)
        self.assertTrue(all(not r["training_eligible"] for r in self.rows))
        self.assertEqual(query_experiments(source_record="PSI-25", test_id="O20")[0]["burned_binary"], None)

    def test_missing_pressure_and_variable_flow(self):
        self.assertTrue(all(r["pressure_kpa"] is None for r in query_experiments(source_record="PSI-25")))
        row = query_experiments(source_record="PSI-25", test_id="B6")[0]
        self.assertIsNone(row["airflow_cm_s"])
        self.assertIn("approaching", row["airflow_raw"])
        flagged = [r["test_id"] for r in self.rows if "oxygen_final_increase_requires_review" in r["quality_flags"]]
        self.assertEqual(set(flagged), {"P22b", "T28b"})

    def test_sample_group_and_citations(self):
        groups = {}
        for row in self.rows:
            key = row["source_record"], row["sample_id"].lower()
            groups.setdefault(key, set()).add(row["split_group"])
            self.assertTrue(row["source_file"] and row["source_row"] and row["source_url"])
        self.assertTrue(all(len(values) == 1 for values in groups.values()))
        chunks = load_evidence()
        self.assertEqual(len(chunks), len({r["chunk_id"] for r in chunks}))
        self.assertTrue(all(r["text"] and r["locator"] and r["source_url"] for r in chunks))

    def test_ground_and_flex(self):
        with (ROOT / "clean/ground_thresholds.csv").open() as f:
            ground = list(csv.DictReader(f))
        self.assertTrue(all(r["gravity_regime"] == "earth_1g" for r in ground))
        cast = [r for r in ground if r["table_number"] == "7" and r["configuration"] == "cast; hot wire"][0]
        self.assertEqual((float(cast["uloi_oxygen_pct"]), float(cast["moc_oxygen_pct"])), (15.7, 14))
        with (ROOT / "clean/flex_backup.csv").open() as f:
            flex = list(csv.DictReader(f))
        self.assertEqual(len(flex), 274)
        self.assertEqual(len({r["experiment_id"] for r in flex}), 274)
        self.assertEqual(float(flex[0]["oxygen_pct"]), 21)
        self.assertAlmostEqual(float(flex[0]["pressure_kpa"]), 757.7 / 760 * 101.325)
        self.assertEqual(load_quality_report()["training_eligible_rows"], 0)


if __name__ == "__main__":
    unittest.main()
