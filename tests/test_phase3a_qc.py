#!/usr/bin/env python3
"""
Unit tests for Earth Pulse Phase 3A.1: Classification Quality Audit & Correction.
Covers all 10 required test topics using synthetic arrays and GDAL rasters.
"""

from pathlib import Path
import tempfile
import numpy as np
import pytest
from osgeo import gdal, ogr, osr

# Robust dual-resolution import pattern
try:
    from scripts.audit_phase3a import (
        generate_candidate_mask_corrected,
        assess_classification_metrics_corrected,
        analyze_2d_quadrants,
        verify_kittler_illingworth_physics,
        CAT_VALID_ORDINARY,
        CAT_SOURCE_NODATA,
        CAT_SNAP_CLIPPING_FLOOR,
        CAT_OTHER_INVALID,
        MASK_NON_WATER,
        MASK_CANDIDATE_WATER,
        MASK_INDETERMINATE,
        MASK_NODATA_INVALID,
        MASK_AMBIGUOUS_DISCORDANT,
        PIXEL_SPACING_M,
        PIXEL_AREA_KM2,
        PIXEL_AREA_HA,
    )
except ImportError:
    from audit_phase3a import (
        generate_candidate_mask_corrected,
        assess_classification_metrics_corrected,
        analyze_2d_quadrants,
        verify_kittler_illingworth_physics,
        CAT_VALID_ORDINARY,
        CAT_SOURCE_NODATA,
        CAT_SNAP_CLIPPING_FLOOR,
        CAT_OTHER_INVALID,
        MASK_NON_WATER,
        MASK_CANDIDATE_WATER,
        MASK_INDETERMINATE,
        MASK_NODATA_INVALID,
        MASK_AMBIGUOUS_DISCORDANT,
        PIXEL_SPACING_M,
        PIXEL_AREA_KM2,
        PIXEL_AREA_HA,
    )


# 1. Single-polarization clipping-floor preservation
def test_single_polarization_clipping_floor_preservation():
    shape = (4, 4)
    # Linear values
    vv_lin = np.full(shape, 0.01, dtype=np.float32) # ~ -20 dB
    vh_lin = np.full(shape, 0.001, dtype=np.float32) # ~ -30 dB

    q_vh = np.full(shape, CAT_VALID_ORDINARY, dtype=np.uint8)
    q_vv = np.full(shape, CAT_VALID_ORDINARY, dtype=np.uint8)

    # Set clipping floor on specific pixels
    q_vv[1, 1] = CAT_SNAP_CLIPPING_FLOOR
    q_vh[2, 2] = CAT_SNAP_CLIPPING_FLOOR

    # For VV-only, pixel (1, 1) MUST be Category 2 (Indeterminate), while (2, 2) is ordinary
    mask_vv = generate_candidate_mask_corrected(vh_lin, vv_lin, q_vh, q_vv, "vv_only", threshold_vv=-12.0)
    assert mask_vv[1, 1] == MASK_INDETERMINATE
    assert mask_vv[2, 2] == MASK_CANDIDATE_WATER

    # For VH-only, pixel (2, 2) MUST be Category 2 (Indeterminate), while (1, 1) is ordinary
    mask_vh = generate_candidate_mask_corrected(vh_lin, vv_lin, q_vh, q_vv, "vh_only", threshold_vh=-20.0)
    assert mask_vh[2, 2] == MASK_INDETERMINATE
    assert mask_vh[1, 1] == MASK_CANDIDATE_WATER


