"""
Phase 8.4 Source-Backed Backend Corrections Regression Suite
NASA Space Apps Challenge 2026: Dancing with the SARs

Validates the 15 critical data-contract and service corrections identified during
independent external review of the Earth Pulse backend.
"""

import pytest
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.services.raster_service import RASTER_CATALOG


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# Scenario 1: Common-Valid-Domain Surface Water Transition Accounting
# ==============================================================================
def test_01_common_valid_domain_flood_transitions(client):
    """Verifies Common-Valid-Domain transition counts match phase5_inundation_area_summary.csv."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/flood/transitions")
    assert response.status_code == 200
    data = response.json()

    assert data["region_id"] == "jamuna_sirajganj"
    assert data["common_valid_domain_cells"] == 993_736
    assert data["common_valid_domain_ha"] == 39_749.44
    assert data["common_valid_domain_km2"] == 397.4944
    assert data["net_inundation_balance_ha"] == 5_814.32

    transitions = {t["class_id"]: t for t in data["transitions"]}

    # Class 1: Persistent Water
    assert transitions[1]["pixel_count"] == 216_595
    assert transitions[1]["area_ha"] == 8_663.80
    assert transitions[1]["area_km2"] == 86.6380
    assert abs(transitions[1]["percentage_of_valid_domain"] - 21.7960) < 0.01

    # Class 2: Newly Inundated Candidate
    assert transitions[2]["pixel_count"] == 146_992
    assert transitions[2]["area_ha"] == 5_879.68
    assert transitions[2]["area_km2"] == 58.7968
    assert abs(transitions[2]["percentage_of_valid_domain"] - 14.7919) < 0.01

    # Class 3: Receded Water
    assert transitions[3]["pixel_count"] == 1_634
    assert transitions[3]["area_ha"] == 65.36
    assert transitions[3]["area_km2"] == 0.6536
    assert abs(transitions[3]["percentage_of_valid_domain"] - 0.1644) < 0.01

    # Class 4: Persistent Non-Water
    assert transitions[4]["pixel_count"] == 628_515
    assert transitions[4]["area_ha"] == 25_140.60
    assert transitions[4]["area_km2"] == 251.4060
    assert abs(transitions[4]["percentage_of_valid_domain"] - 63.2477) < 0.01


# ==============================================================================
# Scenario 2: Whole-Epoch Unmasked Delta vs Common-Valid-Domain Reconciliation
# ==============================================================================
def test_02_whole_epoch_delta_vs_common_valid_reconciliation(client):
    """Verifies net change (5,814.32 ha) vs whole-epoch unmasked delta (6,452.24 ha) and gap (637.92 ha)."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/flood/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["net_candidate_water_change_ha"] == 5_814.32
    assert data["net_candidate_water_change_km2"] == 58.1432
    assert data["whole_epoch_unmasked_delta_ha"] == 6_452.24
    assert data["whole_epoch_unmasked_delta_km2"] == 64.5224
    assert data["asymmetric_exclusions_gap_ha"] == 637.92
    assert "637.92 ha" in data["accounting_note"]
    assert "common valid domain" in data["accounting_note"].lower()


# ==============================================================================
# Scenario 3: Flood Summary Terminology and Hydrological Condition
# ==============================================================================
def test_03_flood_summary_terminology_and_dates(client):
    """Verifies July observation is labeled flood-period observation, not peak crest of season."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/flood/summary")
    assert response.status_code == 200
    data = response.json()

    pre = data["pre_monsoon_epoch"]
    assert "Pre-Monsoon Baseflow" in pre["epoch_name"]
    assert pre["acquisition_date"].startswith("2024-06-10")
    assert pre["candidate_water_cells"] == 218_229
    assert pre["candidate_water_area_ha"] == 8_729.16

    obs = data["flood_observation_epoch"]
    assert "Monsoon Flood-Period Observation" in obs["epoch_name"]
    assert obs["acquisition_date"].startswith("2024-07-16")
    assert obs["candidate_water_cells"] == 363_587
    assert obs["candidate_water_area_ha"] == 14_543.48
    assert "Not Annual Peak Crest" in obs["hydrological_condition"]


# ==============================================================================
# Scenario 4: Riverbank Transects Audited Counts (154 evaluated, 122 valid, 32 outside)
# ==============================================================================
def test_04_riverbank_transects_audited_counts(client):
    """Verifies 154 evaluated, 122 valid local migration, and 32 outside valid-local transects."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["total_transects_evaluated"] == 154
    assert data["valid_transects_count"] == 122
    assert data["outside_valid_transects_count"] == 32
    assert data["ambiguous_transects_count"] == 32
    assert abs(data["valid_transect_fraction_pct"] - 79.22) < 0.05

    # only_valid = true returns exactly 122
    r_valid = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/transects?only_valid=true&limit=200")
    assert r_valid.status_code == 200
    d_valid = r_valid.json()
    assert d_valid["valid_count"] == 122
    assert len(d_valid["transects"]) == 122
    assert all(t["is_valid"] is True for t in d_valid["transects"])

    # only_valid = false returns all 154 evaluated transects
    r_all = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/transects?only_valid=false&limit=200")
    assert r_all.status_code == 200
    d_all = r_all.json()
    assert d_all["total_count"] == 154
    assert len(d_all["transects"]) == 154


