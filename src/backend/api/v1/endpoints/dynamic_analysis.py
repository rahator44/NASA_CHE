"""
Dynamic Satellite Analysis & Time-Series API Endpoints.
NASA Space Apps Challenge 2026: Dancing with the SARs

ARCHITECTURE NOTE - BACKGROUND TASK LIFECYCLE & RECOVERY:
FastAPI `BackgroundTasks` execute asynchronously inside the ASGI worker process threadpool.
If the server process crashes, restarts, or is redeployed during execution, active tasks
running under `BackgroundTasks` will terminate abruptly without automatic state recovery,
leaving job records in intermediate states (e.g., 'DOWNLOADING' or 'PREPROCESSING').
For mission-critical production deployments requiring durable cross-restart worker execution,
persistent state hydration, and distributed task queues, an external broker (Celery + Redis/RabbitMQ)
is recommended. DynamicAnalysisService persists run parameters in `request.json` and SQLite, allowing
manual or scheduled resumption of uncompleted runs.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Response
from pydantic import BaseModel, Field

from src.backend.services.dynamic_analysis_service import DynamicAnalysisService, atomic_write_json
from src.backend.database.database import get_db_connection
from src.backend.config import settings
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
    # Correction G: default is async (False) to avoid blocking API requests.
    # Set run_synchronously=True only for unit testing or single-threaded local dev.
    # Production use must leave this False and poll /analysis-requests/{run_id} for status.
    run_synchronously: bool = Field(
        default=False,
        description=(
            "Execute synchronously and block until complete (for testing only). "
            "Default is False — submit async and poll /analysis-requests/{run_id}."
        ),
    )


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
    if settings.DEMO_MODE_RESTRICTED_EXECUTION:
        raise HTTPException(
            status_code=403,
            detail=(
                "Analysis job submission is restricted in public demo mode to protect host compute. "
                "Precomputed scientific runs are available via GET /api/v1/runs/{run_id}. "
                "To enable dynamic acquisition and processing, set DEMO_MODE_RESTRICTED_EXECUTION=false "
                "in a private or authenticated environment."
            ),
        )

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
            # Correction G: check actual returned status — do not override CANCELLED with COMPLETED
            returned_status = summary.get("status", "COMPLETED")
            if returned_status == "CANCELLED":
                return {
                    "run_id": run_id,
                    "status": "CANCELLED",
                    "progress_pct": summary.get("progress_pct", 0.0),
                    "error": summary.get("error", "Analysis was cancelled."),
                    "summary": summary,
                }
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
    Uses the SQLite status ledger as the authoritative source of truth.
    """
    run_dir = service.get_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Analysis run '{run_id}' not found.")

    summary_file = run_dir / "summary.json"
    error_file = run_dir / "error.json"
    req_file = run_dir / "request.json"

    req_data = {}
    if req_file.exists():
        try:
            req_data = json.loads(req_file.read_text())
        except Exception:
            pass

    # 1. Authoritative check via SQLite ledger
    db_row = None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, metadata, completed_at FROM analysis_runs WHERE run_id = ?", (run_id,))
        db_row = cursor.fetchone()

    if db_row:
        db_status = db_row[0]
        meta = {}
        if db_row[1]:
            try:
                meta = json.loads(db_row[1]) if isinstance(db_row[1], str) else db_row[1]
            except Exception:
                meta = {}

        if db_status == "COMPLETED":
            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "progress_pct": 100.0,
                "stage": "COMPLETED",
                "completed_at": db_row[2],
                "request": req_data,
            }
        elif db_status == "CANCELLED":
            err_msg = meta.get("error", "Analysis run was cancelled.")
            if error_file.exists():
                try:
                    e_data = json.loads(error_file.read_text())
                    err_msg = e_data.get("error", err_msg)
                except Exception:
                    pass
            return {
                "run_id": run_id,
                "status": "CANCELLED",
                "error": err_msg,
                "progress_pct": float(meta.get("progress_pct", 0.0)),
                "stage": "CANCELLED",
                "request": req_data,
            }
        elif db_status == "FAILED":
            err_msg = meta.get("error", "Analysis run failed.")
            if error_file.exists():
                try:
                    e_data = json.loads(error_file.read_text())
                    err_msg = e_data.get("error", err_msg)
                except Exception:
                    pass
            return {
                "run_id": run_id,
                "status": "FAILED",
                "error": err_msg,
                "progress_pct": float(meta.get("progress_pct", 0.0)),
                "stage": "FAILED",
                "request": req_data,
            }
        else:
            # Active in-flight stage (e.g. SEARCHING_SCENES, DOWNLOADING, etc.)
            progress_pct = float(meta.get("progress_pct", 0.0))
            stage_name = meta.get("stage", db_status)
            return {
                "run_id": run_id,
                "status": db_status,
                "progress_pct": progress_pct,
                "stage": stage_name,
                "request": req_data,
            }

    # 2. Disk fallback if SQLite has no record for this run_id
    if error_file.exists():
        try:
            err_data = json.loads(error_file.read_text())
            # Explicit user cancellation always takes precedence
            if err_data.get("status") == "CANCELLED":
                return {
                    "run_id": run_id,
                    "status": "CANCELLED",
                    "error": err_data.get("error", "Analysis was cancelled."),
                    "stage": "CANCELLED",
                    "request": req_data,
                }
        except Exception:
            pass

    if summary_file.exists():
        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "progress_pct": 100.0,
            "stage": "COMPLETED",
            "request": req_data,
        }

    if error_file.exists():
        try:
            err_data = json.loads(error_file.read_text())
            status = err_data.get("status", "FAILED")
            return {
                "run_id": run_id,
                "status": status,
                "error": err_data.get("error"),
                "stage": status,
                "request": req_data,
            }
        except Exception:
            return {
                "run_id": run_id,
                "status": "FAILED",
                "error": "Unparseable error.json",
                "stage": "FAILED",
                "request": req_data,
            }

    return {
        "run_id": run_id,
        "status": "PROCESSING",
        "progress_pct": 0.0,
        "stage": "PROCESSING",
        "request": req_data,
    }


