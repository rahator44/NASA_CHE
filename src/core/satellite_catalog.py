"""
Satellite Catalog Service for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Provides dynamic catalog search and scene discovery over arbitrary dates
and spatial footprints (WKT, GeoJSON, or bounding box) for Sentinel-1 GRD SAR.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Ensure workspace-vendored packages are accessible if present
_LOCAL_PACKAGES = Path(__file__).resolve().parent.parent.parent / ".packages"
if _LOCAL_PACKAGES.exists() and str(_LOCAL_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_LOCAL_PACKAGES))

from src.acquisition.asf_client import ASFClient
from src.acquisition.scene_selector import SceneSelector
from src.core.earthdata_auth import audit_earthdata_configuration, EarthdataSessionManager

logger = logging.getLogger("EarthPulse.SatelliteCatalog")

# Default Jamuna River bounding polygon WKT (Sirajganj study corridor)
JAMUNA_DEFAULT_AOI_WKT = "POLYGON((89.5 24.3, 89.9 24.3, 89.9 24.8, 89.5 24.8, 89.5 24.3))"


class SatelliteCatalogService:
    """
    Core service for querying satellite archives, filtering observations,
    and pairing multi-temporal scenes for environmental change detection.
    """

    def __init__(self):
        self.asf_client = ASFClient()

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
        """
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
        return scenes

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

