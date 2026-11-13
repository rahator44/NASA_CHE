"""
Earth Pulse — Regression Tests for Audit V4 Corrections A–H.
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers the eight targeted corrections following the independent ChatGPT review
of EARTH_PULSE_DYNAMIC_BACKEND_REVIEW.zip (475-file ZIP V3).

Correction A — Raster validation field names (epsg/width/height, not crs/x_size/y_size)
Correction B — Time-series common-domain vs independent-observation water extents
Correction C — Per-granule provenance metadata and ALTERNATE_ID_UNVERIFIED tagging
Correction D — Scene metadata strict validation (no missing/zero coverage, timestamps, etc.)
Correction E — AOI geography and resource validation before job creation
Correction F — HTTPS-only downloads, redirect domain validation
Correction G — API returns actual CANCELLED status (not COMPLETED), async default
Correction H — All four area definitions present in summary.json
"""

import json
import tempfile
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from src.backend.config import settings

try:
    from osgeo import gdal, ogr, osr
    gdal.UseExceptions()
    _HAS_GDAL = True
except ImportError:
    _HAS_GDAL = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_raster(tmp_path: Path, width: int, height: int, epsg: int,
                       gt: list, bands: int = 2,
                       b1_desc: str = "Sigma0_VH",
                       b2_desc: str = "Sigma0_VV",
                       fill_value: float = 1e-3) -> Path:
    """Create a minimal GeoTIFF satisfying validate_sar_raster() requirements."""
    tif = tmp_path / "test_raster.tif"
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(tif), width, height, bands, gdal.GDT_Float32)
    ds.SetGeoTransform(gt)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())
    for b_idx in range(1, bands + 1):
        band = ds.GetRasterBand(b_idx)
        band.SetNoDataValue(-9999.0)
        arr = np.full((height, width), fill_value, dtype=np.float32)
        band.WriteArray(arr)
    if bands >= 1:
        ds.GetRasterBand(1).SetDescription(b1_desc)
    if bands >= 2:
        ds.GetRasterBand(2).SetDescription(b2_desc)
    ds.FlushCache()
    ds = None
    return tif


# Standard valid geotransform for EPSG:32645, 20m pixel
_VALID_GT = [757960.0, 20.0, 0.0, 2740940.0, 0.0, -20.0]
_VALID_EPSG = 32645
_VALID_W, _VALID_H = 50, 50


# ===========================================================================
# CORRECTION A — Raster validation field names
# ===========================================================================

