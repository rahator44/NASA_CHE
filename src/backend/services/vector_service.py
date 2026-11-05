"""
Vector Data Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from src.backend.config import settings

VECTOR_CATALOG: Dict[str, Dict[str, Any]] = {
    "phase5_inundation_clusters": {
        "relative_path": "data/outputs/phase5/maps/phase5_major_inundation_clusters.geojson",
        "vector_type": "inundation_clusters",
        "region_id": "jamuna_sirajganj",
    },
    "phase6_riverbank_transects": {
        "relative_path": "data/outputs/phase6_1/maps/phase6_1_riverbank_transects.geojson",
        "vector_type": "riverbank_transects",
        "region_id": "jamuna_sirajganj",
    },
    "phase6_centerline": {
        "relative_path": "data/outputs/phase6/maps/phase6_provisional_centerline.geojson",
        "vector_type": "stream_centerline",
        "region_id": "jamuna_sirajganj",
    },
    "newly_inundated_candidate": {
        "relative_path": "data/processed/phase3b/newly_inundated_candidate.geojson",
        "vector_type": "candidate_flood_polygons",
        "region_id": "jamuna_sirajganj",
    },
}


class VectorService:
    @staticmethod
    def list_vector_assets(region_id: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        for asset_id, info in VECTOR_CATALOG.items():
            if region_id and info["region_id"] != region_id:
                continue

            full_path = settings.PROJECT_ROOT_DIR / info["relative_path"]
            if not full_path.exists():
                continue

            with open(full_path, "r") as f:
                geo = json.load(f)

            results.append({
                "asset_id": asset_id,
                "region_id": info["region_id"],
                "vector_type": info["vector_type"],
                "feature_count": len(geo.get("features", [])),
                "crs": geo.get("crs", {}).get("properties", {}).get("name", "EPSG:32645"),
            })
        return results

    @staticmethod
    def _lookup_asset(asset_id: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        if asset_id in VECTOR_CATALOG:
            return asset_id, VECTOR_CATALOG[asset_id]
        for prefix in ("phase5_", "phase6_", "phase7a_"):
            cand = f"{prefix}{asset_id}"
            if cand in VECTOR_CATALOG:
                return cand, VECTOR_CATALOG[cand]
        for key in VECTOR_CATALOG:
            for prefix in ("phase5_", "phase6_", "phase7a_"):
                if key.startswith(prefix) and key[len(prefix):] == asset_id:
                    return key, VECTOR_CATALOG[key]
        return None

    @classmethod
    def get_vector_geojson(cls, asset_id: str) -> Optional[Dict[str, Any]]:
        lookup = cls._lookup_asset(asset_id)
        if not lookup:
            return None
        resolved_id, info = lookup

        full_path = settings.PROJECT_ROOT_DIR / info["relative_path"]
        if not full_path.exists():
            return None

        with open(full_path, "r") as f:
            return json.load(f)
