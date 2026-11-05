"""
Earth Pulse — Phase 4A: Independent Flood Validation Framework
NASA Space Apps Challenge 2026 — Dancing with the SARs

This module implements:
1. Audit and verification of existing Phase 3B/3B.1 primary candidate inundation results.
2. Local reference-data inventory across Optical, Hydrological, Terrain, and Event Documentation.
3. Strict prevention of circular validation (rejection of SAR-derived masks as ground truth).
4. Independent validation metrics engine (Confusion Matrix, Precision, Recall, F1, IoU, Specificity, Balanced Accuracy).
5. Ingestion specifications for Sentinel-2, Landsat, BWDB river gauges, and DEM/HAND datasets.
6. Spatial block validation protocol for preventing autocorrelation leakage in future ML models.
7. Emission of phase4a_validation_readiness.json report.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from osgeo import gdal, ogr, osr

# Enable GDAL exceptions
gdal.UseExceptions()

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("EarthPulse.Phase4A_Validation")

# Constants
PRELIMINARY_AOI_WKT = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"
PIXEL_SPACING_M = 20.0
PIXEL_AREA_KM2 = 0.0004
FULL_SCENE_CELLS = 1957165
AOI_TARGET_CELLS = 1010039

# Status codes
STATUS_BLOCKED_MISSING_DATA = "BLOCKED_REFERENCE_DATA_MISSING"
STATUS_READY_FOR_EVALUATION = "READY_FOR_EVALUATION"


def find_project_root(start_path: Optional[Path] = None) -> Path:
    """Locate canonical EarthPulse-SAR project root directory."""
    candidates = []
    if start_path is not None:
        candidates.append(Path(start_path).resolve())
    candidates.append(Path.cwd().resolve())
    candidates.append(Path(__file__).resolve().parent.parent)

    for c in candidates:
        if (c / "EarthPulse-SAR").is_dir():
            return c / "EarthPulse-SAR"
        if (c / "data" / "raw" / "sentinel1").is_dir() and (c / "scripts").is_dir():
            return c
        for parent in c.parents:
            if (parent / "EarthPulse-SAR").is_dir():
                return parent / "EarthPulse-SAR"
            if (parent / "data" / "raw" / "sentinel1").is_dir() and (parent / "scripts").is_dir():
                return parent

    fallback = Path("/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR")
    if fallback.is_dir():
        return fallback
    raise FileNotFoundError("Could not identify EarthPulse-SAR project root directory.")


def audit_phase3b_results(project_root: Path) -> Dict[str, Any]:
    """
    Verifies that the primary candidate inundation outputs from Phase 3B/3B.1
    exist and match the certified benchmark counts.
    """
    # Prefer Phase 3B.1 QC raster if present, else fallback to Phase 3B
    proc_qc_dir = project_root / "data" / "processed" / "phase3b_qc"
    proc_dir = project_root / "data" / "processed" / "phase3b"

    trans_path = proc_qc_dir / "transition_primary_qc.tif"
    if not trans_path.is_file():
        trans_path = proc_dir / "transition_primary.tif"
    if not trans_path.is_file():
        raise FileNotFoundError(f"Missing primary transition raster in {proc_qc_dir} and {proc_dir}")

    # Load raster
    ds = gdal.Open(str(trans_path), gdal.GA_ReadOnly)
    w, h = ds.RasterXSize, ds.RasterYSize
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    trans_arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None

    # Rasterize AOI
    srs_raster = osr.SpatialReference()
    srs_raster.ImportFromWkt(proj)
    srs_wgs84 = osr.SpatialReference()
    srs_wgs84.ImportFromEPSG(4326)
    srs_wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(srs_wgs84, srs_raster)
    geom = ogr.CreateGeometryFromWkt(PRELIMINARY_AOI_WKT)
    geom.Transform(ct)

    mem_drv = ogr.GetDriverByName("MEM")
    mem_ds = mem_drv.CreateDataSource("mem_aoi")
    mem_lyr = mem_ds.CreateLayer("aoi", srs_raster, ogr.wkbPolygon)
    feat = ogr.Feature(mem_lyr.GetLayerDefn())
    feat.SetGeometry(geom)
    mem_lyr.CreateFeature(feat)

    target_drv = gdal.GetDriverByName("MEM")
    target_ds = target_drv.Create("mem_mask", w, h, 1, gdal.GDT_Byte)
    target_ds.SetGeoTransform(gt)
    target_ds.SetProjection(proj)
    gdal.RasterizeLayer(target_ds, [1], mem_lyr, burn_values=[1])
    aoi_mask = (target_ds.GetRasterBand(1).ReadAsArray() == 1)
    mem_ds = None
    target_ds = None

    aoi_data = trans_arr[aoi_mask]
    c1 = int(np.sum(aoi_data == 1))
    c2 = int(np.sum(aoi_data == 2))
    c3 = int(np.sum(aoi_data == 3))
    c4 = int(np.sum(aoi_data == 4))
    c5 = int(np.sum(aoi_data == 5))
    c6 = int(np.sum(aoi_data == 6))
    total_aoi = len(aoi_data)

    # Expected values verification
    expected = {
        "aoi_total_cells": 1010039,
        "newly_inundated_cells": 146992,
        "gross_expansion_km2": 58.7968,
        "receded_water_cells": 1634,
        "gross_recession_km2": 0.6536,
        "net_area_change_km2": 58.1432,
        "indeterminate_cells": 16242,
        "indeterminate_km2": 6.4968,
        "nodata_cells": 61,
        "nodata_km2": 0.0244,
    }

    actual = {
        "aoi_total_cells": total_aoi,
        "persistent_water_cells": c1,
        "persistent_water_km2": round(c1 * PIXEL_AREA_KM2, 4),
        "newly_inundated_cells": c2,
        "gross_expansion_km2": round(c2 * PIXEL_AREA_KM2, 4),
        "receded_water_cells": c3,
        "gross_recession_km2": round(c3 * PIXEL_AREA_KM2, 4),
        "net_area_change_km2": round((c2 - c3) * PIXEL_AREA_KM2, 4),
        "persistent_non_water_cells": c4,
        "persistent_non_water_km2": round(c4 * PIXEL_AREA_KM2, 4),
        "indeterminate_cells": c5,
        "indeterminate_km2": round(c5 * PIXEL_AREA_KM2, 4),
        "nodata_cells": c6,
        "nodata_km2": round(c6 * PIXEL_AREA_KM2, 4),
        "reconciliation_identity_holds": bool((c2 - c3) == (c1 + c2) - (c1 + c3)),
        "all_benchmarks_match": bool(
            total_aoi == expected["aoi_total_cells"]
            and c2 == expected["newly_inundated_cells"]
            and c3 == expected["receded_water_cells"]
            and c5 == expected["indeterminate_cells"]
            and c6 == expected["nodata_cells"]
        ),
    }
    return actual


def scan_local_reference_inventory(project_root: Path) -> Dict[str, Any]:
    """
    Inspects the project directory for independent reference data across 10 categories.
    Strictly verifies provenance and guards against circular validation.
    """
    ref_dir = project_root / "data" / "reference"
    categories = {
        "optical": ref_dir / "optical",
        "hydrology": ref_dir / "hydrology",
        "terrain": ref_dir / "terrain",
        "event_documents": ref_dir / "event_documents",
    }

    found_files: Dict[str, List[Dict[str, Any]]] = {k: [] for k in categories.keys()}
    circular_rejections: List[str] = []

    # Check reference directories
    for cat, p in categories.items():
        if p.is_dir():
            for item in p.rglob("*"):
                if item.is_file():
                    # Reject SAR candidate masks or intermediate files
                    name_lower = item.name.lower()
                    path_str = str(item).lower()
                    if any(s in path_str for s in ["sigma0", "candidate_mask", "phase3a", "phase3b", "lee_", "otsu"]):
                        circular_rejections.append(str(item))
                        continue

                    # Record potential reference file
                    found_files[cat].append({
                        "filename": item.name,
                        "path": str(item.relative_to(project_root)),
                        "size_bytes": item.stat().st_size,
                    })

    # Also inspect data/raw and root for any optical, gauge, or DEM files
    other_scans = [
        ("sentinel2_optical", list((project_root / "data").glob("**/*S2*.*"))),
        ("landsat_optical", list((project_root / "data").glob("**/*LC08*.*")) + list((project_root / "data").glob("**/*LC09*.*"))),
        ("dem_terrain", list((project_root / "data").glob("**/*dem*.*")) + list((project_root / "data").glob("**/*hand*.*"))),
        ("gauge_hydrology", list((project_root / "data").glob("**/*gauge*.*")) + list((project_root / "data").glob("**/*bwdb*.*"))),
    ]

    total_reference_count = sum(len(v) for v in found_files.values())
    status = STATUS_READY_FOR_EVALUATION if total_reference_count > 0 else STATUS_BLOCKED_MISSING_DATA

    inventory_report = {
        "status": status,
        "total_independent_reference_files": total_reference_count,
        "categories": {
            "sentinel2_imagery": {"available": False, "count": 0, "provenance": "Missing"},
            "landsat_imagery": {"available": False, "count": 0, "provenance": "Missing"},
            "cloud_masked_optical_products": {"available": False, "count": 0, "provenance": "Missing"},
            "water_reference_masks": {"available": False, "count": 0, "provenance": "Missing"},
            "dem_datasets": {"available": False, "count": 0, "provenance": "Missing"},
            "hand_datasets": {"available": False, "count": 0, "provenance": "Missing"},
            "river_gauge_observations": {"available": False, "count": 0, "provenance": "Missing"},
            "bwdb_water_level_csv": {"available": False, "count": 0, "provenance": "Missing"},
            "official_flood_reports": {"available": False, "count": 0, "provenance": "Missing"},
            "other_hydrological_evidence": {"available": False, "count": 0, "provenance": "Missing"},
        },
        "circular_validation_guard": {
            "sar_masks_rejected_as_ground_truth": len(circular_rejections),
            "rejected_paths": circular_rejections,
            "rule": "SAR-derived candidate masks cannot validate SAR-derived candidate masks (Circular Validation Fallacy).",
        },
        "registered_datasets_found": found_files,
        "blocking_notice": (
            "Independent scientific validation is currently BLOCKED because no independent ground truth "
            "(optical cloud-masked water masks, BWDB river stage gauges, or DEM/HAND rasters) exists locally in the workspace. "
            "Governance rules strictly prohibit downloading external datasets or inventing observations."
        ) if status == STATUS_BLOCKED_MISSING_DATA else "Reference data available for evaluation.",
    }
    return inventory_report


def validate_reference_dataset_provenance(
    meta: Dict[str, Any],
    require_quality_info: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Ensures that any candidate reference dataset records all required provenance fields
    and is not a self-referential SAR product.
    """
    required = [
        "dataset_name", "category", "provider", "source_url_or_citation",
        "spatial_extent_wkt", "crs", "resolution", "license_or_usage_conditions",
        "intended_validation_purpose", "local_file_path"
    ]
    errors = []
    for f in required:
        if f not in meta or not str(meta[f]).strip():
            errors.append(f"Missing required metadata field: '{f}'")

    # Date field: allow original_acquisition_date or acquisition_date_or_interval
    if not (meta.get("original_acquisition_date") or meta.get("acquisition_date_or_interval")):
        errors.append("Missing required metadata field: 'acquisition_date' ('original_acquisition_date' or 'acquisition_date_or_interval')")

    # Processing field: allow processing_history or processing_method
    if not (meta.get("processing_history") or meta.get("processing_method")):
        errors.append("Missing required metadata field: 'processing_history' or 'processing_method'")

    # Quality information requirement
    if require_quality_info or "quality_information" in meta:
        if not meta.get("quality_information") or not str(meta.get("quality_information")).strip():
            errors.append("Missing required metadata field: 'quality_information'")

    # Anti-circular validation check
    path_val = str(meta.get("local_file_path", "")).lower()
    name_val = str(meta.get("dataset_name", "")).lower()
    method_val = str(meta.get("processing_method", meta.get("processing_history", ""))).lower()

    if any(s in path_val or s in name_val or s in method_val for s in ["sentinel-1", "sar", "otsu", "lee_5x5", "lee_3x3", "sigma0"]):
        errors.append("CIRCULAR_VALIDATION_ERROR: SAR-derived water masks cannot serve as independent ground truth.")

    return len(errors) == 0, errors


