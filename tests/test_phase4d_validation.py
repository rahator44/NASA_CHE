"""
Earth Pulse — Phase 4D: Independent Optical Validation & Agreement Assessment Test Suite
NASA Space Apps Challenge 2026 — Dancing with the SARs

This module tests:
1. SCL Class 7 separation (unclassified vs classes 8-10 pure cloud).
2. Diagnostic GeoTIFF mask generation and spatial metadata matching canonical SAR grid.
3. Rigorous area reconciliation (full raster, vector UTM, geodesic WGS84, rasterized AOI).
4. Conservative optical reference labeling and vegetation quarantining (strict vs secondary mode).
5. Confusion matrix, agreement metrics (Precision, Recall, F1, IoU, Specificity, Balanced Accuracy).
6. Exclusion verification for SAR indeterminate clipping-floor (Cat 2) and source NoData (Cat 3).
7. 1 km spatial block analysis, minimum pixel thresholding, and deterministic block bootstrap CI.
8. Phase 4D outputs integrity: CSV tables, high-res maps, master metadata JSON, and PARTIALLY_EVALUABLE designation.
9. Scientific terminology compliance: optical-reference agreement vs ground-truth accuracy.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal

from scripts.ingest_reference_data import mask_sentinel2_scl
from scripts.validate_reference_phase4d import (
    PIXEL_AREA_KM2,
    SAR_TARGET_EPSG,
    STUDY_AREA_AOI_WKT,
    compute_area_reconciliation,
    compute_confusion_matrix_and_metrics,
    compute_spatial_block_statistics,
    create_study_aoi_raster_mask,
    find_project_root,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return find_project_root()


@pytest.fixture(scope="module")
def sar_canonical_path(project_root: Path) -> Path:
    p = project_root / "data/processed/phase3a_qc/candidate_masks/june10_lee_5x5_otsu_dual_and_qc.tif"
    if not p.exists():
        pytest.skip(f"Canonical SAR mask not found: {p}")
    return p


@pytest.fixture(scope="module")
def master_metadata_json(project_root: Path) -> dict:
    meta_path = project_root / "data/metadata/phase4d_independent_reference_validation.json"
    if not meta_path.exists():
        pytest.skip(f"Phase 4D metadata JSON not found: {meta_path}")
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_scl_class7_separation_diagnostic_masks():
    """
    Verify that mask_sentinel2_scl strictly separates SCL Class 7 (unclassified)
    from Classes 8, 9, 10 (pure cloud), while maintaining backward-compatible
    cloud_cirrus_mask containing Classes 7 through 10.
    """
    # Create synthetic SCL array with all classes 0..11
    scl = np.array([
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [8, 9, 10, 11]
    ], dtype=np.uint8)

    res = mask_sentinel2_scl(scl)

    # Pure cloud must be ONLY classes 8, 9, 10
    expected_pure_cloud = np.array([
        [False, False, False, False],
        [False, False, False, False],
        [True,  True,  True,  False]
    ])
    assert np.array_equal(res.pure_cloud_mask, expected_pure_cloud)

    # Unclassified must be ONLY class 7
    expected_unclassified = np.array([
        [False, False, False, False],
        [False, False, False, True],
        [False, False, False, False]
    ])
    assert np.array_equal(res.unclassified_mask, expected_unclassified)

    # Backward compatibility: cloud_cirrus_mask must be union of pure_cloud and unclassified
    expected_combined_cloud = expected_pure_cloud | expected_unclassified
    assert np.array_equal(res.cloud_cirrus_mask, expected_combined_cloud)

    # Cloud shadow must be class 3
    assert np.array_equal(res.cloud_shadow_mask, scl == 3)
    # Dark area must be class 2
    assert np.array_equal(res.dark_area_mask, scl == 2)
    # Defective must be class 1
    assert np.array_equal(res.invalid_defective_mask, scl == 1)
    # Snow/ice must be class 11
    assert np.array_equal(res.snow_ice_mask, scl == 11)


def test_diagnostic_geotiff_files_exist_and_match_properties(project_root: Path):
    """
    Verify that pure cloud and unclassified diagnostic GeoTIFFs exist for both
    June and July and strictly match canonical SAR spatial grid.
    """
    diagnostics = [
        project_root / "data/processed/reference/optical/sentinel2/june_2024/s2_june07_aligned_cloud_pure_mask.tif",
        project_root / "data/processed/reference/optical/sentinel2/june_2024/s2_june07_aligned_unclassified_mask.tif",
        project_root / "data/processed/reference/optical/sentinel2/july_2024/s2_july17_aligned_cloud_pure_mask.tif",
        project_root / "data/processed/reference/optical/sentinel2/july_2024/s2_july17_aligned_unclassified_mask.tif",
    ]

    for p in diagnostics:
        assert p.exists(), f"Diagnostic GeoTIFF missing: {p}"
        ds = gdal.Open(str(p), gdal.GA_ReadOnly)
        assert ds is not None, f"Could not open GeoTIFF: {p}"
        assert ds.RasterXSize == 1405
        assert ds.RasterYSize == 1393
        gt = ds.GetGeoTransform()
        assert abs(gt[1] - 20.0) < 1e-4
        assert abs(gt[5] - (-20.0)) < 1e-4
        ds = None


def test_area_reconciliation_calculations(sar_canonical_path: Path):
    """
    Verify mathematical consistency and precision of area reconciliation across
    full raster footprint, vector UTM, geodesic WGS84, and rasterized AOI cells.
    """
    recon = compute_area_reconciliation(sar_canonical_path)

    full = recon["full_raster_footprint"]
    assert full["columns"] == 1405
    assert full["rows"] == 1393
    assert full["total_cells"] == 1957165
    assert abs(full["area_km2"] - 782.8660) < 1e-3

    vec = recon["vector_aoi"]
    assert abs(vec["projected_utm45n_area_km2"] - 404.0163) < 1e-3
    assert abs(vec["geodesic_wgs84_ellipsoidal_area_km2"] - 403.6218) < 1e-3

    rast = recon["rasterized_aoi"]
    assert rast["cells"] == 1010039
    assert abs(rast["raster_area_km2"] - 404.0156) < 1e-3

    disc = recon["discrepancy_analysis"]
    # Discrepancy between rasterized AOI and projected vector polygon is < 0.001 km² (< 2 px)
    assert abs(disc["rasterization_difference_km2"]) < 0.001
    assert abs(disc["rasterization_difference_pct"]) < 0.001
    assert "copernicus_browser_discrepancy_explanation" in disc
    assert "EPSG:3857" in disc["copernicus_browser_discrepancy_explanation"]


def test_optical_reference_labeling_and_vegetation_quarantining():
    """
    Verify conservative optical reference labeling:
    - Primary Strict: SCL 6 = water, SCL 5 = non-water, SCL 4 is quarantined (excluded).
    - Secondary: SCL 6 = water, SCL 4 + 5 = non-water.
    - Non-clear SCL classes (0, 1, 2, 3, 7, 8, 9, 10, 11) are excluded in both modes.
    """
    aoi_mask = np.ones((1, 5), dtype=bool)
    # SAR mask has valid water (1) and non-water (0)
    sar_mask = np.array([[1, 0, 1, 0, 1]], dtype=np.uint8)

    # Optical SCL: 6 (water), 5 (bare), 4 (vegetation), 8 (cloud), 2 (dark area)
    optical_scl = np.array([[6, 5, 4, 8, 2]], dtype=np.uint8)

    # 1. Primary strict
    res_strict = compute_confusion_matrix_and_metrics(sar_mask, optical_scl, aoi_mask, mode="primary_strict")
    # Evaluated pixels must be ONLY indices 0 (SCL 6) and 1 (SCL 5) -> 2 pixels
    assert res_strict["confusion_matrix"]["total_evaluated_pixels"] == 2
    # Pixel 0: SAR=1, Ref=1 -> TP
    # Pixel 1: SAR=0, Ref=0 -> TN
    assert res_strict["confusion_matrix"]["true_positive"] == 1
    assert res_strict["confusion_matrix"]["true_negative"] == 1
    assert res_strict["confusion_matrix"]["false_positive"] == 0
    assert res_strict["confusion_matrix"]["false_negative"] == 0

    # 2. Secondary mode (vegetation included in non-water)
    res_sec = compute_confusion_matrix_and_metrics(sar_mask, optical_scl, aoi_mask, mode="secondary_vegetation_included")
    # Evaluated pixels must be indices 0 (SCL 6), 1 (SCL 5), and 2 (SCL 4) -> 3 pixels
    assert res_sec["confusion_matrix"]["total_evaluated_pixels"] == 3
    # Pixel 0: SAR=1, Ref=1 -> TP
    # Pixel 1: SAR=0, Ref=0 -> TN
    # Pixel 2: SAR=1, Ref=0 (veg non-water) -> FP
    assert res_sec["confusion_matrix"]["true_positive"] == 1
    assert res_sec["confusion_matrix"]["true_negative"] == 1
    assert res_sec["confusion_matrix"]["false_positive"] == 1
    assert res_sec["confusion_matrix"]["false_negative"] == 0


def test_confusion_matrix_and_metrics_calculation():
    """
    Verify exact mathematical correctness of Precision, Recall, F1, IoU, Specificity,
    and Balanced Accuracy on a known synthetic confusion matrix.
    """
    aoi_mask = np.ones((1, 4), dtype=bool)
    # SAR: 1 (water), 1 (water), 0 (non-water), 0 (non-water)
    sar_mask = np.array([[1, 1, 0, 0]], dtype=np.uint8)
    # Ref SCL: 6 (water), 5 (bare), 6 (water), 5 (bare)
    # Pixel 0: SAR=1, Ref=6 -> TP
    # Pixel 1: SAR=1, Ref=5 -> FP
    # Pixel 2: SAR=0, Ref=6 -> FN
    # Pixel 3: SAR=0, Ref=5 -> TN
    optical_scl = np.array([[6, 5, 6, 5]], dtype=np.uint8)

    res = compute_confusion_matrix_and_metrics(sar_mask, optical_scl, aoi_mask, mode="primary_strict")
    cm = res["confusion_matrix"]
    assert cm["true_positive"] == 1
    assert cm["false_positive"] == 1
    assert cm["false_negative"] == 1
    assert cm["true_negative"] == 1
    assert cm["total_evaluated_pixels"] == 4

    metrics = res["agreement_metrics"]
    # Precision = 1 / (1 + 1) = 0.5000
    assert abs(metrics["precision"] - 0.5) < 1e-4
    # Recall = 1 / (1 + 1) = 0.5000
    assert abs(metrics["recall"] - 0.5) < 1e-4
    # F1 = 2 * (0.5 * 0.5) / (0.5 + 0.5) = 0.5000
    assert abs(metrics["f1_score"] - 0.5) < 1e-4
    # IoU = 1 / (1 + 1 + 1) = 0.3333
    assert abs(metrics["iou"] - (1.0 / 3.0)) < 1e-4
    # Specificity = 1 / (1 + 1) = 0.5000
    assert abs(metrics["specificity"] - 0.5) < 1e-4
    # Balanced Accuracy = 0.5 * (0.5 + 0.5) = 0.5000
    assert abs(metrics["balanced_accuracy"] - 0.5) < 1e-4


def test_exclusion_handling_sar_indeterminate_and_nodata():
    """
    Verify that SAR Category 2 (indeterminate clipping floor) and Category 3
    (source NoData / invalid) are strictly quarantined from evaluation.
    """
    aoi_mask = np.ones((1, 4), dtype=bool)
    # SAR mask has: 2 (clipping floor), 3 (NoData), 1 (water), 0 (non-water)
    sar_mask = np.array([[2, 3, 1, 0]], dtype=np.uint8)
    # Optical has clear water (6) and clear bare ground (5)
    optical_scl = np.array([[6, 5, 6, 5]], dtype=np.uint8)

    res = compute_confusion_matrix_and_metrics(sar_mask, optical_scl, aoi_mask, mode="primary_strict")
    # Categories 2 and 3 must be excluded
    assert res["confusion_matrix"]["total_evaluated_pixels"] == 2
    assert res["confusion_matrix"]["true_positive"] == 1
    assert res["confusion_matrix"]["true_negative"] == 1
    assert res["confusion_matrix"]["false_positive"] == 0
    assert res["confusion_matrix"]["false_negative"] == 0
    assert res["aoi_exclusions"]["sar_indeterminate_clipping_floor"] == 1
    assert res["aoi_exclusions"]["sar_nodata"] == 1


def test_spatial_block_statistics_and_bootstrapping():
    """
    Verify spatial block analysis, minimum pixel thresholding, and deterministic
    1000-iteration block bootstrap confidence intervals.
    """
    # 100 x 100 array with 2x2 50-pixel blocks
    aoi_mask = np.ones((100, 100), dtype=bool)
    sar_mask = np.zeros((100, 100), dtype=np.uint8)
    optical_scl = np.full((100, 100), 5, dtype=np.uint8)

    # Block (0,0): 50x50 = 2500 pixels, set 1000 water in both -> TP=1000, TN=1500
    sar_mask[0:50, 0:50][:20, :50] = 1
    optical_scl[0:50, 0:50][:20, :50] = 6

    # Block (0,1): Make all pixels cloud (SCL 8) -> Evaluated = 0, should be skipped
    optical_scl[0:50, 50:100] = 8

    # Block (1,0): Make only 50 pixels evaluated (below min_pixels_threshold=100) -> should be skipped
    optical_scl[50:100, 0:50] = 8
    optical_scl[50:100, 0:50][:1, :50] = 5

    # Block (1,1): 2500 evaluated pixels, 500 water, 2000 bare -> evaluable
    sar_mask[50:100, 50:100][:10, :50] = 1
    optical_scl[50:100, 50:100][:10, :50] = 6

    blocks, summary = compute_spatial_block_statistics(
        sar_mask, optical_scl, aoi_mask, block_size_px=50, min_pixels_threshold=100, n_bootstrap=200, random_seed=42
    )

    # Only blocks meeting min_pixels_threshold=100 and containing both water and non-water should be evaluable
    assert summary["evaluable_blocks_count"] == 2
    assert "bootstrap_uncertainty_95ci" in summary
    boot = summary["bootstrap_uncertainty_95ci"]
    # Guard verification: With only 2 blocks (< 20 threshold), notice is emitted
    assert "notice" in boot
    assert "Insufficient evaluable spatial blocks" in boot["notice"]

    # Test with >= 20 evaluable blocks (e.g., 5x5 grid of 10-pixel blocks on 50x50 array)
    aoi_grid = np.ones((50, 50), dtype=bool)
    sar_grid = np.zeros((50, 50), dtype=np.uint8)
    opt_grid = np.full((50, 50), 5, dtype=np.uint8)

    # In every 10x10 block, create some water (SCL 6) and bare ground (SCL 5)
    for r in range(0, 50, 10):
        for c in range(0, 50, 10):
            sar_grid[r:r+5, c:c+10] = 1
            opt_grid[r:r+5, c:c+10] = 6

    blocks_multi, summary_multi = compute_spatial_block_statistics(
        sar_grid, opt_grid, aoi_grid, block_size_px=10, min_pixels_threshold=50, n_bootstrap=100, random_seed=42
    )
    assert summary_multi["evaluable_blocks_count"] == 25
    boot_multi = summary_multi["bootstrap_uncertainty_95ci"]
    assert "precision_ci_95" in boot_multi
    assert "recall_ci_95" in boot_multi
    assert "f1_score_ci_95" in boot_multi
    assert "iou_ci_95" in boot_multi


def test_phase4d_output_artifacts_and_metadata(project_root: Path, master_metadata_json: dict):
    """
    Verify that all required Phase 4D outputs exist, CSVs have proper headers,
    maps are high resolution, and July is formally designated as PARTIALLY_EVALUABLE.
    """
    # 1. Output CSV files
    stats_dir = project_root / "data/outputs/phase4d/statistics"
    expected_csvs = [
        "phase4d_confusion_matrices.csv",
        "phase4d_agreement_metrics.csv",
        "phase4d_spatial_block_statistics.csv",
        "phase4d_reference_coverage.csv",
        "phase4d_method_sensitivity.csv",
        "phase4d_uncertainty_statistics.csv",
    ]
    for csv_name in expected_csvs:
        p = stats_dir / csv_name
        assert p.exists(), f"Expected CSV missing: {p}"
        assert p.stat().st_size > 0

    # 2. Map PNG files
    maps_dir = project_root / "data/outputs/phase4d/maps"
    june_map = maps_dir / "phase4d_june10_optical_agreement_map.png"
    july_map = maps_dir / "phase4d_july16_optical_agreement_map.png"
    assert june_map.exists() and june_map.stat().st_size > 100_000
    assert july_map.exists() and july_map.stat().st_size > 100_000

    # 3. Master JSON verification
    meta = master_metadata_json
    assert "4D" in meta["phase"] and "Independent Optical Validation" in meta["phase"]
    evals = meta["evaluations"]
    assert "evaluation_a_baseline_june" in evals
    assert "evaluation_b_flood_peak_july" in evals

    # Coverage verification
    june_cov = evals["evaluation_a_baseline_june"]["primary_strict"]["confusion_matrix"]["aoi_coverage_pct"]
    assert abs(june_cov - 53.59) < 0.1

    july_cov = evals["evaluation_b_flood_peak_july"]["primary_strict"]["confusion_matrix"]["aoi_coverage_pct"]
    assert abs(july_cov - 11.83) < 0.1

    # July partial evaluability status
    july_status = evals["evaluation_b_flood_peak_july"]["spatial_block_summary"]["spatial_representativeness_status"]
    assert july_status == "PARTIALLY_EVALUABLE"


def test_scientific_terminology_standards(master_metadata_json: dict):
    """
    Enforce scientific rigor: ensure reports and metadata adopt 'optical-reference agreement'
    and explicitly disclaim 'ground-truth accuracy'.
    """
    concl = master_metadata_json["scientific_conclusions"]
    term = concl["terminology_standard"]
    assert "optical_reference_agreement" in term
    assert "NOT ground_truth_accuracy" in term or "not ground-truth accuracy" in term.lower()