@router.post("/analysis-requests/{run_id}/cancel")
def cancel_analysis_request(run_id: str):
    """Cancel an active or queued dynamic analysis run."""
    run_dir = service.get_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Analysis run '{run_id}' not found.")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM analysis_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        if row and row[0] == "COMPLETED":
            raise HTTPException(status_code=400, detail=f"Cannot cancel run '{run_id}' because it is already COMPLETED.")
        if row and row[0] == "CANCELLED":
            return {"run_id": run_id, "status": "CANCELLED"}

    now_iso = datetime.now(timezone.utc).isoformat()
    cancel_file = run_dir / "error.json"
    atomic_write_json(cancel_file, {
        "status": "CANCELLED",
        "error": "Analysis cancelled by user.",
        "timestamp": now_iso,
    })

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE analysis_runs
            SET status = ?, metadata = ?
            WHERE run_id = ? AND status NOT IN ('COMPLETED', 'CANCELLED')
        """, ("CANCELLED", json.dumps({"status": "CANCELLED", "error": "Analysis cancelled by user."}), run_id))
        conn.commit()

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
    except FileNotFoundError as fe:
        raise HTTPException(status_code=404, detail=str(fe))
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


@router.get("/runs/{run_id}/visual-manifest")
def get_visual_manifest(run_id: str):
    """Retrieve map-ready layers, coordinate bounds, legends, and tile templates for interactive mapping."""
    run_dir = service.get_run_dir(run_id)
    manifest_path = run_dir / "visual_manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail=f"Visual manifest for run '{run_id}' not found.")

    summary = json.loads(summary_path.read_text())
    from src.pipeline.visualization import ScientificVisualizer
    manifest = ScientificVisualizer.build_visual_manifest(run_dir, summary)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest


@router.get("/runs/{run_id}/previews/{asset_name}")
def get_run_preview(run_id: str, asset_name: str):
    """Retrieve map-ready preview PNG image with legend, coordinates, and scale."""
    run_dir = service.get_run_dir(run_id)
    previews_dir = run_dir / "previews"

    base_name = asset_name.removesuffix(".png")
    if not base_name.startswith("preview_"):
        cand_name = f"preview_{base_name}.png"
    else:
        cand_name = f"{base_name}.png"

    preview_file = previews_dir / cand_name
    if not preview_file.exists():
        preview_file = previews_dir / f"{base_name}.png"
    if not preview_file.exists():
        alias_map = {
            "transitions": "preview_flood_transitions.png",
            "flood_transitions": "preview_flood_transitions.png",
            "riverbank": "preview_riverbank_migration.png",
            "riverbank_migration": "preview_riverbank_migration.png",
            "rf_probability": "preview_rf_probability.png",
            "timeseries": "preview_timeseries_chart.png",
            "timeseries_chart": "preview_timeseries_chart.png",
        }
        if base_name in alias_map:
            preview_file = previews_dir / alias_map[base_name]

    if not preview_file.exists():
        raise HTTPException(status_code=404, detail=f"Preview image '{asset_name}' not found for run '{run_id}'.")

    try:
        resolved_previews = previews_dir.resolve()
        if not preview_file.resolve().is_relative_to(resolved_previews):
            raise HTTPException(status_code=400, detail="Invalid preview asset name.")
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=400, detail="Invalid preview asset name.")

    return Response(content=preview_file.read_bytes(), media_type="image/png")


@router.get("/runs/{run_id}/download/{asset_name}")
def download_run_geotiff(run_id: str, asset_name: str):
    """Download georeferenced GeoTIFF raster asset."""
    run_dir = service.get_run_dir(run_id)
    rasters_dir = run_dir / "rasters"

    base_name = asset_name.removesuffix(".tif")
    alias_map = {
        "t1_sar": "t1_calibrated.tif",
        "t2_sar": "t2_calibrated.tif",
        "t1_water": "t1_water_mask.tif",
        "t2_water": "t2_water_mask.tif",
        "transitions": "transition_classes.tif",
        "flood_transitions": "transition_classes.tif",
        "rf_probability": "rf_probability.tif",
        "inundation_frequency": "inundation_frequency.tif",
    }
    target_name = alias_map.get(base_name, f"{base_name}.tif")
    tif_file = rasters_dir / target_name

    if not tif_file.exists():
        raise HTTPException(status_code=404, detail=f"Raster asset '{asset_name}' not found for run '{run_id}'.")

    try:
        resolved_rasters = rasters_dir.resolve()
        if not tif_file.resolve().is_relative_to(resolved_rasters):
            raise HTTPException(status_code=400, detail="Invalid raster asset name.")
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=400, detail="Invalid raster asset name.")

    filename = f"{run_id}_{tif_file.name}"
    return Response(
        content=tif_file.read_bytes(),
        media_type="image/tiff",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