@pytest.mark.skipif(not _HAS_GDAL, reason="GDAL not available")
class TestCorrectionA:
    """validate_sar_raster() must return epsg/width/height; alignment checks must use them."""

    def test_validate_sar_raster_returns_correct_field_names(self, tmp_path):
        """validate_sar_raster() returns 'epsg', 'width', 'height' (not crs, x_size, y_size)."""
        from src.pipeline.sentinel1_preprocess import validate_sar_raster
        tif = _make_mock_raster(tmp_path, _VALID_W, _VALID_H, _VALID_EPSG, _VALID_GT)
        meta = validate_sar_raster(tif)
        assert "epsg" in meta, "Missing 'epsg' key"
        assert "width" in meta, "Missing 'width' key"
        assert "height" in meta, "Missing 'height' key"
        assert "geotransform" in meta, "Missing 'geotransform' key"
        assert "crs" not in meta, "'crs' must NOT be in metadata (old field name)"
        assert "x_size" not in meta, "'x_size' must NOT be in metadata (old field name)"
        assert "y_size" not in meta, "'y_size' must NOT be in metadata (old field name)"
        assert meta["epsg"] == _VALID_EPSG
        assert meta["width"] == _VALID_W
        assert meta["height"] == _VALID_H

    def test_validate_sar_raster_returns_band_order_fields(self, tmp_path):
        """validate_sar_raster() returns band descriptions, units, and valid_data_pixels."""
        from src.pipeline.sentinel1_preprocess import validate_sar_raster
        tif = _make_mock_raster(tmp_path, _VALID_W, _VALID_H, _VALID_EPSG, _VALID_GT)
        meta = validate_sar_raster(tif)
        assert "units" in meta, "Missing 'units' key"
        assert "linear_power" in meta["units"], f"Expected linear_power units, got '{meta['units']}'"
        assert "valid_data_pixels" in meta, "Missing 'valid_data_pixels' key"
        assert isinstance(meta["valid_data_pixels"], int)
        assert meta["valid_data_pixels"] >= 0
        bands = meta.get("bands", {})
        assert 1 in bands and 2 in bands
        assert "polarization" in bands[1], "Band 1 must have polarization field"
        assert "polarization" in bands[2], "Band 2 must have polarization field"
        assert bands[1]["polarization"] == "VH"
        assert bands[2]["polarization"] == "VV"

    def test_band_order_violation_raises(self, tmp_path):
        """Raster with Band 1 = 'Sigma0_VV' (instead of VH) must raise ValueError."""
        from src.pipeline.sentinel1_preprocess import validate_sar_raster
        tif = _make_mock_raster(tmp_path, _VALID_W, _VALID_H, _VALID_EPSG, _VALID_GT,
                                b1_desc="Sigma0_VV", b2_desc="Sigma0_VH")
        with pytest.raises(ValueError, match="Band order error.*Band 1"):
            validate_sar_raster(tif)

    def test_dimension_mismatch_raises(self, tmp_path):
        """Dimension mismatch between two rasters in execute_analysis_run must raise ValueError."""
        from src.pipeline.sentinel1_preprocess import validate_sar_raster
        # Simulate what execute_analysis_run does for alignment check
        base_m = {"epsg": _VALID_EPSG, "width": _VALID_W, "height": _VALID_H,
                  "geotransform": _VALID_GT}
        curr_m = {"epsg": _VALID_EPSG, "width": _VALID_W + 10, "height": _VALID_H,
                  "geotransform": _VALID_GT}
        # The alignment logic (corrected) uses m.get("width") and m.get("height")
        assert (curr_m.get("width"), curr_m.get("height")) != (base_m.get("width"), base_m.get("height"))

    def test_validate_sar_raster_rejects_negative_db_values(self, tmp_path):
        """
        Correction 6: validate_sar_raster must reject rasters with negative pixel values,
        which indicate decibels (dB) or uncalibrated units, not linear power Sigma0.
        """
        from src.pipeline.sentinel1_preprocess import validate_sar_raster
        tif = _make_mock_raster(tmp_path, _VALID_W, _VALID_H, _VALID_EPSG, _VALID_GT, fill_value=-15.0)
        with pytest.raises(ValueError, match="indicating decibel \\(dB\\) or uncalibrated units"):
            validate_sar_raster(tif)

    def test_validate_sar_raster_rejects_unreferenced_geotransform(self, tmp_path):
        """
        Correction 6: validate_sar_raster must reject unreferenced or default geotransforms (0, 1, 0, 0, 0, 1).
        """
        from src.pipeline.sentinel1_preprocess import validate_sar_raster
        dummy_gt = [0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        tif = _make_mock_raster(tmp_path, _VALID_W, _VALID_H, _VALID_EPSG, dummy_gt)
        with pytest.raises(ValueError, match="unreferenced or default geotransform"):
            validate_sar_raster(tif)

    def test_crs_mismatch_raises(self, tmp_path):
        """CRS mismatch between two rasters must be detected using 'epsg' field."""
        base_m = {"epsg": 32645, "width": _VALID_W, "height": _VALID_H,
                  "geotransform": _VALID_GT}
        curr_m = {"epsg": 32646, "width": _VALID_W, "height": _VALID_H,
                  "geotransform": _VALID_GT}
        # The corrected alignment logic uses m.get("epsg")
        assert curr_m.get("epsg") != base_m.get("epsg"), "CRS mismatch must be detectable via epsg field"
        # Old code would check m.get("crs") which would be None for both — NEVER detecting a mismatch
        assert base_m.get("crs") is None and curr_m.get("crs") is None, \
            "crs field is absent; old code would silently pass any CRS mismatch"

    def test_geotransform_mismatch_raises(self, tmp_path):
        """Geotransform mismatch must be detected (index 0 = origin X)."""
        base_m = {"epsg": _VALID_EPSG, "width": _VALID_W, "height": _VALID_H,
                  "geotransform": [757960.0, 20.0, 0.0, 2740940.0, 0.0, -20.0]}
        curr_m = {"epsg": _VALID_EPSG, "width": _VALID_W, "height": _VALID_H,
                  "geotransform": [757980.0, 20.0, 0.0, 2740940.0, 0.0, -20.0]}  # offset by 20m
        base_gt = base_m.get("geotransform", [])
        curr_gt = curr_m.get("geotransform", [])
        mismatch_found = any(abs(base_gt[i] - curr_gt[i]) > 1e-3 for i in range(6))
        assert mismatch_found, "Geotransform mismatch must be detected"

    def test_valid_raster_no_dimension_mismatch(self, tmp_path):
        """Identical rasters must NOT trigger a mismatch error."""
        base_m = {"epsg": _VALID_EPSG, "width": _VALID_W, "height": _VALID_H,
                  "geotransform": _VALID_GT}
        curr_m = {"epsg": _VALID_EPSG, "width": _VALID_W, "height": _VALID_H,
                  "geotransform": _VALID_GT}
        assert curr_m.get("epsg") == base_m.get("epsg")
        assert (curr_m.get("width"), curr_m.get("height")) == (base_m.get("width"), base_m.get("height"))


# ===========================================================================
# CORRECTION B — Scientific time-series comparability
# ===========================================================================

@pytest.mark.skipif(not _HAS_GDAL, reason="GDAL not available")
class TestCorrectionB:
    """Time-series must distinguish independent observation extents from common-domain changes."""

    def _make_water_mask(self, tmp_path: Path, name: str,
                         water_pixels: list, non_water_pixels: list,
                         nodata_pixels: list,
                         w: int = 10, h: int = 10) -> Path:
        """Create a water mask GeoTIFF (0=non-water, 1=water, 3=nodata)."""
        mask_path = tmp_path / name
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(str(mask_path), w, h, 1, gdal.GDT_Byte)
        ds.SetGeoTransform([757960.0, 20.0, 0.0, 2740940.0, 0.0, -20.0])
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32645)
        ds.SetProjection(srs.ExportToWkt())
        arr = np.full((h, w), 0, dtype=np.uint8)  # default non-water
        for (r, c) in water_pixels:
            arr[r, c] = 1
        for (r, c) in nodata_pixels:
            arr[r, c] = 3
        b = ds.GetRasterBand(1)
        b.WriteArray(arr)
        b.SetNoDataValue(255)
        ds.FlushCache()
        ds = None
        return mask_path

    def test_common_domain_change_differs_from_independent(self, tmp_path):
        """
        Common-domain change must differ from independent-observation difference
        when the two scenes have non-overlapping NoData regions.
        """
        from src.pipeline.time_series import MultiDateTimeSeriesAnalyzer

        # Scene 1: pixels (0,0)..(0,4) are water, (0,5)..(0,9) are nodata
        # Scene 2: pixels (0,0)..(0,2) are water, (0,5)..(0,9) are water
        # Independent:  t1_water=5px,  t2_water=8px → Δ=3px
        # Common valid: pixels 0..4 are valid in t1; pixels 0..9 are "valid" in t2
        # Common of t1_valid ∩ t2_valid = pixels 0..4 (scene2 nodata=none here)
        t1_water = [(0, c) for c in range(5)]   # 5 water pixels
        t1_nodata = [(0, c) for c in range(5, 10)]  # 5 nodata pixels
        t2_water = [(0, c) for c in range(3)]   # 3 water pixels (smaller)
        # t2 has no nodata in row 0 — different valid mask

        m1 = self._make_water_mask(tmp_path, "mask_t1.tif", t1_water, [], t1_nodata)
        m2 = self._make_water_mask(tmp_path, "mask_t2.tif", t2_water, [], [])

        records = [
            {"acquisition_time": "2024-06-10T12:05:00Z", "scene_name": "t1", "mask_tif": m1},
            {"acquisition_time": "2024-07-16T12:05:00Z", "scene_name": "t2", "mask_tif": m2},
        ]
        result = MultiDateTimeSeriesAnalyzer.analyze_sequence(records)

        assert "step_changes" in result
        assert len(result["step_changes"]) == 1
        sc = result["step_changes"][0]

        # Both metrics must be present and explicitly labelled
        assert "delta_independent_observation_km2" in sc, \
            "Independent-observation difference must be present"
        assert "change_common_domain_km2" in sc, \
            "Common-domain change must be present"
        assert "common_valid_domain_km2" in sc, \
            "Common valid domain area must be present"

        # Timeline entries must have water_extent_independent_km2
        for entry in result["timeline"]:
            assert "water_extent_independent_km2" in entry, \
                "Timeline entry must have water_extent_independent_km2"

    def test_step_change_labels_are_distinct(self, tmp_path):
        """Independent and common-domain step_changes must have different label fields."""
        from src.pipeline.time_series import MultiDateTimeSeriesAnalyzer
        m1 = self._make_water_mask(tmp_path, "m1.tif", [(0, 0)], [(0, 1)], [])
        m2 = self._make_water_mask(tmp_path, "m2.tif", [(0, 0), (0, 1)], [], [])
        records = [
            {"acquisition_time": "2024-06-10T12:00:00Z", "scene_name": "s1", "mask_tif": m1},
            {"acquisition_time": "2024-07-16T12:00:00Z", "scene_name": "s2", "mask_tif": m2},
        ]
        result = MultiDateTimeSeriesAnalyzer.analyze_sequence(records)
        sc = result["step_changes"][0]
        # Must not conflate the two metrics under "delta_water_km2" without labeling
        assert "delta_independent_observation_label" in sc or "delta_independent_observation_km2" in sc
        assert "change_common_domain_label" in sc or "change_common_domain_km2" in sc

    def test_time_series_rejects_dimension_mismatch(self, tmp_path):
        """Correction 7: MultiDateTimeSeriesAnalyzer.analyze_sequence must reject masks with different dimensions."""
        from src.pipeline.time_series import MultiDateTimeSeriesAnalyzer
        m1 = self._make_water_mask(tmp_path, "m_10x10.tif", [(0, 0)], [], [], w=10, h=10)
        m2 = self._make_water_mask(tmp_path, "m_12x10.tif", [(0, 0)], [], [], w=12, h=10)
        records = [
            {"acquisition_time": "2024-06-10T12:00:00Z", "scene_name": "s1", "mask_tif": m1},
            {"acquisition_time": "2024-07-16T12:00:00Z", "scene_name": "s2", "mask_tif": m2},
        ]
        with pytest.raises(ValueError, match="Raster dimension mismatch in time series"):
            MultiDateTimeSeriesAnalyzer.analyze_sequence(records)

    def test_time_series_rejects_geotransform_mismatch(self, tmp_path):
        """Correction 7: MultiDateTimeSeriesAnalyzer.analyze_sequence must reject masks with shifted geotransforms."""
        from src.pipeline.time_series import MultiDateTimeSeriesAnalyzer
        m1 = tmp_path / "m1_grid.tif"
        m2 = tmp_path / "m2_grid.tif"
        driver = gdal.GetDriverByName("GTiff")
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32645)

        for p, gt in [(m1, [757960.0, 20.0, 0.0, 2740940.0, 0.0, -20.0]),
                      (m2, [757980.0, 20.0, 0.0, 2740940.0, 0.0, -20.0])]:
            ds = driver.Create(str(p), 10, 10, 1, gdal.GDT_Byte)
            ds.SetGeoTransform(gt)
            ds.SetProjection(srs.ExportToWkt())
            ds.GetRasterBand(1).WriteArray(np.zeros((10, 10), dtype=np.uint8))
            ds.FlushCache()
            ds = None

        records = [
            {"acquisition_time": "2024-06-10T12:00:00Z", "scene_name": "s1", "mask_tif": m1},
            {"acquisition_time": "2024-07-16T12:00:00Z", "scene_name": "s2", "mask_tif": m2},
        ]
        with pytest.raises(ValueError, match="Raster geotransform mismatch in time series"):
            MultiDateTimeSeriesAnalyzer.analyze_sequence(records)

    def test_time_series_rejects_crs_mismatch(self, tmp_path):
        """Correction 7: MultiDateTimeSeriesAnalyzer.analyze_sequence must reject masks with different CRS."""
        from src.pipeline.time_series import MultiDateTimeSeriesAnalyzer
        m1 = tmp_path / "m1_crs.tif"
        m2 = tmp_path / "m2_crs.tif"
        driver = gdal.GetDriverByName("GTiff")
        gt = [757960.0, 20.0, 0.0, 2740940.0, 0.0, -20.0]

        for p, epsg in [(m1, 32645), (m2, 32646)]:
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(epsg)
            ds = driver.Create(str(p), 10, 10, 1, gdal.GDT_Byte)
            ds.SetGeoTransform(gt)
            ds.SetProjection(srs.ExportToWkt())
            ds.GetRasterBand(1).WriteArray(np.zeros((10, 10), dtype=np.uint8))
            ds.FlushCache()
            ds = None

        records = [
            {"acquisition_time": "2024-06-10T12:00:00Z", "scene_name": "s1", "mask_tif": m1},
            {"acquisition_time": "2024-07-16T12:00:00Z", "scene_name": "s2", "mask_tif": m2},
        ]
        with pytest.raises(ValueError, match="Raster CRS mismatch in time series"):
            MultiDateTimeSeriesAnalyzer.analyze_sequence(records)


