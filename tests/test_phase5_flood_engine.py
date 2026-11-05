"""
Tests for Phase 5: Final SAR Flood-Change Engine & Inundation Area Accounting.

NASA Space Apps Challenge 2026: Dancing with the SARs
Study Area: Jamuna River reach, Kazipur / Sirajganj, Bangladesh.
"""

import json
import os
from pathlib import Path
import numpy as np
import pytest
from osgeo import gdal

from scripts.run_phase5_flood_engine import create_study_aoi_raster_mask

PROJECT_ROOT = Path("/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR")
METADATA_PATH = PROJECT_ROOT / "data/metadata/phase5_flood_change_report.json"
TRANSITION_TIF = PROJECT_ROOT / "data/processed/phase5/phase5_flood_transitions.tif"
NEW_INUNDATION_TIF = PROJECT_ROOT / "data/processed/phase5/phase5_newly_inundated_candidate.tif"
RECEDED_TIF = PROJECT_ROOT / "data/processed/phase5/phase5_receded_water.tif"
PERSISTENT_WATER_TIF = PROJECT_ROOT / "data/processed/phase5/phase5_persistent_water.tif"
PERSISTENT_NON_WATER_TIF = PROJECT_ROOT / "data/processed/phase5/phase5_persistent_non_water.tif"
INDETERMINATE_TIF = PROJECT_ROOT / "data/processed/phase5/phase5_indeterminate_mask.tif"
GEOJSON_PATH = PROJECT_ROOT / "data/processed/phase5/phase5_major_inundation_clusters.geojson"
CSV_DIR = PROJECT_ROOT / "data/outputs/phase5/statistics"


