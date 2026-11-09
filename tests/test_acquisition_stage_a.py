"""
Unit Tests for Stage A: Dynamic NASA Satellite Data Access & Scene Selection.
NASA Space Apps Challenge 2026: Dancing with the SARs — Earth Pulse
"""

import os
import stat
import tempfile
import unittest
from pathlib import Path

from src.core.earthdata_auth import (
    verify_file_permissions,
    mask_secret,
    _parse_token_from_text,
    get_stored_token,
    audit_earthdata_configuration,
)
from src.acquisition.scene_selector import SceneSelector
from src.acquisition.download_manager import DownloadManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JAMUNA_TEST_AOI_WKT = "POLYGON((89.5 24.3, 89.9 24.3, 89.9 24.8, 89.5 24.8, 89.5 24.3))"


class TestAcquisitionStageA(unittest.TestCase):
    def test_01_token_parsing_and_masking(self):
        """Token parser safely extracts token from KEY=VALUE or raw text, and masks secrets."""
        # Key=Value format
        token_env = "EARTHDATA_TOKEN=my_secret_token_12345"
        self.assertEqual(_parse_token_from_text(token_env), "my_secret_token_12345")

        # Export format
        export_env = "export EARTHDATA_TOKEN=\"quoted_secret_token_abc\""
        self.assertEqual(_parse_token_from_text(export_env), "quoted_secret_token_abc")

        # Direct token
        direct = "raw_bearer_jwt_token_xyz"
        self.assertEqual(_parse_token_from_text(direct), "raw_bearer_jwt_token_xyz")

        # Masking
        masked = mask_secret("super_sensitive_token_98765")
        self.assertTrue(masked.startswith("supe"))
        self.assertTrue(masked.endswith("8765"))
        self.assertNotIn("sensitive", masked)

    def test_02_file_permission_enforcement(self):
        """Sensitive credential files must strictly enforce 0600 permissions."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"SECRET_DATA")
            tmp_path = Path(tmp.name)

        try:
            # Set to 0600 -> valid
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
            valid, msg = verify_file_permissions(tmp_path)
            self.assertTrue(valid)

            # Set to 0644 (world readable) -> invalid
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            valid, msg = verify_file_permissions(tmp_path)
            self.assertFalse(valid)
            self.assertIn("Insecure permissions", msg)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_03_scene_evaluation_and_comparability_rules(self):
        """Scene selector validates orbital comparability, polarization, and AOI overlap."""
        # Baseline scene: Ascending, Track 40, VV+VH, 100% overlap
        scene_1 = {
            "scene_name": "S1A_IW_GRDH_20240610",
            "acquisition_time": "2024-06-10T12:05:08Z",
            "orbit_direction": "ASCENDING",
            "relative_orbit": 40,
            "polarization": "VV+VH",
            "beam_mode": "IW",
            "processing_level": "GRD_HD",
            "aoi_coverage_pct": 100.0,
            "wkt_geometry": "POLYGON((89.0 24.0, 90.0 24.0, 90.0 25.0, 89.0 25.0, 89.0 24.0))",
        }

        # Compatible observation scene: Ascending, Track 40, VV+VH, 100% overlap
        scene_2 = {
            "scene_name": "S1A_IW_GRDH_20240716",
            "acquisition_time": "2024-07-16T12:05:07Z",
            "orbit_direction": "ASCENDING",
            "relative_orbit": 40,
            "polarization": "VV+VH",
            "beam_mode": "IW",
            "processing_level": "GRD_HD",
            "aoi_coverage_pct": 100.0,
            "wkt_geometry": "POLYGON((89.0 24.0, 90.0 24.0, 90.0 25.0, 89.0 25.0, 89.0 24.0))",
        }

        # Incompatible observation scene: DESCENDING, Track 142
        scene_bad_dir = dict(scene_2, orbit_direction="DESCENDING", relative_orbit=142)

        # Incompatible polarization scene: VV only
        scene_bad_pol = dict(scene_2, polarization="VV")

        # Test valid pair
        is_comp, reasons, metrics = SceneSelector.evaluate_pair_comparability(scene_1, scene_2, JAMUNA_TEST_AOI_WKT)
        self.assertTrue(is_comp)
        self.assertEqual(len(reasons), 0)
        self.assertTrue(metrics["track_match"])

        # Test direction mismatch rejection
        is_comp_bad, reasons_bad, _ = SceneSelector.evaluate_pair_comparability(scene_1, scene_bad_dir, JAMUNA_TEST_AOI_WKT)
        self.assertFalse(is_comp_bad)
        self.assertTrue(any("Flight direction mismatch" in r for r in reasons_bad))
        self.assertTrue(any("Relative orbit track mismatch" in r for r in reasons_bad))

        # Test polarization mismatch rejection
        is_comp_pol, reasons_pol, _ = SceneSelector.evaluate_pair_comparability(scene_1, scene_bad_pol, JAMUNA_TEST_AOI_WKT)
        self.assertFalse(is_comp_pol)
        self.assertTrue(any("Dual-polarization mismatch" in r for r in reasons_pol))

    def test_04_download_manager_local_cache_bypass(self):
        """Download manager detects existing local archives and bypasses redundant downloads."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dm = DownloadManager(cache_dir=Path(tmp_dir))

            # Create fake existing archive
            fake_scene = "S1A_IW_GRDH_1SDV_20240610_TEST"
            fake_zip = Path(tmp_dir) / f"{fake_scene}.zip"
            fake_zip.write_bytes(b"0" * 200_000)

            # Query download
            res = dm.download_product(
                url="https://fake.url.com/scene.zip",
                scene_name=fake_scene,
            )
            self.assertTrue(res["success"])
            self.assertTrue(res["cached"])
            self.assertFalse(res["downloaded"])
            self.assertEqual(res["local_path"], str(fake_zip))

    def test_05_snap_installation_and_canonical_graph_xml(self):
        """Verified ESA SNAP gpt executable and canonical 8-node XML preprocessing graph exist."""
        # 1. Canonical graph XML template exists and contains all 8 nodes
        graph_xml_path = PROJECT_ROOT / "graphs/s1_grd_calibration_terrain_correction.xml"
        self.assertTrue(graph_xml_path.exists(), "Canonical SNAP graph XML missing")
        content = graph_xml_path.read_text()
        required_nodes = [
            "Read",
            "Apply-Orbit-File",
            "ThermalNoiseRemoval",
            "Remove-GRD-Border-Noise",
            "Subset",
            "Calibration",
            "Terrain-Correction",
            "Write",
        ]
        for node in required_nodes:
            self.assertIn(f'<node id="{node}">', content)

        # 2. ESA SNAP gpt executable exists on system
        snap_gpt_path = Path(os.environ.get("SNAP_GPT_PATH", "/home/orr/esa-snap/bin/gpt"))
        if not snap_gpt_path.exists():
            import shutil
            gpt_in_path = shutil.which("gpt")
            if not gpt_in_path:
                self.skipTest(f"ESA SNAP gpt binary at {snap_gpt_path} not accessible from current environment/sandbox.")
        self.assertTrue(snap_gpt_path.exists() or shutil.which("gpt"))


if __name__ == "__main__":
    unittest.main()