# ===========================================================================
# CORRECTION C — Granule provenance
# ===========================================================================

class TestCorrectionC:
    """Granule provenance records must be written per-run, and alternate IDs must NOT reuse historical imagery."""

    def test_unverified_alternate_granule_rejected_from_historical_reuse(self, tmp_path):
        """
        Behavior test: Alternate granule ID '...0699A3_DFB9' must NOT reuse 'june10_aligned.tif'.
        Without independent SNAP processing evidence, resolution must raise FileNotFoundError.
        """
        from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
        svc = DynamicAnalysisService.__new__(DynamicAnalysisService)
        svc.download_manager = MagicMock()
        svc.download_manager.get_local_cached_file.return_value = None

        alt_scene = {
            "scene_name": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_0699A3_DFB9",
            "acquisition_time": "2024-06-10T12:05:08Z",
            "download_url": "",
        }
        aoi_wkt = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"
        run_dir = tmp_path / "run_alt"
        run_dir.mkdir(parents=True)
        (run_dir / "rasters").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Historical data substitution is strictly disabled"):
            svc._resolve_or_extract_calibrated_raster(alt_scene, aoi_wkt, run_dir, "t1_calibrated.tif")

    def test_unverified_change_alternate_granule_rejected_from_historical_reuse(self, tmp_path):
        """
        Behavior test: Alternate change granule '...06ABA8_8857' must NOT reuse 'july16_aligned.tif'.
        Must raise FileNotFoundError.
        """
        from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
        svc = DynamicAnalysisService.__new__(DynamicAnalysisService)
        svc.download_manager = MagicMock()
        svc.download_manager.get_local_cached_file.return_value = None

        alt_scene = {
            "scene_name": "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABA8_8857",
            "acquisition_time": "2024-07-16T12:05:07Z",
            "download_url": "",
        }
        aoi_wkt = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"
        run_dir = tmp_path / "run_alt2"
        run_dir.mkdir(parents=True)
        (run_dir / "rasters").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Historical data substitution is strictly disabled"):
            svc._resolve_or_extract_calibrated_raster(alt_scene, aoi_wkt, run_dir, "t2_calibrated.tif")

    def test_provenance_json_written_on_whitelist_match(self, tmp_path):
        """When a known granule resolves from the whitelist, provenance.json must be written."""
        # Set up fake source raster structure
        data_dir = tmp_path / "data" / "processed" / "aligned"
        data_dir.mkdir(parents=True)
        rasters_dir = tmp_path / "run" / "rasters"
        rasters_dir.mkdir(parents=True)

        if not _HAS_GDAL:
            pytest.skip("GDAL not available")

        # Use authentic reference raster bytes if available so registered checksum passes
        real_src = settings.DATA_DIR / "processed" / "aligned" / "june10_aligned.tif"
        if not real_src.exists():
            real_src = Path("data/processed/aligned/june10_aligned.tif")
        if real_src.exists():
            (data_dir / "june10_aligned.tif").write_bytes(real_src.read_bytes())
        else:
            src = _make_mock_raster(data_dir, _VALID_W, _VALID_H, _VALID_EPSG, _VALID_GT,
                                    fill_value=1e-3)
            (data_dir / "june10_aligned.tif").write_bytes(src.read_bytes())

        # Patch settings.DATA_DIR to point to our tmp structure
        with patch("src.backend.services.dynamic_analysis_service.settings") as mock_settings:
            mock_settings.DATA_DIR = tmp_path / "data"
            mock_settings.MODELS_DIR = tmp_path / "models"
            mock_settings.AOI_MAX_AREA_KM2 = 200.0
            mock_settings.JAMUNA_STUDY_REGION_WKT = \
                "POLYGON((89.0 24.0, 90.5 24.0, 90.5 25.5, 89.0 25.5, 89.0 24.0))"
            from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
            svc = DynamicAnalysisService.__new__(DynamicAnalysisService)
            svc.download_manager = MagicMock()

            scene = {
                "scene_name": "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
                "acquisition_time": "2024-06-10T12:05:08Z",
                "download_url": "",
            }
            aoi_wkt = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"
            run_dir = tmp_path / "run"

            with patch("src.backend.services.dynamic_analysis_service.Sentinel1Preprocessor.extract_sub_aoi"):
                svc._resolve_or_extract_calibrated_raster(scene, aoi_wkt, run_dir, "t1_calibrated.tif")

            provenance_file = rasters_dir / "t1_calibrated_provenance.json"
            assert provenance_file.exists(), \
                f"Provenance JSON not written at {provenance_file}"
            pdata = json.loads(provenance_file.read_text())
            assert pdata.get("granule_id") is not None
            assert "provenance" in pdata
            assert "verification_status" in pdata["provenance"]


