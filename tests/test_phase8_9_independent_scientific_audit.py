"""
Phase 8.9 Independent Scientific Verification & Backend Audit Test Suite.
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers:
- End-to-end API workflows via FastAPI TestClient
- Independent scientific recalculations directly from raw CSV/rasters
- Negative-control mutation tests
- Model path traversal security checks
- Strict dataset ID matching and cryptographic verification invalidation
- Real GDAL Web Mercator tile rendering, boundary masking, palette purity & error observability
"""

import os
import io
import time
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image
from fastapi.testclient import TestClient

from src.backend.main import app
from src.backend import contracts
from src.backend.services.model_service import ModelService
from src.backend.services.dataset_service import DatasetService
from src.backend.services.raster_service import RasterService, RASTER_CATALOG
from src.backend.database.database import get_db_connection
from src.ml.random_forest import RandomForestClassifier
from src.ml.explainability import (
    TreePathExplainer,
    validate_feature_schema,
    AUTHORITATIVE_FEATURE_ORDER,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestPhase89IndependentScientificAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.project_root = PROJECT_ROOT
        cls.model_path = cls.project_root / "models/phase7a/phase7a_random_forest_model.joblib"
        cls.transects_csv = (
            cls.project_root
            / "data/outputs/phase6_1/statistics/phase6_1_transect_displacement_audit.csv"
        )
        cls.samples_csv = (
            cls.project_root
            / "data/outputs/phase7a/statistics/phase7a_training_samples.csv"
        )

        # Assert local existence of required files directly (never silently skip!)
        assert cls.model_path.exists(), f"Model artifact missing at {cls.model_path}"
        assert cls.transects_csv.exists(), f"Transects CSV missing at {cls.transects_csv}"
        assert cls.samples_csv.exists(), f"Samples CSV missing at {cls.samples_csv}"

    # =========================================================================
    # 1. End-to-End API Integration Tests
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
    # 2. Independent Scientific Recalculations from Raw CSVs
    # =========================================================================

    def test_11_independent_recalculation_riverbank_statistics(self):
        """Independent recalculation of riverbank statistics from raw audit CSV matches exactly."""
        self.assertTrue(self.transects_csv.exists(), "Transect audit CSV not found")
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
        self.assertTrue(self.samples_csv.exists(), "Samples CSV missing")
        self.assertTrue(self.model_path.exists(), "Model artifact missing")

        model = RandomForestClassifier.load(str(self.model_path))
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
        """Negative control: model discriminates genuine water vs dry land test samples and detects perturbations."""
        self.assertTrue(self.model_path.exists(), "Model artifact missing")
        self.assertTrue(self.samples_csv.exists(), "Samples CSV missing")

        model = RandomForestClassifier.load(str(self.model_path))
        df = pd.read_csv(self.samples_csv)
        test_df = df[df["split"] == "test"].copy()
        self.assertGreater(len(test_df), 0)

        # Genuine held-out water samples (label == 1) and dry land samples (label == 0)
        water_df = test_df[test_df["label"] == 1]
        land_df = test_df[test_df["label"] == 0]

        self.assertGreater(len(water_df), 0)
        self.assertGreater(len(land_df), 0)

        water_samples = water_df[AUTHORITATIVE_FEATURE_ORDER].values
        land_samples = land_df[AUTHORITATIVE_FEATURE_ORDER].values

        # Predict probability across test samples
        p_water = model.predict_proba(water_samples)[:, 1]
        p_land = model.predict_proba(land_samples)[:, 1]

        # Water samples have significantly higher mean candidate water probability than land
        self.assertGreater(float(np.mean(p_water)), float(np.mean(p_land)))
        # Over 90% of water samples exceed the optimal threshold 0.35 (demonstrating 0.9214 recall)
        self.assertGreater(float(np.mean(p_water >= 0.35)), 0.90)

        # Perturbation test: take a genuine water test sample and perturb its features with dry land values
        water_sample = water_df.iloc[10][AUTHORITATIVE_FEATURE_ORDER].values.astype(float)
        orig_p = float(model.predict_proba(water_sample.reshape(1, -1))[0, 1])

        land_sample = land_df.iloc[10][AUTHORITATIVE_FEATURE_ORDER].values.astype(float)

        # Replace radar backscatter features with land return
        mutated_sample = water_sample.copy()
        mutated_sample[0] = land_sample[0]
        mutated_sample[1] = land_sample[1]
        mutated_p = float(model.predict_proba(mutated_sample.reshape(1, -1))[0, 1])

        # Water probability drops significantly toward dry land probability
        self.assertLess(mutated_p, orig_p)
        self.assertNotEqual(round(orig_p, 4), round(mutated_p, 4))

    def test_14_model_loading_security_path_traversal(self):
        """Model service strictly prevents loading models outside models/phase7a directory."""
        with self.assertRaises(ValueError) as ctx:
            ModelService.load_model("nonexistent_model")
        self.assertIn("not registered", str(ctx.exception))

        # Explicit path traversal tests via ModelService.validate_model_path
        traversal_attempts = [
            Path("../../etc/passwd"),
            Path("/tmp/malicious_model.joblib"),
            self.project_root / "models/phase7a/../../etc/shadow",
            Path("/etc/hosts"),
        ]
        for bad_path in traversal_attempts:
            with self.assertRaises(ValueError) as ctx2:
                ModelService.validate_model_path(bad_path)
            self.assertIn("Security violation", str(ctx2.exception))

    # =========================================================================
    # 4. Strict Dataset ID Validation & Cryptographic Ledger Tests
    # =========================================================================

    def test_15_dataset_exact_id_and_checksum_integrity(self):
        """Dataset service enforces exact dataset IDs and detects checksum mismatches & modifications."""
        # Exact ID lookup succeeds
        res_exact = self.client.get("/api/v1/datasets/s1a_iw_grd_20240610_aligned")
        self.assertEqual(res_exact.status_code, 200)
        data_exact = res_exact.json()
        self.assertEqual(data_exact["dataset_id"], "s1a_iw_grd_20240610_aligned")
        self.assertTrue(data_exact["checksum_verified"])
        self.assertEqual(data_exact["quality_status"], "VERIFIED")

        # Partial substring lookup must return 404 (exact match required)
        res_partial = self.client.get("/api/v1/datasets/s1a")
        self.assertEqual(res_partial.status_code, 404)
        res_partial2 = self.client.get("/api/v1/datasets/20240610")
        self.assertEqual(res_partial2.status_code, 404)

        # Test checksum verification under file modification and mismatch
        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
            tmp.write(b"EarthPulseTestContentOriginal")
            tmp_path = Path(tmp.name)

        try:
            fake_item = {
                "dataset_id": "test_mismatch_dataset",
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            }
            # Manually insert verification with CHECKSUM_MISMATCH
            stat = tmp_path.stat()
            with get_db_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO dataset_verifications
                    (dataset_id, verified_sha256, file_mtime, file_size, verified_at, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, ("test_mismatch_dataset", "badhash", stat.st_mtime, stat.st_size, "2026-01-01T00:00:00Z", "CHECKSUM_MISMATCH"))
                conn.commit()

            verified, qstatus = DatasetService._get_verification_status("test_mismatch_dataset", fake_item, tmp_path)
            self.assertFalse(verified)
            self.assertEqual(qstatus, "CHECKSUM_MISMATCH")

            # Now modify file st_mtime -> status must become UNVERIFIED_MODIFIED
            time.sleep(0.02)
            tmp_path.write_bytes(b"EarthPulseTestContentModifiedData")

            verified_mod, qstatus_mod = DatasetService._get_verification_status("test_mismatch_dataset", fake_item, tmp_path)
            self.assertFalse(verified_mod)
            self.assertEqual(qstatus_mod, "UNVERIFIED_MODIFIED")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            with get_db_connection() as conn:
                conn.execute("DELETE FROM dataset_verifications WHERE dataset_id = ?", ("test_mismatch_dataset",))
                conn.commit()

    # =========================================================================
    # 5. Real GDAL Tile Integration & Failure Observability Tests
    # =========================================================================

    def test_16_real_gdal_tile_rendering_and_palette_integrity(self):
        """GDAL Web Mercator tile rendering correctly handles cutline boundaries and preserves discrete palettes."""
        # 1. Tile 11/1533/878 intersects AOI cutline boundary for phase5_flood_transitions
        res_boundary = self.client.get("/api/v1/tiles/phase5_flood_transitions/11/1533/878.png")
        self.assertEqual(res_boundary.status_code, 200)
        img_boundary = Image.open(io.BytesIO(res_boundary.content))
        self.assertEqual(img_boundary.size, (256, 256))
        arr_boundary = np.array(img_boundary)
        alphas = arr_boundary[:, :, 3]

        # Pixels inside cutline have alpha > 0, pixels outside cutline have alpha == 0
        inside_count = int(np.sum(alphas > 0))
        outside_count = int(np.sum(alphas == 0))
        self.assertGreater(inside_count, 1000)
        self.assertGreater(outside_count, 1000)
        self.assertEqual(inside_count + outside_count, 256 * 256)

        # 2. Out-of-bounds tile (11/1530/878) outside AOI returns 100% transparent PNG
        res_oob = self.client.get("/api/v1/tiles/phase5_flood_transitions/11/1530/878.png")
        self.assertEqual(res_oob.status_code, 200)
        img_oob = Image.open(io.BytesIO(res_oob.content))
        arr_oob = np.array(img_oob)
        self.assertTrue(np.all(arr_oob[:, :, 3] == 0))

        # 3. Categorical color integrity: unique RGBA colors match authoritative palette
        palette_colors = set(tuple(c) for c in RASTER_CATALOG["phase5_flood_transitions"]["palette"].values())
        unique_pixels = set(tuple(p) for p in arr_boundary.reshape(-1, 4))
        for px in unique_pixels:
            self.assertIn(px, palette_colors, f"Color {px} not in authoritative palette!")

    def test_17_tile_failure_observability(self):
        """Tile renderer does not silently mask internal errors or missing files as blank PNGs."""
        # 1. Non-existent asset ID raises ValueError from RasterService and 404 from endpoint
        with self.assertRaises(ValueError):
            RasterService.render_tile("completely_bogus_asset_123", 11, 1533, 878)
        res_404_asset = self.client.get("/api/v1/tiles/completely_bogus_asset_123/11/1533/878.png")
        self.assertEqual(res_404_asset.status_code, 404)

        # 2. Valid asset entry pointing to missing file raises FileNotFoundError from RasterService and 404 from endpoint
        RASTER_CATALOG["test_missing_raster_asset"] = {
            "relative_path": "data/processed/nonexistent_folder/missing.tif",
            "layer_name": "Test Missing",
            "layer_type": "categorical",
            "palette": {0: [0, 0, 0, 0]},
        }
        try:
            with self.assertRaises(FileNotFoundError):
                RasterService.render_tile("test_missing_raster_asset", 11, 1533, 878)
            res_404_missing = self.client.get("/api/v1/tiles/test_missing_raster_asset/11/1533/878.png")
            self.assertEqual(res_404_missing.status_code, 404)
        finally:
            RASTER_CATALOG.pop("test_missing_raster_asset", None)


if __name__ == "__main__":
    unittest.main()
