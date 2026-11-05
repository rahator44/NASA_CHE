"""
Automated Test Suite for Phase 4A: Independent Flood Validation Framework
Earth Pulse: Dancing with the SARs (NASA Space Apps Challenge 2026)

Tests cover:
1. Confusion-matrix calculations.
2. Precision and recall.
3. F1-score.
4. IoU.
5. Specificity.
6. Balanced accuracy.
7. NoData exclusion.
8. Uncertain-pixel exclusion.
9. Spatial-grid compatibility.
10. Missing-reference-data handling.
11. Provenance validation.
12. Rejection of SAR-derived masks as independent ground truth.
"""

from pathlib import Path
import numpy as np
import pytest

from scripts.validate_reference_data import (
    find_project_root,
    compute_validation_metrics,
    scan_local_reference_inventory,
    validate_reference_dataset_provenance,
    audit_phase3b_results,
    STATUS_BLOCKED_MISSING_DATA,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return find_project_root()


# Test 1: Confusion-matrix calculations
def test_confusion_matrix_calculation():
    """Verify exact calculation of TP, FP, TN, and FN."""
    # candidate: 1, 1, 0, 0, 1, 0
    # reference: 1, 0, 1, 0, 1, 0
    # idx 0: C=1, R=1 -> TP
    # idx 1: C=1, R=0 -> FP
    # idx 2: C=0, R=1 -> FN
    # idx 3: C=0, R=0 -> TN
    # idx 4: C=1, R=1 -> TP
    # idx 5: C=0, R=0 -> TN
    # TP=2, FP=1, TN=2, FN=1
    cand = np.array([1, 1, 0, 0, 1, 0], dtype=np.uint8)
    ref = np.array([1, 0, 1, 0, 1, 0], dtype=np.uint8)

    res = compute_validation_metrics(cand, ref)
    cm = res["confusion_matrix"]
    assert cm["true_positive"] == 2
    assert cm["false_positive"] == 1
    assert cm["true_negative"] == 2
    assert cm["false_negative"] == 1


# Test 2: Precision and recall
def test_precision_and_recall():
    """Verify precision = TP/(TP+FP) and recall = TP/(TP+FN)."""
    cand = np.array([1, 1, 0, 0, 1, 0], dtype=np.uint8)
    ref = np.array([1, 0, 1, 0, 1, 0], dtype=np.uint8)
    # TP=2, FP=1, FN=1 -> precision=2/3 (~0.6667), recall=2/3 (~0.6667)
    res = compute_validation_metrics(cand, ref)
    m = res["metrics"]
    assert abs(m["precision"] - (2.0 / 3.0)) < 1e-4
    assert abs(m["recall"] - (2.0 / 3.0)) < 1e-4

    # Edge case: No positive predictions (TP=0, FP=0) -> Precision should be 0.0, not NaN
    cand_zero = np.array([0, 0, 0], dtype=np.uint8)
    ref_pos = np.array([1, 1, 0], dtype=np.uint8)
    res_zero = compute_validation_metrics(cand_zero, ref_pos)
    assert res_zero["metrics"]["precision"] == 0.0
    assert res_zero["metrics"]["recall"] == 0.0


# Test 3: F1-score
def test_f1_score():
    """Verify F1 = 2*P*R / (P+R)."""
    cand = np.array([1, 1, 1, 0], dtype=np.uint8)
    ref = np.array([1, 1, 0, 0], dtype=np.uint8)
    # TP=2, FP=1, TN=1, FN=0 -> P = 2/3, R = 2/2 = 1.0
    # F1 = 2 * (2/3) * 1 / (2/3 + 1) = (4/3) / (5/3) = 4/5 = 0.8
    res = compute_validation_metrics(cand, ref)
    assert abs(res["metrics"]["f1_score"] - 0.8) < 1e-4


# Test 4: IoU (Jaccard Index)
def test_iou_calculation():
    """Verify IoU = TP / (TP + FP + FN)."""
    cand = np.array([1, 1, 1, 0], dtype=np.uint8)
    ref = np.array([1, 1, 0, 0], dtype=np.uint8)
    # TP=2, FP=1, FN=0 -> IoU = 2 / (2 + 1 + 0) = 2/3 (~0.6667)
    res = compute_validation_metrics(cand, ref)
    assert abs(res["metrics"]["intersection_over_union"] - (2.0 / 3.0)) < 1e-4


# Test 5: Specificity
def test_specificity():
    """Verify Specificity = TN / (TN + FP)."""
    cand = np.array([1, 1, 0, 0, 0], dtype=np.uint8)
    ref = np.array([1, 0, 0, 0, 0], dtype=np.uint8)
    # TP=1, FP=1, TN=3, FN=0 -> Specificity = 3 / (3 + 1) = 0.75
    res = compute_validation_metrics(cand, ref)
    assert abs(res["metrics"]["specificity"] - 0.75) < 1e-4


# Test 6: Balanced accuracy
def test_balanced_accuracy():
    """Verify Balanced Accuracy = (Recall + Specificity) / 2."""
    cand = np.array([1, 1, 0, 0, 0], dtype=np.uint8)
    ref = np.array([1, 0, 0, 0, 0], dtype=np.uint8)
    # Recall = 1.0, Specificity = 0.75 -> Balanced Acc = 1.75 / 2 = 0.875
    res = compute_validation_metrics(cand, ref)
    assert abs(res["metrics"]["balanced_accuracy"] - 0.875) < 1e-4


# Test 7: NoData exclusion
def test_nodata_exclusion():
    """Verify candidate NoData (6) and reference NoData (255) are excluded from evaluation."""
    cand = np.array([1, 0, 6, 1, 0], dtype=np.uint8)
    ref = np.array([1, 0, 1, 255, -9999], dtype=np.int16)
    # idx 0: valid (C=1, R=1) -> TP
    # idx 1: valid (C=0, R=0) -> TN
    # idx 2: cand is 6 (NoData) -> EXCLUDED
    # idx 3: ref is 255 (NoData) -> EXCLUDED
    # idx 4: ref is -9999 (NoData) -> EXCLUDED
    # Valid = 2
    res = compute_validation_metrics(cand, ref)
    assert res["valid_comparison_pixels"] == 2
    assert res["excluded_candidate_nodata"] == 1
    assert res["excluded_reference_nodata"] == 2
    assert res["confusion_matrix"]["true_positive"] == 1
    assert res["confusion_matrix"]["true_negative"] == 1


# Test 8: Uncertain-pixel exclusion
def test_uncertain_pixel_exclusion():
    """Verify candidate Indeterminate (5) and reference Uncertain (254) are excluded."""
    cand = np.array([1, 0, 5, 0], dtype=np.uint8)
    ref = np.array([1, 0, 1, 254], dtype=np.uint16)
    # idx 0: TP
    # idx 1: TN
    # idx 2: C=5 (Indeterminate) -> EXCLUDED
    # idx 3: R=254 (Uncertain cloud/shadow) -> EXCLUDED
    res = compute_validation_metrics(cand, ref)
    assert res["valid_comparison_pixels"] == 2
    assert res["excluded_candidate_indeterminate"] == 1
    assert res["excluded_reference_uncertain"] == 1


# Test 9: Spatial-grid compatibility
def test_spatial_grid_compatibility():
    """Verify that shape mismatch raises an assertion error."""
    cand = np.ones((10, 10), dtype=np.uint8)
    ref = np.ones((10, 12), dtype=np.uint8)

    with pytest.raises(AssertionError, match="Shape mismatch"):
        compute_validation_metrics(cand, ref)


# Test 10: Missing-reference-data handling
def test_missing_reference_data_handling(tmp_path: Path):
    """Verify scan_local_reference_inventory returns BLOCKED_REFERENCE_DATA_MISSING when empty."""
    inv = scan_local_reference_inventory(tmp_path)
    assert inv["status"] == STATUS_BLOCKED_MISSING_DATA
    assert inv["total_independent_reference_files"] == 0
    assert "BLOCKED" in inv["blocking_notice"]


# Test 11: Provenance validation
def test_provenance_validation():
    """Verify that metadata validator checks for required provenance attributes."""
    valid_meta = {
        "dataset_name": "Sentinel-2 MSI Level-2A",
        "category": "optical",
        "provider": "Copernicus ESA",
        "source_url_or_citation": "https://dataspace.copernicus.eu",
        "acquisition_date_or_interval": "2024-07-15",
        "spatial_extent_wkt": "POLYGON((89.5 24.5, 89.8 24.5, 89.8 24.8, 89.5 24.8, 89.5 24.5))",
        "crs": "EPSG:32645",
        "resolution": "20m",
        "processing_method": "MNDWI thresholding with SCL cloud masking",
        "license_or_usage_conditions": "CC-BY 4.0 Open Data",
        "intended_validation_purpose": "Optical independent flood extent comparison",
        "local_file_path": "data/reference/optical/s2_20240715_mndwi.tif",
    }
    is_valid, errors = validate_reference_dataset_provenance(valid_meta)
    assert is_valid is True
    assert len(errors) == 0

    # Incomplete metadata
    invalid_meta = {"dataset_name": "Incomplete"}
    is_valid2, errors2 = validate_reference_dataset_provenance(invalid_meta)
    assert is_valid2 is False
    assert len(errors2) > 0


# Test 12: Rejection of SAR-derived masks as independent ground truth
def test_rejection_of_sar_derived_masks():
    """Verify that circular validation using SAR masks is strictly prohibited."""
    circular_meta = {
        "dataset_name": "Sentinel-1 Otsu Water Mask",
        "category": "optical",
        "provider": "Self",
        "source_url_or_citation": "EarthPulse internal",
        "acquisition_date_or_interval": "2024-07-16",
        "spatial_extent_wkt": "POLYGON(...)",
        "crs": "EPSG:32645",
        "resolution": "20m",
        "processing_method": "SAR Lee 5x5 Otsu thresholding",
        "license_or_usage_conditions": "Internal",
        "intended_validation_purpose": "Validation",
        "local_file_path": "data/processed/phase3a_qc/candidate_masks/july16_lee_5x5_otsu_dual_and_qc.tif",
    }
    is_valid, errors = validate_reference_dataset_provenance(circular_meta)
    assert is_valid is False
    assert any("CIRCULAR_VALIDATION_ERROR" in e for e in errors)