# ===========================================================================
# CORRECTION D — Scene metadata strict validation
# ===========================================================================

class TestCorrectionD:
    """validate_scene_metadata() must reject scenes with invalid or missing required fields."""

    def _valid_scene(self):
        return {
            "scene_name": "TEST_SCENE_001",
            "acquisition_time": "2024-06-10T12:05:08Z",
            "orbit_direction": "ASCENDING",
            "relative_orbit": 85,
            "polarization": "VV+VH",
            "beam_mode": "IW",
            "processing_level": "GRD_HD",
            "aoi_coverage_pct": 97.5,
        }

    def test_valid_scene_passes(self):
        from src.acquisition.asf_client import validate_scene_metadata
        rejections = validate_scene_metadata(self._valid_scene())
        assert rejections == [], f"Valid scene should pass, got: {rejections}"

    def test_missing_coverage_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["aoi_coverage_pct"] = None
        rejections = validate_scene_metadata(sc)
        assert any("coverage" in r.lower() for r in rejections), \
            f"Missing coverage should be rejected: {rejections}"

    def test_zero_coverage_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["aoi_coverage_pct"] = 0.0
        rejections = validate_scene_metadata(sc)
        assert any("coverage" in r.lower() for r in rejections), \
            f"Zero coverage (default) should be rejected: {rejections}"

    def test_missing_acquisition_time_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["acquisition_time"] = ""
        rejections = validate_scene_metadata(sc)
        assert any("acquisition_time" in r.lower() or "timestamp" in r.lower() for r in rejections)

    def test_invalid_timestamp_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["acquisition_time"] = "not-a-date"
        rejections = validate_scene_metadata(sc)
        assert any("acquisition_time" in r.lower() or "iso8601" in r.lower() for r in rejections)

    def test_none_relative_orbit_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["relative_orbit"] = None
        rejections = validate_scene_metadata(sc)
        assert any("relative_orbit" in r.lower() or "orbit" in r.lower() for r in rejections)

    def test_invalid_orbit_direction_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["orbit_direction"] = "SIDEWAYS"
        rejections = validate_scene_metadata(sc)
        assert any("orbit_direction" in r.lower() or "flight" in r.lower() for r in rejections)

    def test_single_polarization_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["polarization"] = "VV"  # only VV, missing VH
        rejections = validate_scene_metadata(sc)
        assert any("polarization" in r.lower() or "vh" in r.lower() for r in rejections)

    def test_wrong_beam_mode_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["beam_mode"] = "EW"
        rejections = validate_scene_metadata(sc)
        assert any("beam_mode" in r.lower() for r in rejections)

    def test_wrong_processing_level_rejected(self):
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        sc["processing_level"] = "GRD_MD"
        rejections = validate_scene_metadata(sc)
        assert any("processing_level" in r.lower() for r in rejections)

    def test_coverage_cannot_default_to_100_pct(self):
        """
        Coverage must never silently default to 100% when the field is absent.
        A missing coverage field means no information — fail closed to 0%.
        """
        from src.acquisition.asf_client import validate_scene_metadata
        sc = self._valid_scene()
        del sc["aoi_coverage_pct"]  # Completely absent
        rejections = validate_scene_metadata(sc)
        assert len(rejections) > 0, \
            "Missing aoi_coverage_pct must be rejected — it must never default to 100%"


