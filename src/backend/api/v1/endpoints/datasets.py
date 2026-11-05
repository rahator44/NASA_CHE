"""
Datasets API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from src.backend.schemas.dataset import DatasetListResponse, DatasetRecordResponse
from src.backend.services.dataset_service import DatasetService

router = APIRouter()


@router.get("/datasets", response_model=DatasetListResponse, tags=["Datasets"])
def list_datasets(
    region_id: Optional[str] = Query(None, description="Filter by region identifier"),
    sensor: Optional[str] = Query(None, description="Filter by satellite sensor (e.g. Sentinel-1, Sentinel-2)"),
    acquisition_date: Optional[str] = Query(None, description="Filter by acquisition date prefix (e.g. 2024-06-10)"),
    product_type: Optional[str] = Query(None, description="Filter by product type (e.g. GRD, SCL, FILTERED)"),
    quality_status: Optional[str] = Query(None, description="Filter by quality status (e.g. VERIFIED)"),
):
    """Retrieves safe registered dataset inventory with optional metadata filters."""
    datasets = DatasetService.list_datasets(
        region_id=region_id,
        sensor=sensor,
        acquisition_date=acquisition_date,
        product_type=product_type,
        quality_status=quality_status,
    )
    return DatasetListResponse(total_datasets=len(datasets), datasets=datasets)


@router.get("/datasets/{dataset_id}", response_model=DatasetRecordResponse, tags=["Datasets"])
def get_dataset(dataset_id: str):
    """Retrieves detailed provenance, spatial reference, and checksum status for a dataset."""
    ds = DatasetService.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")
    return ds


@router.get("/regions/{region_id}/datasets", response_model=DatasetListResponse, tags=["Datasets"])
def get_region_datasets(region_id: str):
    """Retrieves all registered datasets associated with a specific region."""
    datasets = DatasetService.list_datasets(region_id=region_id)
    return DatasetListResponse(total_datasets=len(datasets), datasets=datasets)

