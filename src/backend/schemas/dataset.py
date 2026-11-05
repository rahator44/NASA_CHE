"""
Dataset and Provenance API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field


class DatasetRecordResponse(BaseModel):
    dataset_id: str
    region_id: str
    sensor: str
    satellite: str
    acquisition_date: str
    product_type: str
    processing_level: str
    polarization: Optional[Union[str, List[str]]] = None
    spatial_resolution_m: float
    crs: str
    quality_status: str
    checksum_verified: bool
    sha256: Optional[str] = None
    file_format: str
    relative_path: str


class DatasetListResponse(BaseModel):
    total_datasets: int
    datasets: List[DatasetRecordResponse]
