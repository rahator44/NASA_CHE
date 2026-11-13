"""
Integration Test Suite: Frontend API Contract Verification.
NASA Space Apps Challenge 2026: Dancing with the SARs

Verifies that the serialized responses for:
- GET /api/v1/runs/{run_id}/summary
- GET /api/v1/runs/{run_id}/visual-manifest
- GET /api/v1/runs/{run_id}/explanations
- GET /api/v1/runs/{run_id}/rasters
match the actual production response schemas, layer IDs, URL templates,
and 6-class flood transition classifications without mock substitutions.
"""

import unittest
from unittest.mock import patch
from pathlib import Path
from fastapi.testclient import TestClient
from src.backend.main import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIVE_RUN_ID = "run_20261111_164348_f3c2b8"


class TestFrontendAPIHandoffContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.run_id = LIVE_RUN_ID

    def test_01_summary_contract(self):
        """GET /runs/{run_id}/summary returns true production summary structure."""
        resp = self.client.get(f"/api/v1/runs/{self.run_id}/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Core schema keys
        required_keys = [
            "run_id",
            "status",
            "completed_at",
            "study_aoi",
            "observations",
            "flood_transitions_km2",
            "flood_reconciliation",
            "comparability_reconciliation",
            "riverbank_dynamics",
            "ai_evaluation",
        ]
        for k in required_keys:
            self.assertIn(k, data, f"Missing key in summary: {k}")

        self.assertEqual(data["run_id"], self.run_id)
        self.assertEqual(data["status"], "COMPLETED")

        # Scientific reconciliation
        transitions = data["flood_transitions_km2"]
        self.assertAlmostEqual(transitions["net_candidate_water_change"], 1.0440, places=4)
        self.assertAlmostEqual(transitions["newly_inundated"], 1.6160, places=4)
        self.assertAlmostEqual(transitions["receded_water"], 0.5720, places=4)
        self.assertTrue(data["flood_reconciliation"]["net_equals_inundation_minus_recession"])

        # Riverbank dynamics
        rb = data["riverbank_dynamics"]
        self.assertIn("channel_correspondence_status", rb)
        self.assertGreaterEqual(rb["valid_migration_transects"], 5)
        self.assertIsNotNone(rb["mean_left_bank_displacement_m"])
        self.assertIsNotNone(rb["mean_right_bank_displacement_m"])

    def test_02_visual_manifest_contract(self):
        """GET /runs/{run_id}/visual-manifest returns true layer catalog & 6-class legend."""
        resp = self.client.get(f"/api/v1/runs/{self.run_id}/visual-manifest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("geographic_bounds", data)
        self.assertIn("layers", data)
        layers = data["layers"]
        self.assertTrue(len(layers) >= 4)

        # Transitions layer check
        trans_layer = next((l for l in layers if l["layer_id"] == "transitions"), None)
        self.assertIsNotNone(trans_layer, "Layer 'transitions' missing in visual manifest")
        self.assertEqual(trans_layer["type"], "raster_categorical")
        self.assertIn("tile_url_template", trans_layer)
        self.assertIn("preview_png_url", trans_layer)
        self.assertIn("download_geotiff_url", trans_layer)

        legend = trans_layer.get("legend", {})
        self.assertEqual(legend.get("type"), "categorical")
        classes = legend.get("classes", [])
        class_values = [c["value"] for c in classes]

        # Must include the real scientific transition classes (1: Persistent Water, 2: Newly Inundated, etc.)
        self.assertIn(1, class_values)
        self.assertIn(2, class_values)
        self.assertIn(3, class_values)
        self.assertIn(4, class_values)
        self.assertIn(5, class_values)
        self.assertIn(6, class_values)  # Outside AOI / NoData (transparent #00000000)

        # RF probability layer check
        rf_layer = next((l for l in layers if l["layer_id"] == "rf_probability"), None)
        self.assertIsNotNone(rf_layer, "Layer 'rf_probability' missing in visual manifest")
        self.assertEqual(rf_layer["type"], "raster_continuous")

    def test_03_explanations_contract(self):
        """GET /runs/{run_id}/explanations returns true Saabas explanation structure."""
        resp = self.client.get(f"/api/v1/runs/{self.run_id}/explanations")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["model_id"], "phase7a_rf_jamuna_v1")
        self.assertTrue(data["additivity_verified"])
        self.assertAlmostEqual(data["mean_water_probability"], 0.532, places=3)
        self.assertIn("sample_explanations", data)

        samples = data["sample_explanations"]
        self.assertGreater(len(samples), 0)
        first = samples[0]
        self.assertIn("base_value", first)
        self.assertIn("prediction_probability", first)
        self.assertIn("attributions", first)
        self.assertIn("additivity_error", first)
        self.assertIn("is_additive", first)
        self.assertTrue(first["is_additive"])
        # Check that error is numerically small
        self.assertLess(first["additivity_error"], 1e-6)

    def test_04_rasters_contract(self):
        """GET /runs/{run_id}/rasters returns asset listing with filename, size, and tile templates."""
        resp = self.client.get(f"/api/v1/runs/{self.run_id}/rasters")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["run_id"], self.run_id)
        self.assertIn("rasters", data)
        raster_ids = [r["asset_id"] for r in data["rasters"]]
        self.assertIn("transition_classes", raster_ids)
        self.assertIn("rf_probability", raster_ids)

    @patch("src.backend.api.v1.endpoints.dynamic_analysis.service.search_scenes")
    @patch("src.backend.api.v1.endpoints.dynamic_analysis.service.discover_pairs")
    def test_05_catalog_search_contract(self, mock_pairs, mock_scenes):
        """POST /catalog/sentinel1/search returns total_scenes, scenes, compatible_pairs_count, compatible_pairs (no invented status/aoi_wkt)."""
        mock_scenes.return_value = [{"scene_id": "S1A_TEST_1"}, {"scene_id": "S1A_TEST_2"}]
        mock_pairs.return_value = [{"t1": "S1A_TEST_1", "t2": "S1A_TEST_2"}]

        payload = {
            "aoi_wkt": "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))",
            "start_date": "2024-06-10",
            "end_date": "2024-07-16",
        }
        resp = self.client.post("/api/v1/catalog/sentinel1/search", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Contract reconciliation A: exact verified keys
        self.assertEqual(data["total_scenes"], 2)
        self.assertEqual(len(data["scenes"]), 2)
        self.assertEqual(data["compatible_pairs_count"], 1)
        self.assertEqual(len(data["compatible_pairs"]), 1)

        # Ensure invented fields are NOT in the serialized top-level response
        self.assertNotIn("status", data)
        self.assertNotIn("aoi_wkt", data)

    @patch("fastapi.BackgroundTasks.add_task")
    def test_06_analysis_requests_contract(self, mock_add_task):
        """POST /analysis-requests returns 200 OK under private/authenticated execution."""
        from src.backend.config import settings
        orig_demo = settings.DEMO_MODE_RESTRICTED_EXECUTION
        try:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = False
            payload = {
                "aoi_wkt": "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))",
                "start_date": "2024-06-10",
                "end_date": "2024-07-16",
                "run_synchronously": False,
            }
            resp = self.client.post("/api/v1/analysis-requests", json=payload)
            # Contract reconciliation B: route returns 200 OK
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("run_id", data)
            self.assertIn("status", data)
            self.assertIn(data["status"], ("CREATED", "SUBMITTED"))
            self.assertIn("request", data)
            self.assertIn("aoi_wkt", data["request"])
            mock_add_task.assert_called_once()
        finally:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = orig_demo

    def test_07_cors_settings_contract(self):
        """Settings.ALLOWED_ORIGINS is configured and respects environment overrides."""
        from src.backend.config import settings
        self.assertTrue(hasattr(settings, "ALLOWED_ORIGINS"))
        self.assertIsInstance(settings.ALLOWED_ORIGINS, list)
        self.assertTrue(len(settings.ALLOWED_ORIGINS) > 0)

    def test_08_demo_mode_restricted_execution(self):
        """In public demo mode (default), job creation is blocked (403) even for historical dates."""
        from src.backend.config import settings
        orig_val = settings.DEMO_MODE_RESTRICTED_EXECUTION
        try:
            settings.DEMO_MODE_RESTRICTED_EXECUTION = True
            # Even a pre-authorized date range cannot trigger new jobs in demo mode
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


if __name__ == "__main__":
    unittest.main()

