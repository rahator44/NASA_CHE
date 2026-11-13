"""
Stage 3 Demo Readiness & Reproducibility Verification Suite.
NASA Space Apps Challenge 2026: Dancing with the SARs

Validates:
1. Two demonstration runs (2024 and 2025) appear in precomputed catalog.
2. 2024 and 2025 summaries load with exact net water change (+5.8432 and +1.0440 km²).
3. Each run's visual manifest resolves to its own assets.
4. Scientific tile rendering produces valid RGBA PNG tiles for all layers.
5. AOI polygon loads and is non-empty.
6. Random Forest metadata is available and protected model SHA-256 matches.
7. Explainable AI endpoint returns genuine saved results with exact tree additivity.
8. Demo-mode execution restrictions are enabled by default and reject unauthenticated compute.
9. No Earthdata credentials are required to view completed demonstration runs.
10. Missing assets/runs return informative HTTP 404 rather than silently substituting other data.
"""

import io
import json
import os
import unittest
from unittest.mock import patch
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from src.backend.config import settings, Settings
from src.backend.main import app
from src.backend.database.database import get_db_connection

RUN_2025 = "run_20261111_164348_f3c2b8"
RUN_2024 = "run_20261110_221732_1f2e94"
PROTECTED_RF_SHA256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"
PROTECTED_SNAP_SHA256 = "c239c2691ebcf45b778e171553c1656f9ce4d4a1dded160d929fa8e73cf316a0"


