"""
Earth Pulse — Phase 1: Unit and Integration Test Suite
NASA Space Apps Challenge 2026: Dancing with the SARs

Tests for scripts/align_sar_rasters.py:
1. Correct band identification and metadata assignment.
2. Correct handling of zero-valued NoData pixels.
3. Correct conversion of invalid pixels to -9999.
4. Correct reference-grid preservation.
5. July 16 resampling to exact June 10 dimensions.
6. Identical CRS and geotransforms after alignment.
7. Preservation of valid VV/VH values within expected resampling tolerance.
8. Rejection of incorrect band counts.
9. Rejection of missing inputs.
10. Protection against overwriting existing outputs.
"""

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
    from align_sar_rasters import (
        compute_common_coverage_and_validation,
        compute_sha256,
        harmonize_reference_raster,
        harmonize_target_raster,
        run_pipeline,
        verify_dimap_metadata,
        verify_source_geotiff,
    )
except ImportError:
    from scripts.align_sar_rasters import (  # type: ignore
        compute_common_coverage_and_validation,
        compute_sha256,
        harmonize_reference_raster,
        harmonize_target_raster,
        run_pipeline,
        verify_dimap_metadata,
        verify_source_geotiff,
    )

gdal.UseExceptions()


def create_synthetic_geotiff(
    filepath: str,
    width: int,
    height: int,
    geotransform: tuple,
    band_data: list,
    epsg: int = 32645,
    nodata: float = None,
    band_descriptions: list = None,
) -> str:
    """Helper to generate synthetic multi-band GeoTIFFs for testing."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    nbands = len(band_data)
    ds = driver.Create(filepath, width, height, nbands, gdal.GDT_Float32)

    ds.SetGeoTransform(geotransform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())

    for i, data in enumerate(band_data, start=1):
        band = ds.GetRasterBand(i)
        band.WriteArray(data.astype(np.float32))
        if nodata is not None:
            band.SetNoDataValue(nodata)
        if band_descriptions and i <= len(band_descriptions):
            band.SetDescription(band_descriptions[i - 1])

    ds.FlushCache()
    ds = None
    return filepath


def create_synthetic_dimap(
    dim_filepath: str,
    band_names: list = ("Sigma0_VH", "Sigma0_VV"),
    nodata_val: str = "0.0",
) -> str:
    """Helper to create minimal synthetic BEAM-DIMAP XML for testing."""
    os.makedirs(os.path.dirname(dim_filepath), exist_ok=True)
    xml_content = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<Dimap_Document name="{Path(dim_filepath).stem}">
    <Data_Access>
        <Data_File>
            <DATA_FILE_PATH href="{Path(dim_filepath).stem}.data" />
        </Data_File>
    </Data_Access>
    <Image_Interpretation>
        <Spectral_Band_Info>
            <BAND_INDEX>0</BAND_INDEX>
            <BAND_NAME>{band_names[0]}</BAND_NAME>
            <DATA_TYPE>float32</DATA_TYPE>
            <NO_DATA_VALUE>{nodata_val}</NO_DATA_VALUE>
            <NO_DATA_VALUE_USED>true</NO_DATA_VALUE_USED>
        </Spectral_Band_Info>
        <Spectral_Band_Info>
            <BAND_INDEX>1</BAND_INDEX>
            <BAND_NAME>{band_names[1]}</BAND_NAME>
            <DATA_TYPE>float32</DATA_TYPE>
            <NO_DATA_VALUE>{nodata_val}</NO_DATA_VALUE>
            <NO_DATA_VALUE_USED>true</NO_DATA_VALUE_USED>
        </Spectral_Band_Info>
    </Image_Interpretation>
</Dimap_Document>
"""
    with open(dim_filepath, "w") as f:
        f.write(xml_content)
    return dim_filepath


# =========================================================================
# TEST CASES
# =========================================================================

