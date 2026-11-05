"""
Phase 8.7 Regression Test Suite: Scientific & Explainability Corrections.
Tests feature order alignment, exact background baseline additivity,
spatial evaluation claims, scientific provenance/uncertainty metadata,
and test portability.
"""

import json
import os
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

from src.ml.random_forest import RandomForestClassifier
from src.ml.explainability import (
    TreePathExplainer,
    validate_feature_schema,
    AUTHORITATIVE_FEATURE_ORDER,
    audit_explainability_environment,
)
from src.backend.services.model_service import ModelService
from src.backend.services.region_service import RegionService
from src.backend.services.flood_service import FloodService
from src.backend.database.database import get_db_connection
from src.backend import contracts


class TestPhase87ScientificCorrections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.model_path = cls.project_root / "models/phase7a/phase7a_random_forest_model.joblib"
        cls.samples_path = cls.project_root / "data/outputs/phase7a/statistics/phase7a_training_samples.csv"
        
        assert cls.model_path.exists(), f"Required model file not found at {cls.model_path}"
        assert cls.samples_path.exists(), f"Required samples file not found at {cls.samples_path}"
        
        cls.model = RandomForestClassifier.load(str(cls.model_path))
        cls.df = pd.read_csv(cls.samples_path)
        cls.test_df = cls.df[cls.df["split"] == "test"].copy()

    def test_01_feature_schema_validation(self):
        """Feature schema validation strictly enforces the 6 authoritative features and order."""
        # Valid order
        validate_feature_schema(AUTHORITATIVE_FEATURE_ORDER)

        # Inverted features (e.g. cross_pol_ratio before vv_minus_vh_db)
        inverted = [
            "vv_db",
            "vh_db",
            "cross_pol_ratio",
            "vv_minus_vh_db",
            "texture_vv",
            "texture_vh",
        ]
        with self.assertRaises(ValueError) as ctx:
            validate_feature_schema(inverted)
        self.assertIn("Incorrect feature ordering", str(ctx.exception))

        # Missing feature
        missing = ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv"]
        with self.assertRaises(ValueError) as ctx:
            validate_feature_schema(missing)
        self.assertIn("Feature count mismatch", str(ctx.exception))

        # Unexpected feature
        unexpected = [
            "vv_db",
            "vh_db",
            "vv_minus_vh_db",
            "cross_pol_ratio",
            "texture_vv",
            "extra_feat",
        ]
        with self.assertRaises(ValueError) as ctx:
            validate_feature_schema(unexpected)
        self.assertIn("Unexpected features found", str(ctx.exception))

    def test_02_held_out_test_confusion_matrix(self):
        """Frozen RF model matches authoritative confusion matrix on held-out test split (N=6,124)."""
        X_test = self.test_df[AUTHORITATIVE_FEATURE_ORDER].values
        y_test = self.test_df["label"].values
        self.assertEqual(len(X_test), 6124)

        probas = self.model.predict_proba(X_test)[:, 1]
        preds = (probas >= 0.35).astype(int)

        tp = int(np.sum((preds == 1) & (y_test == 1)))
        tn = int(np.sum((preds == 0) & (y_test == 0)))
        fp = int(np.sum((preds == 1) & (y_test == 0)))
        fn = int(np.sum((preds == 0) & (y_test == 1)))

        self.assertEqual(tp, 2239)
        self.assertEqual(tn, 932)
        self.assertEqual(fp, 2762)
        self.assertEqual(fn, 191)

    def test_03_ensemble_root_additivity_on_test_samples(self):
        """Ensemble root mode satisfies exact additivity (|residual| < 1e-5) across >= 100 test samples."""
        explainer = TreePathExplainer(self.model, feature_names=AUTHORITATIVE_FEATURE_ORDER)
        X_test = self.test_df[AUTHORITATIVE_FEATURE_ORDER].values[:120]

        for i in range(len(X_test)):
            sample = X_test[i]
            res = explainer.explain_instance(sample, baseline_mode="ensemble_root")
            pred_p = self.model.predict_proba(sample.reshape(1, -1))[0, 1]
            sum_contrib = sum(res["attributions"].values())
            reconstructed = res["base_value"] + sum_contrib
            self.assertAlmostEqual(reconstructed, pred_p, places=5)
            self.assertAlmostEqual(res["prediction_probability"], pred_p, places=5)
            self.assertLess(res["additivity_error"], 1e-5)
            self.assertTrue(res["is_additive"])

    def test_04_background_baseline_additivity_mathematical_correction(self):
        """Background baseline mode satisfies exact additivity (|residual| < 1e-5) across >= 100 test samples."""
        train_df = self.df[self.df["split"] == "train"].copy()
        bg_samples = train_df[AUTHORITATIVE_FEATURE_ORDER].values[:50]

        explainer = TreePathExplainer(
            self.model,
            feature_names=AUTHORITATIVE_FEATURE_ORDER,
            background_X=bg_samples,
        )
        X_test = self.test_df[AUTHORITATIVE_FEATURE_ORDER].values[:120]

        for i in range(len(X_test)):
            sample = X_test[i]
            res = explainer.explain_instance(sample, baseline_mode="background")
            pred_p = self.model.predict_proba(sample.reshape(1, -1))[0, 1]
            sum_contrib = sum(res["attributions"].values())
            reconstructed = res["base_value"] + sum_contrib
            self.assertAlmostEqual(reconstructed, pred_p, places=5)
            self.assertAlmostEqual(res["prediction_probability"], pred_p, places=5)
            self.assertLess(res["additivity_error"], 1e-5)
            self.assertTrue(res["is_additive"])

    def test_05_background_mode_requires_background_data(self):
        """Calling baseline_mode='background' without setting background data raises ValueError."""
        explainer = TreePathExplainer(self.model, feature_names=AUTHORITATIVE_FEATURE_ORDER)
        sample = np.array([-15.0, -22.0, 7.0, 0.68, 120.0, 80.0])
        with self.assertRaises(ValueError) as ctx:
            explainer.explain_instance(sample, baseline_mode="background")
        self.assertIn("no background dataset was provided", str(ctx.exception))

    def test_06_split_threshold_and_nextafter_boundary_additivity(self):
        """Boundary split threshold and np.nextafter cases satisfy exact additivity."""
        train_df = self.df[self.df["split"] == "train"].copy()
        bg_samples = train_df[AUTHORITATIVE_FEATURE_ORDER].values[:30]
        explainer = TreePathExplainer(
            self.model,
            feature_names=AUTHORITATIVE_FEATURE_ORDER,
            background_X=bg_samples,
        )

        first_tree = self.model.estimators_[0]
        thresh = first_tree.root.threshold
        feat = first_tree.root.feature

        base_sample = np.array([-15.0, -22.0, 7.0, 0.68, 120.0, 80.0])

        for delta in [0.0, np.nextafter(thresh, thresh + 1.0) - thresh, np.nextafter(thresh, thresh - 1.0) - thresh]:
            sample = base_sample.copy()
            sample[feat] = thresh + delta

            # Check both modes
            for mode in ["ensemble_root", "background"]:
                res = explainer.explain_instance(sample, baseline_mode=mode)
                pred_p = self.model.predict_proba(sample.reshape(1, -1))[0, 1]
                self.assertLess(
                    res["additivity_error"],
                    1e-5,
                    f"Residual failed for mode {mode} at delta {delta}",
                )
                self.assertAlmostEqual(res["prediction_probability"], pred_p, places=5)
                self.assertTrue(res["is_additive"])

    def test_07_flood_uncertainty_no_unsupported_terrain_subdivisions(self):
        """Flood uncertainty endpoint provides true indeterminate counts without fabricated shadow/layover."""
        flood_service = FloodService()
        uncertainty = flood_service.get_flood_uncertainty(contracts.STUDY_AREA_ID)
        self.assertEqual(uncertainty["total_indeterminate_cells"], 16242)
        self.assertEqual(uncertainty["total_indeterminate_ha"], 649.68)
        self.assertEqual(uncertainty["total_indeterminate_km2"], 6.4968)
        self.assertEqual(uncertainty["percentage_of_aoi"], 1.6081)

        # Confirm unsupported field names are not in dictionary
        self.assertNotIn("radar_shadow_exclusion_ha", uncertainty)
        self.assertNotIn("layover_exclusion_ha", uncertainty)
        self.assertNotIn("water_lookalike_exclusion_ha", uncertainty)

        # Confirm scientific explanation is present
        self.assertIn("subdivision_note", uncertainty)
        self.assertIn("alluvial terrain", uncertainty["subdivision_note"])

    def test_08_analysis_runs_provenance_distinct_from_acquisitions(self):
        """Seeded database analysis_runs reflect genuine execution timestamps and distinct acquisitions."""
        conn = get_db_connection()
        try:
            runs = conn.execute("SELECT run_id, executed_at, parameters FROM analysis_runs").fetchall()
            for run in runs:
                exec_time = run["executed_at"]
                params = json.loads(run["parameters"]) if run["parameters"] else {}
                acquisitions = params.get("satellite_acquisitions", [])
                # Execution timestamps should be 2026-11-* or UNKNOWN, not 2024-11-*
                self.assertTrue(
                    exec_time.startswith("2026-11-") or exec_time == "UNKNOWN",
                    f"Unexpected executed_at {exec_time} for run {run['run_id']}",
                )
                # Satellite acquisitions should be 2024-06-10 / 2024-07-16
                self.assertIn("2024-06-10", acquisitions)
                self.assertIn("2024-07-16", acquisitions)
        finally:
            conn.close()

    def test_09_model_validation_claims_accuracy(self):
        """Model service accurately claims spatial held-out evaluation and unverified temporal generalization."""
        model_service = ModelService()
        metrics = model_service.get_metrics("phase7a_rf_jamuna_v1")
        self.assertIsNotNone(metrics)

        self.assertIn("Spatial-block held-out evaluation", metrics["evaluation_dataset"])
        self.assertIn("N=6,124", metrics["evaluation_dataset"])
        self.assertIn("UNVERIFIED", metrics["temporal_generalization_status"])

        model_meta = model_service.get_model("phase7a_rf_jamuna_v1")
        self.assertIsNotNone(model_meta)
        self.assertEqual(model_meta["status"], "RETAINED_AS_PROBABILITY_LAYER")

    def test_10_region_acquisition_label(self):
        """Region service labels July 16 acquisition as mid_monsoon_flood_observation."""
        region_service = RegionService()
        detail = region_service.get_region_detail(contracts.STUDY_AREA_ID)
        self.assertIsNotNone(detail)
        acquisitions = detail["available_acquisitions"]
        self.assertTrue(any("mid_monsoon_flood_observation" in acq for acq in acquisitions))

    def test_11_explainability_environment_audit_portability(self):
        """audit_explainability_environment behaves correctly when shap is present or absent."""
        env_audit = audit_explainability_environment()
        self.assertIn("primary_explainer_engine", env_audit)
        self.assertIn("TreePathExplainer", env_audit["primary_explainer_engine"])

        # Test simulated missing shap
        real_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "shap":
                raise ImportError("No module named 'shap'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            mocked_audit = audit_explainability_environment()
            self.assertFalse(mocked_audit["shap_available"])
            self.assertEqual(mocked_audit["shap_status"], "BLOCKED_DEPENDENCY_MISSING")


if __name__ == "__main__":
    unittest.main()
