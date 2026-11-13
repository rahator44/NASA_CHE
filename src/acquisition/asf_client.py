"""
NASA Alaska Satellite Facility (ASF) DAAC Client.
NASA Space Apps Challenge 2026: Dancing with the SARs

Handles communication with the ASF Search API and Sentinel-1 data services.
All search operations are unauthenticated by default.
Authenticated requests utilize EarthdataSessionManager (Bearer Token or .netrc).
"""

import sys
import math
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np

# Ensure workspace-vendored packages are accessible if present
_LOCAL_PACKAGES = Path(__file__).resolve().parent.parent.parent / ".packages"
if _LOCAL_PACKAGES.exists() and str(_LOCAL_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_LOCAL_PACKAGES))

from src.core.earthdata_auth import EarthdataSessionManager
from src.acquisition.scene_selector import validate_relative_orbit

try:
    import asf_search as asf
    _HAS_ASF_SEARCH = True
except ImportError:
    asf = None
    _HAS_ASF_SEARCH = False

import json
import requests
from osgeo import ogr

logger = logging.getLogger("EarthPulse.ASFClient")

ASF_SEARCH_API_ENDPOINT = "https://api.daac.asf.alaska.edu/services/search/param"

# Valid metadata values for Sentinel-1 IW GRD SAR scenes used in Earth Pulse
VALID_ORBIT_DIRECTIONS = {"ASCENDING", "DESCENDING"}
VALID_POLARIZATIONS = {"VV+VH", "VV VH", "VV, VH"}  # common ASF representations of dual-pol
REQUIRED_BEAM_MODE = "IW"
REQUIRED_PROCESSING_LEVEL = "GRD_HD"


def validate_scene_metadata(scene: Dict[str, Any], scene_source: str = "") -> List[str]:
    """
    Validate that a scene dict has all required scientifically-meaningful metadata fields.
    Returns a list of rejection reasons (empty list means the scene is valid).

    Rules enforced:
    - aoi_coverage_pct must be > 0.0 (missing/zero coverage is rejected)
    - acquisition_time must be a parseable ISO8601 string
    - relative_orbit must not be None
    - orbit_direction must be ASCENDING or DESCENDING
    - polarization must contain both VV and VH channels
    - beam_mode must be IW
    - processing_level must be GRD_HD
    """
    rejections = []

    # Coverage: fail-closed — 0.0, missing, or NaN means no scientifically usable intersection
    cov = scene.get("aoi_coverage_pct")
    if cov is None:
        rejections.append(
            f"[{scene_source}] aoi_coverage_pct is missing. "
            "Coverage must NEVER default to 100%; strict fail-closed policy applies."
        )
    else:
        try:
            cov_f = float(cov)
            if not np.isfinite(cov_f) or cov_f <= 0.0 or cov_f > 100.0:
                rejections.append(
                    f"[{scene_source}] aoi_coverage_pct={cov!r} — invalid coverage percentage (must be finite float in 0.0-100.0). "
                    "Coverage must NEVER default to 100%; strict fail-closed policy applies."
                )
        except (ValueError, TypeError):
            rejections.append(f"[{scene_source}] aoi_coverage_pct={cov!r} is unparseable.")

    # Acquisition timestamp must be parseable
    acq_time = scene.get("acquisition_time", "")
    if not acq_time:
        rejections.append(f"[{scene_source}] acquisition_time is missing.")
    else:
        try:
            datetime.fromisoformat(str(acq_time).replace("Z", "+00:00").replace(" ", "T"))
        except (ValueError, TypeError):
            rejections.append(
                f"[{scene_source}] acquisition_time='{acq_time}' is not a valid ISO8601 timestamp."
            )

    # Relative orbit (track number) required for repeat-pass comparability
    rel_orbit = scene.get("relative_orbit")
    is_valid_orbit, _, orbit_err = validate_relative_orbit(rel_orbit)
    if not is_valid_orbit:
        rejections.append(
            f"[{scene_source}] Invalid relative_orbit ({rel_orbit!r}): {orbit_err}. "
            "Cannot guarantee repeat-pass geometry for SAR comparison."
        )

    # Flight direction must be explicit and valid
    orbit_dir = str(scene.get("orbit_direction", "")).upper()
    if orbit_dir not in VALID_ORBIT_DIRECTIONS:
        rejections.append(
            f"[{scene_source}] orbit_direction='{orbit_dir}' is not in {VALID_ORBIT_DIRECTIONS}."
        )

    # Dual polarization required (VV+VH)
    pol = str(scene.get("polarization", "")).upper()
    has_vh = "VH" in pol
    has_vv = "VV" in pol
    if not (has_vh and has_vv):
        rejections.append(
            f"[{scene_source}] polarization='{pol}' does not contain both VV and VH channels. "
            "Earth Pulse requires dual-polarization IW GRD (VV+VH)."
        )

    # Beam mode must be IW
    beam_mode = scene.get("beam_mode", "")
    if str(beam_mode).upper() != REQUIRED_BEAM_MODE:
        rejections.append(
            f"[{scene_source}] beam_mode='{beam_mode}', expected '{REQUIRED_BEAM_MODE}'."
        )

    # Processing level must be GRD_HD
    proc_level = scene.get("processing_level", "")
    if str(proc_level).upper() not in (REQUIRED_PROCESSING_LEVEL, "GRD_HD"):
        rejections.append(
            f"[{scene_source}] processing_level='{proc_level}', expected '{REQUIRED_PROCESSING_LEVEL}'."
        )

    return rejections


