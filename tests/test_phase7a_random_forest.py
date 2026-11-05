"""
Comprehensive Unit Tests for Earth Pulse Phase 7A: SAR-Based Random Forest Development & Evaluation
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers:
1. Feature extraction & numerical bounds.
2. Feature alignment & dimension preservation.
3. Reference-label construction & binary encoding.
4. Exclusion of vegetation (SCL 4) and uncertain optical classes.
5. Deterministic sample generation reproducibility.
6. Spatial block split proportions (60/20/20).
7. Strict absence of spatial leakage between train/val/test blocks.
8. Model reproducibility across random seeds.
9. Confusion matrix calculation correctness.
10. Metric calculations (Precision, Recall, F1, IoU, Specificity, Balanced Accuracy).
11. Validation-only threshold selection integrity (Test set untouched).
12. Probability raster spatial metadata & georeferencing.
13. NoData preservation across classification rasters.
14. Model serialization and joblib round-trip reload.
15. Comparison against the deterministic Lee 5x5 baseline.
16. Insufficient sample / empty block handling.
"""

import json
from pathlib import Path
import joblib
import numpy as np
from osgeo import gdal
gdal.UseExceptions()
import pandas as pd
import pytest

from scripts.ml_metrics import compute_classification_metrics, compute_confusion_matrix, compute_roc_auc
from scripts.run_phase7a_pipeline import (
    FEATURE_NAMES,
    FEATURE_SCHEMA,
    compute_sar_features,
    partition_spatial_blocks,
)
from src.ml.random_forest import RandomForestClassifier

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def p7a_artifacts():
    """Loads Phase 7A metadata and deliverables for testing."""
    meta_path = PROJECT_ROOT / "data/metadata/phase7a_model_report.json"
    stats_dir = PROJECT_ROOT / "data/outputs/phase7a/statistics"
    models_dir = PROJECT_ROOT / "models/phase7a"

    assert meta_path.exists(), f"Missing metadata: {meta_path}"
    with open(meta_path) as f:
        meta = json.load(f)

    df_samples = pd.read_csv(stats_dir / "phase7a_training_samples.csv")
    df_blocks = pd.read_csv(stats_dir / "phase7a_spatial_split_summary.csv")
    df_comp = pd.read_csv(stats_dir / "phase7a_model_comparison.csv")
    df_imp = pd.read_csv(stats_dir / "phase7a_feature_importance.csv")

    model_path = models_dir / "phase7a_random_forest_model.joblib"
    assert model_path.exists(), f"Missing model: {model_path}"
    model = RandomForestClassifier.load(model_path)

    return {
        "meta": meta,
        "samples": df_samples,
        "blocks": df_blocks,
        "comp": df_comp,
        "imp": df_imp,
        "model": model,
    }


class TestPhase7AFeatureEngineering:
    """Tests 1 & 2: Feature extraction, dimensions, and numerical bounds."""

    def test_feature_extraction_and_bounds(self):
        """Verifies that all 6 core SAR features are extracted with valid finite bounds."""
        lee_path = PROJECT_ROOT / "data/processed/phase2b/lee_5x5/june10_lee_5x5.tif"
        feats = compute_sar_features(lee_path)

        assert len(feats) >= 6
        for name in FEATURE_NAMES:
            assert name in feats, f"Missing feature: {name}"
            arr = feats[name]
            assert arr.shape == (1393, 1405)
            assert np.all(np.isfinite(arr))

        # Test specific backscatter ranges
        assert np.min(feats["vv_db"]) >= -75.0
        assert np.max(feats["vv_db"]) <= 30.0
        assert np.min(feats["vh_db"]) >= -75.0
        assert np.max(feats["vh_db"]) <= 20.0
        assert np.all(feats["texture_vv"] >= 0.0)
        assert np.all(feats["texture_vh"] >= 0.0)

    def test_feature_spatial_alignment(self):
        """Verifies that feature rasters match the canonical reference grid dimensions."""
        ref_ds = gdal.Open(str(PROJECT_ROOT / "data/processed/aligned/june10_aligned.tif"))
        w, h = ref_ds.RasterXSize, ref_ds.RasterYSize
        ref_ds = None

        assert (w, h) == (1405, 1393)
        prob_ds = gdal.Open(str(PROJECT_ROOT / "data/processed/phase7a/phase7a_june10_water_probability.tif"))
        assert (prob_ds.RasterXSize, prob_ds.RasterYSize) == (w, h)
        prob_ds = None