def test_reference_grid_preservation_and_metadata(tmp_path):
    """Test 4: Correct reference-grid preservation and metadata assignment."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 40, 30
    b1 = np.full((h, w), 0.02, dtype=np.float32)
    b2 = np.full((h, w), 0.12, dtype=np.float32)

    ref_in = str(tmp_path / "ref.tif")
    ref_out = str(tmp_path / "ref_aligned.tif")
    create_synthetic_geotiff(ref_in, w, h, gt, [b1, b2])

    result = harmonize_reference_raster(ref_in, ref_out)
    assert os.path.exists(ref_out)
    assert result["width"] == w
    assert result["height"] == h
    assert result["geotransform"] == gt

    ds = gdal.Open(ref_out, gdal.GA_ReadOnly)
    assert ds.RasterXSize == w
    assert ds.RasterYSize == h
    assert ds.GetGeoTransform() == gt
    assert ds.GetRasterBand(1).GetDescription() == "Sigma0_VH"
    assert ds.GetRasterBand(2).GetDescription() == "Sigma0_VV"
    assert ds.GetRasterBand(1).GetNoDataValue() == -9999.0
    assert ds.GetRasterBand(2).GetNoDataValue() == -9999.0
    ds = None


def test_zero_and_invalid_pixel_conversion_to_nodata(tmp_path):
    """Tests 2 & 3: Correct handling of zero NoData and invalid pixels to -9999."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 20, 20

    # Create pattern with positive, zero, negative, NaN, and Inf values
    b1 = np.ones((h, w), dtype=np.float32) * 0.05
    b1[0:5, :] = 0.0          # Zero out-of-swath border
    b1[5:7, :] = -0.01        # Negative noise
    b1[7, 0:5] = np.nan       # Non-finite NaN
    b1[8, 0:5] = np.inf       # Non-finite Inf

    b2 = b1 * 2.0

    ref_in = str(tmp_path / "invalid_input.tif")
    ref_out = str(tmp_path / "invalid_cleaned.tif")
    create_synthetic_geotiff(ref_in, w, h, gt, [b1, b2])

    harmonize_reference_raster(ref_in, ref_out)

    ds = gdal.Open(ref_out, gdal.GA_ReadOnly)
    out_b1 = ds.GetRasterBand(1).ReadAsArray()
    out_b2 = ds.GetRasterBand(2).ReadAsArray()

    # Verify that valid pixels are untouched
    assert np.isclose(out_b1[10, 10], 0.05)
    assert np.isclose(out_b2[10, 10], 0.10)

    # Verify all invalid elements are strictly -9999.0
    assert np.all(out_b1[0:5, :] == -9999.0)
    assert np.all(out_b1[5:7, :] == -9999.0)
    assert np.all(out_b1[7, 0:5] == -9999.0)
    assert np.all(out_b1[8, 0:5] == -9999.0)

    assert np.all(out_b2[0:5, :] == -9999.0)
    assert np.all(out_b2[5:7, :] == -9999.0)

    # Verify no zeros, negatives or non-finite remain
    assert not np.any(out_b1 == 0.0)
    assert not np.any((out_b1 <= 0.0) & (out_b1 != -9999.0))
    assert np.all(np.isfinite(out_b1))
    ds = None


def test_target_resampling_to_exact_reference_dimensions(tmp_path):
    """Test 5: Resampling of target raster to exact reference dimensions."""
    ref_gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    ref_w, ref_h = 50, 40

    # Target has different origin and width (simulating July 16)
    target_gt = (754108.386, 20.0, 0.0, 2744937.814, 0.0, -20.0)
    target_w, target_h = 52, 40

    ref_in = str(tmp_path / "ref_june.tif")
    target_in = str(tmp_path / "target_july.tif")
    target_out = str(tmp_path / "target_aligned.tif")

    b_ref = np.full((ref_h, ref_w), 0.04, dtype=np.float32)
    b_tgt = np.full((target_h, target_w), 0.06, dtype=np.float32)

    create_synthetic_geotiff(ref_in, ref_w, ref_h, ref_gt, [b_ref, b_ref])
    create_synthetic_geotiff(target_in, target_w, target_h, target_gt, [b_tgt, b_tgt])

    res = harmonize_target_raster(target_in, ref_in, target_out)
    assert res["width"] == ref_w
    assert res["height"] == ref_h
    assert res["geotransform"] == ref_gt

    ds = gdal.Open(target_out, gdal.GA_ReadOnly)
    assert ds.RasterXSize == ref_w
    assert ds.RasterYSize == ref_h
    assert ds.GetGeoTransform() == ref_gt
    assert ds.GetRasterBand(1).GetDescription() == "Sigma0_VH"
    assert ds.GetRasterBand(2).GetDescription() == "Sigma0_VV"
    assert ds.GetRasterBand(1).GetNoDataValue() == -9999.0
    ds = None


