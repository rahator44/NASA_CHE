"""
Common API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "EarthPulse-SAR Scientific API"
    version: str = "1.0.0"
    study_area: str = "Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)"


class SystemStatusResponse(BaseModel):
    status: str
    uptime_utc: str
    environment: Dict[str, Any]
    hardware: Dict[str, Any]
    database: Dict[str, Any]
    active_jobs_count: int


class SystemCapabilitiesResponse(BaseModel):
    service_name: str
    version: str
    study_area_focused: str
    core_modules: List[str]
    supported_sensors: List[str]
    raster_tile_engine: str
    provenance_tracking: bool
    scientific_baselines: Dict[str, str]


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: int = 400