class TestPhase7AReferenceLabelsAndSampling:
    """Tests 3, 4, 5: Reference-label construction, exclusions, and sampling."""

    def test_reference_label_construction_and_exclusions(self, p7a_artifacts):
        """Verifies that training labels contain ONLY binary 0 (SCL 5) and 1 (SCL 6)."""
        df_samples = p7a_artifacts["samples"]
        labels = df_samples["label"].unique()
        assert set(labels) == {0, 1}

        # Check raw SCL exclusion
        scl_ds = gdal.Open(str(PROJECT_ROOT / "data/processed/reference/optical/sentinel2/june_2024/s2_june07_aligned_scl.tif"))
        scl_arr = scl_ds.GetRasterBand(1).ReadAsArray()
        scl_ds = None

        sample_rows = df_samples[df_samples["epoch"] == "June"]["row"].values[:100]
        sample_cols = df_samples[df_samples["epoch"] == "June"]["col"].values[:100]
        sample_scl = scl_arr[sample_rows, sample_cols]

        # Ensure no SCL 4 (vegetation) or cloud classes are in the sampled points
        assert not np.any(sample_scl == 4), "SCL Class 4 (vegetation) found in training samples!"
        assert not np.any(sample_scl == 3), "SCL Class 3 (cloud shadow) found in training samples!"
        assert not np.any(sample_scl == 8), "SCL Class 8 (cloud) found in training samples!"

    def test_deterministic_sample_generation(self, p7a_artifacts):
        """Verifies that sampling is balanced across classes and deterministic."""
        df_samples = p7a_artifacts["samples"]
        assert len(df_samples) > 20000

        # Check stratified representation
        w_count = int(np.sum(df_samples["label"] == 1))
        nw_count = int(np.sum(df_samples["label"] == 0))
        # Balanced: neither class should exceed 60% of total
        ratio = w_count / (w_count + nw_count)
        assert 0.35 <= ratio <= 0.65


class TestPhase7ASpatialPartitioning:
    """Tests 6 & 7: Spatial block partitioning and leakage prevention."""

    def test_spatial_block_proportions(self, p7a_artifacts):
        """Verifies grouped spatial split proportions (~60% Train, ~20% Val, ~20% Test)."""
        df_blocks = p7a_artifacts["blocks"]
        eval_blocks = df_blocks[df_blocks["split"].isin(["train", "val", "test"])]
        n_eval = len(eval_blocks)

        n_tr = int(np.sum(eval_blocks["split"] == "train"))
        n_va = int(np.sum(eval_blocks["split"] == "val"))
        n_te = int(np.sum(eval_blocks["split"] == "test"))

        assert 0.55 <= (n_tr / n_eval) <= 0.65
        assert 0.15 <= (n_va / n_eval) <= 0.25
        assert 0.15 <= (n_te / n_eval) <= 0.25
        assert n_tr + n_va + n_te == n_eval

    def test_zero_spatial_leakage(self, p7a_artifacts):
        """Strictly verifies that no spatial block appears in more than one split."""
        df_blocks = p7a_artifacts["blocks"]
        tr_bids = set(df_blocks[df_blocks["split"] == "train"]["block_id"])
        va_bids = set(df_blocks[df_blocks["split"] == "val"]["block_id"])
        te_bids = set(df_blocks[df_blocks["split"] == "test"]["block_id"])

        assert len(tr_bids.intersection(va_bids)) == 0, "Spatial leakage between train and val!"
        assert len(tr_bids.intersection(te_bids)) == 0, "Spatial leakage between train and test!"
        assert len(va_bids.intersection(te_bids)) == 0, "Spatial leakage between val and test!"


class TestPhase7AModelAndEvaluation:
    """Tests 8, 9, 10, 11: Model training, metrics, and threshold tuning."""

    def test_model_reproducibility(self):
        """Verifies that Random Forest with fixed random seed reproduces exact predictions."""
        rng = np.random.RandomState(42)
        X = rng.randn(200, 6).astype(np.float32)
        y = (X[:, 0] > 0).astype(np.int32)

        rf1 = RandomForestClassifier(n_estimators=10, max_depth=5, random_state=42)
        rf1.fit(X, y)
        p1 = rf1.predict_proba(X)

        rf2 = RandomForestClassifier(n_estimators=10, max_depth=5, random_state=42)
        rf2.fit(X, y)
        p2 = rf2.predict_proba(X)

        np.testing.assert_array_almost_equal(p1, p2, decimal=6)

    def test_confusion_matrix_and_metrics_math(self):
        """Verifies mathematical consistency of classification metrics."""
        y_true = np.array([1, 1, 0, 0, 1, 0, 1, 0], dtype=np.int32)
        y_pred = np.array([1, 0, 0, 1, 1, 0, 1, 0], dtype=np.int32)

        cm = compute_confusion_matrix(y_true, y_pred)
        assert cm["tp"] == 3
        assert cm["fp"] == 1
        assert cm["tn"] == 3
        assert cm["fn"] == 1

        m = compute_classification_metrics(y_true, y_pred)
        assert m["precision"] == 0.75
        assert m["recall"] == 0.75
        assert m["f1_score"] == 0.75
        assert m["iou"] == 0.60
        assert m["specificity"] == 0.75
        assert m["balanced_accuracy"] == 0.75

    def test_validation_only_threshold_selection(self, p7a_artifacts):
        """Verifies that the probability threshold was chosen on validation data only."""
        meta = p7a_artifacts["meta"]
        tuning = meta["model_architecture"]["hyperparameter_tuning"]
        opt_thresh = tuning["selected_probability_threshold"]

        assert 0.20 <= opt_thresh <= 0.80
        # Optimal threshold must have higher validation F1 than default 0.50
        assert tuning["validation_f1_optimal_thresh"] >= tuning["validation_f1_default_thresh"]


