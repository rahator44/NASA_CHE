"""
System & Health API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from datetime import datetime, timezone
import sys
from fastapi import APIRouter
from src.backend.schemas.common import HealthResponse, SystemStatusResponse, SystemCapabilitiesResponse
from src.backend.config import settings
from src.backend.services.job_service import JobService

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
def get_health():
    """Health check endpoint for the Earth Pulse API."""
    return HealthResponse(
        status="healthy",
        service="EarthPulse-SAR Scientific API",
        version=settings.PROJECT_VERSION,
        study_area="Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)",
    )


@router.get("/system/status", response_model=SystemStatusResponse, tags=["System"])
def get_system_status():
    """Returns current environment hardware, software versions, and SQLite database status."""
    import numpy as np
    import scipy
    import pandas as pd
    from osgeo import gdal

    jobs = JobService.list_jobs(limit=100)
    active_jobs = sum(1 for j in jobs if j["status"] in ("PENDING", "RUNNING"))

    return SystemStatusResponse(
        status="OPERATIONAL",
        uptime_utc=datetime.now(timezone.utc).isoformat(),
        environment={
            "python_version": sys.version.split()[0],
            "gdal_version": gdal.__version__,
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
            "pandas_version": pd.__version__,
            "fastapi_available": True,
        },
        hardware={
            "os": "Linux",
            "cpu_architecture": "x86_64 (Intel 12th Gen)",
            "memory_ram_gb": 16,
            "acceleration": "CPU-only",
        },
        database={
            "engine": "SQLite3",
            "path": str(settings.SQLITE_DB_PATH.name),
            "status": "CONNECTED",
            "persisted_jobs_count": len(jobs),
        },
        active_jobs_count=active_jobs,
    )


@router.get("/system/capabilities", response_model=SystemCapabilitiesResponse, tags=["System"])
def get_system_capabilities():
    """Enumerates core capabilities, supported sensors, and scientific baselines."""
    return SystemCapabilitiesResponse(
        service_name=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        study_area_focused="Jamuna River (Kazipur / Sirajganj, Bangladesh)",
        core_modules=[
            "SAR Alignment & Sub-Pixel Co-Registration",
            "Calibrated Radiometric Backscatter Differencing (VV, VH, CR)",
            "Adaptive Lee Speckle Filtering & ENL Optimization",
            "Deterministic Dual-AND Otsu Flood Inundation Mapping",
            "Common-Valid-Domain Surface Water Transition Accounting",
            "Fluvial Riverbank Migration & 200m Transect Displacement",
            "Supervised Pure-NumPy Random Forest Candidate Water Probability",
            "Saabas Path-Dependent Tree Feature Attribution",
            "Scientific Uncertainty Budgeting & Quadrature Error Modeling",
            "XYZ Web Mercator Dynamic Map Tile Generation",
        ],
        supported_sensors=[
            "Sentinel-1 C-Band SAR (IW GRD, VV+VH)",
            "Sentinel-2 Optical MSI (SCL, MNDWI, AWEI Validation Reference)",
        ],
        raster_tile_engine="Native GDAL Warp Reprojection (EPSG:32645 -> EPSG:3857) + PIL RGBA Encoding",
        provenance_tracking=True,
        scientific_baselines={
            "primary_operational_flood_baseline": "Adaptive Lee 5x5 Dual-AND Otsu (VV & VH)",
            "secondary_auxiliary_probability_layer": "Pure-NumPy Random Forest (tau* = 0.35, status: RETAINED_AS_PROBABILITY_LAYER)",
            "primary_riverbank_analysis": "Automated 200m Normal Transects on Filtered SAR Channel Belts (Total: 154, Valid: 122, Outside Valid-Local: 32)",
        },
    )
