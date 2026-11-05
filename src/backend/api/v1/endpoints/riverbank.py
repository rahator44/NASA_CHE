"""
Riverbank Migration & Displacement API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from fastapi import APIRouter, HTTPException, Query
from src.backend.schemas.riverbank import (
    RiverbankSummaryResponse,
    TransectsListResponse,
    DisplacementResponse,
    ErosionCandidatesResponse,
    RiverbankUncertaintyResponse,
)
from src.backend.services.riverbank_service import RiverbankService

router = APIRouter()


@router.get("/regions/{region_id}/riverbank/summary", response_model=RiverbankSummaryResponse, tags=["Riverbank"])
def get_riverbank_summary(region_id: str):
    """Retrieves overall riverbank migration, lateral displacement, and channel-width expansion statistics."""
    try:
        return RiverbankService.get_riverbank_summary(region_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Riverbank summary unavailable for region '{region_id}': {e}")


@router.get("/regions/{region_id}/riverbank/transects", response_model=TransectsListResponse, tags=["Riverbank"])
def get_transects(
    region_id: str,
    limit: int = Query(200, ge=1, le=500, description="Max transects to return"),
    only_valid: bool = Query(False, description="Filter to only audited valid transects"),
):
    """Retrieves 200m-spaced orthogonal sampling transects with displacement measurements and ambiguity flags."""
    try:
        return RiverbankService.get_transects(region_id, limit=limit, only_valid=only_valid)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Transects unavailable for region '{region_id}': {e}")


@router.get("/regions/{region_id}/riverbank/displacement", response_model=DisplacementResponse, tags=["Riverbank"])
def get_displacement_stats(region_id: str):
    """Retrieves empirical displacement distributions and spatial bootstrap confidence intervals for right and left banks."""
    try:
        return RiverbankService.get_displacement_stats(region_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Displacement stats unavailable for region '{region_id}': {e}")


@router.get("/regions/{region_id}/riverbank/erosion-candidates", response_model=ErosionCandidatesResponse, tags=["Riverbank"])
def get_erosion_candidates(region_id: str):
    """Retrieves classified candidate bank expansion zones and char submergence areas."""
    try:
        return RiverbankService.get_erosion_candidates(region_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Erosion candidates unavailable for region '{region_id}': {e}")


@router.get("/regions/{region_id}/riverbank/uncertainty", response_model=RiverbankUncertaintyResponse, tags=["Riverbank"])
def get_riverbank_uncertainty(region_id: str):
    """Retrieves quadrature error budget, minimum detectable displacement threshold, and hydrodynamic caveats."""
    try:
        return RiverbankService.get_riverbank_uncertainty(region_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Riverbank uncertainty unavailable for region '{region_id}': {e}")

