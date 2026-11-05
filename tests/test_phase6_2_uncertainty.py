"""
Tests for Earth Pulse Phase 6.2: Displacement Uncertainty, Statistical Confidence & Final Scientific Readiness Audit
NASA Space Apps Challenge 2026: Dancing with the SARs

Covers:
1. Uncertainty calculation arithmetic & discrepancy verification.
2. Error component provenance & empty GCP audit.
3. Single-epoch vs two-epoch error propagation.
4. Deterministic spatial moving block bootstrap reproducibility.
5. Confidence interval validity (lower <= point <= upper).
6. Transect quality classification & invalid transect exclusion.
7. Provisional detection threshold range enforcement.
8. Scientific terminology & causal claim auditing.
9. Scientific readiness classification integrity (long-term erosion rate strictly BLOCKED).
"""

import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def p62_outputs():
    """Loads Phase 6.2 CSV tables and metadata JSON."""
    stats_dir = PROJECT_ROOT / "data/outputs/phase6_2/statistics"
    meta_path = PROJECT_ROOT / "data/metadata/phase6_2_uncertainty_audit.json"

    assert stats_dir.exists(), f"Missing stats dir: {stats_dir}"
    assert meta_path.exists(), f"Missing metadata file: {meta_path}"

    with open(meta_path) as f:
        meta = json.load(f)

    df_budget = pd.read_csv(stats_dir / "phase6_2_uncertainty_budget.csv")
    df_stats = pd.read_csv(stats_dir / "phase6_2_bank_displacement_statistics.csv")
    df_boot = pd.read_csv(stats_dir / "phase6_2_spatial_bootstrap_intervals.csv")
    df_thresh = pd.read_csv(stats_dir / "phase6_2_detection_threshold_assessment.csv")
    df_sens = pd.read_csv(stats_dir / "phase6_2_sampling_sensitivity_audit.csv")
    df_readiness = pd.read_csv(stats_dir / "phase6_2_scientific_readiness.csv")

    return {
        "meta": meta,
        "budget": df_budget,
        "stats": df_stats,
        "boot": df_boot,
        "thresh": df_thresh,
        "sens": df_sens,
        "readiness": df_readiness,
    }


class TestPhase62UncertaintyArithmetic:
    """Verifies the mathematical and arithmetic calculations of the uncertainty audit."""

    def test_legacy_uncertainty_arithmetic_discrepancy(self, p62_outputs):
        """Verifies that the legacy Phase 6.1 uncertainty calculation contained a +0.203 m arithmetic error."""
        u_pixel = 14.14
        u_orbit = 4.00
        u_mixel = 20.00
        u_angle = 10.00

        calculated_rms = math.sqrt(u_pixel**2 + u_orbit**2 + u_mixel**2 + u_angle**2)
        reported_rms = 26.96

        assert round(calculated_rms, 3) == 26.757
        discrepancy = reported_rms - calculated_rms
        assert round(discrepancy, 3) == 0.203

        meta_audit = p62_outputs["meta"]["phase6_1_uncertainty_audit"]
        assert meta_audit["calculated_rms_m"] == 26.757
        assert meta_audit["reported_rms_m"] == 26.96
        assert meta_audit["arithmetic_discrepancy_m"] == 0.203

    def test_two_epoch_discretization_propagation(self):
        """Verifies uniform quantization standard deviation for single and two epochs."""
        grid_spacing = 20.0
        # Single-epoch uniform quantization: sigma = Delta / sqrt(12)
        sigma_1epoch = grid_spacing / math.sqrt(12.0)
        assert round(sigma_1epoch, 2) == 5.77

        # Two-epoch differential discretization: sqrt(sigma^2 + sigma^2) = Delta / sqrt(6)
        sigma_2epoch = grid_spacing / math.sqrt(6.0)
        assert round(sigma_2epoch, 2) == 8.16

    def test_empty_gcp_provenance_verification(self):
        """Verifies that intermediate GCP files contain 0 measured ground control points."""
        june_gcp = PROJECT_ROOT / "data/intermediate/june10_sigma0_vv_vh_tc.data/vector_data/ground_control_points.csv"
        july_gcp = PROJECT_ROOT / "data/intermediate/july16_sigma0_vv_vh_tc.data/vector_data/ground_control_points.csv"

        for gcp_file in [june_gcp, july_gcp]:
            assert gcp_file.exists(), f"GCP file not found: {gcp_file}"
            lines = [line.strip() for line in gcp_file.read_text().splitlines() if line.strip()]
            # Only header comment and column names exist (2 lines)
            assert len(lines) == 2, f"Expected empty GCP template, found {len(lines)} lines in {gcp_file}"
            assert lines[1].startswith("org.esa.snap.GroundControlPoint")


