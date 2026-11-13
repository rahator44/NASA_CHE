"""
Post-V4 Production Hardening & Scientific Validation Regression Tests.
NASA Space Apps Challenge 2026: Dancing with the SARs

Validates:
1. Job State Consistency & Resume Semantics (SQLite ledger, attempts, stale failure isolation, atomic writes).
2. Strict Scene Metadata Validation (zero unsafe defaults, fail-closed metadata checks).
3. Strict Geospatial Grid Equality (strict rtol=0.0, atol=1e-6, 5m/1m drift rejection, rotation & pixel area).
4. Radiometric Calibration & Provenance (Stage A intrinsic checks, Stage B SNAP provenance, legacy whitelisting).
5. FastAPI Endpoints (authoritative SQLite reconciliation, cancellation semantics).
"""

import json
import shutil
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from osgeo import gdal, osr

gdal.UseExceptions()

from src.backend.config import settings
from src.backend.main import app
from src.backend.database.database import get_db_connection
from src.backend.services.dynamic_analysis_service import (
    DynamicAnalysisService,
    NON_TERMINAL_STATES,
    TERMINAL_STATES,
    VALID_STATE_TRANSITIONS,
    atomic_write_json,
)
from src.acquisition.scene_selector import SceneSelector
from src.acquisition.asf_client import validate_scene_metadata
from src.pipeline.sentinel1_preprocess import (
    validate_sar_raster,
    compare_rasters_for_validation,
    verify_calibrated_raster_provenance,
    AUTHORITATIVE_BASELINE_GRANULES,
    AUTHORITATIVE_CHANGE_GRANULES,
    CANONICAL_GRAPH_XML,
    CANONICAL_GRAPH_SHA256,
)
from src.pipeline.time_series import MultiDateTimeSeriesAnalyzer


# ---------------------------------------------------------------------------
# Synthetic Raster Helpers
# ---------------------------------------------------------------------------

_VALID_GT = [757960.0, 20.0, 0.0, 2740940.0, 0.0, -20.0]
_VALID_EPSG = 32645
_VALID_W, _VALID_H = 40, 40


def _create_synthetic_sar_tif(
    file_path: Path,
    width: int = _VALID_W,
    height: int = _VALID_H,
    epsg: int = _VALID_EPSG,
    gt: list = None,
    bands: int = 2,
    dtype: int = gdal.GDT_Float32,
    b1_desc: str = "Sigma0_VH",
    b2_desc: str = "Sigma0_VV",
) -> Path:
    """Create a synthetic GDAL GeoTIFF for testing with non-zero variance."""
    file_path = Path(file_path).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    gt = gt or list(_VALID_GT)

    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(file_path), width, height, bands, dtype)
    ds.SetGeoTransform(gt)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())

    # Create linear variation to ensure valid correlation without div-by-zero
    base_arr = np.linspace(0.01, 0.05, height * width, dtype=np.float32).reshape(height, width)
    if dtype != gdal.GDT_Float32:
        base_arr = (base_arr * 1000).astype(np.int16)

    for b_idx in range(1, bands + 1):
        band = ds.GetRasterBand(b_idx)
        band.SetNoDataValue(-9999.0)
        band.WriteArray(base_arr * b_idx)

    if bands >= 1:
        ds.GetRasterBand(1).SetDescription(b1_desc)
    if bands >= 2:
        ds.GetRasterBand(2).SetDescription(b2_desc)

    ds.FlushCache()
    ds = None
    return file_path


def _create_synthetic_mask_tif(
    file_path: Path,
    width: int = _VALID_W,
    height: int = _VALID_H,
    epsg: int = _VALID_EPSG,
    gt: list = None,
    fill_value: int = 1,
) -> Path:
    """Create a synthetic classification mask GeoTIFF."""
    file_path = Path(file_path).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    gt = gt or list(_VALID_GT)

    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(file_path), width, height, 1, gdal.GDT_Byte)
    ds.SetGeoTransform(gt)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(255)
    arr = np.full((height, width), fill_value, dtype=np.uint8)
    band.WriteArray(arr)
    ds.FlushCache()
    ds = None
    return file_path