@pytest.fixture(scope="module")
def phase5_metadata():
    """Load Phase 5 master metadata report."""
    assert METADATA_PATH.exists(), f"Metadata report missing: {METADATA_PATH}"
    with open(METADATA_PATH, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def aoi_mask():
    """Rasterize AOI boolean mask using canonical study area polygon."""
    mask = create_study_aoi_raster_mask(TRANSITION_TIF)
    assert mask.shape == (1393, 1405)
    assert np.sum(mask) == 1010039
    return mask


@pytest.fixture(scope="module")
def transition_raster():
    """Load Phase 5 transition raster array and geotransform."""
    assert TRANSITION_TIF.exists(), f"Transition GeoTIFF missing: {TRANSITION_TIF}"
    ds = gdal.Open(str(TRANSITION_TIF))
    arr = ds.GetRasterBand(1).ReadAsArray()
    geotransform = ds.GetGeoTransform()
    proj = ds.GetProjection()
    ds = None
    return arr, geotransform, proj


class TestPhase5TransitionConservation:
    """Verifies complete spatial cell conservation and mutual exclusivity."""

    def test_aoi_total_cell_conservation(self, transition_raster, aoi_mask):
        arr, _, _ = transition_raster
        aoi_data = arr[aoi_mask]
        valid_aoi_mask = (aoi_data >= 1) & (aoi_data <= 6)
        total_aoi_cells = int(np.sum(valid_aoi_mask))
        assert total_aoi_cells == 1010039, (
            f"Expected AOI total cells to be 1,010,039, found {total_aoi_cells}"
        )

    def test_transition_class_counts_inside_aoi(self, transition_raster, aoi_mask):
        arr, _, _ = transition_raster
        aoi_data = arr[aoi_mask]
        c1 = int(np.sum(aoi_data == 1))
        c2 = int(np.sum(aoi_data == 2))
        c3 = int(np.sum(aoi_data == 3))
        c4 = int(np.sum(aoi_data == 4))
        c5 = int(np.sum(aoi_data == 5))
        c6 = int(np.sum(aoi_data == 6))

        assert c1 == 216595, f"Persistent Water mismatch: {c1} != 216595"
        assert c2 == 146992, f"Newly Inundated mismatch: {c2} != 146992"
        assert c3 == 1634, f"Receded Water mismatch: {c3} != 1634"
        assert c4 == 628515, f"Persistent Non-Water mismatch: {c4} != 628515"
        assert c5 == 16242, f"Indeterminate mismatch: {c5} != 16242"
        assert c6 == 61, f"NoData mismatch: {c6} != 61"

        assert c1 + c2 + c3 + c4 + c5 + c6 == 1010039

    def test_full_scene_cell_conservation(self, transition_raster):
        arr, _, _ = transition_raster
        assert arr.size == 1957165
        c1 = int(np.sum(arr == 1))
        c2 = int(np.sum(arr == 2))
        c3 = int(np.sum(arr == 3))
        c4 = int(np.sum(arr == 4))
        c5 = int(np.sum(arr == 5))
        c6 = int(np.sum(arr == 6))
        assert c1 == 250766
        assert c2 == 200211
        assert c3 == 2145
        assert c4 == 907806
        assert c5 == 18930
        assert c6 == 577307
        assert c1 + c2 + c3 + c4 + c5 + c6 == 1957165

    def test_binary_rasters_mutual_exclusivity(self):
        """Verifies binary transition rasters are non-overlapping and sum to total valid domain."""
        ds_c1 = gdal.Open(str(PERSISTENT_WATER_TIF))
        ds_c2 = gdal.Open(str(NEW_INUNDATION_TIF))
        ds_c3 = gdal.Open(str(RECEDED_TIF))
        ds_c4 = gdal.Open(str(PERSISTENT_NON_WATER_TIF))
        ds_c5 = gdal.Open(str(INDETERMINATE_TIF))

        a1 = ds_c1.GetRasterBand(1).ReadAsArray() == 1
        a2 = ds_c2.GetRasterBand(1).ReadAsArray() == 1
        a3 = ds_c3.GetRasterBand(1).ReadAsArray() == 1
        a4 = ds_c4.GetRasterBand(1).ReadAsArray() == 1
        a5 = ds_c5.GetRasterBand(1).ReadAsArray() == 1

        # Check pairwise non-overlap
        assert not np.any(a1 & a2), "Overlap detected between Persistent Water and Newly Inundated"
        assert not np.any(a1 & a3), "Overlap detected between Persistent Water and Receded Water"
        assert not np.any(a1 & a4), "Overlap detected between Persistent Water and Persistent Non-Water"
        assert not np.any(a2 & a3), "Overlap detected between Newly Inundated and Receded Water"
        assert not np.any(a2 & a4), "Overlap detected between Newly Inundated and Persistent Non-Water"
        assert not np.any(a3 & a4), "Overlap detected between Receded Water and Persistent Non-Water"
        assert not np.any((a1 | a2 | a3 | a4) & a5), "Overlap detected between Valid transitions and Indeterminate"


class TestPhase5InundationAccountingIdentities:
    """Verifies rigorous mathematical accounting and net change identity."""

    def test_net_change_identity(self, phase5_metadata):
        recon = phase5_metadata["transition_accounting"]["net_change_reconciliation"]
        gross_new = recon["gross_candidate_inundation_km2"]
        gross_receded = recon["gross_candidate_recession_km2"]
        net_change = recon["net_candidate_water_area_change_km2"]
        valid_july = recon["valid_july_water_km2"]
        valid_june = recon["valid_june_water_km2"]

        assert pytest.approx(gross_new - gross_receded, 1e-4) == net_change
        assert pytest.approx(valid_july - valid_june, 1e-4) == net_change
        assert recon["mathematical_identity_holds"] is True

    def test_pixel_to_km2_conversion(self, phase5_metadata):
        """Verifies 20m x 20m pixel area exact conversion factor (0.0004 km2/pixel)."""
        new_inundated = phase5_metadata["transition_accounting"]["newly_inundated_candidate"]
        cells = new_inundated["cells"]
        area_km2 = new_inundated["area_km2"]
        area_ha = new_inundated["area_ha"]

        assert cells == 146992
        assert pytest.approx(cells * 0.0004, 1e-4) == area_km2
        assert pytest.approx(area_km2 * 100.0, 1e-4) == area_ha
        assert pytest.approx(area_km2, 1e-4) == 58.7968

    def test_whole_epoch_vs_common_valid_domain_discrepancy(self, phase5_metadata):
        """Audits the +6.3792 km2 discrepancy between whole-epoch and common-domain net change."""
        unmasked_change = phase5_metadata["epoch_statistics"]["whole_epoch_unmasked_change"][
            "net_candidate_water_area_change_km2"
        ]
        common_domain_change = phase5_metadata["transition_accounting"][
            "net_change_reconciliation"
        ]["net_candidate_water_area_change_km2"]
        gap_km2 = phase5_metadata["reconciliation_findings"]["whole_epoch_vs_common_domain_gap_km2"]

        assert pytest.approx(unmasked_change, 1e-4) == 64.5224
        assert pytest.approx(common_domain_change, 1e-4) == 58.1432
        assert pytest.approx(unmasked_change - common_domain_change, 1e-4) == gap_km2
        assert pytest.approx(gap_km2, 1e-4) == 6.3792


class TestPhase5SpatialMetadata:
    """Verifies geospatial raster consistency, projections, and formats."""

    def test_geotiff_spatial_attributes(self, transition_raster):
        arr, geotransform, proj = transition_raster
        assert arr.shape == (1393, 1405), f"Shape mismatch: {arr.shape}"
        assert geotransform[1] == 20.0, f"Pixel width mismatch: {geotransform[1]}"
        assert geotransform[5] == -20.0, f"Pixel height mismatch: {geotransform[5]}"
        assert "32645" in proj or "UTM zone 45N" in proj, f"CRS mismatch: {proj}"

    def test_all_processed_rasters_exist(self, phase5_metadata):
        for rel_path in phase5_metadata["output_files"]["processed_rasters"]:
            full_path = PROJECT_ROOT / rel_path
            assert full_path.exists(), f"Processed raster missing: {full_path}"
            ds = gdal.Open(str(full_path))
            assert ds.RasterXSize == 1405
            assert ds.RasterYSize == 1393
            ds = None


class TestPhase5SpatialClustering:
    """Verifies connected components flood cluster extraction and rankings."""

    def test_cluster_totals(self, phase5_metadata):
        cluster_meta = phase5_metadata["flood_cluster_analysis"]
        assert cluster_meta["total_clusters_identified"] == 3934
        assert cluster_meta["total_inundated_pixels"] == 146992
        assert pytest.approx(cluster_meta["total_inundated_area_km2"], 1e-4) == 58.7968
        assert cluster_meta["major_clusters_count_gte_1ha"] == 306
        assert pytest.approx(cluster_meta["major_clusters_area_km2"], 1e-2) == 55.08
        assert cluster_meta["major_clusters_pct_of_inundation"] > 90.0

    def test_top_ranked_cluster(self, phase5_metadata):
        top_1 = phase5_metadata["flood_cluster_analysis"]["top_10_clusters"][0]
        assert top_1["rank"] == 1
        assert top_1["pixel_count"] == 15950
        assert pytest.approx(top_1["area_ha"], 1e-2) == 638.00
        assert pytest.approx(top_1["area_km2"], 1e-4) == 6.3800
        assert pytest.approx(top_1["pct_of_new_inundation"], 1e-2) == 10.85
        assert top_1["connectivity_rule"] == "8-connectivity"

    def test_geojson_file_structure(self):
        assert GEOJSON_PATH.exists(), f"GeoJSON missing: {GEOJSON_PATH}"
        with open(GEOJSON_PATH, "r") as f:
            data = json.load(f)
        assert data["type"] == "FeatureCollection"
        features = data["features"]
        unique_cids = set(feat["properties"]["cluster_id"] for feat in features)
        assert len(unique_cids) == 306  # Major clusters >= 1.0 ha
        assert len(features) == 1177  # Total polygon components across major clusters
        first_feat = features[0]
        assert "cluster_id" in first_feat["properties"]
        assert first_feat["geometry"]["type"] == "Polygon"


class TestPhase5CsvIntegrity:
    """Verifies that all 6 statistical summary tables are generated and non-empty."""

    @pytest.mark.parametrize("filename", [
        "phase5_transition_matrix.csv",
        "phase5_inundation_area_summary.csv",
        "phase5_epoch_water_area.csv",
        "phase5_cluster_statistics.csv",
        "phase5_uncertainty_summary.csv",
        "phase5_exclusion_summary.csv",
    ])
    def test_csv_exists_and_populated(self, filename):
        path = CSV_DIR / filename
        assert path.exists(), f"CSV file missing: {path}"
        assert path.stat().st_size > 100, f"CSV file appears truncated: {path}"
