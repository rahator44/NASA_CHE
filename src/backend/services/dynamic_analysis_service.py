"""
Dynamic Satellite Analysis & Processing Service for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Coordinates:
- Dynamic Scene Discovery & ASF Querying
- Per-run isolated storage under data/runs/<run_id>/
- Long-running SQLite-backed persistent analysis execution
- Automated Lee 5x5 + Dual-Pol Otsu Water Classification
- Multi-temporal transition mapping & area reconciliation
- Riverbank and channel migration analysis
- Experimental pure-NumPy Random Forest & Saabas XAI feature attributions
- Dynamic XYZ Map Tile rendering and vector GeoJSON exports
"""

import os
import io
import re
import json
import time
import uuid
import hashlib
import logging
import joblib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
from PIL import Image
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

from src.backend.config import settings
from src.backend.database.database import get_db_connection
from src.core.satellite_catalog import SatelliteCatalogService, JAMUNA_DEFAULT_AOI_WKT
from src.acquisition.download_manager import DownloadManager
from src.acquisition.scene_selector import SceneSelector
from src.pipeline.sentinel1_preprocess import (
    Sentinel1Preprocessor,
    validate_sar_raster,
    verify_calibrated_raster_provenance,
    AUTHORITATIVE_BASELINE_GRANULES,
    AUTHORITATIVE_CHANGE_GRANULES,
    GRANULE_PROVENANCE,
    HISTORICAL_REFERENCE_REGISTRY,
    CANONICAL_GRAPH_XML,
    CANONICAL_GRAPH_SHA256,
)
from src.pipeline.water_classification import DynamicWaterClassifier
from src.pipeline.change_detection import DynamicChangeDetector
from src.pipeline.riverbank_analysis import DynamicRiverbankAnalyzer
from src.pipeline.feature_builder import SARFeatureBuilder
from src.pipeline.time_series import MultiDateTimeSeriesAnalyzer
from src.ml.random_forest import RandomForestClassifier
from src.ml.explainability import TreePathExplainer, validate_feature_schema

logger = logging.getLogger("EarthPulse.DynamicAnalysisService")

RUNS_BASE_DIR = settings.DATA_DIR / "runs"
DEFAULT_MODEL_PATH = settings.MODELS_DIR / "phase7a" / "phase7a_random_forest_model.joblib"

# Authoritative State Model & Legal Transitions
NON_TERMINAL_STATES = {
    "CREATED",
    "QUEUED",
    "SEARCHING_SCENES",
    "DOWNLOADING",
    "PREPROCESSING",
    "QUALITY_CHECKING",
    "CLASSIFYING",
    "CHANGE_ANALYSIS",
    "AI_ANALYSIS",
    "PUBLISHING_RESULTS",
}

TERMINAL_STATES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}

ALL_VALID_STATES = NON_TERMINAL_STATES | TERMINAL_STATES

VALID_STATE_TRANSITIONS = {
    "CREATED": {"QUEUED", "SEARCHING_SCENES", "FAILED", "CANCELLED"},
    "QUEUED": {"SEARCHING_SCENES", "DOWNLOADING", "FAILED", "CANCELLED"},
    "SEARCHING_SCENES": {"QUEUED", "DOWNLOADING", "PREPROCESSING", "FAILED", "CANCELLED"},
    "DOWNLOADING": {"PREPROCESSING", "FAILED", "CANCELLED"},
    "PREPROCESSING": {"QUALITY_CHECKING", "CLASSIFYING", "FAILED", "CANCELLED"},
    "QUALITY_CHECKING": {"CLASSIFYING", "FAILED", "CANCELLED"},
    "CLASSIFYING": {"CHANGE_ANALYSIS", "FAILED", "CANCELLED"},
    "CHANGE_ANALYSIS": {"AI_ANALYSIS", "PUBLISHING_RESULTS", "FAILED", "CANCELLED"},
    "AI_ANALYSIS": {"PUBLISHING_RESULTS", "FAILED", "CANCELLED"},
    "PUBLISHING_RESULTS": {"COMPLETED", "FAILED", "CANCELLED"},
    "FAILED": {"QUEUED", "SEARCHING_SCENES", "DOWNLOADING", "PREPROCESSING"},  # On retry
    "CANCELLED": set(),  # Terminal
    "COMPLETED": set(),  # Terminal
}


class IllegalStateTransitionError(ValueError):
    """Raised when an illegal, invalid, or out-of-order state transition is attempted."""
    pass