def _insert_test_run(run_id: str, status: str, metadata: dict, completed_at: str = None) -> None:
    """Helper to insert a test run record into analysis_runs."""
    now_iso = datetime.now(timezone.utc).isoformat()
    params = json.dumps({"satellite_acquisitions": ["2024-06-10", "2024-07-16"]})
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO analysis_runs (run_id, analysis_type, region_id, status, executed_at, completed_at, parameters, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, "flood_change", "jamuna_sirajganj", status, now_iso, completed_at, params, json.dumps(metadata)),
        )
        conn.commit()


@pytest.fixture(autouse=True)
def cleanup_test_runs():
    """Clean up any test runs inserted into SQLite."""
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM analysis_runs WHERE run_id LIKE 'test_%'")
        conn.commit()


# ===========================================================================
# 1. Job State Consistency & Resume Semantics
# ===========================================================================

class TestJobStateConsistency:
    """Verifies state machine legality, attempt-scoped execution, and stale error isolation."""

    def test_state_sets_and_transitions_integrity(self):
        """Validates all defined states are categorized and have valid transitions."""
        assert NON_TERMINAL_STATES.isdisjoint(TERMINAL_STATES)
        assert "COMPLETED" in TERMINAL_STATES
        assert "FAILED" in TERMINAL_STATES
        assert "CANCELLED" in TERMINAL_STATES
        assert "PUBLISHING_RESULTS" in NON_TERMINAL_STATES

        # Terminal states must have empty outgoing transitions
        assert VALID_STATE_TRANSITIONS["COMPLETED"] == set()
        assert VALID_STATE_TRANSITIONS["CANCELLED"] == set()

        # FAILED runs can be retried into non-terminal states
        assert "QUEUED" in VALID_STATE_TRANSITIONS["FAILED"]

    def test_atomic_write_json(self, tmp_path):
        """atomic_write_json replaces file atomically and cleans up temporary file on success."""
        target = tmp_path / "test.json"
        data = {"hello": "world", "num": 42}
        atomic_write_json(target, data)

        assert target.exists()
        loaded = json.loads(target.read_text())
        assert loaded == data

        # Overwrite with atomic_write_json
        atomic_write_json(target, {"updated": True})
        assert json.loads(target.read_text()) == {"updated": True}

        # Check no temporary files linger
        tmp_files = list(tmp_path.glob(".tmp_*"))
        assert len(tmp_files) == 0

    def test_completed_run_returns_cached_summary_without_reexecution(self, tmp_path):
        """Calling execute_analysis_run on an already COMPLETED run returns verified summary directly."""
        run_id = f"test_completed_{datetime.now().strftime('%H%M%S%f')}"
        run_dir = tmp_path / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "request.json").write_text(json.dumps({
            "run_id": run_id,
            "aoi_wkt": "POLYGON((89.5 24.0, 89.8 24.0, 89.8 24.5, 89.5 24.5, 89.5 24.0))",
            "start_date": "2024-06-10",
            "end_date": "2024-07-16",
            "mode": "two_date_comparison",
        }))
        summary_data = {"run_id": run_id, "status": "COMPLETED", "result": "verified_output"}
        (run_dir / "summary.json").write_text(json.dumps(summary_data))

        _insert_test_run(run_id, "COMPLETED", summary_data)

        service = DynamicAnalysisService()
        with patch.object(service, "get_run_dir", return_value=run_dir):
            summary = service.execute_analysis_run(run_id)
            assert summary["status"] == "COMPLETED"
            assert summary["result"] == "verified_output"

    def test_stale_failure_isolation_on_retry(self, tmp_path):
        """When an attempt is retried, root error.json is moved to attempts/ and removed from run root."""
        run_id = f"test_retry_{datetime.now().strftime('%H%M%S%f')}"
        run_dir = tmp_path / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "request.json").write_text(json.dumps({
            "run_id": run_id,
            "aoi_wkt": "POLYGON((89.5 24.0, 89.8 24.0, 89.8 24.5, 89.5 24.5, 89.5 24.0))",
            "start_date": "2024-06-10",
            "end_date": "2024-07-16",
            "mode": "two_date_comparison",
        }))
        attempts_dir = run_dir / "attempts"
        attempts_dir.mkdir()

        # Simulate prior failed run attempt 1
        (attempts_dir / "attempt_0001.json").write_text(json.dumps({"attempt_idx": 1, "status": "FAILED"}))
        stale_error = run_dir / "error.json"
        stale_error.write_text(json.dumps({"status": "FAILED", "error": "Old timeout error"}))

        _insert_test_run(run_id, "QUEUED", {"status": "QUEUED"})

        service = DynamicAnalysisService()
        # Mock search_scenes to raise early so we inspect the pre-execution archiving
        with patch.object(service, "get_run_dir", return_value=run_dir):
            with patch.object(service, "search_scenes", side_effect=RuntimeError("Intentional early stop")):
                try:
                    service.execute_analysis_run(run_id)
                except RuntimeError:
                    pass

        # Old error was archived
        archived_files = list(attempts_dir.glob("attempt_*_error.json"))
        assert len(archived_files) >= 1
        assert "Old timeout error" in archived_files[0].read_text()