def test_identical_crs_and_geotransform_after_alignment(tmp_path):
    """Test 6: Identical CRS and geotransforms after harmonization."""
    ref_gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 30, 30
    tgt_gt = (754108.386, 20.0, 0.0, 2744937.814, 0.0, -20.0)

    june_in = str(tmp_path / "june_in.tif")
    july_in = str(tmp_path / "july_in.tif")
    june_out = str(tmp_path / "june_aligned.tif")
    july_out = str(tmp_path / "july_aligned.tif")

    b_june = np.full((h, w), 0.02, dtype=np.float32)
    b_july = np.full((h, w + 1), 0.03, dtype=np.float32)

    create_synthetic_geotiff(june_in, w, h, ref_gt, [b_june, b_june])
    create_synthetic_geotiff(july_in, w + 1, h, tgt_gt, [b_july, b_july])

    harmonize_reference_raster(june_in, june_out)
    harmonize_target_raster(july_in, june_in, july_out)

    ds_june = gdal.Open(june_out, gdal.GA_ReadOnly)
    ds_july = gdal.Open(july_out, gdal.GA_ReadOnly)

    assert ds_june.RasterXSize == ds_july.RasterXSize
    assert ds_june.RasterYSize == ds_july.RasterYSize
    assert ds_june.GetGeoTransform() == ds_july.GetGeoTransform()
    assert ds_june.GetProjection() == ds_july.GetProjection()

    # Ensure coverage analysis succeeds without error
    metrics = compute_common_coverage_and_validation(june_out, july_out)
    assert metrics["common_valid_pixels"] > 0
    ds_june = None
    ds_july = None


def test_preservation_of_valid_values_within_tolerance(tmp_path):
    """Test 7: Preservation of valid VV/VH values within expected resampling tolerance."""
    ref_gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    tgt_gt = (754108.386, 20.0, 0.0, 2744937.814, 0.0, -20.0)
    w, h = 50, 50

    ref_in = str(tmp_path / "ref_val.tif")
    tgt_in = str(tmp_path / "tgt_val.tif")
    tgt_out = str(tmp_path / "tgt_aligned.tif")

    # Target has uniform constant values inside (VH=0.035, VV=0.145)
    tgt_vh = np.full((h, w), 0.035, dtype=np.float32)
    tgt_vv = np.full((h, w), 0.145, dtype=np.float32)

    create_synthetic_geotiff(ref_in, w, h, ref_gt, [tgt_vh, tgt_vv])
    create_synthetic_geotiff(tgt_in, w, h, tgt_gt, [tgt_vh, tgt_vv])

    harmonize_target_raster(tgt_in, ref_in, tgt_out)

    ds = gdal.Open(tgt_out, gdal.GA_ReadOnly)
    warped_vh = ds.GetRasterBand(1).ReadAsArray()
    warped_vv = ds.GetRasterBand(2).ReadAsArray()

    # In the interior (away from edges), values should match original constants
    interior_vh = warped_vh[5:45, 5:45]
    interior_vv = warped_vv[5:45, 5:45]

    assert np.allclose(interior_vh, 0.035, atol=1e-4)
    assert np.allclose(interior_vv, 0.145, atol=1e-4)
    ds = None


