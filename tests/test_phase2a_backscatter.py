"""
Earth Pulse — Phase 2A: Unit and Integration Test Suite
NASA Space Apps Challenge 2026: Dancing with the SARs

Tests for scripts/analyze_backscatter_phase2a.py:
1. Correct linear Sigma0 to dB conversion.
2. Zero-value masking.
3. Negative-value masking.
4. NoData preservation.
5. NaN and Inf handling.
6. Correct VV/VH band mapping.
7. Correct difference sign (July - June).
8. Difference calculation using common valid pixels only.
9. Statistical calculations against known arrays.
10. Histogram counts and normalization.
11. AOI geometry transformation and coverage calculation.
12. Output CRS, dimensions and geotransform preservation.
"""

import csv
import os
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal, osr

# Ensure project root and scripts directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from analyze_backscatter_phase2a import (
        NODATA_VALUE,
        PRELIMINARY_AOI_WKT,
        assess_aoi_valid_data,
        compute_channel_statistics,
        compute_difference_raster,
        convert_linear_array_to_db,
        create_db_raster,
        generate_histograms_and_tables,
        verify_aligned_inputs,
        verify_thermal_noise_correction,
    )
except ImportError:
    from scripts.analyze_backscatter_phase2a import (  # type: ignore
        NODATA_VALUE,
        PRELIMINARY_AOI_WKT,
        assess_aoi_valid_data,
        compute_channel_statistics,
        compute_difference_raster,
        convert_linear_array_to_db,
        create_db_raster,
        generate_histograms_and_tables,
        verify_aligned_inputs,
        verify_thermal_noise_correction,
    )

gdal.UseExceptions()


def create_synthetic_raster(
    filepath: str,
    width: int,
    height: int,
    geotransform: tuple,
    band_arrays: list,
    epsg: int = 32645,
    nodata: float = NODATA_VALUE,
    descriptions: list = None,
) -> str:
    """Helper to generate synthetic test GeoTIFFs."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(filepath, width, height, len(band_arrays), gdal.GDT_Float32)
    ds.SetGeoTransform(geotransform)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())

    for i, arr in enumerate(band_arrays, start=1):
        b = ds.GetRasterBand(i)
        b.WriteArray(arr.astype(np.float32))
        b.SetNoDataValue(nodata)
        if descriptions and i <= len(descriptions):
            b.SetDescription(descriptions[i - 1])

    ds.FlushCache()
    ds = None
    return filepath


# =========================================================================
# TEST CASES
# =========================================================================

def test_linear_to_db_conversion_and_known_values():
    """Test 1: Correct linear Sigma0 to dB conversion."""
    linear = np.array([1.0, 0.1, 0.01, 10.0, 0.001], dtype=np.float32)
    db_out, mask = convert_linear_array_to_db(linear, NODATA_VALUE)

    expected = np.array([0.0, -10.0, -20.0, 10.0, -30.0], dtype=np.float32)
    assert np.all(mask)
    assert np.allclose(db_out, expected, atol=1e-5)


def test_zero_negative_nodata_and_nonfinite_masking():
    """Tests 2, 3, 4, 5: Zero, negative, nodata, NaN, and Inf masking."""
    linear = np.array([
        0.05,            # Valid
        0.0,             # Zero
        -0.01,           # Negative
        NODATA_VALUE,    # Pre-existing NoData (-9999.0)
        np.nan,          # NaN
        np.inf,          # +Inf
        -np.inf,         # -Inf
    ], dtype=np.float32)

    db_out, mask = convert_linear_array_to_db(linear, NODATA_VALUE)

    assert mask[0] is True or mask[0] == 1
    assert np.isclose(db_out[0], 10.0 * np.log10(0.05), atol=1e-5)

    # All invalid must be masked and equal to NODATA_VALUE
    assert not np.any(mask[1:])
    assert np.all(db_out[1:] == NODATA_VALUE)


def test_correct_band_mapping_and_input_verification(tmp_path):
    """Test 6: Correct VV/VH band mapping and verification."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 1405, 1393

    june_p = str(tmp_path / "june_al.tif")
    july_p = str(tmp_path / "july_al.tif")

    b_vh = np.full((h, w), 0.02, dtype=np.float32)
    b_vv = np.full((h, w), 0.10, dtype=np.float32)

    # Compliant aligned rasters
    create_synthetic_raster(june_p, w, h, gt, [b_vh, b_vv], descriptions=["Sigma0_VH", "Sigma0_VV"])
    create_synthetic_raster(july_p, w, h, gt, [b_vh, b_vv], descriptions=["Sigma0_VH", "Sigma0_VV"])

    res = verify_aligned_inputs(june_p, july_p)
    assert res["status"] == "VERIFIED_COMPLIANT"
    assert res["bands"][1] == "Sigma0_VH"
    assert res["bands"][2] == "Sigma0_VV"

    # Mismatched descriptions should fail
    bad_p = str(tmp_path / "bad.tif")
    create_synthetic_raster(bad_p, w, h, gt, [b_vh, b_vv], descriptions=["Sigma0_VV", "Sigma0_VH"])
    with pytest.raises(ValueError, match="Band 1 description must be 'Sigma0_VH'"):
        verify_aligned_inputs(bad_p, july_p)