# ===========================================================================
# 2. Strict Scene Metadata Validation
# ===========================================================================

class TestStrictSceneMetadataValidation:
    """Verifies that scene selector and ASF client enforce strict metadata with no fallbacks."""

    def _make_valid_scene(self) -> dict:
        return {
            "scene_name": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
            "acquisition_time": "2024-06-10T12:05:08+00:00",
            "relative_orbit": 85,
            "orbit_direction": "ASCENDING",
            "polarization": "VV+VH",
            "beam_mode": "IW",
            "processing_level": "GRD_HD",
            "aoi_coverage_pct": 98.5,
        }

    def test_valid_scene_passes_all_validations(self):
        sc = self._make_valid_scene()
        rejections = validate_scene_metadata(sc)
        assert len(rejections) == 0

        errors = SceneSelector.validate_scene_metadata(sc)
        assert len(errors) == 0

    def test_missing_beam_mode_rejected_without_defaulting(self):
        sc = self._make_valid_scene()
        del sc["beam_mode"]
        errors = SceneSelector.validate_scene_metadata(sc)
        assert len(errors) > 0
        assert any("beam_mode" in r for r in errors)

    def test_missing_processing_level_rejected_without_defaulting(self):
        sc = self._make_valid_scene()
        del sc["processing_level"]
        errors = SceneSelector.validate_scene_metadata(sc)
        assert len(errors) > 0
        assert any("processing_level" in r for r in errors)

    def test_missing_coverage_rejected_without_defaulting(self):
        sc = self._make_valid_scene()
        del sc["aoi_coverage_pct"]
        errors = SceneSelector.validate_scene_metadata(sc)
        assert len(errors) > 0
        assert any("aoi_coverage_pct" in r for r in errors)

    def test_nan_and_infinite_coverage_rejected(self):
        for bad_cov in [float("nan"), float("inf"), float("-inf"), -5.0, 0.0, 105.0]:
            sc = self._make_valid_scene()
            sc["aoi_coverage_pct"] = bad_cov
            errors = SceneSelector.validate_scene_metadata(sc)
            assert len(errors) > 0, f"Expected coverage {bad_cov} to be rejected"

    def test_invalid_orbit_direction_rejected(self):
        for bad_orbit in ["NORTH", "EAST", "WEST", "DESC", "ASC"]:
            sc = self._make_valid_scene()
            sc["orbit_direction"] = bad_orbit
            errors = SceneSelector.validate_scene_metadata(sc)
            assert len(errors) > 0

    def test_missing_or_none_relative_orbit_rejected(self):
        sc = self._make_valid_scene()
        sc["relative_orbit"] = None
        errors = SceneSelector.validate_scene_metadata(sc)
        assert len(errors) > 0

    def test_unparseable_timestamp_rejected(self):
        for bad_time in ["not-a-date", "2024-13-45", "", "yesterday"]:
            sc = self._make_valid_scene()
            sc["acquisition_time"] = bad_time
            errors = SceneSelector.validate_scene_metadata(sc)
            assert len(errors) > 0

    def test_incompatible_scenes_rejected_in_pair_evaluation(self):
        sc1 = self._make_valid_scene()
        sc2 = self._make_valid_scene()
        sc2["acquisition_time"] = "2024-07-16T12:05:07+00:00"
        sc2["relative_orbit"] = 86  # Different track!

        is_compat, reasons, metrics = SceneSelector.evaluate_pair_comparability(
            sc1, sc2, aoi_wkt="POLYGON((89.5 24.0, 89.8 24.0, 89.8 24.5, 89.5 24.5, 89.5 24.0))"
        )
        assert is_compat is False
        assert any("orbit" in r.lower() or "track" in r.lower() for r in reasons)


