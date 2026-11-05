"""
Flood and Surface-Water Change Data Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
from src.backend.config import settings


class FloodService:
    @staticmethod
    def get_flood_summary(region_id: str) -> Dict[str, Any]:
        report_path = settings.METADATA_DIR / "phase5_flood_change_report.json"
        with open(report_path, "r") as f:
            meta = json.load(f)

        trans = meta["transition_accounting"]
        recon = trans["net_change_reconciliation"]

        return {
            "region_id": region_id,
            "methodology": meta.get("primary_sar_method", "Adaptive Lee 5x5 Dual-AND Otsu (VV & VH)"),
            "pre_monsoon_epoch": {
                "epoch_name": "June 10, 2024 (Pre-Monsoon Low Flow)",
                "acquisition_date": "2024-06-10T12:05:08Z",
                "hydrological_condition": "Pre-Monsoon Baseflow / Exposed Sandbars",
                "candidate_water_cells": recon["valid_june_water_pixels"],
                "candidate_water_area_ha": round(recon["valid_june_water_km2"] * 100.0, 2),
                "candidate_water_area_km2": recon["valid_june_water_km2"],
                "candidate_water_pct_valid": round(recon["valid_june_water_km2"] / trans["valid_transition_area_km2"] * 100.0, 2),
                "candidate_water_pct_aoi": round(recon["valid_june_water_km2"] / trans["aoi_total_area_km2"] * 100.0, 2),
                "vv_threshold_db": -12.457,
                "vh_threshold_db": -21.697,
            },
            "monsoon_crest_epoch": {
                "epoch_name": "July 16, 2024 (Monsoon Flood Crest)",
                "acquisition_date": "2024-07-16T12:05:07Z",
                "hydrological_condition": "Monsoon Peak Inundation / Anabranch Expansion",
                "candidate_water_cells": recon["valid_july_water_pixels"],
                "candidate_water_area_ha": round(recon["valid_july_water_km2"] * 100.0, 2),
                "candidate_water_area_km2": recon["valid_july_water_km2"],
                "candidate_water_pct_valid": round(recon["valid_july_water_km2"] / trans["valid_transition_area_km2"] * 100.0, 2),
                "candidate_water_pct_aoi": round(recon["valid_july_water_km2"] / trans["aoi_total_area_km2"] * 100.0, 2),
                "vv_threshold_db": -14.960,
                "vh_threshold_db": -21.828,
            },
            "net_candidate_water_change_ha": recon["net_candidate_water_area_change_ha"],
            "net_candidate_water_change_km2": recon["net_candidate_water_area_change_km2"],
            "accounting_note": (
                "Scientific Accounting Distinction: Net candidate water-area change (5,814.32 ha) reflects "
                "the net balance of newly inundated areas minus receded water over the common valid domain. "
                "Whole-epoch unmasked delta across the entire AOI is 6,452.24 ha, with 637.92 ha attributable "
                "to asymmetric radar quality mask exclusions."
            ),
        }

    @staticmethod
    def get_flood_transitions(region_id: str) -> Dict[str, Any]:
        report_path = settings.METADATA_DIR / "phase5_flood_change_report.json"
        with open(report_path, "r") as f:
            meta = json.load(f)

        trans = meta["transition_accounting"]
        pw = trans["persistent_water"]
        ni = trans["newly_inundated_candidate"]
        rw = trans["receded_water"]
        pnw = trans["persistent_non_water"]

        classes = [
            {
                "class_id": 1,
                "class_name": "Persistent Water",
                "pixel_count": pw["cells"],
                "area_ha": pw["area_ha"],
                "area_km2": pw["area_km2"],
                "percentage_of_valid_domain": pw["pct_valid_domain"],
                "description": "Standing water present in both June and July (main braided channels and permanent waterbodies).",
            },
            {
                "class_id": 2,
                "class_name": "Newly Inundated Candidate",
                "pixel_count": ni["cells"],
                "area_ha": ni["area_ha"],
                "area_km2": ni["area_km2"],
                "percentage_of_valid_domain": ni["pct_valid_domain"],
                "description": "Dry land/sand in June that converted to water in July due to monsoon flood crest expansion.",
            },
            {
                "class_id": 3,
                "class_name": "Receded Water",
                "pixel_count": rw["cells"],
                "area_ha": rw["area_ha"],
                "area_km2": rw["area_km2"],
                "percentage_of_valid_domain": rw["pct_valid_domain"],
                "description": "Water in June that dried/receded by July (ephemeral drainage pools and isolated bar depressions).",
            },
            {
                "class_id": 4,
                "class_name": "Persistent Non-Water",
                "pixel_count": pnw["cells"],
                "area_ha": pnw["area_ha"],
                "area_km2": pnw["area_km2"],
                "percentage_of_valid_domain": pnw["pct_valid_domain"],
                "description": "Dry land, vegetation, and settlement embankments unflooded across both observation periods.",
            },
        ]

        return {
            "region_id": region_id,
            "common_valid_domain_cells": trans["valid_transition_cells"],
            "common_valid_domain_ha": trans["valid_transition_area_ha"],
            "common_valid_domain_km2": trans["valid_transition_area_km2"],
            "transitions": classes,
            "net_inundation_balance_ha": round(ni["area_ha"] - rw["area_ha"], 2),
            "accounting_rule": "Strict spatial intersection on mutually valid, non-indeterminate pixels.",
        }

    @staticmethod
    def get_flood_clusters(region_id: str, limit: int = 15) -> Dict[str, Any]:
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

    @staticmethod
    def get_flood_uncertainty(region_id: str) -> Dict[str, Any]:
        report_path = settings.METADATA_DIR / "phase5_flood_change_report.json"
        with open(report_path, "r") as f:
            meta = json.load(f)

        return {
            "region_id": region_id,
            "radar_shadow_exclusion_ha": 12.8,
            "layover_exclusion_ha": 8.4,
            "water_lookalike_exclusion_ha": 628.48,
            "total_indeterminate_ha": 649.68,
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

