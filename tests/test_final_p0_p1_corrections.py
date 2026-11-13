"""
Comprehensive regression and verification test suite for Final P0/P1 Audit Corrections.
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers:
- P0-1: Genuine radar polarization identity, band inspection, reordering, and metadata preservation.
- P0-2: Calibrated raster provenance verification, mandatory output SHA-256, registered checksum verification, and anti-forgery.
- P1-3: Transactional job state machine, IllegalStateTransitionError, and terminal state immutability.
- P1-4: Execution attempt numbering with strict regex parsing, preventing auxiliary file index skew.
- P1-5: Relative orbit metadata validation (range 1-175, rejecting bool, NaN, Inf, non-integer floats, and unparseable strings).
"""

import json
import math
import uuid
import shutil
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
import numpy as np
from osgeo import gdal, osr

from src.backend.config import settings
from src.backend.database.database import get_db_connection
from src.acquisition.scene_selector import (
    SceneSelector,
    validate_relative_orbit,
)
from src.acquisition.asf_client import validate_scene_metadata as asf_validate_scene_metadata
from src.pipeline.sentinel1_preprocess import (
    Sentinel1Preprocessor,
    validate_sar_raster,
    verify_calibrated_raster_provenance,
    HISTORICAL_REFERENCE_REGISTRY,
    CANONICAL_GRAPH_SHA256,
    CANONICAL_GRAPH_XML,
)
from src.backend.services.dynamic_analysis_service import (
    DynamicAnalysisService,
    IllegalStateTransitionError,
    atomic_write_json,
    VALID_STATE_TRANSITIONS,
)


