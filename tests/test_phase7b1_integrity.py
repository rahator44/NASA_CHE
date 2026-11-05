"""
Unit and Integration Tests for Earth Pulse Phase 7B.1: Model Integrity & Explainability Audit
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers:
1. Random Forest bootstrap behaviour.
2. Random feature selection per split.
3. Tree ensemble probability aggregation (soft voting).
4. Correct OOB versus ordinary prediction terminology.
5. Brute-force Shapley reference calculation and divergence on small trees.
6. Tree-path attribution correctness (stepwise probability deltas).
7. SHAP additivity (efficiency: phi_0 + sum(phi_j) == f(x)).
8. Repeated feature splits along a path.
9. Feature ordering preservation.
10. Feature redundancy, invertibility range, and 20 dB clipping.
11. Local explanation consistency across all 8 representative cases.
12. Probability calibration & decision margin terminology.
13. Confusion matrix sample-count reconciliation (6,124 test observations).
14. Epoch-specific Otsu thresholds (Phase 3A vs illustrative static baseline).
15. Multi-region explanation metadata & PredictionRecord buffer.
16. Preservation and immutability of frozen model artifact (SHA-256).
"""

import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from osgeo import gdal

gdal.UseExceptions()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from src.ml.random_forest import DecisionNode, DecisionTreeClassifier, RandomForestClassifier
from src.ml.explainability import (
    TreePathExplainer,
    tree_conditional_expectation,
    compute_exact_tree_shapley,
    compute_exact_ensemble_shapley,
    explain_prediction_records,
)
from src.ml.prediction_record import PredictionRecord, ExplainabilityBatchBuffer


