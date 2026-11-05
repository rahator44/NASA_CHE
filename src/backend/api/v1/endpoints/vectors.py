"""
Vector Asset API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from src.backend.schemas.raster import VectorAssetResponse
from src.backend.services.vector_service import VectorService

router = APIRouter()


@router.get("/vectors", tags=["Vectors"])
def list_vectors(region_id: Optional[str] = Query(None, description="Filter by region")):
    """Lists safe vector assets available in the catalog with standard EPSG:4326 reprojection."""
    return VectorService.list_vector_assets(region_id=region_id)


@router.get("/vectors/{asset_id}", response_model=VectorAssetResponse, tags=["Vectors"])
def get_vector_geojson(asset_id: str):
    """Retrieves standard GeoJSON feature collection (EPSG:4326) for a registered vector asset."""
    result = VectorService.get_vector_geojson(asset_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Vector asset '{asset_id}' not found.")

    geo, info = result
    return VectorAssetResponse(
        asset_id=asset_id,
        region_id=info.get("region_id", "jamuna_sirajganj"),
        vector_type=info.get("vector_type", asset_id),
        feature_count=len(geo.get("features", [])),
        crs="EPSG:4326",
        native_crs=info.get("native_crs", "EPSG:32645"),
        geojson=geo,
    )
