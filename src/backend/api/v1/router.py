"""
Earth Pulse API v1 Router Aggregator
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from fastapi import APIRouter
from src.backend.api.v1.endpoints import (
    system,
    regions,
    datasets,
    analyses,
    flood,
    riverbank,
    models,
    rasters,
    vectors,
    tiles,
    reports,
    jobs,
    dynamic_analysis,
)

api_v1_router = APIRouter()

# Include sub-routers under /api/v1
api_v1_router.include_router(system.router)
api_v1_router.include_router(regions.router)
api_v1_router.include_router(datasets.router)
api_v1_router.include_router(analyses.router)
api_v1_router.include_router(flood.router)
api_v1_router.include_router(riverbank.router)
api_v1_router.include_router(models.router)
api_v1_router.include_router(rasters.router)
api_v1_router.include_router(vectors.router)
api_v1_router.include_router(tiles.router)
api_v1_router.include_router(reports.router)
api_v1_router.include_router(jobs.router)
api_v1_router.include_router(dynamic_analysis.router)

