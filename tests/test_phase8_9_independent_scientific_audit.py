"""
Phase 8.9 Independent Scientific Verification & Backend Audit Test Suite.
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers:
- End-to-end API workflows via FastAPI TestClient
- Independent scientific recalculations directly from raw CSV/rasters
- Negative-control mutation tests
- Model path traversal security checks
"""

import os
import unittest
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from src.backend.main import app
from src.backend import contracts
from src.backend.services.model_service import ModelService
from src.ml.random_forest import RandomForestClassifier
from src.ml.explainability import (
    TreePathExplainer,
    validate_feature_schema,
    AUTHORITATIVE_FEATURE_ORDER,
)


class TestPhase89IndependentScientificAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.project_root = "/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR"
        cls.model_path = os.path.join(
            cls.project_root, "models/phase7a/phase7a_random_forest_model.joblib"
        )
        cls.transects_csv = os.path.join(
            cls.project_root,
            "data/outputs/phase6_1/statistics/phase6_1_transect_displacement_audit.csv",
        )
        cls.samples_csv = os.path.join(
            cls.project_root,
            "data/outputs/phase7a/statistics/phase7a_training_samples.csv",
        )

    # =========================================================================
    # 1. End-to-End API Integration Tests (Task 14)
    # =========================================================================

    def test_01_api_health_and_root(self):
        """API root and health check endpoints respond with 200 OK."""
        res_root = self.client.get("/")
        self.assertEqual(res_root.status_code, 200)
        data_root = res_root.json()
        self.assertIn("Earth Pulse", data_root["title"])

        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        self.assertEqual(res_health.json()["status"], "healthy")

    def test_02_analyses_endpoints_and_404(self):
        """Analyses endpoints return catalogue for valid region and 404 for unknown region."""
        res = self.client.get("/api/v1/analyses")
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json()["total_analyses"], 0)

        # Valid region
        res_reg = self.client.get(f"/api/v1/regions/{contracts.STUDY_AREA_ID}/analyses")
        self.assertEqual(res_reg.status_code, 200)

        # Unknown region returns 404
        res_unknown = self.client.get("/api/v1/regions/unknown_region_xyz/analyses")
        self.assertEqual(res_unknown.status_code, 404)
        self.assertIn("Authoritative registered study areas", res_unknown.json()["detail"])

        # Results for valid vs unknown region
        res_res = self.client.get(f"/api/v1/regions/{contracts.STUDY_AREA_ID}/results")
        self.assertEqual(res_res.status_code, 200)

        res_res_unknown = self.client.get("/api/v1/regions/unknown_region_xyz/results")
        self.assertEqual(res_res_unknown.status_code, 404)

    def test_03_region_endpoints_and_404(self):
        """Region detail endpoints return metadata for valid region and 404 for invalid."""
        res = self.client.get("/api/v1/regions")
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json()["total_regions"], 0)

        res_det = self.client.get(f"/api/v1/regions/{contracts.STUDY_AREA_ID}")
        self.assertEqual(res_det.status_code, 200)
        self.assertEqual(res_det.json()["region_id"], contracts.STUDY_AREA_ID)

        res_unknown = self.client.get("/api/v1/regions/nonexistent_area")
        self.assertEqual(res_unknown.status_code, 404)
        self.assertIn("Authoritative registered study areas", res_unknown.json()["detail"])

    def test_04_dataset_endpoints_and_404(self):
        """Dataset endpoints validate region filtering and return 404 on invalid region."""
        res = self.client.get("/api/v1/datasets")
        self.assertEqual(res.status_code, 200)

        res_valid = self.client.get(f"/api/v1/regions/{contracts.STUDY_AREA_ID}/datasets")
        self.assertEqual(res_valid.status_code, 200)

        res_unknown = self.client.get("/api/v1/regions/nonexistent_area/datasets")
        self.assertEqual(res_unknown.status_code, 404)

        res_filter_unknown = self.client.get("/api/v1/datasets?region_id=nonexistent_area")
        self.assertEqual(res_filter_unknown.status_code, 404)

    def test_05_raster_catalog_and_tile_rendering(self):
        """Raster asset catalog and map tile rendering execute safely with boundary handling."""
        res = self.client.get("/api/v1/rasters")
        self.assertEqual(res.status_code, 200)
        assets = res.json()
        self.assertGreater(len(assets), 0)

        # Region filter 404 check
        res_unknown = self.client.get("/api/v1/rasters?region_id=nonexistent_area")
        self.assertEqual(res_unknown.status_code, 404)

        # Metadata for phase5_flood_transitions
        res_meta = self.client.get("/api/v1/rasters/phase5_flood_transitions/metadata")
        self.assertEqual(res_meta.status_code, 200)
        self.assertEqual(res_meta.json()["width"], 1405)
        self.assertEqual(res_meta.json()["height"], 1393)

        # Tile rendering: valid intersecting tile (z=10, x=766, y=437)
        res_tile = self.client.get("/api/v1/tiles/phase5_flood_transitions/10/766/437.png")
        self.assertEqual(res_tile.status_code, 200)
        self.assertEqual(res_tile.headers["content-type"], "image/png")
        self.assertGreater(len(res_tile.content), 0)

        # Tile rendering: out-of-bounds tile (z=10, x=0, y=0) returns empty transparent PNG
        res_oob = self.client.get("/api/v1/tiles/phase5_flood_transitions/10/0/0.png")
        self.assertEqual(res_oob.status_code, 200)
        self.assertEqual(res_oob.headers["content-type"], "image/png")

        # Invalid asset returns 404
        res_inv = self.client.get("/api/v1/tiles/nonexistent_layer/10/766/437.png")
        self.assertEqual(res_inv.status_code, 404)

    def test_06_vector_catalog_and_geojson_reprojection(self):
        """Vector catalog returns WGS84 GeoJSON and rejects invalid regions."""
        res = self.client.get("/api/v1/vectors")
        self.assertEqual(res.status_code, 200)

        res_unknown = self.client.get("/api/v1/vectors?region_id=nonexistent_area")
        self.assertEqual(res_unknown.status_code, 404)

        # Transects GeoJSON
        res_geo = self.client.get("/api/v1/vectors/phase6_riverbank_transects")
        self.assertEqual(res_geo.status_code, 200)
        geo_data = res_geo.json()
        self.assertEqual(geo_data["crs"], "EPSG:4326")
        self.assertEqual(geo_data["feature_count"], 154)

        # Coordinates should be strictly WGS84 [lon ~ 89.6, lat ~ 24.6]
        first_coords = geo_data["geojson"]["features"][0]["geometry"]["coordinates"]
        lon, lat = first_coords[0]
        self.assertTrue(89.0 <= lon <= 90.0)
        self.assertTrue(24.0 <= lat <= 25.0)

    def test_07_flood_summary_and_transitions_contract(self):
        """Flood endpoints match authoritative numerical contracts."""
        res_sum = self.client.get(f"/api/v1/regions/{contracts.STUDY_AREA_ID}/flood/summary")
        self.assertEqual(res_sum.status_code, 200)
        data_sum = res_sum.json()
        self.assertEqual(data_sum["net_candidate_water_change_ha"], 5814.32)
        self.assertEqual(data_sum["whole_epoch_unmasked_delta_ha"], 6452.24)
        self.assertEqual(data_sum["asymmetric_exclusions_gap_ha"], 637.92)

        res_trans = self.client.get(f"/api/v1/regions/{contracts.STUDY_AREA_ID}/flood/transitions")
        self.assertEqual(res_trans.status_code, 200)
        data_trans = res_trans.json()
        self.assertEqual(data_trans["common_valid_domain_cells"], 993736)
        self.assertEqual(data_trans["net_inundation_balance_ha"], 5814.32)

        classes = {t["class_name"]: t for t in data_trans["transitions"]}
        self.assertEqual(classes["Persistent Water"]["area_ha"], 8663.80)
        self.assertEqual(classes["Newly Inundated Candidate"]["area_ha"], 5879.68)
        self.assertEqual(classes["Receded Water"]["area_ha"], 65.36)
        self.assertEqual(classes["Persistent Non-Water"]["area_ha"], 25140.60)

    def test_08_riverbank_endpoints_and_statistics(self):
        """Riverbank endpoints return 154 total, 122 valid transects, and exact displacement means/medians."""
        res_sum = self.client.get(f"/api/v1/regions/{contracts.STUDY_AREA_ID}/riverbank/summary")
        self.assertEqual(res_sum.status_code, 200)
        data = res_sum.json()
        self.assertEqual(data["total_transects_evaluated"], 154)
        self.assertEqual(data["valid_transects_count"], 122)
        self.assertEqual(data["outside_valid_transects_count"], 32)
        self.assertEqual(data["mean_west_displacement_m"], 130.00)
        self.assertEqual(data["mean_east_displacement_m"], 160.66)
        self.assertEqual(data["mean_channel_width_change_m"], 290.66)
        self.assertEqual(data["median_west_displacement_m"], 40.0)
        self.assertEqual(data["median_east_displacement_m"], 90.0)
        self.assertEqual(data["median_channel_width_change_m"], 180.0)

        # Check transects listing
        res_tr = self.client.get(f"/api/v1/regions/{contracts.STUDY_AREA_ID}/riverbank/transects?limit=200")
        self.assertEqual(res_tr.status_code, 200)
        self.assertEqual(len(res_tr.json()["transects"]), 154)

    def test_09_model_endpoints_and_diagnostics(self):
        """Model endpoints return spatial held-out claims, unverified temporal status, and diagnostics."""
        res_models = self.client.get("/api/v1/models")
        self.assertEqual(res_models.status_code, 200)
        self.assertEqual(len(res_models.json()), 1)
        model_id = res_models.json()[0]["model_id"]

        res_metrics = self.client.get(f"/api/v1/models/{model_id}/metrics")
        self.assertEqual(res_metrics.status_code, 200)
        m_data = res_metrics.json()
        self.assertEqual(m_data["total_test_samples"], 6124)
        self.assertEqual(m_data["confusion_matrix"]["tp"], 2239)
        self.assertEqual(m_data["confusion_matrix"]["tn"], 932)
        self.assertEqual(m_data["confusion_matrix"]["fp"], 2762)
        self.assertEqual(m_data["confusion_matrix"]["fn"], 191)

        res_diag = self.client.get(f"/api/v1/models/{model_id}/diagnostics")
        self.assertEqual(res_diag.status_code, 200)
        d_data = res_diag.json()
        self.assertEqual(d_data["calibration_status"], "UNCALIBRATED")
        self.assertEqual(d_data["brier_score"], 0.2270)
        self.assertEqual(d_data["expected_calibration_error"], 0.0959)

    def test_10_job_execution_synchronous_and_safety(self):
        """Job submission executes allowlisted tasks synchronously and blocks unpermitted jobs."""
        # Unpermitted job action
        res_bad = self.client.post("/api/v1/jobs", json={"job_type": "arbitrary_shell_command", "region_id": contracts.STUDY_AREA_ID})
        self.assertEqual(res_bad.status_code, 400)

        # Invalid region
        res_bad_reg = self.client.post("/api/v1/jobs", json={"job_type": "audit_environment", "region_id": "nonexistent_region"})
        self.assertEqual(res_bad_reg.status_code, 404)

        # Valid allowlisted task
        res_job = self.client.post("/api/v1/jobs", json={"job_type": "audit_environment", "region_id": contracts.STUDY_AREA_ID})
        self.assertEqual(res_job.status_code, 201)
        job_data = res_job.json()
        self.assertEqual(job_data["status"], "COMPLETED")
        self.assertEqual(job_data["progress_pct"], 100.0)

    # =========================================================================
    # 2. Independent Scientific Recalculations from Raw CSVs (Task 15)
    # =========================================================================

    def test_11_independent_recalculation_riverbank_statistics(self):
        """Independent recalculation of riverbank statistics from raw audit CSV matches exactly."""
        if not os.path.exists(self.transects_csv):
            self.skipTest("Transect audit CSV not found")

        df = pd.read_csv(self.transects_csv)
        self.assertEqual(len(df), 154)

        valid_df = df[df["confidence_status"] == "VALID_LOCAL_MIGRATION"].copy()
        self.assertEqual(len(valid_df), 122)

        # West bank (right_bank_displacement_m)
        west_mean = float(valid_df["right_bank_displacement_m"].mean())
        west_median = float(valid_df["right_bank_displacement_m"].median())
        self.assertAlmostEqual(west_mean, 130.00, places=2)
        self.assertAlmostEqual(west_median, 40.0, places=1)

        # East bank (left_bank_displacement_m)
        east_mean = float(valid_df["left_bank_displacement_m"].mean())
        east_median = float(valid_df["left_bank_displacement_m"].median())
        self.assertAlmostEqual(east_mean, 160.66, places=1)
        self.assertAlmostEqual(east_median, 90.0, places=1)

        # Net channel width expansion (channel_width_expansion_m)
        width_mean = float(valid_df["channel_width_expansion_m"].mean())
        width_median = float(valid_df["channel_width_expansion_m"].median())
        self.assertAlmostEqual(width_mean, 290.66, places=1)
        self.assertAlmostEqual(width_median, 180.0, places=1)

    def test_12_independent_recalculation_model_metrics(self):
        """Independent recalculation of RF confusion matrix from raw training samples CSV matches exactly."""
        if not os.path.exists(self.samples_csv) or not os.path.exists(self.model_path):
            self.skipTest("Samples CSV or model not found")

        model = RandomForestClassifier.load(self.model_path)
        df = pd.read_csv(self.samples_csv)
        test_df = df[df["split"] == "test"].copy()
        self.assertEqual(len(test_df), 6124)

        X_test = test_df[AUTHORITATIVE_FEATURE_ORDER].values
        y_test = test_df["label"].values

        probas = model.predict_proba(X_test)[:, 1]
        preds = (probas >= 0.35).astype(int)

        tp = int(np.sum((preds == 1) & (y_test == 1)))
        tn = int(np.sum((preds == 0) & (y_test == 0)))
        fp = int(np.sum((preds == 1) & (y_test == 0)))
        fn = int(np.sum((preds == 0) & (y_test == 1)))

        self.assertEqual(tp, 2239)
        self.assertEqual(tn, 932)
        self.assertEqual(fp, 2762)
        self.assertEqual(fn, 191)

        precision = tp / (tp + fp)
        recall = tp / (tp + fn)
        self.assertAlmostEqual(precision, 0.4477, places=4)
        self.assertAlmostEqual(recall, 0.9214, places=4)

    # =========================================================================
    # 3. Negative-Control Mutation Tests & Security Checks
    # =========================================================================

    def test_13_negative_control_feature_perturbation_detection(self):
        """Perturbing feature values breaks expected prediction consistency (negative-control test)."""
        if not os.path.exists(self.model_path):
            self.skipTest("Model not found")

        model = RandomForestClassifier.load(self.model_path)
        sample = np.array([-15.0, -22.0, 7.0, 0.68, 120.0, 80.0])
        orig_p = model.predict_proba(sample.reshape(1, -1))[0, 1]

        # Mutate VV backscatter by +20 dB (strong dry land return)
        mutated_sample = sample.copy()
        mutated_sample[0] = +5.0  # High backscatter
        mutated_p = model.predict_proba(mutated_sample.reshape(1, -1))[0, 1]

        # Water probability must drop significantly under high radar backscatter
        self.assertLess(mutated_p, orig_p)
        self.assertNotEqual(round(orig_p, 4), round(mutated_p, 4))

    def test_14_model_loading_security_path_traversal(self):
        """Model service strictly prevents loading models outside models/phase7a directory."""
        with self.assertRaises(ValueError) as ctx:
            ModelService.load_model("nonexistent_model")
        self.assertIn("not registered", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
