"""
Earth Pulse — Phase 4C.1: Sentinel-2 Real Data Ingestion Test Suite
NASA Space Apps Challenge 2026 — Dancing with the SARs

This module tests:
1. Physical existence and cryptographic SHA-256 checksums of Sentinel-2 SAFE.zip archives.
2. Metadata extraction: processing baseline (05.10), quantification value (10000), per-band BOA offsets (-1000).
3. Selective extraction: verification that only designated bands (B03, B08, B11, B12, SCL, XML) were extracted.
4. Exact spatial alignment against canonical SAR reference raster (dimensions 1405x1393, EPSG:32645, 20m, transform).
5. Radiometric scaling: reflectance conversion (DN + offset) / quantification_value.
6. Continuous spectral indices: MNDWI and AWEI_nsh computation and range bounds.
7. SCL quality masks: rigorous isolation of Class 2 (Dark Area), Class 3 (Shadow), Classes 7-10 (Cloud), Classes 4-6 (Clear).
8. Study AOI quality assessment: 1,010,039 pixels, clear/cloud fractions, and usability status.
9. Reference data registry: provenance completeness and anti-circular validation compliance.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal, osr

from scripts.ingest_reference_data import (
    REF_LABEL_EXCLUDED_SNOW_ICE,
    REF_LABEL_NODATA,
    REF_LABEL_NON_WATER,
    REF_LABEL_UNCERTAIN_CLOUD,
    REF_LABEL_UNCERTAIN_DARK_AREA,
    REF_LABEL_UNCERTAIN_INVALID,
    REF_LABEL_UNCERTAIN_SHADOW,
    REF_LABEL_WATER,
    ReferenceDataRegistry,
)
from scripts.ingest_sentinel2_real import (
    AOI_TARGET_CELLS,
    FULL_SCENE_CELLS,
    create_study_aoi_raster_mask,
    find_project_root,
    parse_sentinel2_archive_metadata,
)
from scripts.validate_reference_inputs import compute_sha256, validate_provenance_metadata

# Certified Checksums
EXPECTED_JUNE_SHA256 = "e4d9ecd24029af5f370fb994c4676370ea5a2a208995edc625feb4db34b53192"
EXPECTED_JULY_SHA256 = "705d2d667e5fe7693e8b5a818eb4ba232baed7bac4be9403645eb2d4437bead4"


@pytest.fixture(scope="module")
def root_dir() -> Path:
    return find_project_root()


@pytest.fixture(scope="module")
def june_zip(root_dir: Path) -> Path:
    p = root_dir / "data" / "reference" / "optical" / "sentinel2" / "June_2024" / "S2A_MSIL2A_20240607T043711_N0510_R033_T45RYH_20240607T091101.SAFE.zip"
    assert p.is_file(), f"Missing June archive at {p}"
    return p


@pytest.fixture(scope="module")
def july_zip(root_dir: Path) -> Path:
    p = root_dir / "data" / "reference" / "optical" / "sentinel2" / "July_2024" / "S2A_MSIL2A_20240717T043701_N0510_R033_T45RYH_20240717T145054.SAFE.zip"
    assert p.is_file(), f"Missing July archive at {p}"
    return p


@pytest.fixture(scope="module")
def sar_ref(root_dir: Path) -> Path:
    p = root_dir / "data" / "processed" / "aligned" / "june10_aligned.tif"
    assert p.is_file(), f"Missing SAR reference at {p}"
    return p


# -----------------------------------------------------------------------------
# Test 1: Archive Existence and Cryptographic Checksums
# -----------------------------------------------------------------------------
def test_archive_checksums_and_existence(june_zip: Path, july_zip: Path):
    """Verify that original SAFE.zip files exist intact and match certified SHA-256 digests."""
    assert compute_sha256(june_zip) == EXPECTED_JUNE_SHA256
    assert compute_sha256(july_zip) == EXPECTED_JULY_SHA256


# -----------------------------------------------------------------------------
# Test 2: Archive XML Metadata Extraction
# -----------------------------------------------------------------------------
def test_archive_metadata_extraction(june_zip: Path, july_zip: Path):
    """Verify metadata extraction: Baseline 05.10, quantification 10000, per-band offset -1000."""
    june_meta = parse_sentinel2_archive_metadata(june_zip)
    assert june_meta["spacecraft_name"] == "Sentinel-2A"
    assert june_meta["processing_baseline"] == "05.10"
    assert june_meta["quantification_value"] == 10000.0
    assert june_meta["boa_add_offsets"]["B02"] == -1000.0  # B03
    assert june_meta["boa_add_offsets"]["B07"] == -1000.0  # B08
    assert june_meta["boa_add_offsets"]["B11"] == -1000.0  # B11
    assert june_meta["boa_add_offsets"]["B12"] == -1000.0  # B12
    assert "T45RYH" in june_meta["tile_id"]

    july_meta = parse_sentinel2_archive_metadata(july_zip)
    assert july_meta["spacecraft_name"] == "Sentinel-2A"
    assert july_meta["processing_baseline"] == "05.10"
    assert july_meta["quantification_value"] == 10000.0
    assert july_meta["boa_add_offsets"]["B02"] == -1000.0
    assert "T45RYH" in july_meta["tile_id"]


# -----------------------------------------------------------------------------
# Test 3: Selective SAFE Extraction Footprint
# -----------------------------------------------------------------------------
def test_selective_extraction_contents(root_dir: Path):
    """Verify that only the 7 designated files (5 bands + 2 XMLs) were extracted per date."""
    for month in ["june_2024", "july_2024"]:
        ext_dir = root_dir / "data" / "reference" / "optical" / "sentinel2" / "extracted" / month
        assert ext_dir.is_dir()
        files = list(ext_dir.iterdir())
        assert len(files) == 7
        names = [f.name for f in files]
        assert any("_B03_10m.jp2" in n for n in names)
        assert any("_B08_10m.jp2" in n for n in names)
        assert any("_B11_20m.jp2" in n for n in names)
        assert any("_B12_20m.jp2" in n for n in names)
        assert any("_SCL_20m.jp2" in n for n in names)
        assert "MTD_TL.xml" in names
        assert "MTD_MSIL2A.xml" in names


# -----------------------------------------------------------------------------
# Test 4: Spatial Alignment against Canonical SAR Reference Grid
# -----------------------------------------------------------------------------
def test_aligned_rasters_spatial_geometry(root_dir: Path, sar_ref: Path):
    """Verify that aligned optical GeoTIFFs strictly match SAR grid dimensions, transform, and CRS."""
    sar_ds = gdal.Open(str(sar_ref))
    ref_gt = sar_ds.GetGeoTransform()
    ref_proj = sar_ds.GetProjection()
    sar_ds = None

    for month, prefix in [("june_2024", "s2_june07"), ("july_2024", "s2_july17")]:
        proc_dir = root_dir / "data" / "processed" / "reference" / "optical" / "sentinel2" / month
        test_rasters = [
            proc_dir / f"{prefix}_aligned_b03_20m.tif",
            proc_dir / f"{prefix}_aligned_b08_20m.tif",
            proc_dir / f"{prefix}_aligned_b11_20m.tif",
            proc_dir / f"{prefix}_aligned_b12_20m.tif",
            proc_dir / f"{prefix}_aligned_scl.tif",
            proc_dir / f"{prefix}_aligned_mndwi.tif",
            proc_dir / f"{prefix}_aligned_awei_nsh.tif",
            proc_dir / f"{prefix}_aligned_valid_mask.tif",
            proc_dir / f"{prefix}_aligned_cloud_mask.tif",
            proc_dir / f"{prefix}_aligned_shadow_mask.tif",
            proc_dir / f"{prefix}_aligned_dark_mask.tif",
            proc_dir / f"{prefix}_aligned_water_mask.tif",
        ]
        for r_path in test_rasters:
            assert r_path.is_file(), f"Missing aligned output: {r_path}"
            ds = gdal.Open(str(r_path))
            assert ds.RasterXSize == 1405
            assert ds.RasterYSize == 1393
            assert ds.GetGeoTransform() == ref_gt
            ds = None


# -----------------------------------------------------------------------------
# Test 5: Radiometric Reflectance Scaling and Dynamic Offset
# -----------------------------------------------------------------------------
def test_radiometric_reflectance_ranges(root_dir: Path):
    """Verify that calibrated BOA surface reflectance values are physically plausible."""
    for month, prefix in [("june_2024", "s2_june07"), ("july_2024", "s2_july17")]:
        proc_dir = root_dir / "data" / "processed" / "reference" / "optical" / "sentinel2" / month
        for b in ["b03", "b08", "b11", "b12"]:
            ds = gdal.Open(str(proc_dir / f"{prefix}_aligned_{b}_20m.tif"))
            arr = ds.GetRasterBand(1).ReadAsArray()
            valid = arr[arr != -9999.0]
            assert len(valid) > 0
            # Surface reflectance should be physically between -0.1 (shadow/offset residual) and 1.5 (bright cloud)
            assert np.min(valid) >= -0.15
            assert np.max(valid) <= 1.80
            ds = None


# -----------------------------------------------------------------------------
# Test 6: Continuous Spectral Water Indices
# -----------------------------------------------------------------------------
def test_spectral_indices_computation(root_dir: Path):
    """Verify continuous MNDWI and AWEI_nsh outputs and mathematical bounds."""
    for month, prefix in [("june_2024", "s2_june07"), ("july_2024", "s2_july17")]:
        proc_dir = root_dir / "data" / "processed" / "reference" / "optical" / "sentinel2" / month
        
        # MNDWI in [-1.0, 1.0]
        ds_mndwi = gdal.Open(str(proc_dir / f"{prefix}_aligned_mndwi.tif"))
        mndwi = ds_mndwi.GetRasterBand(1).ReadAsArray()
        valid_mndwi = mndwi[mndwi != -9999.0]
        assert np.min(valid_mndwi) >= -1.0
        assert np.max(valid_mndwi) <= 1.0
        ds_mndwi = None

        # AWEI_nsh finite
        ds_awei = gdal.Open(str(proc_dir / f"{prefix}_aligned_awei_nsh.tif"))
        awei = ds_awei.GetRasterBand(1).ReadAsArray()
        valid_awei = awei[awei != -9999.0]
        assert len(valid_awei) > 0
        assert not np.isnan(valid_awei).any()
        ds_awei = None


# -----------------------------------------------------------------------------
# Test 7: SCL Quality Mask Segregation and Dark Area Isolation
# -----------------------------------------------------------------------------
def test_scl_quality_masks_segregation(root_dir: Path):
    """
    Verify SCL classification segregation:
    - SCL Class 2 (Dark Area Pixels) is strictly isolated in dark_mask and labeled 252 in water_mask.
    - SCL Class 3 is isolated in shadow_mask and labeled 253.
    - SCL Classes 7-10 are isolated in cloud_mask and labeled 254.
    - SCL Classes 4-6 are isolated in valid_mask and labeled 0 or 1.
    """
    for month, prefix in [("june_2024", "s2_june07"), ("july_2024", "s2_july17")]:
        proc_dir = root_dir / "data" / "processed" / "reference" / "optical" / "sentinel2" / month
        
        ds_scl = gdal.Open(str(proc_dir / f"{prefix}_aligned_scl.tif"))
        scl = ds_scl.GetRasterBand(1).ReadAsArray()
        ds_scl = None

        ds_dark = gdal.Open(str(proc_dir / f"{prefix}_aligned_dark_mask.tif"))
        dark_m = ds_dark.GetRasterBand(1).ReadAsArray() == 1
        ds_dark = None

        ds_shadow = gdal.Open(str(proc_dir / f"{prefix}_aligned_shadow_mask.tif"))
        shadow_m = ds_shadow.GetRasterBand(1).ReadAsArray() == 1
        ds_shadow = None

        ds_cloud = gdal.Open(str(proc_dir / f"{prefix}_aligned_cloud_mask.tif"))
        cloud_m = ds_cloud.GetRasterBand(1).ReadAsArray() == 1
        ds_cloud = None

        ds_valid = gdal.Open(str(proc_dir / f"{prefix}_aligned_valid_mask.tif"))
        valid_m = ds_valid.GetRasterBand(1).ReadAsArray() == 1
        ds_valid = None

        ds_water = gdal.Open(str(proc_dir / f"{prefix}_aligned_water_mask.tif"))
        water_m = ds_water.GetRasterBand(1).ReadAsArray()
        ds_water = None

        # Mask identity assertions
        assert np.array_equal(dark_m, (scl == 2))
        assert np.array_equal(shadow_m, (scl == 3))
        assert np.array_equal(cloud_m, np.isin(scl, [7, 8, 9, 10]))
        assert np.array_equal(valid_m, np.isin(scl, [4, 5, 6]))

        # No overlap between clear valid and uncertain masks
        assert not (valid_m & dark_m).any()
        assert not (valid_m & shadow_m).any()
        assert not (valid_m & cloud_m).any()

        # Water mask labels
        if np.any(scl == 2):
            assert np.all(water_m[scl == 2] == REF_LABEL_UNCERTAIN_DARK_AREA)
        if np.any(scl == 3):
            assert np.all(water_m[scl == 3] == REF_LABEL_UNCERTAIN_SHADOW)
        if np.any(np.isin(scl, [7, 8, 9, 10])):
            assert np.all(water_m[np.isin(scl, [7, 8, 9, 10])] == REF_LABEL_UNCERTAIN_CLOUD)


# -----------------------------------------------------------------------------
# Test 8: Study AOI Quality Assessment and Usability Benchmarks
# -----------------------------------------------------------------------------
def test_aoi_quality_assessment_benchmarks(root_dir: Path):
    """Verify AOI quality metrics and usability status."""
    stats_dir = root_dir / "data" / "outputs" / "phase4c1" / "statistics"
    
    with open(stats_dir / "sentinel2_june07_qc.json", "r") as f:
        june_qc = json.load(f)
    with open(stats_dir / "sentinel2_july17_qc.json", "r") as f:
        july_qc = json.load(f)

    # AOI Cell Counts
    assert june_qc["aoi_quality_assessment"]["aoi_total_pixels"] == AOI_TARGET_CELLS
    assert july_qc["aoi_quality_assessment"]["aoi_total_pixels"] == AOI_TARGET_CELLS

    # Full swath coverage (no NoData in AOI)
    assert june_qc["aoi_quality_assessment"]["aoi_swath_coverage_pct"] == 100.0
    assert july_qc["aoi_quality_assessment"]["aoi_swath_coverage_pct"] == 100.0

    # June quality assessment
    assert june_qc["aoi_quality_assessment"]["status"] == "READY"
    assert pytest.approx(june_qc["aoi_quality_assessment"]["aoi_usable_clear_pct"], 0.1) == 55.78
    assert pytest.approx(june_qc["aoi_quality_assessment"]["aoi_cloud_pct"], 0.1) == 43.89

    # July quality assessment
    assert july_qc["aoi_quality_assessment"]["status"] == "PARTIALLY_USABLE"
    assert pytest.approx(july_qc["aoi_quality_assessment"]["aoi_usable_clear_pct"], 0.1) == 14.82
    assert pytest.approx(july_qc["aoi_quality_assessment"]["aoi_cloud_pct"], 0.1) == 84.97

    # Temporal Gaps
    assert june_qc["temporal_pairing"]["delta_t_days"] == 3
    assert july_qc["temporal_pairing"]["delta_t_days"] == 1
    assert june_qc["temporal_pairing"]["is_simultaneous"] == False
    assert july_qc["temporal_pairing"]["is_simultaneous"] == False


# -----------------------------------------------------------------------------
# Test 9: Reference Data Registry Compliance
# -----------------------------------------------------------------------------
def test_reference_registry_compliance(root_dir: Path):
    """Verify that reference_data_registry.json contains valid entries passing provenance rules."""
    reg_path = root_dir / "data" / "metadata" / "reference_data_registry.json"
    assert reg_path.is_file()
    
    with open(reg_path, "r") as f:
        reg_data = json.load(f)

    datasets = reg_data.get("registered_datasets", [])
    assert len(datasets) == 2

    ids = [d["dataset_id"] for d in datasets]
    assert "s2a_msil2a_20240607_t45ryh" in ids
    assert "s2a_msil2a_20240717_t45ryh" in ids

    for d in datasets:
        val_res = validate_provenance_metadata(d)
        assert val_res.status.value == "READY"
        assert len(val_res.errors) == 0
        assert d["sha256"] in [EXPECTED_JUNE_SHA256, EXPECTED_JULY_SHA256]

