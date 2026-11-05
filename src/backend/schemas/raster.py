"""
Raster and Vector Asset API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class RasterAssetResponse(BaseModel):
    asset_id: str
    region_id: str
    analysis_id: Optional[str] = None
    layer_name: str
    layer_type: str  # categorical, continuous, mask
    acquisition_date: Optional[str] = None
    file_format: str
    crs: str
    bounds_epsg3857: List[float]
    bounds_native: List[float]
    dimensions: List[int]
    pixel_spacing_m: List[float]
    nodata_value: Optional[float] = None
    band_count: int
    data_type: str
    description: str


class RasterMetadataResponse(BaseModel):
    asset_id: str
    driver: str
    width: int
    height: int
    count: int
    dtype: str
    nodata: Optional[float]
    crs: str
    transform: List[float]
    bounds: Dict[str, float]


class RasterBandStats(BaseModel):
    band_index: int
    min: float
    max: float
    mean: float
    std: float
    valid_pixel_count: int


class RasterStatsResponse(BaseModel):
    asset_id: str
    bands: List[RasterBandStats]


class VectorAssetResponse(BaseModel):
    asset_id: str
    region_id: str
    vector_type: str
    feature_count: int
    crs: str
    geojson: Dict[str, Any]

