"""
Satellite Catalog Service for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Provides dynamic catalog search and scene discovery over arbitrary dates
and spatial footprints (WKT, GeoJSON, or bounding box) for Sentinel-1 GRD SAR.
"""

import sys
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Ensure workspace-vendored packages are accessible if present
_LOCAL_PACKAGES = Path(__file__).resolve().parent.parent.parent / ".packages"
if _LOCAL_PACKAGES.exists() and str(_LOCAL_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_LOCAL_PACKAGES))

from src.acquisition.asf_client import ASFClient, validate_scene_metadata
from src.acquisition.scene_selector import SceneSelector
from src.core.earthdata_auth import audit_earthdata_configuration, EarthdataSessionManager

logger = logging.getLogger("EarthPulse.SatelliteCatalog")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "catalog"

# Default Jamuna River bounding polygon WKT (Sirajganj study corridor)
JAMUNA_DEFAULT_AOI_WKT = "POLYGON((89.5 24.3, 89.9 24.3, 89.9 24.8, 89.5 24.8, 89.5 24.3))"


def atomic_write_json(path: Path, data: Any) -> None:
    """Safely write JSON using an atomic replace operation."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp_{os_pid_tag()}")
    tmp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp_path.replace(path)


def os_pid_tag() -> str:
    import os
    return f"{os.getpid()}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"


class SatelliteCatalogService:
    """
    Core service for querying satellite archives, filtering observations,
    and pairing multi-temporal scenes for environmental change detection.
    Enforces exact query identity, strict metadata validation, and zero cross-query leakage.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.asf_client = ASFClient()
        self.cache_dir = cache_dir or CATALOG_CACHE_DIR

    @staticmethod
    def compute_query_signature(
        wkt_polygon: str,
        start_date: str,
        end_date: str,
        platform: str = "SENTINEL-1",
        processing_level: str = "GRD_HD",
        beam_mode: str = "IW",
        polarization: Optional[str] = "VV+VH",
        orbit_direction: Optional[str] = None,
        relative_orbit: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Compute deterministic SHA-256 signature for exact satellite catalogue query parameters.
        """
        norm_aoi = " ".join(wkt_polygon.strip().split())
        norm_start = start_date[:10]
        norm_end = end_date[:10]
        query_dict = {
            "aoi_wkt": norm_aoi,
            "start_date": norm_start,
            "end_date": norm_end,
            "platform": (platform or "SENTINEL-1").upper(),
            "processing_level": (processing_level or "GRD_HD").upper(),
            "beam_mode": (beam_mode or "IW").upper(),
            "polarization": (polarization or "VV+VH").upper() if polarization else "VV+VH",
            "orbit_direction": orbit_direction.upper() if orbit_direction else None,
            "relative_orbit": int(relative_orbit) if relative_orbit is not None else None,
        }
        raw_repr = json.dumps(query_dict, sort_keys=True)
        sig = hashlib.sha256(raw_repr.encode("utf-8")).hexdigest()
        return sig, query_dict

    def _get_validated_cache(self, sig: str, query_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Retrieve cached catalogue search results ensuring exact query identity,
        temporal validity, and strict metadata conformance.
        """
        cache_file = self.cache_dir / f"{sig}.json"
        if not cache_file.exists():
            return []

        try:
            cached_doc = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_query = cached_doc.get("query", {})
            for key in ["aoi_wkt", "start_date", "end_date", "platform", "processing_level", "beam_mode", "polarization", "orbit_direction", "relative_orbit"]:
                if cached_query.get(key) != query_dict.get(key):
                    logger.warning("Catalogue cache key collision or parameter mismatch on '%s': ignoring cache", key)
                    return []

            req_start_day = query_dict["start_date"]
            req_end_day = query_dict["end_date"]
            scenes = cached_doc.get("scenes", [])
            valid_scenes = []
            for sc in scenes:
                acq = sc.get("acquisition_time", "")
                if not acq or len(acq) < 10:
                    continue
                sc_day = acq[:10]
                if sc_day < req_start_day or sc_day > req_end_day:
                    logger.warning("Cached scene '%s' date %s falls outside requested [%s, %s]", sc.get("scene_name"), sc_day, req_start_day, req_end_day)
                    continue

                rejections = validate_scene_metadata(sc, scene_source=sc.get("scene_name", "cache"))
                if rejections:
                    logger.warning("Cached scene '%s' failed validation: %s", sc.get("scene_name"), "; ".join(rejections))
                    continue

                valid_scenes.append(sc)

            if valid_scenes:
                logger.info("Retrieved %d validated scenes from catalogue query cache (%s)", len(valid_scenes), sig[:8])
            return valid_scenes
        except Exception as e:
            logger.warning("Failed to read catalogue cache %s: %s", cache_file, e)
            return []

    def _save_cache(self, sig: str, query_dict: Dict[str, Any], scenes: List[Dict[str, Any]]) -> None:
        """Atomically persist validated catalogue query results."""
        if not scenes:
            return
        try:
            cache_file = self.cache_dir / f"{sig}.json"
            doc = {
                "signature": sig,
                "query": query_dict,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "scene_count": len(scenes),
                "scenes": scenes,
            }
            atomic_write_json(cache_file, doc)
        except Exception as e:
            logger.warning("Failed to write catalogue query cache: %s", e)

    def search_sentinel1_scenes(
        self,
        wkt_polygon: str = JAMUNA_DEFAULT_AOI_WKT,
        start_date: str = "2024-01-01",
        end_date: str = "2024-12-31",
        orbit_direction: Optional[str] = None,
        relative_orbit: Optional[int] = None,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search NASA ASF DAAC for Sentinel-1 IW GRD dual-pol observations.
        First queries ASF DAAC. On failure or offline mode, consults query-bound cache with exact parameter identity.
        """
        sig, query_dict = self.compute_query_signature(
            wkt_polygon=wkt_polygon,
            start_date=start_date,
            end_date=end_date,
            platform="SENTINEL-1",
            processing_level="GRD_HD",
            beam_mode="IW",
            polarization="VV+VH",
            orbit_direction=orbit_direction,
            relative_orbit=relative_orbit,
        )

        scenes: List[Dict[str, Any]] = []
        try:
            scenes = self.asf_client.search_scenes(
                wkt_polygon=wkt_polygon,
                start_date=start_date,
                end_date=end_date,
                platform="SENTINEL-1",
                processing_level="GRD_HD",
                beam_mode="IW",
                polarization="VV+VH",
                flight_direction=orbit_direction,
                relative_orbit=relative_orbit,
                max_results=max_results,
            )
        except Exception as e:
            logger.warning("Live ASF search failed (%s), checking query-bound cache...", e)
            scenes = []

        if scenes:
            self._save_cache(sig, query_dict, scenes)
            return scenes

        # Check exact query cache
        cached_scenes = self._get_validated_cache(sig, query_dict)
        if cached_scenes:
            return cached_scenes

        return []

    def discover_compatible_pairs(
        self,
        wkt_polygon: str,
        start_date: str,
        end_date: str,
        min_temporal_baseline_days: int = 6,
        max_temporal_baseline_days: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Find all scientifically valid observation pairs (baseline + change)
        satisfying identical relative orbit, flight direction, and dual polarization.
        """
        scenes = self.search_sentinel1_scenes(
            wkt_polygon=wkt_polygon,
            start_date=start_date,
            end_date=end_date,
        )

        return SceneSelector.find_all_compatible_pairs(
            scenes=scenes,
            wkt_polygon=wkt_polygon,
            min_days=min_temporal_baseline_days,
            max_days=max_temporal_baseline_days,
        )

    def check_catalog_status(self) -> Dict[str, Any]:
        """
        Perform a health check on the NASA Earthdata / ASF search endpoint.
        """
        auth_audit = audit_earthdata_configuration()
        try:
            test_scenes = self.search_sentinel1_scenes(
                wkt_polygon=JAMUNA_DEFAULT_AOI_WKT,
                start_date="2024-06-10",
                end_date="2024-06-11",
                max_results=1,
            )
            return {
                "status": "healthy",
                "asf_search_reachable": True,
                "test_query_count": len(test_scenes),
                "auth": auth_audit,
            }
        except Exception as e:
            logger.error("Catalog health check failed: %s", e)
            return {
                "status": "degraded",
                "asf_search_reachable": False,
                "error": str(e),
                "auth": auth_audit,
            }

