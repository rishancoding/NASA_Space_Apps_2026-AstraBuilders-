"""Check the selected model contract without fitting a model."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / "model/model_spec.json").read_text())
        cls.audit = json.loads((ROOT / "data/clean/model_readiness.json").read_text())

    def test_selected_dataset_and_hash(self):
        spec = self.spec
        self.assertEqual(spec["source_record"], "PSI-69")
        self.assertEqual(spec["number_of_final_models"], 1)
        self.assertEqual(spec["target"], "extinction_binary")
        self.assertEqual(spec["training_rows"], 202)
        path = ROOT / spec["dataset"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), spec["dataset_sha256"])
        self.assertEqual(spec["class_counts"], {"1": 176, "0": 26})

    def test_features_and_scope_do_not_claim_solid_predictions(self):
        spec = self.spec
        self.assertFalse(spec["solid_prediction_enabled"])
        self.assertEqual(spec["fuel_categories"], ["Heptane", "Methanol"])
        self.assertEqual(set(spec["features"]), {"fuel", "oxygen_pct", "pressure_kpa", "co2_fraction", "helium_fraction", "droplet_diameter_mm"})
        self.assertFalse(set(spec["features"]) & set(spec["excluded_predictor_columns"]))
        self.assertNotIn("nitrogen_fraction", spec["features"])

    def test_group_and_class_support_for_planned_folds(self):
        spec = self.spec
        with (ROOT / spec["dataset"]).open() as f:
            rows = list(csv.DictReader(f))
        for label in ["0", "1"]:
            groups = {r[spec["group_column"]] for r in rows if r[spec["target"]] == label}
            self.assertGreaterEqual(len(groups), spec["validation_plan"]["outer_folds"])
        self.assertTrue(spec["validation_plan"]["no_group_overlap"])

    def test_solid_limitations_and_no_training(self):
        audit = self.audit
        self.assertFalse(audit["model_fitted"])
        self.assertEqual(audit["solid_candidates"]["rows"], 47)
        self.assertEqual(audit["solid_candidates"]["by_protocol"]["ongoing_burn_trial"]["classes"]["0"], 3)
        self.assertEqual(audit["flex_candidates"]["rows"], 202)
        self.assertEqual(audit["flex_candidates"]["groups"], 201)
        self.assertAlmostEqual(audit["flex_candidates"]["majority_class_reference_accuracy_not_model_evaluation"], 176/202)
        self.assertTrue(self.spec["no_training_in_step_2"])


if __name__ == "__main__":
    unittest.main()
