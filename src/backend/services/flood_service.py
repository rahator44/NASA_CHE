"""
Flood and Surface-Water Change Data Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
from src.backend.config import settings
from src.backend import contracts


class FloodService:
    @staticmethod
    def _validate_region(region_id: str) -> None:
        if region_id != contracts.STUDY_AREA_ID:
            raise ValueError(
                f"Region '{region_id}' not found or data not available. "
                f"Authoritative registered study areas: ['{contracts.STUDY_AREA_ID}']"
            )

    @classmethod
    def get_flood_summary(cls, region_id: str) -> Dict[str, Any]:
        cls._validate_region(region_id)

        pre_monsoon = {
            "epoch_name": contracts.BASELINE_LABEL,
            "acquisition_date": f"{contracts.BASELINE_DATE}T12:05:08Z",
            "hydrological_condition": "Pre-Monsoon Baseflow / Exposed Sandbars",
            "candidate_water_cells": contracts.VALID_JUNE_WATER_CELLS,
            "candidate_water_area_ha": contracts.VALID_JUNE_WATER_HA,
            "candidate_water_area_km2": contracts.VALID_JUNE_WATER_KM2,
            "candidate_water_pct_valid": round(
                contracts.VALID_JUNE_WATER_KM2 / contracts.COMMON_VALID_DOMAIN_KM2 * 100.0, 2
            ),
            "candidate_water_pct_aoi": round(
                contracts.VALID_JUNE_WATER_KM2 / contracts.AOI_TOTAL_AREA_KM2 * 100.0, 2
            ),
            "vv_threshold_db": -12.457,
            "vh_threshold_db": -21.697,
        }

        flood_obs = {
            "epoch_name": contracts.FLOOD_OBSERVATION_LABEL,
            "acquisition_date": f"{contracts.FLOOD_OBSERVATION_DATE}T12:05:07Z",
            "hydrological_condition": "Monsoon Inundation Stage / Anabranch Expansion (Not Annual Peak Crest)",
            "candidate_water_cells": contracts.VALID_JULY_WATER_CELLS,
            "candidate_water_area_ha": contracts.VALID_JULY_WATER_HA,
            "candidate_water_area_km2": contracts.VALID_JULY_WATER_KM2,
            "candidate_water_pct_valid": round(
                contracts.VALID_JULY_WATER_KM2 / contracts.COMMON_VALID_DOMAIN_KM2 * 100.0, 2
            ),
            "candidate_water_pct_aoi": round(
                contracts.VALID_JULY_WATER_KM2 / contracts.AOI_TOTAL_AREA_KM2 * 100.0, 2
            ),
            "vv_threshold_db": -14.960,
            "vh_threshold_db": -21.828,
        }

        return {
            "region_id": region_id,
            "methodology": "Adaptive Lee 5x5 Dual-AND Otsu (VV & VH)",
            "pre_monsoon_epoch": pre_monsoon,
            "flood_observation_epoch": flood_obs,
            "monsoon_crest_epoch": flood_obs,  # Preserved for backward compatibility
            "net_candidate_water_change_ha": contracts.NET_VALID_DOMAIN_CHANGE_HA,
            "net_candidate_water_change_km2": contracts.NET_VALID_DOMAIN_CHANGE_KM2,
            "whole_epoch_unmasked_delta_ha": contracts.WHOLE_EPOCH_UNMASKED_DELTA_HA,
            "whole_epoch_unmasked_delta_km2": contracts.WHOLE_EPOCH_UNMASKED_DELTA_KM2,
            "asymmetric_exclusions_gap_ha": contracts.ASYMMETRIC_EXCLUSIONS_GAP_HA,
            "accounting_note": (
                "Scientific Accounting Distinction: Net candidate water-area change (5,814.32 ha) reflects "
                "the net balance of newly inundated areas (5,879.68 ha) minus receded water (65.36 ha) over the common valid domain. "
                "Whole-epoch unmasked delta across the entire AOI is 6,452.24 ha, with 637.92 ha attributable "
                "to asymmetric radar quality mask exclusions."
            ),
        }

    @classmethod
    def get_flood_transitions(cls, region_id: str) -> Dict[str, Any]:
        cls._validate_region(region_id)

        classes = [
            {
                "class_id": 1,
                "class_name": "Persistent Water",
                "pixel_count": contracts.PERSISTENT_WATER_CELLS,
                "area_ha": contracts.PERSISTENT_WATER_HA,
                "area_km2": contracts.PERSISTENT_WATER_KM2,
                "percentage_of_valid_domain": contracts.PERSISTENT_WATER_PCT_VALID,
                "description": "Standing water present in both June and July (main braided channels and permanent waterbodies).",
            },
            {
                "class_id": 2,
                "class_name": "Newly Inundated Candidate",
                "pixel_count": contracts.NEWLY_INUNDATED_CANDIDATE_CELLS,
                "area_ha": contracts.NEWLY_INUNDATED_CANDIDATE_HA,
                "area_km2": contracts.NEWLY_INUNDATED_CANDIDATE_KM2,
                "percentage_of_valid_domain": contracts.NEWLY_INUNDATED_CANDIDATE_PCT_VALID,
                "description": "Dry land/sand in June that converted to water in July due to monsoon flood stage expansion.",
            },
            {
                "class_id": 3,
                "class_name": "Receded Water",
                "pixel_count": contracts.RECEDED_WATER_CELLS,
                "area_ha": contracts.RECEDED_WATER_HA,
                "area_km2": contracts.RECEDED_WATER_KM2,
                "percentage_of_valid_domain": contracts.RECEDED_WATER_PCT_VALID,
                "description": "Water in June that dried/receded by July (ephemeral drainage pools and isolated bar depressions).",
            },
            {
                "class_id": 4,
                "class_name": "Persistent Non-Water",
                "pixel_count": contracts.PERSISTENT_NON_WATER_CELLS,
                "area_ha": contracts.PERSISTENT_NON_WATER_HA,
                "area_km2": contracts.PERSISTENT_NON_WATER_KM2,
                "percentage_of_valid_domain": contracts.PERSISTENT_NON_WATER_PCT_VALID,
                "description": "Dry land, vegetation, and settlement embankments unflooded across both observation periods.",
            },
        ]

        return {
            "region_id": region_id,
            "common_valid_domain_cells": contracts.COMMON_VALID_DOMAIN_CELLS,
            "common_valid_domain_ha": contracts.COMMON_VALID_DOMAIN_HA,
            "common_valid_domain_km2": contracts.COMMON_VALID_DOMAIN_KM2,
            "transitions": classes,
            "net_inundation_balance_ha": contracts.NET_VALID_DOMAIN_CHANGE_HA,
            "accounting_rule": "Strict spatial intersection on mutually valid, non-indeterminate pixels (Common Valid Domain).",
        }

    @classmethod
    def get_flood_clusters(cls, region_id: str, limit: int = 15) -> Dict[str, Any]:
        cls._validate_region(region_id)

        csv_path = settings.OUTPUTS_DIR / "phase5/statistics/phase5_cluster_statistics.csv"
        if not csv_path.exists():
            return {"region_id": region_id, "total_clusters_count": 0, "total_clustered_area_ha": 0.0, "major_clusters": []}

        df = pd.read_csv(csv_path)
        total_count = len(df)
        total_ha = float(df["area_ha"].sum())

        major_subset = df[df["is_major_cluster"] == True].head(limit)
        clusters = []
        for _, row in major_subset.iterrows():
            clusters.append({
                "cluster_id": int(row["cluster_id"]),
                "area_ha": float(row["area_ha"]),
                "area_km2": float(row["area_km2"]),
                "cell_count": int(row["pixel_count"]),
                "centroid_utm": [float(row["centroid_utm45n_x"]), float(row["centroid_utm45n_y"])],
                "geographic_zone": (
                    "Eastern Floodplain Inundation Complex" if row["centroid_utm45n_x"] > 773000
                    else "Western Embankment Adjacent Flood Zone"
                ),
                "description": f"Contiguous inundation patch (rank {int(row['rank'])}, {float(row['area_ha']):.1f} ha).",
            })

        return {
            "region_id": region_id,
            "total_clusters_count": total_count,
            "total_clustered_area_ha": round(total_ha, 2),
            "major_clusters": clusters,
        }

    @classmethod
    def get_flood_uncertainty(cls, region_id: str) -> Dict[str, Any]:
        cls._validate_region(region_id)

        return {
            "region_id": region_id,
            "total_indeterminate_cells": contracts.INDETERMINATE_CELLS,
            "total_indeterminate_ha": contracts.INDETERMINATE_HA,
            "total_indeterminate_km2": contracts.INDETERMINATE_KM2,
            "percentage_of_aoi": round(contracts.INDETERMINATE_CELLS / contracts.AOI_TOTAL_CELLS * 100, 4),
            "noise_floor_definition": (
                "Empirical indeterminate noise-floor mask (Phase 5) isolating pixels near the dual-pol "
                "bimodal classification threshold boundary where cross-polarization separation is ambiguous."
            ),
            "subdivision_note": (
                "No speculative topographic shadow/layover subdivisions are asserted; the Jamuna "
                "braid-belt is low-relief alluvial terrain where relief-induced shadow/layover is physically negligible."
            ),
            "classification_confidence": {
                "deep_channel_water": "HIGH (coincident VV/VH backscatter < -18 dB)",
                "floodplain_anabranch": "HIGH (coincident VV/VH backscatter < -16 dB)",
                "shallow_sandbar_edge": "MODERATE (mixed pixel / boundary transition)",
                "moist_char_sediment": "UNCERTAIN (requires multi-temporal confirmation)",
            },
            "quality_standards": [
                "Lee 5x5 adaptive speckle filtering applied prior to thresholding",
                "Dual-AND logical intersection suppresses single-polarization false alarms",
                "Indeterminate noise floor isolated before transition differencing",
            ],
        }