def validate_gauge_reading_input(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates a river gauge observation record.
    Rejects unverified gauge values, missing source citations, or unverified danger levels.
    """
    errors = []
    required = ["station_id", "station_name", "timestamp_utc", "water_level_m", "vertical_datum", "source_citation"]
    for f in required:
        if f not in record or str(record[f]).strip() == "":
            errors.append(f"Missing required gauge field: '{f}'")

    if not record.get("provider_verified", False):
        errors.append("UNVERIFIED_GAUGE_DATA_REJECTED: Provider is not authenticated or observation is unverified.")

    citation = str(record.get("source_citation", "")).strip().upper()
    if not citation or citation in ["UNVERIFIED", "ASSUMPTION", "NONE"]:
        errors.append("UNVERIFIED_GAUGE_DATA_REJECTED: Missing official BWDB/FFWC citation for gauge readings.")

    # Danger level check
    if "danger_level_m" in record and record["danger_level_m"] is not None:
        dl_cite = str(record.get("danger_level_citation", "")).strip().upper()
        if not dl_cite or dl_cite in ["UNVERIFIED", "ASSUMPTION", "NONE"]:
            errors.append("UNVERIFIED_DANGER_LEVEL_REJECTED: Danger level must have an official published citation.")

    return len(errors) == 0, errors


def validate_terrain_threshold_input(params: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates proposed terrain thresholds (elevation cutoff, HAND threshold).
    Rejects unsupported elevation thresholds when unsupported by local DEM data.
    """
    errors = []
    if "dem_path" not in params or not params["dem_path"]:
        errors.append("UNSUPPORTED_TERRAIN_THRESHOLD_REJECTED: No local DEM raster available to evaluate terrain thresholds.")

    if not params.get("dem_provenance_verified", False):
        errors.append("UNSUPPORTED_TERRAIN_THRESHOLD_REJECTED: Terrain dataset provenance is unverified.")

    if "elevation_range_m" in params:
        cite = str(params.get("elevation_calibration_source", "")).strip().upper()
        if not cite or cite in ["UNVERIFIED", "ASSUMPTION", "NONE"]:
            errors.append("UNSUPPORTED_TERRAIN_THRESHOLD_REJECTED: Elevation range (e.g. 11-18m) is an uncalibrated assumption without survey calibration.")

    if "hand_threshold_m" in params:
        cite = str(params.get("hand_calibration_source", "")).strip().upper()
        if not cite or cite in ["UNVERIFIED", "ASSUMPTION", "NONE"]:
            errors.append("UNSUPPORTED_TERRAIN_THRESHOLD_REJECTED: HAND threshold is an uncalibrated assumption without hydraulic modeling calibration.")

    return len(errors) == 0, errors


def compute_validation_metrics(
    candidate_mask: np.ndarray,
    reference_mask: np.ndarray,
    valid_domain_mask: Optional[np.ndarray] = None,
    candidate_nodata_val: int = 6,
    candidate_indet_val: int = 5,
    reference_nodata_val: int = 255,
    reference_uncertain_val: Union[int, List[int], Tuple[int, ...]] = 254,
) -> Dict[str, Any]:
    """
    Calculates pixel-level validation metrics against genuine independent reference ground truth.
    Strictly excludes NoData and uncertain pixels from both sources.
    """
    assert candidate_mask.shape == reference_mask.shape, "Shape mismatch between candidate and reference rasters"

    if valid_domain_mask is not None:
        c_sub = candidate_mask[valid_domain_mask]
        r_sub = reference_mask[valid_domain_mask]
    else:
        c_sub = candidate_mask.ravel()
        r_sub = reference_mask.ravel()

    total_pixels = len(c_sub)

    # Exclusions
    c_nodata = (c_sub == candidate_nodata_val)
    c_indet = (c_sub == candidate_indet_val)
    r_nodata = (r_sub == reference_nodata_val) | (r_sub < 0)
    if isinstance(reference_uncertain_val, (list, tuple, set, np.ndarray)):
        r_uncertain = np.isin(r_sub, list(reference_uncertain_val))
    else:
        # Also treat any value in [250, 254] as uncertain
        r_uncertain = (r_sub == reference_uncertain_val) | ((r_sub >= 250) & (r_sub < reference_nodata_val))

    excluded_mask = c_nodata | c_indet | r_nodata | r_uncertain
    valid_mask = ~excluded_mask

    c_valid = c_sub[valid_mask]
    r_valid = r_sub[valid_mask]
    n_valid = len(c_valid)

    if n_valid == 0:
        return {
            "status": "NO_VALID_OVERLAPPING_PIXELS",
            "total_pixels_considered": total_pixels,
            "valid_comparison_pixels": 0,
            "excluded_candidate_nodata": int(np.sum(c_nodata)),
            "excluded_candidate_indeterminate": int(np.sum(c_indet)),
            "excluded_reference_nodata": int(np.sum(r_nodata)),
            "excluded_reference_uncertain": int(np.sum(r_uncertain)),
            "confusion_matrix": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "metrics": None,
        }

    # Binary comparison (1 = Water, 0 = Non-Water)
    tp = int(np.sum((c_valid == 1) & (r_valid == 1)))
    fp = int(np.sum((c_valid == 1) & (r_valid == 0)))
    tn = int(np.sum((c_valid == 0) & (r_valid == 0)))
    fn = int(np.sum((c_valid == 0) & (r_valid == 1)))

    # Class distribution analysis
    pos_pred = tp + fp
    pos_ref = tp + fn
    neg_pred = tn + fn
    neg_ref = tn + fp

    flags = {
        "positive_predictions_count": pos_pred,
        "positive_reference_count": pos_ref,
        "negative_predictions_count": neg_pred,
        "negative_reference_count": neg_ref,
        "precision_undefined": bool(pos_pred == 0),
        "recall_undefined": bool(pos_ref == 0),
        "f1_undefined": False,
        "specificity_undefined": bool(neg_ref == 0),
        "class_coverage_complete": bool(pos_ref > 0 and neg_ref > 0 and pos_pred > 0 and neg_pred > 0),
        "notes": [],
    }

    # Zero-division handling with documented class presence
    if pos_pred == 0:
        precision = 0.0
        flags["notes"].append("Precision undefined: Candidate mask contains 0 positive predictions (TP+FP=0).")
    else:
        precision = tp / pos_pred

    if pos_ref == 0:
        recall = 0.0
        flags["notes"].append("Recall undefined: Reference ground truth contains 0 positive labels (TP+FN=0).")
    else:
        recall = tp / pos_ref

    if (precision + recall) == 0:
        f1 = 0.0
        flags["f1_undefined"] = True
        flags["notes"].append("F1 undefined: Sum of precision and recall is 0.")
    else:
        f1 = 2 * precision * recall / (precision + recall)

    iou_denom = tp + fp + fn
    if iou_denom == 0:
        iou = 1.0 if (tn > 0) else 0.0
        flags["notes"].append("IoU edge case: Zero positive pixels in both candidate and reference (pure non-water agreement).")
    else:
        iou = tp / iou_denom

    if neg_ref == 0:
        specificity = 0.0
        flags["notes"].append("Specificity undefined: Reference ground truth contains 0 negative labels (TN+FP=0).")
    else:
        specificity = tn / neg_ref

    balanced_acc = (recall + specificity) / 2.0
    overall_acc = ((tp + tn) / n_valid) if n_valid > 0 else 0.0

    return {
        "status": "VALIDATION_COMPUTED",
        "total_pixels_considered": total_pixels,
        "valid_comparison_pixels": n_valid,
        "valid_percentage": round(n_valid / total_pixels * 100.0, 4) if total_pixels > 0 else 0.0,
        "excluded_candidate_nodata": int(np.sum(c_nodata)),
        "excluded_candidate_indeterminate": int(np.sum(c_indet)),
        "excluded_reference_nodata": int(np.sum(r_nodata)),
        "excluded_reference_uncertain": int(np.sum(r_uncertain)),
        "confusion_matrix": {
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": fn,
        },
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "intersection_over_union": round(iou, 4),
            "specificity": round(specificity, 4),
            "balanced_accuracy": round(balanced_acc, 4),
            "overall_accuracy": round(overall_acc, 4),
        },
        "class_distribution_flags": flags,
    }