# ==============================================================================
# Scenario 5: Transect Field Naming - chainage_m
# ==============================================================================
def test_05_transect_field_naming_chainage(client):
    """Verifies chainage_m is populated from phase6_1_transect_displacement_audit.csv."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/transects?limit=10")
    assert response.status_code == 200
    data = response.json()

    transects = data["transects"]
    assert len(transects) >= 1
    t0 = transects[0]
    assert "chainage_m" in t0
    assert isinstance(t0["chainage_m"], (int, float))
    assert t0["chainage_m"] >= 0.0


# ==============================================================================
# Scenario 6: Spatial Block Bootstrap 95% Confidence Intervals
# ==============================================================================
def test_06_spatial_bootstrap_confidence_intervals(client):
    """Verifies 95% spatial bootstrap intervals are used instead of empirical [P10, P90]."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/displacement")
    assert response.status_code == 200
    data = response.json()

    west = data["west_bank_expansion_stats"]
    east = data["east_bank_expansion_stats"]
    width = data["net_channel_width_change_stats"]

    # West median 95% CI is [20.0, 80.0]
    assert west["bootstrap_ci_95"] == [20.0, 80.0]
    assert west["p10_m"] == 0.0
    assert west["p90_m"] == 440.0
    assert west["bootstrap_ci_95"] != [west["p10_m"], west["p90_m"]]

    # East median 95% CI is [20.0, 150.0]
    assert east["bootstrap_ci_95"] == [20.0, 150.0]
    assert east["p10_m"] == 0.0
    assert east["p90_m"] == 400.0

    # Width median 95% CI is [120.0, 320.0]
    assert width["bootstrap_ci_95"] == [120.0, 320.0]
    assert width["p10_m"] == 0.0
    assert width["p90_m"] == 760.0


