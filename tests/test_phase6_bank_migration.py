"""
Tests for Phase 6: Riverbank Migration, Channel-Margin Displacement & Erosion Analysis.

NASA Space Apps Challenge 2026: Dancing with the SARs
Study Area: Jamuna River reach, Kazipur / Sirajganj, Bangladesh.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from osgeo import gdal

from scripts.run_phase6_riverbank_migration import (
    AOI_TARGET_CELLS,
    ZONE_MAINLAND_DRY,
    ZONE_PERSISTENT_CHANNEL_WATER,
    ZONE_EXTERNAL_BANK_EROSION,
    ZONE_INTERNAL_CHAR_SUBMERGENCE,
    ZONE_APPARENT_ACCRETION,
    ZONE_PERSISTENT_INTERNAL_CHAR,
    ZONE_FLOODPLAIN_INUNDATION,
    ZONE_INDETERMINATE_NOISE_FLOOR,
    ZONE_NODATA_BORDER,
    create_study_aoi_raster_mask,
)

PROJECT_ROOT = Path("/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR")
METADATA_PATH = PROJECT_ROOT / "data/metadata/phase6_riverbank_migration_report.json"
ZONES_TIF = PROJECT_ROOT / "data/processed/phase6/phase6_channel_change_zones.tif"
EXT_BANK_TIF = PROJECT_ROOT / "data/processed/phase6/phase6_external_bank_erosion_candidate.tif"
CHAR_SUB_TIF = PROJECT_ROOT / "data/processed/phase6/phase6_internal_char_submergence.tif"
ACCRETION_TIF = PROJECT_ROOT / "data/processed/phase6/phase6_channel_contraction_accretion.tif"
FLOODPLAIN_TIF = PROJECT_ROOT / "data/processed/phase6/phase6_disconnected_floodplain_inundation.tif"
BELT_JUNE_TIF = PROJECT_ROOT / "data/processed/phase6/phase6_channel_belt_june.tif"
BELT_JULY_TIF = PROJECT_ROOT / "data/processed/phase6/phase6_channel_belt_july.tif"

TRANSECTS_GEOJSON = PROJECT_ROOT / "data/processed/phase6/phase6_riverbank_transects.geojson"
CENTERLINE_GEOJSON = PROJECT_ROOT / "data/processed/phase6/phase6_provisional_centerline.geojson"
STATS_DIR = PROJECT_ROOT / "data/outputs/phase6/statistics"


@pytest.fixture(scope="module")
def phase6_metadata():
    assert METADATA_PATH.exists(), f"Metadata missing: {METADATA_PATH}"
    with open(METADATA_PATH, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def aoi_mask():
    assert ZONES_TIF.exists(), f"Zones raster missing: {ZONES_TIF}"
    mask = create_study_aoi_raster_mask(ZONES_TIF)
    assert mask.shape == (1393, 1405)
    assert np.sum(mask) == AOI_TARGET_CELLS
    return mask


@pytest.fixture(scope="module")
def zones_array():
    ds = gdal.Open(str(ZONES_TIF))
    arr = ds.GetRasterBand(1).ReadAsArray()
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    ds = None
    return arr, gt, proj


class TestPhase6ChannelZoneConservation:
    """Verifies complete spatial cell conservation and mutual exclusivity of channel zones."""

    def test_aoi_total_cell_conservation(self, zones_array, aoi_mask):
        arr, _, _ = zones_array
        aoi_data = arr[aoi_mask]
        # Codes 0 to 7 are valid AOI classifications, 255 is NoData border inside AOI
        valid_cells = np.sum((aoi_data >= 0) & (aoi_data <= 7))
        nodata_cells = np.sum(aoi_data == ZONE_NODATA_BORDER)
        assert valid_cells + nodata_cells == AOI_TARGET_CELLS
        assert AOI_TARGET_CELLS == 1010039

    def test_phase5_inundation_decomposition_identity(self, phase6_metadata):
        """Verifies exact 3-way decomposition of Phase 5 newly inundated candidate cells."""
        decomp = phase6_metadata["phase5_inundation_decomposition"]
        total_new = decomp["total_new_inundation"]
        n_bank = decomp["external_bank_expansion_cells"]
        n_char = decomp["internal_char_submergence_cells"]
        n_flood = decomp["floodplain_inundation_cells"]

        assert total_new == 146992
        assert n_bank == 54850
        assert n_char == 58025
        assert n_flood == 34117
        assert n_bank + n_char + n_flood == total_new

    def test_west_vs_east_bank_decomposition(self, phase6_metadata):
        decomp = phase6_metadata["phase5_inundation_decomposition"]
        n_bank = decomp["external_bank_expansion_cells"]
        n_west = decomp["west_bank_cells"]
        n_east = decomp["east_bank_cells"]

        assert n_west == 6716
        assert n_east == 48134
        assert n_west + n_east == n_bank

    def test_binary_rasters_mutual_exclusivity(self):
        """Verifies candidate bank erosion, char submergence, accretion, and floodplain masks have zero overlap."""
        ds_b = gdal.Open(str(EXT_BANK_TIF))
        ds_c = gdal.Open(str(CHAR_SUB_TIF))
        ds_a = gdal.Open(str(ACCRETION_TIF))
        ds_f = gdal.Open(str(FLOODPLAIN_TIF))

        a_b = ds_b.GetRasterBand(1).ReadAsArray() == 1
        a_c = ds_c.GetRasterBand(1).ReadAsArray() == 1
        a_a = ds_a.GetRasterBand(1).ReadAsArray() == 1
        a_f = ds_f.GetRasterBand(1).ReadAsArray() == 1

        assert not np.any(a_b & a_c), "Overlap between external bank erosion and char submergence"
        assert not np.any(a_b & a_a), "Overlap between external bank erosion and accretion"
        assert not np.any(a_b & a_f), "Overlap between external bank erosion and floodplain inundation"
        assert not np.any(a_c & a_a), "Overlap between char submergence and accretion"
        assert not np.any(a_c & a_f), "Overlap between char submergence and floodplain inundation"
        assert not np.any(a_a & a_f), "Overlap between accretion and floodplain inundation"


class TestPhase6TransectDisplacementMath:
    """Verifies transect displacement geometry and mathematical consistency."""

    def test_transect_width_expansion_identity(self):
        df = pd.read_csv(STATS_DIR / "phase6_transect_displacement_summary.csv")
        assert len(df) == 154  # 200m baseline transects

        # Invariant: Channel Width Expansion == d_RB + d_LB
        for _, row in df.iterrows():
            d_rb = row["right_bank_displacement_m"]
            d_lb = row["left_bank_displacement_m"]
            w_exp = row["channel_width_expansion_m"]
            w_ju = row["channel_width_june_m"]
            w_jl = row["channel_width_july_m"]

            assert pytest.approx(w_jl - w_ju, 1e-2) == w_exp
            assert pytest.approx(d_rb + d_lb, 1e-2) == w_exp

    def test_transect_summary_statistics(self, phase6_metadata):
        summary = phase6_metadata["transect_displacement_analysis_200m"]
        assert summary["transect_count"] == 154
        assert summary["right_bank"]["median_m"] == 40.0
        assert summary["right_bank"]["max_m"] == 5660.0
        assert summary["left_bank"]["median_m"] == 140.0
        assert summary["left_bank"]["max_m"] == 3580.0
        assert summary["channel_width"]["median_m"] == 320.0

    def test_transect_sensitivity_monotonicity(self):
        df_sens = pd.read_csv(STATS_DIR / "phase6_transect_sensitivity.csv")
        assert len(df_sens) == 4
        # Sampling intervals: 200, 100, 500, 1000
        # Right Bank median displacement remains stable at 40m across all intervals
        for _, row in df_sens.iterrows():
            assert row["right_bank_median_m"] == 40.0


class TestPhase6SpatialMetadataAndVectors:
    """Verifies CRS, affine transform, dimensions, and GeoJSON validity."""

    def test_geotiff_spatial_attributes(self, zones_array):
        arr, gt, proj = zones_array
        assert arr.shape == (1393, 1405)
        assert gt[1] == 20.0
        assert gt[5] == -20.0
        assert "32645" in proj or "UTM zone 45N" in proj

    def test_transect_geojson_features(self):
        assert TRANSECTS_GEOJSON.exists()
        with open(TRANSECTS_GEOJSON, "r") as f:
            data = json.load(f)
        assert data["type"] == "FeatureCollection"
        features = data["features"]
        assert len(features) == 154
        first = features[0]
        assert first["geometry"]["type"] == "LineString"
        assert "right_bank_displacement_m" in first["properties"]
        assert "left_bank_displacement_m" in first["properties"]

    def test_centerline_geojson_features(self):
        assert CENTERLINE_GEOJSON.exists()
        with open(CENTERLINE_GEOJSON, "r") as f:
            data = json.load(f)
        assert data["type"] == "FeatureCollection"
        feat = data["features"][0]
        assert feat["geometry"]["type"] == "LineString"
        coords = feat["geometry"]["coordinates"]
        assert len(coords) > 500


class TestPhase6CsvIntegrity:
    """Verifies that all 5 statistical summary CSV tables exist and are properly populated."""

    @pytest.mark.parametrize("filename", [
        "phase6_transect_displacement_summary.csv",
        "phase6_channel_change_zones.csv",
        "phase6_transect_sensitivity.csv",
        "phase6_bank_displacement_distribution.csv",
        "phase6_floodplain_vs_channel_accounting.csv",
    ])
    def test_csv_exists_and_populated(self, filename):
        path = STATS_DIR / filename
        assert path.exists(), f"CSV file missing: {path}"
        assert path.stat().st_size > 100, f"CSV file truncated: {path}"