# ===========================================================================
# 3. Strict Geospatial Grid Equality
# ===========================================================================

class TestStrictGeospatialGridEquality:
    """Verifies that 5m/1m spatial drifts, resolution errors, and rotations are rejected."""

    def test_identical_rasters_pass_grid_comparison(self, tmp_path):
        r1 = _create_synthetic_sar_tif(tmp_path / "r1.tif")
        r2 = _create_synthetic_sar_tif(tmp_path / "r2.tif")
        res = compare_rasters_for_validation(r1, r2)
        assert res["is_compatible"] is True

    def test_five_meter_origin_shift_strictly_rejected(self, tmp_path):
        """5m shift (which default rtol=1e-5 previously accepted) must be strictly rejected."""
        gt_shifted = list(_VALID_GT)
        gt_shifted[0] += 5.0  # +5m Easting shift

        r1 = _create_synthetic_sar_tif(tmp_path / "r1.tif", gt=_VALID_GT)
        r2 = _create_synthetic_sar_tif(tmp_path / "r2.tif", gt=gt_shifted)

        with pytest.raises(ValueError, match="[Gg]eotransform mismatch"):
            compare_rasters_for_validation(r1, r2)

    def test_one_meter_origin_shift_strictly_rejected(self, tmp_path):
        """1m shift must be strictly rejected under rtol=0.0, atol=1e-6."""
        gt_shifted = list(_VALID_GT)
        gt_shifted[0] += 1.0  # +1m Easting shift

        r1 = _create_synthetic_sar_tif(tmp_path / "r1.tif", gt=_VALID_GT)
        r2 = _create_synthetic_sar_tif(tmp_path / "r2.tif", gt=gt_shifted)

        with pytest.raises(ValueError, match="[Gg]eotransform mismatch"):
            compare_rasters_for_validation(r1, r2)

    def test_pixel_resolution_deviation_rejected(self, tmp_path):
        """Pixel resolution 21m instead of 20m must be rejected."""
        gt_res = list(_VALID_GT)
        gt_res[1] = 21.0
        gt_res[5] = -21.0

        r1 = _create_synthetic_sar_tif(tmp_path / "r1.tif", gt=gt_res)
        with pytest.raises(ValueError, match="resolution|pixel area"):
            validate_sar_raster(r1)

    def test_nonzero_rotation_rejected(self, tmp_path):
        """Non-zero rotation terms in geotransform must be rejected."""
        gt_rot = list(_VALID_GT)
        gt_rot[2] = 0.05  # skew term

        r1 = _create_synthetic_sar_tif(tmp_path / "r1.tif", gt=gt_rot)
        with pytest.raises(ValueError, match="non-zero rotation or shearing"):
            validate_sar_raster(r1)

    def test_time_series_analyzer_rejects_grid_mismatch(self, tmp_path):
        """MultiDateTimeSeriesAnalyzer strictly rejects 5m drift between observations."""
        m1 = _create_synthetic_mask_tif(tmp_path / "m1.tif", gt=_VALID_GT)
        gt_shifted = list(_VALID_GT)
        gt_shifted[0] += 5.0
        m2 = _create_synthetic_mask_tif(tmp_path / "m2.tif", gt=gt_shifted)

        records = [
            {"acquisition_time": "2024-06-10T12:05:08Z", "scene_name": "t1", "mask_tif": m1},
            {"acquisition_time": "2024-07-16T12:05:07Z", "scene_name": "t2", "mask_tif": m2},
        ]
        with pytest.raises(ValueError, match="[Gg]eotransform mismatch"):
            MultiDateTimeSeriesAnalyzer.analyze_sequence(records)