def test_difference_sign_and_common_valid_masking(tmp_path):
    """Tests 7 & 8: Correct difference sign (July - June) on common valid pixels only."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 4, 1

    # June dB: [-10.0, -10.0,  NODATA, -15.0]
    # July dB: [-15.0,  -5.0,  -10.0,  NODATA]
    # Diff   : [ -5.0,  +5.0,  NODATA, NODATA]
    june_db = np.array([[-10.0, -10.0, NODATA_VALUE, -15.0]], dtype=np.float32)
    july_db = np.array([[-15.0, -5.0, -10.0, NODATA_VALUE]], dtype=np.float32)

    j_path = str(tmp_path / "j_db.tif")
    y_path = str(tmp_path / "y_db.tif")
    d_path = str(tmp_path / "diff.tif")

    create_synthetic_raster(j_path, w, h, gt, [june_db])
    create_synthetic_raster(y_path, w, h, gt, [july_db])

    res = compute_difference_raster(j_path, y_path, d_path, "Delta_Test_dB")
    assert res["valid_common_pixels"] == 2
    assert res["nodata_pixels"] == 2

    ds = gdal.Open(d_path)
    diff_arr = ds.GetRasterBand(1).ReadAsArray()

    # Pixel 0: -15 - (-10) = -5 (Negative: backscatter decreased in July)
    assert np.isclose(diff_arr[0, 0], -5.0)
    # Pixel 1: -5 - (-10) = +5 (Positive: backscatter increased in July)
    assert np.isclose(diff_arr[0, 1], 5.0)
    # Pixels 2 & 3: Only one acquisition valid -> NoData
    assert diff_arr[0, 2] == NODATA_VALUE
    assert diff_arr[0, 3] == NODATA_VALUE
    ds = None


def test_statistical_calculations_against_known_array(tmp_path):
    """Test 9: Statistical calculations against known analytical distribution."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    # Known 10-element array in linear and dB
    lin_known = np.array([[0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, NODATA_VALUE]], dtype=np.float32)
    db_known, _ = convert_linear_array_to_db(lin_known, NODATA_VALUE)

    lin_path = str(tmp_path / "lin.tif")
    db_path = str(tmp_path / "db.tif")
    create_synthetic_raster(lin_path, 10, 1, gt, [lin_known])
    create_synthetic_raster(db_path, 10, 1, gt, [db_known])

    stats = compute_channel_statistics(db_path, lin_path, 1)

    assert stats["valid_pixels"] == 9
    assert stats["invalid_pixels"] == 1

    valid_db = db_known[db_known != NODATA_VALUE]
    assert np.isclose(stats["decibel_stats"]["min_db"], np.min(valid_db))
    assert np.isclose(stats["decibel_stats"]["max_db"], np.max(valid_db))
    assert np.isclose(stats["decibel_stats"]["mean_db"], np.mean(valid_db))
    assert np.isclose(stats["decibel_stats"]["median_db"], np.median(valid_db))
    assert np.isclose(stats["decibel_stats"]["stddev_db"], np.std(valid_db, ddof=1))
    assert np.isclose(stats["decibel_stats"]["percentiles_db"]["p50"], np.percentile(valid_db, 50))


