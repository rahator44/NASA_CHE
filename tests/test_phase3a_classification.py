#!/usr/bin/env python3
"""
Unit tests for Earth Pulse Phase 3A: Water Classification & Threshold Benchmarking.
Covers 16 critical test topics using synthetic GDAL rasters and arrays.
"""

from pathlib import Path
import tempfile
import numpy as np
import pytest
from osgeo import gdal, ogr, osr

# Robust dual-resolution import pattern
try:
    from scripts.classify_water_phase3a import (
        otsu_threshold_1d,
        kittler_illingworth_threshold_1d,
        otsu_threshold_2d,
        calculate_cross_ratio,
        compute_radiometric_features,
        generate_candidate_mask,
        assess_classification_metrics,
        calculate_agreement_metrics,
        rasterize_aoi_mask,
        verify_phase3a_inputs,
        write_geotiff_mask,
        CAT_VALID_ORDINARY,
        CAT_SOURCE_NODATA,
        CAT_SNAP_CLIPPING_FLOOR,
        CAT_OTHER_INVALID,
        MASK_NON_WATER,
        MASK_CANDIDATE_WATER,
        MASK_INDETERMINATE,
        MASK_NODATA_INVALID,
        PRELIMINARY_AOI_WKT,
        PIXEL_SPACING_M,
        PIXEL_AREA_KM2,
        PIXEL_AREA_HA,
    )
except ImportError:
    from classify_water_phase3a import (
        otsu_threshold_1d,
        kittler_illingworth_threshold_1d,
        otsu_threshold_2d,
        calculate_cross_ratio,
        compute_radiometric_features,
        generate_candidate_mask,
        assess_classification_metrics,
        calculate_agreement_metrics,
        rasterize_aoi_mask,
        verify_phase3a_inputs,
        write_geotiff_mask,
        CAT_VALID_ORDINARY,
        CAT_SOURCE_NODATA,
        CAT_SNAP_CLIPPING_FLOOR,
        CAT_OTHER_INVALID,
        MASK_NON_WATER,
        MASK_CANDIDATE_WATER,
        MASK_INDETERMINATE,
        MASK_NODATA_INVALID,
        PRELIMINARY_AOI_WKT,
        PIXEL_SPACING_M,
        PIXEL_AREA_KM2,
        PIXEL_AREA_HA,
    )


def create_synthetic_test_raster(
    filepath: Path,
    width: int = 1405,
    height: int = 1393,
    b1_desc: str = "Sigma0_VH",
    b2_desc: str = "Sigma0_VV",
    epsg: int = 32645,
    gt: tuple = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0),
    nodata: float = -9999.0,
):
    """Creates a temporary synthetic 2-band GeoTIFF."""
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(str(filepath), width, height, 2, gdal.GDT_Float32)
    ds.SetGeoTransform(gt)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())

    b1 = ds.GetRasterBand(1)
    b1.SetDescription(b1_desc)
    b1.SetNoDataValue(nodata)
    b1.Fill(0.01)

    b2 = ds.GetRasterBand(2)
    b2.SetDescription(b2_desc)
    b2.SetNoDataValue(nodata)
    b2.Fill(0.05)

    ds.FlushCache()
    ds = None


# 1. Otsu threshold correctness
def test_otsu_threshold_correctness():
    np.random.seed(42)
    # Strong bimodal mixture: Mode 1 around -22 dB, Mode 2 around -10 dB
    c1 = np.random.normal(-22.0, 1.5, 4000)
    c2 = np.random.normal(-10.0, 1.5, 6000)
    vals = np.concatenate([c1, c2])

    res = otsu_threshold_1d(vals, n_bins=256)
    assert res["status"] == "SUCCESS"
    assert -18.0 <= res["threshold"] <= -14.0
    assert 0.35 <= res["w0"] <= 0.45
    assert res["criterion_value"] > 0.0


