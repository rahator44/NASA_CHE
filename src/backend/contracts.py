"""
Earth Pulse Backend Source-of-Truth Scientific Contracts
NASA Space Apps Challenge 2026: Dancing with the SARs

This module serves as the authoritative, immutable source-of-truth contract for
all scientific figures, accounting rules, geographic zones, and data codes
established across Phases 1 through 7B.1. All backend services import and adhere
to these constants.
"""

from typing import Dict, Any, List, Tuple
from dataclasses import dataclass


# ==============================================================================
# 1. Study Area & Event Definition
# ==============================================================================

STUDY_AREA_ID = "jamuna_sirajganj"
STUDY_AREA_NAME = "Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)"

# Multi-temporal SAR acquisitions:
# June 10, 2024: Pre-monsoon baseflow / low water condition
# July 16, 2024: Monsoon flood-period observation (mid-monsoon high stage, not peak crest of entire season)
BASELINE_DATE = "2024-06-10"
FLOOD_OBSERVATION_DATE = "2024-07-16"
BASELINE_LABEL = "June 10, 2024 (Pre-Monsoon Baseflow)"
FLOOD_OBSERVATION_LABEL = "July 16, 2024 (Monsoon Flood-Period Observation)"


# ==============================================================================
# 2. Phase 5: Common-Valid-Domain Surface-Water Accounting
# Authoritative Source: data/metadata/phase5_flood_change_report.json
#                     & data/outputs/phase5/statistics/phase5_inundation_area_summary.csv
# ==============================================================================

# Total Study AOI grid cells within the defined study boundary
AOI_TOTAL_CELLS = 1_010_039
AOI_TOTAL_AREA_KM2 = 404.0156
AOI_TOTAL_AREA_HA = 40_401.56

# Full bounding-box grid dimensions (1405 x 1393 at 20 m pixel spacing)
RASTER_BOUNDING_BOX_CELLS = 1_957_165
RASTER_BOUNDING_BOX_KM2 = 782.8660
RASTER_BOUNDING_BOX_HA = 78_286.60

# Mutually valid common domain (intersection of valid, non-indeterminate SAR data in both epochs)
COMMON_VALID_DOMAIN_CELLS = 993_736
COMMON_VALID_DOMAIN_KM2 = 397.4944
COMMON_VALID_DOMAIN_HA = 39_749.44
COMMON_VALID_DOMAIN_PCT_AOI = 98.3859

# Surface water transition components within the Common Valid Domain:
PERSISTENT_WATER_CELLS = 216_595
PERSISTENT_WATER_KM2 = 86.6380
PERSISTENT_WATER_HA = 8_663.80
PERSISTENT_WATER_PCT_VALID = 21.7960
PERSISTENT_WATER_PCT_AOI = 21.4442

NEWLY_INUNDATED_CANDIDATE_CELLS = 146_992
NEWLY_INUNDATED_CANDIDATE_KM2 = 58.7968
NEWLY_INUNDATED_CANDIDATE_HA = 5_879.68
NEWLY_INUNDATED_CANDIDATE_PCT_VALID = 14.7919
NEWLY_INUNDATED_CANDIDATE_PCT_AOI = 14.5531

RECEDED_WATER_CELLS = 1_634
RECEDED_WATER_KM2 = 0.6536
RECEDED_WATER_HA = 65.36
RECEDED_WATER_PCT_VALID = 0.1644
RECEDED_WATER_PCT_AOI = 0.1618

PERSISTENT_NON_WATER_CELLS = 628_515
PERSISTENT_NON_WATER_KM2 = 251.4060
PERSISTENT_NON_WATER_HA = 25_140.60
PERSISTENT_NON_WATER_PCT_VALID = 63.2477
PERSISTENT_NON_WATER_PCT_AOI = 62.2268

# Indeterminate & NoData within Study AOI (excluded from Common Valid Domain):
INDETERMINATE_CELLS = 16_242
INDETERMINATE_KM2 = 6.4968
INDETERMINATE_HA = 649.68
INDETERMINATE_PCT_AOI = 1.6081

NODATA_AOI_CELLS = 61
NODATA_AOI_KM2 = 0.0244
NODATA_AOI_HA = 2.44
NODATA_AOI_PCT_AOI = 0.0060