def atomic_write_json(file_path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON data to a temporary file in the same directory and atomically replace."""
    file_path = Path(file_path).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.parent / f".tmp_{file_path.name}_{uuid.uuid4().hex[:6]}"
    try:
        content = json.dumps(data, indent=indent, default=str)
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(file_path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


# Color Palettes for Dynamic Tile Rendering
TRANSITION_PALETTE = {
    1: [8, 81, 156, 240],     # Persistent Water (Navy Blue)
    2: [65, 182, 196, 240],   # Newly Inundated (Cyan)
    3: [254, 153, 41, 240],   # Receded Water (Orange)
    4: [200, 200, 200, 40],   # Persistent Non-Water (Light gray semi-transparent)
    5: [166, 206, 227, 180],  # Indeterminate Noise Floor (Powder Blue)
    6: [0, 0, 0, 0],          # NoData / Invalid (Transparent)
    255: [0, 0, 0, 0],        # Outside AOI
}

WATER_MASK_PALETTE = {
    0: [200, 200, 200, 30],   # Non-water
    1: [8, 81, 156, 240],     # Water
    2: [166, 206, 227, 180],  # Indeterminate
    3: [0, 0, 0, 0],          # NoData
    255: [0, 0, 0, 0],
}


class DynamicAnalysisService:
    """
    Core backend service managing dynamic analysis runs from scene query to scientific outputs.
    """

    def __init__(self):
        self.catalog = SatelliteCatalogService()
        self.download_manager = DownloadManager()
        settings.resolve_data_path("runs").mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_run_dir(cls, run_id: str) -> Path:
        if ".." in run_id or "/" in run_id or "\\" in run_id:
            raise ValueError(f"Invalid run_id '{run_id}': path traversal forbidden.")
        return settings.resolve_data_path(f"runs/{run_id}")

    def search_scenes(
        self,
        aoi_wkt: str = JAMUNA_DEFAULT_AOI_WKT,
        start_date: str = "2024-06-01",
        end_date: str = "2024-07-31",
        orbit_direction: Optional[str] = None,
        relative_orbit: Optional[int] = None,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query ASF DAAC for Sentinel-1 scenes over specified area and date range."""
        return self.catalog.search_sentinel1_scenes(
            wkt_polygon=aoi_wkt,
            start_date=start_date,
            end_date=end_date,
            orbit_direction=orbit_direction,
            relative_orbit=relative_orbit,
            max_results=max_results,
        )

    def discover_pairs(
        self,
        aoi_wkt: str = JAMUNA_DEFAULT_AOI_WKT,
        start_date: str = "2024-06-01",
        end_date: str = "2024-07-31",
    ) -> List[Dict[str, Any]]:
        """Find scientifically compatible observation pairs."""
        return self.catalog.discover_compatible_pairs(
            wkt_polygon=aoi_wkt,
            start_date=start_date,
            end_date=end_date,
        )

    def create_analysis_request(
        self,
        aoi_wkt: str,
        start_date: str,
        end_date: str,
        mode: str = "two_date_comparison",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new persistent dynamic analysis run.
        Validates AOI geometry, size, and geographic intersection with the Jamuna study region
        BEFORE creating any run directory or database record (Correction E).
        """
        # Validate AOI — parse and check geometry validity
        try:
            geom = ogr.CreateGeometryFromWkt(aoi_wkt)
            if geom is None or not geom.IsValid():
                raise ValueError("Invalid AOI polygon geometry WKT.")
        except Exception as e:
            raise ValueError(f"Failed to parse AOI WKT: {e}")

        # Enforce actual Jamuna geographic containment (Correction 3)
        study_geom = ogr.CreateGeometryFromWkt(settings.JAMUNA_STUDY_REGION_WKT)
        if study_geom is not None and not study_geom.Contains(geom):
            raise ValueError(
                "The submitted AOI polygon is not completely contained within the supported Jamuna study region "
                f"({settings.JAMUNA_STUDY_REGION_WKT}). Earth Pulse requires the entire AOI to lie within "
                "the Sirajganj / Kazipur reach of the Jamuna River, Bangladesh. Polygons extending partially "
                "or completely beyond this boundary are rejected."
            )

        # Correction E — validate AOI area against configurable limit
        try:
            aoi_area_km2 = Sentinel1Preprocessor.get_polygon_area_km2(aoi_wkt)
        except Exception as e:
            raise ValueError(f"Could not compute AOI area: {e}")
        if aoi_area_km2 > settings.AOI_MAX_AREA_KM2:
            raise ValueError(
                f"AOI area {aoi_area_km2:.2f} km² exceeds the maximum allowed area of "
                f"{settings.AOI_MAX_AREA_KM2:.2f} km². Submit a smaller polygon."
            )
        if aoi_area_km2 <= 0:
            raise ValueError("AOI area is zero or negative — degenerate geometry.")

        # Validate date ordering
        if start_date > end_date:
            raise ValueError(f"Start date ({start_date}) cannot be after end date ({end_date})")

        # Future date limitation check (Sentinel-1 observations only exist up to present)
        current_year = datetime.now(timezone.utc).year
        start_year = int(start_date.split("-")[0])
        if start_year > current_year:
            raise ValueError(
                f"Requested observation year ({start_year}) is in the future. "
                "Earth Pulse is an empirical satellite observation system and cannot invent future data."
            )

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_uuid = uuid.uuid4().hex[:6]
        run_id = f"run_{timestamp_str}_{run_uuid}"

        run_dir = self.get_run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "rasters").mkdir(parents=True, exist_ok=True)
        (run_dir / "vectors").mkdir(parents=True, exist_ok=True)

        merged_params = dict(parameters or {})
        merged_params.setdefault("satellite_acquisitions", [start_date, end_date])

        req_config = {
            "run_id": run_id,
            "mode": mode,
            "aoi_wkt": aoi_wkt,
            "start_date": start_date,
            "end_date": end_date,
            "satellite_acquisitions": [start_date, end_date],
            "parameters": merged_params,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        atomic_write_json(run_dir / "request.json", req_config)

        # Record in SQLite analysis_runs table
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO analysis_runs (run_id, analysis_type, region_id, status, executed_at, parameters)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                f"dynamic_{mode}",
                "jamuna_sirajganj",
                "CREATED",
                req_config["created_at"],
                json.dumps(req_config),
            ))
            conn.commit()

        logger.info("Created analysis run %s in state CREATED", run_id)
        return {
            "run_id": run_id,
            "status": "CREATED",
            "progress_pct": 0.0,
            "request": req_config,
        }

    def execute_analysis_run(self, run_id: str) -> Dict[str, Any]:
        """
        Execute the full dynamic pipeline for an analysis run through all verified stages.
        Derives state authoritatively, manages execution attempts, and performs atomic artifact completion.
        """
        run_dir = self.get_run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")

        req_path = run_dir / "request.json"
        if not req_path.exists():
            raise FileNotFoundError(f"Run request config missing: {req_path}")

        req_config = json.loads(req_path.read_text())
        aoi_wkt = req_config["aoi_wkt"]
        start_date = req_config["start_date"]
        end_date = req_config["end_date"]
        mode = req_config.get("mode", "two_date_comparison")

        # 1. Authoritative check: do not re-execute or overwrite an already COMPLETED run
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, metadata, completed_at FROM analysis_runs WHERE run_id = ?", (run_id,))
            db_row = cursor.fetchone()

        db_status = db_row["status"] if db_row else None
        if db_status == "COMPLETED":
            summary_path = run_dir / "summary.json"
            if summary_path.exists():
                try:
                    existing_summary = json.loads(summary_path.read_text())
                    if existing_summary.get("status") == "COMPLETED":
                        logger.info("Run %s is already COMPLETED with verified summary. Returning existing results.", run_id)
                        return existing_summary
                except Exception:
                    pass

        # 2. Establish attempt tracking under attempts/
        attempts_dir = run_dir / "attempts"
        attempts_dir.mkdir(parents=True, exist_ok=True)
        existing_indices = []
        for p in attempts_dir.iterdir():
            m = re.match(r"^attempt_(\d{4})\.json$", p.name)
            if m:
                existing_indices.append(int(m.group(1)))
        attempt_idx = max(existing_indices, default=0) + 1

        # Check for pre-execution cancellation vs stale failure from a prior attempt
        old_err = run_dir / "error.json"
        if old_err.exists():
            try:
                old_err_data = json.loads(old_err.read_text())
                if old_err_data.get("status") == "CANCELLED":
                    logger.info("Run %s was cancelled before execution.", run_id)
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE analysis_runs
                            SET status = ?, metadata = ?
                            WHERE run_id = ?
                        """, ("CANCELLED", json.dumps({"status": "CANCELLED", "error": old_err_data.get("error", "Analysis run was cancelled.")}), run_id))
                        conn.commit()
                    return {"run_id": run_id, "status": "CANCELLED", "error": old_err_data.get("error", "Analysis run was cancelled.")}

                old_idx = attempt_idx - 1 if attempt_idx > 1 else 1
                archived_name = f"attempt_{old_idx:04d}_error.json"
                atomic_write_json(attempts_dir / archived_name, old_err_data)
                old_err.unlink()
            except Exception as e:
                logger.warning("Could not process error.json: %s", e)

        attempt_record = {
            "attempt_index": attempt_idx,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "RUNNING",
            "mode": mode,
        }
        atomic_write_json(attempts_dir / f"attempt_{attempt_idx:04d}.json", attempt_record)

        def _check_cancellation():
            cancel_file = run_dir / "error.json"
            if cancel_file.exists():
                try:
                    data = json.loads(cancel_file.read_text())
                    if data.get("status") == "CANCELLED":
                        raise InterruptedError("Analysis run was cancelled by user request.")
                except json.JSONDecodeError:
                    pass
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM analysis_runs WHERE run_id = ?", (run_id,))
                row = cursor.fetchone()
                if row and row[0] == "CANCELLED":
                    raise InterruptedError("Analysis run was cancelled by user request.")

        def _update_stage(status: str, progress: float, metadata: Optional[Dict[str, Any]] = None):
            _check_cancellation()
            # Validate state transition against legal state machine
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM analysis_runs WHERE run_id = ?", (run_id,))
                cur_row = cursor.fetchone()
                cur_status = cur_row[0] if cur_row else "CREATED"

            if cur_status in ("COMPLETED", "CANCELLED"):
                raise IllegalStateTransitionError(
                    f"Cannot transition run {run_id} from terminal state '{cur_status}' to '{status}'"
                )

            allowed = VALID_STATE_TRANSITIONS.get(cur_status, set())
            if status not in allowed and cur_status != status:
                raise IllegalStateTransitionError(
                    f"Illegal state transition for run {run_id}: '{cur_status}' -> '{status}'. "
                    f"Registered allowed transitions from '{cur_status}': {allowed}"
                )

            meta_dict = dict(metadata or {})
            meta_dict["progress_pct"] = round(float(progress), 1)
            meta_dict["stage"] = status
            meta_dict["current_attempt"] = attempt_idx
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE analysis_runs
                    SET status = ?, metadata = ?
                    WHERE run_id = ? AND status = ?
                """, (status, json.dumps(meta_dict), run_id, cur_status))
                if cursor.rowcount == 0:
                    raise RuntimeError(
                        f"Concurrent state conflict on run {run_id}: expected current status '{cur_status}' "
                        f"prior to transitioning to '{status}', but the database row was modified concurrently."
                    )
                conn.commit()
            logger.info("Run %s (attempt %d) transitioned to %s (%.1f%%)", run_id, attempt_idx, status, progress)

        try:
            # Stage 1: SEARCHING_SCENES
            _update_stage("SEARCHING_SCENES", 15.0)
            scenes = self.search_scenes(aoi_wkt=aoi_wkt, start_date=start_date, end_date=end_date)

            # Intra-run resumption check: if an earlier attempt of THIS EXACT run already selected scenes,
            # we may reuse them only if they strictly validate against the requested date window, granule identity,
            # metadata contract, and AOI spatial coverage.
            # Cross-run scene substitution across different run directories is strictly forbidden (P0 safety requirement).
            cached_scenes_path = run_dir / "scenes.json"
            if len(scenes) < 2 and cached_scenes_path.exists():
                try:
                    cached_data = json.loads(cached_scenes_path.read_text())
                    cached_b = cached_data.get("selected_baseline")
                    cached_c = cached_data.get("selected_change")
                    if isinstance(cached_b, dict) and isinstance(cached_c, dict):
                        b_name = str(cached_b.get("scene_name", "")).strip()
                        c_name = str(cached_c.get("scene_name", "")).strip()
                        b_acq = cached_b.get("acquisition_time", "")[:10]
                        c_acq = cached_c.get("acquisition_time", "")[:10]
                        req_start = start_date[:10]
                        req_end = end_date[:10]
                        
                        # Validate distinct granule identity and date window against immutable request
                        if b_name and c_name and b_name != c_name and req_start <= b_acq <= req_end and req_start <= c_acq <= req_end and b_acq != c_acq:
                            # Positional metadata validation via SceneSelector (no extra keyword arguments)
                            rej_b = SceneSelector.validate_scene_metadata(cached_b)
                            rej_c = SceneSelector.validate_scene_metadata(cached_c)

                            # Recompute and enforce AOI spatial coverage against run request geometry
                            # Require actual parseable scene footprint geometry for both scenes (fail closed on missing or invalid footprints)
                            from src.acquisition.asf_client import parse_geometry, _compute_aoi_coverage_pct

                            geom_b = cached_b.get("footprint_geojson") or cached_b.get("footprint_wkt") or cached_b.get("geometry")
                            if geom_b is None:
                                rej_b.append("Cached baseline scene is missing mandatory footprint geometry")
                            else:
                                parsed_b = parse_geometry(geom_b)
                                if parsed_b is None or not parsed_b.IsValid():
                                    rej_b.append("Cached baseline scene footprint geometry is invalid or unparseable")
                                else:
                                    cov_b = _compute_aoi_coverage_pct(aoi_wkt, geom_b)
                                    if cov_b < 95.0:
                                        rej_b.append(f"Recomputed AOI coverage {cov_b:.2f}% is below 95.0% threshold")

                            geom_c = cached_c.get("footprint_geojson") or cached_c.get("footprint_wkt") or cached_c.get("geometry")
                            if geom_c is None:
                                rej_c.append("Cached change scene is missing mandatory footprint geometry")
                            else:
                                parsed_c = parse_geometry(geom_c)
                                if parsed_c is None or not parsed_c.IsValid():
                                    rej_c.append("Cached change scene footprint geometry is invalid or unparseable")
                                else:
                                    cov_c = _compute_aoi_coverage_pct(aoi_wkt, geom_c)
                                    if cov_c < 95.0:
                                        rej_c.append(f"Recomputed AOI coverage {cov_c:.2f}% is below 95.0% threshold")

                            if not rej_b and not rej_c:
                                scenes = [cached_b, cached_c]
                                logger.info("Reusing %d validated intra-run scene(s) from %s", len(scenes), cached_scenes_path)
                            else:
                                logger.warning("Intra-run cached scenes failed validation: %s / %s", rej_b, rej_c)
                        else:
                            logger.warning(
                                "Intra-run cached scenes failed identity or date check against request [%s, %s]: b=%s (%s), c=%s (%s)",
                                req_start, req_end, b_name, b_acq, c_name, c_acq
                            )
                except Exception as e:
                    logger.warning("Failed to load intra-run cached scenes from %s: %s", cached_scenes_path, e)

            # Strict scientific failure: if fewer than 2 valid scenes exist for this query, fail explicitly
            if len(scenes) < 2:
                raise RuntimeError(
                    f"Insufficient Sentinel-1 scenes found between {start_date} and {end_date} for specified AOI. "
                    f"Found {len(scenes)} observation(s); at least 2 comparable acquisitions required."
                )

            # Stage 2: PAIRING / SCENE_SELECTION
            _update_stage("QUEUED", 25.0, {"candidate_scene_count": len(scenes)})
            
            # Discard cached serialized all_compatible_pairs as authoritative input (Fix 1 requirement)
            # Recompute compatibility strictly using SceneSelector.find_all_compatible_pairs()
            pairs = SceneSelector.find_all_compatible_pairs(
                scenes=scenes,
                wkt_polygon=aoi_wkt,
            )

            if not pairs:
                raise RuntimeError("No scientifically comparable observation pair (matching track, flight direction, and dual polarization) found.")

            # Select pair closest to the requested start_date and end_date
            min_dist = float("inf")
            req_t1_date = start_date[:10]
            req_t2_date = end_date[:10]
            selected_pair = pairs[0]
            for p in pairs:
                t1_str = p["baseline"].get("acquisition_time", "")[:10]
                t2_str = p["change"].get("acquisition_time", "")[:10]
                try:
                    d1 = abs((datetime.fromisoformat(t1_str) - datetime.fromisoformat(req_t1_date)).total_seconds())
                    d2 = abs((datetime.fromisoformat(t2_str) - datetime.fromisoformat(req_t2_date)).total_seconds())
                    dist = d1 + d2
                    if dist < min_dist:
                        min_dist = dist
                        selected_pair = p
                except Exception:
                    pass

            scene_t1 = selected_pair["baseline"]
            scene_t2 = selected_pair["change"]

            # Save scenes selection
            atomic_write_json(run_dir / "scenes.json", {
                "selected_baseline": scene_t1,
                "selected_change": scene_t2,
                "all_compatible_pairs": pairs,
            })

            # Determine observations to process
            if mode == "multi_date_timeseries":
                other_scenes = []
                for s in scenes:
                    if s.get("scene_name") in (scene_t1.get("scene_name"), scene_t2.get("scene_name")):
                        continue
                    is_compat, reasons, _ = SceneSelector.evaluate_pair_comparability(scene_t1, s, aoi_wkt)
                    if is_compat:
                        other_scenes.append(s)
                    else:
                        logger.info("Excluding scene %s from multi-date series: %s", s.get("scene_name"), "; ".join(reasons))
                raw_list = [scene_t1, scene_t2] + other_scenes
                if len(raw_list) < 3:
                    raise RuntimeError(
                        f"Insufficient scientifically compatible observations for multi-date time series between {start_date} and {end_date}. "
                        f"Found {len(raw_list)} compatible scene(s); at least 3 mutually comparable observations (matching relative orbit track, "
                        "flight direction, and dual polarization) are required."
                    )
                raw_list = raw_list[:5]
            else:
                raw_list = [scene_t1, scene_t2]

            # Chronological sort ensuring t0 < t1 < t2 ...
            def _parse_acq_dt(sc: Dict[str, Any]) -> datetime:
                t_str = sc.get("acquisition_time", "")
                try:
                    return datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                except Exception:
                    return datetime.min.replace(tzinfo=timezone.utc)

            scenes_to_process = sorted(raw_list, key=_parse_acq_dt)
            scene_t1 = scenes_to_process[0]
            scene_t2 = scenes_to_process[1]

            # Stage 3: DOWNLOADING / ACQUIRING
            _update_stage("DOWNLOADING", 40.0)
            calibrated_observations = []
            for s_idx, sc in enumerate(scenes_to_process):
                _check_cancellation()
                out_name = "t1_calibrated.tif" if s_idx == 0 else ("t2_calibrated.tif" if s_idx == 1 else f"obs_{s_idx}_calibrated.tif")
                cal_tif = self._resolve_or_extract_calibrated_raster(sc, aoi_wkt, run_dir, out_name)
                calibrated_observations.append({
                    "scene": sc,
                    "calibrated_tif": cal_tif,
                    "out_name": out_name,
                })

            # Stage 4: PREPROCESSING & QUALITY CHECKING
            _update_stage("PREPROCESSING", 55.0)
            obs_meta = []
            for s_idx, item in enumerate(calibrated_observations):
                _check_cancellation()
                m = validate_sar_raster(item["calibrated_tif"])
                obs_meta.append(m)

                # Verify spatial alignment against baseline
                # NOTE: validate_sar_raster() returns "epsg", "width", "height" (not "crs", "x_size", "y_size")
                if s_idx > 0:
                    base_m = obs_meta[0]
                    if m.get("epsg") != base_m.get("epsg"):
                        raise ValueError(
                            f"Raster CRS mismatch between {item['out_name']} (EPSG:{m.get('epsg')}) "
                            f"and baseline (EPSG:{base_m.get('epsg')})"
                        )
                    if (m.get("width"), m.get("height")) != (base_m.get("width"), base_m.get("height")):
                        raise ValueError(
                            f"Raster dimension mismatch between {item['out_name']} "
                            f"({m.get('width')}×{m.get('height')}) and baseline "
                            f"({base_m.get('width')}×{base_m.get('height')})"
                        )
                    base_gt = base_m.get("geotransform", [])
                    curr_gt = m.get("geotransform", [])
                    if len(base_gt) == 6 and len(curr_gt) == 6:
                        # Validate rotation/skew terms are strictly zero
                        if abs(curr_gt[2]) > 1e-6 or abs(curr_gt[4]) > 1e-6:
                            raise ValueError(
                                f"Raster {item['out_name']} has non-zero rotation or shearing: geotransform={curr_gt}"
                            )
                        # Validate pixel area against 20m standard
                        pix_area = abs(curr_gt[1] * curr_gt[5])
                        if abs(pix_area - 400.0) > 2.0:
                            raise ValueError(
                                f"Raster {item['out_name']} pixel area {pix_area:.2f} m² deviates from 20m standard (400 m²)"
                            )
                        # Strict coordinate equality (rtol=0.0, atol=1e-6)
                        if not np.allclose(curr_gt, base_gt, rtol=0.0, atol=1e-6):
                            raise ValueError(
                                f"Raster geotransform mismatch between {item['out_name']} ({curr_gt}) "
                                f"and baseline ({base_gt})"
                            )

            t1_meta = obs_meta[0]
            t2_meta = obs_meta[1]
            _update_stage("QUALITY_CHECKING", 65.0, {"t1_meta": t1_meta, "t2_meta": t2_meta, "total_observations": len(obs_meta)})

            # Stage 5: CLASSIFYING WATER
            _update_stage("CLASSIFYING", 75.0)
            classifier = DynamicWaterClassifier(filter_size=5, fusion_strategy="dual_and")

            obs_records = []
            for s_idx, item in enumerate(calibrated_observations):
                _check_cancellation()
                mask_name = "t1_water_mask.tif" if s_idx == 0 else ("t2_water_mask.tif" if s_idx == 1 else f"obs_{s_idx}_water_mask.tif")
                mask_tif = run_dir / "rasters" / mask_name
                meta_json = run_dir / f"obs_{s_idx}_water_metadata.json"
                m_res = classifier.classify_scene(item["calibrated_tif"], mask_tif, meta_json)
                obs_records.append({
                    "scene": item["scene"],
                    "calibrated_tif": item["calibrated_tif"],
                    "mask_tif": mask_tif,
                    "meta": m_res,
                    "acquisition_time": item["scene"].get("acquisition_time", f"obs_{s_idx}"),
                })

            t1_calibrated_tif = obs_records[0]["calibrated_tif"]
            t2_calibrated_tif = obs_records[1]["calibrated_tif"]
            mask1_tif = obs_records[0]["mask_tif"]
            mask2_tif = obs_records[1]["mask_tif"]
            mask1_res = obs_records[0]["meta"]
            mask2_res = obs_records[1]["meta"]

            # Stage 6: CHANGE ANALYSIS
            _update_stage("CHANGE_ANALYSIS", 85.0)
            trans_tif = run_dir / "rasters" / "transition_classes.tif"
            trans_meta_json = run_dir / "transition_metadata.json"
            inun_geojson = run_dir / "vectors" / "newly_inundated.geojson"

            change_res = DynamicChangeDetector.detect_changes(
                baseline_mask_tif=mask1_tif,
                change_mask_tif=mask2_tif,
                output_transition_tif=trans_tif,
                output_metadata_json=trans_meta_json,
                output_vector_geojson=inun_geojson,
            )

            # Riverbank migration analysis
            riverbank_res = DynamicRiverbankAnalyzer.analyze_reach(
                transition_tif=trans_tif,
                output_metadata_json=run_dir / "riverbank_metadata.json",
            )

            # Stage 7: AI ANALYSIS (RANDOM FOREST & SAABAS EXPLAINABILITY)
            _update_stage("AI_ANALYSIS", 90.0)
            ai_res = self._run_ai_inference_and_explanations(t2_calibrated_tif, mask2_tif, run_dir)

            # Stage 8: TIME-SERIES TRAJECTORY
            time_series_res = None
            if mode == "multi_date_timeseries" and len(obs_records) >= 3:
                _check_cancellation()
                mask_records = [
                    {
                        "acquisition_time": rec["acquisition_time"],
                        "scene_name": rec["scene"].get("scene_name", ""),
                        "mask_tif": rec["mask_tif"],
                    }
                    for rec in obs_records
                ]
                freq_tif = run_dir / "rasters" / "inundation_frequency.tif"
                time_series_res = MultiDateTimeSeriesAnalyzer.analyze_sequence(
                    mask_records=mask_records,
                    output_frequency_tif=freq_tif,
                    output_metadata_json=run_dir / "timeseries.json",
                )

            # Stage 9: PUBLISHING RESULTS & SUMMARY
            _update_stage("PUBLISHING_RESULTS", 95.0)
            now_iso = datetime.now(timezone.utc).isoformat()
            geom_vector_area_km2 = round(Sentinel1Preprocessor.get_polygon_area_km2(aoi_wkt), 4)
            # Correction 1: Derive raster_polygon_area_km2 from actual inside-polygon pixels (Classes 1-5)
            # independent of common valid comparison domain (Classes 1-4)
            raster_polygon_area_km2 = round(
                change_res["area_metrics_km2"].get("raster_polygon_area", change_res["area_metrics_km2"]["valid_comparison_area"]), 4
            )
            bounding_box_area_km2 = round(change_res["area_metrics_km2"]["total_study_aoi"], 4)
            common_valid_domain_km2 = round(change_res["area_metrics_km2"]["valid_comparison_area"], 4)
            diff_pct = (
                abs(raster_polygon_area_km2 - geom_vector_area_km2) / geom_vector_area_km2 * 100.0
                if geom_vector_area_km2 > 0 else 0.0
            )

            # Correction H & V4-1 — four distinct area definitions calculated independently:
            #   1. geometric_vector_area_km2 — planar polygon area in UTM Zone 45N projection
            #      (source: OGR, computed directly from submitted WKT before any rasterisation)
            #   2. raster_polygon_area_km2 — count of pixels whose centroid falls inside the
            #      cutline polygon × (20m × 20m) pixel area (all non-NoData pixels in transition raster).
            #      The raster-to-vector difference is due to 20m pixel-boundary inclusion rules.
            #   3. bounding_box_area_km2 — all pixels in the axis-aligned bounding box extent
            #      (includes pixels outside the polygon assigned Class 6 NoData).
            #   4. common_valid_domain_km2 — pixels classified as 0 or 1 in BOTH baseline and change
            #      scenes simultaneously (Classes 1-4). Excludes indeterminate noise floor (Class 5).

            summary = {
                "run_id": run_id,
                "status": "COMPLETED",
                "completed_at": now_iso,
                "study_aoi": {
                    "wkt": aoi_wkt,
                    # Correction H & V4-1: all four area definitions present and independently derived
                    "geometric_vector_area_km2": geom_vector_area_km2,
                    "raster_polygon_area_km2": raster_polygon_area_km2,
                    "bounding_box_area_km2": bounding_box_area_km2,
                    "common_valid_domain_km2": common_valid_domain_km2,
                    "pixel_area_km2": 0.0004,  # 20m × 20m pixel
                    "discretization_pct": round(diff_pct, 4),
                    "area_definitions_note": (
                        "geometric_vector_area_km2: planar polygon area in UTM Zone 45N (OGR, pre-rasterisation). "
                        "raster_polygon_area_km2: pixels inside cutline × 0.0004 km² (20m pixel grid, classes 1-5). "
                        "bounding_box_area_km2: all pixels in bounding-box extent (includes outside-polygon NoData). "
                        "common_valid_domain_km2: pixels valid (class 0 or 1) in BOTH scenes simultaneously — "
                        "the only scientifically comparable domain for water-change calculation."
                    ),
                    # Legacy keys preserved for backward compatibility
                    "analyzed_pixel_area_km2": raster_polygon_area_km2,
                    "total_area_km2": raster_polygon_area_km2,
                    "valid_comparison_km2": common_valid_domain_km2,
                },
                "observations": {
                    "baseline": {
                        "scene_name": scene_t1.get("scene_name", "Baseline_Observation"),
                        "acquisition_time": scene_t1.get("acquisition_time", "2024-06-10"),
                        "water_area_km2": mask1_res["area_measurements"]["water_area_km2"],
                        "independent_observed_water_km2": round(mask1_res["area_measurements"]["water_area_km2"], 4),
                        "common_domain_water_km2": round(
                            change_res["area_metrics_km2"]["persistent_water"] + change_res["area_metrics_km2"]["receded_water"], 4
                        ),
                        "threshold_vv_db": mask1_res["thresholds"]["vv_db"],
                        "threshold_vh_db": mask1_res["thresholds"]["vh_db"],
                        "note": "water_area_km2 and independent_observed_water_km2 are observed over this scene's valid mask.",
                    },
                    "change": {
                        "scene_name": scene_t2.get("scene_name", "Change_Observation"),
                        "acquisition_time": scene_t2.get("acquisition_time", "2024-07-16"),
                        "water_area_km2": mask2_res["area_measurements"]["water_area_km2"],
                        "independent_observed_water_km2": round(mask2_res["area_measurements"]["water_area_km2"], 4),
                        "common_domain_water_km2": round(
                            change_res["area_metrics_km2"]["persistent_water"] + change_res["area_metrics_km2"]["newly_inundated"], 4
                        ),
                        "threshold_vv_db": mask2_res["thresholds"]["vv_db"],
                        "threshold_vh_db": mask2_res["thresholds"]["vh_db"],
                        "note": "water_area_km2 and independent_observed_water_km2 are observed over this scene's valid mask.",
                    },
                },
                "flood_transitions_km2": change_res["area_metrics_km2"],
                "flood_reconciliation": change_res["reconciliation"],
                "comparability_reconciliation": {
                    "common_domain_net_change_km2": round(change_res["area_metrics_km2"]["net_candidate_water_change"], 4),
                    "common_domain_valid_area_km2": round(change_res["area_metrics_km2"]["valid_comparison_area"], 4),
                    "independent_extent_difference_km2": round(
                        mask2_res["area_measurements"]["water_area_km2"] - mask1_res["area_measurements"]["water_area_km2"], 4
                    ),
                    "explanation": (
                        f"The difference between single-date observed water extents ({round(mask2_res['area_measurements']['water_area_km2'] - mask1_res['area_measurements']['water_area_km2'], 4):+.4f} km²) "
                        f"and the common-domain transition result ({round(change_res['area_metrics_km2']['net_candidate_water_change'], 4):+.4f} km², gap of {round(abs((mask2_res['area_measurements']['water_area_km2'] - mask1_res['area_measurements']['water_area_km2']) - change_res['area_metrics_km2']['net_candidate_water_change']), 4):.4f} km²) "
                        "occurs because single-date water extents are measured independently within each scene's own valid pixels, "
                        f"which includes pixels that are indeterminate noise floor ({round(change_res['area_metrics_km2']['indeterminate_floor'], 4):.4f} km²) or unobserved/NoData "
                        "in the opposite acquisition. For scientific multi-temporal change detection, "
                        f"water transitions must be calculated strictly over the mutually valid common domain "
                        f"({round(change_res['area_metrics_km2']['valid_comparison_area'], 4):.4f} km²), giving the verified net candidate water change of {round(change_res['area_metrics_km2']['net_candidate_water_change'], 4):+.4f} km² "
                        f"({round(change_res['area_metrics_km2']['newly_inundated'], 4):.4f} km² newly inundated minus {round(change_res['area_metrics_km2']['receded_water'], 4):.4f} km² receded)."
                    ),
                },
                "riverbank_dynamics": riverbank_res,
                "ai_evaluation": ai_res.get("summary", {}),
                "time_series": time_series_res,
            }

            # Validate required output rasters before publication
            required_rasters = [
                run_dir / "rasters" / "t1_calibrated.tif",
                run_dir / "rasters" / "t2_calibrated.tif",
                run_dir / "rasters" / "t1_water_mask.tif",
                run_dir / "rasters" / "t2_water_mask.tif",
                run_dir / "rasters" / "transition_classes.tif",
            ]
            for rf in required_rasters:
                if not rf.exists():
                    raise FileNotFoundError(f"Required analysis output raster missing: {rf}")
                ds = gdal.Open(str(rf), gdal.GA_ReadOnly)
                if ds is None:
                    raise ValueError(f"Corrupt or unreadable output raster: {rf}")
                ds = None

            # Generate map-ready preview PNGs and web manifest for visualization
            from src.pipeline.visualization import ScientificVisualizer
            preview_outputs = ScientificVisualizer.generate_all_run_previews(run_dir, summary)
            manifest_path = run_dir / "visual_manifest.json"

            summary["visual_manifest"] = str(manifest_path)
            summary["previews"] = {k: str(v) for k, v in preview_outputs.items()}

            atomic_write_json(run_dir / "summary.json", summary)

            # Record attempt completion
            attempt_file = attempts_dir / f"attempt_{attempt_idx:04d}.json"
            attempt_completed_file = attempts_dir / f"attempt_{attempt_idx:04d}_completed.json"
            completed_record = {
                "attempt_index": attempt_idx,
                "started_at": attempt_record.get("started_at"),
                "completed_at": now_iso,
                "status": "COMPLETED",
                "mode": mode,
                "run_id": run_id,
            }
            atomic_write_json(attempt_file, completed_record)
            atomic_write_json(attempt_completed_file, completed_record)

            # Update SQLite to COMPLETED
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE analysis_runs
                    SET status = ?, completed_at = ?, outputs = ?, metadata = ?
                    WHERE run_id = ? AND status NOT IN ('COMPLETED', 'CANCELLED')
                """, (
                    "COMPLETED",
                    now_iso,
                    json.dumps({
                        "summary": str(run_dir / "summary.json"),
                        "visual_manifest": str(manifest_path),
                        "transition_raster": str(trans_tif),
                        "vector_geojson": str(inun_geojson),
                        "previews": {k: str(v) for k, v in preview_outputs.items()},
                    }),
                    json.dumps(summary),
                    run_id,
                ))
                conn.commit()

            logger.info("Run %s completed successfully!", run_id)
            return summary

        except InterruptedError as ie:
            logger.info("Analysis run %s was cancelled: %s", run_id, ie)
            err_msg = str(ie)
            now_iso = datetime.now(timezone.utc).isoformat()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE analysis_runs
                    SET status = ?, metadata = ?
                    WHERE run_id = ? AND status NOT IN ('COMPLETED', 'CANCELLED')
                """, ("CANCELLED", json.dumps({"status": "CANCELLED", "error": err_msg}), run_id))
                conn.commit()

            atomic_write_json(run_dir / "error.json", {
                "status": "CANCELLED",
                "error": err_msg,
                "timestamp": now_iso,
                "attempt_index": attempt_idx,
            })
            cancelled_record = {
                "attempt_index": attempt_idx,
                "started_at": attempt_record.get("started_at"),
                "cancelled_at": now_iso,
                "status": "CANCELLED",
                "error": err_msg,
                "run_id": run_id,
            }
            atomic_write_json(attempts_dir / f"attempt_{attempt_idx:04d}.json", cancelled_record)
            atomic_write_json(attempts_dir / f"attempt_{attempt_idx:04d}_cancelled.json", cancelled_record)
            return {"run_id": run_id, "status": "CANCELLED", "error": err_msg}

        except Exception as e:
            logger.error("Analysis run %s failed: %s", run_id, e, exc_info=True)
            err_msg = str(e)
            now_iso = datetime.now(timezone.utc).isoformat()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE analysis_runs
                    SET status = ?, metadata = ?
                    WHERE run_id = ? AND status NOT IN ('COMPLETED', 'CANCELLED')
                """, ("FAILED", json.dumps({"error": err_msg}), run_id))
                conn.commit()

            atomic_write_json(run_dir / "error.json", {
                "status": "FAILED",
                "error": err_msg,
                "timestamp": now_iso,
                "attempt_index": attempt_idx,
            })
            failed_record = {
                "attempt_index": attempt_idx,
                "started_at": attempt_record.get("started_at"),
                "failed_at": now_iso,
                "status": "FAILED",
                "error": err_msg,
                "run_id": run_id,
            }
            atomic_write_json(attempts_dir / f"attempt_{attempt_idx:04d}.json", failed_record)
            atomic_write_json(attempts_dir / f"attempt_{attempt_idx:04d}_failed.json", failed_record)
            raise

    def _resolve_or_extract_calibrated_raster(
        self,
        scene: Dict[str, Any],
        aoi_wkt: str,
        run_dir: Path,
        out_filename: str,
    ) -> Path:
        """
        Resolves calibrated SAR raster for scene.
        Extracts sub-AOI with cutline masking if existing calibrated scene is available.
        Otherwise downloads archive and runs ESA SNAP GPT preprocessing.
        Fails with clear error if data cannot be located or acquired (no historical substitution).
        Writes per-granule provenance.json to rasters/ documenting the specific granule-to-raster mapping.
        """
        target_tif = run_dir / "rasters" / out_filename
        scene_name = scene.get("scene_name", "")
        acq_time = scene.get("acquisition_time", "")

        # 1. Authoritative verified historical granules for 2024 Jamuna campaign
        # Exact granule identity matching ONLY - arbitrary date matching or alternate ID reuse is strictly forbidden.
        AUTHORITATIVE_BASELINE_GRANULES = {
            "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69",
            "june10_aligned",
        }
        AUTHORITATIVE_CHANGE_GRANULES = {
            "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511",
            "july16_aligned",
        }

        # Correction C & V4-2 — per-granule provenance metadata
        # Documents which granule ID was processed to which raster, and verification status.
        # Only verified granules with documented SNAP processing chains are permitted to reuse historical rasters.
        GRANULE_PROVENANCE = {
            "S1A_IW_GRDH_1SDV_20240610T120508_20240610T120533_054261_06999F_7B69": {
                "preprocessed_raster": "data/processed/aligned/june10_aligned.tif",
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
                "processing_reference": "configs/regions/jamuna_sirajganj.yaml#acquisitions.june10",
                "verification_status": "VERIFIED",
                "notes": "Primary granule. Documented in Jamuna region YAML. Processing chain independently verified.",
            },
            "june10_aligned": {
                "preprocessed_raster": "data/processed/aligned/june10_aligned.tif",
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
                "processing_reference": "configs/regions/jamuna_sirajganj.yaml#acquisitions.june10",
                "verification_status": "VERIFIED",
                "notes": "Shorthand alias for june10 baseline raster.",
            },
            "S1A_IW_GRDH_1SDV_20240716T120507_20240716T120532_054786_06ABD2_6511": {
                "preprocessed_raster": "data/processed/aligned/july16_aligned.tif",
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
                "processing_reference": "configs/regions/jamuna_sirajganj.yaml#acquisitions.july16",
                "verification_status": "VERIFIED",
                "notes": "Primary change-date granule. Documented in Jamuna region YAML.",
            },
            "july16_aligned": {
                "preprocessed_raster": "data/processed/aligned/july16_aligned.tif",
                "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
                "processing_reference": "configs/regions/jamuna_sirajganj.yaml#acquisitions.july16",
                "verification_status": "VERIFIED",
                "notes": "Shorthand alias for july16 change-date raster.",
            },
        }

        candidate_sources = [
            settings.DATA_DIR / "processed" / "aligned" / "june10_aligned.tif",
            settings.DATA_DIR / "processed" / "aligned" / "july16_aligned.tif",
        ]
        source_tif = None
        provenance_entry = None
        clean_scene = Path(scene_name).name.replace(".zip", "").replace(".SAFE", "")

        if clean_scene in AUTHORITATIVE_BASELINE_GRANULES:
            source_tif = candidate_sources[0]
            provenance_entry = GRANULE_PROVENANCE.get(clean_scene)
        elif clean_scene in AUTHORITATIVE_CHANGE_GRANULES:
            source_tif = candidate_sources[1]
            provenance_entry = GRANULE_PROVENANCE.get(clean_scene)
        else:
            # Check for exact matching preprocessed raster in processed directory (no date guessing)
            processed_dir = settings.DATA_DIR / "processed" / "aligned"
            exact_aligned = processed_dir / f"{clean_scene}_aligned.tif"
            if exact_aligned.exists():
                source_tif = exact_aligned
            else:
                exact_raw = processed_dir / f"{clean_scene}.tif"
                if exact_raw.exists():
                    source_tif = exact_raw

        if source_tif and source_tif.exists():
            # Compute source_raster SHA-256 and verify historical reference checksum
            h_src = hashlib.sha256()
            with open(source_tif, "rb") as f:
                while chunk := f.read(65536):
                    h_src.update(chunk)
            source_sha256 = h_src.hexdigest().lower()

            if clean_scene in HISTORICAL_REFERENCE_REGISTRY:
                expected_src_sha = HISTORICAL_REFERENCE_REGISTRY[clean_scene]["sha256"].lower()
                if source_sha256 != expected_src_sha:
                    raise ValueError(
                        f"Historical reference raster '{source_tif.name}' failed registered checksum validation: "
                        f"expected {expected_src_sha}, got {source_sha256}. "
                        "Forged or tampered historical reference rasters are strictly rejected."
                    )

            # Identify source polarization bands mapping
            _, _, band_mapping = Sentinel1Preprocessor.identify_polarization_bands(source_tif)

            # Extract and cutline-mask sub-AOI
            Sentinel1Preprocessor.extract_sub_aoi(source_tif, target_tif, aoi_wkt)

            # Compute output target raster SHA-256
            target_sha256 = None
            if target_tif.exists():
                h = hashlib.sha256()
                with open(target_tif, "rb") as f:
                    while chunk := f.read(65536):
                        h.update(chunk)
                target_sha256 = h.hexdigest().lower()

            # Verify that provenance exists for this raster (no arbitrary unverified reuse)
            if provenance_entry is None:
                cand_prov = source_tif.with_name(f"{source_tif.stem}_provenance.json")
                if cand_prov.exists():
                    try:
                        cand_data = json.loads(cand_prov.read_text())
                        provenance_entry = cand_data.get("provenance")
                    except Exception:
                        pass

            if provenance_entry is None:
                raise ValueError(
                    f"Unverified raster: scene '{clean_scene}' ({source_tif}) has no documented calibration provenance. "
                    "Arbitrary raster reuse or unverified substitution is strictly prohibited."
                )

            graph_xml = CANONICAL_GRAPH_XML
            graph_sha256 = CANONICAL_GRAPH_SHA256
            if graph_xml.exists():
                hg = hashlib.sha256()
                with open(graph_xml, "rb") as f:
                    while chunk := f.read(65536):
                        hg.update(chunk)
                graph_sha256 = hg.hexdigest().lower()

            provenance_record = {
                "granule_id": clean_scene,
                "scene_name": scene_name,
                "acquisition_time": acq_time,
                "source_raster": str(source_tif),
                "source_raster_sha256": source_sha256,
                "output_raster": str(target_tif),
                "output_sha256": target_sha256,
                "source_band_mapping": band_mapping,
                "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
                "graph_sha256": graph_sha256,
                "processing_parameters": {
                    "radiometric_quantity": "Sigma0",
                    "radiometric_domain": "linear_power",
                    "terrain_correction": "Range-Doppler",
                    "output_bands": ["Sigma0_VH", "Sigma0_VV"],
                    "expected_crs": "EPSG:32645",
                    "pixel_spacing_m": 20.0,
                },
                "resolution": "matched_from_whitelist",
                "provenance": provenance_entry,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            provenance_path = run_dir / "rasters" / f"{Path(out_filename).stem}_provenance.json"
            atomic_write_json(provenance_path, provenance_record)

            # Stage B verification (fails closed if unverified)
            if target_tif.exists():
                verify_calibrated_raster_provenance(target_tif, provenance_path, scene_name=clean_scene)
            logger.info("Provenance record verified for granule %s → %s", clean_scene, provenance_path)
            return target_tif

        # 2. Check local raw cache or attempt download via DownloadManager
        cached_archive = self.download_manager.get_local_cached_file(scene_name)
        download_url = scene.get("download_url")

        if not cached_archive and download_url:
            logger.info("Attempting download for scene %s from %s", scene_name, download_url)
            dl_res = self.download_manager.download_product(download_url, scene_name)
            if dl_res.get("success") and dl_res.get("local_path"):
                cached_archive = Path(dl_res["local_path"])

        if cached_archive and cached_archive.exists():
            # Archive is present; attempt ESA SNAP GPT preprocessing
            preprocessor = Sentinel1Preprocessor()
            if preprocessor.is_snap_available:
                intermediate_tif = run_dir / "rasters" / f"raw_snap_{out_filename}"
                logger.info("Running ESA SNAP GPT on archive %s", cached_archive)
                snap_res = preprocessor.run_snap_gpt(cached_archive, intermediate_tif, wkt_polygon=aoi_wkt)
                actual_intermediate = Path(snap_res.get("output_path", intermediate_tif))
                Sentinel1Preprocessor.extract_sub_aoi(actual_intermediate, target_tif, aoi_wkt)

                # Compute source archive SHA-256
                h_arch = hashlib.sha256()
                with open(cached_archive, "rb") as f:
                    while chunk := f.read(65536):
                        h_arch.update(chunk)
                archive_sha256 = h_arch.hexdigest().lower()

                # Compute output target raster SHA-256
                h = hashlib.sha256()
                with open(target_tif, "rb") as f:
                    while chunk := f.read(65536):
                        h.update(chunk)
                target_sha256 = h.hexdigest().lower()

                # Identify output band mapping
                _, _, band_mapping = Sentinel1Preprocessor.identify_polarization_bands(target_tif)

                graph_xml = CANONICAL_GRAPH_XML
                graph_sha256 = CANONICAL_GRAPH_SHA256
                if graph_xml.exists():
                    hg = hashlib.sha256()
                    with open(graph_xml, "rb") as f:
                        while chunk := f.read(65536):
                            hg.update(chunk)
                    graph_sha256 = hg.hexdigest().lower()

                # Write provenance for freshly preprocessed scene
                provenance_record = {
                    "granule_id": clean_scene,
                    "scene_name": scene_name,
                    "acquisition_time": acq_time,
                    "source_archive": str(cached_archive),
                    "source_archive_sha256": archive_sha256,
                    "intermediate_raster": str(actual_intermediate),
                    "output_raster": str(target_tif),
                    "output_sha256": target_sha256,
                    "source_band_mapping": band_mapping,
                    "graph_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
                    "graph_sha256": graph_sha256,
                    "processing_parameters": {
                        "radiometric_quantity": "Sigma0",
                        "radiometric_domain": "linear_power",
                        "terrain_correction": "Range-Doppler",
                        "output_bands": ["Sigma0_VH", "Sigma0_VV"],
                        "expected_crs": "EPSG:32645",
                        "pixel_spacing_m": 20.0,
                    },
                    "resolution": "snap_preprocessed",
                    "provenance": {
                        "preprocessed_raster": str(target_tif),
                        "processing_chain": "ESA SNAP GPT s1_grd_calibration_terrain_correction.xml",
                        "processing_reference": "graphs/s1_grd_calibration_terrain_correction.xml",
                        "verification_status": "FRESHLY_PREPROCESSED",
                        "notes": "Processed from raw archive using canonical SNAP graph.",
                    },
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
                provenance_path = run_dir / "rasters" / f"{Path(out_filename).stem}_provenance.json"
                atomic_write_json(provenance_path, provenance_record)

                # Stage B verification
                verify_calibrated_raster_provenance(target_tif, provenance_path, scene_name=clean_scene)
                return target_tif
            else:
                raise RuntimeError(
                    f"Sentinel-1 archive for scene '{scene_name}' ({acq_time}) was located at '{cached_archive}', "
                    "but ESA SNAP 'gpt' binary is not accessible on the host to execute radiometric calibration and terrain correction. "
                    "Configure SNAP_GPT_PATH to enable automatic preprocessing of new acquisitions."
                )

        # 3. Neither preprocessed raster nor raw archive available
        raise FileNotFoundError(
            f"Calibrated SAR raster or satellite archive for scene '{scene_name}' ({acq_time}) "
            "could not be located or acquired. Historical data substitution is strictly disabled."
        )

    def _run_ai_inference_and_explanations(
        self,
        calibrated_tif: Path,
        water_mask_tif: Path,
        run_dir: Path,
        sample_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Execute experimental Random Forest probability prediction, 2D continuous probability GeoTIFF,
        and Saabas XAI attributions.
        """
        if not DEFAULT_MODEL_PATH.exists():
            return {"status": "SKIPPED", "reason": "Model artifact not found"}

        # Extract features
        fb = SARFeatureBuilder()
        X_sample, coords_sample, extracted = fb.prepare_feature_matrix(
            calibrated_tif,
            max_samples=sample_size,
            random_seed=42,
        )

        rf = RandomForestClassifier.load(DEFAULT_MODEL_PATH)
        probs_sample = rf.predict_proba(X_sample)
        # In binary classification, column 1 is water probability
        sample_water_probs = probs_sample[:, 1] if probs_sample.ndim == 2 else probs_sample

        # Generate full-raster continuous water probability GeoTIFF
        mean_aoi_prob = float(np.mean(sample_water_probs))
        try:
            w, h = extracted["dimensions"]
            gt = extracted["geotransform"]
            proj = extracted["projection"]
            valid_mask = extracted["valid_mask"]
            feature_maps = extracted["feature_maps"]

            valid_rows, valid_cols = np.where(valid_mask)
            n_valid = len(valid_rows)

            rf_prob_arr = np.full((h, w), -9999.0, dtype=np.float32)

            if n_valid > 0:
                FEATURE_NAMES = ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"]
                X_full = np.column_stack([feature_maps[feat][valid_mask] for feat in FEATURE_NAMES])

                chunk_size = 25000
                water_probs_full = np.empty(n_valid, dtype=np.float32)
                for start in range(0, n_valid, chunk_size):
                    end = min(start + chunk_size, n_valid)
                    p = rf.predict_proba(X_full[start:end])
                    water_probs_full[start:end] = p[:, 1] if p.ndim == 2 else p

                rf_prob_arr[valid_mask] = water_probs_full
                mean_aoi_prob = float(np.mean(water_probs_full))

            out_prob_tif = run_dir / "rasters" / "rf_probability.tif"
            driver = gdal.GetDriverByName("GTiff")
            out_ds = driver.Create(str(out_prob_tif), w, h, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE"])
            out_ds.SetGeoTransform(gt)
            out_ds.SetProjection(proj)
            b = out_ds.GetRasterBand(1)
            b.SetNoDataValue(-9999.0)
            b.WriteArray(rf_prob_arr)
            b.FlushCache()
            out_ds = None
            logger.info("Saved RF continuous water probability raster to %s", out_prob_tif)
        except Exception as e:
            logger.warning("Failed to generate full-raster RF probability: %s", e)

        # Saabas tree-path explanations
        explainer = TreePathExplainer(rf)
        sample_explanations = []
        for i in range(min(5, len(X_sample))):
            exp = explainer.explain_instance(X_sample[i], baseline_mode="ensemble_root")
            # Convert attributions_array numpy array to list for JSON serialization
            exp_clean = dict(exp)
            if "attributions_array" in exp_clean:
                del exp_clean["attributions_array"]
            sample_explanations.append(exp_clean)

        additivity_verified = sample_explanations[0]["is_additive"] if sample_explanations else True

        ai_output = {
            "model_id": "phase7a_rf_jamuna_v1",
            "sample_evaluated": len(X_sample),
            "mean_water_probability": round(mean_aoi_prob, 4),
            "additivity_verified": additivity_verified,
            "sample_explanations": sample_explanations,
        }

        (run_dir / "explanations.json").write_text(json.dumps(ai_output, indent=2))
        return {"status": "SUCCESS", "summary": ai_output}

    def render_tile(
        self,
        run_id: str,
        asset_id: str,
        z: int,
        x: int,
        y: int,
    ) -> bytes:
        """
        Dynamically render a 256x256 PNG XYZ map tile for a run's raster layer.
        """
        run_dir = self.get_run_dir(run_id)
        asset_map = {
            "transitions": run_dir / "rasters" / "transition_classes.tif",
            "transition_classes": run_dir / "rasters" / "transition_classes.tif",
            "flood_transitions": run_dir / "rasters" / "transition_classes.tif",
            "t1_water": run_dir / "rasters" / "t1_water_mask.tif",
            "t1_water_mask": run_dir / "rasters" / "t1_water_mask.tif",
            "t2_water": run_dir / "rasters" / "t2_water_mask.tif",
            "t2_water_mask": run_dir / "rasters" / "t2_water_mask.tif",
            "t1_sar": run_dir / "rasters" / "t1_calibrated.tif",
            "t1_calibrated": run_dir / "rasters" / "t1_calibrated.tif",
            "t2_sar": run_dir / "rasters" / "t2_calibrated.tif",
            "t2_calibrated": run_dir / "rasters" / "t2_calibrated.tif",
            "rf_probability": run_dir / "rasters" / "rf_probability.tif",
            "inundation_frequency": run_dir / "rasters" / "inundation_frequency.tif",
        }

        tif_path = asset_map.get(asset_id)
        if not tif_path or not tif_path.exists():
            raise FileNotFoundError(f"Raster asset '{asset_id}' not found for run '{run_id}' at path: {tif_path}")

        # Compute Web Mercator (EPSG:3857) bounds of the tile
        n = 2.0 ** z
        lon_deg_w = x / n * 360.0 - 180.0
        lat_rad_n = np.arctan(np.sinh(np.pi * (1.0 - 2.0 * y / n)))
        lat_deg_n = np.degrees(lat_rad_n)

        lon_deg_e = (x + 1) / n * 360.0 - 180.0
        lat_rad_s = np.arctan(np.sinh(np.pi * (1.0 - 2.0 * (y + 1) / n)))
        lat_deg_s = np.degrees(lat_rad_s)

        # Convert tile bounds to EPSG:3857
        def _to_3857(lon, lat):
            x_m = lon * 20037508.34 / 180.0
            y_m = np.log(np.tan((90.0 + lat) * np.pi / 360.0)) / (np.pi / 180.0)
            y_m = y_m * 20037508.34 / 180.0
            return x_m, y_m

        minx, miny = _to_3857(lon_deg_w, lat_deg_s)
        maxx, maxy = _to_3857(lon_deg_e, lat_deg_n)

        # Select resampling algorithm
        is_continuous = asset_id in ("t1_sar", "t2_sar", "rf_probability")
        resample_alg = gdal.GRA_Bilinear if is_continuous else gdal.GRA_NearestNeighbour

        # Warp tile using GDAL VSI MEM
        warp_opts = gdal.WarpOptions(
            format="MEM",
            width=256,
            height=256,
            outputBounds=[minx, miny, maxx, maxy],
            dstSRS="EPSG:3857",
            resampleAlg=resample_alg,
        )

        src_ds = gdal.Open(str(tif_path), gdal.GA_ReadOnly)
        mem_ds = gdal.Warp("", src_ds, options=warp_opts)
        src_ds = None

        if mem_ds is None:
            img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        rgba = np.zeros((256, 256, 4), dtype=np.uint8)

        if asset_id in ("t1_sar", "t2_sar"):
            band_idx = 2 if mem_ds.RasterCount >= 2 else 1
            arr = mem_ds.GetRasterBand(band_idx).ReadAsArray().astype(np.float32)
            mem_ds = None

            valid = (arr != -9999.0) & np.isfinite(arr) & (arr > 0)
            is_linear = np.median(arr[valid]) < 2.0 if np.any(valid) else False

            arr_db = np.full_like(arr, -9999.0, dtype=np.float32)
            if is_linear:
                arr_db[valid] = 10.0 * np.log10(arr[valid])
            else:
                arr_db[valid] = arr[valid]

            norm = np.clip((arr_db - (-25.0)) / 25.0, 0.0, 1.0)
            gray = (norm * 255).astype(np.uint8)

            rgba[valid, 0] = gray[valid]
            rgba[valid, 1] = gray[valid]
            rgba[valid, 2] = gray[valid]
            rgba[valid, 3] = 240

        elif asset_id == "rf_probability":
            arr = mem_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
            mem_ds = None

            valid = (arr >= 0.0) & (arr <= 1.0)
            if np.any(valid):
                from matplotlib import cm
                c_vals = (cm.cividis(np.clip(arr[valid], 0.0, 1.0)) * 255).astype(np.uint8)
                c_vals[:, 3] = 230
                rgba[valid] = c_vals

        elif asset_id == "inundation_frequency":
            arr = mem_ds.GetRasterBand(1).ReadAsArray().astype(np.int32)
            mem_ds = None

            rgba[arr == 1] = [166, 206, 227, 220]
            rgba[arr == 2] = [65, 182, 196, 230]
            rgba[arr >= 3] = [8, 81, 156, 240]

        else:
            arr = mem_ds.GetRasterBand(1).ReadAsArray()
            mem_ds = None

            palette = TRANSITION_PALETTE if asset_id == "transitions" else WATER_MASK_PALETTE
            for val, color in palette.items():
                mask = (arr == val)
                if np.any(mask):
                    rgba[mask] = color

        img = Image.fromarray(rgba, "RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