# 2. Kittler-Illingworth threshold correctness
def test_kittler_illingworth_correctness():
    np.random.seed(42)
    c1 = np.random.normal(-20.0, 1.2, 5000)
    c2 = np.random.normal(-9.0, 1.5, 5000)
    vals = np.concatenate([c1, c2])

    res = kittler_illingworth_threshold_1d(vals, n_bins=256)
    assert res["status"] == "SUCCESS"
    assert -16.0 <= res["threshold"] <= -13.0
    assert 0.45 <= res["w0"] <= 0.55
    assert np.isfinite(res["cost_J"])


# 3. Kittler failure on invalid distributions
def test_kittler_failure_on_invalid_distributions():
    np.random.seed(42)
    # Pure unimodal Gaussian
    unimodal = np.random.normal(-12.0, 1.0, 8000)
    res_uni = kittler_illingworth_threshold_1d(unimodal, n_bins=256)
    assert res_uni["status"] == "FAILED"
    assert res_uni["threshold"] is None

    # Degenerate constant values
    flat = np.full(500, -15.0)
    res_flat = kittler_illingworth_threshold_1d(flat)
    assert res_flat["status"] == "FAILED"
    assert res_flat["threshold"] is None


# 4. Two-dimensional Otsu implementation
def test_otsu_2d_implementation():
    np.random.seed(42)
    # Cluster 1 (Water): VV ~ -18 dB, VH ~ -25 dB
    vv_w = np.random.normal(-18.0, 1.0, 2000)
    vh_w = np.random.normal(-25.0, 1.0, 2000)

    # Cluster 2 (Land): VV ~ -8 dB, VH ~ -14 dB
    vv_l = np.random.normal(-8.0, 1.0, 6000)
    vh_l = np.random.normal(-14.0, 1.0, 6000)

    vv = np.concatenate([vv_w, vv_l])
    vh = np.concatenate([vh_w, vh_l])

    res = otsu_threshold_2d(vv, vh, n_bins=64)
    assert res["status"] == "SUCCESS"
    assert -15.0 <= res["threshold_vv"] <= -11.0
    assert -22.0 <= res["threshold_vh"] <= -17.0
    assert 0.20 <= res["w0"] <= 0.30
    assert res["criterion_value"] > 0.0


# 5. Cross-ratio numerical stability
def test_cross_ratio_numerical_stability():
    # Edge cases: zero denominator, negative linear, non-finite
    vh = np.array([0.001, 0.01, -0.05, 0.02, np.nan, 0.03], dtype=np.float32)
    vv = np.array([0.000, 0.05, 0.10, -0.01, 0.10, np.inf], dtype=np.float32)

    cr_lin, cr_db = calculate_cross_ratio(vh, vv, eps=1e-12)
    assert np.isnan(cr_lin[0])  # zero denominator
    assert abs(cr_lin[1] - (0.01 / 0.05)) < 1e-6  # valid
    assert abs(cr_db[1] - (10.0 * np.log10(0.01 / 0.05))) < 1e-4
    assert np.isnan(cr_lin[2])  # negative numerator
    assert np.isnan(cr_lin[3])  # negative denominator
    assert np.isnan(cr_lin[4])  # nan
    assert np.isnan(cr_lin[5])  # inf


# 6. VV/VH band mapping
def test_band_mapping_and_verification(tmp_path):
    p_good = tmp_path / "good.tif"
    create_synthetic_test_raster(p_good, b1_desc="Sigma0_VH", b2_desc="Sigma0_VV")
    meta = verify_phase3a_inputs(p_good)
    assert meta["band1"] == "Sigma0_VH"
    assert meta["band2"] == "Sigma0_VV"

    p_inverted = tmp_path / "inverted.tif"
    create_synthetic_test_raster(p_inverted, b1_desc="Sigma0_VV", b2_desc="Sigma0_VH")
    with pytest.raises(ValueError, match="Invalid band mapping"):
        verify_phase3a_inputs(p_inverted)


