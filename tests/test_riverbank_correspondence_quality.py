"""
Regression Test Suite: Conservative Riverbank Channel Correspondence Quality Gate.
NASA Space Apps Challenge 2026: Dancing with the SARs

Verifies:
1. Detached water clusters several kilometers away on floodplains do NOT corrupt
   riverbank displacement measurements or produce false multi-kilometer bank jumps.
2. Genuine corresponding channel boundaries with known physical displacement
   are accurately identified and measured.
3. When channel correspondence fails or reliable transects are insufficient (< 5),
   status is QUALIFIED_UNRELIABLE_TRANSECTS and quantitative metrics are suppressed (None).
4. Historical 2024 scientific baseline figures remain completely untouched.
"""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

from src.pipeline.riverbank_analysis import DynamicRiverbankAnalyzer

gdal.UseExceptions()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_synthetic_transition_tif(
    output_path: Path,
    array: np.ndarray,
    pixel_spacing: float = 20.0,
    origin_x: float = 763000.0,
    origin_y: float = 2732000.0,
):
    """Creates a temporary GeoTIFF with the given 2D array and UTM Zone 45N georeferencing."""
    h, w = array.shape
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(output_path), w, h, 1, gdal.GDT_Byte)
    ds.SetGeoTransform([origin_x, pixel_spacing, 0.0, origin_y, 0.0, -pixel_spacing])
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32645)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(array)
    ds.FlushCache()
    ds = None


class TestRiverbankCorrespondenceQuality(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_01_detached_water_does_not_corrupt_bank_measurements(self):
        """
        Detached floodplain water cluster several km away does NOT generate
        falsely confident multi-kilometer bank migration.
        """
        # Grid: 100 rows x 250 cols at 20m = 2000m north-south x 5000m east-west
        h, w = 100, 250
        # Transition classes:
        # 1: Persistent Water, 2: Newly Inundated, 3: Receded, 4: Persistent Land
        grid = np.full((h, w), 4, dtype=np.uint8)

        # Principal channel: columns 120 to 180 across all rows (width 60 px = 1200m)
        # T1 channel: cols 120 to 180 (Persistent water = 1)
        grid[:, 120:180] = 1

        # Known migration in T2:
        # Left edge shifts outward (erodes left) by 2 pixels (40m): cols 118:120 are Newly Inundated (2)
        grid[:, 118:120] = 2
        # Right edge recedes inward (land accretion) by 2 pixels (40m): cols 178:180 are Receded Water (3)
        grid[:, 178:180] = 3

        # Add a DETACHED water cluster 2.2 kilometers to the west:
        # Columns 10 to 18 (width 8 px = 160m), rows 20 to 40
        # In T1 it was water, in T2 it dried up (Receded Water = 3)
        grid[20:40, 10:18] = 3

        tif_path = self.tmp_path / "detached_test.tif"
        create_synthetic_transition_tif(tif_path, grid)

        meta_path = self.tmp_path / "detached_meta.json"
        res = DynamicRiverbankAnalyzer.analyze_reach(
            transition_tif=tif_path,
            output_metadata_json=meta_path,
            transect_spacing_m=100.0,
        )

        self.assertEqual(res["status"], "ANALYSIS_SUCCESS")
        self.assertGreaterEqual(res["reliable_transects_count"], 5)

        # Expected true displacement:
        # Left bank: T1 was col 120, T2 is col 118 -> disp = (120 - 118) * 20m = +40m
        # Right bank: T1 was col 180, T2 is col 178 -> disp = (178 - 180) * 20m = -40m
        # Detached water at col 10 would have produced apparent disp of (10 - 118) * 20m = -2160m!
        self.assertAlmostEqual(res["mean_left_bank_displacement_m"], 40.0, delta=5.0)
        self.assertAlmostEqual(res["mean_right_bank_displacement_m"], -40.0, delta=5.0)

        # Verify no reliable transect accepted the ~2 km jump
        for t in res["sample_transects"]:
            self.assertLess(abs(t["left_bank_displacement_m"]), 500.0)
            self.assertLess(abs(t["right_bank_displacement_m"]), 500.0)

    def test_02_known_corresponding_displacement(self):
        """Genuine connected channel boundaries with known displacement are accurately measured."""
        h, w = 80, 200
        grid = np.full((h, w), 4, dtype=np.uint8)

        # Main channel:
        # T1: cols 80 to 140 (Persistent water = 1)
        grid[:, 80:140] = 1
        # In T2, river expands rightward by 3 pixels (60m): cols 140:143 are Newly Inundated (2)
        grid[:, 140:143] = 2

        tif_path = self.tmp_path / "known_disp.tif"
        create_synthetic_transition_tif(tif_path, grid)

        res = DynamicRiverbankAnalyzer.analyze_reach(tif_path, transect_spacing_m=100.0)

        self.assertEqual(res["status"], "ANALYSIS_SUCCESS")
        self.assertEqual(res["channel_correspondence_status"], "VERIFIED_CHANNEL_CORRESPONDENCE")
        self.assertAlmostEqual(res["mean_left_bank_displacement_m"], 0.0, delta=1.0)
        self.assertAlmostEqual(res["mean_right_bank_displacement_m"], 60.0, delta=1.0)
        self.assertAlmostEqual(res["max_bank_displacement_m"], 60.0, delta=1.0)

    def test_03_suppresses_metrics_when_channel_correspondence_fails(self):
        """
        When channel correspondence cannot be established or reliable transects < 5,
        status is QUALIFIED_UNRELIABLE_TRANSECTS and quantitative displacement is None.
        """
        h, w = 80, 200
        grid = np.full((h, w), 4, dtype=np.uint8)

        # Create scattered small pools (none forming a continuous channel)
        # Just 3 small ponds
        grid[10:15, 20:25] = 1
        grid[30:35, 80:85] = 1
        grid[50:55, 150:155] = 1

        tif_path = self.tmp_path / "disconnected_pools.tif"
        create_synthetic_transition_tif(tif_path, grid)

        res = DynamicRiverbankAnalyzer.analyze_reach(tif_path)

        # Insufficient channel context or unreliable transects
        self.assertIn("QUALIFIED", res["status"])
        self.assertIsNone(res.get("mean_left_bank_displacement_m"))
        self.assertIsNone(res.get("mean_right_bank_displacement_m"))

    def test_04_historical_2024_demonstration_intact(self):
        """The authoritative historical 2024 demonstration figures remain intact and unmodified."""
        summary_path = PROJECT_ROOT / "data/runs/run_20261110_221732_1f2e94/summary.json"
        self.assertTrue(summary_path.exists())

        summary = json.loads(summary_path.read_text())
        transitions = summary["flood_transitions_km2"]

        self.assertAlmostEqual(transitions["newly_inundated"], 5.9312, places=4)
        self.assertAlmostEqual(transitions["receded_water"], 0.0880, places=4)
        self.assertAlmostEqual(transitions["net_candidate_water_change"], 5.8432, places=4)
        self.assertTrue(summary["flood_reconciliation"]["net_equals_inundation_minus_recession"])
        self.assertEqual(summary["flood_reconciliation"]["net_change_pixels"], 14608)


if __name__ == "__main__":
    unittest.main()