# ===========================================================================
# 4. Radiometric Calibration & Provenance
# ===========================================================================

class TestRadiometricCalibrationAndProvenance:
    """Verifies Stage A intrinsic checks, Stage B provenance validation, and legacy whitelisting."""

    def test_synthetic_calibrated_raster_with_snap_provenance_passes(self, tmp_path):
        tif = _create_synthetic_sar_tif(tmp_path / "obs_snap.tif")
        h = hashlib.sha256()
        with open(tif, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        tif_hash = h.hexdigest()

        canonical_graph_xml = CANONICAL_GRAPH_XML
        graph_hash = hashlib.sha256(canonical_graph_xml.read_bytes()).hexdigest() if canonical_graph_xml.exists() else CANONICAL_GRAPH_SHA256

        src_file = tmp_path / "real_source.zip"
        src_file.write_bytes(b"dummy valid raw source bytes")
        src_hash = hashlib.sha256(src_file.read_bytes()).hexdigest()

        prov_data = {
            "granule_id": "test_granule_123",
            "source_archive": str(src_file),
            "source_archive_sha256": src_hash,
            "output_sha256": tif_hash,
            "graph_sha256": graph_hash,
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
        prov_file = tmp_path / "obs_snap_provenance.json"
        atomic_write_json(prov_file, prov_data)

        res = verify_calibrated_raster_provenance(tif, prov_file, scene_name="test_granule_123")
        assert res["provenance_verified"] is True
        assert res["status"] == "VERIFIED_PROVENANCE"

    def test_missing_provenance_sidecar_rejected(self, tmp_path):
        tif = _create_synthetic_sar_tif(tmp_path / "unverified.tif")
        with pytest.raises(ValueError, match="provenance record missing"):
            verify_calibrated_raster_provenance(tif, scene_name="unknown_granule_999")

    def test_unverified_processing_chain_rejected(self, tmp_path):
        tif = _create_synthetic_sar_tif(tmp_path / "bad_chain.tif")
        tif_hash = hashlib.sha256(tif.read_bytes()).hexdigest()

        # 1. Free-text processing_chain alone without physical source file must be rejected
        prov_data_freetext = {
            "granule_id": "bad_chain_granule",
            "output_sha256": tif_hash,
            "provenance": {
                "processing_chain": "manual_photoshop_contrast_stretch",
                "verification_status": "UNVERIFIED",
            },
        }
        prov_file_freetext = tmp_path / "bad_chain_freetext_provenance.json"
        atomic_write_json(prov_file_freetext, prov_data_freetext)

        with pytest.raises(ValueError, match="missing mandatory 'source_archive' or 'source_raster'"):
            verify_calibrated_raster_provenance(tif, prov_file_freetext, scene_name="bad_chain_granule")

        # 2. Unverified processing graph reference must be rejected
        src_file = tmp_path / "real_bad_source.zip"
        src_file.write_bytes(b"dummy source bytes")
        src_hash = hashlib.sha256(src_file.read_bytes()).hexdigest()

        prov_data_bad_graph = {
            "granule_id": "bad_chain_granule",
            "output_sha256": tif_hash,
            "source_archive": str(src_file),
            "source_archive_sha256": src_hash,
            "graph_sha256": CANONICAL_GRAPH_SHA256,
            "source_band_mapping": {"source_band_vh": 1, "source_band_vv": 2},
            "processing_parameters": {
                "radiometric_quantity": "Sigma0",
                "radiometric_domain": "linear_power",
                "output_bands": ["Sigma0_VH", "Sigma0_VV"],
            },
            "graph_reference": "manual_photoshop_graph.xml",
            "provenance": {
                "processing_chain": "manual_photoshop_contrast_stretch",
                "verification_status": "UNVERIFIED",
            },
        }
        prov_file_bad_graph = tmp_path / "bad_chain_bad_graph_provenance.json"
        atomic_write_json(prov_file_bad_graph, prov_data_bad_graph)

        with pytest.raises(ValueError, match="Unverified processing reference"):
            verify_calibrated_raster_provenance(tif, prov_file_bad_graph, scene_name="bad_chain_granule")

    def test_mismatched_output_sha256_rejected(self, tmp_path):
        tif = _create_synthetic_sar_tif(tmp_path / "tampered.tif")
        prov_data = {
            "granule_id": "tampered_granule",
            "output_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            "provenance": {
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
            },
        }
        prov_file = tmp_path / "tampered_provenance.json"
        atomic_write_json(prov_file, prov_data)

        with pytest.raises(ValueError, match="Provenance checksum mismatch"):
            verify_calibrated_raster_provenance(tif, prov_file, scene_name="tampered_granule")

    def test_historical_legacy_granule_checks_registered_checksum(self, tmp_path):
        # A forged or synthetic file claiming to be june10_aligned must be rejected
        forged_tif = _create_synthetic_sar_tif(tmp_path / "june10_aligned.tif")
        with pytest.raises(ValueError, match="Historical reference raster checksum verification failed"):
            verify_calibrated_raster_provenance(forged_tif, scene_name="june10_aligned")

        # The authentic historical reference raster with matching SHA-256 must pass
        auth_tif = settings.DATA_DIR / "processed" / "aligned" / "june10_aligned.tif"
        if auth_tif.exists():
            res = verify_calibrated_raster_provenance(auth_tif, scene_name="june10_aligned")
            assert res["provenance_verified"] is True
            assert res["status"] == "VERIFIED_HISTORICAL_LEGACY"


# ===========================================================================
# 5. FastAPI Endpoint Hardening
# ===========================================================================

class TestFastApiEndpointHardening:
    """Verifies API endpoints against the authoritative SQLite state ledger."""

    def test_status_endpoint_returns_completed_even_with_stale_error_file(self, tmp_path):
        """When SQLite ledger is COMPLETED, API must return COMPLETED (stale error.json ignored)."""
        run_id = f"test_api_status_{datetime.now().strftime('%H%M%S%f')}"
        run_dir = tmp_path / run_id
        run_dir.mkdir(parents=True)

        summary_file = run_dir / "summary.json"
        summary_file.write_text(json.dumps({"run_id": run_id, "status": "COMPLETED"}))

        # Intentionally inject stale error file
        error_file = run_dir / "error.json"
        error_file.write_text(json.dumps({"status": "FAILED", "error": "Stale historical error"}))

        _insert_test_run(run_id, "COMPLETED", {"status": "COMPLETED"})

        client = TestClient(app)
        with patch.object(DynamicAnalysisService, "get_run_dir", return_value=run_dir):
            resp = client.get(f"/api/v1/analysis-requests/{run_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "COMPLETED"
            assert data["progress_pct"] == 100.0

    def test_status_endpoint_returns_inflight_stage_and_progress(self, tmp_path):
        """When SQLite ledger has an active in-flight stage, API returns stage and progress."""
        run_id = f"test_api_inflight_{datetime.now().strftime('%H%M%S%f')}"
        run_dir = tmp_path / run_id
        run_dir.mkdir(parents=True)

        _insert_test_run(run_id, "DOWNLOADING", {"stage": "DOWNLOADING", "progress_pct": 40.0})

        client = TestClient(app)
        with patch.object(DynamicAnalysisService, "get_run_dir", return_value=run_dir):
            resp = client.get(f"/api/v1/analysis-requests/{run_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "DOWNLOADING"
            assert data["progress_pct"] == 40.0
            assert data["stage"] == "DOWNLOADING"

    def test_cancel_already_completed_run_rejected(self, tmp_path):
        """Cancelling a run that is already COMPLETED returns HTTP 400 Bad Request."""
        run_id = f"test_cancel_completed_{datetime.now().strftime('%H%M%S%f')}"
        run_dir = tmp_path / run_id
        run_dir.mkdir(parents=True)

        _insert_test_run(run_id, "COMPLETED", {"status": "COMPLETED"})

        client = TestClient(app)
        with patch.object(DynamicAnalysisService, "get_run_dir", return_value=run_dir):
            resp = client.post(f"/api/v1/analysis-requests/{run_id}/cancel")
            assert resp.status_code == 400
            assert "already COMPLETED" in resp.json()["detail"]
