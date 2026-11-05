"""
Earth Pulse — Phase 4D.1: Validation Metric Reconciliation & Scientific Correction Test Suite
NASA Space Apps Challenge 2026 — Dancing with the SARs

This module tests:
1. Strict reference non-water count cannot exceed AOI SCL Class 5 count.
2. Secondary reference non-water count cannot exceed AOI SCL Classes 4 + 5.
3. Reference water count cannot exceed AOI SCL Class 6.
4. Confusion matrix conservation (N = TP + FP + TN + FN).
5. Strict and secondary evaluation domains are correctly separated.
6. SCL class 4 never enters strict validation.
7. SCL class 7 never enters the water or non-water reference labels.
8. Cloud, shadow, and dark-area pixels remain excluded.
9. SAR categories 2 and 3 remain excluded.
10. July and June Phase 4C.1 versus Phase 4D optical water count reconciliation.
11. Raster alignment and AOI masking consistency.
12. Deterministic block-bootstrap reproducibility.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal

from scripts.reconcile_phase4d1 import (
    AOI_TARGET_CELLS,
    CANONICAL_HEIGHT,
    CANONICAL_WIDTH,
    compute_reconciled_confusion_matrix,
    compute_scl_cross_tabulation,
    compute_spatial_block_statistics_phase4d1,
    create_study_aoi_raster_mask,
    find_project_root,
    read_raster_band,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return find_project_root()


@pytest.fixture(scope="module")
def canonical_aoi_mask(project_root: Path) -> np.ndarray:
    sar_path = project_root / "data/processed/phase3a_qc/candidate_masks/june10_lee_5x5_otsu_dual_and_qc.tif"
    return create_study_aoi_raster_mask(sar_path)


@pytest.fixture(scope="module")
def source_rasters(project_root: Path):
    s2_dir = project_root / "data/processed/reference/optical/sentinel2"
    sar_dir = project_root / "data/processed/phase3a_qc/candidate_masks"

    sar_june, gt_sar, proj_sar = read_raster_band(sar_dir / "june10_lee_5x5_otsu_dual_and_qc.tif")
    sar_july, _, _ = read_raster_band(sar_dir / "july16_lee_5x5_otsu_dual_and_qc.tif")
    scl_june, gt_opt, proj_opt = read_raster_band(s2_dir / "june_2024/s2_june07_aligned_scl.tif")
    scl_july, _, _ = read_raster_band(s2_dir / "july_2024/s2_july17_aligned_scl.tif")
    wat_june, _, _ = read_raster_band(s2_dir / "june_2024/s2_june07_aligned_water_mask.tif")
    wat_july, _, _ = read_raster_band(s2_dir / "july_2024/s2_july17_aligned_water_mask.tif")
    mndwi_june, _, _ = read_raster_band(s2_dir / "june_2024/s2_june07_aligned_mndwi.tif")
    mndwi_july, _, _ = read_raster_band(s2_dir / "july_2024/s2_july17_aligned_mndwi.tif")

    return {
        "sar_june": sar_june,
        "sar_july": sar_july,
        "scl_june": scl_june,
        "scl_july": scl_july,
        "wat_june": wat_june,
        "wat_july": wat_july,
        "mndwi_june": mndwi_june,
        "mndwi_july": mndwi_july,
        "gt_sar": gt_sar,
        "gt_opt": gt_opt,
    }


def test_strict_reference_non_water_lte_scl5(source_rasters, canonical_aoi_mask):
    """
    Test 1: Strict reference non-water (FP + TN) must be strictly <= total AOI SCL Class 5 count.
    """
    # June
    res_june = compute_reconciled_confusion_matrix(
        source_rasters["sar_june"], source_rasters["scl_june"], canonical_aoi_mask, mode="primary_strict"
    )
    cm_june = res_june["confusion_matrix"]
    aoi_scl5_june = int(np.sum((source_rasters["scl_june"] == 5) & canonical_aoi_mask))
    assert aoi_scl5_june == 353793
    assert (cm_june["false_positive"] + cm_june["true_negative"]) <= aoi_scl5_june
    assert (cm_june["false_positive"] + cm_june["true_negative"]) == 349040

    # July
    res_july = compute_reconciled_confusion_matrix(
        source_rasters["sar_july"], source_rasters["scl_july"], canonical_aoi_mask, mode="primary_strict"
    )
    cm_july = res_july["confusion_matrix"]
    aoi_scl5_july = int(np.sum((source_rasters["scl_july"] == 5) & canonical_aoi_mask))
    assert aoi_scl5_july == 70297
    assert (cm_july["false_positive"] + cm_july["true_negative"]) <= aoi_scl5_july
    assert (cm_july["false_positive"] + cm_july["true_negative"]) == 70283


def test_secondary_reference_non_water_lte_scl4_plus_scl5(source_rasters, canonical_aoi_mask):
    """
    Test 2: Secondary reference non-water (FP + TN) must be <= total AOI SCL Class 4 + Class 5 count.
    """
    # June
    res_june = compute_reconciled_confusion_matrix(
        source_rasters["sar_june"], source_rasters["scl_june"], canonical_aoi_mask, mode="secondary_vegetation_included"
    )
    cm_june = res_june["confusion_matrix"]
    aoi_scl4_5_june = int(np.sum(np.isin(source_rasters["scl_june"], [4, 5]) & canonical_aoi_mask))
    assert aoi_scl4_5_june == 353793 + 9813
    assert (cm_june["false_positive"] + cm_june["true_negative"]) <= aoi_scl4_5_june
    assert (cm_june["false_positive"] + cm_june["true_negative"]) == 358853

    # July
    res_july = compute_reconciled_confusion_matrix(
        source_rasters["sar_july"], source_rasters["scl_july"], canonical_aoi_mask, mode="secondary_vegetation_included"
    )
    cm_july = res_july["confusion_matrix"]
    aoi_scl4_5_july = int(np.sum(np.isin(source_rasters["scl_july"], [4, 5]) & canonical_aoi_mask))
    assert aoi_scl4_5_july == 70297 + 30215
    assert (cm_july["false_positive"] + cm_july["true_negative"]) <= aoi_scl4_5_july
    assert (cm_july["false_positive"] + cm_july["true_negative"]) == 100498


def test_reference_water_lte_scl6(source_rasters, canonical_aoi_mask):
    """
    Test 3: Evaluated reference water (TP + FN) must be strictly <= total AOI SCL Class 6 count.
    """
    # June
    res_june = compute_reconciled_confusion_matrix(
        source_rasters["sar_june"], source_rasters["scl_june"], canonical_aoi_mask, mode="primary_strict"
    )
    cm_june = res_june["confusion_matrix"]
    aoi_scl6_june = int(np.sum((source_rasters["scl_june"] == 6) & canonical_aoi_mask))
    assert aoi_scl6_june == 199802
    assert (cm_june["true_positive"] + cm_june["false_negative"]) <= aoi_scl6_june
    assert (cm_june["true_positive"] + cm_june["false_negative"]) == 192202

    # July
    res_july = compute_reconciled_confusion_matrix(
        source_rasters["sar_july"], source_rasters["scl_july"], canonical_aoi_mask, mode="primary_strict"
    )
    cm_july = res_july["confusion_matrix"]
    aoi_scl6_july = int(np.sum((source_rasters["scl_july"] == 6) & canonical_aoi_mask))
    assert aoi_scl6_july == 49206
    assert (cm_july["true_positive"] + cm_july["false_negative"]) <= aoi_scl6_july
    assert (cm_july["true_positive"] + cm_july["false_negative"]) == 49195


def test_confusion_matrix_conservation(source_rasters, canonical_aoi_mask):
    """
    Test 4: Confusion matrix conservation: N = TP + FP + TN + FN.
    """
    for ep, (sar_k, scl_k) in [("June", ("sar_june", "scl_june")), ("July", ("sar_july", "scl_july"))]:
        for mode in ["primary_strict", "secondary_vegetation_included"]:
            res = compute_reconciled_confusion_matrix(
                source_rasters[sar_k], source_rasters[scl_k], canonical_aoi_mask, mode=mode
            )
            cm = res["confusion_matrix"]
            n = cm["total_evaluated_pixels"]
            assert n == (cm["true_positive"] + cm["false_positive"] + cm["true_negative"] + cm["false_negative"])


def test_strict_and_secondary_evaluation_domains_separation(source_rasters, canonical_aoi_mask):
    """
    Test 5: Secondary evaluated count minus strict evaluated count must exactly equal
    the valid SCL Class 4 (Vegetation) count coincident with valid SAR.
    """
    # June
    june_strict = compute_reconciled_confusion_matrix(source_rasters["sar_june"], source_rasters["scl_june"], canonical_aoi_mask, mode="primary_strict")
    june_sec = compute_reconciled_confusion_matrix(source_rasters["sar_june"], source_rasters["scl_june"], canonical_aoi_mask, mode="secondary_vegetation_included")
    diff_june = june_sec["confusion_matrix"]["total_evaluated_pixels"] - june_strict["confusion_matrix"]["total_evaluated_pixels"]
    assert diff_june == 9813

    # July
    july_strict = compute_reconciled_confusion_matrix(source_rasters["sar_july"], source_rasters["scl_july"], canonical_aoi_mask, mode="primary_strict")
    july_sec = compute_reconciled_confusion_matrix(source_rasters["sar_july"], source_rasters["scl_july"], canonical_aoi_mask, mode="secondary_vegetation_included")
    diff_july = july_sec["confusion_matrix"]["total_evaluated_pixels"] - july_strict["confusion_matrix"]["total_evaluated_pixels"]
    assert diff_july == 30215


def test_scl_class4_never_enters_strict_validation():
    """
    Test 6: Synthetic test verifying SCL Class 4 never enters primary strict validation.
    """
    aoi = np.ones((2, 2), dtype=bool)
    sar = np.array([[1, 0], [1, 0]], dtype=np.uint8)
    scl = np.array([[4, 4], [5, 6]], dtype=np.uint8)

    res = compute_reconciled_confusion_matrix(sar, scl, aoi, mode="primary_strict")
    # Only bottom row (indices [1,0] and [1,1]) is evaluated (SCL 5, 6)
    assert res["confusion_matrix"]["total_evaluated_pixels"] == 2
    assert res["aoi_exclusions"]["optical_vegetation_class_4"] == 2


def test_scl_class7_never_enters_water_or_non_water_labels():
    """
    Test 7: Synthetic test verifying SCL Class 7 (unclassified) never enters reference water or non-water.
    """
    aoi = np.ones((1, 4), dtype=bool)
    sar = np.array([[1, 0, 1, 0]], dtype=np.uint8)
    scl = np.array([[7, 7, 5, 6]], dtype=np.uint8)

    res_strict = compute_reconciled_confusion_matrix(sar, scl, aoi, mode="primary_strict")
    assert res_strict["confusion_matrix"]["total_evaluated_pixels"] == 2
    assert res_strict["aoi_exclusions"]["optical_unclassified_class_7"] == 2

    res_sec = compute_reconciled_confusion_matrix(sar, scl, aoi, mode="secondary_vegetation_included")
    assert res_sec["confusion_matrix"]["total_evaluated_pixels"] == 2


def test_cloud_shadow_dark_area_pixels_remain_excluded():
    """
    Test 8: Synthetic test verifying SCL Classes 2 (dark area), 3 (shadow), and 8..10 (cloud) are excluded.
    """
    aoi = np.ones((1, 5), dtype=bool)
    sar = np.array([[1, 0, 1, 0, 1]], dtype=np.uint8)
    scl = np.array([[2, 3, 8, 9, 10]], dtype=np.uint8)

    res = compute_reconciled_confusion_matrix(sar, scl, aoi, mode="primary_strict")
    assert res["confusion_matrix"]["total_evaluated_pixels"] == 0
    assert res["aoi_exclusions"]["optical_dark_area_class_2"] == 1
    assert res["aoi_exclusions"]["optical_cloud_shadow_class_3"] == 1
    assert res["aoi_exclusions"]["optical_pure_cloud_classes_8_9_10"] == 3


def test_sar_categories_2_and_3_remain_excluded():
    """
    Test 9: Synthetic test verifying SAR Category 2 (indeterminate) and 3 (NoData) are excluded.
    """
    aoi = np.ones((1, 4), dtype=bool)
    sar = np.array([[2, 3, 1, 0]], dtype=np.uint8)
    scl = np.array([[6, 5, 6, 5]], dtype=np.uint8)

    res = compute_reconciled_confusion_matrix(sar, scl, aoi, mode="primary_strict")
    assert res["confusion_matrix"]["total_evaluated_pixels"] == 2
    assert res["aoi_exclusions"]["sar_indeterminate_clipping_floor"] == 1
    assert res["aoi_exclusions"]["sar_nodata"] == 1


def test_july_phase4c1_vs_phase4d_water_count_reconciliation(source_rasters, canonical_aoi_mask):
    """
    Test 10: Reconcile the Phase 4C.1 hybrid MNDWI water mask count vs Phase 4D raw SCL 6.
    Exact identities:
    June: 256,636 == 199,802 (SCL 6) + 56,834 (SCL 5 with MNDWI > 0)
    July: 99,131 == 49,206 (SCL 6) + 49,899 (SCL 5 with MNDWI > 0) + 26 (SCL 4 with MNDWI > 0)
    """
    # June
    wat_june = source_rasters["wat_june"]
    scl_june = source_rasters["scl_june"]
    mndwi_june = source_rasters["mndwi_june"]

    june_hybrid_count = int(np.sum((wat_june == 1) & canonical_aoi_mask))
    june_scl6_count = int(np.sum((scl_june == 6) & canonical_aoi_mask))
    june_scl5_wet = int(np.sum((scl_june == 5) & canonical_aoi_mask & (mndwi_june > 0.0)))
    june_scl4_wet = int(np.sum((scl_june == 4) & canonical_aoi_mask & (mndwi_june > 0.0)))

    assert june_hybrid_count == 256636
    assert june_scl6_count == 199802
    assert june_scl5_wet == 56834
    assert june_scl4_wet == 0
    assert june_hybrid_count == (june_scl6_count + june_scl5_wet + june_scl4_wet)

    # July
    wat_july = source_rasters["wat_july"]
    scl_july = source_rasters["scl_july"]
    mndwi_july = source_rasters["mndwi_july"]

    july_hybrid_count = int(np.sum((wat_july == 1) & canonical_aoi_mask))
    july_scl6_count = int(np.sum((scl_july == 6) & canonical_aoi_mask))
    july_scl5_wet = int(np.sum((scl_july == 5) & canonical_aoi_mask & (mndwi_july > 0.0)))
    july_scl4_wet = int(np.sum((scl_july == 4) & canonical_aoi_mask & (mndwi_july > 0.0)))

    assert july_hybrid_count == 99131
    assert july_scl6_count == 49206
    assert july_scl5_wet == 49899
    assert july_scl4_wet == 26
    assert july_hybrid_count == (july_scl6_count + july_scl5_wet + july_scl4_wet)


def test_raster_alignment_and_aoi_masking(source_rasters, canonical_aoi_mask):
    """
    Test 11: Verify identical spatial raster geometry and canonical AOI cell count (1,010,039 cells).
    """
    assert canonical_aoi_mask.shape == (CANONICAL_HEIGHT, CANONICAL_WIDTH)
    assert np.sum(canonical_aoi_mask) == AOI_TARGET_CELLS

    gt_sar = source_rasters["gt_sar"]
    gt_opt = source_rasters["gt_opt"]
    for a, b in zip(gt_sar, gt_opt):
        assert abs(a - b) < 1e-4


def test_deterministic_block_bootstrap_reproducibility(source_rasters, canonical_aoi_mask):
    """
    Test 12: Verify deterministic block bootstrap reproducibility with random seed 42.
    """
    _, sum1 = compute_spatial_block_statistics_phase4d1(
        source_rasters["sar_june"], source_rasters["scl_june"], canonical_aoi_mask, block_size_px=50, random_seed=42, n_bootstrap=200
    )
    _, sum2 = compute_spatial_block_statistics_phase4d1(
        source_rasters["sar_june"], source_rasters["scl_june"], canonical_aoi_mask, block_size_px=50, random_seed=42, n_bootstrap=200
    )

    ci1 = sum1["bootstrap_uncertainty_95ci"]
    ci2 = ci2 = sum2["bootstrap_uncertainty_95ci"]

    assert ci1["f1_score_ci_95"] == ci2["f1_score_ci_95"]
    assert ci1["precision_ci_95"] == ci2["precision_ci_95"]
    assert ci1["recall_ci_95"] == ci2["recall_ci_95"]
    assert ci1["iou_ci_95"] == ci2["iou_ci_95"]