# Enforce authoritative accounting identities
assert PERSISTENT_WATER_CELLS + NEWLY_INUNDATED_CANDIDATE_CELLS + RECEDED_WATER_CELLS + PERSISTENT_NON_WATER_CELLS == COMMON_VALID_DOMAIN_CELLS, (
    f"Common valid domain accounting error: {PERSISTENT_WATER_CELLS + NEWLY_INUNDATED_CANDIDATE_CELLS + RECEDED_WATER_CELLS + PERSISTENT_NON_WATER_CELLS} != {COMMON_VALID_DOMAIN_CELLS}"
)
assert COMMON_VALID_DOMAIN_CELLS + INDETERMINATE_CELLS + NODATA_AOI_CELLS == AOI_TOTAL_CELLS, (
    f"Total AOI accounting error: {COMMON_VALID_DOMAIN_CELLS + INDETERMINATE_CELLS + NODATA_AOI_CELLS} != {AOI_TOTAL_CELLS}"
)

# Net surface-water change over common valid domain: Newly Inundated - Receded
NET_VALID_DOMAIN_CHANGE_CELLS = 145_358
NET_VALID_DOMAIN_CHANGE_KM2 = 58.1432
NET_VALID_DOMAIN_CHANGE_HA = 5_814.32

# Valid per-epoch candidate water totals within Common Valid Domain:
VALID_JUNE_WATER_CELLS = 218_229
VALID_JUNE_WATER_KM2 = 87.2916
VALID_JUNE_WATER_HA = 8_729.16

VALID_JULY_WATER_CELLS = 363_587
VALID_JULY_WATER_KM2 = 145.4348
VALID_JULY_WATER_HA = 14_543.48

# Whole-epoch unmasked delta across full study extent (distinct domain):
# June unmasked water = 218,330 cells (87.3320 km², 8,733.20 ha)
# July unmasked water = 379,636 cells (151.8544 km², 15,185.44 ha)
WHOLE_EPOCH_JUNE_WATER_CELLS = 218_330
WHOLE_EPOCH_JUNE_WATER_HA = 8_733.20
WHOLE_EPOCH_JULY_WATER_CELLS = 379_636
WHOLE_EPOCH_JULY_WATER_HA = 15_185.44
WHOLE_EPOCH_UNMASKED_DELTA_CELLS = 161_306
WHOLE_EPOCH_UNMASKED_DELTA_KM2 = 64.5224
WHOLE_EPOCH_UNMASKED_DELTA_HA = 6_452.24

# Asymmetric radar quality mask exclusions gap:
# Gap = Whole-Epoch Delta (6,452.24 ha) - Common-Valid-Domain Net Change (5,814.32 ha) = 637.92 ha
ASYMMETRIC_EXCLUSIONS_GAP_CELLS = 15_948
ASYMMETRIC_EXCLUSIONS_GAP_KM2 = 6.3792
ASYMMETRIC_EXCLUSIONS_GAP_HA = 637.92


# ==============================================================================
# 3. Phase 6.1 & 6.2: Riverbank Transects & Geomorphic Displacement
# Authoritative Source: data/outputs/phase6_1/statistics/phase6_1_transect_displacement_audit.csv
#                     & data/outputs/phase6_2/statistics/phase6_2_spatial_bootstrap_intervals.csv
#                     & data/outputs/phase6_2/statistics/phase6_2_bank_displacement_statistics.csv
# ==============================================================================

# Evaluated transects in the Phase 6.1 audit:
TOTAL_EVALUATED_TRANSECTS = 154
VALID_LOCAL_MIGRATION_COUNT = 122
OUTSIDE_VALID_LOCAL_COUNT = 32

# Breakdown of the 32 non-valid transects:
AMBIGUOUS_EDGE_EFFECT_COUNT = 23
ANABRANCH_ACTIVATION_COUNT = 5
MAJOR_CHANNEL_EXPANSION_COUNT = 4

