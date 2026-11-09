"""
Dynamic Satellite Analysis & Time-Series API Endpoints.
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Response
from pydantic import BaseModel, Field

from src.backend.services.dynamic_analysis_service import DynamicAnalysisService
from src.core.satellite_catalog import JAMUNA_DEFAULT_AOI_WKT

router = APIRouter(tags=["Dynamic Analysis & Earthdata Catalog"])
service = DynamicAnalysisService()


class CatalogSearchRequest(BaseModel):
    aoi_wkt: str = Field(default=JAMUNA_DEFAULT_AOI_WKT, description="WGS84 polygon WKT")
    start_date: str = Field(default="2024-06-01", description="Start date (YYYY-MM-DD)")
    end_date: str = Field(default="2024-07-31", description="End date (YYYY-MM-DD)")
    orbit_direction: Optional[str] = Field(default=None, description="ASCENDING or DESCENDING")
    relative_orbit: Optional[int] = Field(default=None, description="Relative orbit track number")
    max_results: int = Field(default=50, ge=1, le=200)


class AnalysisCreateRequest(BaseModel):
    aoi_wkt: str = Field(default=JAMUNA_DEFAULT_AOI_WKT, description="WGS84 polygon WKT")
    start_date: str = Field(default="2024-06-10", description="Baseline date (YYYY-MM-DD)")
    end_date: str = Field(default="2024-07-16", description="Observation date (YYYY-MM-DD)")
    mode: str = Field(default="two_date_comparison", description="'two_date_comparison' or 'multi_date_timeseries'")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    run_synchronously: bool = Field(default=True, description="Execute synchronously for testing/direct response")


@router.post("/catalog/sentinel1/search")
def search_sentinel1_catalog(req: CatalogSearchRequest):
    """
    Search NASA ASF DAAC for Sentinel-1 IW GRD observations matching area and dates.
    """
    try:
        scenes = service.search_scenes(
            aoi_wkt=req.aoi_wkt,
            start_date=req.start_date,
            end_date=req.end_date,
            orbit_direction=req.orbit_direction,
            relative_orbit=req.relative_orbit,
            max_results=req.max_results,
        )
        pairs = service.discover_pairs(
            aoi_wkt=req.aoi_wkt,
            start_date=req.start_date,
            end_date=req.end_date,
        )
        return {
            "total_scenes": len(scenes),
            "scenes": scenes,
            "compatible_pairs_count": len(pairs),
            "compatible_pairs": pairs,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Search failed: {e}")


@router.post("/analysis-requests")
def create_analysis_request(req: AnalysisCreateRequest, background_tasks: BackgroundTasks):
    """
    Submit a dynamic satellite observation and flood change analysis job.
    """
    try:
        run_record = service.create_analysis_request(
            aoi_wkt=req.aoi_wkt,
            start_date=req.start_date,
            end_date=req.end_date,
            mode=req.mode,
            parameters=req.parameters,
        )
        run_id = run_record["run_id"]

        if req.run_synchronously:
            # Execute synchronously
            summary = service.execute_analysis_run(run_id)
            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "progress_pct": 100.0,
                "summary": summary,
            }
        else:
            # Background task
            background_tasks.add_task(service.execute_analysis_run, run_id)
            return run_record

    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis submission failed: {e}")


@router.get("/analysis-requests/{run_id}")
def get_analysis_status(run_id: str):
    """
    Check real-time execution status of a dynamic analysis run.
    """
    run_dir = service.get_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Analysis run '{run_id}' not found.")

    summary_file = run_dir / "summary.json"
    error_file = run_dir / "error.json"
    req_file = run_dir / "request.json"

    req_data = json.loads(req_file.read_text()) if req_file.exists() else {}

    if summary_file.exists():
        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "progress_pct": 100.0,
            "request": req_data,
        }
    elif error_file.exists():
        err_data = json.loads(error_file.read_text())
        return {
            "run_id": run_id,
            "status": "FAILED",
            "error": err_data.get("error"),
            "request": req_data,
        }
    else:
        return {
            "run_id": run_id,
            "status": "PROCESSING",
            "progress_pct": 50.0,
            "request": req_data,
        }


@router.post("/analysis-requests/{run_id}/cancel")
def cancel_analysis_request(run_id: str):
    """Cancel an active or queued dynamic analysis run."""
    run_dir = service.get_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Analysis run '{run_id}' not found.")

    cancel_file = run_dir / "error.json"
    cancel_file.write_text(json.dumps({
        "status": "CANCELLED",
        "error": "Analysis cancelled by user.",
    }, indent=2))

    return {"run_id": run_id, "status": "CANCELLED"}


@router.get("/runs/{run_id}/summary")
def get_run_summary(run_id: str):
    """Retrieve full scientific results, transition metrics, and area accounting for run."""
    run_dir = service.get_run_dir(run_id)
    summary_file = run_dir / "summary.json"
    if not summary_file.exists():
        raise HTTPException(status_code=404, detail=f"Summary for run '{run_id}' not found or not yet completed.")

    return json.loads(summary_file.read_text())


@router.get("/runs/{run_id}/timeseries")
def get_run_timeseries(run_id: str):
    """Retrieve multi-temporal trajectory and inundation frequency stats."""
    run_dir = service.get_run_dir(run_id)
    ts_file = run_dir / "timeseries.json"
    if not ts_file.exists():
        raise HTTPException(status_code=404, detail=f"Time-series data for run '{run_id}' not available.")

    return json.loads(ts_file.read_text())


@router.get("/runs/{run_id}/rasters")
def list_run_rasters(run_id: str):
    """List all generated GeoTIFF raster assets for this run."""
    run_dir = service.get_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    rasters_dir = run_dir / "rasters"
    if not rasters_dir.exists():
        return {"run_id": run_id, "rasters": []}

    assets = []
    for f in rasters_dir.glob("*.tif"):
        assets.append({
            "asset_id": f.stem,
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "path": str(f),
            "tile_url_template": f"/api/v1/runs/{run_id}/tiles/{f.stem}/{{z}}/{{x}}/{{y}}.png",
        })

    return {"run_id": run_id, "total_rasters": len(assets), "rasters": assets}


@router.get("/runs/{run_id}/tiles/{asset_id}/{z}/{x}/{y}.png")
def render_dynamic_tile(run_id: str, asset_id: str, z: int, x: int, y: int):
    """Render XYZ PNG map tile for a run's raster layer."""
    try:
        png_bytes = service.render_tile(run_id, asset_id, z, x, y)
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tile rendering failed: {e}")


@router.get("/runs/{run_id}/vectors/{asset_id}")
def get_run_vector_geojson(run_id: str, asset_id: str):
    """Retrieve GeoJSON vector layer for this run."""
    run_dir = service.get_run_dir(run_id)
    vec_path = run_dir / "vectors" / f"{asset_id}.geojson"
    if not vec_path.exists():
        raise HTTPException(status_code=404, detail=f"Vector asset '{asset_id}' not found for run '{run_id}'.")

    return json.loads(vec_path.read_text())


@router.get("/runs/{run_id}/explanations")
def get_run_explanations(run_id: str):
    """Retrieve experimental Random Forest probabilities and Saabas XAI feature attributions."""
    run_dir = service.get_run_dir(run_id)
    exp_file = run_dir / "explanations.json"
    if not exp_file.exists():
        raise HTTPException(status_code=404, detail=f"Explanations for run '{run_id}' not available.")

    return json.loads(exp_file.read_text())