def parse_geometry(geom_input: Any) -> Optional[ogr.Geometry]:
    """
    Parse geometry from WKT string, GeoJSON string, or GeoJSON dict into an OGR Geometry.
    Fails closed and returns None on any malformed or invalid input.
    """
    if not geom_input:
        return None
    try:
        if isinstance(geom_input, dict):
            return ogr.CreateGeometryFromJson(json.dumps(geom_input))
        if isinstance(geom_input, str):
            s = geom_input.strip()
            if s.startswith("{"):
                try:
                    return ogr.CreateGeometryFromJson(s)
                except Exception:
                    pass
            if s.startswith(("POLYGON", "MULTIPOLYGON", "POINT", "LINESTRING", "GEOMETRYCOLLECTION")):
                return ogr.CreateGeometryFromWkt(s)
            try:
                import ast
                d = ast.literal_eval(s)
                if isinstance(d, dict):
                    return ogr.CreateGeometryFromJson(json.dumps(d))
            except Exception:
                pass
    except Exception as ex:
        logger.debug("Failed to parse geometry: %s", ex)
    return None


def export_geometry_to_wkt(geom_input: Any) -> str:
    """Safely convert any valid geometry representation to standard WKT string."""
    geom = parse_geometry(geom_input)
    if geom is not None and geom.IsValid():
        return geom.ExportToWkt()
    return ""


def _compute_aoi_coverage_pct(aoi_wkt: str, footprint_input: Any) -> float:
    """
    Calculate actual intersection coverage percentage between AOI and scene footprint.
    Fail-closed policy: strictly returns 0.0 if footprint is missing, invalid, disjoint, or unparseable.
    """
    if not aoi_wkt or not footprint_input:
        return 0.0
    try:
        g_aoi = parse_geometry(aoi_wkt)
        g_scene = parse_geometry(footprint_input)
        if g_aoi is None or g_scene is None or not g_aoi.IsValid() or not g_scene.IsValid():
            return 0.0
        area_aoi = g_aoi.GetArea()
        if area_aoi <= 0:
            return 0.0
        intersection = g_aoi.Intersection(g_scene)
        if intersection is None or intersection.IsEmpty():
            return 0.0
        area_inter = intersection.GetArea()
        pct = (area_inter / area_aoi) * 100.0
        return float(min(100.0, max(0.0, round(pct, 2))))
    except Exception as ex:
        logger.warning("Failed to calculate AOI coverage percentage (failing closed to 0.0%%): %s", ex)
        return 0.0


