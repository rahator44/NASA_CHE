"""
Deployment Safety Gates & External Data Root Resolution Tests.
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers:
- Task 1: Public compute execution protection, fail-safe defaults, and bypass rejection.
- Task 2: Centralized external scientific data-root resolution and path traversal security.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.backend.config import Settings, settings
from src.backend.main import app
from src.backend.services.raster_service import RasterService, RASTER_CATALOG
from src.backend.services.vector_service import VectorService, VECTOR_CATALOG
from src.backend.services.dataset_service import DatasetService


class TestDeploymentSafetyGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.live_2025_run_id = "run_20261111_164348_f3c2b8"
        cls.hist_2024_run_id = "run_20261110_221732_1f2e94"

    # =========================================================================
    # Task 1: Fail-Safe Public Compute Protection
    # =========================================================================

    def test_01_missing_env_defaults_to_safe_restricted_execution(self):
        """When DEMO_MODE_RESTRICTED_EXECUTION is unset, Settings must default to True (restricted)."""
        # Test a fresh Settings instance with no env var
        with patch.dict(os.environ, {}, clear=False):
            if "DEMO_MODE_RESTRICTED_EXECUTION" in os.environ:
                del os.environ["DEMO_MODE_RESTRICTED_EXECUTION"]
            fresh_settings = Settings()
            self.assertTrue(
                fresh_settings.DEMO_MODE_RESTRICTED_EXECUTION,
                "DEMO_MODE_RESTRICTED_EXECUTION must default to True when env var is absent.",
            )

    def test_02_public_historical_run_retrieval_succeeds(self):
        """In public demo mode, precomputed historical 2024 run retrieval must succeed."""
        resp = self.client.get(f"/api/v1/runs/{self.hist_2024_run_id}/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["run_id"], self.hist_2024_run_id)
        self.assertAlmostEqual(
            data["flood_transitions_km2"]["net_candidate_water_change"],
            5.8432,
            places=4,
        )

    def test_03_public_january_2025_run_retrieval_succeeds(self):
        """In public demo mode, precomputed genuine January 2025 run retrieval must succeed."""
        resp = self.client.get(f"/api/v1/runs/{self.live_2025_run_id}/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["run_id"], self.live_2025_run_id)
        self.assertAlmostEqual(
            data["flood_transitions_km2"]["net_candidate_water_change"],
            1.0440,
            places=4,
        )

    def test_04_unauthenticated_job_creation_rejected_in_demo_mode(self):
        """In public demo mode, any new job creation via POST /analysis-requests is rejected with 403."""
        orig_val = settings.DEMO_MODE_RESTRICTED_EXECUTION
        try:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = True
            payload = {
                "aoi_wkt": "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))",
                "start_date": "2024-06-10",
                "end_date": "2024-07-16",
                "run_synchronously": False,
            }
            resp = self.client.post("/api/v1/analysis-requests", json=payload)
            self.assertEqual(resp.status_code, 403)
            self.assertIn("restricted in public demo mode", resp.json()["detail"])
        finally:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = orig_val

    def test_05_preapproved_dates_cannot_bypass_demo_restriction(self):
        """Submitting approved historical or 2025 dates still returns 403 in public demo mode."""
        orig_val = settings.DEMO_MODE_RESTRICTED_EXECUTION
        try:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = True
            # Test 2025 preapproved dates
            payload_2025 = {
                "aoi_wkt": "POLYGON((89.65 24.58, 89.75 24.58, 89.75 24.76, 89.65 24.76, 89.65 24.58))",
                "start_date": "2025-01-12",
                "end_date": "2025-01-24",
                "run_synchronously": False,
            }
            resp = self.client.post("/api/v1/analysis-requests", json=payload_2025)
            self.assertEqual(resp.status_code, 403)

            # Test synchronous execution flag cannot bypass restriction
            payload_sync = dict(payload_2025)
            payload_sync["run_synchronously"] = True
            resp_sync = self.client.post("/api/v1/analysis-requests", json=payload_sync)
            self.assertEqual(resp_sync.status_code, 403)
        finally:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = orig_val

    @patch("fastapi.BackgroundTasks.add_task")
    def test_06_private_authenticated_mode_allows_execution(self, mock_add_task):
        """When DEMO_MODE_RESTRICTED_EXECUTION=False (private mode), job creation succeeds."""
        orig_val = settings.DEMO_MODE_RESTRICTED_EXECUTION
        try:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = False
            payload = {
                "aoi_wkt": "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.60, 89.60 24.60))",
                "start_date": "2024-06-10",
                "end_date": "2024-07-16",
                "run_synchronously": False,
            }
            resp = self.client.post("/api/v1/analysis-requests", json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("run_id", data)
            self.assertIn(data["status"], ("CREATED", "SUBMITTED"))
            mock_add_task.assert_called_once()
        finally:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = orig_val

    # =========================================================================
    # Task 2: External Scientific Data-Root Resolution & Security
    # =========================================================================

    def test_07_resolve_data_path_strips_legacy_data_prefix(self):
        """resolve_data_path must strip leading 'data/' without duplicating the folder prefix."""
        test_path = "data/processed/phase5/phase5_flood_transitions.tif"
        resolved = settings.resolve_data_path(test_path)
        expected = settings.DATA_DIR / "processed/phase5/phase5_flood_transitions.tif"
        self.assertEqual(resolved, expected.resolve())
        # Ensure no 'data/data/' duplicate
        self.assertNotIn("data/data", str(resolved))

    def test_08_resolve_data_path_rejects_directory_traversal(self):
        """resolve_data_path must raise ValueError when paths attempt directory traversal."""
        traversal_attempts = [
            "data/../../etc/passwd",
            "../../../etc/shadow",
            "data/outputs/../../../../root/.bashrc",
            "runs/../../../secret.txt",
        ]
        for bad_path in traversal_attempts:
            with self.assertRaises(ValueError, msg=f"Should reject traversal: {bad_path}"):
                settings.resolve_data_path(bad_path)

    def test_09_external_data_root_redirection(self):
        """When DATA_DIR points to an external directory, services locate files there."""
        temp_dir = Path(tempfile.mkdtemp(prefix="earthpulse_test_ext_data_"))
        try:
            # Create external directory structure
            ext_proc = temp_dir / "processed" / "phase5"
            ext_proc.mkdir(parents=True, exist_ok=True)
            mock_tif = ext_proc / "phase5_flood_transitions.tif"
            mock_tif.write_text("DUMMY_RASTER_DATA")

            ext_vec = temp_dir / "outputs" / "phase5" / "maps"
            ext_vec.mkdir(parents=True, exist_ok=True)
            mock_geojson = ext_vec / "phase5_major_inundation_clusters.geojson"
            mock_geojson.write_text('{"type": "FeatureCollection", "features": []}')

            # Temporarily redirect DATA_DIR
            orig_data_dir = settings.DATA_DIR
            try:
                settings.DATA_DIR = temp_dir

                # 1. Test raster path resolution
                resolved_raster = settings.resolve_data_path(
                    "data/processed/phase5/phase5_flood_transitions.tif"
                )
                self.assertEqual(resolved_raster, mock_tif.resolve())
                self.assertTrue(resolved_raster.exists())

                # 2. Test vector path resolution
                resolved_vec = settings.resolve_data_path(
                    "data/outputs/phase5/maps/phase5_major_inundation_clusters.geojson"
                )
                self.assertEqual(resolved_vec, mock_geojson.resolve())
                self.assertTrue(resolved_vec.exists())

                # 3. Test VectorService reads external asset
                res = VectorService.get_vector_geojson("phase5_inundation_clusters")
                self.assertIsNotNone(res)
                vec_data, meta = res
                self.assertEqual(vec_data.get("type"), "FeatureCollection")

            finally:
                settings.DATA_DIR = orig_data_dir
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_10_missing_file_handled_gracefully(self):
        """Missing scientific assets must return None or appropriate errors without unhandled crashes."""
        # Nonexistent asset ID
        missing_vec = VectorService.get_vector_geojson("nonexistent_layer_12345")
        self.assertIsNone(missing_vec)

        # Path traversal in service.get_run_dir raises ValueError
        from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
        with self.assertRaises(ValueError):
            DynamicAnalysisService.get_run_dir("../../etc")

        # Missing preview returns 404
        resp = self.client.get(f"/api/v1/runs/{self.live_2025_run_id}/previews/nonexistent_image.png")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
