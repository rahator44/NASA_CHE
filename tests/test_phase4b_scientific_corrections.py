"""
Automated Test Suite for Phase 4B.1: Reference Ingestion Scientific Corrections and Acquisition Readiness
Earth Pulse: Dancing with the SARs (NASA Space Apps Challenge 2026)

Test Coverage:
1. SCL class 2 interpretation (Dark Area Pixels, not conflated with shadow or water).
2. SCL class 3 interpretation (Cloud Shadows uncertainty, distinct from class 2).
3. SCL NoData handling (Class 0 mapped to NoData 255).
4. Per-band BOA_ADD_OFFSET parsing.
5. Processing Baseline compatibility (Pre-04.00 vs Post-04.00).
6. Missing reflectance metadata rejection.
7. Landsat native-resolution preservation (30m spatial support documentation).
8. Landsat QA_RADSAT saturation handling.
9. PWD/EGM2008 incompatibility protection.
10. Configurable gauge plausibility warnings.
11. Preservation of raw gauge values.
12. Validation spatial-support compatibility (60m block aggregation).
"""

from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import pytest
from osgeo import gdal, osr

from scripts.validate_reference_inputs import (
    STUDY_AREA_AOI_WKT,
    ValidationResult,
    ValidationStatus,
    validate_dem_dataset,
    validate_hydrological_csv,
    validate_landsat_optical,
    validate_sentinel2_optical,
    validate_sentinel2_scaling_metadata,
)
from scripts.ingest_reference_data import (
    REF_LABEL_EXCLUDED_SNOW_ICE,
    REF_LABEL_NODATA,
    REF_LABEL_NON_WATER,
    REF_LABEL_UNCERTAIN_CLOUD,
    REF_LABEL_UNCERTAIN_DARK_AREA,
    REF_LABEL_UNCERTAIN_INVALID,
    REF_LABEL_UNCERTAIN_SHADOW,
    REF_LABEL_WATER,
    SCLMaskResult,
    aggregate_validation_to_blocks,
    find_project_root,
    ingest_copernicus_dem,
    ingest_hydrological_csv,
    ingest_landsat_l2,
    ingest_sentinel2_l2a,
    mask_landsat_qa_pixel,
    mask_sentinel2_scl,
    scale_landsat_reflectance,
    scale_sentinel2_reflectance,
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return find_project_root()


def create_synthetic_geotiff(
    path: Path,
    width: int = 20,
    height: int = 20,
    epsg: int = 32645,
    gt: Tuple[float, float, float, float, float, float] = (760000.0, 20.0, 0.0, 2735000.0, 0.0, -20.0),
    dtype: int = gdal.GDT_Float32,
    data: Optional[np.ndarray] = None,
    nodata: Optional[float] = None,
) -> Path:
    """Helper to create a synthetic georeferenced GeoTIFF in tmp_path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(str(path), width, height, 1, dtype)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetGeoTransform(gt)
    band = ds.GetRasterBand(1)
    if nodata is not None:
        band.SetNoDataValue(nodata)
    if data is not None:
        band.WriteArray(data)
    else:
        band.WriteArray(np.ones((height, width), dtype=np.float32) * 100.0)
    ds = None
    return path


# -----------------------------------------------------------------------------
# Test 1: SCL Class 2 Interpretation (Dark Area Pixels)
# -----------------------------------------------------------------------------
def test_01_scl_class2_dark_area_interpretation():
    """Verify SCL class 2 is identified as Dark Area Pixels and NOT conflated with cloud shadow (class 3) or water (class 6)."""
    scl = np.array([[2, 3, 6], [2, 4, 5]], dtype=np.uint8)
    res = mask_sentinel2_scl(scl)

    assert isinstance(res, SCLMaskResult)
    # Class 2 positions
    assert res.dark_area_mask[0, 0] == True
    assert res.dark_area_mask[1, 0] == True

    # Confirm NOT conflated with cloud shadow (class 3)
    assert res.cloud_shadow_mask[0, 0] == False
    assert res.cloud_shadow_mask[0, 1] == True  # Only position (0, 1) is class 3
    assert np.all(res.dark_area_mask & res.cloud_shadow_mask == False)

    # Confirm NOT conflated with water (class 6)
    assert res.water_mask[0, 0] == False
    assert res.water_mask[0, 2] == True  # Position (0, 2) is water
    assert np.all(res.dark_area_mask & res.water_mask == False)

    # Dark area pixels must be included in uncertain mask (not clear)
    assert res.uncertain_mask[0, 0] == True
    assert res.clear_mask[0, 0] == False


# -----------------------------------------------------------------------------
# Test 2: SCL Class 3 Interpretation (Cloud Shadows)
# -----------------------------------------------------------------------------
def test_02_scl_class3_cloud_shadow_interpretation():
    """Verify SCL class 3 is identified specifically as Cloud Shadows uncertainty."""
    scl = np.array([[3, 3], [7, 8]], dtype=np.uint8)
    res = mask_sentinel2_scl(scl)

    assert np.all(res.cloud_shadow_mask[0, :] == True)
    assert np.all(res.cloud_shadow_mask[1, :] == False)
    assert np.all(res.dark_area_mask == False)
    # Cloud cirrus mask should only be row 1
    assert np.all(res.cloud_cirrus_mask[1, :] == True)
    assert np.all(res.cloud_cirrus_mask[0, :] == False)


# -----------------------------------------------------------------------------
# Test 3: SCL NoData Handling
# -----------------------------------------------------------------------------
def test_03_scl_nodata_handling():
    """Verify SCL class 0 is mapped to NoData (value 255), distinct from atmospheric uncertainty."""
    scl = np.array([[0, 2], [3, 4]], dtype=np.uint8)
    res = mask_sentinel2_scl(scl)

    assert res.nodata_mask[0, 0] == True
    assert res.nodata_mask[0, 1] == False
    assert res.clear_mask[0, 0] == False
    assert res.uncertain_mask[0, 0] == True


# -----------------------------------------------------------------------------
# Test 4: Per-Band BOA_ADD_OFFSET Parsing
# -----------------------------------------------------------------------------
def test_04_per_band_boa_add_offset_parsing():
    """Verify parsing per-band BOA_ADD_OFFSET dictionary for baseline >= 04.00."""
    meta_post_04 = {
        "processing_baseline": "04.00",
        "quantification_value": 10000.0,
        "boa_add_offsets": {
            "B03": -1000.0,
            "B08": -1000.0,
            "B11": -1000.0,
            "B12": -1000.0,
        },
    }
    is_valid, errs, info = validate_sentinel2_scaling_metadata(meta_post_04)
    assert is_valid is True
    assert len(errs) == 0
    assert info["baseline_numeric"] == 4.00
    assert info["quantification_value"] == 10000.0
    assert info["per_band_offsets"]["B03"] == -1000.0
    assert info["per_band_offsets"]["B11"] == -1000.0


# -----------------------------------------------------------------------------
# Test 5: Processing Baseline Compatibility
# -----------------------------------------------------------------------------
def test_05_processing_baseline_compatibility():
    """Verify baseline < 04.00 defaults offset to 0.0 while >= 04.00 enforces explicit offsets."""
    # Pre-04.00 baseline (e.g. 02.14) without offsets supplied
    meta_pre_04 = {
        "processing_baseline": "02.14",
        "quantification_value": 10000.0,
    }
    is_valid_pre, errs_pre, info_pre = validate_sentinel2_scaling_metadata(meta_pre_04)
    assert is_valid_pre is True
    assert info_pre["baseline_numeric"] == 2.14
    assert info_pre["per_band_offsets"]["B03"] == 0.0
    assert info_pre["per_band_offsets"]["B11"] == 0.0

    # Post-04.00 baseline (e.g. 05.10) without offsets supplied must fail
    meta_post_missing = {
        "processing_baseline": "05.10",
        "quantification_value": 10000.0,
    }
    is_valid_post, errs_post, _ = validate_sentinel2_scaling_metadata(meta_post_missing)
    assert is_valid_post is False
    assert any("boa_add_offsets" in e for e in errs_post)


# -----------------------------------------------------------------------------
# Test 6: Missing Reflectance Metadata Rejection
# -----------------------------------------------------------------------------
def test_06_missing_reflectance_metadata_rejection():
    """Verify missing or non-positive quantification value causes validation failure."""
    meta_bad_quant = {
        "processing_baseline": "04.00",
        "quantification_value": -100.0,  # Negative invalid
        "boa_add_offsets": {"B03": -1000, "B08": -1000, "B11": -1000, "B12": -1000},
    }
    is_valid, errs, _ = validate_sentinel2_scaling_metadata(meta_bad_quant)
    assert is_valid is False
    assert any("quantification_value" in e for e in errs)

    meta_missing_baseline = {
        "quantification_value": 10000.0,
    }
    is_valid_b, errs_b, _ = validate_sentinel2_scaling_metadata(meta_missing_baseline)
    assert is_valid_b is False
    assert any("processing_baseline" in e for e in errs_b)


# -----------------------------------------------------------------------------
# Test 7: Landsat Native-Resolution Preservation
# -----------------------------------------------------------------------------
def test_07_landsat_native_resolution_preservation(tmp_path: Path):
    """Verify ingested Landsat metadata documents native 30m resolution and spatial support notice."""
    bands = {}
    for b in ["SR_B3", "SR_B5", "SR_B6", "QA_PIXEL"]:
        bands[b] = create_synthetic_geotiff(tmp_path / f"ls_{b}.tif", width=15, height=15)

    out_dir = tmp_path / "out_ls"
    result = ingest_landsat_l2(bands, out_dir)

    assert "spatial_support" in result
    sp = result["spatial_support"]
    assert sp["native_spatial_resolution_m"] == 30.0
    assert sp["resampled_grid_resolution_m"] == 20.0
    assert "spatial_support_notice" in sp
    assert "30 m" in sp["spatial_support_notice"]
    assert "does NOT generate independent 20 m optical ground information" in sp["spatial_support_notice"]


# -----------------------------------------------------------------------------
# Test 8: Landsat QA_RADSAT Saturation Handling
# -----------------------------------------------------------------------------
def test_08_landsat_qa_radsat_handling():
    """Verify QA_RADSAT saturation in reflective bands B3 (bit 2), B5 (bit 4), or B6 (bit 5) masks pixels."""
    qa_pixel = np.zeros(4, dtype=np.uint16)  # Clear pixel per QA_PIXEL
    # QA_RADSAT:
    # idx 0: 0 (No saturation)
    # idx 1: (1 << 2) = 4 (Band 3 saturation)
    # idx 2: (1 << 4) = 16 (Band 5 saturation)
    # idx 3: (1 << 5) = 32 (Band 6 saturation)
    qa_radsat = np.array([0, 4, 16, 32], dtype=np.uint16)

    clear_mask, cloud_shadow_mask, nodata_mask = mask_landsat_qa_pixel(qa_pixel, qa_radsat)

    assert clear_mask[0] == True
    assert cloud_shadow_mask[0] == False

    # Indices 1, 2, 3 must be excluded due to radiometric saturation
    assert clear_mask[1] == False
    assert cloud_shadow_mask[1] == True
    assert clear_mask[2] == False
    assert cloud_shadow_mask[2] == True
    assert clear_mask[3] == False
    assert cloud_shadow_mask[3] == True


# -----------------------------------------------------------------------------
# Test 9: PWD / EGM2008 Incompatibility Protection
# -----------------------------------------------------------------------------
def test_09_pwd_egm2008_incompatibility_protection(tmp_path: Path):
    """Verify multiple conflicting vertical datums (PWD and EGM2008) in single gauge series are rejected."""
    csv_p = tmp_path / "mixed_datums.csv"
    csv_p.write_text(
        "station_id,station_name,observation_datetime,water_level,unit,vertical_datum,provider,source_identifier,source_citation,quality_flag\n"
        "SW46.9,Sirajganj,2024-07-16T06:00:00Z,13.45,m,PWD,BWDB,FFWC-2024,BWDB 2024,GOOD\n"
        "SW46.9,Sirajganj,2024-07-16T09:00:00Z,13.91,m,EGM2008,BWDB,FFWC-2024,BWDB 2024,GOOD\n",
        encoding="utf-8",
    )

    val_res = validate_hydrological_csv(csv_p)
    assert val_res.status == ValidationStatus.REJECTED
    assert any("DATUM_INCOMPATIBILITY_PROTECTION" in e for e in val_res.errors)


# -----------------------------------------------------------------------------
# Test 10: Configurable Gauge Plausibility Warnings
# -----------------------------------------------------------------------------
def test_10_configurable_gauge_plausibility_warnings(tmp_path: Path):
    """Verify out-of-plausibility gauge readings emit a WARNING but are NOT rejected."""
    csv_p = tmp_path / "high_stage.csv"
    csv_p.write_text(
        "station_id,station_name,observation_datetime,water_level,unit,vertical_datum,provider,source_identifier,source_citation,quality_flag\n"
        "SW46.9,Sirajganj,2024-07-16T06:00:00Z,16.50,m,PWD,BWDB,FFWC-2024,BWDB 2024,GOOD\n",
        encoding="utf-8",
    )

    # Pass station plausibility range (5.0, 15.0) -> 16.50 exceeds max plausibility
    val_res = validate_hydrological_csv(csv_p, plausibility_range=(5.0, 15.0))
    assert val_res.status == ValidationStatus.WARNING
    assert len(val_res.errors) == 0
    assert any("Plausibility notice" in w for w in val_res.warnings)


# -----------------------------------------------------------------------------
# Test 11: Preservation of Raw Gauge Values
# -----------------------------------------------------------------------------
def test_11_preservation_of_raw_gauge_values(tmp_path: Path):
    """Verify raw observed water level values are preserved exactly in output CSV."""
    csv_p = tmp_path / "raw_gauge.csv"
    csv_p.write_text(
        "station_id,station_name,observation_datetime,water_level,unit,vertical_datum,provider,source_identifier,source_citation,quality_flag\n"
        "SW46.9,Sirajganj,2024-07-16T06:00:00Z,13.4567,m,PWD,BWDB,FFWC-2024,BWDB 2024,GOOD\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out_hydro"
    summary = ingest_hydrological_csv(csv_p, out_dir)

    validated_csv = Path(summary["validated_csv"])
    df_out = pd.read_csv(validated_csv)
    # Check exact raw float preservation
    assert pytest.approx(df_out.loc[0, "water_level"], 1e-6) == 13.4567


# -----------------------------------------------------------------------------
# Test 12: Validation Spatial-Support Compatibility
# -----------------------------------------------------------------------------
def test_12_validation_spatial_support_compatibility():
    """Verify 60m block aggregation comparison between 20m SAR and optical reference masks."""
    # 6x6 SAR grid (20m pixels) -> two 3x3 60m blocks
    # Block 1 (top-left 3x3): all 1s (water)
    # Block 2 (top-right 3x3): all 0s (non-water)
    sar_mask = np.zeros((6, 6), dtype=np.uint8)
    sar_mask[:3, :3] = 1
    sar_mask[:3, 3:] = 0
    sar_mask[3:, :] = 0

    # Optical mask: same pattern
    opt_mask = np.zeros((6, 6), dtype=np.uint8)
    opt_mask[:3, :3] = 1
    opt_mask[:3, 3:] = 0
    opt_mask[3:, :] = 0

    sar_blocks, opt_blocks = aggregate_validation_to_blocks(
        sar_mask, opt_mask, block_size_sar=3, block_size_optical=3
    )

    # 6x6 with block_size=3 yields 2x2 blocks
    assert sar_blocks.shape == (2, 2)
    assert opt_blocks.shape == (2, 2)
    assert sar_blocks[0, 0] == 1  # Water block
    assert sar_blocks[0, 1] == 0  # Non-water block
    assert opt_blocks[0, 0] == 1
    assert opt_blocks[0, 1] == 0

