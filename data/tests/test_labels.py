"""Evidence alignment, censoring and leakage checks for the label handoff."""
import csv
import json
from pathlib import Path
import sys
import unittest

DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA / "scripts"))
from label_data import airflow_readings, source_hash, flex_initial_problems


def read(name):
    with (DATA / "clean" / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class LabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tests = {r["experiment_id"]: r for r in read("solid_combustion_model.csv")}
        cls.stages = read("solid_stage_observations.csv")
        cls.candidates = read("solid_stage_training.csv")

    def test_review_coverage_and_source_hashes(self):
        reviews = [json.loads(x) for x in (DATA / "annotations/solid_test_reviews.jsonl").read_text().splitlines()]
        self.assertEqual(len(reviews), 250)
        self.assertEqual({r["experiment_id"] for r in reviews}, set(self.tests))
        for review in reviews:
            self.assertEqual(source_hash(self.tests[review["experiment_id"]]), review["source_evidence_sha256"])
            self.assertEqual(review["review_status"], "team_verified")
            self.assertIn("Project team", review["reviewer"])
            self.assertIn("initial annotation by Codex", review["reviewer"])
        changed = dict(next(iter(self.tests.values())))
        before = source_hash(changed)
        changed["notes"] += " changed source"
        self.assertNotEqual(source_hash(changed), before)

    def test_every_stage_has_exact_evidence_and_parent(self):
        self.assertEqual(len({s["stage_id"] for s in self.stages}), len(self.stages))
        self.assertEqual({s["experiment_id"] for s in self.stages}, set(self.tests))
        for stage in self.stages:
            parent = self.tests[stage["experiment_id"]]
            self.assertIn(stage["evidence_quote"], parent[stage["evidence_field"]])
            self.assertEqual(stage["oxygen_at_stage_pct"], "")
            self.assertTrue(stage["source_url"] and stage["validation_group"])

    def test_no_labels_are_smeared_across_a_sequence(self):
        b6 = [s for s in self.candidates if s["test_id"] == "B6"]
        self.assertEqual({float(s["airflow_cm_s"]) for s in b6}, {3, 5})
        b9 = [s for s in self.stages if s["test_id"] == "B9"]
        self.assertEqual([s["airflow_cm_s"] for s in b9 if s["sustained_flame_binary"] == "0"], [""])
        self.assertTrue(any(s["test_id"] == "O2" and s["airflow_cm_s"] == "2" for s in self.stages))
        self.assertFalse(any(s["test_id"] == "O2" and s["airflow_cm_s"] == "0" for s in self.candidates))

    def test_bounds_and_fan_settings_are_not_airspeed(self):
        self.assertEqual(airflow_readings("10, 5"), [("10", 10., "exact_display"), ("5", 5., "exact_display")])
        for value in ["3-4", "<1", "~5"]:
            self.assertEqual(airflow_readings(value)[0][1], "")
        for value in ["3 0.5 pot 0.4 pot", "49 5 cm/s", "5 down to ext"]:
            self.assertEqual(airflow_readings(value)[0][2], "unresolved_text_or_mixed_units")
        for stage in self.candidates:
            self.assertEqual(stage["airflow_qualifier"], "exact")
            self.assertGreater(float(stage["airflow_cm_s"]), 0)
            self.assertEqual(stage["exclusion_reasons"], "")

    def test_burn_and_terminal_extinction_are_distinct(self):
        b1 = next(r for r in self.tests.values() if r["test_id"] == "B1")
        self.assertEqual(b1["burned_binary"], "1")
        terminal = [s for s in self.stages if s["experiment_id"] == b1["experiment_id"] and s["event_state"] == "terminal_extinction"]
        self.assertEqual(terminal[0]["sustained_flame_binary"], "0")
        self.assertEqual(terminal[0]["training_eligible"], "false")
        self.assertFalse(any("hardware_failure" == self.tests[s["experiment_id"]]["outcome"] for s in self.candidates))

    def test_protocol_does_not_encode_the_outcome(self):
        # Trial type describes the prior experimental setup, not "success".
        for protocol in {s["protocol"] for s in self.candidates}:
            self.assertEqual({s["sustained_flame_binary"] for s in self.candidates if s["protocol"] == protocol}, {"0", "1"})
        report = json.loads((DATA / "clean/labeling_report.json").read_text())
        self.assertNotIn("event_state", report["required_solid_features"])
        self.assertIn("event_state", report["forbidden_features"])

    def test_censoring_and_missing_flex_features(self):
        labeled, training = read("flex_labeled.csv"), read("flex_training.csv")
        self.assertEqual(len(labeled), 274)
        disrupted = [r for r in labeled if r["test_end_raw"] == "Disruption"]
        self.assertEqual(len(disrupted), 61)
        self.assertTrue(all(r["extinction_binary"] == "" and r["training_eligible"] == "false" for r in disrupted))
        self.assertEqual(len(training), 202)
        self.assertEqual(sum(r["extinction_binary"] == "1" for r in training), 176)
        self.assertTrue(all(r["source_record"] == "PSI-69" and r["exclusion_reasons"] == "" for r in training))

    def test_flex_initial_physical_sanity(self):
        labeled = read("flex_labeled.csv")
        zero_pressure = next(r for r in labeled if r["test_id"] == "114")
        self.assertEqual(float(zero_pressure["pressure_kpa"]), 0)
        self.assertIn("nonpositive_initial_feature:pressure_kpa", zero_pressure["exclusion_reasons"])
        self.assertEqual(zero_pressure["training_eligible"], "false")
        for test in ["69", "75", "76", "79"]:
            row = next(r for r in labeled if r["test_id"] == test)
            self.assertIn("initial_gas_fractions_do_not_sum_to_one", row["exclusion_reasons"])
        valid = read("flex_training.csv")[0]
        self.assertEqual(flex_initial_problems(valid), [])
        for field, value in [("pressure_kpa", "NaN"), ("droplet_diameter_mm", "-1"), ("oxygen_pct", "101"), ("co2_fraction", "1.1")]:
            self.assertTrue(flex_initial_problems({**valid, field: value}))


if __name__ == "__main__":
    unittest.main()
