"""
Tests for Phase 6.1: Riverbank Geometry Audit, Cross-Phase Reconciliation & Scientific Validation.

NASA Space Apps Challenge 2026: Dancing with the SARs
Study Area: Jamuna River reach, Kazipur / Sirajganj, Bangladesh.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from osgeo import gdal

from scripts.run_phase6_1_audit import (
    AOI_TARGET_CELLS,
    P61_ZONE_MAINLAND_DRY,
    P61_ZONE_PERSISTENT_CHANNEL_WATER,
    P61_ZONE_EXTERNAL_BANK_EXPANSION,
    P61_ZONE_INTERNAL_CHAR_SUBMERGENCE,
    P61_ZONE_CHANNEL_CONTRACTION,
    P61_ZONE_PERSISTENT_INTERNAL_CHAR,
    P61_ZONE_DISCONNECTED_FLOODPLAIN_INUNDATION,
    P61_ZONE_INDETERMINATE_NOISE_FLOOR,
    P61_ZONE_PERSISTENT_FLOODPLAIN_WATER,
    P61_ZONE_RECEDED_FLOODPLAIN_WATER,
    P61_ZONE_PERSISTENT_CHAR_WATER_POND,
    P61_ZONE_NODATA_BORDER,
    create_study_aoi_raster_mask,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
P5_TIF = PROJECT_ROOT / "data/processed/phase5/phase5_flood_transitions.tif"
P6_TIF = PROJECT_ROOT / "data/processed/phase6/phase6_channel_change_zones.tif"
P61_TIF = PROJECT_ROOT / "data/processed/phase6_1/phase6_1_channel_change_zones.tif"
P61_METADATA = PROJECT_ROOT / "data/metadata/phase6_1_riverbank_audit_report.json"
P61_STATS_DIR = PROJECT_ROOT / "data/outputs/phase6_1/statistics"
P61_TRANSECTS_GEOJSON = PROJECT_ROOT / "data/processed/phase6_1/phase6_1_riverbank_transects.geojson"


@pytest.fixture(scope="module")
def aoi_mask():
    assert P61_TIF.exists(), f"Phase 6.1 raster missing: {P61_TIF}"
    mask = create_study_aoi_raster_mask(P61_TIF)
    assert mask.shape == (1393, 1405)
    assert np.sum(mask) == AOI_TARGET_CELLS
    return mask


@pytest.fixture(scope="module")
def phase6_1_metadata():
    assert P61_METADATA.exists(), f"Phase 6.1 metadata missing: {P61_METADATA}"
    with open(P61_METADATA, "r") as f:
        return json.load(f)


class TestPhase61CrossPhaseConservation:
    """Verifies complete spatial cell conservation and cross-tabulation consistency."""

    def test_p61_raster_total_cell_conservation(self, aoi_mask):
        ds = gdal.Open(str(P61_TIF))
        arr = ds.GetRasterBand(1).ReadAsArray()
        aoi_data = arr[aoi_mask]

        valid_aoi = np.sum((aoi_data >= 0) & (aoi_data <= 10))
        nodata_aoi = np.sum(aoi_data == P61_ZONE_NODATA_BORDER)
        assert valid_aoi + nodata_aoi == AOI_TARGET_CELLS
        assert AOI_TARGET_CELLS == 1010039

    def test_crosstab_purity_and_conservation(self, aoi_mask):
        df_ct = pd.read_csv(P61_STATS_DIR / "phase6_1_phase5_phase6_crosstab.csv")
        assert df_ct["pixel_count"].sum() == AOI_TARGET_CELLS

        # Verify newly inundated candidate area strictly decomposes
        new_inundated = df_ct[df_ct["phase5_code"] == 2]
        assert new_inundated["pixel_count"].sum() == 146992
        p6_codes = set(new_inundated["phase6_code"])
        assert p6_codes == {2, 3, 6}

    def test_reconciled_indeterminate_noise_floor_purity(self, aoi_mask):
        """Verifies Phase 5 indeterminate noise floor (16,242 px) is 100% conserved in Zone 7."""
        ds_p5 = gdal.Open(str(P5_TIF))
        p5 = ds_p5.GetRasterBand(1).ReadAsArray()
        ds_p61 = gdal.Open(str(P61_TIF))
        p61 = ds_p61.GetRasterBand(1).ReadAsArray()

        p5_indet = (p5 == 5) & aoi_mask
        assert np.sum(p5_indet) == 16242
        assert np.sum(p61[p5_indet] == P61_ZONE_INDETERMINATE_NOISE_FLOOR) == 16242


class TestPhase61TransectGeometryAndAnomalies:
    """Verifies transect geometry audit, status classification, and mathematical identities."""

    def test_transect_count_and_width_identity(self):
        df = pd.read_csv(P61_STATS_DIR / "phase6_1_transect_displacement_audit.csv")
        assert len(df) == 154

        for _, row in df.iterrows():
            d_rb = row["right_bank_displacement_m"]
            d_lb = row["left_bank_displacement_m"]
            w_exp = row["channel_width_expansion_m"]
            w_ju = row["channel_width_june_m"]
            w_jl = row["channel_width_july_m"]

            assert pytest.approx(w_jl - w_ju, 1e-2) == w_exp
            assert pytest.approx(d_rb + d_lb, 1e-2) == w_exp

    def test_transect_confidence_status_distribution(self):
        df = pd.read_csv(P61_STATS_DIR / "phase6_1_transect_displacement_audit.csv")
        counts = df["confidence_status"].value_counts()

        assert counts["VALID_LOCAL_MIGRATION"] == 122
        assert counts["AMBIGUOUS_EDGE_EFFECT"] == 23
        assert counts["ANABRANCH_ACTIVATION"] == 5
        assert counts["MAJOR_CHANNEL_EXPANSION"] == 4

    def test_northern_edge_anomaly_provenance(self):
        """Verifies the 5,660m right bank displacement occurs exclusively at the northern edge."""
        df = pd.read_csv(P61_STATS_DIR / "phase6_1_transect_displacement_audit.csv")
        max_rb = df.loc[df["right_bank_displacement_m"].idxmax()]

        assert max_rb["right_bank_displacement_m"] == 5660.0
        assert max_rb["confidence_status"] == "AMBIGUOUS_EDGE_EFFECT"
        assert max_rb["raster_row"] < 202

    def test_eastern_anabranch_anomaly_provenance(self):
        """Verifies the 3,580m left bank displacement is classified as seasonal anabranch activation."""
        df = pd.read_csv(P61_STATS_DIR / "phase6_1_transect_displacement_audit.csv")
        max_lb = df.loc[df["left_bank_displacement_m"].idxmax()]

        assert max_lb["left_bank_displacement_m"] == 3580.0
        assert max_lb["confidence_status"] == "ANABRANCH_ACTIVATION"
        assert max_lb["raster_row"] >= 776

    def test_valid_core_displacement_statistics(self):
        df_geom = pd.read_csv(P61_STATS_DIR / "phase6_1_transect_geometry_audit.csv")
        valid_row = df_geom[df_geom["confidence_status"] == "VALID_LOCAL_MIGRATION"].iloc[0]

        assert valid_row["transect_count"] == 122
        assert valid_row["right_bank_median_m"] == 40.0
        assert valid_row["right_bank_max_m"] == 820.0
        assert valid_row["left_bank_median_m"] == 90.0
        assert valid_row["left_bank_max_m"] == 960.0


class TestPhase61UncertaintyAndCausalAudit:
    """Verifies uncertainty budget and evidence classification of causal claims."""

    def test_mdd_threshold(self):
        df_unc = pd.read_csv(P61_STATS_DIR / "phase6_1_uncertainty_summary.csv")
        mdd_row = df_unc[df_unc["error_source"].str.contains("Minimum Detectable Displacement")].iloc[0]
        assert pytest.approx(mdd_row["standard_uncertainty_m"], 1e-1) == 53.92

    def test_causal_claim_audit_verdicts(self):
        df_causal = pd.read_csv(P61_STATS_DIR / "phase6_1_causal_claim_audit.csv")
        verdicts = dict(zip(df_causal["claim_topic"], df_causal["audit_verdict"]))

        assert verdicts["Brahmaputra Right Embankment (BRE) Confinement"] == "UNVERIFIED_HYPOTHESIS"
        assert verdicts["Embankment Breach Assertions"] == "DISPROVED_ASSERTION"
        assert verdicts["July 16 Confirmed Flood Crest"] == "UNVERIFIED_DESIGNATION"
        assert verdicts["Erosion vs. Stage Submergence"] == "SCIENTIFICALLY_AMBIGUOUS"


class TestPhase61SpatialMetadataAndDeliverables:
    """Verifies GeoTIFF and GeoJSON spatial consistency and properties."""

    def test_p61_geotiff_spatial_attributes(self):
        ds = gdal.Open(str(P61_TIF))
        assert ds.RasterXSize == 1405
        assert ds.RasterYSize == 1393
        gt = ds.GetGeoTransform()
        assert gt[1] == 20.0
        assert gt[5] == -20.0
        proj = ds.GetProjection()
        assert "32645" in proj or "UTM zone 45N" in proj

    def test_audited_transects_geojson(self):
        assert P61_TRANSECTS_GEOJSON.exists()
        with open(P61_TRANSECTS_GEOJSON, "r") as f:
            data = json.load(f)
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 154
        feat0 = data["features"][0]
        assert "confidence_status" in feat0["properties"]
        assert "anomaly_type" in feat0["properties"]
        assert "audit_notes" in feat0["properties"]