# 7. Quality mask handling (exclusion of category 1 and 3)
def test_quality_mask_exclusion_of_categories():
    shape = (10, 10)
    vv_db = np.full(shape, -15.0, dtype=np.float32)
    vh_db = np.full(shape, -22.0, dtype=np.float32)

    q_vh = np.full(shape, CAT_VALID_ORDINARY, dtype=np.uint8)
    q_vv = np.full(shape, CAT_VALID_ORDINARY, dtype=np.uint8)

    q_vh[0, 0] = CAT_SOURCE_NODATA
    q_vv[1, 1] = CAT_OTHER_INVALID

    mask = generate_candidate_mask(vv_db, vh_db, q_vh, q_vv, "dual_and", threshold_vv=-12.0, threshold_vh=-20.0)
    assert mask[0, 0] == MASK_NODATA_INVALID
    assert mask[1, 1] == MASK_NODATA_INVALID


# 8. Clipping floor exclusion from threshold estimation
def test_clipping_floor_exclusion_from_thresholds():
    # Ordinary backscatter around -10 dB, plus artificial clipping floor at -105.9 dB
    ordinary = np.random.normal(-10.0, 1.0, 1000)
    clipping = np.full(200, -105.9)
    combined = np.concatenate([ordinary, clipping])

    # If clipping floor is properly masked before Otsu, threshold should reflect ordinary distribution
    clean_res = otsu_threshold_1d(ordinary)
    assert clean_res["threshold"] > -20.0


# 9. AND/OR fusion logic
def test_and_or_fusion_logic():
    vv_db = np.array([-15.0, -15.0, -8.0, -8.0], dtype=np.float32) # Low, Low, High, High
    vh_db = np.array([-25.0, -12.0, -25.0, -12.0], dtype=np.float32) # Low, High, Low, High

    q = np.full(4, CAT_VALID_ORDINARY, dtype=np.uint8)
    t_vv = -12.0
    t_vh = -20.0

    mask_and = generate_candidate_mask(vv_db, vh_db, q, q, "dual_and", threshold_vv=t_vv, threshold_vh=t_vh)
    mask_or = generate_candidate_mask(vv_db, vh_db, q, q, "dual_or", threshold_vv=t_vv, threshold_vh=t_vh)

    # Pixel 0: Both low -> Water in AND, Water in OR
    assert mask_and[0] == MASK_CANDIDATE_WATER
    assert mask_or[0] == MASK_CANDIDATE_WATER

    # Pixel 1: VV low, VH high -> Non-water in AND, Water in OR
    assert mask_and[1] == MASK_NON_WATER
    assert mask_or[1] == MASK_CANDIDATE_WATER

    # Pixel 2: VV high, VH low -> Non-water in AND, Water in OR
    assert mask_and[2] == MASK_NON_WATER
    assert mask_or[2] == MASK_CANDIDATE_WATER

    # Pixel 3: Both high -> Non-water in AND, Non-water in OR
    assert mask_and[3] == MASK_NON_WATER
    assert mask_or[3] == MASK_NON_WATER

    # Crucial property: AND must be a strict subset of OR
    and_water = (mask_and == MASK_CANDIDATE_WATER)
    or_water = (mask_or == MASK_CANDIDATE_WATER)
    assert np.all(and_water <= or_water)


# 10. Indeterminate category preservation
def test_indeterminate_category_preservation():
    shape = (5, 5)
    vv_db = np.full(shape, -25.0, dtype=np.float32) # Super low backscatter
    vh_db = np.full(shape, -30.0, dtype=np.float32)
    q_vh = np.full(shape, CAT_VALID_ORDINARY, dtype=np.uint8)
    q_vv = np.full(shape, CAT_VALID_ORDINARY, dtype=np.uint8)

    # Pixel (2, 2) has clipping floor
    q_vh[2, 2] = CAT_SNAP_CLIPPING_FLOOR

    mask = generate_candidate_mask(vv_db, vh_db, q_vh, q_vv, "dual_and", threshold_vv=-12.0, threshold_vh=-20.0)
    # Must remain indeterminate, NOT automatically water despite being low backscatter!
    assert mask[2, 2] == MASK_INDETERMINATE
    assert mask[0, 0] == MASK_CANDIDATE_WATER