def test_histogram_counts_and_normalization(tmp_path):
    """Test 10: Histogram counts sum and probability density normalization."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 50, 50

    # Normal random distribution in dB
    np.random.seed(42)
    j_data = np.random.normal(loc=-15.0, scale=3.0, size=(h, w)).astype(np.float32)
    y_data = np.random.normal(loc=-18.0, scale=4.0, size=(h, w)).astype(np.float32)

    j_p = str(tmp_path / "j_hist.tif")
    y_p = str(tmp_path / "y_hist.tif")
    create_synthetic_raster(j_p, w, h, gt, [j_data])
    create_synthetic_raster(y_p, w, h, gt, [y_data])

    p_dir = str(tmp_path / "plots")
    d_dir = str(tmp_path / "data")
    res = generate_histograms_and_tables(j_p, y_p, "VV", p_dir, d_dir, bins=50)

    assert os.path.exists(res["plots"]["june10"])
    assert os.path.exists(res["plots"]["july16"])
    assert os.path.exists(res["plots"]["comparative"])
    assert os.path.exists(res["csv_tables"]["june10"])

    # Read CSV and verify normalization
    total_count = 0
    density_integral = 0.0
    with open(res["csv_tables"]["june10"]) as f:
        reader = csv.DictReader(f)
        for row in reader:
            c = int(row["pixel_count"])
            d = float(row["density_probability"])
            bw = float(row["bin_right_db"]) - float(row["bin_left_db"])
            total_count += c
            density_integral += d * bw

    assert total_count == w * h
    assert np.isclose(density_integral, 1.0, atol=1e-3)


def test_aoi_geometry_transformation_and_coverage(tmp_path):
    """Test 11: AOI geometry transformation and valid pixel coverage assessment."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 100, 100

    b_valid = np.full((h, w), 0.05, dtype=np.float32)
    j_p = str(tmp_path / "j_aoi.tif")
    y_p = str(tmp_path / "y_aoi.tif")

    create_synthetic_raster(j_p, w, h, gt, [b_valid, b_valid], descriptions=["Sigma0_VH", "Sigma0_VV"])
    create_synthetic_raster(y_p, w, h, gt, [b_valid, b_valid], descriptions=["Sigma0_VH", "Sigma0_VV"])

    # Box centered inside 100x100 test raster in WGS84 (around 89.523 E, 24.788 N)
    test_wkt = "POLYGON((89.520 24.785, 89.525 24.785, 89.525 24.790, 89.520 24.790, 89.520 24.785))"
    aoi_res = assess_aoi_valid_data(j_p, y_p, test_wkt)

    assert aoi_res["status"] == "PRELIMINARY_AOI_ASSESSED"
    assert aoi_res["total_aoi_grid_cells"] > 0
    assert aoi_res["common_valid_aoi_cells"] == aoi_res["total_aoi_grid_cells"]
    assert aoi_res["common_valid_aoi_pct"] == 100.0


def test_output_crs_dimensions_and_geotransform(tmp_path):
    """Test 12: Output CRS, dimensions and geotransform preservation."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 30, 25

    lin_arr = np.full((h, w), 0.08, dtype=np.float32)
    in_p = str(tmp_path / "in.tif")
    out_p = str(tmp_path / "out_db.tif")
    create_synthetic_raster(in_p, w, h, gt, [lin_arr, lin_arr], descriptions=["Sigma0_VH", "Sigma0_VV"])

    create_db_raster(in_p, 1, out_p, "Sigma0_VH_dB")

    ds = gdal.Open(out_p)
    assert ds.RasterXSize == w
    assert ds.RasterYSize == h
    assert ds.GetGeoTransform() == gt
    assert ds.GetRasterBand(1).GetDescription() == "Sigma0_VH_dB"
    assert ds.GetRasterBand(1).GetNoDataValue() == NODATA_VALUE

    srs = osr.SpatialReference()
    srs.ImportFromWkt(ds.GetProjection())
    assert srs.GetAttrValue("AUTHORITY", 1) == "32645"
    ds = None


def test_thermal_noise_verification_logic(tmp_path):
    """Test thermal-noise verification guardrails against potential double correction."""
    # Create mock SAFE archive with thermalNoiseCorrectionPerformed = true (hazardous)
    bad_zip = str(tmp_path / "S1A_BAD.zip")
    mock_xml = """<annotation><imageAnnotation><processingInformation>
    <thermalNoiseCorrectionPerformed>true</thermalNoiseCorrectionPerformed>
    </processingInformation></imageAnnotation></annotation>"""

    with zipfile.ZipFile(bad_zip, "w") as z:
        z.writestr("S1A_BAD.SAFE/annotation/s1a-iw-grd-vh.xml", mock_xml)

    with pytest.raises(RuntimeError, match="CRITICAL DOUBLE-CORRECTION HAZARD"):
        verify_thermal_noise_correction(str(tmp_path))
