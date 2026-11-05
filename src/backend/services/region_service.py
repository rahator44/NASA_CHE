"""
Region Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from src.backend.config import settings
from src.core.config_loader import load_region_config


class RegionService:
    @staticmethod
    def list_regions() -> List[Dict[str, Any]]:
        regions_dir = settings.CONFIGS_DIR / "regions"
        if not regions_dir.exists():
            return []

        results = []
        for yaml_path in sorted(regions_dir.glob("*.yaml")):
            rid = yaml_path.stem
            try:
                cfg = load_region_config(rid)
                results.append(RegionService._format_summary(cfg))
            except Exception:
                continue
        return results

    @staticmethod
    def _format_summary(cfg: Dict[str, Any]) -> Dict[str, Any]:
        grid = cfg.get("grid", {})
        acqs = cfg.get("acquisitions", {})
        acq_dates = [f"{info.get('date', '')} ({k})" for k, info in acqs.items()]

        return {
            "region_id": cfg.get("region_id", ""),
            "name": cfg.get("region_name", cfg.get("name", "")),
            "country": cfg.get("country", "Bangladesh"),
            "description": f"Study area: {cfg.get('region_name', '')}",
            "river_system": "Jamuna / Brahmaputra River",
            "crs": grid.get("crs", "EPSG:32645"),
            "spatial_resolution_m": float(grid.get("pixel_spacing_m", 20.0)),
            "raster_dimensions": [
                int(grid.get("raster_height", 1393)),
                int(grid.get("raster_width", 1405)),
            ],
            "available_acquisitions": acq_dates or [
                "2024-06-10 (pre_monsoon_low_flow)",
                "2024-07-16 (peak_monsoon_flood)",
            ],
            "available_analysis_modules": [
                "flood_change_detection",
                "riverbank_migration_displacement",
                "random_forest_classification",
                "model_explainability_attribution",
                "scientific_uncertainty_audit",
            ]
        }

    @staticmethod
    def get_region_detail(region_id: str) -> Optional[Dict[str, Any]]:
        try:
            cfg = load_region_config(region_id)
        except Exception:
            return None

        summary = RegionService._format_summary(cfg)

        aoi = cfg.get("aoi", {})
        bbox_list = aoi.get("bbox", [89.55, 24.58, 89.75, 24.76])
        min_lon, min_lat, max_lon, max_lat = bbox_list[0], bbox_list[1], bbox_list[2], bbox_list[3]

        wkt = aoi.get("wkt", f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))")
        coords = [
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]

        detail = dict(summary)
        detail.update({
            "bounding_box": {
                "west": float(min_lon),
                "east": float(max_lon),
                "south": float(min_lat),
                "north": float(max_lat),
            },
            "bounding_polygon": {
                "wkt": wkt,
                "crs": "EPSG:4326",
                "coordinates_wgs84": coords,
            },
            "hydrological_regime": "Braided Multi-Channel Alluvial Sand-Bed River",
            "morphological_classification": "Dynamic Anabranching Braided Reach",
            "baseline_classifier": "Adaptive Lee 5x5 Dual-AND Otsu (VV & VH)",
        })
        return detail
