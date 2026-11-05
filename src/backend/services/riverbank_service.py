"""
Riverbank Migration & Displacement Data Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
from src.backend.config import settings
from src.backend import contracts


class RiverbankService:
    @staticmethod
    def _validate_region(region_id: str) -> None:
        if region_id != contracts.STUDY_AREA_ID:
            raise ValueError(
                f"Region '{region_id}' not found or data not available. "
                f"Authoritative registered study areas: ['{contracts.STUDY_AREA_ID}']"
            )

    @classmethod
    def get_riverbank_summary(cls, region_id: str) -> Dict[str, Any]:
        cls._validate_region(region_id)

        return {
            "region_id": region_id,
            "total_transects_evaluated": contracts.TOTAL_EVALUATED_TRANSECTS,  # 154
            "valid_transects_count": contracts.VALID_LOCAL_MIGRATION_COUNT,    # 122
            "ambiguous_transects_count": contracts.OUTSIDE_VALID_LOCAL_COUNT,  # 32
            "outside_valid_transects_count": contracts.OUTSIDE_VALID_LOCAL_COUNT,  # 32
            "valid_transect_fraction_pct": round(
                contracts.VALID_LOCAL_MIGRATION_COUNT / contracts.TOTAL_EVALUATED_TRANSECTS * 100.0, 2
            ),
            "mean_west_displacement_m": round(contracts.DISPLACEMENT_EMPIRICAL_STATS["west_bank"]["mean_m"], 2),
            "mean_east_displacement_m": round(contracts.DISPLACEMENT_EMPIRICAL_STATS["east_bank"]["mean_m"], 2),
            "mean_channel_width_change_m": round(contracts.DISPLACEMENT_EMPIRICAL_STATS["channel_width"]["mean_m"], 2),
            "median_west_displacement_m": round(contracts.DISPLACEMENT_EMPIRICAL_STATS["west_bank"]["median_m"], 2),
            "median_east_displacement_m": round(contracts.DISPLACEMENT_EMPIRICAL_STATS["east_bank"]["median_m"], 2),
            "median_channel_width_change_m": round(contracts.DISPLACEMENT_EMPIRICAL_STATS["channel_width"]["median_m"], 2),
            "provisional_detection_range_m": "35-85m",
            "provisional_detection_scenarios_m": contracts.PROVISIONAL_SCENARIO_THRESHOLDS_M,
            "morphological_behavior": "Lateral channel expansion and char submergence under monsoon high-stage discharge",
            "scientific_readiness_status": "PROVISIONAL_MONSOON_FLOOD_STAGE_EFFECT_NOT_LONG_TERM_EROSION",
            "hydrodynamic_caveat": (
                "Displacements reflect waterline shifts between pre-monsoon low flow (June 10) and monsoon flood "
                "observation (July 16). They must not be conflated with permanent subaerial cut-bank erosion rates."
            ),
        }

    @classmethod
    def get_transects(cls, region_id: str, limit: int = 200, only_valid: bool = False) -> Dict[str, Any]:
        cls._validate_region(region_id)

        csv_path = settings.OUTPUTS_DIR / "phase6_1/statistics/phase6_1_transect_displacement_audit.csv"
        if not csv_path.exists():
            return {"region_id": region_id, "total_count": 0, "valid_count": 0, "ambiguous_count": 0, "transects": []}

        df = pd.read_csv(csv_path)
        total_eval = len(df)
        valid_count = int((df["confidence_status"] == "VALID_LOCAL_MIGRATION").sum())
        outside_count = total_eval - valid_count

        if only_valid:
            df = df[df["confidence_status"] == "VALID_LOCAL_MIGRATION"]

        items = []
        for _, row in df.head(limit).iterrows():
            is_val = (row["confidence_status"] == "VALID_LOCAL_MIGRATION")
            chainage = float(row["chainage_m"]) if pd.notnull(row.get("chainage_m")) else 0.0

            # Compute origin and terminus coordinates along transect row
            c_y = float(row.get("center_utm_y", 0.0))
            rb_x = float(row.get("right_bank_june_x", 0.0)) if pd.notnull(row.get("right_bank_june_x")) else 770000.0
            lb_x = float(row.get("left_bank_june_x", 0.0)) if pd.notnull(row.get("left_bank_june_x")) else 780000.0

            items.append({
                "transect_id": int(row.get("transect_id", 0)),
                "chainage_m": chainage,
                "station_m": chainage,  # Preserved for backward compatibility
                "origin_utm": [rb_x, c_y],
                "terminus_utm": [lb_x, c_y],
                "bearing_deg": 90.0,
                "is_valid": is_val,
                "ambiguity_flag": str(row.get("confidence_status", "")) if not is_val else None,
                "audit_category": str(row.get("confidence_status", "")),
                "west_bank_displacement_m": float(row.get("right_bank_displacement_m", 0.0)) if pd.notnull(row.get("right_bank_displacement_m")) else None,
                "east_bank_displacement_m": float(row.get("left_bank_displacement_m", 0.0)) if pd.notnull(row.get("left_bank_displacement_m")) else None,
                "channel_width_june_m": float(row.get("channel_width_june_m", 0.0)) if pd.notnull(row.get("channel_width_june_m")) else None,
                "channel_width_july_m": float(row.get("channel_width_july_m", 0.0)) if pd.notnull(row.get("channel_width_july_m")) else None,
                "net_width_change_m": float(row.get("channel_width_expansion_m", 0.0)) if pd.notnull(row.get("channel_width_expansion_m")) else None,
            })

        return {
            "region_id": region_id,
            "total_count": len(df),
            "valid_count": valid_count,
            "ambiguous_count": outside_count,
            "outside_valid_count": outside_count,
            "transects": items,
        }

    @classmethod
    def get_displacement_stats(cls, region_id: str) -> Dict[str, Any]:
        cls._validate_region(region_id)

        west = dict(contracts.DISPLACEMENT_EMPIRICAL_STATS["west_bank"])
        west["bootstrap_ci_95"] = contracts.SPATIAL_BOOTSTRAP_CI_95["median"]["west_bank_ci_m"]
        west["bootstrap_ci_95_mean"] = contracts.SPATIAL_BOOTSTRAP_CI_95["mean"]["west_bank_ci_m"]

        east = dict(contracts.DISPLACEMENT_EMPIRICAL_STATS["east_bank"])
        east["bootstrap_ci_95"] = contracts.SPATIAL_BOOTSTRAP_CI_95["median"]["east_bank_ci_m"]
        east["bootstrap_ci_95_mean"] = contracts.SPATIAL_BOOTSTRAP_CI_95["mean"]["east_bank_ci_m"]

        width = dict(contracts.DISPLACEMENT_EMPIRICAL_STATS["channel_width"])
        width["bootstrap_ci_95"] = contracts.SPATIAL_BOOTSTRAP_CI_95["median"]["channel_width_ci_m"]
        width["bootstrap_ci_95_mean"] = contracts.SPATIAL_BOOTSTRAP_CI_95["mean"]["channel_width_ci_m"]

        return {
            "region_id": region_id,
            "west_bank_expansion_stats": west,
            "east_bank_expansion_stats": east,
            "net_channel_width_change_stats": width,
            "detection_threshold_m": 60.0,
            "provisional_scenario_thresholds_m": contracts.PROVISIONAL_SCENARIO_THRESHOLDS_M,
            "unfiltered_vs_filtered_note": (
                "Statistics derived from 122 audited valid transects. 95% spatial block bootstrap confidence "
                "intervals capture spatial autocorrelation across the reach: West median CI [20.0, 80.0] m, "
                "East median CI [20.0, 150.0] m, and Net Channel Width median CI [120.0, 320.0] m. "
                "P10/P90 are empirical sample percentiles (West P90=440 m, East P90=400 m, Width P90=760 m), "
                "not bootstrap intervals."
            ),
        }

    @classmethod
    def get_erosion_candidates(cls, region_id: str) -> Dict[str, Any]:
        cls._validate_region(region_id)

        return {
            "region_id": region_id,
            "candidate_zones": contracts.PHASE6_1_GENERAL_ZONES,
            "bre_embankment_influence_note": (
                "Brahmaputra Right Embankment (BRE) structural influence is documented as an unverified geomorphic "
                "hypothesis; independent structural stability surveys are required to determine structural retreat."
            ),
        }

    @classmethod
    def get_riverbank_uncertainty(cls, region_id: str) -> Dict[str, Any]:
        cls._validate_region(region_id)

        return {
            "region_id": region_id,
            "quadrature_uncertainty_budget": {
                "pixel_discretization_1sigma_m": 8.16,
                "orbit_coregistration_1sigma_m": 5.66,
                "water_edge_mixels_speckle_1sigma_m": 28.28,
                "combined_two_epoch_rms_m": 29.86,
            },
            "total_displacement_uncertainty_m": 29.86,
            "minimum_resolvable_displacement_m": 35.0,
            "provisional_scenario_thresholds_m": contracts.PROVISIONAL_SCENARIO_THRESHOLDS_M,
            "spatial_autocorrelation_decorrelation_length_m": 800.0,
            "scientific_caveats": [
                "Provisional detection range spans 35 m (steep cut-banks) to 85 m (low-gradient char fringes), with 60 m nominal",
                "Displacements reflect short-term flood stage response, not annual net sediment flux",
                "Ambiguous transects with multiple channel threads (32 transects) are segregated from simple bank migration",
            ],
        }
