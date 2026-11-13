"""
Earth Pulse Backend API Application
NASA Space Apps Challenge 2026: Dancing with the SARs

Provides high-throughput, structured scientific data services for the Jamuna River
flood-change detection, riverbank migration, and explainable AI application.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from src.backend.config import settings
from src.backend.database.database import init_db
from src.backend.api.v1.router import api_v1_router
from src.backend.schemas.common import HealthResponse

logger = logging.getLogger("src.backend.main")

FRONTEND_DIST = settings.PROJECT_ROOT_DIR / "frontend" / "dist"


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


# Mount static assets if frontend distribution exists
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


# Root-level endpoint: serves index.html for browsers (accept: text/html), JSON for API consumers
@app.get("/", tags=["System"])
def root(request: Request):
    """Root endpoint returning SPA web interface or API identification."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept and FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")
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


# Mount SPA fallback for client-side routing (/explorer, /comparison, /explainable-ai, /science, /new-analysis)
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json", "health"):
            raise HTTPException(status_code=404, detail=f"Endpoint '{full_path}' not found")
        try:
            target = (FRONTEND_DIST / full_path).resolve()
            if target.is_file() and target.is_relative_to(FRONTEND_DIST.resolve()):
                return FileResponse(target)
        except (ValueError, RuntimeError):
            pass
        return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.backend.main:app", host="127.0.0.1", port=8000, reload=False)