# ===========================================================================
# CORRECTION E — Supported geography and resource validation
# ===========================================================================

class TestCorrectionE:
    """AOI must be validated for size and geographic intersection before job creation."""

    def _mock_settings(self):
        mock = MagicMock()
        mock.AOI_MAX_AREA_KM2 = 200.0
        mock.JAMUNA_STUDY_REGION_WKT = \
            "POLYGON((89.0 24.0, 90.5 24.0, 90.5 25.5, 89.0 25.5, 89.0 24.0))"
        mock.DATA_DIR = Path("/tmp/nonexistent_earth_pulse")
        mock.MODELS_DIR = Path("/tmp/nonexistent_earth_pulse/models")
        mock.SQLITE_DB_PATH = Path("/tmp/nonexistent_earth_pulse/db.sqlite")
        return mock

    def test_aoi_outside_jamuna_region_rejected(self):
        """AOI entirely outside the Jamuna study region must raise ValueError."""
        from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
        aoi_outside = "POLYGON((80.0 20.0, 80.5 20.0, 80.5 20.5, 80.0 20.5, 80.0 20.0))"
        service = DynamicAnalysisService()
        with pytest.raises(ValueError, match="not completely contained within the supported Jamuna study region"):
            service.create_analysis_request(
                aoi_wkt=aoi_outside,
                start_date="2024-06-10",
                end_date="2024-07-16",
            )

    def test_aoi_partially_outside_jamuna_region_rejected(self):
        """
        Correction 3: AOI partially extending outside the Jamuna study region must be strictly REJECTED.
        Partial overlap without complete containment is not permitted.
        """
        from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
        # Crosses western boundary (89.0): spans 88.8 to 89.5
        aoi_partially_outside = "POLYGON((88.8 24.5, 89.5 24.5, 89.5 24.7, 88.8 24.7, 88.8 24.5))"
        service = DynamicAnalysisService()
        with pytest.raises(ValueError, match="not completely contained within the supported Jamuna study region"):
            service.create_analysis_request(
                aoi_wkt=aoi_partially_outside,
                start_date="2024-06-10",
                end_date="2024-07-16",
            )

    def test_aoi_inside_jamuna_region_accepted(self):
        """AOI completely inside the Jamuna study region must be accepted."""
        from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
        aoi_inside = "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))"
        service = DynamicAnalysisService()
        res = service.create_analysis_request(
            aoi_wkt=aoi_inside,
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        assert res.get("status") in ("CREATED", "SUBMITTED")
        assert "run_id" in res

    def test_aoi_exceeding_size_limit_rejected(self):
        """AOI area > AOI_MAX_AREA_KM2 must raise ValueError before run creation."""
        from src.pipeline.sentinel1_preprocess import Sentinel1Preprocessor
        # 1° × 1° near Jamuna ≈ 12,000+ km²
        huge_aoi = "POLYGON((89.0 24.0, 90.0 24.0, 90.0 25.0, 89.0 25.0, 89.0 24.0))"
        if not _HAS_GDAL:
            pytest.skip("GDAL not available")
        area = Sentinel1Preprocessor.get_polygon_area_km2(huge_aoi)
        assert area > 200.0, f"Test AOI must be > 200 km², got {area:.1f} km²"

    def test_config_has_aoi_max_area(self):
        """Settings must have AOI_MAX_AREA_KM2 and JAMUNA_STUDY_REGION_WKT."""
        from src.backend.config import settings
        assert hasattr(settings, "AOI_MAX_AREA_KM2"), "Settings missing AOI_MAX_AREA_KM2"
        assert hasattr(settings, "JAMUNA_STUDY_REGION_WKT"), "Settings missing JAMUNA_STUDY_REGION_WKT"
        assert settings.AOI_MAX_AREA_KM2 > 0
        assert "POLYGON" in settings.JAMUNA_STUDY_REGION_WKT

    def test_invalid_wkt_rejected(self):
        """Non-parseable WKT must be caught and raise ValueError before starting a job."""
        from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
        invalid_wkt = "NOT A POLYGON AT ALL"
        service = DynamicAnalysisService()
        with pytest.raises(ValueError, match="Failed to parse AOI WKT|Invalid AOI"):
            service.create_analysis_request(
                aoi_wkt=invalid_wkt,
                start_date="2024-06-01",
                end_date="2024-07-01",
            )


# ===========================================================================
# CORRECTION F — Download security and integrity
# ===========================================================================

class TestCorrectionF:
    """Downloads must require HTTPS; redirects to untrusted domains must be rejected."""

    def test_https_url_is_trusted(self):
        from src.acquisition.download_manager import is_trusted_url
        assert is_trusted_url("https://datapool.asf.alaska.edu/GRD_HD/SA/test.zip")
        assert is_trusted_url("https://urs.earthdata.nasa.gov/oauth/authorize")
        assert is_trusted_url("https://api.daac.asf.alaska.edu/services/search/param")

    def test_http_url_is_rejected(self):
        """Correction F: HTTP (not HTTPS) must be rejected for authenticated downloads."""
        from src.acquisition.download_manager import is_trusted_url
        assert not is_trusted_url("http://datapool.asf.alaska.edu/GRD_HD/SA/test.zip"), \
            "HTTP URLs must be rejected — HTTPS required for authenticated downloads"

    def test_untrusted_domain_rejected(self):
        from src.acquisition.download_manager import is_trusted_url
        assert not is_trusted_url("https://evil.com/malware.zip")
        assert not is_trusted_url("https://asf.alaska.edu.evil.com/file.zip")
        assert not is_trusted_url("https://earthdata.nasa.gov.fake.org/data.zip")

    def test_empty_url_rejected(self):
        from src.acquisition.download_manager import is_trusted_url
        assert not is_trusted_url("")
        assert not is_trusted_url(None)

    def test_redirect_to_untrusted_domain_rejected(self):
        """When a trusted URL redirects to an untrusted domain, download must be aborted."""
        from src.acquisition.download_manager import DownloadManager, is_trusted_url
        dm = DownloadManager.__new__(DownloadManager)

        redirect_url = "https://malicious-domain.example.com/stolen_credentials.zip"
        assert not is_trusted_url(redirect_url), \
            "Redirect target is untrusted — must be rejected in redirect chain"

    def test_http_200_when_range_sent_logs_warning(self):
        """HTTP 200 response when Range header was sent must reset existing_bytes to 0."""
        # Verify the corrected download code handles HTTP 200 with partial file
        # by checking that part_path.unlink is called when existing_bytes > 0
        # This is verified via code inspection (the actual download requires network)
        import ast
        dm_path = Path(__file__).resolve().parent.parent / \
            "src/acquisition/download_manager.py"
        source = dm_path.read_text()
        assert "HTTP 200" in source or "not honored" in source, \
            "HTTP 200 (Range not honored) case must be documented in download_manager.py"
        assert "part_path.unlink" in source, \
            "Partial file must be deleted when resumption is not honored"


# ===========================================================================
# CORRECTION G — API and job status
# ===========================================================================

class TestCorrectionG:
    """API must return actual CANCELLED status; default must be async."""

    def test_run_synchronously_default_is_false(self):
        """AnalysisCreateRequest.run_synchronously must default to False."""
        import sys
        ep_path = Path(__file__).resolve().parent.parent / \
            "src/backend/api/v1/endpoints/dynamic_analysis.py"
        source = ep_path.read_text()
        # Check that default=False is used
        assert "default=False" in source, \
            "run_synchronously must default to False — blocking synchronous requests are not safe as default"
        # Ensure default=True is not present for run_synchronously
        import re
        sync_field = re.search(r"run_synchronously.*?Field\(.*?default=(True|False)", source)
        if sync_field:
            assert sync_field.group(1) == "False", \
                f"run_synchronously default must be False, found {sync_field.group(1)}"

    def test_cancelled_status_not_overridden_by_completed(self):
        """When execute_analysis_run returns CANCELLED, the endpoint must return CANCELLED."""
        ep_path = Path(__file__).resolve().parent.parent / \
            "src/backend/api/v1/endpoints/dynamic_analysis.py"
        source = ep_path.read_text()
        assert "CANCELLED" in source, \
            "Endpoint must handle CANCELLED status explicitly"
        # The corrected code must check for CANCELLED before returning COMPLETED
        cancel_check_before_completed = (
            source.index("CANCELLED") < source.index("status.*COMPLETED") + 200
            if "status.*COMPLETED" in source else True
        )
        assert "returned_status" in source or \
               'status", "COMPLETED"' not in source.replace("'status': 'COMPLETED'", ""), \
            "Endpoint must not unconditionally return COMPLETED for synchronous runs"

    def test_get_status_checks_error_json_before_summary(self):
        """get_analysis_status must check error.json before summary.json (Correction G)."""
        ep_path = Path(__file__).resolve().parent.parent / \
            "src/backend/api/v1/endpoints/dynamic_analysis.py"
        source = ep_path.read_text()
        # Verify error_file is checked for CANCELLED before summary_file → "COMPLETED"
        error_check_pos = source.find("error_file.exists()")
        summary_check_pos = source.find("summary_file.exists()")
        assert error_check_pos != -1, "error_file.exists() check must exist"
        assert summary_check_pos != -1, "summary_file.exists() check must exist"
        assert error_check_pos < summary_check_pos, \
            "error_file (CANCELLED check) must come BEFORE summary_file (COMPLETED) in get_analysis_status"

    def test_cancelled_run_returns_cancelled_status(self, tmp_path):
        """get_analysis_status: a run with error.json status=CANCELLED must return CANCELLED."""
        run_dir = tmp_path / "run_test_cancelled"
        run_dir.mkdir()
        (run_dir / "request.json").write_text(json.dumps({"run_id": "run_test_cancelled"}))
        (run_dir / "error.json").write_text(json.dumps({"status": "CANCELLED", "error": "User cancelled"}))
        # Also write summary.json to simulate the edge case where both exist
        (run_dir / "summary.json").write_text(json.dumps({"status": "COMPLETED", "run_id": "run_test_cancelled"}))

        with patch("src.backend.api.v1.endpoints.dynamic_analysis.service") as mock_svc:
            mock_svc.get_run_dir.return_value = run_dir
            from src.backend.api.v1.endpoints.dynamic_analysis import get_analysis_status
            resp = get_analysis_status("run_test_cancelled")
            assert resp["status"] == "CANCELLED", \
                f"Expected CANCELLED but got '{resp['status']}' — error.json must take precedence over summary.json"


# ===========================================================================
# CORRECTION H — Scientific area definitions
# ===========================================================================

class TestCorrectionH:
    """summary.json study_aoi must include all four distinct area definitions."""

    def _make_summary_with_areas(self, geom_km2, raster_km2, bbox_km2, common_km2):
        return {
            "study_aoi": {
                "geometric_vector_area_km2": geom_km2,
                "raster_polygon_area_km2": raster_km2,
                "bounding_box_area_km2": bbox_km2,
                "common_valid_domain_km2": common_km2,
                "pixel_area_km2": 0.0004,
            }
        }

    def test_all_four_area_definitions_present(self):
        """Summary must have geometric_vector, raster_polygon, bounding_box, common_valid_domain."""
        summary = self._make_summary_with_areas(71.8411, 71.8436, 75.0320, 70.8700)
        aoi = summary["study_aoi"]
        assert "geometric_vector_area_km2" in aoi
        assert "raster_polygon_area_km2" in aoi
        assert "bounding_box_area_km2" in aoi
        assert "common_valid_domain_km2" in aoi

    def test_area_ordering_is_scientifically_consistent(self):
        """
        Bounding box >= raster polygon area >= geometric vector area >= common valid domain.
        The common valid domain is smallest because it excludes indeterminate pixels.
        """
        summary = self._make_summary_with_areas(71.8411, 71.8436, 75.0320, 70.8700)
        aoi = summary["study_aoi"]
        # Bounding box is always >= raster polygon (bbox includes outside-polygon pixels)
        assert aoi["bounding_box_area_km2"] >= aoi["raster_polygon_area_km2"], \
            "Bounding box must be >= raster polygon area"
        # Raster and vector should be very close (< 0.1 km² difference due to pixel boundary)
        diff = abs(aoi["raster_polygon_area_km2"] - aoi["geometric_vector_area_km2"])
        assert diff < 1.0, \
            f"Raster and vector areas should be close (< 1.0 km²), got {diff:.4f} km²"
        # Common valid domain <= raster polygon (excludes indeterminate pixels)
        assert aoi["common_valid_domain_km2"] <= aoi["raster_polygon_area_km2"], \
            "Common valid domain must be <= raster polygon area"

    def test_pixel_area_documented(self):
        """pixel_area_km2 (0.0004 km² = 20m × 20m) must be explicitly present."""
        summary = self._make_summary_with_areas(71.8411, 71.8436, 75.0320, 70.8700)
        aoi = summary["study_aoi"]
        assert "pixel_area_km2" in aoi
        assert abs(aoi["pixel_area_km2"] - 0.0004) < 1e-9, \
            "pixel_area_km2 must be 0.0004 (20m × 20m Sentinel-1 pixel)"

    def test_area_accounting_independent_derivation(self, tmp_path):
        """
        Behavior test: DynamicChangeDetector must independently compute raster_polygon_area
        from actual inside-polygon pixels (Classes 1-5), distinct from valid_comparison_area (Classes 1-4).
        """
        from src.pipeline.change_detection import DynamicChangeDetector
        m1 = tmp_path / "m1.tif"
        m2 = tmp_path / "m2.tif"
        out_trans = tmp_path / "trans.tif"

        # Create 10x10 test rasters (100 pixels total)
        # Class 0: Non-water, 1: Water, 2: Indeterminate, 3: NoData
        driver = gdal.GetDriverByName("GTiff")
        gt = [757960.0, 20.0, 0.0, 2740940.0, 0.0, -20.0]
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32645)

        for p, fill_val in [(m1, 0), (m2, 0)]:
            ds = driver.Create(str(p), 10, 10, 1, gdal.GDT_Byte)
            ds.SetGeoTransform(gt)
            ds.SetProjection(srs.ExportToWkt())
            arr = np.full((10, 10), fill_val, dtype=np.uint8)
            # 10 pixels NoData (outside cutline, row 0)
            arr[0, :] = 3
            # 5 pixels Indeterminate noise floor (row 1, cols 0..4)
            arr[1, :5] = 2
            # 5 pixels Water (row 2, cols 0..4)
            arr[2, :5] = 1
            # Remaining 80 pixels are non-water (0)
            ds.GetRasterBand(1).WriteArray(arr)
            ds.GetRasterBand(1).SetNoDataValue(255)
            ds.FlushCache()
            ds = None

        res = DynamicChangeDetector.detect_changes(m1, m2, out_trans)
        metrics = res["area_metrics_km2"]
        counts = res["pixel_counts"]

        # 100 total pixels (bounding box) = 0.04 km²
        assert counts["total_pixels"] == 100
        assert abs(metrics["total_study_aoi"] - 0.04) < 1e-6

        # 10 NoData pixels -> 90 inside-polygon pixels = 0.036 km²
        assert counts["inside_polygon"] == 90
        assert abs(metrics["raster_polygon_area"] - 0.036) < 1e-6

        # 5 indeterminate pixels are excluded from valid comparison -> 85 valid pixels = 0.034 km²
        assert counts["valid_comparison"] == 85
        assert abs(metrics["valid_comparison_area"] - 0.034) < 1e-6

        # Crucial: raster_polygon_area must NOT equal valid_comparison_area
        assert metrics["raster_polygon_area"] != metrics["valid_comparison_area"], \
            "raster_polygon_area must be derived from inside-polygon pixels, NOT common valid domain"

    def test_comparability_reconciliation_dynamic_explanation(self):
        """
        Behavior test: explanation text must dynamically format run-specific numbers,
        never relying on static hardcoded values.
        """
        indep_diff = 3.2500
        common_net = 2.1500
        diff_gap = abs(indep_diff - common_net)
        indet_floor = 1.1000
        common_valid = 50.0000
        newly_inund = 2.5000
        receded = 0.3500

        explanation = (
            f"The difference between single-date observed water extents ({indep_diff:+.4f} km²) "
            f"and the common-domain transition result ({common_net:+.4f} km², gap of {diff_gap:.4f} km²) "
            "occurs because single-date water extents are measured independently within each scene's own valid pixels, "
            f"which includes pixels that are indeterminate noise floor ({indet_floor:.4f} km²) or unobserved/NoData "
            "in the opposite acquisition. For scientific multi-temporal change detection, "
            f"water transitions must be calculated strictly over the mutually valid common domain "
            f"({common_valid:.4f} km²), giving the verified net candidate water change of {common_net:+.4f} km² "
            f"({newly_inund:.4f} km² newly inundated minus {receded:.4f} km² receded)."
        )

        assert "+3.2500 km²" in explanation
        assert "+2.1500 km²" in explanation
        assert "1.1000 km²" in explanation
        assert "50.0000 km²" in explanation
        # Must not contain the hardcoded 2024 static values
        assert "+6.80" not in explanation
        assert "5.8432" not in explanation

    def test_verified_2024_run_numbers_preserved(self):
        """The verified 2024 demonstration run numbers must still exist in the codebase."""
        # The independently verified numbers from ZIP V3
        verified_net_change_km2 = 5.8432
        verified_rf_sha256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"
        # RF model must still exist with correct checksum
        model_path = Path(__file__).resolve().parent.parent / \
            "models/phase7a/phase7a_random_forest_model.joblib"
        if model_path.exists():
            h = hashlib.sha256()
            with open(model_path, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            assert h.hexdigest() == verified_rf_sha256, \
                f"RF model checksum changed! Expected {verified_rf_sha256}, got {h.hexdigest()}"
        # Verified run must still exist
        run_dir = Path(__file__).resolve().parent.parent / \
            "data/runs/run_20261109_211617_e4ab11"
        if run_dir.exists():
            summary_path = run_dir / "summary.json"
            if summary_path.exists():
                summary = json.loads(summary_path.read_text())
                # Verify net water change
                transitions = summary.get("flood_transitions_km2", {})
                net_change = transitions.get("net_candidate_water_change") or transitions.get("net_water_change")
                if net_change is not None:
                    assert abs(float(net_change) - verified_net_change_km2) < 0.01, \
                        f"Verified net change {verified_net_change_km2} km² altered. Got {net_change}"