# Empirical Displacement Statistics across the 122 Valid Local Transects:
DISPLACEMENT_EMPIRICAL_STATS = {
    "west_bank": {
        "mean_m": 130.00,
        "std_m": 200.83,
        "median_m": 40.0,
        "iqr_m": 200.0,
        "p10_m": 0.0,
        "p25_m": 0.0,
        "p75_m": 200.0,
        "p90_m": 440.0,
        "p95_m": 578.0,
        "min_m": -120.0,
        "max_m": 820.0,
    },
    "east_bank": {
        "mean_m": 160.66,
        "std_m": 209.95,
        "median_m": 90.0,
        "iqr_m": 275.0,
        "p10_m": 0.0,
        "p25_m": 0.0,
        "p75_m": 275.0,
        "p90_m": 400.0,
        "p95_m": 539.0,
        "min_m": -20.0,
        "max_m": 960.0,
    },
    "channel_width": {
        "mean_m": 290.66,
        "std_m": 286.68,
        "median_m": 180.0,
        "iqr_m": 360.0,
        "p10_m": 0.0,
        "p25_m": 60.0,
        "p75_m": 420.0,
        "p90_m": 760.0,
        "p95_m": 879.0,
        "min_m": -60.0,
        "max_m": 1100.0,
    },
}

# 95% Spatial Block Bootstrap Confidence Intervals (from phase6_2_spatial_bootstrap_intervals.csv):
SPATIAL_BOOTSTRAP_CI_95 = {
    "median": {
        "west_bank_ci_m": [20.0, 80.0],
        "east_bank_ci_m": [20.0, 150.0],
        "channel_width_ci_m": [120.0, 320.0],
    },
    "mean": {
        "west_bank_ci_m": [59.8361, 203.2787],
        "east_bank_ci_m": [101.9672, 222.7869],
        "channel_width_ci_m": [194.4262, 378.0328],
    },
}

# Provisional Geomorphic Detection Scenario Thresholds:
# 53.92 m was a deprecated early scalar; the authoritative audit establishes 3 scenarios:
PROVISIONAL_SCENARIO_THRESHOLDS_M = {
    "cut_bank_minimum_resolvable_m": 35.0,
    "nominal_unconsolidated_bank_m": 60.0,
    "char_fringe_submergence_m": 85.0,
}

# General Riverbank Change Zones (Phase 6.1 Area Reconciliation):
# Authoritative Source: data/outputs/phase6_1/statistics/phase6_1_area_reconciliation.csv
PHASE6_1_GENERAL_ZONES = [
    {
        "zone_code": 2,
        "zone_type": "External Bank Expansion / Erosion Candidate",
        "area_km2": 21.9400,
        "area_ha": 2194.00,
        "pixel_count": 54850,
        "pct_study_aoi": 5.4305,
        "geomorphic_classification": "Mainland Fluvial Bank Line Retreat / Lowland Cut-Bank",
        "certainty_level": "MODERATE_STAGE_SENSITIVE",
        "description": "Apparent lateral channel expansion along outer mainland margins.",
    },
    {
        "zone_code": 3,
        "zone_type": "Internal Char Submergence Candidate",
        "area_km2": 23.2100,
        "area_ha": 2321.00,
        "pixel_count": 58025,
        "pct_study_aoi": 5.7448,
        "geomorphic_classification": "Hydrodynamic Inundation of Sandbar Margins",
        "certainty_level": "HYDROLOGICAL_FLOOD_STAGE_RESPONSE",
        "description": "Submergence of internal braid bars and char margins under high-stage discharge.",
    },
    {
        "zone_code": 4,
        "zone_type": "Apparent Channel Contraction / Accretion Candidate",
        "area_km2": 0.4148,
        "area_ha": 41.48,
        "pixel_count": 1037,
        "pct_study_aoi": 0.1027,
        "geomorphic_classification": "Local Emergence / Ephemeral Sediment Splays",
        "certainty_level": "LOCALIZED_ANOMALY",
        "description": "Localized emergent sand splays or boundary artifacts.",
    },
    {
        "zone_code": 6,
        "zone_type": "Disconnected Floodplain Inundation",
        "area_km2": 13.6468,
        "area_ha": 1364.68,
        "pixel_count": 34117,
        "pct_study_aoi": 3.3778,
        "geomorphic_classification": "Overbank Floodplain Ponding / Lowland Depressions",
        "certainty_level": "HYDROLOGICAL_FLOODPLAIN_PONDING",
        "description": "Backswamp and paleochannel ponding disconnected from the main river corridor.",
    },
]


# ==============================================================================
# 4. Phase 6.1 Raster 12-Class Codebook & Color Palette
# Authoritative Source: data/processed/phase6_1/phase6_1_channel_change_zones.tif
#                     & data/outputs/phase6_1/statistics/phase6_1_area_reconciliation.csv
# ==============================================================================

