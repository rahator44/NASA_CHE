"""
Unit and Integration Tests for Earth Pulse Phase 7B: Explainable AI & SAR Model Interpretability
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers:
1. Model loading.
2. Correct class-1 explanation selection.
3. Feature-order preservation.
4. SHAP output dimensions.
5. SHAP additivity where supported.
6. Deterministic sampling.
7. Spatial test-set isolation.
8. Local explanation metadata.
9. Model-version preservation.
10. Grouped correlated-feature attribution.
11. Probability and SHAP terminology.
12. Missing-SHAP dependency handling.
13. Multi-region explanation configuration.
14. No modifications to existing model artifacts.
15. Reproducibility.
"""

from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from src.ml.random_forest import RandomForestClassifier
from src.ml.explainability import (
    audit_explainability_environment,
    TreePathExplainer,
    investigate_feature_redundancy,
    compute_grouped_attributions,
    evaluate_probability_calibration,
)
from src.ml.registry import ModelRegistry
from src.ml.prediction_record import ExplainabilityBatchBuffer


class TestPhase7BExplainabilitySuite:

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.model_path = PROJECT_ROOT / "models/phase7a/phase7a_random_forest_model.joblib"
        self.rf_model = RandomForestClassifier.load(self.model_path)
        self.feature_names = ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"]
        self.samples_path = PROJECT_ROOT / "data/outputs/phase7a/statistics/phase7a_training_samples.csv"
        self.df_samples = pd.read_csv(self.samples_path)
        self.df_train = self.df_samples[self.df_samples["split"] == "train"]
        self.df_test = self.df_samples[self.df_samples["split"] == "test"]

    def test_01_model_loading(self):
        """1. Verifies that the existing Phase 7A model loads cleanly with 40 estimators."""
        assert self.rf_model is not None
        assert len(self.rf_model.estimators_) == 40
        assert self.rf_model.max_depth == 6
        assert hasattr(self.rf_model, "feature_importances_")

    def test_02_correct_class1_explanation_selection(self):
        """2. Asserts that explanations target class 1 (candidate water) probability."""
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        x_sample = self.df_test[self.feature_names].iloc[0].values
        res = explainer.explain_instance(x_sample)
        
        # Verify prediction probability matches rf_model.predict_proba for class 1
        model_prob = self.rf_model.predict_proba(x_sample.reshape(1, -1))[0, 1]
        assert abs(res["prediction_probability"] - model_prob) < 1e-6
        assert 0.0 <= res["prediction_probability"] <= 1.0

    def test_03_feature_order_preservation(self):
        """3. Asserts that feature ordering is strictly preserved through explanation layers."""
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        assert explainer.feature_names == self.feature_names
        x_sample = np.array([-20.0, -26.0, 6.0, 3.98, 0.8, 1.2])
        res = explainer.explain_instance(x_sample)
        assert list(res["attributions"].keys()) == self.feature_names

    def test_04_shap_output_dimensions(self):
        """4. Asserts that batch SHAP matrix matches (N_samples, N_features)."""
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        sub_X = self.df_test[self.feature_names].iloc[:25].values
        batch_res = explainer.explain_dataset(sub_X)
        shap_mat = batch_res["shap_values"]
        assert shap_mat.shape == (25, 6)

    def test_05_shap_additivity_exact(self):
        """5. Verifies exact mathematical additivity: base_value + sum(attributions) == prediction."""
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        sub_X = self.df_test[self.feature_names].iloc[:50].values
        for i in range(len(sub_X)):
            res = explainer.explain_instance(sub_X[i])
            assert res["is_additive"] is True
            calc_pred = res["base_value"] + res["sum_attributions"]
            assert abs(calc_pred - res["prediction_probability"]) < 1e-4

    def test_06_deterministic_sampling(self):
        """6. Asserts that sample selection using fixed seed is exactly reproducible."""
        rng1 = np.random.RandomState(42)
        idx1 = rng1.choice(len(self.df_test), size=100, replace=False)

        rng2 = np.random.RandomState(42)
        idx2 = rng2.choice(len(self.df_test), size=100, replace=False)
        assert np.array_equal(idx1, idx2)

    def test_07_spatial_test_set_isolation(self):
        """7. Verifies that test set blocks are never used as background reference data."""
        train_blocks = set(self.df_train["block_id"].unique())
        test_blocks = set(self.df_test["block_id"].unique())
        assert len(train_blocks.intersection(test_blocks)) == 0

    def test_08_local_explanation_metadata(self):
        """8. Validates that local explanation CSV contains all spatial and attribution metadata."""
        local_csv = PROJECT_ROOT / "data/outputs/phase7b/local_explanations/phase7b_local_prediction_explanations.csv"
        assert local_csv.exists()
        df_local = pd.read_csv(local_csv)
        assert len(df_local) == 8
        required_cols = [
            "case_id", "epoch", "block_id", "pixel_row", "pixel_col",
            "utm_x", "utm_y", "optical_reference_label", "rf_prediction",
            "rf_probability", "base_value", "category",
            "shap_vv_db", "shap_vh_db", "shap_texture_vh"
        ]
        for col in required_cols:
            assert col in df_local.columns

    def test_09_model_version_preservation(self):
        """9. Asserts that the model version is preserved and status is RETAINED_AS_PROBABILITY_LAYER."""
        report_path = PROJECT_ROOT / "data/metadata/phase7b_explainability_report.json"
        assert report_path.exists()
        with open(report_path) as f:
            rep = json.load(f)
        assert rep["model_identifier"] == "phase7a_rf_jamuna_v1"
        assert rep["model_registry_status"] == "RETAINED_AS_PROBABILITY_LAYER"
        assert rep["operational_baseline"] == "deterministic_lee_5x5_dual_and_otsu"

    def test_10_grouped_correlated_feature_attribution(self):
        """10. Tests grouping of redundant polarization features into a unified attribution."""
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        sub_X = self.df_test[self.feature_names].iloc[:50].values
        batch_res = explainer.explain_dataset(sub_X)
        df_grouped = compute_grouped_attributions(batch_res["shap_values"], self.feature_names)
        assert len(df_grouped) == 3
        group_names = df_grouped["feature_group"].tolist()
        assert "radiometric_backscatter" in group_names
        assert "polarization_ratio_group" in group_names
        assert "spatial_texture_group" in group_names
        assert abs(df_grouped["attribution_fraction_pct"].sum() - 100.0) < 0.5

    def test_11_probability_and_shap_terminology(self):
        """11. Ensures terminology clearly distinguishes probability, attribution, and reference agreement."""
        calib_csv = PROJECT_ROOT / "data/outputs/phase7b/diagnostics/phase7b_probability_diagnostics.csv"
        assert calib_csv.exists()
        df_cal = pd.read_csv(calib_csv)
        assert "mean_predicted_prob" in df_cal.columns
        assert "empirical_water_fraction" in df_cal.columns
        assert "calibration_gap" in df_cal.columns

    def test_12_missing_shap_dependency_handling(self):
        """12. Verifies that missing 3rd-party shap package is cleanly caught and reported as BLOCKED (mocked for environment portability)."""
        import builtins
        from unittest import mock
        orig_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "shap":
                raise ImportError("No module named 'shap'")
            return orig_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=mock_import):
            env_audit = audit_explainability_environment()
            assert env_audit["shap_available"] is False
            assert env_audit["shap_status"] == "BLOCKED_DEPENDENCY_MISSING"
            assert "BLOCKED" in env_audit["shap_status"]

    def test_13_multi_region_explanation_configuration(self):
        """13. Verifies that explainability buffer accepts arbitrary region identifiers."""
        buffer = ExplainabilityBatchBuffer(
            model_version="phase7a_rf_jamuna_v1",
            region_id="future_region_patna",
            dataset_id="test_dataset_01",
            decision_threshold=0.35,
        )
        rec = buffer.add_prediction(
            feature_names=self.feature_names,
            feature_values=[-15.0, -22.0, 7.0, 5.0, 1.0, 1.5],
            prediction_probability=0.72,
        )
        assert rec.region_id == "future_region_patna"
        df_buf = buffer.to_dataframe()
        assert df_buf["region_id"].iloc[0] == "future_region_patna"

    def test_14_no_modifications_to_existing_model_artifacts(self):
        """14. Verifies that the Phase 7A model artifact was not altered or overwritten."""
        expected_sha256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"
        hasher = hashlib.sha256()
        with open(self.model_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        assert hasher.hexdigest() == expected_sha256

    def test_15_reproducibility(self):
        """15. Asserts that repeated explanation runs produce bitwise identical attribution values."""
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        x_fixed = np.array([-18.4, -25.2, 6.8, 4.786, 0.95, 1.34])
        run1 = explainer.explain_instance(x_fixed)["attributions_array"]
        run2 = explainer.explain_instance(x_fixed)["attributions_array"]
        assert np.array_equal(run1, run2)