# 2. Dual-polarization quality-mask logic
def test_dual_polarization_quality_mask_logic():
    shape = (2, 2)
    vv_lin = np.full(shape, 0.01, dtype=np.float32)
    vh_lin = np.full(shape, 0.001, dtype=np.float32)

    q_vh = np.full(shape, CAT_VALID_ORDINARY, dtype=np.uint8)
    q_vv = np.full(shape, CAT_VALID_ORDINARY, dtype=np.uint8)

    # (0, 0): both valid ordinary
    # (0, 1): VV clipping floor, VH ordinary
    # (1, 0): VV ordinary, VH clipping floor
    # (1, 1): VV NoData, VH ordinary
    q_vv[0, 1] = CAT_SNAP_CLIPPING_FLOOR
    q_vh[1, 0] = CAT_SNAP_CLIPPING_FLOOR
    q_vv[1, 1] = CAT_SOURCE_NODATA

    mask_dual = generate_candidate_mask_corrected(
        vh_lin, vv_lin, q_vh, q_vv, "dual_and", threshold_vv=-12.0, threshold_vh=-20.0
    )

    assert mask_dual[0, 0] == MASK_CANDIDATE_WATER
    assert mask_dual[0, 1] == MASK_INDETERMINATE
    assert mask_dual[1, 0] == MASK_INDETERMINATE
    assert mask_dual[1, 1] == MASK_NODATA_INVALID


# 3. NoData preservation
def test_nodata_preservation():
    shape = (3, 3)
    vv_lin = np.full(shape, -9999.0, dtype=np.float32)
    vh_lin = np.full(shape, -9999.0, dtype=np.float32)
    q_vh = np.full(shape, CAT_SOURCE_NODATA, dtype=np.uint8)
    q_vv = np.full(shape, CAT_SOURCE_NODATA, dtype=np.uint8)

    for m in ["vv_only", "vh_only", "dual_and", "dual_or", "otsu_2d", "cross_ratio"]:
        mask = generate_candidate_mask_corrected(vh_lin, vv_lin, q_vh, q_vv, m, threshold_vv=-12.0, threshold_vh=-20.0, threshold_2d=(-12.0, -20.0), threshold_cr=-10.0)
        assert np.all(mask == MASK_NODATA_INVALID)


# 4. Four-quadrant observation conservation
def test_four_quadrant_observation_conservation():
    np.random.seed(42)
    n = 5000
    vv_lin = 10.0 ** (np.random.normal(-12.0, 3.0, (n, 1)) / 10.0)
    vh_lin = 10.0 ** (np.random.normal(-20.0, 3.0, (n, 1)) / 10.0)
    q = np.full(vv_lin.shape, CAT_VALID_ORDINARY, dtype=np.uint8)
    aoi = np.ones(vv_lin.shape, dtype=bool)

    t_vv = -12.0
    t_vh = -20.0

    quad = analyze_2d_quadrants(vv_lin, vh_lin, q, q, aoi, t_vv, t_vh)
    total_quad = (
        quad["q0_water_cells"]
        + quad["q1_land_cells"]
        + quad["q2_discordant_low_vv_high_vh_cells"]
        + quad["q3_discordant_high_vv_low_vh_cells"]
    )
    assert total_quad == quad["total_valid_cells"] == n
    assert abs((quad["q0_water_pct"] + quad["q1_land_pct"] + quad["q2_discordant_pct"] + quad["q3_discordant_pct"]) - 100.0) < 1e-3


# 5. Ambiguous quadrant classification
def test_ambiguous_quadrant_classification():
    # 4 distinct points representing Q0, Q1, Q2, Q3
    # Q0: VV=-15, VH=-25 (Water)
    # Q1: VV=-8,  VH=-12 (Land)
    # Q2: VV=-15, VH=-12 (Low VV, High VH -> Ambiguous)
    # Q3: VV=-8,  VH=-25 (High VV, Low VH -> Ambiguous)
    vv_lin = 10.0 ** (np.array([-15.0, -8.0, -15.0, -8.0], dtype=np.float32) / 10.0)
    vh_lin = 10.0 ** (np.array([-25.0, -12.0, -12.0, -25.0], dtype=np.float32) / 10.0)
    q = np.full(4, CAT_VALID_ORDINARY, dtype=np.uint8)

    t_2d = (-12.0, -20.0)
    mask = generate_candidate_mask_corrected(vh_lin, vv_lin, q, q, "otsu_2d", threshold_2d=t_2d)

    assert mask[0] == MASK_CANDIDATE_WATER
    assert mask[1] == MASK_NON_WATER
    assert mask[2] == MASK_AMBIGUOUS_DISCORDANT
    assert mask[3] == MASK_AMBIGUOUS_DISCORDANT