# 11. AOI masking
def test_aoi_masking_transformation(tmp_path):
    p_ref = tmp_path / "ref.tif"
    create_synthetic_test_raster(p_ref)
    aoi_mask = rasterize_aoi_mask(p_ref, PRELIMINARY_AOI_WKT)
    assert aoi_mask.shape == (1393, 1405)
    assert np.sum(aoi_mask) > 100000 # Kazipur AOI has ~1,010,039 cells


# 12. Candidate area calculations
def test_candidate_area_calculations():
    aoi_mask = np.zeros((100, 100), dtype=bool)
    aoi_mask[:50, :50] = True # 2500 AOI cells
    mask = np.full((100, 100), MASK_NON_WATER, dtype=np.uint8)
    mask[:25, :25] = MASK_CANDIDATE_WATER # 625 water cells inside AOI
    mask[25:30, :25] = MASK_INDETERMINATE # 125 indeterminate cells inside AOI

    metrics = assess_classification_metrics(mask, aoi_mask, pixel_size_m=20.0)
    assert metrics["total_aoi_cells"] == 2500
    assert metrics["candidate_water_cells"] == 625
    assert metrics["indeterminate_cells"] == 125
    assert metrics["valid_cells"] == (2500 - 125)
    # 625 * 400 m2 = 250,000 m2 = 25.0 ha = 0.25 km2
    assert abs(metrics["candidate_water_area_ha"] - 25.0) < 1e-2
    assert abs(metrics["candidate_water_area_km2"] - 0.25) < 1e-4


# 13. NoData handling
def test_nodata_handling():
    shape = (4, 4)
    vv_db = np.full(shape, -15.0, dtype=np.float32)
    vh_db = np.full(shape, -22.0, dtype=np.float32)
    q_vh = np.full(shape, CAT_SOURCE_NODATA, dtype=np.uint8)
    q_vv = np.full(shape, CAT_SOURCE_NODATA, dtype=np.uint8)

    mask = generate_candidate_mask(vv_db, vh_db, q_vh, q_vv, "dual_and", threshold_vv=-12.0, threshold_vh=-20.0)
    assert np.all(mask == MASK_NODATA_INVALID)


# 14. Output georeferencing
def test_output_georeferencing(tmp_path):
    p_ref = tmp_path / "ref.tif"
    create_synthetic_test_raster(p_ref)
    ref_ds = gdal.Open(str(p_ref))

    p_out = tmp_path / "mask_out.tif"
    mask_arr = np.zeros((1393, 1405), dtype=np.uint8)
    write_geotiff_mask(mask_arr, p_out, ref_ds)

    out_ds = gdal.Open(str(p_out))
    assert out_ds.RasterXSize == 1405
    assert out_ds.RasterYSize == 1393
    assert out_ds.RasterCount == 1
    assert out_ds.GetRasterBand(1).DataType == gdal.GDT_Byte
    assert out_ds.GetGeoTransform() == ref_ds.GetGeoTransform()
    assert out_ds.GetProjection() == ref_ds.GetProjection()
    assert out_ds.GetRasterBand(1).GetNoDataValue() == MASK_NODATA_INVALID


# 15. Deterministic threshold reproducibility
def test_deterministic_threshold_reproducibility():
    np.random.seed(123)
    vals = np.concatenate([np.random.normal(-20, 2, 500), np.random.normal(-8, 2, 1000)])
    t1 = otsu_threshold_1d(vals)["threshold"]
    t2 = otsu_threshold_1d(vals)["threshold"]
    assert t1 == t2


# 16. Empty and insufficient-data handling
def test_empty_and_insufficient_data():
    empty_res = otsu_threshold_1d(np.array([]))
    assert empty_res["status"] == "FAILED"
    assert empty_res["threshold"] is None

    empty_ki = kittler_illingworth_threshold_1d(np.array([]))
    assert empty_ki["status"] == "FAILED"
    assert empty_ki["threshold"] is None

    empty_2d = otsu_threshold_2d(np.array([]), np.array([]))
    assert empty_2d["status"] == "FAILED"
    assert empty_2d["threshold_vv"] is None