def test_rejection_of_incorrect_band_counts(tmp_path):
    """Test 8: Rejection of incorrect band counts (e.g. 1-band or 3-band raster)."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 20, 20
    b = np.full((h, w), 0.05, dtype=np.float32)

    one_band_tif = str(tmp_path / "one_band.tif")
    three_band_tif = str(tmp_path / "three_band.tif")

    create_synthetic_geotiff(one_band_tif, w, h, gt, [b])
    create_synthetic_geotiff(three_band_tif, w, h, gt, [b, b, b])

    with pytest.raises(ValueError, match="must have exactly 2 bands"):
        verify_source_geotiff(one_band_tif)

    with pytest.raises(ValueError, match="must have exactly 2 bands"):
        verify_source_geotiff(three_band_tif)


def test_rejection_of_missing_inputs(tmp_path):
    """Test 9: Rejection of nonexistent input paths."""
    nonexistent = str(tmp_path / "nonexistent.tif")
    with pytest.raises(FileNotFoundError):
        verify_source_geotiff(nonexistent)

    with pytest.raises(RuntimeError):
        harmonize_reference_raster(nonexistent, str(tmp_path / "out.tif"))


def test_protection_against_overwriting_existing_outputs(tmp_path):
    """Test 10: Protection against overwriting existing output files."""
    gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    w, h = 10, 10
    b = np.full((h, w), 0.05, dtype=np.float32)

    src_tif = str(tmp_path / "src.tif")
    out_tif = str(tmp_path / "out.tif")

    create_synthetic_geotiff(src_tif, w, h, gt, [b, b])
    # Create existing dummy file at output location
    with open(out_tif, "w") as f:
        f.write("pre-existing content")

    # By default, must refuse to overwrite
    with pytest.raises(FileExistsError, match="already exists"):
        harmonize_reference_raster(src_tif, out_tif, overwrite=False)

    with pytest.raises(FileExistsError, match="already exists"):
        harmonize_target_raster(src_tif, src_tif, out_tif, overwrite=False)

    # With overwrite=True, it succeeds
    harmonize_reference_raster(src_tif, out_tif, overwrite=True)
    assert os.path.getsize(out_tif) > 100


def test_dimap_metadata_verification(tmp_path):
    """Test DIMAP XML cross-verification and band name validation."""
    dim_valid = str(tmp_path / "valid.dim")
    create_synthetic_dimap(dim_valid, band_names=("Sigma0_VH", "Sigma0_VV"), nodata_val="0.0")
    res = verify_dimap_metadata(dim_valid)
    assert res["verified_band_mapping"][1] == "Sigma0_VH"
    assert res["verified_band_mapping"][2] == "Sigma0_VV"
    assert res["source_nodata"] == 0.0

    # Test bad band names
    dim_invalid = str(tmp_path / "invalid.dim")
    create_synthetic_dimap(dim_invalid, band_names=("Intensity_VV", "Intensity_VH"))
    with pytest.raises(ValueError, match="expected to be 'Sigma0_VH'"):
        verify_dimap_metadata(dim_invalid)


def test_full_pipeline_synthetic_execution(tmp_path):
    """Integration test running complete pipeline on synthetic inputs."""
    ref_gt = (754115.646, 20.0, 0.0, 2744939.182, 0.0, -20.0)
    tgt_gt = (754108.386, 20.0, 0.0, 2744937.814, 0.0, -20.0)
    w, h = 30, 25

    june_in = str(tmp_path / "data" / "processed" / "geotiff" / "june10.tif")
    july_in = str(tmp_path / "data" / "processed" / "geotiff" / "july16.tif")
    june_dim = str(tmp_path / "data" / "intermediate" / "june10.dim")
    july_dim = str(tmp_path / "data" / "intermediate" / "july16.dim")

    june_out = str(tmp_path / "data" / "processed" / "aligned" / "june10_aligned.tif")
    july_out = str(tmp_path / "data" / "processed" / "aligned" / "july16_aligned.tif")
    rep_out = str(tmp_path / "data" / "metadata" / "report.json")

    b_june = np.full((h, w), 0.05, dtype=np.float32)
    b_july = np.full((h, w + 1), 0.06, dtype=np.float32)

    create_synthetic_geotiff(june_in, w, h, ref_gt, [b_june, b_june])
    create_synthetic_geotiff(july_in, w + 1, h, tgt_gt, [b_july, b_july])
    create_synthetic_dimap(june_dim)
    create_synthetic_dimap(july_dim)

    report = run_pipeline(
        project_root=tmp_path,
        june10_in=june_in,
        july16_in=july_in,
        june10_dim=june_dim,
        july16_dim=july_dim,
        june10_out=june_out,
        july16_out=july_out,
        report_out=rep_out,
        overwrite=True,
    )

    assert os.path.exists(june_out)
    assert os.path.exists(july_out)
    assert os.path.exists(rep_out)

    with open(rep_out) as f:
        rep_data = json.load(f)

    assert rep_data["validation_results"]["dimensions_match"] is True
    assert rep_data["validation_results"]["geotransform_match"] is True
    assert rep_data["coverage_metrics"]["common_valid_pixels"] > 0