PHASE6_1_ZONE_CODEBOOK: Dict[int, Dict[str, Any]] = {
    0: {
        "name": "Persistent Mainland Non-Water",
        "rgba": [0, 0, 0, 0],  # Transparent
        "hex": "#00000000",
        "description": "Stable terrestrial mainland unflooded in both epochs",
    },
    1: {
        "name": "Persistent Channel Water",
        "rgba": [8, 48, 107, 240],  # Deep Navy Blue
        "hex": "#08306b",
        "description": "Main braided channel water present in June and July",
    },
    2: {
        "name": "External Bank Expansion / Erosion Candidate",
        "rgba": [227, 26, 28, 240],  # Bright Red
        "hex": "#e31a1c",
        "description": "Mainland riverbank line retreat / outer channel expansion",
    },
    3: {
        "name": "Internal Char Submergence Candidate",
        "rgba": [251, 154, 153, 240],  # Soft Pink / Coral
        "hex": "#fb9a99",
        "description": "Internal char sandbar submergence under high stage",
    },
    4: {
        "name": "Apparent Channel Contraction / Accretion Candidate",
        "rgba": [51, 160, 44, 240],  # Forest Green
        "hex": "#33a02c",
        "description": "Apparent water-to-land accretion or emerging bar splays",
    },
    5: {
        "name": "Persistent Internal Char Islands",
        "rgba": [178, 223, 138, 200],  # Olive Pale Green
        "hex": "#b2df8a",
        "description": "Elevated char cores unflooded during both observation dates",
    },
    6: {
        "name": "Disconnected Floodplain Inundation",
        "rgba": [31, 120, 180, 240],  # Medium Blue
        "hex": "#1f78b4",
        "description": "Lowland floodplain depressions outside primary channel corridor",
    },
    7: {
        "name": "Indeterminate Noise Floor",
        "rgba": [166, 206, 227, 180],  # Powder Blue / Gray
        "hex": "#a6cee3",
        "description": "Radar shadow, layover, or indeterminate boundary transition",
    },
    8: {
        "name": "Persistent Floodplain Water Bodies",
        "rgba": [253, 191, 111, 220],  # Soft Orange
        "hex": "#fdbf6f",
        "description": "Perennial beels, oxbows, and inland lakes on the floodplain",
    },
    9: {
        "name": "Receded Floodplain Water",
        "rgba": [255, 127, 0, 220],  # Vivid Orange
        "hex": "#ff7f00",
        "description": "Ephemeral floodplain depressions dry by mid-July",
    },
    10: {
        "name": "Persistent Char Island Water Depressions",
        "rgba": [255, 255, 153, 220],  # Pale Yellow
        "hex": "#ffff99",
        "description": "Standing water pools within internal char bar complexes",
    },
    255: {
        "name": "Source NoData / Border",
        "rgba": [0, 0, 0, 0],  # Transparent
        "hex": "#00000000",
        "description": "Out-of-bounds or border nodata pixels",
    },
}


# ==============================================================================
# 5. Phase 7A & 7B.1: Model Registry Status & Scientific Interpretation
# Authoritative Source: models/model_registry.json
#                     & data/metadata/phase7a_model_report.json
# ==============================================================================

MODEL_ID_JAMUNA_V1 = "phase7a_rf_jamuna_v1"
MODEL_STATUS = "RETAINED_AS_PROBABILITY_LAYER"
MODEL_PRIMARY_BASELINE = "Adaptive Lee 5x5 Dual-AND Otsu (VV & VH)"
MODEL_TEST_ROC_AUC = 0.6810
MODEL_DECISION_THRESHOLD = 0.35

MODEL_ARTIFACT_SHA256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"

DECISION_MARGIN_INTERPRETATION = (
    "The metric |P - 0.5| represents distance from the uncalibrated symmetric classification boundary (0.5), "
    "not distance from the operational decision threshold (tau* = 0.35). It does not represent a calibrated "
    "posterior probability of physical water presence, as unpruned Gini leaf purity incentives polarize tree outputs."
)

EPISTEMOLOGICAL_DISCLAIMER = (
    "The specular scattering mechanism on saturated alluvial sediments is a physically grounded hypothesis "
    "consistent with electromagnetic theory, not an in-situ proven causal fact, due to the absence of synchronous "
    "dielectric probe measurements during Sentinel-1 overpasses."
)