class ASFClient:
    """
    Client for NASA ASF DAAC satellite search and metadata discovery.
    """

    @classmethod
    def search_scenes(
        cls,
        wkt_polygon: str,
        start_date: str,
        end_date: str,
        platform: str = "SENTINEL-1",
        processing_level: str = "GRD_HD",
        beam_mode: str = "IW",
        polarization: Optional[str] = "VV+VH",
        flight_direction: Optional[str] = None,
        relative_orbit: Optional[int] = None,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search for Sentinel-1 products matching geographic polygon and time range.
        Unauthenticated public search.
        """
        # Normalize date-only strings (YYYY-MM-DD) to cover the complete 24-hour acquisition window
        norm_start = f"{start_date}T00:00:00Z" if len(start_date) == 10 and "T" not in start_date else start_date
        norm_end = f"{end_date}T23:59:59Z" if len(end_date) == 10 and "T" not in end_date else end_date

        # Try official asf_search python package first
        if _HAS_ASF_SEARCH:
            try:
                opts = {
                    "intersectsWith": wkt_polygon,
                    "platform": asf.PLATFORM.SENTINEL1,
                    "processingLevel": asf.PRODUCT_TYPE.GRD_HD,
                    "beamMode": asf.BEAMMODE.IW,
                    "start": norm_start,
                    "end": norm_end,
                    "maxResults": max_results,
                }
                if polarization:
                    opts["polarization"] = polarization
                if flight_direction:
                    opts["flightDirection"] = flight_direction.upper()
                if relative_orbit:
                    opts["relativeOrbit"] = relative_orbit

                results = asf.geo_search(**opts)
                scenes = []
                for r in results:
                    props = r.properties
                    wkt_str = export_geometry_to_wkt(r.geometry)
                    cov_pct = _compute_aoi_coverage_pct(wkt_polygon, r.geometry)
                    scenes.append({
                        "scene_name": props.get("sceneName", ""),
                        "platform": props.get("platform", "Sentinel-1"),
                        "sensor": "C-SAR",
                        "acquisition_time": props.get("startTime", ""),
                        "orbit_direction": props.get("flightDirection", "").upper(),
                        "relative_orbit": props.get("pathNumber"),
                        "polarization": props.get("polarization"),
                        "beam_mode": props.get("beamModeType"),
                        "processing_level": props.get("processingLevel"),
                        "download_url": props.get("url", ""),
                        "size_mb": float(props.get("bytes", 0)) / (1024 * 1024) if props.get("bytes") else 0.0,
                        "wkt_geometry": wkt_str,
                        "aoi_coverage_pct": cov_pct,
                    })
                # Apply strict metadata validation filter (Correction D)
                valid_scenes = []
                for sc in scenes:
                    rejections = validate_scene_metadata(sc, scene_source=sc.get("scene_name", "asf_search"))
                    if rejections:
                        logger.info("Filtered scene '%s': %s", sc.get("scene_name"), "; ".join(rejections))
                    else:
                        valid_scenes.append(sc)
                if len(scenes) != len(valid_scenes):
                    logger.info("Scene metadata filter: %d/%d scenes passed validation", len(valid_scenes), len(scenes))
                if valid_scenes:
                    return valid_scenes
            except Exception as e:
                logger.warning("asf_search failed, falling back to HTTP API: %s", e)

        # Fallback to direct ASF Search REST API
        try:
            params = {
                "intersectsWith": wkt_polygon,
                "platform": platform,
                "processingLevel": processing_level,
                "beamMode": beam_mode,
                "start": norm_start,
                "end": norm_end,
                "output": "json",
                "maxResults": max_results,
            }
            if polarization:
                params["polarization"] = polarization
            if flight_direction:
                params["flightDirection"] = flight_direction.upper()
            if relative_orbit:
                params["relativeOrbit"] = relative_orbit

            resp = requests.get(ASF_SEARCH_API_ENDPOINT, params=params, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                # If nested list [ [ {item1}, {item2} ] ]
                items = data[0] if data and isinstance(data[0], list) else data
                scenes = []
                for item in items:
                    raw_footprint = item.get("stringFootprint") or item.get("geometry")
                    wkt_str = export_geometry_to_wkt(raw_footprint)
                    cov_pct = _compute_aoi_coverage_pct(wkt_polygon, raw_footprint)
                    scenes.append({
                        "scene_name": item.get("sceneName", item.get("granuleName", "")),
                        "platform": item.get("platform", "Sentinel-1"),
                        "sensor": "C-SAR",
                        "acquisition_time": item.get("startTime", ""),
                        "orbit_direction": item.get("flightDirection", "").upper(),
                        "relative_orbit": int(item.get("pathNumber", 0)) if item.get("pathNumber") else None,
                        "polarization": item.get("polarization"),
                        "beam_mode": item.get("beamModeType") or item.get("beamMode"),
                        "processing_level": item.get("processingLevel"),
                        "download_url": item.get("downloadUrl", ""),
                        "size_mb": float(item.get("bytes", 0)) / (1024 * 1024) if item.get("bytes") else 0.0,
                        "wkt_geometry": wkt_str,
                        "aoi_coverage_pct": cov_pct,
                    })
                # Apply strict metadata validation filter (Correction D)
                valid_scenes = []
                for sc in scenes:
                    rejections = validate_scene_metadata(sc, scene_source=sc.get("scene_name", "http_api"))
                    if rejections:
                        logger.info("Filtered scene '%s': %s", sc.get("scene_name"), "; ".join(rejections))
                    else:
                        valid_scenes.append(sc)
                if len(scenes) != len(valid_scenes):
                    logger.info("Scene metadata filter: %d/%d scenes passed validation", len(valid_scenes), len(scenes))
                if valid_scenes:
                    return valid_scenes
        except Exception as e:
            logger.warning("Direct ASF HTTP API failed: %s", e)

        # No synthetic fallback in production: if online providers are unreachable or return no items,
        # return empty list rather than hardcoded historical dates.
        logger.info("ASF search completed; 0 observations found or provider unreachable.")
        return []

