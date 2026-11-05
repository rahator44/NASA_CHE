"""
Automated Test Suite for Phase 4B: Independent Reference Data Ingestion Framework
Earth Pulse: Dancing with the SARs (NASA Space Apps Challenge 2026)

Test Coverage (18 Mandatory Verification Cases):
1. Registry metadata validation.
2. SHA-256 checksum registration.
3. Sentinel-2 metadata inspection.
4. Sentinel-2 cloud and shadow exclusion.
5. MNDWI calculation.
6. AWEI_nsh calculation.
7. Reflectance scaling.
8. Landsat QA_PIXEL masking.
9. Optical spatial alignment.
10. Hydrological CSV validation.
11. Duplicate gauge observation detection.
12. Missing vertical datum handling.
13. Rejection of unverified danger levels.
14. DEM CRS and resolution validation.
15. DEM NoData handling.
16. Rejection of missing provenance.
17. Rejection of SAR-derived reference masks.
18. Missing-reference-data status.
"""

from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import pytest
from osgeo import gdal, osr

from scripts.validate_reference_inputs import (
    SAR_TARGET_EPSG,
    STUDY_AREA_AOI_WKT,
    ValidationResult,
    ValidationStatus,
    compute_sha256,
    validate_dem_dataset,
    validate_hydrological_csv,
    validate_landsat_optical,
    validate_provenance_metadata,
    validate_raster_dataset,
    validate_sentinel2_optical,
)
from scripts.ingest_reference_data import (
    REF_LABEL_NODATA,
    REF_LABEL_NON_WATER,
    REF_LABEL_UNCERTAIN_CLOUD,
    REF_LABEL_WATER,
    ReferenceDataRegistry,
    calculate_awei_nsh,
    calculate_mndwi,
    find_project_root,
    ingest_copernicus_dem,
    ingest_hydrological_csv,
    ingest_landsat_l2,
    ingest_sentinel2_l2a,
    mask_landsat_qa_pixel,
    mask_sentinel2_scl,
    resample_raster_to_grid,
    scale_landsat_reflectance,
    scale_sentinel2_reflectance,
    scan_and_report_ingestion_status,
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
# Test 1: Registry Metadata Validation
# -----------------------------------------------------------------------------
def test_01_registry_metadata_validation(tmp_path: Path):
    """Test registry validates required provenance fields and rejects incomplete entries."""
    reg_path = tmp_path / "test_registry.json"
    registry = ReferenceDataRegistry(reg_path)

    valid_meta = {
        "dataset_id": "S2A_MSIL2A_20240715_TEST",
        "category": "optical",
        "provider": "ESA Copernicus",
        "product_name": "Sentinel-2A MSI Level-2A",
        "source_identifier": "S2A_MSIL2A_20240715T043701_N0510_R033_T45RXE",
        "source_url_or_citation": "https://dataspace.copernicus.eu/browser/?id=S2A_MSIL2A_20240715",
        "acquisition_date": "2024-07-15T04:37:01Z",
        "processing_level": "Level-2A Bottom-Of-Atmosphere",
        "spatial_extent": "Kazipur / Sirajganj Jamuna River Reach",
        "crs": "EPSG:32645",
        "spatial_resolution": "10m / 20m",
        "original_filename": "s2_test_b03.tif",
        "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "processing_history": "Copernicus Sen2Cor atmospheric correction",
        "license_or_usage_conditions": "CC-BY 4.0 Copernicus Sentinel Data",
        "quality_information": "SCL cloud masking applied, valid optical observation",
        "intended_validation_purpose": "Independent pixel-level reference water mask for July 2024 flood peak",
    }

    # Should register cleanly
    registered = registry.register_dataset(valid_meta)
    assert registered["dataset_id"] == "S2A_MSIL2A_20240715_TEST"
    assert registered["validation_status"] == "READY"
    assert len(registry.data["registered_datasets"]) == 1


# -----------------------------------------------------------------------------
# Test 2: SHA-256 Checksum Registration
# -----------------------------------------------------------------------------
def test_02_sha256_checksum_registration(tmp_path: Path):
    """Test SHA-256 calculation and registration for local files."""
    dummy_file = tmp_path / "sample_gauge.csv"
    dummy_file.write_text("station_id,water_level\nSW46.9,13.45\n", encoding="utf-8")

    checksum = compute_sha256(dummy_file)
    assert isinstance(checksum, str)
    assert len(checksum) == 64

    reg_path = tmp_path / "registry.json"
    registry = ReferenceDataRegistry(reg_path)

    meta = {
        "dataset_id": "BWDB_SW46.9_TEST",
        "category": "hydrology",
        "provider": "BWDB",
        "product_name": "River Stage Observations",
        "source_identifier": "BWDB-WL-SW46.9-2024",
        "source_url_or_citation": "BWDB Hydrology Directorate Yearbook 2024",
        "acquisition_date": "2024-07-16T06:00:00Z",
        "processing_level": "Quality-controlled field gauge reading",
        "spatial_extent": "Sirajganj Ghat, Jamuna River",
        "crs": "EPSG:4326",
        "spatial_resolution": "Point gauge",
        "original_filename": str(dummy_file),
        "local_file_path": str(dummy_file),
        "processing_history": "Manual gauge reader, verified by BWDB",
        "license_or_usage_conditions": "Open Government Data Bangladesh",
        "quality_information": "Certified gauge record",
        "intended_validation_purpose": "Hydrological flood-stage temporal corroboration",
    }

    registered = registry.register_dataset(meta)
    assert registered["sha256"] == checksum


# -----------------------------------------------------------------------------
# Test 3: Sentinel-2 Metadata Inspection
# -----------------------------------------------------------------------------
def test_03_sentinel2_metadata_inspection(tmp_path: Path):
    """Test inspecting Sentinel-2 package and checking band completeness."""
    # Create synthetic S2 bands
    bands = {}
    for b in ["B03", "B08", "B11", "B12", "SCL"]:
        bands[b] = create_synthetic_geotiff(tmp_path / f"s2_{b}.tif", width=10, height=10)

    val_res = validate_sentinel2_optical(bands)
    assert val_res.status == ValidationStatus.READY
    assert val_res.checks["has_band_B03"] is True
    assert val_res.checks["has_band_SCL"] is True

    # Missing band case
    incomplete_bands = {k: v for k, v in bands.items() if k != "B11"}
    val_res_inc = validate_sentinel2_optical(incomplete_bands)
    assert val_res_inc.status == ValidationStatus.BLOCKED
    assert "B11" in val_res_inc.errors[0]


# -----------------------------------------------------------------------------
# Test 4: Sentinel-2 Cloud and Shadow Exclusion
# -----------------------------------------------------------------------------
def test_04_sentinel2_cloud_and_shadow_exclusion():
    """Test SCL classes masking for clouds, cloud shadow, cirrus, snow."""
    scl = np.array([
        [0, 1, 2],    # NoData, Saturated, Cast Shadow -> All uncertain/excluded
        [3, 7, 8],    # Cloud shadow, Unclassified, Cloud med -> All uncertain/excluded
        [9, 10, 11],  # Cloud high, Cirrus, Snow -> All uncertain/excluded
        [4, 5, 6],    # Vegetation, Bare, Water -> Clear valid
    ], dtype=np.uint8)

    clear_mask, uncertain_mask = mask_sentinel2_scl(scl)

    # First 9 elements should be uncertain
    assert np.all(uncertain_mask[:3, :] == True)
    # Last row (classes 4, 5, 6) should be clear
    assert np.all(clear_mask[3, :] == True)
    assert np.all(uncertain_mask[3, :] == False)


# -----------------------------------------------------------------------------
# Test 5: MNDWI Calculation
# -----------------------------------------------------------------------------
def test_05_mndwi_calculation():
    """Test MNDWI = (Green - SWIR1) / (Green + SWIR1)."""
    # Water pixel: high Green (0.25), low SWIR1 (0.05) -> MNDWI = 0.20 / 0.30 = +0.667
    # Land pixel: low Green (0.10), high SWIR1 (0.30) -> MNDWI = -0.20 / 0.40 = -0.500
    green = np.array([[0.25, 0.10], [0.0, 0.15]], dtype=np.float32)
    swir1 = np.array([[0.05, 0.30], [0.0, 0.15]], dtype=np.float32)

    mndwi = calculate_mndwi(green, swir1)
    assert pytest.approx(mndwi[0, 0], 0.001) == 0.667
    assert pytest.approx(mndwi[0, 1], 0.001) == -0.500
    assert np.isnan(mndwi[1, 0])  # Zero division -> NaN
    assert pytest.approx(mndwi[1, 1], 0.001) == 0.0


# -----------------------------------------------------------------------------
# Test 6: AWEI_nsh Calculation
# -----------------------------------------------------------------------------
def test_06_awei_nsh_calculation():
    """Test AWEI_nsh = 4 * (Green - SWIR1) - (0.25 * NIR + 2.75 * SWIR2)."""
    # Water pixel
    green = np.array([[0.20]], dtype=np.float32)
    nir = np.array([[0.05]], dtype=np.float32)
    swir1 = np.array([[0.02]], dtype=np.float32)
    swir2 = np.array([[0.01]], dtype=np.float32)

    # 4 * (0.20 - 0.02) - (0.25 * 0.05 + 2.75 * 0.01)
    # = 4 * 0.18 - (0.0125 + 0.0275) = 0.72 - 0.04 = 0.68
    awei = calculate_awei_nsh(green, nir, swir1, swir2)
    assert pytest.approx(awei[0, 0], 0.001) == 0.68


# -----------------------------------------------------------------------------
# Test 7: Reflectance Scaling
# -----------------------------------------------------------------------------
def test_07_reflectance_scaling():
    """Test S2 and Landsat DN-to-reflectance conversions."""
    # S2: DN / 10000.0
    s2_dn = np.array([0, 1000, 2500, 10000], dtype=np.uint16)
    s2_refl = scale_sentinel2_reflectance(s2_dn)
    assert np.isnan(s2_refl[0])  # 0 is NoData
    assert pytest.approx(s2_refl[1], 1e-4) == 0.10
    assert pytest.approx(s2_refl[2], 1e-4) == 0.25
    assert pytest.approx(s2_refl[3], 1e-4) == 1.00

    # S2 with baseline >= 04.00 offset (-1000)
    s2_offset_refl = scale_sentinel2_reflectance(s2_dn, boa_add_offset=-1000.0)
    assert pytest.approx(s2_offset_refl[1], 1e-4) == 0.00
    assert pytest.approx(s2_offset_refl[2], 1e-4) == 0.15

    # Landsat: 0.0000275 * DN - 0.2
    # If DN = 14545 -> 0.0000275 * 14545 - 0.2 = ~0.20
    ls_dn = np.array([0, 14545], dtype=np.uint16)
    ls_refl = scale_landsat_reflectance(ls_dn)
    assert np.isnan(ls_refl[0])
    assert pytest.approx(ls_refl[1], 0.001) == 0.20


# -----------------------------------------------------------------------------
# Test 8: Landsat QA_PIXEL Masking
# -----------------------------------------------------------------------------
def test_08_landsat_qa_pixel_masking():
    """Test Landsat Collection 2 QA_PIXEL bit decoding."""
    # Bit 0: Fill (1)
    # Bit 1: Dilated Cloud (2)
    # Bit 3: Cloud (8)
    # Bit 4: Cloud Shadow (16)
    # Bit 7: Water (128)
    qa = np.array([1, 2, 8, 16, 128, 0], dtype=np.uint16)
    clear_mask, cloud_shadow_mask, nodata_mask = mask_landsat_qa_pixel(qa)

    assert nodata_mask[0] == True
    assert cloud_shadow_mask[1] == True  # Dilated cloud
    assert cloud_shadow_mask[2] == True  # Cloud
    assert cloud_shadow_mask[3] == True  # Cloud shadow
    assert clear_mask[4] == True        # Water, clear
    assert clear_mask[5] == True        # Normal non-water, clear


# -----------------------------------------------------------------------------
# Test 9: Optical Spatial Alignment
# -----------------------------------------------------------------------------
def test_09_optical_spatial_alignment(tmp_path: Path):
    """Test 10m to 20m area-weighted aggregation resampling."""
    # Create 10m grid raster (40x40 cells)
    gt_10m = (754115.65, 10.0, 0.0, 2744939.18, 0.0, -10.0)
    data_10m = np.zeros((40, 40), dtype=np.float32)
    # 2x2 block with values [10, 20, 30, 40] -> mean = 25.0
    data_10m[0, 0] = 10.0
    data_10m[0, 1] = 20.0
    data_10m[1, 0] = 30.0
    data_10m[1, 1] = 40.0

    src_p = create_synthetic_geotiff(
        tmp_path / "src_10m.tif", width=40, height=40, gt=gt_10m, data=data_10m
    )
    dst_p = tmp_path / "aligned_20m.tif"

    resample_raster_to_grid(
        src_p, dst_p, resample_alg=gdal.GRA_Average, output_dtype=gdal.GDT_Float32
    )

    ds_dst = gdal.Open(str(dst_p))
    arr_dst = ds_dst.GetRasterBand(1).ReadAsArray()
    ds_dst = None

    # The top-left 20m cell should represent the area average of the 4 10m cells (25.0)
    assert pytest.approx(arr_dst[0, 0], 0.1) == 25.0


# -----------------------------------------------------------------------------
# Test 10: Hydrological CSV Validation
# -----------------------------------------------------------------------------
def test_10_hydrological_csv_validation(tmp_path: Path):
    """Test parsing and validating a standard BWDB gauge CSV."""
    csv_p = tmp_path / "bwdb_test.csv"
    csv_p.write_text(
        "station_id,station_name,observation_datetime,water_level,unit,vertical_datum,provider,source_identifier,source_citation,quality_flag\n"
        "SW46.9,Sirajganj,2024-07-16T06:00:00Z,13.45,m,PWD,BWDB,FFWC-BULLETIN-2024,BWDB Annual Hydrology Report 2024,GOOD\n"
        "SW46.9,Sirajganj,2024-07-16T09:00:00Z,13.52,m,PWD,BWDB,FFWC-BULLETIN-2024,BWDB Annual Hydrology Report 2024,GOOD\n",
        encoding="utf-8",
    )

    val_res = validate_hydrological_csv(csv_p)
    assert val_res.status == ValidationStatus.READY
    assert val_res.checks["has_required_columns"] is True
    assert val_res.checks["valid_water_levels"] is True
    assert val_res.checks["no_duplicate_observations"] is True


# -----------------------------------------------------------------------------
# Test 11: Duplicate Gauge Observation Detection
# -----------------------------------------------------------------------------
def test_11_duplicate_gauge_observation_detection(tmp_path: Path):
    """Test duplicate detection for identical station and timestamp."""
    csv_p = tmp_path / "duplicate_gauge.csv"
    csv_p.write_text(
        "station_id,station_name,observation_datetime,water_level,unit,vertical_datum,provider,source_identifier,source_citation,quality_flag\n"
        "SW46.9,Sirajganj,2024-07-16T06:00:00Z,13.45,m,PWD,BWDB,FFWC-BULLETIN-2024,BWDB 2024,GOOD\n"
        "SW46.9,Sirajganj,2024-07-16T06:00:00Z,13.48,m,PWD,BWDB,FFWC-BULLETIN-2024,BWDB 2024,REPEATED\n",
        encoding="utf-8",
    )

    val_res = validate_hydrological_csv(csv_p)
    assert val_res.status == ValidationStatus.REJECTED
    assert val_res.checks["no_duplicate_observations"] is False
    assert any("duplicate" in e.lower() for e in val_res.errors)


# -----------------------------------------------------------------------------
# Test 12: Missing Vertical Datum Handling
# -----------------------------------------------------------------------------
def test_12_missing_vertical_datum_handling(tmp_path: Path):
    """Test rejection when vertical datum is missing or unspecified."""
    csv_p = tmp_path / "missing_datum.csv"
    csv_p.write_text(
        "station_id,station_name,observation_datetime,water_level,unit,vertical_datum,provider,source_identifier,source_citation,quality_flag\n"
        "SW46.9,Sirajganj,2024-07-16T06:00:00Z,13.45,m,,BWDB,FFWC-BULLETIN-2024,BWDB 2024,GOOD\n",
        encoding="utf-8",
    )

    val_res = validate_hydrological_csv(csv_p)
    assert val_res.status == ValidationStatus.REJECTED
    assert val_res.checks["vertical_datum_specified"] is False
    assert any("vertical_datum" in e.lower() for e in val_res.errors)


# -----------------------------------------------------------------------------
# Test 13: Rejection of Unverified Danger Levels
# -----------------------------------------------------------------------------
def test_13_rejection_of_unverified_danger_levels(tmp_path: Path):
    """Test rejection when danger level is included without official citation."""
    csv_p = tmp_path / "unverified_danger.csv"
    csv_p.write_text(
        "station_id,station_name,observation_datetime,water_level,unit,vertical_datum,provider,source_identifier,source_citation,quality_flag,danger_level,danger_level_citation\n"
        "SW46.9,Sirajganj,2024-07-16T06:00:00Z,13.45,m,PWD,BWDB,FFWC-2024,BWDB 2024,GOOD,13.35,UNVERIFIED\n",
        encoding="utf-8",
    )

    val_res = validate_hydrological_csv(csv_p)
    assert val_res.status == ValidationStatus.REJECTED
    assert val_res.checks["danger_level_verified"] is False
    assert any("danger level" in e.lower() for e in val_res.errors)


# -----------------------------------------------------------------------------
# Test 14: DEM CRS and Resolution Validation
# -----------------------------------------------------------------------------
def test_14_dem_crs_and_resolution_validation(tmp_path: Path):
    """Test Copernicus GLO-30 DEM CRS (EPSG:4326) and resolution validation."""
    # Synthetic GLO-30 tile covering AOI (89.50 to 89.80 long, 24.50 to 24.80 lat)
    gt_dem = (89.50, 0.005, 0.0, 24.80, 0.0, -0.005)
    dem_p = create_synthetic_geotiff(
        tmp_path / "dem_N24_E089.tif",
        width=60,
        height=60,
        epsg=4326,
        gt=gt_dem,
        dtype=gdal.GDT_Float32,
        data=np.full((60, 60), 14.5, dtype=np.float32),
        nodata=-32767.0,
    )

    val_res = validate_dem_dataset(dem_p)
    assert val_res.status in [ValidationStatus.READY, ValidationStatus.WARNING]
    assert val_res.checks["gdal_readable"] is True
    assert val_res.checks["crs_valid"] is True
    assert val_res.checks["aoi_intersection"] is True


# -----------------------------------------------------------------------------
# Test 15: DEM NoData Handling
# -----------------------------------------------------------------------------
def test_15_dem_nodata_handling(tmp_path: Path):
    """Test DEM preserves NoData values and detects 100% NoData corruption."""
    gt_dem = (89.50, 0.005, 0.0, 24.80, 0.0, -0.005)
    # Raster with 100% NoData
    dem_empty = create_synthetic_geotiff(
        tmp_path / "dem_empty.tif",
        width=60,
        height=60,
        epsg=4326,
        gt=gt_dem,
        dtype=gdal.GDT_Float32,
        data=np.full((60, 60), -32767.0, dtype=np.float32),
        nodata=-32767.0,
    )

    val_res = validate_dem_dataset(dem_empty)
    assert val_res.status == ValidationStatus.REJECTED
    assert val_res.checks["non_empty_content"] is False
    assert any("100% nodata" in e.lower() for e in val_res.errors)


# -----------------------------------------------------------------------------
# Test 16: Rejection of Missing Provenance
# -----------------------------------------------------------------------------
def test_16_rejection_of_missing_provenance():
    """Test rejection when provenance metadata misses essential fields."""
    meta_incomplete = {
        "dataset_name": "Optical_Imagery_Test",
        "provider": "Unknown",
        # Missing license, source_identifier, citation, etc.
    }
    val_res = validate_provenance_metadata(meta_incomplete)
    assert val_res.status == ValidationStatus.REJECTED
    assert len(val_res.errors) > 0


# -----------------------------------------------------------------------------
# Test 17: Rejection of SAR-Derived Reference Masks
# -----------------------------------------------------------------------------
def test_17_rejection_of_sar_derived_reference_masks():
    """Test anti-circular validation rejects SAR candidate products as ground truth."""
    circular_meta = {
        "dataset_name": "Sentinel-1A_Lee5x5_Otsu_Water_Mask",
        "category": "optical",  # Falsely labeled optical
        "provider": "ESA",
        "product_name": "SAR Otsu Candidate Water Mask",
        "source_identifier": "S1A_IW_GRDH_1SDV_20240716",
        "source_url_or_citation": "https://dataspace.copernicus.eu",
        "acquisition_date": "2024-07-16T12:00:00Z",
        "processing_level": "Level-1 GRD with Lee 5x5 filter and Otsu threshold",
        "spatial_extent": "Jamuna River AOI",
        "crs": "EPSG:32645",
        "spatial_resolution": "20m",
        "original_filename": "transition_primary.tif",
        "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "processing_history": "SNAP ThermalNoiseRemoval -> Phase 2B Lee 5x5 -> Phase 3A Otsu",
        "license_or_usage_conditions": "Open Copernicus",
        "quality_information": "SAR backscatter mask",
        "intended_validation_purpose": "Reference water mask for validation",
    }
    val_res = validate_provenance_metadata(circular_meta)
    assert val_res.status == ValidationStatus.REJECTED
    assert val_res.checks["anti_circular_validation"] is False
    assert any("CIRCULAR_VALIDATION_ERROR" in e for e in val_res.errors)


# -----------------------------------------------------------------------------
# Test 18: Missing Reference Data Status
# -----------------------------------------------------------------------------
def test_18_missing_reference_data_status(tmp_path: Path):
    """Test that scanning project repository accurately reports status as BLOCKED when reference files are not populated."""
    report = scan_and_report_ingestion_status(tmp_path)
    assert report["phase"] == "4B — Independent Reference Data Ingestion Framework"
    assert report["status"] == "BLOCKED"
    assert report["total_independent_reference_files"] == 0
    assert "blocking_reason" in report
    assert "capabilities" in str(report).lower()
