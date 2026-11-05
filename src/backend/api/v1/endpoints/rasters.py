"""
Raster Asset Catalog & Metadata API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from src.backend.schemas.raster import RasterAssetResponse, RasterMetadataResponse, RasterStatsResponse
from src.backend.services.raster_service import RasterService

router = APIRouter()


@router.get("/rasters", response_model=List[RasterAssetResponse], tags=["Rasters"])
def list_rasters(region_id: Optional[str] = Query(None, description="Filter by region")):
    """Lists safe raster assets available in the catalog with spatial extents and layer descriptions."""
    return RasterService.list_assets(region_id=region_id)


@router.get("/rasters/{asset_id}/metadata", response_model=RasterMetadataResponse, tags=["Rasters"])
def get_raster_metadata(asset_id: str):
    """Retrieves GeoTIFF driver metadata, bounding coordinates, affine transform, and data types."""
    meta = RasterService.get_metadata(asset_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Raster asset '{asset_id}' not found.")
    return meta


@router.get("/rasters/{asset_id}/statistics", response_model=RasterStatsResponse, tags=["Rasters"])
def get_raster_statistics(asset_id: str):
    """Computes band min, max, mean, standard deviation, and valid pixel counts."""
    stats = RasterService.get_statistics(asset_id)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Raster asset '{asset_id}' not found.")
    return stats

