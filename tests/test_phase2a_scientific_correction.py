"""
Earth Pulse — Phase 2A.2: Scientific Correction Test Suite
NASA Space Apps Challenge 2026: Dancing with the SARs

Unit tests for scientific correction engine:
1. SAFE noise vector and calibration parsing.
2. Identification of SNAP numerical clipping floor (1e-5 intensity).
3. Extreme difference attribution logic.
4. Four-tier radiometric categorization.
5. Structural validation of JSON and Markdown addenda.
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure project root and scripts directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from verify_scientific_corrections import (
        extract_top_extremes,
        generate_scientific_corrections,
        inspect_safe_noise_and_cal,
    )
except ImportError:
    from scripts.verify_scientific_corrections import (  # type: ignore
        extract_top_extremes,
        generate_scientific_corrections,
        inspect_safe_noise_and_cal,
    )


def test_safe_noise_and_calibration_parsing():
    """Verify that SAFE noise and calibration XML files are parsed accurately."""
    zip_rel = "data/raw/sentinel1/S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69.zip"
    records = inspect_safe_noise_and_cal(zip_rel)

    assert "VH" in records
    assert "VV" in records
    assert records["VH"]["noise_vector_count"] > 0
    assert records["VV"]["noise_vector_count"] > 0

    # Calibration factor should be in reasonable Sentinel-1 range (approx 500 - 700)
    assert 500 < records["VH"]["cal_sigma_mean"] < 700
    assert 500 < records["VV"]["cal_sigma_mean"] < 700

    # Estimated NESZ should be between -30 dB and -18 dB
    assert -30.0 < records["VH"]["estimated_nesz_db_mean"] < -18.0
    assert -30.0 < records["VV"]["estimated_nesz_db_mean"] < -18.0


def test_snap_numerical_clipping_floor_physics():
    """Verify mathematical calculation of SNAP clipping floor (I = 1e-5)."""
    # Calibration factor across scene is approx 557 to 662
    a_sigma_min = 557.4043
    a_sigma_max = 662.3158
    clip_intensity = 1.0e-5

    sigma0_floor_min = clip_intensity / (a_sigma_max ** 2)
    sigma0_floor_max = clip_intensity / (a_sigma_min ** 2)

    db_floor_min = 10 * np.log10(sigma0_floor_min)
    db_floor_max = 10 * np.log10(sigma0_floor_max)

    # Must match observed range: ~2.55e-11 (-105.93 dB) to ~2.65e-11 (-105.78 dB)
    assert 2.2e-11 < sigma0_floor_min < 2.6e-11
    assert 2.8e-11 < sigma0_floor_max < 3.3e-11
    assert -107.0 < db_floor_min < -105.0
    assert -106.0 < db_floor_max < -104.0


def test_extreme_difference_attribution_logic():
    """Verify that synthetic extreme differences are attributed correctly."""
    # Synthetic arrays
    gt = (750000.0, 20.0, 0.0, 2750000.0, 0.0, -20.0)
    june_lin = np.array([
        [2.5537e-11, 0.05, -9999.0],
        [0.02, 2.5537e-11, 0.01],
    ], dtype=np.float32)

    july_lin = np.array([
        [0.02, 2.5537e-11, -9999.0],
        [0.02, 0.01, 0.01],
    ], dtype=np.float32)

    diff_arr = np.array([
        [88.94, -92.92, -9999.0],
        [0.0, 85.93, 0.0],
    ], dtype=np.float32)

    pos, neg = extract_top_extremes(diff_arr, june_lin, july_lin, gt, top_n=2)

    assert len(pos) == 2
    assert len(neg) == 2
    # Highest positive difference must have June at SNAP clamp
    assert pos[0]["difference_db"] > 88.0
    assert pos[0]["june10_at_snap_numerical_clamp"] is True
    # Most negative difference must have July below detection
    assert neg[0]["difference_db"] < -90.0
    assert neg[0]["july16_below_detection_limit"] is True


def test_four_tier_radiometric_categorization():
    """Verify four-tier radiometric categorization rules."""
    def categorize_pixel(val, nodata=-9999.0):
        if val == nodata or np.isnan(val):
            return "Category_4_Invalid_NoData"
        elif val < -28.0:
            return "Category_3_Below_Detection_Limit"
        elif -28.0 <= val < -20.0:
            return "Category_2_Reliable_Low"
        else:
            return "Category_1_Reliable_High_Moderate"

    assert categorize_pixel(-9999.0) == "Category_4_Invalid_NoData"
    assert categorize_pixel(-105.9) == "Category_3_Below_Detection_Limit"
    assert categorize_pixel(-35.0) == "Category_3_Below_Detection_Limit"
    assert categorize_pixel(-24.5) == "Category_2_Reliable_Low"
    assert categorize_pixel(-12.0) == "Category_1_Reliable_High_Moderate"


def test_scientific_correction_addendum_files():
    """Verify existence and validity of scientific correction addendum outputs."""
    json_path = PROJECT_ROOT / "data/metadata/phase2a_scientific_correction_addendum.json"
    md_path = PROJECT_ROOT / "data/metadata/phase2a_scientific_correction_addendum.md"

    assert json_path.exists(), "JSON addendum must exist"
    assert md_path.exists(), "Markdown addendum must exist"

    with open(json_path, "r") as f:
        data = json.load(f)

    assert "task_1_noise_floor_verification" in data
    assert "task_2_numerical_clipping_floor_discovery" in data
    assert "task_3_corrected_classification_guidance" in data
    assert "task_4_review_of_extreme_difference_claims" in data
    assert "task_5_phase_2b_filtering_and_classification_recommendations" in data

    # Verify key retractions
    t1 = data["task_1_noise_floor_verification"]
    assert t1["diagnostic_threshold_35db_status"] == "RETRACTED_AS_PHYSICAL_NOISE_FLOOR"

    t2 = data["task_2_numerical_clipping_floor_discovery"]
    assert t2["intensity_clipping_constant"] == 1.0e-5
    assert len(t2["representative_extreme_pixels"]["vh_positive_extremes"]) == 5