class TestStage3DemoReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_both_demo_runs_appear_in_catalog(self):
        """1. Verify both 2024 and 2025 demonstration runs appear correctly in SQLite database."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for run_id in [RUN_2024, RUN_2025]:
                cursor.execute("SELECT status, completed_at, outputs FROM analysis_runs WHERE run_id = ?", (run_id,))
                row = cursor.fetchone()
                self.assertIsNotNone(row, f"Run {run_id} missing from analysis_runs table")
                self.assertEqual(row[0], "COMPLETED")
                self.assertIsNotNone(row[1])
                # Ensure no hardcoded developer paths in outputs
                outputs_str = row[2]
                self.assertNotIn("/home/orr", outputs_str)
                self.assertNotIn("/mnt/NewVolume1", outputs_str)

    def test_02_summaries_load_with_exact_invariants(self):
        """2. The 2024 and 2025 summaries load and match validated scientific invariants."""
        # 2025 Live Run
        resp_2025 = self.client.get(f"/api/v1/runs/{RUN_2025}/summary")
        self.assertEqual(resp_2025.status_code, 200)
        s_2025 = resp_2025.json()
        self.assertEqual(s_2025["run_id"], RUN_2025)
        self.assertAlmostEqual(s_2025["flood_transitions_km2"]["net_candidate_water_change"], 1.0440, places=4)
        self.assertEqual(s_2025["riverbank_dynamics"]["reliable_transects_count"], 35)
        self.assertEqual(s_2025["riverbank_dynamics"]["unqualified_transects_count"], 1)

        # 2024 Historical Run
        resp_2024 = self.client.get(f"/api/v1/runs/{RUN_2024}/summary")
        self.assertEqual(resp_2024.status_code, 200)
        s_2024 = resp_2024.json()
        self.assertEqual(s_2024["run_id"], RUN_2024)
        self.assertAlmostEqual(s_2024["flood_transitions_km2"]["net_candidate_water_change"], 5.8432, places=4)

    def test_03_visual_manifests_resolve_to_own_assets(self):
        """3. Each run's visual manifest resolves to its own assets without crossover."""
        for run_id in [RUN_2024, RUN_2025]:
            resp = self.client.get(f"/api/v1/runs/{run_id}/visual-manifest")
            self.assertEqual(resp.status_code, 200)
            manifest = resp.json()
            self.assertEqual(manifest["run_id"], run_id)
            for layer in manifest["layers"]:
                if "tile_url_template" in layer and layer["tile_url_template"]:
                    self.assertIn(f"/api/v1/runs/{run_id}/tiles/", layer["tile_url_template"])
                if "preview_png_url" in layer and layer["preview_png_url"]:
                    self.assertIn(f"/api/v1/runs/{run_id}/previews/", layer["preview_png_url"])

    def test_04_scientific_tiles_render_valid_rgba(self):
        """4. The frontend can fetch scientific tiles and receive valid 256x256 PNGs."""
        z, x, y = 13, 6135, 3517
        layers_to_test = ["transitions", "t1_sar", "t2_sar", "t1_water", "t2_water", "rf_probability"]
        for layer in layers_to_test:
            resp = self.client.get(f"/api/v1/runs/{RUN_2025}/tiles/{layer}/{z}/{x}/{y}.png")
            self.assertEqual(resp.status_code, 200, f"Tile {layer} failed")
            self.assertEqual(resp.headers["content-type"], "image/png")
            img = Image.open(io.BytesIO(resp.content))
            self.assertEqual(img.size, (256, 256))
            self.assertEqual(img.mode, "RGBA")

    def test_05_aoi_polygon_loads(self):
        """5. The AOI polygon loads and is non-empty for both runs."""
        for run_id in [RUN_2024, RUN_2025]:
            resp = self.client.get(f"/api/v1/runs/{run_id}/summary")
            data = resp.json()
            aoi_wkt = data["study_aoi"]["wkt"]
            self.assertTrue(aoi_wkt.startswith("POLYGON"))
            self.assertIn("89.60", aoi_wkt)
            self.assertIn("24.60", aoi_wkt)

            # Check GeoJSON vector endpoint as well
            vec_resp = self.client.get(f"/api/v1/runs/{run_id}/vectors/newly_inundated")
            self.assertEqual(vec_resp.status_code, 200)
            geojson = vec_resp.json()
            self.assertEqual(geojson["type"], "FeatureCollection")
            self.assertGreater(len(geojson["features"]), 0)

    def test_06_random_forest_metadata_and_checksum(self):
        """6. Random Forest metadata is available and protected model SHA-256 matches."""
        import hashlib
        model_path = settings.MODELS_DIR / "phase7a" / "phase7a_random_forest_model.joblib"
        self.assertTrue(model_path.exists(), f"Model missing at {model_path}")

        h = hashlib.sha256()
        with open(model_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        self.assertEqual(h.hexdigest(), PROTECTED_RF_SHA256)

        # Check SNAP graph checksum
        graph_path = settings.PROJECT_ROOT_DIR / "graphs" / "s1_grd_calibration_terrain_correction.xml"
        self.assertTrue(graph_path.exists(), f"SNAP graph missing at {graph_path}")
        h_snap = hashlib.sha256()
        with open(graph_path, "rb") as f:
            while chunk := f.read(65536):
                h_snap.update(chunk)
        self.assertEqual(h_snap.hexdigest(), PROTECTED_SNAP_SHA256)

    def test_07_xai_endpoint_returns_genuine_attributions(self):
        """7. Explainable AI endpoint returns genuine saved results with exact tree additivity."""
        resp = self.client.get(f"/api/v1/runs/{RUN_2025}/explanations")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["model_id"], "phase7a_rf_jamuna_v1")
        self.assertTrue(data["additivity_verified"])
        self.assertGreaterEqual(len(data["sample_explanations"]), 5)

        for expl in data["sample_explanations"]:
            base = expl["base_value"]
            pred = expl["prediction_probability"]
            attrs = expl["attributions"]
            self.assertEqual(len(attrs), 6)
            total = base + sum(attrs.values())
            self.assertAlmostEqual(total, pred, places=5)

    def test_08_demo_mode_restrictions_enabled_by_default(self):
        """8. Demo-mode execution restrictions remain enabled by default and reject unauthenticated jobs."""
        self.assertTrue(settings.DEMO_MODE_RESTRICTED_EXECUTION)
        req_body = {
            "mode": "two_date_comparison",
            "aoi_wkt": "POLYGON((89.60 24.60, 89.68 24.60, 89.68 24.68, 89.60 24.68, 89.60 24.60))",
            "start_date": "2025-01-12",
            "end_date": "2025-01-24",
            "satellite_acquisitions": ["2025-01-12", "2025-01-24"],
        }
        resp = self.client.post("/api/v1/analysis-requests", json=req_body)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("restricted in public demo mode", resp.json()["detail"])

    def test_09_no_earthdata_credentials_needed_for_demo(self):
        """9. No Earthdata credentials are required to view completed demonstration results."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EARTHDATA_USERNAME", None)
            os.environ.pop("EARTHDATA_PASSWORD", None)
            resp_s = self.client.get(f"/api/v1/runs/{RUN_2025}/summary")
            self.assertEqual(resp_s.status_code, 200)
            resp_m = self.client.get(f"/api/v1/runs/{RUN_2025}/visual-manifest")
            self.assertEqual(resp_m.status_code, 200)

    def test_10_missing_assets_return_404_no_silent_substitution(self):
        """10. Missing assets or runs return informative HTTP 404 rather than silently substituting data."""
        # Non-existent run
        resp_fake = self.client.get("/api/v1/runs/nonexistent_run_999999/summary")
        self.assertEqual(resp_fake.status_code, 404)
        self.assertIn("nonexistent_run_999999", resp_fake.json()["detail"])

        # Non-existent layer tile
        resp_fake_tile = self.client.get(f"/api/v1/runs/{RUN_2025}/tiles/nonexistent_layer/13/6135/3517.png")
        self.assertEqual(resp_fake_tile.status_code, 404)

        # Non-existent preview
        resp_fake_prev = self.client.get(f"/api/v1/runs/{RUN_2025}/previews/nonexistent_preview.png")
        self.assertEqual(resp_fake_prev.status_code, 404)


if __name__ == "__main__":
    unittest.main()