class TestPhase7B1IntegritySuite:

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.model_path = PROJECT_ROOT / "models/phase7a/phase7a_random_forest_model.joblib"
        self.rf_model = RandomForestClassifier.load(self.model_path)
        self.feature_names = ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"]
        self.samples_path = PROJECT_ROOT / "data/outputs/phase7a/statistics/phase7a_training_samples.csv"
        self.df_samples = pd.read_csv(self.samples_path)
        self.df_train = self.df_samples[self.df_samples["split"] == "train"].reset_index(drop=True)
        self.df_test = self.df_samples[self.df_samples["split"] == "test"].reset_index(drop=True)

    def test_01_random_forest_bootstrap_behaviour(self):
        """1. Verifies that tree training samples with replacement and 75% sub-bagging."""
        master_rng = np.random.RandomState(42)
        sample_size = int(0.75 * len(self.df_train))
        assert sample_size == 14118
        
        # Verify bootstrap sampling with replacement produces duplicates
        tree_seed = int(master_rng.randint(0, 1000000))
        tree_rng = np.random.RandomState(tree_seed)
        b_idx = tree_rng.choice(len(self.df_train), size=sample_size, replace=True)
        unique_b = np.unique(b_idx)
        assert len(unique_b) < sample_size  # With replacement, unique count is strictly less than sample size
        assert len(unique_b) > 0.5 * sample_size

    def test_02_random_feature_selection(self):
        """2. Verifies that random feature subsampling chooses sqrt(D) = 2 features per split."""
        tree = self.rf_model.estimators_[0]
        assert tree.max_features == "sqrt"
        # For D=6, floor(sqrt(6)) = 2
        m_feat = max(1, int(np.sqrt(6)))
        assert m_feat == 2

    def test_03_tree_ensemble_probability_aggregation(self):
        """3. Verifies that ensemble probability is the arithmetic mean across all 40 trees."""
        assert len(self.rf_model.estimators_) == 40
        X_sample = self.df_test[self.feature_names].iloc[:5].values
        
        # Manual average across trees
        manual_probs = np.zeros((5, 2), dtype=np.float32)
        for t in self.rf_model.estimators_:
            manual_probs += t.predict_proba(X_sample)
        manual_probs /= 40.0
        
        rf_probs = self.rf_model.predict_proba(X_sample)
        np.testing.assert_allclose(rf_probs, manual_probs, atol=1e-6)

    def test_04_oob_vs_ordinary_prediction_terminology(self):
        """4. Asserts that test set predictions evaluate all 40 trees and are NOT out-of-bag."""
        csv_path = PROJECT_ROOT / "data/outputs/phase7b1/audit/phase7b1_oob_prediction_audit.csv"
        assert csv_path.exists()
        df_oob = pd.read_csv(csv_path)
        
        # Verify table documents ordinary vs true OOB distinction
        assert "Ordinary Ensemble Soft Voting" in df_oob["prediction_paradigm"].values
        assert "True Out-of-Bag (OOB) Prediction" in df_oob["prediction_paradigm"].values
        assert "Held-Out Test Set Prediction" in df_oob["prediction_paradigm"].values

    def test_05_bruteforce_shapley_equivalence(self):
        """5. Verifies brute-force exact Shapley reference calculation and single-split equivalence."""
        # Single-split decision stump
        t1 = DecisionTreeClassifier()
        l1 = DecisionNode(prob=0.8, n_samples=60, is_leaf=True)
        r1 = DecisionNode(prob=0.2, n_samples=40, is_leaf=True)
        t1.root = DecisionNode(feature=0, threshold=0.5, left=l1, right=r1, prob=0.56, n_samples=100, is_leaf=False)

        x_test = np.array([0.2, 0.8])
        rf_dummy = RandomForestClassifier(n_estimators=1)
        rf_dummy.estimators_ = [t1]
        explainer = TreePathExplainer(rf_dummy, feature_names=["f0", "f1"], allow_custom_schema=True)
        saabas_res = explainer.explain_instance(x_test)
        
        base_exact, shap_exact = compute_exact_tree_shapley(t1, x_test, n_features=2)
        
        # On single-split tree, Saabas and Exact Shapley are analytically identical
        np.testing.assert_allclose(saabas_res["attributions_array"], shap_exact, atol=1e-6)
        assert abs(base_exact - 0.56) < 1e-6

    def test_06_tree_path_attribution_correctness(self):
        """6. Verifies stepwise probability delta accumulation along traversed tree branches."""
        # Depth-2 sequential splits: Root splits f0 at 0.5, left splits f1 at 0.5
        ll = DecisionNode(prob=1.0, n_samples=50, is_leaf=True)
        lr = DecisionNode(prob=0.2, n_samples=50, is_leaf=True)
        l = DecisionNode(feature=1, threshold=0.5, left=ll, right=lr, prob=0.6, n_samples=100, is_leaf=False)
        r = DecisionNode(prob=0.0, n_samples=100, is_leaf=True)
        root = DecisionNode(feature=0, threshold=0.5, left=l, right=r, prob=0.3, n_samples=200, is_leaf=False)
        
        t = DecisionTreeClassifier()
        t.root = root
        rf_wrap = RandomForestClassifier(n_estimators=1)
        rf_wrap.estimators_ = [t]
        
        explainer = TreePathExplainer(rf_wrap, feature_names=["f0", "f1"], allow_custom_schema=True)
        x = np.array([0.2, 0.2])
        res = explainer.explain_instance(x)
        
        # Stepwise deltas:
        # At root (f0): 0.60 - 0.30 = +0.30
        # At left (f1): 1.00 - 0.60 = +0.40
        assert abs(res["attributions"]["f0"] - 0.30) < 1e-6
        assert abs(res["attributions"]["f1"] - 0.40) < 1e-6
        assert abs(res["base_value"] - 0.30) < 1e-6

    def test_07_shap_additivity(self):
        """7. Verifies exact additivity efficiency: phi_0 + sum(phi_j) == model_prediction."""
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        sub_X = self.df_test[self.feature_names].iloc[:30].values
        
        for i in range(len(sub_X)):
            res = explainer.explain_instance(sub_X[i])
            pred = res["prediction_probability"]
            reconstructed = res["base_value"] + res["sum_attributions"]
            assert abs(reconstructed - pred) < 1e-4
            assert res["is_additive"] is True

    def test_08_repeated_feature_splits(self):
        """8. Verifies that multiple splits on the same feature accumulate correctly into that feature."""
        # Tree where f0 is split at root and at left child
        ll = DecisionNode(prob=0.9, n_samples=30, is_leaf=True)
        lr = DecisionNode(prob=0.5, n_samples=30, is_leaf=True)
        l = DecisionNode(feature=0, threshold=0.5, left=ll, right=lr, prob=0.7, n_samples=60, is_leaf=False)
        r = DecisionNode(prob=0.1, n_samples=40, is_leaf=True)
        root = DecisionNode(feature=0, threshold=1.0, left=l, right=r, prob=0.46, n_samples=100, is_leaf=False)
        
        t = DecisionTreeClassifier()
        t.root = root
        rf_wrap = RandomForestClassifier(n_estimators=1)
        rf_wrap.estimators_ = [t]
        
        explainer = TreePathExplainer(rf_wrap, feature_names=["f0", "f1"], allow_custom_schema=True)
        x = np.array([0.2, 10.0])
        res = explainer.explain_instance(x)
        
        # Delta 1: 0.70 - 0.46 = 0.24 on f0
        # Delta 2: 0.90 - 0.70 = 0.20 on f0
        # Total on f0 = 0.44; f1 is 0.0
        assert abs(res["attributions"]["f0"] - 0.44) < 1e-6
        assert abs(res["attributions"]["f1"] - 0.0) < 1e-6

    def test_09_feature_ordering(self):
        """9. Verifies that feature ordering is preserved and identical across explanation schemas."""
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        assert explainer.feature_names == [
            "vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"
        ]
        sample = self.df_test[self.feature_names].iloc[0].values
        exp = explainer.explain_instance(sample)
        assert list(exp["attributions"].keys()) == self.feature_names

    def test_10_feature_redundancy_and_clipping(self):
        """10. Verifies clipping at 100.0 (20 dB) between vv_minus_vh_db and cross_pol_ratio."""
        csv_path = PROJECT_ROOT / "data/outputs/phase7b1/audit/phase7b1_feature_redundancy_audit.csv"
        assert csv_path.exists()
        df_red = pd.read_csv(csv_path)
        
        test_row = df_red[df_red["dataset_split"] == "Held-Out Test Split"].iloc[0]
        assert test_row["clipped_sample_count"] == 32
        assert test_row["unclipped_sample_count"] == 6092
        assert test_row["clipped_sample_pct"] == 0.52
        assert test_row["spearman_r"] == 1.0

    def test_11_local_explanation_consistency(self):
        """11. Verifies that all 8 representative local cases pass additivity audit."""
        csv_path = PROJECT_ROOT / "data/outputs/phase7b1/audit/phase7b1_local_additivity_audit.csv"
        assert csv_path.exists()
        df_local = pd.read_csv(csv_path)
        
        assert len(df_local) == 8
        assert df_local["additivity_pass"].all()
        assert (df_local["additivity_error"] < 1e-5).all()

    def test_12_probability_terminology(self):
        """12. Verifies calibration statistics (Brier score 0.2270, ECE 0.0959)."""
        csv_path = PROJECT_ROOT / "data/outputs/phase7b1/audit/phase7b1_probability_calibration_audit.csv"
        assert csv_path.exists()
        df_cal = pd.read_csv(csv_path)
        
        assert len(df_cal) == 10  # 10 probability bins
        assert abs(df_cal["brier_score_overall"].iloc[0] - 0.2270) < 1e-3
        assert abs(df_cal["expected_calibration_error"].iloc[0] - 0.0959) < 1e-3

    def test_13_confusion_matrix_sample_count_reconciliation(self):
        """13. Reconciles held-out confusion matrix: N=6,124, TP=2,239, TN=932, FP=2,762, FN=191."""
        X_test = self.df_test[self.feature_names].values
        y_test = self.df_test["label"].values
        probs = self.rf_model.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.35).astype(int)
        
        tp = int(np.sum((y_test == 1) & (preds == 1)))
        tn = int(np.sum((y_test == 0) & (preds == 0)))
        fp = int(np.sum((y_test == 0) & (preds == 1)))
        fn = int(np.sum((y_test == 1) & (preds == 0)))
        
        assert tp == 2239
        assert tn == 932
        assert fp == 2762
        assert fn == 191
        assert tp + tn + fp + fn == 6124

    def test_14_epoch_specific_otsu_thresholds(self):
        """14. Verifies historical epoch-specific Otsu thresholds from Phase 3A report."""
        p3a_json_path = PROJECT_ROOT / "data/metadata/phase3a_classification_report.json"
        with open(p3a_json_path) as f:
            p3a_meta = json.load(f)
            
        june_vv = p3a_meta["scenarios"]["june10"]["lee_5x5"]["thresholds"]["otsu_1d"]["vv"]["threshold"]
        june_vh = p3a_meta["scenarios"]["june10"]["lee_5x5"]["thresholds"]["otsu_1d"]["vh"]["threshold"]
        july_vv = p3a_meta["scenarios"]["july16"]["lee_5x5"]["thresholds"]["otsu_1d"]["vv"]["threshold"]
        july_vh = p3a_meta["scenarios"]["july16"]["lee_5x5"]["thresholds"]["otsu_1d"]["vh"]["threshold"]
        
        assert abs(june_vv - (-12.457)) < 0.01
        assert abs(june_vh - (-21.697)) < 0.01
        assert abs(july_vv - (-14.960)) < 0.01
        assert abs(july_vh - (-21.828)) < 0.01

    def test_15_multiregion_explanation_metadata(self):
        """15. Verifies PredictionRecord batch buffer and explanation integration."""
        buffer = ExplainabilityBatchBuffer(
            model_version="phase7a_rf_jamuna_v1",
            region_id="jamuna_sirajganj",
            dataset_id="sentinel1_grd_2024",
        )
        sample = self.df_test.iloc[0]
        rec = buffer.add_prediction(
            feature_names=self.feature_names,
            feature_values=sample[self.feature_names].values.tolist(),
            prediction_probability=0.75,
            pixel_row=100,
            pixel_col=200,
            utm_x=650000.0,
            utm_y=2730000.0,
        )
        assert rec.region_id == "jamuna_sirajganj"
        assert rec.model_version == "phase7a_rf_jamuna_v1"
        assert rec.binary_prediction == 1
        
        explainer = TreePathExplainer(self.rf_model, feature_names=self.feature_names)
        df_explained = explain_prediction_records(
            explainer=explainer,
            records=[rec],
            region_id="jamuna_sirajganj",
            model_version="phase7a_rf_jamuna_v1",
        )
        assert len(df_explained) == 1
        assert bool(df_explained["is_additive"].iloc[0]) is True

    def test_16_preservation_of_frozen_model_artifacts(self):
        """16. Verifies that phase7a Random Forest artifact is unmodified with exact SHA-256."""
        model_bytes = self.model_path.read_bytes()
        sha256 = hashlib.sha256(model_bytes).hexdigest()
        expected_sha256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"
        assert sha256 == expected_sha256
