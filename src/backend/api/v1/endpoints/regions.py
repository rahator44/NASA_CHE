"""
Regions API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from fastapi import APIRouter, HTTPException
from src.backend.schemas.region import RegionListResponse, RegionDetailResponse, RegionSummaryResponse
from src.backend.services.region_service import RegionService

router = APIRouter()


@router.get("/regions", response_model=RegionListResponse, tags=["Regions"])
def get_regions():
    """Lists all registered regions available for analysis."""
    regions = RegionService.list_regions()
    return RegionListResponse(
        total_regions=len(regions),
        regions=regions,
    )


@router.get("/regions/{region_id}", response_model=RegionDetailResponse, tags=["Regions"])
def get_region_detail(region_id: str):
    """Retrieves full geographic, coordinate reference, and bounding geometry for a specified region."""
    res = RegionService.get_region_detail(region_id)
    if not res:
        raise HTTPException(
            status_code=404,
            detail=f"Region '{region_id}' not found. Authoritative registered study areas: ['jamuna_sirajganj']"
        )
    return res


@router.get("/regions/{region_id}/summary", response_model=RegionSummaryResponse, tags=["Regions"])
def get_region_summary(region_id: str):
    """Retrieves high-level summary of study area, dimensions, and available modules."""
    res = RegionService.get_region_detail(region_id)
    if not res:
        raise HTTPException(
            status_code=404,
            detail=f"Region '{region_id}' not found. Authoritative registered study areas: ['jamuna_sirajganj']"
        )
    return RegionSummaryResponse(**res)