def generate_validation_readiness_report(
    project_root: Path,
    output_path: Path,
) -> Dict[str, Any]:
    """Compiles the Phase 4A Validation Readiness Report."""
    phase3b_audit = audit_phase3b_results(project_root)
    inventory = scan_local_reference_inventory(project_root)

    report = {
        "project": "NASA Space Apps Challenge 2026 — Dancing with the SARs",
        "phase": "Phase 4A: Independent Flood Validation Framework",
        "study_area": {
            "reach": "Jamuna River, Kazipur / Sirajganj, Bangladesh",
            "aoi_wkt": PRELIMINARY_AOI_WKT,
            "target_crs": "EPSG:32645",
            "target_resolution_m": PIXEL_SPACING_M,
        },
        "phase3b_candidate_results_audit": phase3b_audit,
        "local_reference_inventory": inventory,
        "evidence_taxonomy": {
            "tier_1_flood_event_documentation": {
                "definition": "Government situation reports (NDRCC/DMB), humanitarian assessments (NIRAPAD, UN OCHA), and news records.",
                "scientific_status": "Confirms regional flood occurrence; does not provide pixel-level boundary truth.",
            },
            "tier_2_hydrological_corroboration": {
                "definition": "BWDB/FFWC daily river stage readings at Kazipur and Sirajganj gauge stations.",
                "scientific_status": "Provides 1D hydraulic temporal corroboration (e.g. water level relative to Danger Level); does not delineate 2D spatial inundation footprint.",
            },
            "tier_3_pixel_level_reference_validation": {
                "definition": "Concurrent high-resolution optical water masks (Sentinel-2 MSI 10m/20m or Landsat 8/9 30m) with cloud/shadow masking.",
                "scientific_status": "Provides direct spatial ground truth for confusion matrix and IoU metrics.",
            },
            "tier_4_terrain_contextual_assessment": {
                "definition": "Copernicus GLO-30 DEM, FABDEM, and Height Above Nearest Drainage (HAND).",
                "scientific_status": "Provides topographic plausibility checks (depressions vs terraces) and layover/shadow boundaries; not dynamic water truth.",
            },
        },
        "optical_ingestion_specification": {
            "sentinel_2": {
                "sensor": "MSI Level-2A (Bottom of Atmosphere Reflectance)",
                "band_selection": "B03 (Green, 10m), B08 (NIR, 10m), B11 (SWIR1, 20m), B12 (SWIR2, 20m), SCL (Scene Classification Layer, 20m)",
                "cloud_shadow_masking": "Mask SCL values 3 (Cloud Shadow), 7 (Low Proba Cloud), 8 (Med Proba Cloud), 9 (High Proba Cloud), 10 (Cirrus), 11 (Snow/Ice)",
                "water_indices": ["MNDWI = (Green - SWIR1) / (Green + SWIR1)", "AWEInsh = Blue + 2.5*Green - 1.5*(NIR + SWIR1) - 0.25*SWIR2"],
                "spatial_alignment": "Bicubic / area-weighted aggregation to common 20m grid (EPSG:32645) matching june10_aligned.tif",
                "monsoon_constraint": "Heavy cloud cover during June-July monsoon in Bangladesh requires multi-day temporal search window (+/- 5 days of SAR epoch)",
            },
            "landsat_8_9": {
                "sensor": "OLI/TIRS Collection 2 Level-2 Surface Reflectance",
                "band_selection": "Band 3 (Green, 30m), Band 5 (NIR, 30m), Band 6 (SWIR1, 30m), QA_PIXEL (Quality Bitmask, 30m)",
                "cloud_masking": "Dilated cloud bit 1, Cirrus bit 2, Cloud bit 3, Cloud Shadow bit 4",
                "spatial_alignment": "Reproject and bilinear resample from 30m to 20m EPSG:32645",
            },
        },
        "hydrological_gauge_specification": {
            "source_authority": "Bangladesh Water Development Board (BWDB) / Flood Forecasting and Warning Centre (FFWC)",
            "key_stations_preliminary_reference": [
                {
                    "station_id": "SW46.9",
                    "station_name": "Sirajganj",
                    "river": "Jamuna",
                    "danger_level_m_pwd": 13.35,
                    "provenance_classification": "UNVERIFIED",
                    "operational_rule": "PROHIBITED_FROM_AUTOMATIC_USE_WITHOUT_OFFICIAL_CITATION",
                    "notes": "Preliminary literature value; requires official BWDB bulletin citation."
                },
                {
                    "station_id": "SW46.9A",
                    "station_name": "Kazipur",
                    "river": "Jamuna",
                    "danger_level_m_pwd": 15.25,
                    "provenance_classification": "UNVERIFIED",
                    "operational_rule": "PROHIBITED_FROM_AUTOMATIC_USE_WITHOUT_OFFICIAL_CITATION",
                    "notes": "Preliminary literature value; requires official BWDB bulletin citation."
                },
                {
                    "station_id": "SW46.8",
                    "station_name": "Sariakandi",
                    "river": "Jamuna",
                    "danger_level_m_pwd": 16.70,
                    "provenance_classification": "UNVERIFIED",
                    "operational_rule": "PROHIBITED_FROM_AUTOMATIC_USE_WITHOUT_OFFICIAL_CITATION",
                    "notes": "Located north of AOI; preliminary literature value."
                },
            ],
            "required_fields_for_operational_ingestion": [
                "station_id", "station_name", "river", "timestamp_utc",
                "water_level_m", "danger_level_m", "vertical_datum", "source_citation",
                "provider_verified", "quality_flag"
            ],
            "vertical_datum": {
                "datum_name": "Public Works Department (PWD) Datum",
                "pwd_to_msl_formula": "PWD = MSL - 0.46m (Regional approximation)",
                "provenance_classification": "ASSUMPTION",
                "operational_rule": "UNVERIFIED_LOCAL_DATUM_OFFSET",
                "notes": "Exact geodetic offset against Survey of Bangladesh (SoB) MSL requires local benchmark monument verification."
            },
        },
        "terrain_validation_specification": {
            "recommended_dem": "Copernicus GLO-30 or FABDEM (bare-earth corrected)",
            "dem_availability_in_workspace": False,
            "hand_model": "Height Above Nearest Drainage (HAND)",
            "preliminary_hypotheses": {
                "floodplain_elevation_range_m": {
                    "range": [11.0, 18.0],
                    "provenance_classification": "ASSUMPTION",
                    "operational_rule": "PROHIBITED_FROM_AUTOMATIC_USE_WITHOUT_CALIBRATED_DEM",
                    "notes": "Unverified regional rule-of-thumb; must not be used as active filter without local DEM."
                },
                "hand_connectivity_threshold_m": {
                    "threshold": 3.0,
                    "provenance_classification": "ASSUMPTION",
                    "operational_rule": "PROHIBITED_FROM_AUTOMATIC_USE_WITHOUT_CALIBRATED_DEM",
                    "notes": "Unverified threshold; requires hydrodynamic drainage calibration."
                },
                "barind_tract_pleistocene_elevation_m": {
                    "threshold": 25.0,
                    "provenance_classification": "ASSUMPTION",
                    "operational_rule": "PROHIBITED_FROM_AUTOMATIC_USE_WITHOUT_CALIBRATED_DEM",
                    "notes": "Regional geomorphological assumption; no local DEM present."
                }
            },
            "validation_utility": [
                "Assess topographic plausibility of candidate inundation (water flows downhill).",
                "Examine hydraulic connectivity between candidate water and the active river network.",
                "Delineate potential radar shadow and layover along tall embankments.",
                "CRITICAL: DEM/HAND information is supporting terrain context, NOT independent flood ground truth."
            ],
        },
        "spatial_block_validation_ml_protocol": {
            "motivation": "Prevent spatial autocorrelation data leakage between training and testing sets in future ML classifiers.",
            "design": "Spatial block cross-validation (5 km x 5 km grid blocks with 500 m exclusion buffer / halo zones between folds).",
            "metric_reporting": "Report spatially stratified IoU and Balanced Accuracy across independent blocks.",
        },
        "validation_readiness_status": inventory["status"],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Saved validation readiness report: {output_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description="Earth Pulse — Phase 4A: Independent Flood Validation Framework")
    parser.add_argument("--project-root", type=str, default=None, help="Path to project root")
    args = parser.parse_args()

    root = find_project_root(Path(args.project_root) if args.project_root else None)
    out_json = root / "data" / "metadata" / "phase4a_validation_readiness.json"
    generate_validation_readiness_report(root, out_json)


if __name__ == "__main__":
    main()

