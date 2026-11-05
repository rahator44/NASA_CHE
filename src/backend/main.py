"""
Earth Pulse Backend API Application
NASA Space Apps Challenge 2026: Dancing with the SARs

Provides high-throughput, structured scientific data services for the Jamuna River
flood-change detection, riverbank migration, and explainable AI application.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.backend.config import settings
from src.backend.database.database import init_db
from src.backend.api.v1.router import api_v1_router
from src.backend.schemas.common import HealthResponse

logger = logging.getLogger("src.backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize SQLite database and seed catalog
    init_db()
    yield
    # Shutdown logic if needed


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=(
        "Backend API and scientific data-service foundation for the Earth Pulse application. "
        "Provides structured access to Sentinel-1 SAR flood inundation accounting, automated "
        "200m riverbank displacement transects, pure-NumPy Random Forest candidate water probabilities, "
        "Saabas path-dependent tree explainability, and dynamic XYZ Web Mercator map tiles."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Global sanitized error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled server error processing %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "detail": "An internal server error occurred while processing the request.",
            "code": 500,
            "path": str(request.url.path),
        },
    )


# Root-level health endpoint
@app.get("/", tags=["System"])
def root():
    """Root endpoint returning API service identification and navigation links."""
    return {
        "title": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "docs_url": "/docs",
        "api_v1_prefix": settings.API_V1_STR,
        "study_area": "Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)",
    }


@app.get("/health", response_model=HealthResponse, tags=["System"])
def root_health():
    """Root health check endpoint for the Earth Pulse API."""
    return HealthResponse(
        status="healthy",
        service="EarthPulse-SAR Scientific API",
        version=settings.PROJECT_VERSION,
        study_area="Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)",
    )


# Versioned API routes under /api/v1
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.backend.main:app", host="127.0.0.1", port=8000, reload=False)