class TestPhase62DefensibleUncertaintyModels:
    """Verifies the defensible uncertainty models and provisional detection threshold range."""

    def test_provisional_threshold_range_bounds(self, p62_outputs):
        """Verifies that the provisional threshold range is [35.0, 60.0, 85.0] m."""
        models = p62_outputs["meta"]["defensible_uncertainty_model"]
        threshold_range = models["provisional_threshold_range_m"]

        assert threshold_range == [35.0, 60.0, 85.0]
        assert models["models"]["optimistic_consolidated_bank"]["operational_threshold_m"] == 35.0
        assert models["models"]["central_typical_bank"]["operational_threshold_m"] == 60.0
        assert models["models"]["conservative_shallow_char"]["operational_threshold_m"] == 85.0

    def test_two_epoch_model_ordering(self, p62_outputs):
        """Verifies that optimistic < central < conservative sigma_delta."""
        m = p62_outputs["meta"]["defensible_uncertainty_model"]["models"]
        sigma_low = m["optimistic_consolidated_bank"]["sigma_delta_m"]
        sigma_mid = m["central_typical_bank"]["sigma_delta_m"]
        sigma_high = m["conservative_shallow_char"]["sigma_delta_m"]

        assert sigma_low < sigma_mid < sigma_high
        assert sigma_low == 16.6
        assert sigma_mid == 29.86
        assert sigma_high == 43.77


class TestPhase62TransectStatisticsAndBootstrap:
    """Verifies sample statistics, spatial block bootstrapping, and threshold exceedances."""

    def test_valid_transect_count_and_sample_moments(self, p62_outputs):
        """Verifies exact empirical statistics for the 122 valid transects."""
        df_stats = p62_outputs["stats"]
        assert len(df_stats) == 3

        wb = df_stats[df_stats["column_name"] == "right_bank_displacement_m"].iloc[0]
        eb = df_stats[df_stats["column_name"] == "left_bank_displacement_m"].iloc[0]
        cw = df_stats[df_stats["column_name"] == "channel_width_expansion_m"].iloc[0]

        assert wb["transect_count"] == 122
        assert wb["median_displacement_m"] == 40.0
        assert wb["mean_displacement_m"] == 130.0
        assert wb["p90_m"] == 440.0
        assert wb["p95_m"] == 578.0

        assert eb["transect_count"] == 122
        assert eb["median_displacement_m"] == 90.0
        assert eb["mean_displacement_m"] == 160.66
        assert eb["p90_m"] == 400.0
        assert eb["p95_m"] == 539.0

        assert cw["transect_count"] == 122
        assert cw["median_displacement_m"] == 180.0
        assert cw["mean_displacement_m"] == 290.66
        assert cw["p90_m"] == 760.0
        assert cw["p95_m"] == 879.0

    def test_spatial_bootstrap_confidence_interval_integrity(self, p62_outputs):
        """Verifies spatial block bootstrap results and that point estimates lie within 95% CIs."""
        df_boot = p62_outputs["boot"]
        assert len(df_boot) == 12  # 3 features * 4 stats

        for _, row in df_boot.iterrows():
            assert row["block_size_transects"] == 6
            assert row["block_length_km"] == 1.2
            assert row["bootstrap_iterations"] == 2000
            assert row["random_seed"] == 42
            assert row["ci_95_lower_m"] <= row["point_estimate_m"] <= row["ci_95_upper_m"]

    def test_threshold_exceedance_asymmetry(self, p62_outputs):
        """Verifies that at the 60 m central threshold, West Bank is mostly below noise while East Bank is mostly above."""
        df_thresh = p62_outputs["thresh"]

        wb_60 = df_thresh[
            (df_thresh["threshold_m"] == 60.0) & (df_thresh["target_feature"] == "Right Bank (West / Mainland)")
        ].iloc[0]
        eb_60 = df_thresh[
            (df_thresh["threshold_m"] == 60.0) & (df_thresh["target_feature"] == "Left Bank (East / Chars)")
        ].iloc[0]

        # West Bank: only 35.25% exceed 60m (64.75% sub-threshold / within noise)
        assert wb_60["exceeding_count"] == 43
        assert wb_60["exceeding_percentage"] == 35.25
        assert wb_60["sub_threshold_percentage"] == 64.75

        # East Bank: 52.46% exceed 60m (statistically detectable lateral expansion)
        assert eb_60["exceeding_count"] == 64
        assert eb_60["exceeding_percentage"] == 52.46


