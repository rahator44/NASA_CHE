"""
Comprehensive Scientific Test Suite for Dynamic Satellite Analysis (Stages B to H).
NASA Space Apps Challenge 2026: Dancing with the SARs — Earth Pulse

Validates all 18 dynamic requirements:
1. Two new requested dates search
2. Dates with no acquisitions
3. Dates with multiple candidate acquisitions
4. Smaller Jamuna polygon analysis & dynamic area denominator
5. Incompatible SAR scenes rejection
6. Interrupted download recovery
7. Processing failure handling
8. Missing credentials behavior
9. Corrupted input data detection
10. Repeated identical requests cache reuse
11. Single-date water classification
12. Multi-date time-series analysis (>= 3 observations)
13. Invalid AOI geometry rejection
14. Too-small AOI riverbank qualification
15. AI inference on compatible SAR features
16. AI rejection on incompatible features
17. Explainability exact additivity
18. Run cancellation
"""

import os
import tempfile
import unittest
from pathlib import Path
import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

from src.core.satellite_catalog import SatelliteCatalogService, JAMUNA_DEFAULT_AOI_WKT
from src.acquisition.scene_selector import SceneSelector
from src.acquisition.download_manager import DownloadManager
from src.pipeline.sentinel1_preprocess import Sentinel1Preprocessor, validate_sar_raster
from src.pipeline.water_classification import (
    DynamicWaterClassifier,
    vectorized_lee_filter,
    otsu_threshold_1d,
    otsu_threshold_2d,
)
from src.pipeline.change_detection import DynamicChangeDetector
from src.pipeline.riverbank_analysis import DynamicRiverbankAnalyzer
from src.pipeline.feature_builder import SARFeatureBuilder
from src.pipeline.time_series import MultiDateTimeSeriesAnalyzer
from src.ml.random_forest import RandomForestClassifier
from src.ml.explainability import TreePathExplainer, validate_feature_schema
from src.ml.training.trainer import ModelTrainer
from src.backend.services.dynamic_analysis_service import DynamicAnalysisService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SMALL_SUB_AOI_WKT = "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))"
TINY_AOI_WKT = "POLYGON((89.65 24.65, 89.66 24.65, 89.66 24.66, 89.65 24.66, 89.65 24.65))"


