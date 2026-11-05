"""
Region API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class BoundingPolygon(BaseModel):
    wkt: str
    crs: str
    coordinates_wgs84: List[List[float]]


class RegionSummaryResponse(BaseModel):
    region_id: str
    name: str
    country: str
    description: str
    river_system: str
    crs: str
    spatial_resolution_m: float
    raster_dimensions: List[int]
    available_acquisitions: List[str]
    available_analysis_modules: List[str]


class RegionDetailResponse(RegionSummaryResponse):
    bounding_box: Dict[str, float]
    bounding_polygon: BoundingPolygon
    hydrological_regime: str
    morphological_classification: str
    baseline_classifier: str


class RegionListResponse(BaseModel):
    total_regions: int
    regions: List[RegionSummaryResponse]

