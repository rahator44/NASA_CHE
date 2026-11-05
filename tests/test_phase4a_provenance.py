"""
Automated Test Suite for Phase 4A.1: Scientific Provenance and Validation Assumption Audit
Earth Pulse: Dancing with the SARs (NASA Space Apps Challenge 2026)

Tests cover:
1. Rejection of unverified gauge values.
2. Rejection of unverified danger levels.
3. Rejection of unsupported elevation thresholds.
4. Reference provenance requirements (including quality information).
5. Optical uncertainty masking.
6. Anti-circular validation guard.
7. Missing-reference-data status.
8. Validation metrics with incomplete class coverage.
"""

from pathlib import Path
import numpy as np
import pytest

from scripts.validate_reference_data import (
    find_project_root,
    compute_validation_metrics,
    scan_local_reference_inventory,
    validate_reference_dataset_provenance,
    validate_gauge_reading_input,
    validate_terrain_threshold_input,
    STATUS_BLOCKED_MISSING_DATA,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return find_project_root()


# Test 1: Rejection of unverified gauge values
def test_rejection_of_unverified_gauge_values():
    """Verify that unverified gauge records lacking provider verification or citations are rejected."""
    unverified_record = {
        "station_id": "SW46.9A",
        "station_name": "Kazipur",
        "timestamp_utc": "2024-07-16T06:00:00Z",
        "water_level_m": 15.42,
        "vertical_datum": "PWD",
        "provider_verified": False,  # Unverified!
        "source_citation": "UNVERIFIED",  # No citation!
    }
    is_valid, errors = validate_gauge_reading_input(unverified_record)
    assert is_valid is False
    assert any("UNVERIFIED_GAUGE_DATA_REJECTED" in e for e in errors)

    # Valid gauge record for contrast
    verified_record = {
        "station_id": "SW46.9A",
        "station_name": "Kazipur",
        "timestamp_utc": "2024-07-16T06:00:00Z",
        "water_level_m": 15.42,
        "vertical_datum": "PWD",
        "provider_verified": True,
        "source_citation": "BWDB Hydrology Division Daily Bulletin 2024-07-16",
    }
    is_valid_v, errors_v = validate_gauge_reading_input(verified_record)
    assert is_valid_v is True
    assert len(errors_v) == 0


# Test 2: Rejection of unverified danger levels
def test_rejection_of_unverified_danger_levels():
    """Verify that danger levels without official published citations are rejected."""
    record_unverified_dl = {
        "station_id": "SW46.9",
        "station_name": "Sirajganj",
        "timestamp_utc": "2024-07-16T06:00:00Z",
        "water_level_m": 13.50,
        "vertical_datum": "PWD",
        "provider_verified": True,
        "source_citation": "BWDB Bulletin 2024-07-16",
        "danger_level_m": 13.35,
        "danger_level_citation": "UNVERIFIED",  # Unverified danger level citation!
    }
    is_valid, errors = validate_gauge_reading_input(record_unverified_dl)
    assert is_valid is False
    assert any("UNVERIFIED_DANGER_LEVEL_REJECTED" in e for e in errors)


# Test 3: Rejection of unsupported elevation thresholds
def test_rejection_of_unsupported_elevation_thresholds():
    """Verify that uncalibrated elevation or HAND thresholds are rejected without local calibrated DEM."""
    # Attempting to apply 11-18m and 3m HAND threshold without local calibrated DEM
    unsupported_terrain = {
        "dem_path": "",  # Missing DEM!
        "elevation_range_m": [11.0, 18.0],
        "hand_threshold_m": 3.0,
        "dem_provenance_verified": False,
        "elevation_calibration_source": "ASSUMPTION",
        "hand_calibration_source": "ASSUMPTION",
    }
    is_valid, errors = validate_terrain_threshold_input(unsupported_terrain)
    assert is_valid is False
    assert any("UNSUPPORTED_TERRAIN_THRESHOLD_REJECTED" in e for e in errors)


# Test 4: Reference provenance requirements
def test_reference_provenance_requirements():
    """Verify that reference dataset validator enforces quality information and required attributes."""
    complete_meta = {
        "dataset_name": "Sentinel-2 MSI Water Mask",
        "category": "optical",
        "provider": "ESA Copernicus",
        "source_identifier": "S2A_MSIL2A_20240715",
        "source_url_or_citation": "https://dataspace.copernicus.eu",
        "original_acquisition_date": "2024-07-15",
        "spatial_extent_wkt": "POLYGON((89.5 24.5, 89.8 24.5, 89.8 24.8, 89.5 24.8, 89.5 24.5))",
        "crs": "EPSG:32645",
        "resolution": "20m",
        "processing_history": "MNDWI threshold > 0.0 with SCL cloud masking",
        "license_or_usage_conditions": "CC-BY 4.0 Open Data",
        "intended_validation_purpose": "Optical independent flood extent comparison",
        "local_file_path": "data/reference/optical/s2_20240715_mndwi.tif",
        "quality_information": "SCL cloud probability < 20%, shadow masked, valid pixels = 92%",
    }
    is_valid, errors = validate_reference_dataset_provenance(complete_meta, require_quality_info=True)
    assert is_valid is True
    assert len(errors) == 0

    # Missing quality information
    incomplete_meta = dict(complete_meta)
    del incomplete_meta["quality_information"]
    is_valid_inc, errors_inc = validate_reference_dataset_provenance(incomplete_meta, require_quality_info=True)
    assert is_valid_inc is False
    assert any("quality_information" in e for e in errors_inc)


# Test 5: Optical uncertainty masking
def test_optical_uncertainty_masking():
    """Verify that optical cloud/shadow pixels (254) and NoData (255) are strictly excluded."""
    # 4 pixels:
    # idx 0: C=1, R=1 -> TP
    # idx 1: C=0, R=0 -> TN
    # idx 2: C=1, R=254 (Optical cloud/shadow uncertain) -> EXCLUDED
    # idx 3: C=0, R=255 (Optical out-of-swath NoData) -> EXCLUDED
    cand = np.array([1, 0, 1, 0], dtype=np.uint8)
    ref = np.array([1, 0, 254, 255], dtype=np.uint16)

    res = compute_validation_metrics(cand, ref)
    assert res["valid_comparison_pixels"] == 2
    assert res["excluded_reference_uncertain"] == 1
    assert res["excluded_reference_nodata"] == 1
    assert res["confusion_matrix"]["true_positive"] == 1
    assert res["confusion_matrix"]["true_negative"] == 1
    assert res["confusion_matrix"]["false_positive"] == 0
    assert res["confusion_matrix"]["false_negative"] == 0


# Test 6: Anti-circular validation guard
def test_anti_circular_validation_guard():
    """Verify that SAR-derived masks cannot be passed as independent ground truth."""
    sar_reference_attempt = {
        "dataset_name": "Sentinel-1 Otsu Classification",
        "category": "optical",
        "provider": "Self",
        "source_url_or_citation": "Local SAR run",
        "original_acquisition_date": "2024-07-16",
        "spatial_extent_wkt": "POLYGON(...)",
        "crs": "EPSG:32645",
        "resolution": "20m",
        "processing_history": "SAR Lee 5x5 Otsu thresholding",
        "license_or_usage_conditions": "Internal",
        "intended_validation_purpose": "Validation",
        "local_file_path": "data/processed/phase3a_qc/candidate_masks/july16_lee_5x5_otsu_dual_and_qc.tif",
        "quality_information": "Phase 3A quality mask applied",
    }
    is_valid, errors = validate_reference_dataset_provenance(sar_reference_attempt)
    assert is_valid is False
    assert any("CIRCULAR_VALIDATION_ERROR" in e for e in errors)


# Test 7: Missing-reference-data status
def test_missing_reference_data_status(tmp_path: Path):
    """Verify scan_local_reference_inventory correctly reports BLOCKED_REFERENCE_DATA_MISSING."""
    inv = scan_local_reference_inventory(tmp_path)
    assert inv["status"] == STATUS_BLOCKED_MISSING_DATA
    assert inv["total_independent_reference_files"] == 0
    assert "BLOCKED" in inv["blocking_notice"]


# Test 8: Validation metrics with incomplete class coverage
def test_validation_metrics_incomplete_class_coverage():
    """
    Verify zero-division handling and documentation when one validation class is completely absent.
    Case A: Reference has 0 water pixels (pure dry land).
    Case B: Candidate has 0 water predictions.
    """
    # Case A: Reference has 0 water pixels (TN=5, FP=2, TP=0, FN=0)
    cand_a = np.array([1, 1, 0, 0, 0, 0, 0], dtype=np.uint8)
    ref_a = np.array([0, 0, 0, 0, 0, 0, 0], dtype=np.uint8)

    res_a = compute_validation_metrics(cand_a, ref_a)
    flags_a = res_a["class_distribution_flags"]
    assert flags_a["positive_reference_count"] == 0
    assert flags_a["recall_undefined"] is True
    assert flags_a["class_coverage_complete"] is False
    assert any("Recall undefined" in n for n in flags_a["notes"])
    assert res_a["metrics"]["recall"] == 0.0

    # Case B: Candidate has 0 water predictions (TN=5, FN=2, TP=0, FP=0)
    cand_b = np.array([0, 0, 0, 0, 0, 0, 0], dtype=np.uint8)
    ref_b = np.array([1, 1, 0, 0, 0, 0, 0], dtype=np.uint8)

    res_b = compute_validation_metrics(cand_b, ref_b)
    flags_b = res_b["class_distribution_flags"]
    assert flags_b["positive_predictions_count"] == 0
    assert flags_b["precision_undefined"] is True
    assert flags_b["class_coverage_complete"] is False
    assert any("Precision undefined" in n for n in flags_b["notes"])
    assert res_b["metrics"]["precision"] == 0.0