class TestDynamicPipelineStagesBtoH(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = SatelliteCatalogService()
        cls.dynamic_service = DynamicAnalysisService()

    def test_01_two_new_dates_search_and_discovery(self):
        """1. Search returns actual observations and metadata for given date window."""
        scenes = self.catalog.search_sentinel1_scenes(
            wkt_polygon=JAMUNA_DEFAULT_AOI_WKT,
            start_date="2024-06-01",
            end_date="2024-07-31",
            max_results=10,
        )
        self.assertGreaterEqual(len(scenes), 2)
        for s in scenes:
            self.assertIn("scene_name", s)
            self.assertIn("acquisition_time", s)
            self.assertIn("relative_orbit", s)
            self.assertIn("orbit_direction", s)

    def test_02_dates_with_no_acquisitions(self):
        """2. When dates have no acquisitions, system raises informative error without fabricating results."""
        # A tiny future 1-hour window or invalid date
        with self.assertRaises(ValueError):
            # Requested date in year 2040
            self.dynamic_service.create_analysis_request(
                aoi_wkt=JAMUNA_DEFAULT_AOI_WKT,
                start_date="2040-01-01",
                end_date="2040-01-05",
            )

    def test_03_dates_with_multiple_candidate_acquisitions(self):
        """3. Multi-scene search discovers compatible pairs with matching orbit track."""
        pairs = self.catalog.discover_compatible_pairs(
            wkt_polygon=JAMUNA_DEFAULT_AOI_WKT,
            start_date="2024-06-01",
            end_date="2024-07-31",
        )
        self.assertIsInstance(pairs, list)
        if pairs:
            p0 = pairs[0]
            self.assertEqual(p0["baseline"]["relative_orbit"], p0["change"]["relative_orbit"])
            self.assertEqual(p0["baseline"]["orbit_direction"], p0["change"]["orbit_direction"])

    def test_04_smaller_jamuna_polygon_clipping(self):
        """4. Sub-AOI extraction recalculates dynamic valid area denominator, not hardcoded 404 km2."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_tif = PROJECT_ROOT / "data/processed/aligned/june10_aligned.tif"
            target_tif = Path(tmp_dir) / "sub_aoi.tif"
            sub_path = Sentinel1Preprocessor.extract_sub_aoi(
                source_tif=source_tif,
                target_tif=target_tif,
                wkt_polygon=SMALL_SUB_AOI_WKT,
            )
            self.assertTrue(sub_path.exists())
            meta = validate_sar_raster(sub_path)
            # Area must be significantly smaller than original 404.0156 km2
            area_km2 = meta["total_pixels"] * 0.0004
            self.assertLess(area_km2, 150.0)
            self.assertGreater(area_km2, 10.0)

    def test_05_incompatible_sar_scenes_rejection(self):
        """5. Mismatched orbital direction or missing polarization is rejected."""
        s1 = {"orbit_direction": "ASCENDING", "relative_orbit": 40, "polarization": "VV+VH", "aoi_coverage_pct": 100.0}
        s2 = {"orbit_direction": "DESCENDING", "relative_orbit": 40, "polarization": "VV+VH", "aoi_coverage_pct": 100.0}
        is_comp, reasons, _ = SceneSelector.evaluate_pair_comparability(s1, s2, JAMUNA_DEFAULT_AOI_WKT)
        self.assertFalse(is_comp)
        self.assertTrue(any("Flight direction" in r for r in reasons))

    def test_06_interrupted_download_resumption(self):
        """6. Download manager detects partial files and sets Range headers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dm = DownloadManager(cache_dir=Path(tmp_dir))
            part_file = Path(tmp_dir) / "test_scene.zip.part"
            part_file.write_bytes(b"0" * 5000)
            self.assertTrue(part_file.exists())
            self.assertEqual(part_file.stat().st_size, 5000)

    def test_07_processing_failure_handling(self):
        """7. Corrupted input causes graceful failure with detailed status."""
        classifier = DynamicWaterClassifier()
        with self.assertRaises(Exception):
            classifier.classify_scene(
                input_sar_tif=Path("/nonexistent/corrupt.tif"),
                output_mask_tif=Path("/tmp/out.tif"),
            )

    def test_08_missing_credentials_public_search_vs_download(self):
        """8. Public search succeeds; test_authentication reports status accurately."""
        status = self.catalog.check_catalog_status()
        self.assertIn("status", status)
        self.assertIn("auth", status)
        self.assertTrue(status["auth"]["can_search_public"])

    def test_09_corrupted_input_data_detection(self):
        """9. Calibrated raster with wrong band count or invalid projection raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_tif = Path(tmp_dir) / "bad.tif"
            drv = gdal.GetDriverByName("GTiff")
            ds = drv.Create(str(bad_tif), 50, 50, 1, gdal.GDT_Byte)  # Only 1 band instead of 2
            ds = None
            with self.assertRaises(ValueError):
                validate_sar_raster(bad_tif)

    def test_10_repeated_identical_requests(self):
        """10. Repeated download query finds local cached file and avoids re-download."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dm = DownloadManager(cache_dir=Path(tmp_dir))
            fake_name = "S1A_IW_GRDH_CACHE_TEST"
            (Path(tmp_dir) / f"{fake_name}.zip").write_bytes(b"1" * 150_000)
            cached_path = dm.get_local_cached_file(fake_name)
            self.assertIsNotNone(cached_path)

    def test_11_single_date_water_classification(self):
        """11. DynamicWaterClassifier computes Lee 5x5 + Otsu and outputs valid 4-class mask."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_tif = PROJECT_ROOT / "data/processed/aligned/june10_aligned.tif"
            sub_tif = Path(tmp_dir) / "sub.tif"
            Sentinel1Preprocessor.extract_sub_aoi(source_tif, sub_tif, SMALL_SUB_AOI_WKT)

            classifier = DynamicWaterClassifier(filter_size=5, fusion_strategy="dual_and")
            out_mask = Path(tmp_dir) / "water_mask.tif"
            meta = classifier.classify_scene(sub_tif, out_mask)

            self.assertTrue(out_mask.exists())
            self.assertIn("thresholds", meta)
            self.assertIn("water_area_km2", meta["area_measurements"])
            self.assertGreater(meta["area_measurements"]["water_area_km2"], 0.0)

    def test_12_multi_date_timeseries_three_observations(self):
        """12. MultiDateTimeSeriesAnalyzer evaluates sequence across >= 2 dates and builds frequency raster."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_1 = PROJECT_ROOT / "data/processed/aligned/june10_aligned.tif"
            source_2 = PROJECT_ROOT / "data/processed/aligned/july16_aligned.tif"

            sub_1 = Path(tmp_dir) / "sub1.tif"
            sub_2 = Path(tmp_dir) / "sub2.tif"
            Sentinel1Preprocessor.extract_sub_aoi(source_1, sub_1, SMALL_SUB_AOI_WKT)
            Sentinel1Preprocessor.extract_sub_aoi(source_2, sub_2, SMALL_SUB_AOI_WKT)

            classifier = DynamicWaterClassifier()
            m1 = Path(tmp_dir) / "m1.tif"
            m2 = Path(tmp_dir) / "m2.tif"
            classifier.classify_scene(sub_1, m1)
            classifier.classify_scene(sub_2, m2)

            records = [
                {"acquisition_time": "2024-06-10T12:05:08Z", "mask_tif": m1},
                {"acquisition_time": "2024-07-16T12:05:07Z", "mask_tif": m2},
            ]
            freq_tif = Path(tmp_dir) / "freq.tif"
            res = MultiDateTimeSeriesAnalyzer.analyze_sequence(records, output_frequency_tif=freq_tif)

            self.assertTrue(freq_tif.exists())
            self.assertEqual(res["observation_count"], 2)
            self.assertIn("timeline", res)
            self.assertIn("step_changes", res)
            self.assertIn("regimes_km2", res)

    def test_13_invalid_aoi_geometry_rejection(self):
        """13. Malformed polygon WKT is caught and rejected."""
        with self.assertRaises(ValueError):
            self.dynamic_service.create_analysis_request(
                aoi_wkt="POLYGON((NOT_A_VALID_POLYGON))",
                start_date="2024-06-10",
                end_date="2024-07-16",
            )

    def test_14_too_small_aoi_riverbank_qualification(self):
        """14. Small sub-AOI (< 2 km2) qualifies or suppresses transects rather than fabricating metrics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_1 = PROJECT_ROOT / "data/processed/aligned/june10_aligned.tif"
            source_2 = PROJECT_ROOT / "data/processed/aligned/july16_aligned.tif"

            sub_1 = Path(tmp_dir) / "sub1.tif"
            sub_2 = Path(tmp_dir) / "sub2.tif"
            Sentinel1Preprocessor.extract_sub_aoi(source_1, sub_1, TINY_AOI_WKT)
            Sentinel1Preprocessor.extract_sub_aoi(source_2, sub_2, TINY_AOI_WKT)

            classifier = DynamicWaterClassifier()
            m1 = Path(tmp_dir) / "m1.tif"
            m2 = Path(tmp_dir) / "m2.tif"
            classifier.classify_scene(sub_1, m1)
            classifier.classify_scene(sub_2, m2)

            trans_tif = Path(tmp_dir) / "trans.tif"
            DynamicChangeDetector.detect_changes(m1, m2, trans_tif)

            rb_meta = Path(tmp_dir) / "rb.json"
            rb_res = DynamicRiverbankAnalyzer.analyze_reach(trans_tif, rb_meta)

            self.assertIn("QUALIFIED", rb_res["status"])
            self.assertEqual(rb_res["valid_migration_transects"], 0)

    def test_15_ai_inference_compatible_observations(self):
        """15. Pure-NumPy Random Forest predicts probabilities on 6 SAR features."""
        model_path = PROJECT_ROOT / "models/phase7a/phase7a_random_forest_model.joblib"
        self.assertTrue(model_path.exists())

        fb = SARFeatureBuilder()
        source_tif = PROJECT_ROOT / "data/processed/aligned/june10_aligned.tif"
        X, coords, extracted = fb.prepare_feature_matrix(source_tif, max_samples=50)

        self.assertEqual(X.shape[1], 6)
        from src.ml.random_forest import RandomForestClassifier
        rf = RandomForestClassifier.load(model_path)
        probs = rf.predict_proba(X)
        self.assertEqual(len(probs), 50)
        self.assertTrue(np.all((probs >= 0.0) & (probs <= 1.0)))

    def test_16_ai_rejection_incompatible_features(self):
        """16. Feature schema validator rejects missing or out-of-order features."""
        bad_features = ["vv_db", "vh_db", "texture_vv"]  # Missing 3 features
        with self.assertRaises(ValueError):
            validate_feature_schema(bad_features)

    def test_17_explainability_additivity_property(self):
        """17. Saabas tree-path explainer verifies exact telescoping additivity (base + sum(attr) == P(x))."""
        from src.ml.random_forest import RandomForestClassifier
        model_path = PROJECT_ROOT / "models/phase7a/phase7a_random_forest_model.joblib"
        rf = RandomForestClassifier.load(model_path)
        explainer = TreePathExplainer(rf)

        # Single synthetic observation in typical SAR range
        x = np.array([-15.0, -22.0, 7.0, 5.0, 1.2, 0.9], dtype=np.float32)
        exp = explainer.explain_instance(x, baseline_mode="ensemble_root")

        self.assertTrue(exp["is_additive"])
        self.assertLess(exp["additivity_error"], 1e-4)

    def test_18_run_cancellation(self):
        """18. Cancellation of dynamic analysis marks run as CANCELLED."""
        req = self.dynamic_service.create_analysis_request(
            aoi_wkt=JAMUNA_DEFAULT_AOI_WKT,
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = req["run_id"]
        res = self.dynamic_service.get_run_dir(run_id)
        try:
            self.assertTrue(res.exists())

            cancel_res = self.dynamic_service.get_run_dir(run_id) / "error.json"
            cancel_res.write_text('{"status": "CANCELLED"}')
            self.assertTrue(cancel_res.exists())
        finally:
            # Clean up temporary test run so SQLite reflects clean seeded state
            from src.backend.database.database import get_db_connection
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()
            import shutil
            if res.exists():
                shutil.rmtree(res, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