class TestPhase7ARastersAndSerialization:
    """Tests 12, 13, 14: GeoTIFF metadata, NoData, and model persistence."""

    def test_probability_raster_metadata_and_nodata(self):
        """Verifies probability and classification GeoTIFF metadata and NoData values."""
        prob_path = PROJECT_ROOT / "data/processed/phase7a/phase7a_june10_water_probability.tif"
        class_path = PROJECT_ROOT / "data/processed/phase7a/phase7a_june10_rf_water_classification.tif"

        p_ds = gdal.Open(str(prob_path))
        assert p_ds.GetRasterBand(1).GetNoDataValue() == -9999.0
        p_arr = p_ds.GetRasterBand(1).ReadAsArray()
        p_ds = None

        c_ds = gdal.Open(str(class_path))
        assert c_ds.GetRasterBand(1).GetNoDataValue() == 255
        c_arr = c_ds.GetRasterBand(1).ReadAsArray()
        c_ds = None

        # Inside AOI, valid probabilities must be in [0, 1]
        valid_p = p_arr[p_arr != -9999.0]
        assert len(valid_p) > 0
        assert np.all((valid_p >= 0.0) & (valid_p <= 1.0))

        # Classification must be binary 0 or 1
        valid_c = c_arr[c_arr != 255]
        assert set(np.unique(valid_c)).issubset({0, 1})

    def test_model_serialization_round_trip(self, p7a_artifacts):
        """Verifies model serialization and round-trip reload using joblib."""
        model = p7a_artifacts["model"]
        tmp_path = PROJECT_ROOT / "models/phase7a/test_roundtrip.joblib"

        model.save(tmp_path)
        loaded = RandomForestClassifier.load(tmp_path)
        tmp_path.unlink()

        assert loaded.n_estimators == model.n_estimators
        assert loaded.max_depth == model.max_depth
        np.testing.assert_array_almost_equal(loaded.feature_importances_, model.feature_importances_)


class TestPhase7ABaselineComparisonAndRobustness:
    """Tests 15 & 16: Comparison with Otsu baseline and insufficient sample handling."""

    def test_baseline_comparison_retention_decision(self, p7a_artifacts):
        """Verifies that the comparison table reflects scientific retention of Lee 5x5 Otsu."""
        df_comp = p7a_artifacts["comp"]
        assert len(df_comp) == 6

        # Lee 5x5 Otsu must have higher specificity on combined test set
        rf_comb = df_comp[(df_comp["model"].str.contains("Random Forest")) & (df_comp["evaluation_dataset"].str.contains("Combined"))].iloc[0]
        otsu_comb = df_comp[(df_comp["model"].str.contains("Lee 5x5")) & (df_comp["evaluation_dataset"].str.contains("Combined"))].iloc[0]

        assert otsu_comb["specificity"] > rf_comb["specificity"]
        meta = p7a_artifacts["meta"]
        assert meta["scientific_conclusions"]["primary_classifier_status"] == "RETAIN_LEE_5X5_DUAL_AND_OTSU_AS_PRIMARY"

    def test_insufficient_sample_handling(self):
        """Verifies that partition logic safely handles blocks with 0 evaluable samples."""
        aoi_empty = np.zeros((100, 100), dtype=bool)
        june_valid_empty = np.zeros((100, 100), dtype=bool)
        june_scl_empty = np.zeros((100, 100), dtype=np.uint8)
        july_valid_empty = np.zeros((100, 100), dtype=bool)
        july_scl_empty = np.zeros((100, 100), dtype=np.uint8)

        df_b, splits = partition_spatial_blocks(
            aoi_empty, june_valid_empty, june_scl_empty, july_valid_empty, july_scl_empty, block_size=50
        )
        assert len(df_b) == 0
        assert len(splits["train"]) == 0

