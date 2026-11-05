"""
Earth Pulse — Phase 4B: Common Reference Data Quality Control Interface
NASA Space Apps Challenge 2026 — Dancing with the SARs

This module provides common quality-control, provenance-auditing, and validation
interfaces for independent reference datasets:
1. Sentinel-2 MSI Level-2A optical imagery.
2. Landsat 8/9 Level-2 Surface Reflectance.
3. BWDB / FFWC hydrological river stage records.
4. Copernicus GLO-30 DEM.

Validation statuses:
- READY: All structural, spatial, and provenance checks pass.
- WARNING: Minor non-fatal anomalies (e.g. moderate cloud cover, acceptable spatial offset).
- BLOCKED: Missing prerequisites or files required for processing.
- REJECTED: Fails scientific validity, integrity check, anti-circular validation, or missing provenance.
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from osgeo import gdal, ogr, osr

# Enable GDAL exceptions
gdal.UseExceptions()

# Logging Configuration
logger = logging.getLogger("EarthPulse.ReferenceValidation")

# Spatial AOI Constant (Kazipur / Sirajganj Jamuna reach)
STUDY_AREA_AOI_WKT = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"
SAR_TARGET_EPSG = 32645
SAR_TARGET_RESOLUTION = 20.0


class ValidationStatus(str, Enum):
    """Reference data quality control status levels."""
    READY = "READY"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


@dataclass
class ValidationResult:
    """Standardized validation report for reference inputs."""
    status: ValidationStatus
    dataset_name: str
    dataset_type: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checks: Dict[str, bool] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def is_acceptable(self) -> bool:
        """True if dataset is READY or has acceptable WARNINGs only."""
        return self.status in [ValidationStatus.READY, ValidationStatus.WARNING]

    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to dictionary."""
        d = asdict(self)
        d["status"] = self.status.value
        return d


def compute_sha256(file_path: Union[str, Path], chunk_size: int = 65536) -> str:
    """
    Computes cryptographic SHA-256 checksum of a file.

    Parameters
    ----------
    file_path : Union[str, Path]
        Path to the target file.
    chunk_size : int
        Buffer size for chunked hashing.

    Returns
    -------
    str
        Hexadecimal SHA-256 digest string.
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found for checksum computation: {p}")

    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def check_anti_circular_validation(text_identifiers: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Guards against circular validation by rejecting any dataset, file path,
    or algorithm descriptor originating from Sentinel-1 or SAR processing.

    Parameters
    ----------
    text_identifiers : List[str]
        List of strings (names, paths, descriptions) to screen.

    Returns
    -------
    Tuple[bool, Optional[str]]
        (is_circular, failure_reason)
    """
    sar_prohibited_terms = [
        "sentinel-1", "s1a", "s1b", "sigma0", "gamma0", "beta0",
        "lee_filter", "lee_3x3", "lee_5x5", "otsu", "dual_and",
        "sar_derived", "transition_primary", "candidate_mask",
        "phase3a", "phase3b"
    ]
    for text in text_identifiers:
        t_low = text.lower()
        for term in sar_prohibited_terms:
            if term in t_low:
                return True, (
                    f"CIRCULAR_VALIDATION_ERROR: Identified SAR-derived term '{term}' in identifier '{text}'. "
                    "SAR-derived water masks or intermediates cannot serve as independent ground truth."
                )
    return False, None


def validate_provenance_metadata(meta: Dict[str, Any]) -> ValidationResult:
    """
    Validates provenance completeness, authentic source citations, and anti-circular rules.

    Required Fields:
    - dataset_id (or dataset_name)
    - provider
    - product_name
    - source_identifier
    - source_url_or_citation
    - acquisition_date (or original_acquisition_date)
    - processing_level
    - spatial_extent
    - crs
    - spatial_resolution
    - original_filename
    - sha256
    - processing_history
    - license_or_usage_conditions
    - quality_information
    - intended_validation_purpose
    """
    errors: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, bool] = {}

    d_name = meta.get("dataset_name") or meta.get("dataset_id") or "Unknown_Dataset"
    d_type = meta.get("category") or meta.get("dataset_type") or "Unknown_Type"

    # 1. Required fields check
    required_fields = [
        ("dataset_id", ["dataset_id", "dataset_name"]),
        ("provider", ["provider"]),
        ("product_name", ["product_name"]),
        ("source_identifier", ["source_identifier"]),
        ("source_citation", ["source_url_or_citation", "source_citation"]),
        ("acquisition_date", ["acquisition_date", "original_acquisition_date", "observation_datetime"]),
        ("processing_level", ["processing_level"]),
        ("spatial_extent", ["spatial_extent", "spatial_extent_wkt"]),
        ("crs", ["crs"]),
        ("spatial_resolution", ["spatial_resolution", "resolution"]),
        ("original_filename", ["original_filename", "local_file_path"]),
        ("sha256", ["sha256", "checksum_sha256"]),
        ("processing_history", ["processing_history", "processing_method"]),
        ("license", ["license_or_usage_conditions", "license"]),
        ("quality_info", ["quality_information", "quality_flag"]),
        ("purpose", ["intended_validation_purpose"]),
    ]

    for label, keys in required_fields:
        found = any(k in meta and str(meta[k]).strip() != "" for k in keys)
        checks[f"has_{label}"] = found
        if not found:
            errors.append(f"Missing required provenance field: '{label}' (accepted keys: {keys})")

    # 2. Anti-circular check
    identifiers_to_screen = [
        d_name,
        d_type,
        str(meta.get("original_filename", "")),
        str(meta.get("local_file_path", "")),
        str(meta.get("processing_history", "")),
        str(meta.get("intended_validation_purpose", "")),
    ]
    is_circular, circular_reason = check_anti_circular_validation(identifiers_to_screen)
    checks["anti_circular_validation"] = not is_circular
    if is_circular and circular_reason:
        errors.append(circular_reason)

    # 3. Citation authenticity
    citation = str(meta.get("source_url_or_citation", meta.get("source_citation", ""))).strip().upper()
    checks["valid_citation"] = bool(citation and citation not in ["UNVERIFIED", "ASSUMPTION", "NONE", "UNKNOWN"])
    if not checks["valid_citation"]:
        errors.append("UNVERIFIED_CITATION: Source citation is unverified, missing, or labeled ASSUMPTION/NONE.")

    # Status determination
    if errors:
        status = ValidationStatus.REJECTED
    elif warnings:
        status = ValidationStatus.WARNING
    else:
        status = ValidationStatus.READY

    return ValidationResult(
        status=status,
        dataset_name=str(d_name),
        dataset_type=str(d_type),
        errors=errors,
        warnings=warnings,
        checks=checks,
        details={"metadata_evaluated": meta},
    )