# 6. KI boundary-minimum rejection
def test_ki_boundary_minimum_rejection():
    np.random.seed(99)
    # Unimodal distribution with long tail -> minimum hits boundary cutoff
    unimodal_tail = np.concatenate([np.random.normal(-10.0, 1.5, 9900), np.random.uniform(-30.0, -25.0, 100)])
    res = verify_kittler_illingworth_physics(unimodal_tail, n_bins=256)
    # Must detect boundary artifact
    assert res["status"] in ["FAILED", "UNSTABLE_NEAR_BOUNDARY"]


# 7. KI numerical correctness and near-equal-variance convergence
def test_ki_numerical_correctness_and_convergence():
    np.random.seed(42)
    # Equal-variance bimodal mixture: N1(-20, 2), N2(-10, 2)
    m1 = np.random.normal(-20.0, 2.0, 5000)
    m2 = np.random.normal(-10.0, 2.0, 5000)
    vals = np.concatenate([m1, m2])

    res = verify_kittler_illingworth_physics(vals, n_bins=256)
    assert res["status"] == "SUCCESS"
    assert res["near_equal_variance"] is True
    assert res["variance_ratio"] < 1.5
    # Should identify threshold near the midpoint -15 dB
    assert -16.0 <= res["threshold"] <= -14.0
    assert abs(res["best_idx"] - res["otsu_idx"]) <= 1


# 8. Candidate pixel-count conservation
def test_candidate_pixel_count_conservation():
    aoi_mask = np.ones((50, 50), dtype=bool) # 2500 cells
    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[:10, :10] = MASK_CANDIDATE_WATER      # 100
    mask[10:20, :10] = MASK_INDETERMINATE       # 100
    mask[20:30, :10] = MASK_NODATA_INVALID      # 100
    mask[30:40, :10] = MASK_AMBIGUOUS_DISCORDANT# 100
    # Remaining 2100 are MASK_NON_WATER (0)

    stat = assess_classification_metrics_corrected(mask, aoi_mask, pixel_size_m=20.0)
    total_sum = (
        stat["candidate_water_cells"]
        + stat["candidate_non_water_cells"]
        + stat["indeterminate_cells"]
        + stat["nodata_cells"]
        + stat["ambiguous_discordant_cells"]
    )
    assert total_sum == stat["total_aoi_cells"] == 2500
    assert stat["valid_ordinary_cells"] == (2500 - 100 - 100) # 2300


# 9. Area calculations
def test_area_calculations():
    aoi_mask = np.ones((10, 10), dtype=bool) # 100 cells
    mask = np.full((10, 10), MASK_NON_WATER, dtype=np.uint8)
    mask[:5, :5] = MASK_CANDIDATE_WATER # 25 cells

    stat = assess_classification_metrics_corrected(mask, aoi_mask, pixel_size_m=20.0)
    # 25 cells * 400 m2 = 10,000 m2 = 1.0 ha = 0.01 km2
    assert abs(stat["candidate_water_area_ha"] - 1.0) < 1e-4
    assert abs(stat["candidate_water_area_km2"] - 0.01) < 1e-6


# 10. Deterministic mask generation
def test_deterministic_mask_generation():
    vv_lin = np.array([0.001, 0.05, 0.002, 0.04], dtype=np.float32)
    vh_lin = np.array([0.0001, 0.01, 0.0002, 0.008], dtype=np.float32)
    q = np.full(4, CAT_VALID_ORDINARY, dtype=np.uint8)

    m1 = generate_candidate_mask_corrected(vh_lin, vv_lin, q, q, "dual_and", threshold_vv=-15.0, threshold_vh=-22.0)
    m2 = generate_candidate_mask_corrected(vh_lin, vv_lin, q, q, "dual_and", threshold_vv=-15.0, threshold_vh=-22.0)

    assert np.array_equal(m1, m2)
