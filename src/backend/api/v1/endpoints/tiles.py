"""
XYZ Map Tile API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from fastapi import APIRouter, HTTPException, Response, Path
from src.backend.services.raster_service import RasterService, RASTER_CATALOG

router = APIRouter()


@router.get(
    "/tiles/{asset_id}/{z}/{x}/{y}.png",
    response_class=Response,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "256x256 RGBA PNG Map Tile in EPSG:3857 Web Mercator",
        }
    },
    tags=["Map Tiles"],
)
def get_map_tile(
    asset_id: str = Path(..., description="Raster asset identifier from catalog"),
    z: int = Path(..., ge=0, le=20, description="Zoom level"),
    x: int = Path(..., ge=0, description="Tile X coordinate"),
    y: int = Path(..., ge=0, description="Tile Y coordinate"),
):
    """
    Renders an XYZ Web Mercator 256x256 PNG map tile for interactive GIS mapping.
    Uses nearest-neighbor resampling for categorical flood masks and bilinear for continuous rasters.
    Returns transparent PNG if tile falls outside the asset's bounding box.
    """
    lookup = RasterService._lookup_asset(asset_id)
    if not lookup:
        raise HTTPException(status_code=404, detail=f"Raster asset '{asset_id}' not found in catalog.")

    resolved_id, _ = lookup
    try:
        png_bytes = RasterService.render_tile(resolved_id, z, x, y)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tile rendering failed for '{asset_id}': {e}")
    return Response(content=png_bytes, media_type="image/png")