def validate_raster_dataset(
    raster_path: Union[str, Path],
    expected_epsg: Optional[int] = None,
    expected_res: Optional[Tuple[float, float]] = None,
    aoi_wkt: Optional[str] = STUDY_AREA_AOI_WKT,
    dataset_name: Optional[str] = None,
    dataset_type: str = "Raster",
) -> ValidationResult:
    """
    Validates physical GeoTIFF raster properties:
    - Readability and GDAL driver support.
    - Projection / CRS validity.
    - Geotransform and pixel resolution.
    - Bounding box intersection with target AOI.
    - Band count and NoData value validity.
    - Non-empty pixel data (valid pixel fraction).
    """
    p = Path(raster_path)
    d_name = dataset_name or p.name
    errors: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, bool] = {}
    details: Dict[str, Any] = {}

    if not p.is_file():
        return ValidationResult(
            status=ValidationStatus.BLOCKED,
            dataset_name=d_name,
            dataset_type=dataset_type,
            errors=[f"Raster file does not exist on disk: {p}"],
            checks={"file_exists": False},
        )

    checks["file_exists"] = True

    # 1. GDAL Open
    ds = None
    try:
        ds = gdal.Open(str(p), gdal.GA_ReadOnly)
        if ds is None:
            raise RuntimeError("GDAL returned null dataset pointer.")
    except Exception as e:
        return ValidationResult(
            status=ValidationStatus.REJECTED,
            dataset_name=d_name,
            dataset_type=dataset_type,
            errors=[f"Failed to open raster with GDAL: {e}"],
            checks={"gdal_readable": False},
        )

    checks["gdal_readable"] = True

    try:
        w = ds.RasterXSize
        h = ds.RasterYSize
        num_bands = ds.RasterCount
        gt = ds.GetGeoTransform()
        proj_wkt = ds.GetProjection()

        details["width"] = w
        details["height"] = h
        details["num_bands"] = num_bands
        details["geotransform"] = gt

        if w <= 0 or h <= 0 or num_bands <= 0:
            errors.append(f"Invalid raster dimensions: {w}x{h}, bands: {num_bands}")
            checks["valid_dimensions"] = False
        else:
            checks["valid_dimensions"] = True

        # 2. CRS Inspection
        srs = osr.SpatialReference()
        if proj_wkt:
            srs.ImportFromWkt(proj_wkt)
            srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            auth_name = srs.GetAuthorityName(None)
            auth_code = srs.GetAuthorityCode(None)
            details["crs_authority"] = f"{auth_name}:{auth_code}" if auth_name else "Unknown"
        else:
            auth_code = None
            details["crs_authority"] = "None"

        if not proj_wkt:
            errors.append("Missing CRS / projection information in raster.")
            checks["crs_valid"] = False
        elif expected_epsg is not None:
            if auth_code and auth_code == str(expected_epsg):
                checks["crs_valid"] = True
            else:
                target_srs = osr.SpatialReference()
                target_srs.ImportFromEPSG(expected_epsg)
                if srs.IsSame(target_srs):
                    checks["crs_valid"] = True
                else:
                    warnings.append(
                        f"Raster CRS ({details['crs_authority']}) does not match expected EPSG:{expected_epsg}. "
                        "Reprojection/alignment will be required."
                    )
                    checks["crs_valid"] = True  # Reprojection can handle it
        else:
            checks["crs_valid"] = True

        # 3. Resolution Inspection
        if gt:
            res_x = abs(gt[1])
            res_y = abs(gt[5])
            details["resolution"] = (res_x, res_y)
            if expected_res is not None:
                exp_x, exp_y = expected_res
                if abs(res_x - exp_x) > 1e-4 or abs(res_y - exp_y) > 1e-4:
                    warnings.append(f"Pixel resolution ({res_x}, {res_y}) deviates from target ({exp_x}, {exp_y}).")
            checks["resolution_valid"] = (res_x > 0 and res_y > 0)
        else:
            errors.append("Missing GeoTransform matrix in raster.")
            checks["resolution_valid"] = False

        # 4. AOI Bounding Box Intersection
        if aoi_wkt and gt and proj_wkt:
            try:
                min_x = gt[0]
                max_x = gt[0] + w * gt[1]
                max_y = gt[3]
                min_y = gt[3] + h * gt[5]
                if min_x > max_x:
                    min_x, max_x = max_x, min_x
                if min_y > max_y:
                    min_y, max_y = max_y, min_y

                raster_box_wkt = f"POLYGON(({min_x} {min_y}, {max_x} {min_y}, {max_x} {max_y}, {min_x} {max_y}, {min_x} {min_y}))"
                raster_geom = ogr.CreateGeometryFromWkt(raster_box_wkt)

                # AOI geometry transformed to raster CRS
                aoi_geom = ogr.CreateGeometryFromWkt(aoi_wkt)
                wgs84 = osr.SpatialReference()
                wgs84.ImportFromEPSG(4326)
                wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

                ct = osr.CoordinateTransformation(wgs84, srs)
                aoi_geom.Transform(ct)

                intersects = raster_geom.Intersects(aoi_geom)
                checks["aoi_intersection"] = intersects
                if not intersects:
                    errors.append("Raster bounding box does not intersect the target study AOI.")
            except Exception as ex:
                warnings.append(f"Could not evaluate AOI intersection: {ex}")
                checks["aoi_intersection"] = False

        # 5. Data content and NoData validation
        band = ds.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        details["nodata_value"] = nodata

        # Read small sample or full band if moderate
        if w * h <= 25000000:
            arr = band.ReadAsArray()
            if nodata is not None and not np.isnan(nodata):
                valid_pixels = np.sum(arr != nodata)
            elif np.isnan(nodata) if nodata is not None else False:
                valid_pixels = np.sum(~np.isnan(arr))
            else:
                valid_pixels = arr.size

            fraction_valid = float(valid_pixels / arr.size)
            details["valid_pixel_fraction"] = fraction_valid
            checks["non_empty_content"] = (fraction_valid > 0.0)
            if fraction_valid == 0.0:
                errors.append("Raster contains 100% NoData values.")
            elif fraction_valid < 0.10:
                warnings.append(f"Low valid pixel coverage: {fraction_valid * 100:.2f}% of pixels are valid.")
        else:
            checks["non_empty_content"] = True

    finally:
        ds = None

    if errors:
        status = ValidationStatus.REJECTED
    elif warnings:
        status = ValidationStatus.WARNING
    else:
        status = ValidationStatus.READY

    return ValidationResult(
        status=status,
        dataset_name=d_name,
        dataset_type=dataset_type,
        errors=errors,
        warnings=warnings,
        checks=checks,
        details=details,
    )


