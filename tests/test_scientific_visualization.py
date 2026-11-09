"""
Scientific Visualization and Map Preview Test Suite.
NASA Space Apps Challenge 2026: Dancing with the SARs — Earth Pulse

Validates all 7 visualization requirements:
1. Processed Sentinel-1 radar imagery preview (VV/VH decibel grayscale)
2. Before-and-after candidate water classification maps
3. Color-coded flood-change transition maps with area breakdown
4. Riverbank and channel dynamics visualization
5. Random Forest continuous water-probability raster & preview heatmap
6. Multi-date time-series chart generation
7. Web map APIs: XYZ tiles, downloadable GeoTIFFs, PNG previews, and visual manifest
"""

import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from osgeo import gdal, osr
from fastapi.testclient import TestClient

gdal.UseExceptions()

from src.backend.main import app
from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
from src.pipeline.visualization import (
    ScientificVisualizer,
    COLOR_TRANSITIONS,
    COLOR_WATER_MASK,
)
from src.core.satellite_catalog import JAMUNA_DEFAULT_AOI_WKT

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestScientificVisualization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.service = DynamicAnalysisService()
        cls.test_aoi = "POLYGON((89.60 24.62, 89.66 24.62, 89.66 24.68, 89.60 24.68, 89.60 24.62))"

    def test_01_sar_backscatter_preview_generation(self):
        """1. Generate high-dynamic-range calibrated radar backscatter preview PNG with dB colorbar."""
        sar_tif = PROJECT_ROOT / "data/processed/aligned/june10_aligned.tif"
        self.assertTrue(sar_tif.exists(), "Source SAR raster not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_png = Path(tmpdir) / "preview_sar.png"
            res = ScientificVisualizer.generate_sar_preview(
                sar_tif=sar_tif,
                output_png=out_png,
                title="Sentinel-1 SAR Calibrated Backscatter (June 10)",
                acquisition_time="2024-06-10 12:05:08 UTC",
            )
            self.assertTrue(res.exists())
            self.assertGreater(res.stat().st_size, 50000)

            # Check valid PNG format and dimensions
            with Image.open(res) as img:
                self.assertEqual(img.format, "PNG")
                self.assertGreaterEqual(img.width, 1000)
                self.assertGreaterEqual(img.height, 800)

    def test_02_water_mask_preview_with_quantitative_legend(self):
        """2. Generate categorical water classification map preview with exact area legend."""
        mask_tif = PROJECT_ROOT / "data/processed/phase3a/candidate_masks/june10_lee_5x5_otsu_dual_and.tif"
        self.assertTrue(mask_tif.exists(), "Source water mask not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_png = Path(tmpdir) / "preview_water.png"
            res = ScientificVisualizer.generate_water_mask_preview(
                mask_tif=mask_tif,
                output_png=out_png,
                title="June 10 Candidate Water Classification",
                acquisition_time="2024-06-10",
                water_area_km2=142.3,
                total_area_km2=450.0,
            )
            self.assertTrue(res.exists())
            self.assertGreater(res.stat().st_size, 30000)

            with Image.open(res) as img:
                self.assertEqual(img.format, "PNG")
                self.assertGreaterEqual(img.width, 1000)

    def test_03_flood_transitions_preview_with_reconciliation(self):
        """3. Generate flood transition map preview with 6-class color palette and quantitative statistics."""
        trans_tif = PROJECT_ROOT / "data/processed/phase5/phase5_flood_transitions.tif"
        self.assertTrue(trans_tif.exists(), "Source transition raster not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_png = Path(tmpdir) / "preview_transitions.png"
            area_metrics = {
                "persistent_water": 128.5,
                "newly_inundated": 68.3,
                "receded_water": 13.8,
                "persistent_non_water": 180.2,
                "indeterminate_noise_floor": 22.1,
                "valid_comparison_area": 412.9,
            }
            res = ScientificVisualizer.generate_flood_change_preview(
                trans_tif=trans_tif,
                output_png=out_png,
                title="Jamuna Multitemporal Flood Inundation & Transition Dynamics",
                baseline_date="2024-06-10",
                change_date="2024-07-16",
                area_metrics=area_metrics,
            )
            self.assertTrue(res.exists())
            self.assertGreater(res.stat().st_size, 50000)

            with Image.open(res) as img:
                self.assertEqual(img.format, "PNG")

    def test_04_riverbank_migration_preview(self):
        """4. Generate riverbank and channel dynamics preview map with reach status."""
        trans_tif = PROJECT_ROOT / "data/processed/phase5/phase5_flood_transitions.tif"
        self.assertTrue(trans_tif.exists())

        with tempfile.TemporaryDirectory() as tmpdir:
            out_png = Path(tmpdir) / "preview_riverbank.png"
            meta = {
                "status": "VALID_BRAIDED_REACH",
                "mean_net_migration_m": 42.5,
                "bank_erosion_km2": 5.4,
                "valid_migration_transects": 8,
            }
            res = ScientificVisualizer.generate_riverbank_preview(
                trans_tif=trans_tif,
                riverbank_meta=meta,
                output_png=out_png,
            )
            self.assertTrue(res.exists())
            self.assertGreater(res.stat().st_size, 40000)

    def test_05_rf_probability_preview_and_decision_threshold(self):
        """5. Generate continuous Random Forest water probability preview with decision threshold."""
        prob_tif = PROJECT_ROOT / "data/processed/phase7a/phase7a_july16_water_probability.tif"
        self.assertTrue(prob_tif.exists(), "Source RF probability raster not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_png = Path(tmpdir) / "preview_rf_prob.png"
            res = ScientificVisualizer.generate_rf_probability_preview(
                prob_tif=prob_tif,
                output_png=out_png,
                title="Random Forest Continuous Inundation Probability Map",
                acquisition_time="2024-07-16",
                mean_prob=0.384,
                threshold=0.35,
            )
            self.assertTrue(res.exists())
            self.assertGreater(res.stat().st_size, 50000)

            with Image.open(res) as img:
                self.assertEqual(img.format, "PNG")

    def test_06_timeseries_chart_preview(self):
        """6. Generate multi-date hydrological trajectory chart with net flood delta."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_png = Path(tmpdir) / "preview_chart.png"
            ts_meta = {
                "steps": [
                    {"date": "2024-06-10", "water_area_km2": 142.3},
                    {"date": "2024-06-22", "water_area_km2": 164.7},
                    {"date": "2024-07-04", "water_area_km2": 182.1},
                    {"date": "2024-07-16", "water_area_km2": 196.8},
                ]
            }
            res = ScientificVisualizer.generate_timeseries_chart(
                timeseries_meta=ts_meta,
                output_png=out_png,
                title="Multi-Temporal Water Surface Trajectory (June - July 2024)",
            )
            self.assertTrue(res.exists())
            self.assertGreater(res.stat().st_size, 20000)

            with Image.open(res) as img:
                self.assertEqual(img.format, "PNG")

    def test_07_full_pipeline_run_generates_all_visual_assets(self):
        """7. Full dynamic analysis run produces all 7 required map-ready previews, 2D RF probability raster, and manifest."""
        req = self.service.create_analysis_request(
            aoi_wkt=self.test_aoi,
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = req["run_id"]
        run_dir = self.service.get_run_dir(run_id)

        try:
            summary = self.service.execute_analysis_run(run_id)
            self.assertEqual(summary["status"], "COMPLETED")

            # Check 2D RF probability GeoTIFF
            rf_prob_tif = run_dir / "rasters" / "rf_probability.tif"
            self.assertTrue(rf_prob_tif.exists(), "rf_probability.tif was not created in rasters/")

            ds_prob = gdal.Open(str(rf_prob_tif))
            self.assertIsNotNone(ds_prob)
            arr_prob = ds_prob.GetRasterBand(1).ReadAsArray()
            valid_prob = arr_prob[arr_prob != -9999.0]
            self.assertGreater(len(valid_prob), 0)
            self.assertTrue(np.all((valid_prob >= 0.0) & (valid_prob <= 1.0)))
            ds_prob = None

            # Check all preview PNGs exist and have non-zero content
            previews_dir = run_dir / "previews"
            self.assertTrue(previews_dir.exists())

            expected_previews = [
                "preview_t1_sar.png",
                "preview_t2_sar.png",
                "preview_t1_water.png",
                "preview_t2_water.png",
                "preview_flood_transitions.png",
                "preview_riverbank_migration.png",
                "preview_rf_probability.png",
                "preview_timeseries_chart.png",
            ]
            for p_name in expected_previews:
                p_file = previews_dir / p_name
                self.assertTrue(p_file.exists(), f"Preview file {p_name} missing")
                self.assertGreater(p_file.stat().st_size, 10000, f"Preview file {p_name} is empty")

            # Check visual manifest JSON
            manifest_file = run_dir / "visual_manifest.json"
            self.assertTrue(manifest_file.exists())
            manifest = json.loads(manifest_file.read_text())

            self.assertEqual(manifest["run_id"], run_id)
            self.assertIn("geographic_bounds", manifest)
            self.assertEqual(len(manifest["geographic_bounds"]["epsg4326"]), 4)
            self.assertIn("layers", manifest)
            self.assertGreaterEqual(len(manifest["layers"]), 6)

        finally:
            # Clean up test run from DB and filesystem
            from src.backend.database.database import get_db_connection
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()
            if run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)

    def test_08_api_visual_manifest_endpoint(self):
        """8. API GET /api/v1/runs/{run_id}/visual-manifest returns valid layer metadata and bounds."""
        req = self.service.create_analysis_request(
            aoi_wkt=self.test_aoi,
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = req["run_id"]
        run_dir = self.service.get_run_dir(run_id)

        try:
            self.service.execute_analysis_run(run_id)

            resp = self.client.get(f"/api/v1/runs/{run_id}/visual-manifest")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            self.assertEqual(data["run_id"], run_id)
            self.assertIn("epsg4326", data["geographic_bounds"])
            self.assertIn("layers", data)

            layer_ids = [l["layer_id"] for l in data["layers"]]
            self.assertIn("t1_sar", layer_ids)
            self.assertIn("t2_sar", layer_ids)
            self.assertIn("t1_water", layer_ids)
            self.assertIn("t2_water", layer_ids)
            self.assertIn("transitions", layer_ids)
            self.assertIn("rf_probability", layer_ids)

        finally:
            from src.backend.database.database import get_db_connection
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()
            if run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)

    def test_09_api_preview_png_endpoint(self):
        """9. API GET /api/v1/runs/{run_id}/previews/{asset_name} returns valid PNG byte streams."""
        req = self.service.create_analysis_request(
            aoi_wkt=self.test_aoi,
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = req["run_id"]
        run_dir = self.service.get_run_dir(run_id)

        try:
            self.service.execute_analysis_run(run_id)

            for asset in ["t1_sar", "t1_water", "transitions", "rf_probability", "timeseries_chart"]:
                resp = self.client.get(f"/api/v1/runs/{run_id}/previews/{asset}.png")
                self.assertEqual(resp.status_code, 200, f"Preview failed for {asset}")
                self.assertEqual(resp.headers["content-type"], "image/png")
                self.assertGreater(len(resp.content), 5000)

                # Verify PIL can open image stream
                img = Image.open(io.BytesIO(resp.content))
                self.assertEqual(img.format, "PNG")

        finally:
            from src.backend.database.database import get_db_connection
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()
            if run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)

    def test_10_api_geotiff_download_endpoint(self):
        """10. API GET /api/v1/runs/{run_id}/download/{asset_name} streams downloadable GeoTIFF."""
        req = self.service.create_analysis_request(
            aoi_wkt=self.test_aoi,
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = req["run_id"]
        run_dir = self.service.get_run_dir(run_id)

        try:
            self.service.execute_analysis_run(run_id)

            for asset in ["t1_sar", "transitions", "rf_probability"]:
                resp = self.client.get(f"/api/v1/runs/{run_id}/download/{asset}.tif")
                self.assertEqual(resp.status_code, 200, f"Download failed for {asset}")
                self.assertEqual(resp.headers["content-type"], "image/tiff")
                self.assertIn("attachment", resp.headers.get("content-disposition", ""))
                self.assertGreater(len(resp.content), 1000)

        finally:
            from src.backend.database.database import get_db_connection
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()
            if run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)

    def test_11_dynamic_tile_rendering_all_layers(self):
        """11. API GET /api/v1/runs/{run_id}/tiles/{asset_id}/{z}/{x}/{y}.png renders 256x256 PNGs for all layer types."""
        req = self.service.create_analysis_request(
            aoi_wkt=self.test_aoi,
            start_date="2024-06-10",
            end_date="2024-07-16",
        )
        run_id = req["run_id"]
        run_dir = self.service.get_run_dir(run_id)

        try:
            self.service.execute_analysis_run(run_id)

            # Test tile coordinates over Jamuna area (lon=89.63, lat=24.65)
            # At zoom level 11:
            # x = int((89.63 + 180) / 360 * 2048) = 1533
            # lat_rad = 24.65 * pi / 180 = 0.4302
            # y = int((1 - asinh(tan(lat_rad)) / pi) / 2 * 2048) = 879
            z, x, y = 11, 1533, 879

            tested_layers = ["transitions", "t1_water", "t2_water", "t1_sar", "t2_sar", "rf_probability"]
            for layer in tested_layers:
                resp = self.client.get(f"/api/v1/runs/{run_id}/tiles/{layer}/{z}/{x}/{y}.png")
                self.assertEqual(resp.status_code, 200, f"Tile rendering failed for {layer}")
                self.assertEqual(resp.headers["content-type"], "image/png")

                img = Image.open(io.BytesIO(resp.content))
                self.assertEqual(img.size, (256, 256))
                self.assertEqual(img.format, "PNG")

        finally:
            from src.backend.database.database import get_db_connection
            with get_db_connection() as conn:
                conn.execute("DELETE FROM analysis_runs WHERE run_id = ?", (run_id,))
                conn.commit()
            if run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