class TestPhase62ScientificGovernanceAndReadiness:
    """Verifies scientific terminology, sampling sensitivity critique, and readiness verdicts."""

    def test_sampling_sensitivity_audit_critique(self, p62_outputs):
        """Verifies that the sampling sensitivity table flags 1000m aliasing and median invariance."""
        df_sens = p62_outputs["sens"]
        assert len(df_sens) == 4

        s1000 = df_sens[df_sens["sampling_interval_m"] == 1000.0].iloc[0]
        assert s1000["audit_verdict"] == "SEVERE_SPATIAL_ALIASING"
        assert s1000["reported_right_max_m"] == 4420.0  # Artificially lower than 5660 m

        s200 = df_sens[df_sens["sampling_interval_m"] == 200.0].iloc[0]
        assert s200["audit_verdict"] == "PRIMARY_OPERATIONAL_BASELINE"

    def test_scientific_readiness_classifications(self, p62_outputs):
        """Verifies that long-term erosion rate is strictly BLOCKED while others are READY_WITH_LIMITATIONS."""
        df_readiness = p62_outputs["readiness"]
        assert len(df_readiness) == 5

        uc05 = df_readiness[df_readiness["use_case_id"] == "UC-05"].iloc[0]
        assert uc05["readiness_status"] == "BLOCKED"
        assert "Only two acquisition dates" in uc05["operational_conditions_and_limitations"]

        for uc_id in ["UC-01", "UC-02", "UC-03", "UC-04"]:
            uc = df_readiness[df_readiness["use_case_id"] == uc_id].iloc[0]
            assert uc["readiness_status"] == "READY_WITH_LIMITATIONS"

    def test_project_state_roadmap_alignment(self):
        """Verifies that earth_pulse_project_state.json contains the corrected Phase 6.2 state and 10-phase roadmap."""
        state_path = PROJECT_ROOT / "data/metadata/earth_pulse_project_state.json"
        with open(state_path) as f:
            state = json.load(f)

        assert "Phase 6.2" in state["current_phase_completed"]
        assert state["next_phase_planned"] == "Phase 7 (Random Forest and Explainable AI)"

        roadmap = state["development_roadmap"]
        assert "COMPLETE" in roadmap["Phase 6.2"]
        assert "PLANNED" in roadmap["Phase 7"]
        assert "PLANNED" in roadmap["Phase 8"]
        assert "PLANNED" in roadmap["Phase 9"]
        assert "PLANNED" in roadmap["Phase 10"]