# ==============================================================================
# Scenario 7: Provisional Detection Scenario Thresholds
# ==============================================================================
def test_07_provisional_detection_scenario_thresholds(client):
    """Verifies provisional detection scenarios: 35m cut-bank, 60m nominal, 85m char fringe."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/displacement")
    assert response.status_code == 200
    data = response.json()

    scenarios = data["provisional_scenario_thresholds_m"]
    assert scenarios["cut_bank_minimum_resolvable_m"] == 35.0
    assert scenarios["nominal_unconsolidated_bank_m"] == 60.0
    assert scenarios["char_fringe_submergence_m"] == 85.0


# ==============================================================================
# Scenario 8: Candidate Erosion Zones Matching Phase 6.1 General Zones
# ==============================================================================
def test_08_candidate_erosion_zones_phase6_1_general(client):
    """Verifies candidate zones match phase6_1_area_reconciliation.csv (21.94, 23.21, 0.4148, 13.65 km2)."""
    response = client.get("/api/v1/regions/jamuna_sirajganj/riverbank/erosion-candidates")
    assert response.status_code == 200
    data = response.json()

    zones = {z["zone_code"]: z for z in data["candidate_zones"]}

    # Zone 2: External Bank Expansion Candidate
    assert zones[2]["area_km2"] == 21.9400
    assert zones[2]["area_ha"] == 2194.00
    assert zones[2]["pixel_count"] == 54850

    # Zone 3: Internal Char Submergence Candidate
    assert zones[3]["area_km2"] == 23.2100
    assert zones[3]["area_ha"] == 2321.00
    assert zones[3]["pixel_count"] == 58025

    # Zone 4: Apparent Channel Contraction / Accretion Candidate
    assert zones[4]["area_km2"] == 0.4148
    assert zones[4]["area_ha"] == 41.48
    assert zones[4]["pixel_count"] == 1037

    # Zone 6: Disconnected Floodplain Inundation
    assert zones[6]["area_km2"] == 13.6468
    assert zones[6]["area_ha"] == 1364.68
    assert zones[6]["pixel_count"] == 34117


# ==============================================================================
# Scenario 9: Raster Channel Change Zones 12-Class Palette
# ==============================================================================
def test_09_raster_channel_change_zones_12_class_palette():
    """Verifies phase6_channel_change_zones palette covers all 12 classes (0..10 and 255)."""
    assert "phase6_channel_change_zones" in RASTER_CATALOG
    palette = RASTER_CATALOG["phase6_channel_change_zones"]["palette"]

    # All 12 classes must be defined
    for code in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 255):
        assert code in palette, f"Class {code} missing from channel change zones palette"

    # Class 0: Transparent
    assert palette[0][3] == 0
    # Class 1: Navy Blue persistent water
    assert palette[1][:3] == [8, 48, 107]
    # Class 2: Bright Red external bank expansion
    assert palette[2][:3] == [227, 26, 28]
    # Class 255: Transparent nodata
    assert palette[255][3] == 0


# ==============================================================================
# Scenario 10: Dynamic Raster CRS Extraction
# ==============================================================================
def test_10_dynamic_raster_crs_extraction(client):
    """Verifies raster metadata extracts CRS dynamically from dataset projection."""
    response = client.get("/api/v1/rasters/phase5_flood_transitions/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["crs"].startswith("EPSG:")
    assert data["crs"] == "EPSG:32645"


# ==============================================================================
# Scenario 11: Vector EPSG:4326 Reprojection and Native CRS Preservation
# ==============================================================================
def test_11_vector_epsg4326_reprojection(client):
    """Verifies vector service outputs standard EPSG:4326 and preserves native_crs."""
    response = client.get("/api/v1/vectors/phase6_riverbank_transects")
    assert response.status_code == 200
    data = response.json()

    assert data["crs"] == "EPSG:4326"
    assert data["native_crs"] == "EPSG:32645"
    assert data["feature_count"] == 154

    # Check coordinate ranges are in WGS84 degrees
    feat = data["geojson"]["features"][0]
    coords = feat["geometry"]["coordinates"]
    pt0 = coords[0]
    lon, lat = pt0[0], pt0[1]
    assert 89.0 <= lon <= 90.0, f"Expected longitude in degrees, got {lon}"
    assert 24.0 <= lat <= 26.0, f"Expected latitude in degrees, got {lat}"


# ==============================================================================
# Scenario 12: Rejection of Unknown Region and Model with 404
# ==============================================================================
def test_12_unknown_region_and_model_rejection(client):
    """Verifies unknown region_id and model_id are strictly rejected with 404."""
    r_flood = client.get("/api/v1/regions/fictional_basin_xyz/flood/summary")
    assert r_flood.status_code == 404

    r_river = client.get("/api/v1/regions/fictional_basin_xyz/riverbank/summary")
    assert r_river.status_code == 404

    r_stats = client.get("/api/v1/regions/fictional_basin_xyz/statistics")
    assert r_stats.status_code == 404

    r_model_diag = client.get("/api/v1/models/nonexistent_deep_net/diagnostics")
    assert r_model_diag.status_code == 404

    r_model_metrics = client.get("/api/v1/models/nonexistent_deep_net/metrics")
    assert r_model_metrics.status_code == 404


# ==============================================================================
# Scenario 13: Model Decision Margin Interpretation Clarification
# ==============================================================================
def test_13_model_decision_margin_interpretation(client):
    """Verifies |P - 0.5| is interpreted as distance from 0.5 boundary, uncalibrated."""
    response = client.get("/api/v1/models/phase7a_rf_jamuna_v1/diagnostics")
    assert response.status_code == 200
    data = response.json()

    assert data["calibration_status"] == "UNCALIBRATED"
    interp = data["decision_margin_interpretation"]
    assert "0.5" in interp
    assert "tau* = 0.35" in interp or "0.35" in interp
    assert "uncalibrated" in interp.lower()


# ==============================================================================
# Scenario 14: Dataset Integrity Job Execution with Real SHA-256
# ==============================================================================
def test_14_dataset_integrity_job_execution(client):
    """Verifies verify_dataset_integrity computes real hashes and executes without NameError."""
    response = client.post(
        "/api/v1/jobs",
        json={
            "job_type": "verify_dataset_integrity",
            "region_id": "jamuna_sirajganj",
            "parameters": {},
        },
    )
    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "COMPLETED"
    assert job["progress_pct"] == 100.0

    outputs = job["output_references"]
    assert "verified_count" in outputs
    assert "all_valid" in outputs
    assert "details" in outputs
    assert outputs["verified_count"] >= 8
    assert outputs["all_valid"] is True


# ==============================================================================
# Scenario 15: Clean Route Paths and Exception Handler Sanitization
# ==============================================================================
def test_15_clean_route_paths_and_health(client):
    """Verifies /health root route, /api/v1/system/status without double prefix, and capabilities."""
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "healthy"

    r_status = client.get("/api/v1/system/status")
    assert r_status.status_code == 200
    assert r_status.json()["status"] == "OPERATIONAL"

    r_cap = client.get("/api/v1/system/capabilities")
    assert r_cap.status_code == 200
    assert "Jamuna" in r_cap.json()["study_area_focused"]
    # Check riverbank analysis description has 154 total, 122 valid, 32 outside
    assert "154" in r_cap.json()["scientific_baselines"]["primary_riverbank_analysis"]
