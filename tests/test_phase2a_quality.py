"""
Earth Pulse — Phase 2A.1: Quality Control & Anomaly Investigation Test Suite
NASA Space Apps Challenge 2026: Dancing with the SARs

Tests for scripts/quality_check_phase2a.py:
1. Low backscatter threshold quantification.
2. AOI-specific statistical calculation.
3. Extreme difference anomaly attribution.
4. Dual-scale QC histogram generation.
5. Spatial anomaly map generation.
6. Pipeline integration and CSV/JSON reporting.
"""

import csv
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal, osr

# Ensure project root and scripts directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from quality_check_phase2a import (
        LOW_BACKSCATTER_THRESHOLDS,
        NODATA_VALUE,
        PRELIMINARY_AOI_WKT,
        compute_aoi_statistics,
        generate_qc_histograms,
        generate_spatial_anomaly_map,
        get_aoi_mask,
        investigate_extreme_differences,
        quantify_low_backscatter,
    )
except ImportError:
    from scripts.quality_check_phase2a import (  # type: ignore
        LOW_BACKSCATTER_THRESHOLDS,
        NODATA_VALUE,
        PRELIMINARY_AOI_WKT,
        compute_aoi_statistics,
        generate_qc_histograms,
        generate_spatial_anomaly_map,
        get_aoi_mask,
        investigate_extreme_differences,
        quantify_low_backscatter,
    )

gdal.UseExceptions()


def create_test_raster(
    filepath: str,
    width: int,
    height: int,
    geotransform: tuple,
    band_array: np.ndarray,
    epsg: int = 32645,
    nodata: float = NODATA_VALUE,
) -> str:
    """Helper to generate single-band test GeoTIFFs."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(filepath, width, height, 1, gdal.GDT_Float32)
    ds.SetGeoTransform(geotransform)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())

    b = ds.GetRasterBand(1)
    b.WriteArray(band_array.astype(np.float32))
    b.SetNoDataValue(nodata)
    ds.FlushCache()
    ds = None
    return filepath


def test_quantify_low_backscatter(tmp_path):
    """Test 1: Low backscatter threshold quantification."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 10, 1

    # Values: -10, -22, -27, -32, -37, -42, -47, -55, -100, NODATA
    arr = np.array([[-10.0, -22.0, -27.0, -32.0, -37.0, -42.0, -47.0, -55.0, -100.0, NODATA_VALUE]], dtype=np.float32)
    p = str(tmp_path / "test_low.tif")
    create_test_raster(p, w, h, gt, arr)

    res = quantify_low_backscatter(p)
    assert res["total_valid_pixels"] == 9
    assert res["total_grid_pixels"] == 10

    # Below -20 dB: 8 pixels (-22 down to -100)
    assert res["thresholds"]["below_20db"]["pixel_count"] == 8
    # Below -30 dB: 6 pixels (-32 down to -100)
    assert res["thresholds"]["below_30db"]["pixel_count"] == 6
    # Below -50 dB: 2 pixels (-55, -100)
    assert res["thresholds"]["below_50db"]["pixel_count"] == 2


def test_aoi_statistics_calculation(tmp_path):
    """Test 2: AOI-specific statistics calculation."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 50, 50

    # Fill raster with -15 dB
    arr = np.full((h, w), -15.0, dtype=np.float32)
    p = str(tmp_path / "test_aoi_stats.tif")
    create_test_raster(p, w, h, gt, arr)

    # Mock AOI mask covering a 10x10 sub-window
    aoi_mask = np.zeros((h, w), dtype=bool)
    aoi_mask[10:20, 10:20] = True

    stats = compute_aoi_statistics(p, aoi_mask)
    assert stats["aoi_valid_pixels"] == 100
    assert np.isclose(stats["mean_db"], -15.0)
    assert np.isclose(stats["median_db"], -15.0)
    assert np.isclose(stats["min_db"], -15.0)
    assert np.isclose(stats["max_db"], -15.0)
    assert np.isclose(stats["percentiles"]["p50"], -15.0)


def test_extreme_difference_investigation(tmp_path):
    """Test 3: Extreme difference anomaly attribution to noise floor."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 4, 1

    # June: [-105.0, -15.0,  -10.0, NODATA]
    # July: [ -20.0, -105.0, -12.0, NODATA]
    # Diff: [ +85.0,  -90.0,  -2.0, NODATA]
    june_arr = np.array([[-105.0, -15.0, -10.0, NODATA_VALUE]], dtype=np.float32)
    july_arr = np.array([[-20.0, -105.0, -12.0, NODATA_VALUE]], dtype=np.float32)
    diff_arr = np.array([[85.0, -90.0, -2.0, NODATA_VALUE]], dtype=np.float32)

    j_p = str(tmp_path / "j.tif")
    y_p = str(tmp_path / "y.tif")
    d_p = str(tmp_path / "d.tif")

    create_test_raster(j_p, w, h, gt, june_arr)
    create_test_raster(y_p, w, h, gt, july_arr)
    create_test_raster(d_p, w, h, gt, diff_arr)

    res = investigate_extreme_differences(d_p, j_p, y_p, pos_thresh_db=30.0, neg_thresh_db=-30.0)

    # 1 extreme positive (> +30 dB), 1 extreme negative (< -30 dB)
    assert res["extreme_positive"]["count"] == 1
    assert res["extreme_positive"]["max_positive_diff_db"] == 85.0
    assert res["extreme_positive"]["pct_caused_by_low_june_noise_floor"] == 100.0

    assert res["extreme_negative"]["count"] == 1
    assert res["extreme_negative"]["min_negative_diff_db"] == -90.0
    assert res["extreme_negative"]["pct_caused_by_low_july_noise_floor"] == 100.0


def test_qc_histograms_generation(tmp_path):
    """Test 4: Dual-scale QC histogram generation."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 30, 30

    np.random.seed(123)
    j_data = np.random.normal(-15.0, 3.0, (h, w)).astype(np.float32)
    y_data = np.random.normal(-20.0, 4.0, (h, w)).astype(np.float32)

    j_p = str(tmp_path / "j_hist.tif")
    y_p = str(tmp_path / "y_hist.tif")
    create_test_raster(j_p, w, h, gt, j_data)
    create_test_raster(y_p, w, h, gt, y_data)

    out_dir = str(tmp_path / "qc_plots")
    plots = generate_qc_histograms(j_p, y_p, "VV", out_dir, bins=40)

    assert os.path.exists(plots["full_range_plot"])
    assert os.path.exists(plots["robust_range_plot"])
    assert os.path.getsize(plots["full_range_plot"]) > 1000
    assert os.path.getsize(plots["robust_range_plot"]) > 1000


def test_spatial_anomaly_map_generation(tmp_path):
    """Test 5: Spatial anomaly map generation."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 20, 20

    diff_arr = np.zeros((h, w), dtype=np.float32)
    diff_arr[0:5, 0:5] = 45.0   # Extreme positive
    diff_arr[15:20, 15:20] = -40.0 # Extreme negative
    diff_arr[10, 10] = NODATA_VALUE

    d_p = str(tmp_path / "diff_map.tif")
    create_test_raster(d_p, w, h, gt, diff_arr)

    out_png = str(tmp_path / "anomaly_map.png")
    res_png = generate_spatial_anomaly_map(d_p, "VH", out_png)

    assert os.path.exists(res_png)
    assert os.path.getsize(res_png) > 1000

