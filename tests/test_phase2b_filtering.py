"""
Earth Pulse — Phase 2B: Adaptive SAR Speckle Filtering Test Suite
NASA Space Apps Challenge 2026: Dancing with the SARs

Unit and integration tests for scripts/filter_sar_phase2b.py:
1. Lee 3×3 filtering on a constant image.
2. Lee 5×5 filtering on a constant image.
3. Correct adaptive Lee weight calculation.
4. Multiplicative speckle variance reduction.
5. Preservation of a synthetic sharp boundary.
6. NoData exclusion from neighborhood statistics.
7. SNAP clipping-floor exclusion from filtering neighborhoods.
8. Preservation of clipping-floor source values and quality flags.
9. Preservation of CRS and geotransform.
10. Preservation of polarization descriptions.
11. Block-boundary and halo correctness.
12. Rejection of invalid ENL estimates.
13. Protection against output overwriting.
14. Handling of insufficient valid neighborhoods.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal, osr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from filter_sar_phase2b import (
        CAT_CLIPPING_FLOOR,
        CAT_NODATA,
        CAT_VALID_ORDINARY,
        CLIPPING_FLOOR_MAX,
        CLIPPING_FLOOR_MIN,
        NODATA_VALUE,
        create_quality_mask,
        estimate_enl_homogeneous,
        filter_sar_dataset,
        vectorized_lee_filter,
        verify_phase2b_inputs,
    )
except ImportError:
    from scripts.filter_sar_phase2b import (  # type: ignore
        CAT_SNAP_CLIPPING_FLOOR as CAT_CLIPPING_FLOOR,
        CAT_SOURCE_NODATA as CAT_NODATA,
        CAT_VALID_ORDINARY,
        CLIPPING_FLOOR_MAX,
        CLIPPING_FLOOR_MIN,
        NODATA_VALUE,
        create_quality_mask,
        estimate_enl_homogeneous,
        filter_sar_dataset,
        vectorized_lee_filter,
        verify_phase2b_inputs,
    )

gdal.UseExceptions()


def create_test_geotiff(filepath: str, width: int, height: int, gt: tuple,
                        b1_arr: np.ndarray, b2_arr: np.ndarray, epsg=32645):
    """Helper to create a 2-band synthetic test GeoTIFF."""
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(filepath, width, height, 2, gdal.GDT_Float32)
    ds.SetGeoTransform(gt)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())

    for b, arr, desc in [(1, b1_arr, "Sigma0_VH"), (2, b2_arr, "Sigma0_VV")]:
        band = ds.GetRasterBand(b)
        band.WriteArray(arr)
        band.SetDescription(desc)
        band.SetNoDataValue(NODATA_VALUE)
    ds = None


# Test 1: Lee 3x3 on constant image
def test_lee_3x3_constant_image():
    arr = np.full((20, 20), 0.05, dtype=np.float32)
    filtered = vectorized_lee_filter(arr, enl=5.0, window_size=3)
    np.testing.assert_allclose(filtered, arr, rtol=1e-5)


# Test 2: Lee 5x5 on constant image
def test_lee_5x5_constant_image():
    arr = np.full((20, 20), 0.05, dtype=np.float32)
    filtered = vectorized_lee_filter(arr, enl=5.0, window_size=5)
    np.testing.assert_allclose(filtered, arr, rtol=1e-5)


# Test 3: Correct adaptive Lee weight calculation
def test_lee_weight_calculation():
    # Construct a 3x3 patch with known mean and variance
    # Mean = 10, Var = 4
    # If ENL = 5, noise_var = 10^2 / 5 = 20. Since Var (4) <= noise_var (20), W must be 0
    arr_homo = np.array([
        [8.0, 10.0, 12.0],
        [10.0, 10.0, 10.0],
        [12.0, 10.0, 8.0]
    ], dtype=np.float32)
    filt_homo = vectorized_lee_filter(arr_homo, enl=5.0, window_size=3)
    # When W = 0, filtered center must equal local mean (10.0)
    assert abs(filt_homo[1, 1] - 10.0) < 1e-4

    # High variance patch: Mean = 10, Var = 200
    # If ENL = 5, noise_var = 20. W = (200 - 20) / 200 = 0.90
    arr_edge = np.array([
        [0.01, 0.01, 0.01],
        [0.01, 100.0, 0.01],
        [0.01, 0.01, 0.01]
    ], dtype=np.float32)
    filt_edge = vectorized_lee_filter(arr_edge, enl=5.0, window_size=3)
    # Filtered center must preserve most of the high-contrast original
    assert filt_edge[1, 1] > 80.0


# Test 4: Multiplicative speckle variance reduction
def test_multiplicative_speckle_variance_reduction():
    rng = np.random.default_rng(123)
    # Base homogeneous area of 0.02 with multiplicative Gamma speckle (ENL = 5.0)
    base = np.full((100, 100), 0.02, dtype=np.float32)
    speckle = rng.gamma(shape=5.0, scale=1.0 / 5.0, size=(100, 100)).astype(np.float32)
    noisy = base * speckle

    var_noisy = float(np.var(noisy))
    f3 = vectorized_lee_filter(noisy, enl=5.0, window_size=3)
    f5 = vectorized_lee_filter(noisy, enl=5.0, window_size=5)

    var_f3 = float(np.var(f3))
    var_f5 = float(np.var(f5))

    # Variance must decrease monotonically: var_noisy > var_f3 > var_f5
    assert var_f3 < var_noisy * 0.70  # At least 30% reduction
    assert var_f5 < var_f3 * 0.70  # Lee 5x5 reduces even more


# Test 5: Preservation of a synthetic sharp boundary
def test_preservation_of_synthetic_sharp_boundary():
    # Step edge: left half is water (0.005), right half is land (0.100)
    arr = np.zeros((30, 30), dtype=np.float32)
    arr[:, :15] = 0.005
    arr[:, 15:] = 0.100

    f3 = vectorized_lee_filter(arr, enl=5.0, window_size=3)
    # Edge gradient across columns 13 to 16
    grad_orig = arr[15, 15] - arr[15, 14]  # 0.095
    grad_f3 = f3[15, 15] - f3[15, 14]
    # Edge sharpness must be retained within 80%
    assert grad_f3 > 0.80 * grad_orig


# Test 6: NoData exclusion from neighborhood statistics
def test_nodata_exclusion_from_neighborhood_stats():
    # 5x5 array where center and neighbors are 10.0, but one corner is -9999.0
    arr = np.full((5, 5), 10.0, dtype=np.float32)
    arr[0, 0] = NODATA_VALUE
    f3 = vectorized_lee_filter(arr, enl=5.0, window_size=3)
    # Pixel at (1, 1) touches (0, 0). Its mean must still be 10.0, NOT corrupted by -9999
    assert abs(f3[1, 1] - 10.0) < 1e-4
    # Pixel at (0, 0) must remain strictly NoData
    assert f3[0, 0] == NODATA_VALUE


# Test 7: SNAP clipping-floor exclusion from filtering neighborhoods
def test_snap_clipping_floor_exclusion():
    arr = np.full((5, 5), 0.05, dtype=np.float32)
    # Put a SNAP clipping-floor pixel at (0, 0)
    arr[0, 0] = 2.5537e-11
    f3 = vectorized_lee_filter(arr, enl=5.0, window_size=3)
    # Neighbor at (1, 1) must remain 0.05 and NOT be pulled down by 2.55e-11
    assert abs(f3[1, 1] - 0.05) < 1e-4


# Test 8: Preservation of clipping-floor source values and quality flags
def test_preservation_of_clipping_floor_source_values():
    arr = np.full((5, 5), 0.05, dtype=np.float32)
    arr[2, 2] = 2.5537e-11
    f3 = vectorized_lee_filter(arr, enl=5.0, window_size=3)
    # The clipping floor pixel itself must retain its exact original value
    assert f3[2, 2] == np.float32(2.5537e-11)

    # Check quality mask
    q_mask = create_quality_mask(arr)
    assert q_mask[2, 2] == CAT_CLIPPING_FLOOR
    assert q_mask[0, 0] == CAT_VALID_ORDINARY


# Test 9: Preservation of CRS and geotransform
def test_preservation_of_crs_and_geotransform(tmp_path):
    in_tif = str(tmp_path / "test_in.tif")
    out_tif = str(tmp_path / "test_out.tif")
    gt = (750000.0, 20.0, 0.0, 2750000.0, 0.0, -20.0)
    arr = np.full((50, 50), 0.05, dtype=np.float32)

    create_test_geotiff(in_tif, 50, 50, gt, arr, arr, epsg=32645)
    filter_sar_dataset(in_tif, out_tif, enl_vh=5.0, enl_vv=5.0, window_size=3, overwrite=True)

    out_ds = gdal.Open(out_tif)
    assert out_ds.GetGeoTransform() == gt
    srs = osr.SpatialReference()
    srs.ImportFromWkt(out_ds.GetProjection())
    assert str(srs.GetAuthorityCode(None)) == "32645"
    out_ds = None


# Test 10: Preservation of polarization descriptions
def test_preservation_of_polarization_descriptions(tmp_path):
    in_tif = str(tmp_path / "test_in.tif")
    out_tif = str(tmp_path / "test_out.tif")
    gt = (750000.0, 20.0, 0.0, 2750000.0, 0.0, -20.0)
    arr = np.full((30, 30), 0.05, dtype=np.float32)

    create_test_geotiff(in_tif, 30, 30, gt, arr, arr)
    filter_sar_dataset(in_tif, out_tif, enl_vh=5.0, enl_vv=5.0, window_size=3, overwrite=True)

    out_ds = gdal.Open(out_tif)
    assert out_ds.GetRasterBand(1).GetDescription() == "Sigma0_VH"
    assert out_ds.GetRasterBand(2).GetDescription() == "Sigma0_VV"
    out_ds = None


# Test 11: Block-boundary and halo correctness
def test_block_boundary_and_halo_correctness(tmp_path):
    # Create an array of size 60x60 with varying values
    rng = np.random.default_rng(999)
    arr = rng.uniform(0.01, 0.10, size=(60, 60)).astype(np.float32)

    # 1. Filter all at once
    f_full = vectorized_lee_filter(arr, enl=5.0, window_size=3)

    # 2. Filter via block-wise streaming with block size = 25 (creates multiple blocks & seams)
    in_tif = str(tmp_path / "test_block_in.tif")
    out_tif = str(tmp_path / "test_block_out.tif")
    gt = (750000.0, 20.0, 0.0, 2750000.0, 0.0, -20.0)
    create_test_geotiff(in_tif, 60, 60, gt, arr, arr)

    filter_sar_dataset(in_tif, out_tif, enl_vh=5.0, enl_vv=5.0, window_size=3,
                       block_size=25, overwrite=True)

    out_ds = gdal.Open(out_tif)
    f_blocked = out_ds.GetRasterBand(1).ReadAsArray()
    out_ds = None

    # Interior block boundaries must match full filtering
    np.testing.assert_allclose(f_blocked, f_full, rtol=1e-4, atol=1e-6)


# Test 12: Rejection of invalid ENL estimates
def test_rejection_of_invalid_enl_estimates():
    arr = np.full((10, 10), 0.05, dtype=np.float32)
    with pytest.raises(ValueError):
        vectorized_lee_filter(arr, enl=0.0)
    with pytest.raises(ValueError):
        vectorized_lee_filter(arr, enl=-1.5)
    with pytest.raises(ValueError):
        vectorized_lee_filter(arr, enl=float("nan"))


# Test 13: Protection against output overwriting
def test_protection_against_output_overwriting(tmp_path):
    in_tif = str(tmp_path / "in.tif")
    out_tif = str(tmp_path / "out.tif")
    gt = (750000.0, 20.0, 0.0, 2750000.0, 0.0, -20.0)
    arr = np.full((10, 10), 0.05, dtype=np.float32)
    create_test_geotiff(in_tif, 10, 10, gt, arr, arr)

    # Create empty out file
    Path(out_tif).touch()

    with pytest.raises(FileExistsError):
        filter_sar_dataset(in_tif, out_tif, enl_vh=5.0, enl_vv=5.0, overwrite=False)


# Test 14: Handling of insufficient valid neighborhoods
def test_handling_of_insufficient_valid_neighborhoods():
    # Single valid pixel surrounded by NoData
    arr = np.full((5, 5), NODATA_VALUE, dtype=np.float32)
    arr[2, 2] = 0.05
    filt = vectorized_lee_filter(arr, enl=5.0, window_size=3)
    # The valid pixel had < 3 valid neighbors in its 3x3 window, so it falls back to 0.05
    assert filt[2, 2] == 0.05
    # Surrounding pixels remain NoData
    assert filt[1, 1] == NODATA_VALUE

