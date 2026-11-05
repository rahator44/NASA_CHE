"""
Flood and Surface-Water Change API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from fastapi import APIRouter, HTTPException, Query
from src.backend.schemas.flood import FloodSummaryResponse, FloodTransitionsResponse, FloodClustersResponse, FloodUncertaintyResponse
from src.backend.services.flood_service import FloodService

router = APIRouter()


@router.get("/regions/{region_id}/flood/summary", response_model=FloodSummaryResponse, tags=["Flood"])
def get_flood_summary(region_id: str):
    """Retrieves whole-epoch candidate water area statistics and net flood change."""
    try:
        return FloodService.get_flood_summary(region_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Flood summary unavailable for region '{region_id}': {e}")


@router.get("/regions/{region_id}/flood/transitions", response_model=FloodTransitionsResponse, tags=["Flood"])
def get_flood_transitions(region_id: str):
    """Retrieves transition class breakdown (Persistent Water, Newly Inundated, Receded, Persistent Non-Water) over common valid domain."""
    try:
        return FloodService.get_flood_transitions(region_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Flood transitions unavailable for region '{region_id}': {e}")


@router.get("/regions/{region_id}/flood/clusters", response_model=FloodClustersResponse, tags=["Flood"])
def get_flood_clusters(
    region_id: str,
    limit: int = Query(15, ge=1, le=100, description="Maximum number of major clusters to return")
):
    """Retrieves major contiguous inundation clusters with geographic centroids and area accounting."""
    try:
        return FloodService.get_flood_clusters(region_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Flood clusters unavailable for region '{region_id}': {e}")


@router.get("/regions/{region_id}/flood/uncertainty", response_model=FloodUncertaintyResponse, tags=["Flood"])
def get_flood_uncertainty(region_id: str):
    """Retrieves quality mask exclusions, radar shadow/layover noise floor, and classification confidence tiers."""
    try:
        return FloodService.get_flood_uncertainty(region_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Flood uncertainty unavailable for region '{region_id}': {e}")

