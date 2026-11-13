"""
Vector Data Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from osgeo import osr
from src.backend.config import settings

osr.UseExceptions()

VECTOR_CATALOG: Dict[str, Dict[str, Any]] = {
    "phase5_inundation_clusters": {
        "relative_path": "data/outputs/phase5/maps/phase5_major_inundation_clusters.geojson",
        "vector_type": "inundation_clusters",
        "region_id": "jamuna_sirajganj",
        "native_crs": "EPSG:32645",
    },
    "phase6_riverbank_transects": {
        "relative_path": "data/outputs/phase6_1/maps/phase6_1_riverbank_transects.geojson",
        "vector_type": "riverbank_transects",
        "region_id": "jamuna_sirajganj",
        "native_crs": "EPSG:32645",
    },
    "phase6_centerline": {
        "relative_path": "data/outputs/phase6/maps/phase6_provisional_centerline.geojson",
        "vector_type": "stream_centerline",
        "region_id": "jamuna_sirajganj",
        "native_crs": "EPSG:32645",
    },
    "newly_inundated_candidate": {
        "relative_path": "data/processed/phase3b/newly_inundated_candidate.geojson",
        "vector_type": "candidate_flood_polygons",
        "region_id": "jamuna_sirajganj",
        "native_crs": "EPSG:32645",
    },
}


def _create_transformer(src_epsg: int = 32645, dst_epsg: int = 4326) -> osr.CoordinateTransformation:
    s_srs = osr.SpatialReference()
    s_srs.ImportFromEPSG(src_epsg)
    s_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    t_srs = osr.SpatialReference()
    t_srs.ImportFromEPSG(dst_epsg)
    t_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    return osr.CoordinateTransformation(s_srs, t_srs)


def _reproject_coords(coords: Any, ct: osr.CoordinateTransformation) -> Any:
    if not coords:
        return coords
    if isinstance(coords[0], (int, float)):
        x, y = coords[0], coords[1]
        # If already in degree ranges (WGS84 lon: [-180, 180], lat: [-90, 90]), do not re-transform
        if -180.0 <= x <= 180.0 and -90.0 <= y <= 90.0:
            return [round(float(x), 6), round(float(y), 6)]
        lon, lat, _ = ct.TransformPoint(float(x), float(y))
        return [round(lon, 6), round(lat, 6)]
    elif isinstance(coords[0], list):
        return [_reproject_coords(sub, ct) for sub in coords]
    return coords


def _reproject_geojson_to_wgs84(geo: Dict[str, Any], native_epsg: int = 32645) -> Dict[str, Any]:
    ct = _create_transformer(src_epsg=native_epsg, dst_epsg=4326)
    geo_wgs84 = json.loads(json.dumps(geo))  # Deep copy

    for feat in geo_wgs84.get("features", []):
        geom = feat.get("geometry")
        if geom and "coordinates" in geom:
            geom["coordinates"] = _reproject_coords(geom["coordinates"], ct)

    geo_wgs84["crs"] = {
        "type": "name",
        "properties": {"name": "EPSG:4326"}
    }
    return geo_wgs84


class VectorService:
    @staticmethod
    def list_vector_assets(region_id: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        for asset_id, info in VECTOR_CATALOG.items():
            if region_id and info["region_id"] != region_id:
                continue

            full_path = settings.resolve_data_path(info["relative_path"])
            if not full_path.exists():
                continue

            with open(full_path, "r") as f:
                geo = json.load(f)

            results.append({
                "asset_id": asset_id,
                "region_id": info["region_id"],
                "vector_type": info["vector_type"],
                "feature_count": len(geo.get("features", [])),
                "crs": "EPSG:4326",
                "native_crs": info.get("native_crs", "EPSG:32645"),
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
    def get_vector_geojson(cls, asset_id: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        lookup = cls._lookup_asset(asset_id)
        if not lookup:
            return None
        resolved_id, info = lookup

        full_path = settings.resolve_data_path(info["relative_path"])
        if not full_path.exists():
            return None

        with open(full_path, "r") as f:
            raw_geo = json.load(f)

        # Reproject to standard WGS84 EPSG:4326
        geo_wgs84 = _reproject_geojson_to_wgs84(raw_geo, native_epsg=32645)
        return geo_wgs84, info