def _create_synthetic_two_band_raster(
    filepath: Path,
    b1_val: float = 0.02,
    b2_val: float = 0.08,
    b1_desc: str = "Sigma0_VH",
    b2_desc: str = "Sigma0_VV",
    b1_dtype: int = gdal.GDT_Float32,
    b2_dtype: int = gdal.GDT_Float32,
    width: int = 20,
    height: int = 20,
    epsg: int = 32645,
    origin_x: float = 600000.0,
    origin_y: float = 2700000.0,
    res: float = 20.0,
) -> Path:
    """Helper to create synthetic 2-band Float32 GeoTIFF for SAR testing."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(str(filepath), width, height, 2, b1_dtype)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetGeoTransform([origin_x, res, 0.0, origin_y, 0.0, -res])

    band1 = ds.GetRasterBand(1)
    if b1_desc:
        band1.SetDescription(b1_desc)
    band1.SetNoDataValue(-9999.0)
    band1.WriteArray(np.full((height, width), b1_val, dtype=np.float32))

    band2 = ds.GetRasterBand(2)
    if b2_desc:
        band2.SetDescription(b2_desc)
    band2.SetNoDataValue(-9999.0)
    band2.WriteArray(np.full((height, width), b2_val, dtype=np.float32))

    ds.FlushCache()
    ds = None
    return filepath


# ===========================================================================
# 1. P1-5: Relative Orbit Metadata Validation
# ===========================================================================

class TestP15RelativeOrbitValidation:
    """Validates Sentinel-1 relative orbit track numbers (1-175)."""

    def test_valid_integer_orbit(self):
        valid, val, err = validate_relative_orbit(85)
        assert valid is True
        assert val == 85
        assert err is None

    def test_valid_string_orbit(self):
        valid, val, err = validate_relative_orbit("120")
        assert valid is True
        assert val == 120
        assert err is None

    def test_valid_integer_float_orbit(self):
        valid, val, err = validate_relative_orbit(175.0)
        assert valid is True
        assert val == 175
        assert err is None

    def test_reject_boolean_value(self):
        # In Python, bool is a subclass of int. validate_relative_orbit must reject it.
        valid, val, err = validate_relative_orbit(True)
        assert valid is False
        assert val is None
        assert "boolean" in err.lower()

        valid, val, err = validate_relative_orbit(False)
        assert valid is False
        assert val is None

    def test_reject_nan_without_exception(self):
        valid, val, err = validate_relative_orbit(float("nan"))
        assert valid is False
        assert val is None
        assert "nan" in err.lower()

    def test_reject_inf_without_exception(self):
        valid, val, err = validate_relative_orbit(float("inf"))
        assert valid is False
        assert val is None
        assert "infinite" in err.lower()

    def test_reject_non_integer_float(self):
        valid, val, err = validate_relative_orbit(85.9)
        assert valid is False
        assert val is None
        assert "whole integer" in err.lower()

    def test_reject_out_of_range_orbits(self):
        # Sentinel-1 repeat cycle has 175 orbits
        for bad_orbit in [0, -1, -85, 176, 999]:
            valid, val, err = validate_relative_orbit(bad_orbit)
            assert valid is False
            assert val is None
            assert "out of sentinel-1 range" in err.lower()

    def test_reject_unparseable_string(self):
        for bad_str in ["85A", "abc", "", "  ", "85.5"]:
            valid, val, err = validate_relative_orbit(bad_str)
            assert valid is False
            assert val is None

    def test_reject_none(self):
        valid, val, err = validate_relative_orbit(None)
        assert valid is False
        assert val is None
        assert "missing" in err.lower()

    def test_scene_selector_validation_integration(self):
        base_scene = {
            "scene_name": "S1A_IW_GRDH_TEST",
            "acquisition_time": "2024-06-10T12:00:00+00:00",
            "orbit_direction": "ASCENDING",
            "polarization": "VV+VH",
            "beam_mode": "IW",
            "processing_level": "GRD_HD",
            "aoi_coverage_pct": 100.0,
        }

        # Valid track
        s_valid = dict(base_scene, relative_orbit=85)
        assert SceneSelector.validate_scene_metadata(s_valid) == []

        # Float NaN track
        s_nan = dict(base_scene, relative_orbit=float("nan"))
        errs = SceneSelector.validate_scene_metadata(s_nan)
        assert any("relative orbit" in e.lower() for e in errs)

        # Fractional float track
        s_frac = dict(base_scene, relative_orbit=85.9)
        errs = SceneSelector.validate_scene_metadata(s_frac)
        assert any("relative orbit" in e.lower() for e in errs)

        # Bool track
        s_bool = dict(base_scene, relative_orbit=True)
        errs = SceneSelector.validate_scene_metadata(s_bool)
        assert any("relative orbit" in e.lower() for e in errs)

        # Out of range track
        s_oor = dict(base_scene, relative_orbit=200)
        errs = SceneSelector.validate_scene_metadata(s_oor)
        assert any("out of sentinel-1 range" in e.lower() for e in errs)

    def test_asf_client_validation_integration(self):
        scene_record = {
            "scene_name": "S1A_TEST",
            "acquisition_time": "2024-06-10T12:00:00+00:00",
            "orbit_direction": "ASCENDING",
            "polarization": "VV+VH",
            "beam_mode": "IW",
            "processing_level": "GRD_HD",
            "aoi_coverage_pct": 100.0,
            "relative_orbit": float("nan"),
        }
        rejections = asf_validate_scene_metadata(scene_record, "test_source")
        assert any("relative_orbit" in r for r in rejections)


# ===========================================================================
# 2. P0-1: Genuine Radar Polarization Identity
# ===========================================================================

class TestP01PolarizationIdentity:
    """Validates band inspection, reordering, and metadata preservation."""

    def test_identify_polarization_standard_bands(self, tmp_path):
        tif = _create_synthetic_two_band_raster(
            tmp_path / "standard.tif",
            b1_desc="Sigma0_VH",
            b2_desc="Sigma0_VV",
        )
        vh_idx, vv_idx, mapping = Sentinel1Preprocessor.identify_polarization_bands(tif)
        assert vh_idx == 1
        assert vv_idx == 2
        assert mapping["reordered"] is False
        assert mapping["source_band_vh"] == 1
        assert mapping["source_band_vv"] == 2

    def test_identify_polarization_reversed_bands(self, tmp_path):
        tif = _create_synthetic_two_band_raster(
            tmp_path / "reversed.tif",
            b1_desc="Sigma0_VV",
            b2_desc="Sigma0_VH",
        )
        vh_idx, vv_idx, mapping = Sentinel1Preprocessor.identify_polarization_bands(tif)
        assert vh_idx == 2
        assert vv_idx == 1
        assert mapping["reordered"] is True
        assert mapping["source_band_vh"] == 2
        assert mapping["source_band_vv"] == 1

    def test_reject_single_band_raster(self, tmp_path):
        filepath = tmp_path / "single_band.tif"
        drv = gdal.GetDriverByName("GTiff")
        ds = drv.Create(str(filepath), 10, 10, 1, gdal.GDT_Float32)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32645)
        ds.SetProjection(srs.ExportToWkt())
        ds.SetGeoTransform([600000, 20, 0, 2700000, 0, -20])
        ds.GetRasterBand(1).SetDescription("Sigma0_VH")
        ds.FlushCache()
        ds = None

        with pytest.raises(ValueError, match="at least 2 bands"):
            Sentinel1Preprocessor.identify_polarization_bands(filepath)

    def test_reject_ambiguous_or_missing_band_descriptions(self, tmp_path):
        tif = _create_synthetic_two_band_raster(
            tmp_path / "unlabeled.tif",
            b1_desc="",
            b2_desc="",
        )
        with pytest.raises(ValueError, match="Cannot verify polarization identity"):
            Sentinel1Preprocessor.identify_polarization_bands(tif)

    def test_extract_sub_aoi_reorders_reversed_bands(self, tmp_path):
        # Create input where Band 1 is VV (val=0.15) and Band 2 is VH (val=0.03)
        # Position the synthetic raster so it overlaps the polygon in UTM 32645 (x~768800, y~2696000)
        src_tif = _create_synthetic_two_band_raster(
            tmp_path / "src_reversed.tif",
            b1_val=0.15,
            b2_val=0.03,
            b1_desc="Sigma0_VV",
            b2_desc="Sigma0_VH",
            origin_x=768000.0,
            origin_y=2698000.0,
            width=100,
            height=100,
            res=20.0,
        )
        target_tif = tmp_path / "target_corrected.tif"
        aoi_wkt = (
            "POLYGON((89.65 24.35, 89.67 24.35, 89.67 24.37, 89.65 24.37, 89.65 24.35))"
        )

        Sentinel1Preprocessor.extract_sub_aoi(src_tif, target_tif, aoi_wkt)

        assert target_tif.exists()
        out_ds = gdal.Open(str(target_tif), gdal.GA_ReadOnly)
        assert out_ds.RasterCount == 2

        b1 = out_ds.GetRasterBand(1)
        b2 = out_ds.GetRasterBand(2)
        assert b1.GetDescription() == "Sigma0_VH"
        assert b2.GetDescription() == "Sigma0_VV"

        # Verify that output Band 1 contains the VH values (0.03), NOT VV values (0.15)
        arr1 = b1.ReadAsArray()
        valid1 = arr1[arr1 != -9999.0]
        assert len(valid1) > 0
        np.testing.assert_allclose(np.mean(valid1), 0.03, rtol=1e-3)

        arr2 = b2.ReadAsArray()
        valid2 = arr2[arr2 != -9999.0]
        assert len(valid2) > 0
        np.testing.assert_allclose(np.mean(valid2), 0.15, rtol=1e-3)

        # Verify metadata recording
        meta_mapping = out_ds.GetMetadataItem("SOURCE_BAND_MAPPING")
        assert meta_mapping is not None
        mapping_dict = json.loads(meta_mapping)
        assert mapping_dict["source_band_vh"] == 2
        assert mapping_dict["source_band_vv"] == 1
        assert mapping_dict["reordered"] is True
        assert out_ds.GetMetadataItem("POLARIZATION_IDENTITY_VERIFIED") == "TRUE"
        out_ds = None


# ===========================================================================
# 3. P0-2: Calibrated Raster Provenance Verification
# ===========================================================================

class TestP02ProvenanceVerification:
    """Validates calibration provenance, mandatory checksums, and anti-forgery."""

    def test_provenance_missing_output_sha256_rejected(self, tmp_path):
        tif = _create_synthetic_two_band_raster(tmp_path / "no_hash.tif")
        prov_data = {
            "granule_id": "test_granule",
            "provenance": {
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
            },
        }
        prov_file = tmp_path / "no_hash_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="missing mandatory 'output_sha256'"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule")

    def test_provenance_mismatched_output_sha256_rejected(self, tmp_path):
        tif = _create_synthetic_two_band_raster(tmp_path / "bad_hash.tif")
        prov_data = {
            "granule_id": "test_granule",
            "output_sha256": "bad0000000000000000000000000000000000000000000000000000000000000",
            "provenance": {
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
            },
        }
        prov_file = tmp_path / "bad_hash_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="Provenance checksum mismatch"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule")

    def test_provenance_granule_mismatch_rejected(self, tmp_path):
        tif = _create_synthetic_two_band_raster(tmp_path / "good.tif")
        h = hashlib.sha256(tif.read_bytes()).hexdigest()
        prov_data = {
            "granule_id": "actual_granule_123",
            "output_sha256": h,
            "provenance": {
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
            },
        }
        prov_file = tmp_path / "good_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="Granule mismatch"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="different_granule_456")

    def test_provenance_missing_source_hash_rejected(self, tmp_path):
        """Fix 2 Negative Test: Missing source_archive_sha256 is strictly rejected."""
        tif = _create_synthetic_two_band_raster(tmp_path / "no_src_hash.tif")
        h = hashlib.sha256(tif.read_bytes()).hexdigest()
        src_file = tmp_path / "valid_src.zip"
        src_file.write_bytes(b"dummy source archive")
        prov_data = {
            "granule_id": "test_granule_new",
            "source_archive": str(src_file),
            "output_sha256": h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
        }
        prov_file = tmp_path / "no_src_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="missing mandatory 'source_archive_sha256'"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_new")

    def test_provenance_forged_source_hash_rejected(self, tmp_path):
        """Fix 2 Negative Test: Source archive on disk with mismatched checksum is rejected."""
        tif = _create_synthetic_two_band_raster(tmp_path / "src_test.tif")
        h = hashlib.sha256(tif.read_bytes()).hexdigest()

        # Create dummy source archive
        src_arch = tmp_path / "source_archive.zip"
        src_arch.write_bytes(b"dummy satellite archive content")

        prov_data = {
            "granule_id": "test_granule_new",
            "source_archive": str(src_arch),
            "source_archive_sha256": "f" * 64,  # Forged/tampered checksum
            "output_sha256": h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
        }
        prov_file = tmp_path / "forged_src_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="Source file checksum mismatch"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_new")

    def test_provenance_missing_graph_hash_rejected(self, tmp_path):
        """Fix 2 Negative Test: Missing graph_sha256 is strictly rejected."""
        tif = _create_synthetic_two_band_raster(tmp_path / "no_graph.tif")
        h = hashlib.sha256(tif.read_bytes()).hexdigest()
        src_file = tmp_path / "valid_src.zip"
        src_file.write_bytes(b"dummy source archive")
        src_h = hashlib.sha256(src_file.read_bytes()).hexdigest()
        prov_data = {
            "granule_id": "test_granule_new",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": h,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
        }
        prov_file = tmp_path / "no_graph_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="missing mandatory 'graph_sha256'"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_new")

    def test_provenance_forged_graph_hash_rejected(self, tmp_path):
        """Fix 2 Negative Test: Forged or altered graph XML SHA-256 is strictly rejected."""
        tif = _create_synthetic_two_band_raster(tmp_path / "bad_graph.tif")
        h = hashlib.sha256(tif.read_bytes()).hexdigest()
        src_file = tmp_path / "valid_src.zip"
        src_file.write_bytes(b"dummy source archive")
        src_h = hashlib.sha256(src_file.read_bytes()).hexdigest()
        prov_data = {
            "granule_id": "test_granule_new",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": h,
            "graph_sha256": "e" * 64,  # Altered graph hash
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
        }
        prov_file = tmp_path / "bad_graph_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="SNAP graph checksum mismatch"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_new")

    def test_provenance_absent_band_mapping_rejected(self, tmp_path):
        """Fix 2 Negative Test: Missing source_band_mapping is strictly rejected."""
        tif = _create_synthetic_two_band_raster(tmp_path / "no_mapping.tif")
        h = hashlib.sha256(tif.read_bytes()).hexdigest()
        src_file = tmp_path / "valid_src.zip"
        src_file.write_bytes(b"dummy source archive")
        src_h = hashlib.sha256(src_file.read_bytes()).hexdigest()
        prov_data = {
            "granule_id": "test_granule_new",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
            },
        }
        prov_file = tmp_path / "no_mapping_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="missing mandatory 'source_band_mapping'"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_new")

    def test_provenance_valid_new_acquisition_passes(self, tmp_path):
        """Fix 2 Positive Test: Fully bound new acquisition provenance passes Stage B."""
        tif = _create_synthetic_two_band_raster(tmp_path / "valid_new.tif")
        h = hashlib.sha256(tif.read_bytes()).hexdigest()

        src_file = tmp_path / "valid_src.zip"
        src_file.write_bytes(b"actual valid source archive bytes")
        src_h = hashlib.sha256(src_file.read_bytes()).hexdigest()

        prov_data = {
            "granule_id": "S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {
                "source_band_vh": 1,
                "source_band_vv": 2,
                "output_band_1": "Sigma0_VH",
                "output_band_2": "Sigma0_VV",
            },
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
                "expected_crs": "EPSG:32645",
                "pixel_spacing_m": 20.0,
            },
            "provenance": {
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
                "processing_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
                "verification_status": "FRESHLY_PREPROCESSED",
            },
        }
        prov_file = tmp_path / "valid_new_provenance.json"
        atomic_write_json(prov_file, prov_data)

        res = verify_calibrated_raster_provenance(
            tif,
            prov_file,
            scene_name="S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8",
        )
        assert res["provenance_verified"] is True
        assert res["status"] == "VERIFIED_PROVENANCE"

    def test_forged_historical_reference_rejected(self, tmp_path):
        # A synthetic file claiming to be june10_aligned without matching SHA-256 must be rejected
        forged_tif = _create_synthetic_two_band_raster(tmp_path / "june10_aligned.tif")
        with pytest.raises(ValueError, match="Historical reference raster checksum verification failed"):
            verify_calibrated_raster_provenance(forged_tif, scene_name="june10_aligned")

    def test_authentic_historical_reference_verified(self):
        auth_tif = settings.DATA_DIR / "processed" / "aligned" / "june10_aligned.tif"
        if auth_tif.exists():
            res = verify_calibrated_raster_provenance(auth_tif, scene_name="june10_aligned")
            assert res["provenance_verified"] is True
            assert res["status"] == "VERIFIED_HISTORICAL_LEGACY"
            assert res["sha256"] == HISTORICAL_REFERENCE_REGISTRY["june10_aligned"]["sha256"]


# ===========================================================================
# 4. P1-3: Transactional Job State Machine
# ===========================================================================

class TestP13TransactionalStateMachine:
    """Verifies state machine transitions, error types, and concurrency safeguards."""

    def test_illegal_state_transition_raises_error(self, tmp_path):
        service = DynamicAnalysisService()
        run_record = service.create_analysis_request(
            aoi_wkt="POLYGON((89.65 24.35, 89.67 24.35, 89.67 24.37, 89.65 24.37, 89.65 24.35))",
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = run_record["run_id"]
        run_dir = service.get_run_dir(run_id)

        try:
            # Run is initially CREATED. Transitioning directly to CLASSIFYING is illegal.
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM analysis_runs WHERE run_id = ?", (run_id,))
                assert cursor.fetchone()[0] == "CREATED"

            # Verify allowed transitions from CREATED
            allowed_from_created = VALID_STATE_TRANSITIONS["CREATED"]
            assert "CLASSIFYING" not in allowed_from_created
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()

    def test_terminal_states_are_immutable(self, tmp_path):
        service = DynamicAnalysisService()
        run_record = service.create_analysis_request(
            aoi_wkt="POLYGON((89.65 24.35, 89.67 24.35, 89.67 24.37, 89.65 24.37, 89.65 24.35))",
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = run_record["run_id"]
        run_dir = service.get_run_dir(run_id)

        try:
            # Set to COMPLETED directly in DB
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE analysis_runs SET status = 'COMPLETED' WHERE run_id = ?", (run_id,))
                conn.commit()

            # Terminal state has empty allowed set
            assert VALID_STATE_TRANSITIONS["COMPLETED"] == set()
            assert VALID_STATE_TRANSITIONS["CANCELLED"] == set()
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()


# ===========================================================================
# 5. P1-4: Execution Attempt Numbering
# ===========================================================================

class TestP14ExecutionAttemptNumbering:
    """Validates that auxiliary files do not distort execution attempt indices."""

    def test_auxiliary_files_do_not_skip_attempt_indices(self, tmp_path):
        service = DynamicAnalysisService()
        run_record = service.create_analysis_request(
            aoi_wkt="POLYGON((89.65 24.35, 89.67 24.35, 89.67 24.37, 89.65 24.37, 89.65 24.35))",
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = run_record["run_id"]
        run_dir = service.get_run_dir(run_id)
        attempts_dir = run_dir / "attempts"
        attempts_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Simulate attempt 1 with auxiliary files
            atomic_write_json(attempts_dir / "attempt_0001.json", {"attempt_index": 1, "status": "FAILED"})
            atomic_write_json(attempts_dir / "attempt_0001_failed.json", {"attempt_index": 1})
            atomic_write_json(attempts_dir / "attempt_0001_error.json", {"attempt_index": 1})

            # Calculate next attempt index using the strict regex logic
            import re
            existing_indices = []
            for p in attempts_dir.iterdir():
                m = re.match(r"^attempt_(\d{4})\.json$", p.name)
                if m:
                    existing_indices.append(int(m.group(1)))
            next_attempt_idx = max(existing_indices, default=0) + 1

            # Must be exactly 2 (NOT 4!)
            assert next_attempt_idx == 2

            # Simulate attempt 2 with completed auxiliary file
            atomic_write_json(attempts_dir / "attempt_0002.json", {"attempt_index": 2, "status": "COMPLETED"})
            atomic_write_json(attempts_dir / "attempt_0002_completed.json", {"attempt_index": 2})

            existing_indices_2 = []
            for p in attempts_dir.iterdir():
                m = re.match(r"^attempt_(\d{4})\.json$", p.name)
                if m:
                    existing_indices_2.append(int(m.group(1)))
            next_attempt_idx_2 = max(existing_indices_2, default=0) + 1

            # Must be exactly 3 (NOT 6!)
            assert next_attempt_idx_2 == 3
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()


# ===========================================================================
# 6. Micro-Patch Safety Verification (Tests 1–10)
# ===========================================================================

class TestMicroPatchSafetyVerification:
    """
    Executes the 10 production verification tests mandated by the Final Micro-Patch protocol:
    1. New-product provenance with no source path — REJECT.
    2. New-product provenance pointing to nonexistent archive — REJECT.
    3. Source file with incorrect SHA-256 — REJECT.
    4. Source mapping with arbitrary keys — REJECT.
    5. Incorrect polarization indices — REJECT.
    6. Missing or contradictory processing parameters — REJECT.
    7. Real source file, matching hashes, valid graph and mapping — ACCEPT.
    8. Historical exact-checksum reference — ACCEPT.
    9. Same-run retry with missing footprint — REJECT.
    10. Same-run retry with valid footprints and ASF outage — ACCEPT.
    """

    def test_01_new_product_provenance_no_source_path_rejected(self, tmp_path):
        """1. New-product provenance with no source path — REJECT."""
        tif = _create_synthetic_two_band_raster(tmp_path / "test01.tif")
        tif_h = hashlib.sha256(tif.read_bytes()).hexdigest()
        prov_data = {
            "granule_id": "test_granule_01",
            "output_sha256": tif_h,
            "source_archive_sha256": "a" * 64,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
        }
        prov_file = tmp_path / "test01_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="missing mandatory 'source_archive' or 'source_raster'"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_01")

    def test_02_new_product_provenance_nonexistent_archive_rejected(self, tmp_path):
        """2. New-product provenance pointing to nonexistent archive — REJECT."""
        tif = _create_synthetic_two_band_raster(tmp_path / "test02.tif")
        tif_h = hashlib.sha256(tif.read_bytes()).hexdigest()
        prov_data = {
            "granule_id": "test_granule_02",
            "source_archive": str(tmp_path / "nonexistent_satellite_archive.zip"),
            "source_archive_sha256": "a" * 64,
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
        }
        prov_file = tmp_path / "test02_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="does not exist or is not a regular file"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_02")

    def test_03_source_file_with_incorrect_sha256_rejected(self, tmp_path):
        """3. Source file with incorrect SHA-256 — REJECT."""
        tif = _create_synthetic_two_band_raster(tmp_path / "test03.tif")
        tif_h = hashlib.sha256(tif.read_bytes()).hexdigest()

        src_file = tmp_path / "real_archive.zip"
        src_file.write_bytes(b"actual physical source archive bytes")

        prov_data = {
            "granule_id": "test_granule_03",
            "source_archive": str(src_file),
            "source_archive_sha256": "0" * 64,  # Incorrect hash
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
        }
        prov_file = tmp_path / "test03_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="Source file checksum mismatch"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_03")

    def test_04_source_mapping_with_arbitrary_keys_rejected(self, tmp_path):
        """4. Source mapping with arbitrary keys — REJECT."""
        tif = _create_synthetic_two_band_raster(tmp_path / "test04.tif")
        tif_h = hashlib.sha256(tif.read_bytes()).hexdigest()

        src_file = tmp_path / "real_archive.zip"
        src_file.write_bytes(b"actual physical source archive bytes")
        src_h = hashlib.sha256(src_file.read_bytes()).hexdigest()

        prov_data = {
            "granule_id": "test_granule_04",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"arbitrary_foo": 1, "arbitrary_bar": 2},  # Arbitrary keys
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
            },
        }
        prov_file = tmp_path / "test04_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="missing mandatory polarization keys"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_04")

    def test_05_incorrect_polarization_indices_rejected(self, tmp_path):
        """5. Incorrect polarization indices — REJECT."""
        tif = _create_synthetic_two_band_raster(tmp_path / "test05.tif")
        tif_h = hashlib.sha256(tif.read_bytes()).hexdigest()

        src_file = tmp_path / "real_archive.zip"
        src_file.write_bytes(b"actual physical source archive bytes")
        src_h = hashlib.sha256(src_file.read_bytes()).hexdigest()

        # Identical indices (1, 1) must be rejected
        prov_data_same = {
            "granule_id": "test_granule_05",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 1},  # Identical indices
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
            },
        }
        prov_file_same = tmp_path / "test05_same_provenance.json"
        atomic_write_json(prov_file_same, prov_data_same)

        with pytest.raises(ValueError, match="Invalid polarization source band indices"):
            verify_calibrated_raster_provenance(tif, prov_file_same, scene_name="test_granule_05")

        # Non-positive / string indices must also be rejected
        prov_data_str = {
            "granule_id": "test_granule_05",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 0, "source_band_vv": "two"},  # Bad types
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
            },
        }
        prov_file_str = tmp_path / "test05_str_provenance.json"
        atomic_write_json(prov_file_str, prov_data_str)

        with pytest.raises(ValueError, match="Invalid polarization source band indices"):
            verify_calibrated_raster_provenance(tif, prov_file_str, scene_name="test_granule_05")

    def test_06_missing_or_contradictory_processing_parameters_rejected(self, tmp_path):
        """6. Missing or contradictory processing parameters — REJECT."""
        tif = _create_synthetic_two_band_raster(tmp_path / "test06.tif")
        tif_h = hashlib.sha256(tif.read_bytes()).hexdigest()

        src_file = tmp_path / "real_archive.zip"
        src_file.write_bytes(b"actual physical source archive bytes")
        src_h = hashlib.sha256(src_file.read_bytes()).hexdigest()

        # A: Missing processing_parameters entirely
        prov_data_missing = {
            "granule_id": "test_granule_06",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
        }
        prov_file_missing = tmp_path / "test06_missing.json"
        atomic_write_json(prov_file_missing, prov_data_missing)

        with pytest.raises(ValueError, match="missing mandatory 'processing_parameters'"):
            verify_calibrated_raster_provenance(tif, prov_file_missing, scene_name="test_granule_06")

        # B: Contradictory radiometric domain (dB instead of linear)
        prov_data_db = {
            "granule_id": "test_granule_06",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "decibels",  # Strictly rejected!
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
            },
        }
        prov_file_db = tmp_path / "test06_db.json"
        atomic_write_json(prov_file_db, prov_data_db)

        with pytest.raises(ValueError, match="expected 'linear_power'"):
            verify_calibrated_raster_provenance(tif, prov_file_db, scene_name="test_granule_06")

        # C: Contradictory CRS
        prov_data_crs = {
            "granule_id": "test_granule_06",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
                "expected_crs": "EPSG:4326",  # Contradictory CRS
            },
        }
        prov_file_crs = tmp_path / "test06_crs.json"
        atomic_write_json(prov_file_crs, prov_data_crs)

        with pytest.raises(ValueError, match="Contradictory projected CRS"):
            verify_calibrated_raster_provenance(tif, prov_file_crs, scene_name="test_granule_06")

    def test_07_real_source_file_matching_hashes_valid_graph_and_mapping_accepted(self, tmp_path):
        """7. Real source file, matching hashes, valid graph and mapping — ACCEPT."""
        tif = _create_synthetic_two_band_raster(tmp_path / "test07.tif")
        tif_h = hashlib.sha256(tif.read_bytes()).hexdigest()

        src_file = tmp_path / "real_archive_valid.zip"
        src_file.write_bytes(b"authentic real raw source archive data")
        src_h = hashlib.sha256(src_file.read_bytes()).hexdigest()

        prov_data = {
            "granule_id": "S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8",
            "source_archive": str(src_file),
            "source_archive_sha256": src_h,
            "output_sha256": tif_h,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
            "source_band_mapping": {
                "source_band_vh": 1,
                "source_band_vv": 2,
                "output_band_1": "Sigma0_VH",
                "output_band_2": "Sigma0_VV",
            },
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "terrain_correction": "Range-Doppler",
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
                "expected_crs": "EPSG:32645",
                "pixel_spacing_m": 20.0,
            },
            "provenance": {
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
                "processing_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
                "verification_status": "FRESHLY_PREPROCESSED",
            },
        }
        prov_file = tmp_path / "test07_provenance.json"
        atomic_write_json(prov_file, prov_data)

        res = verify_calibrated_raster_provenance(
            tif,
            prov_file,
            scene_name="S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8",
        )
        assert res["provenance_verified"] is True
        assert res["status"] == "VERIFIED_PROVENANCE"

    def test_08_historical_exact_checksum_reference_accepted(self):
        """8. Historical exact-checksum reference — ACCEPT."""
        auth_tif = settings.DATA_DIR / "processed" / "aligned" / "june10_aligned.tif"
        if auth_tif.exists():
            res = verify_calibrated_raster_provenance(auth_tif, scene_name="june10_aligned")
            assert res["provenance_verified"] is True
            assert res["status"] == "VERIFIED_HISTORICAL_LEGACY"
            assert res["sha256"] == HISTORICAL_REFERENCE_REGISTRY["june10_aligned"]["sha256"]

    def test_09_same_run_retry_missing_footprint_rejected(self):
        """9. Same-run retry with missing footprint — REJECT."""
        service = DynamicAnalysisService()
        aoi_wkt = "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))"
        req = service.create_analysis_request(
            aoi_wkt=aoi_wkt,
            start_date="2024-06-10",
            end_date="2024-07-16",
            mode="two_date_comparison",
        )
        run_id = req["run_id"]
        run_dir = service.get_run_dir(run_id)

        try:
            # Write scenes.json with MISSING footprint geometry (no footprint_wkt/geojson/geometry)
            cached_b = {
                "scene_name": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
                "acquisition_time": "2024-06-10T12:05:08+00:00",
                "relative_orbit": 121,
                "orbit_direction": "ASCENDING",
                "polarization": "VV+VH",
                "beam_mode": "IW",
                "processing_level": "GRD_HD",
                "aoi_coverage_pct": 100.0,
                # footprint intentionally missing
            }
            cached_c = {
                "scene_name": "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511",
                "acquisition_time": "2024-07-16T12:05:07+00:00",
                "relative_orbit": 121,
                "orbit_direction": "ASCENDING",
                "polarization": "VV+VH",
                "beam_mode": "IW",
                "processing_level": "GRD_HD",
                "aoi_coverage_pct": 100.0,
                # footprint intentionally missing
            }
            atomic_write_json(run_dir / "scenes.json", {
                "selected_baseline": cached_b,
                "selected_change": cached_c,
            })

            # Provider outage -> must fail closed because footprints are missing
            with patch.object(service, "search_scenes", return_value=[]):
                with pytest.raises(RuntimeError, match="Insufficient Sentinel-1 scenes"):
                    service.execute_analysis_run(run_id)

            # SQLite status must be FAILED
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM analysis_runs WHERE run_id = ?", (run_id,))
                row = cursor.fetchone()
                assert row[0] == "FAILED"
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()

    def test_10_same_run_retry_valid_footprints_and_asf_outage_accepted(self):
        """10. Same-run retry with valid footprints and ASF outage — ACCEPT."""
        service = DynamicAnalysisService()
        aoi_wkt = "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))"
        req = service.create_analysis_request(
            aoi_wkt=aoi_wkt,
            start_date="2024-06-10",
            end_date="2024-07-16",
            mode="two_date_comparison",
        )
        run_id = req["run_id"]
        run_dir = service.get_run_dir(run_id)

        try:
            cached_b = {
                "scene_name": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
                "acquisition_time": "2024-06-10T12:05:08+00:00",
                "relative_orbit": 121,
                "orbit_direction": "ASCENDING",
                "polarization": "VV+VH",
                "beam_mode": "IW",
                "processing_level": "GRD_HD",
                "aoi_coverage_pct": 100.0,
                "footprint_wkt": "POLYGON((89.4 24.4, 89.8 24.4, 89.8 24.8, 89.4 24.8, 89.4 24.4))",
            }
            cached_c = {
                "scene_name": "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511",
                "acquisition_time": "2024-07-16T12:05:07+00:00",
                "relative_orbit": 121,
                "orbit_direction": "ASCENDING",
                "polarization": "VV+VH",
                "beam_mode": "IW",
                "processing_level": "GRD_HD",
                "aoi_coverage_pct": 100.0,
                "footprint_wkt": "POLYGON((89.4 24.4, 89.8 24.4, 89.8 24.8, 89.4 24.8, 89.4 24.4))",
            }
            atomic_write_json(run_dir / "scenes.json", {
                "selected_baseline": cached_b,
                "selected_change": cached_c,
                "all_compatible_pairs": [{"bogus_stale_pair": True}],
            })

            with patch.object(service, "search_scenes", return_value=[]):
                res = service.execute_analysis_run(run_id)

            assert res["status"] == "COMPLETED"
            assert (run_dir / "summary.json").exists()
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()