def validate_sentinel2_scaling_metadata(
    metadata: Dict[str, Any],
    required_bands: List[str] = ["B03", "B08", "B11", "B12"],
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Validates Sentinel-2 Level-2A radiometric scaling metadata:
    - Processing Baseline (e.g. '04.00', '05.10', '02.14')
    - Quantification Value (must be positive float, typically 10000.0)
    - Per-band BOA_ADD_OFFSET values for Baseline >= 04.00

    Returns
    -------
    Tuple[bool, List[str], Dict[str, Any]]
        (is_valid, errors, parsed_scaling_info)
    """
    errors: List[str] = []
    scaling_info: Dict[str, Any] = {}

    # 1. Processing Baseline
    raw_baseline = metadata.get("processing_baseline") or metadata.get("baseline")
    if not raw_baseline:
        errors.append("Missing required Sentinel-2 metadata: 'processing_baseline' (e.g. '04.00' or '05.10').")
        return False, errors, scaling_info

    baseline_str = str(raw_baseline).strip().upper()
    scaling_info["processing_baseline"] = baseline_str

    # Extract numeric baseline (e.g. '04.00' -> 4.00, 'N0510' -> 5.10)
    try:
        clean_num = baseline_str.lstrip("N").lstrip("V")
        if len(clean_num) == 4 and clean_num.isdigit():
            # e.g. 0510 -> 05.10
            baseline_num = float(f"{clean_num[:2]}.{clean_num[2:]}")
        else:
            baseline_num = float(clean_num)
        scaling_info["baseline_numeric"] = baseline_num
    except Exception:
        errors.append(f"Unparseable Sentinel-2 processing_baseline format: '{baseline_str}'.")
        return False, errors, scaling_info

    # 2. Quantification Value
    q_val = metadata.get("quantification_value")
    if q_val is None:
        errors.append("Missing required Sentinel-2 metadata: 'quantification_value'.")
        return False, errors, scaling_info

    try:
        q_float = float(q_val)
        if q_float <= 0:
            errors.append(f"Invalid non-positive quantification_value: {q_float}. Must be > 0.")
            return False, errors, scaling_info
        scaling_info["quantification_value"] = q_float
    except (ValueError, TypeError):
        errors.append(f"Invalid non-numeric quantification_value: '{q_val}'.")
        return False, errors, scaling_info

    # 3. BOA_ADD_OFFSET per-band handling
    per_band_offsets: Dict[str, float] = {}
    raw_offsets = metadata.get("boa_add_offsets") or metadata.get("boa_add_offset_values") or metadata.get("boa_add_offset")

    if baseline_num >= 4.00:
        # Baseline >= 04.00 requires explicit per-band offsets
        if raw_offsets is None:
            errors.append(
                f"Sentinel-2 Processing Baseline {baseline_str} (>= 04.00) requires explicit 'boa_add_offsets' "
                f"per-band metadata. Universal or hardcoded offsets are prohibited."
            )
            return False, errors, scaling_info

        if isinstance(raw_offsets, dict):
            for b in required_bands:
                if b not in raw_offsets and b.lower() not in raw_offsets:
                    errors.append(f"Missing BOA_ADD_OFFSET for band '{b}' in metadata offsets dictionary.")
                else:
                    val = raw_offsets.get(b, raw_offsets.get(b.lower()))
                    try:
                        per_band_offsets[b] = float(val)
                    except (ValueError, TypeError):
                        errors.append(f"Invalid non-numeric BOA_ADD_OFFSET for band '{b}': '{val}'.")
        elif isinstance(raw_offsets, (int, float)):
            # If scalar provided, assign to all required bands
            for b in required_bands:
                per_band_offsets[b] = float(raw_offsets)
        else:
            errors.append("Invalid format for 'boa_add_offsets': must be dictionary or numeric scalar.")
    else:
        # Baseline < 04.00: offsets are 0.0 unless specified
        if isinstance(raw_offsets, dict):
            for b in required_bands:
                val = raw_offsets.get(b, raw_offsets.get(b.lower(), 0.0))
                per_band_offsets[b] = float(val)
        elif isinstance(raw_offsets, (int, float)):
            for b in required_bands:
                per_band_offsets[b] = float(raw_offsets)
        else:
            for b in required_bands:
                per_band_offsets[b] = 0.0

    scaling_info["per_band_offsets"] = per_band_offsets
    is_valid = (len(errors) == 0)
    return is_valid, errors, scaling_info


def validate_sentinel2_optical(
    band_paths: Dict[str, Union[str, Path]],
    metadata: Optional[Dict[str, Any]] = None,
    aoi_wkt: Optional[str] = STUDY_AREA_AOI_WKT,
) -> ValidationResult:
    """
    Validates a candidate Sentinel-2 MSI Level-2A package.

    Required Bands:
    - B03: Green (10 m)
    - B08: NIR (10 m)
    - B11: SWIR-1 (20 m)
    - B12: SWIR-2 (20 m)
    - SCL: Scene Classification Layer (20 m)
    """
    required_bands = ["B03", "B08", "B11", "B12", "SCL"]
    errors: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, bool] = {}
    details: Dict[str, Any] = {}

    d_name = metadata.get("dataset_name") if metadata else "Sentinel-2_MSI_L2A"

    # Check band existence
    missing_bands = [b for b in required_bands if b not in band_paths or not Path(band_paths[b]).is_file()]
    for b in required_bands:
        checks[f"has_band_{b}"] = (b not in missing_bands)

    if missing_bands:
        errors.append(f"Missing required Sentinel-2 L2A bands: {missing_bands}")
        return ValidationResult(
            status=ValidationStatus.BLOCKED,
            dataset_name=d_name,
            dataset_type="Sentinel-2_L2A",
            errors=errors,
            checks=checks,
        )

    # Validate each individual band raster
    for b in required_bands:
        res = validate_raster_dataset(
            band_paths[b],
            aoi_wkt=aoi_wkt,
            dataset_name=f"S2_{b}",
            dataset_type="Sentinel-2_Band",
        )
        if res.status == ValidationStatus.REJECTED:
            errors.extend([f"Band {b}: {e}" for e in res.errors])
        elif res.status == ValidationStatus.WARNING:
            warnings.extend([f"Band {b}: {w}" for w in res.warnings])

    # Validate SCL band specifically with scientifically rigorous class interpretation
    # SCL Classes:
    # 0: No Data
    # 1: Saturated or defective pixels
    # 2: Dark Area Pixels (uncertain dark-area observation, NOT cloud shadow or water)
    # 3: Cloud Shadows (cloud-shadow uncertainty)
    # 4: Vegetation
    # 5: Not Vegetated
    # 6: Water
    # 7: Low Probability Cloud / Unclassified
    # 8: Medium Probability Cloud
    # 9: High Probability Cloud
    # 10: Thin Cirrus
    # 11: Snow or Ice
    scl_path = Path(band_paths["SCL"])
    try:
        ds_scl = gdal.Open(str(scl_path), gdal.GA_ReadOnly)
        scl_arr = ds_scl.GetRasterBand(1).ReadAsArray()
        ds_scl = None

        total_px = scl_arr.size
        nodata_px = int(np.sum(scl_arr == 0))
        defective_px = int(np.sum(scl_arr == 1))
        dark_area_px = int(np.sum(scl_arr == 2))
        cloud_shadow_px = int(np.sum(scl_arr == 3))
        vegetation_px = int(np.sum(scl_arr == 4))
        not_vegetated_px = int(np.sum(scl_arr == 5))
        water_px = int(np.sum(scl_arr == 6))
        cloud_cirrus_px = int(np.sum(np.isin(scl_arr, [7, 8, 9, 10])))
        snow_ice_px = int(np.sum(scl_arr == 11))

        # Cloud and shadow combined uncertainty
        cloud_shadow_uncertain_px = cloud_shadow_px + cloud_cirrus_px
        cloud_pct = float(cloud_shadow_uncertain_px / total_px * 100.0) if total_px > 0 else 0.0

        details["scl_class_breakdown"] = {
            "class_0_nodata": nodata_px,
            "class_1_saturated_defective": defective_px,
            "class_2_dark_area_pixels": dark_area_px,
            "class_3_cloud_shadows": cloud_shadow_px,
            "class_4_vegetation": vegetation_px,
            "class_5_not_vegetated": not_vegetated_px,
            "class_6_water": water_px,
            "classes_7_10_cloud_cirrus": cloud_cirrus_px,
            "class_11_snow_ice": snow_ice_px,
        }
        details["scl_cloud_shadow_percent"] = round(cloud_pct, 2)
        details["scl_dark_area_percent"] = round(float(dark_area_px / total_px * 100.0) if total_px > 0 else 0.0, 2)

        if cloud_pct > 80.0:
            warnings.append(f"Excessive cloud/shadow cover ({cloud_pct:.1f}%). Most pixels will be excluded.")
        elif cloud_pct > 30.0:
            warnings.append(f"Moderate cloud/shadow cover ({cloud_pct:.1f}%).")
        checks["scl_evaluated"] = True
    except Exception as e:
        warnings.append(f"Could not inspect SCL cloud layer: {e}")
        checks["scl_evaluated"] = False

    # Check scaling metadata if provided
    if metadata and ("processing_baseline" in metadata or "quantification_value" in metadata or "baseline" in metadata):
        is_sc_valid, sc_errs, sc_info = validate_sentinel2_scaling_metadata(metadata)
        details["scaling_metadata"] = sc_info
        if not is_sc_valid:
            errors.extend([f"Radiometric scaling metadata error: {e}" for e in sc_errs])
            checks["scaling_metadata_valid"] = False
        else:
            checks["scaling_metadata_valid"] = True

    # Check provenance metadata if provided
    if metadata:
        meta_res = validate_provenance_metadata(metadata)
        if meta_res.status == ValidationStatus.REJECTED:
            errors.extend(meta_res.errors)
        elif meta_res.status == ValidationStatus.WARNING:
            warnings.extend(meta_res.warnings)

    status = ValidationStatus.REJECTED if errors else (ValidationStatus.WARNING if warnings else ValidationStatus.READY)
    return ValidationResult(
        status=status,
        dataset_name=d_name,
        dataset_type="Sentinel-2_L2A",
        errors=errors,
        warnings=warnings,
        checks=checks,
        details=details,
    )


def validate_landsat_optical(
    band_paths: Dict[str, Union[str, Path]],
    metadata: Optional[Dict[str, Any]] = None,
    aoi_wkt: Optional[str] = STUDY_AREA_AOI_WKT,
) -> ValidationResult:
    """
    Validates a candidate Landsat 8/9 Level-2 Surface Reflectance package.

    Required Bands:
    - SR_B3: Green (30 m native)
    - SR_B5: NIR (30 m native)
    - SR_B6: SWIR-1 (30 m native)
    - QA_PIXEL: Pixel Quality Assessment (30 m native)
    Optional Band:
    - QA_RADSAT: Radiometric Saturation and Occlusion (30 m native)
    """
    required_bands = ["SR_B3", "SR_B5", "SR_B6", "QA_PIXEL"]
    errors: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, bool] = {}
    details: Dict[str, Any] = {
        "native_spatial_resolution_m": 30.0,
        "spatial_support_notice": (
            "Landsat 8/9 Level-2 reflective bands possess a native spatial resolution of 30 m. "
            "Resampling to the 20 m SAR grid via bilinear interpolation enables pixel-aligned indexing "
            "but introduces point spread function smoothing and spatial covariance. Resampling does NOT "
            "generate independent 20 m optical ground information. Validation evaluations should respect "
            "native 30 m spatial support (e.g. through block aggregation)."
        ),
    }

    d_name = metadata.get("dataset_name") if metadata else "Landsat_L2_SR"

    missing_bands = [b for b in required_bands if b not in band_paths or not Path(band_paths[b]).is_file()]
    for b in required_bands:
        checks[f"has_band_{b}"] = (b not in missing_bands)

    if missing_bands:
        errors.append(f"Missing required Landsat L2 bands: {missing_bands}")
        return ValidationResult(
            status=ValidationStatus.BLOCKED,
            dataset_name=d_name,
            dataset_type="Landsat_L2_SR",
            errors=errors,
            checks=checks,
            details=details,
        )

    # Validate each band raster
    for b in required_bands:
        res = validate_raster_dataset(
            band_paths[b],
            aoi_wkt=aoi_wkt,
            dataset_name=f"Landsat_{b}",
            dataset_type="Landsat_Band",
        )
        if res.status == ValidationStatus.REJECTED:
            errors.extend([f"Band {b}: {e}" for e in res.errors])
        elif res.status == ValidationStatus.WARNING:
            warnings.extend([f"Band {b}: {w}" for w in res.warnings])

    # Validate QA_PIXEL
    qa_path = Path(band_paths["QA_PIXEL"])
    try:
        ds_qa = gdal.Open(str(qa_path), gdal.GA_ReadOnly)
        qa_arr = ds_qa.GetRasterBand(1).ReadAsArray()
        ds_qa = None

        total_px = qa_arr.size
        # QA_PIXEL bitmask: Bit 1 = Dilated cloud, Bit 2 = Cirrus, Bit 3 = Cloud, Bit 4 = Cloud shadow
        cloud_shadow_mask = ((qa_arr & (1 << 1)) > 0) | ((qa_arr & (1 << 2)) > 0) | \
                            ((qa_arr & (1 << 3)) > 0) | ((qa_arr & (1 << 4)) > 0)
        cloud_px = int(np.sum(cloud_shadow_mask))
        cloud_pct = float(cloud_px / total_px * 100.0) if total_px > 0 else 0.0
        details["qa_cloud_shadow_percent"] = round(cloud_pct, 2)

        if cloud_pct > 80.0:
            warnings.append(f"Excessive cloud/shadow cover ({cloud_pct:.1f}%).")
        elif cloud_pct > 30.0:
            warnings.append(f"Moderate cloud/shadow cover ({cloud_pct:.1f}%).")
        checks["qa_pixel_evaluated"] = True
    except Exception as e:
        warnings.append(f"Could not inspect QA_PIXEL: {e}")
        checks["qa_pixel_evaluated"] = False

    # Optional QA_RADSAT saturation validation
    if "QA_RADSAT" in band_paths and Path(band_paths["QA_RADSAT"]).is_file():
        try:
            ds_radsat = gdal.Open(str(band_paths["QA_RADSAT"]), gdal.GA_ReadOnly)
            radsat_arr = ds_radsat.GetRasterBand(1).ReadAsArray()
            ds_radsat = None

            # QA_RADSAT: Bit 2 = Band 3 saturation, Bit 4 = Band 5 saturation, Bit 5 = Band 6 saturation
            sat_b3 = (radsat_arr & (1 << 2)) > 0
            sat_b5 = (radsat_arr & (1 << 4)) > 0
            sat_b6 = (radsat_arr & (1 << 5)) > 0
            any_sat = sat_b3 | sat_b5 | sat_b6
            sat_px = int(np.sum(any_sat))
            sat_pct = float(sat_px / total_px * 100.0) if total_px > 0 else 0.0

            details["qa_radsat_evaluated"] = True
            details["qa_radsat_saturation_percent"] = round(sat_pct, 2)
            checks["qa_radsat_evaluated"] = True
            if sat_pct > 5.0:
                warnings.append(f"Radiometric saturation detected in {sat_pct:.2f}% of pixels in reflective bands.")
        except Exception as e:
            warnings.append(f"Could not inspect QA_RADSAT: {e}")
            checks["qa_radsat_evaluated"] = False

    # Check metadata if provided
    if metadata:
        meta_res = validate_provenance_metadata(metadata)
        if meta_res.status == ValidationStatus.REJECTED:
            errors.extend(meta_res.errors)
        elif meta_res.status == ValidationStatus.WARNING:
            warnings.extend(meta_res.warnings)

    status = ValidationStatus.REJECTED if errors else (ValidationStatus.WARNING if warnings else ValidationStatus.READY)
    return ValidationResult(
        status=status,
        dataset_name=d_name,
        dataset_type="Landsat_L2_SR",
        errors=errors,
        warnings=warnings,
        checks=checks,
        details=details,
    )


def validate_hydrological_csv(
    csv_path: Union[str, Path],
    require_official_citation: bool = True,
    reject_unverified_danger_level: bool = True,
    reject_unverified_coordinates: bool = True,
    plausibility_range: Optional[Tuple[float, float]] = None,
) -> ValidationResult:
    """
    Validates a BWDB / FFWC river gauge CSV file.

    Expected schema:
    - station_id: str
    - station_name: str
    - observation_datetime: ISO datetime / parseable timestamp
    - water_level: float
    - unit: str (must be 'm' or 'meters')
    - vertical_datum: str (e.g. 'PWD', 'MSL', 'EGM2008')
    - provider: str (e.g. 'BWDB', 'FFWC')
    - source_identifier: str
    - source_citation: str
    - quality_flag: str
    """
    p = Path(csv_path)
    d_name = p.name
    errors: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, bool] = {}
    details: Dict[str, Any] = {}

    if not p.is_file():
        return ValidationResult(
            status=ValidationStatus.BLOCKED,
            dataset_name=d_name,
            dataset_type="Hydrological_CSV",
            errors=[f"Gauge CSV file not found on disk: {p}"],
            checks={"file_exists": False},
        )

    checks["file_exists"] = True

    try:
        df = pd.read_csv(p)
    except Exception as e:
        return ValidationResult(
            status=ValidationStatus.REJECTED,
            dataset_name=d_name,
            dataset_type="Hydrological_CSV",
            errors=[f"Failed to parse CSV file: {e}"],
            checks={"parseable_csv": False},
        )

    checks["parseable_csv"] = True
    details["row_count"] = len(df)
    details["columns"] = list(df.columns)

    # 1. Required columns
    expected_cols = [
        "station_id", "station_name", "observation_datetime", "water_level",
        "unit", "vertical_datum", "provider", "source_identifier",
        "source_citation", "quality_flag"
    ]
    missing_cols = [c for c in expected_cols if c not in df.columns]
    checks["has_required_columns"] = (len(missing_cols) == 0)
    if missing_cols:
        errors.append(f"CSV missing required columns: {missing_cols}")
        return ValidationResult(
            status=ValidationStatus.REJECTED,
            dataset_name=d_name,
            dataset_type="Hydrological_CSV",
            errors=errors,
            checks=checks,
            details=details,
        )

    if len(df) == 0:
        errors.append("CSV contains zero records.")
        return ValidationResult(
            status=ValidationStatus.REJECTED,
            dataset_name=d_name,
            dataset_type="Hydrological_CSV",
            errors=errors,
            checks=checks,
            details=details,
        )

    # 2. Datetime parsing
    try:
        df["parsed_dt"] = pd.to_datetime(df["observation_datetime"], errors="coerce")
        bad_dates = int(df["parsed_dt"].isna().sum())
        checks["valid_datetimes"] = (bad_dates == 0)
        if bad_dates > 0:
            errors.append(f"Contains {bad_dates} unparseable observation_datetime values.")
    except Exception as ex:
        checks["valid_datetimes"] = False
        errors.append(f"Error parsing datetimes: {ex}")

    # 3. Numerical water levels & Configurable Plausibility
    try:
        df["numeric_wl"] = pd.to_numeric(df["water_level"], errors="coerce")
        bad_wl = int(df["numeric_wl"].isna().sum())
        checks["valid_water_levels"] = (bad_wl == 0)
        if bad_wl > 0:
            errors.append(f"Contains {bad_wl} invalid / non-numerical water_level entries.")
        else:
            min_wl = float(df["numeric_wl"].min())
            max_wl = float(df["numeric_wl"].max())
            details["water_level_range"] = (min_wl, max_wl)
            if plausibility_range is not None:
                p_min, p_max = plausibility_range
                if min_wl < p_min or max_wl > p_max:
                    warnings.append(
                        f"Plausibility notice: Water level range [{min_wl}, {max_wl}] extends outside "
                        f"configurable plausibility range [{p_min}, {p_max}]. Raw readings preserved."
                    )
    except Exception as ex:
        checks["valid_water_levels"] = False
        errors.append(f"Error checking numerical water levels: {ex}")

    # 4. Duplicate observation detection (same station_id and observation_datetime)
    dup_mask = df.duplicated(subset=["station_id", "observation_datetime"], keep=False)
    num_dups = int(dup_mask.sum())
    checks["no_duplicate_observations"] = (num_dups == 0)
    if num_dups > 0:
        errors.append(f"Detected {num_dups} duplicate records with identical station_id and observation_datetime.")

    # 5. Units consistency
    units = df["unit"].astype(str).str.strip().str.lower().unique()
    valid_units = {"m", "meter", "meters"}
    invalid_units = [u for u in units if u not in valid_units]
    checks["valid_units"] = (len(invalid_units) == 0)
    if invalid_units:
        errors.append(f"Inconsistent or unsupported units: {invalid_units}. Only 'm' or 'meters' accepted.")

    # 6. Vertical datum check & Datum Incompatibility Protection
    datums = [d for d in df["vertical_datum"].astype(str).str.strip().unique() if d]
    details["vertical_datums"] = datums
    missing_datum = any(d in ["", "nan", "none", "unknown"] for d in map(str.lower, datums)) or (len(datums) == 0)
    checks["vertical_datum_specified"] = not missing_datum
    if missing_datum:
        errors.append("Missing vertical_datum in one or more records (e.g., must specify 'PWD' or 'EGM2008').")

    # Protection against mixed or conflated datums
    norm_datums = set(d.upper() for d in datums if d.lower() not in ["", "nan", "none", "unknown"])
    if len(norm_datums) > 1:
        errors.append(
            f"DATUM_INCOMPATIBILITY_PROTECTION: Multiple conflicting vertical datums {norm_datums} detected in single "
            f"time-series. PWD and EGM2008 are distinct vertical datums and must NEVER be conflated without "
            f"an authoritative surveyed geodetic transformation."
        )

    # 7. Source Citation check
    if require_official_citation:
        citations = df["source_citation"].astype(str).str.strip().str.upper().unique()
        unverified_cites = [c for c in citations if c in ["UNVERIFIED", "ASSUMPTION", "NONE", "UNKNOWN", ""]]
        checks["official_citations_present"] = (len(unverified_cites) == 0)
        if unverified_cites:
            errors.append(
                f"Contains unverified source citations: {unverified_cites}. Official BWDB/FFWC citation required."
            )

    # 8. Danger level checks if column is present
    if "danger_level" in df.columns:
        dl_vals = df["danger_level"].dropna().unique()
        if len(dl_vals) > 0 and reject_unverified_danger_level:
            if "danger_level_citation" not in df.columns:
                errors.append("CSV contains danger_level column but missing 'danger_level_citation' column.")
                checks["danger_level_verified"] = False
            else:
                dl_cites = df["danger_level_citation"].astype(str).str.strip().str.upper().unique()
                bad_dl_cites = [c for c in dl_cites if c in ["UNVERIFIED", "ASSUMPTION", "NONE", "UNKNOWN", ""]]
                checks["danger_level_verified"] = (len(bad_dl_cites) == 0)
                if bad_dl_cites:
                    errors.append(
                        f"Unverified danger level citation: {bad_dl_cites}. Official published citation required."
                    )

    # 9. Station coordinate checks if present
    coord_cols = [c for c in ["latitude", "longitude", "lat", "lon"] if c in df.columns]
    if coord_cols and reject_unverified_coordinates:
        if "coordinates_citation" not in df.columns:
            errors.append("CSV contains station coordinates but missing 'coordinates_citation' column.")
            checks["coordinates_verified"] = False
        else:
            coord_cites = df["coordinates_citation"].astype(str).str.strip().str.upper().unique()
            bad_coord = [c for c in coord_cites if c in ["UNVERIFIED", "ASSUMPTION", "NONE", "UNKNOWN", ""]]
            checks["coordinates_verified"] = (len(bad_coord) == 0)
            if bad_coord:
                errors.append(
                    f"Unverified station coordinates citation: {bad_coord}. Official survey citation required."
                )

    status = ValidationStatus.REJECTED if errors else (ValidationStatus.WARNING if warnings else ValidationStatus.READY)
    return ValidationResult(
        status=status,
        dataset_name=d_name,
        dataset_type="Hydrological_CSV",
        errors=errors,
        warnings=warnings,
        checks=checks,
        details=details,
    )


def validate_dem_dataset(
    dem_path: Union[str, Path],
    aoi_wkt: Optional[str] = STUDY_AREA_AOI_WKT,
    expected_tile: str = "N24_E089",
) -> ValidationResult:
    """
    Validates a Copernicus GLO-30 Digital Surface Model (DSM) GeoTIFF.

    Scientific Characteristics:
    - Model Type: Digital Surface Model (DSM), NOT a bare-earth DEM.
    - Native Resolution: 1.0 arc-second (~30 m at equator; ~27.3 m in longitude at 24.6°N).
    - Horizontal CRS: WGS 84 (EPSG:4326).
    - Vertical Datum: Heights above the EGM2008 geoid in meters.
    - Terrain Limitations: Elevation measurements include canopy height (tree crown top)
      and building structures. In the Jamuna floodplain, riparian and char vegetation
      canopy (3-15 m) introduces elevation overestimation relative to bare ground.
      Deriving Height Above Nearest Drainage (HAND) or flow networks requires hydrologic
      conditioning (sink filling, stream carving) and a calibrated drainage network.
    """
    res = validate_raster_dataset(
        dem_path,
        aoi_wkt=aoi_wkt,
        dataset_name=f"DSM_{Path(dem_path).stem}",
        dataset_type="Copernicus_GLO-30_DSM",
    )

    p = Path(dem_path)
    if expected_tile.lower() not in p.name.lower():
        res.warnings.append(f"Tile name does not explicitly include expected study-area tile identifier '{expected_tile}'.")

    res.details["terrain_model_type"] = "Digital Surface Model (DSM)"
    res.details["vertical_datum_standard"] = "EGM2008"
    res.details["elevation_units"] = "meters"
    res.details["canopy_structure_bias_notice"] = (
        "Copernicus GLO-30 is a DSM derived from TanDEM-X radar interferometry. Measured surface elevations "
        "include tree canopies (3-15 m), riparian vegetation, and human settlements. It must NOT be interpreted "
        "as bare-earth ground elevation."
    )
    res.details["hydrological_limitations"] = (
        "Raw DSM surface features block flow paths and create artificial dams across river channels. "
        "Deriving Height Above Nearest Drainage (HAND) or flow networks requires hydrologic conditioning "
        "(sink-filling, stream-carving) and calibration against a verified drainage network."
    )

    return res
