"""
Earth Pulse — Phase 4C.1: Sentinel-2 Real Data Ingestion Pipeline
NASA Space Apps Challenge 2026 — Dancing with the SARs

This module implements the end-to-end ingestion and processing pipeline for real Sentinel-2 Level-2A datasets:
1. Input and Archive Validation: Checksum computation (SHA-256), zip inspection, XML metadata extraction.
2. Selective SAFE Extraction: Extracts only required bands (B03 10m, B08 10m, B11 20m, B12 20m, SCL 20m, XMLs).
3. Area-Weighted Spatial Alignment: Non-destructive alignment to canonical SAR reference grid (EPSG:32645, 20m, 1405x1393).
4. Radiometric Calibration: Applies Baseline 05.10 BOA_ADD_OFFSET (-1000) and BOA_QUANTIFICATION_VALUE (10000).
5. Spectral Water Indices: Continuous MNDWI and AWEI_nsh.
6. Rigorous SCL Quality Masking: Cloud, cloud shadow, and dark-area pixel isolation (Class 2 preserved as 252).
7. Kazipur Study AOI Quality Assessment: Coverage, clear water/land, cloud/shadow/dark fraction, and readiness status.
8. Provenance Registry Integration: Updates reference_data_registry.json with authenticated provenance.
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from osgeo import gdal, ogr, osr

# Internal imports
try:
    from scripts.ingest_reference_data import (
        REF_LABEL_EXCLUDED_SNOW_ICE,
        REF_LABEL_NODATA,
        REF_LABEL_NON_WATER,
        REF_LABEL_UNCERTAIN_CLOUD,
        REF_LABEL_UNCERTAIN_DARK_AREA,
        REF_LABEL_UNCERTAIN_INVALID,
        REF_LABEL_UNCERTAIN_SHADOW,
        REF_LABEL_WATER,
        SAR_GRID_GEO_TRANSFORM,
        SAR_GRID_HEIGHT,
        SAR_GRID_WIDTH,
        ReferenceDataRegistry,
        calculate_awei_nsh,
        calculate_mndwi,
        mask_sentinel2_scl,
        resample_raster_to_grid,
        scale_sentinel2_reflectance,
    )
    from scripts.validate_reference_inputs import (
        SAR_TARGET_EPSG,
        SAR_TARGET_RESOLUTION,
        STUDY_AREA_AOI_WKT,
        ValidationStatus,
        compute_sha256,
        validate_provenance_metadata,
    )
except ImportError:
    from ingest_reference_data import (
        REF_LABEL_EXCLUDED_SNOW_ICE,
        REF_LABEL_NODATA,
        REF_LABEL_NON_WATER,
        REF_LABEL_UNCERTAIN_CLOUD,
        REF_LABEL_UNCERTAIN_DARK_AREA,
        REF_LABEL_UNCERTAIN_INVALID,
        REF_LABEL_UNCERTAIN_SHADOW,
        REF_LABEL_WATER,
        SAR_GRID_GEO_TRANSFORM,
        SAR_GRID_HEIGHT,
        SAR_GRID_WIDTH,
        ReferenceDataRegistry,
        calculate_awei_nsh,
        calculate_mndwi,
        mask_sentinel2_scl,
        resample_raster_to_grid,
        scale_sentinel2_reflectance,
    )
    from validate_reference_inputs import (
        SAR_TARGET_EPSG,
        SAR_TARGET_RESOLUTION,
        STUDY_AREA_AOI_WKT,
        ValidationStatus,
        compute_sha256,
        validate_provenance_metadata,
    )

# Enable GDAL exceptions
gdal.UseExceptions()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("EarthPulse.Phase4C1")

# Target AOI Cell count constant
AOI_TARGET_CELLS = 1010039
FULL_SCENE_CELLS = 1405 * 1393  # 1,957,165


def find_project_root() -> Path:
    """Locate EarthPulse-SAR project root directory."""
    candidates = [
        Path.cwd().resolve(),
        Path(__file__).resolve().parent.parent,
        Path("/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR"),
    ]
    for c in candidates:
        if (c / "data" / "raw" / "sentinel1").is_dir() and (c / "scripts").is_dir():
            return c
        if (c / "EarthPulse-SAR").is_dir():
            return c / "EarthPulse-SAR"
    raise FileNotFoundError("Could not identify EarthPulse-SAR project root.")


def parse_sentinel2_archive_metadata(zip_path: Path) -> Dict[str, Any]:
    """
    Parses Sentinel-2 L2A metadata directly from zip without full extraction.
    Reads MTD_MSIL2A.xml and MTD_TL.xml.
    """
    logger.info(f"Inspecting metadata from archive: {zip_path.name}")
    meta: Dict[str, Any] = {
        "archive_filename": zip_path.name,
        "archive_size_bytes": zip_path.stat().st_size,
    }

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Find MTD_MSIL2A.xml and MTD_TL.xml
        msi_xml_name = [f for f in zf.namelist() if f.endswith("MTD_MSIL2A.xml")][0]
        tl_xml_name = [f for f in zf.namelist() if f.endswith("MTD_TL.xml")][0]

        root_msi = ET.fromstring(zf.read(msi_xml_name))
        root_tl = ET.fromstring(zf.read(tl_xml_name))

        # Spacecraft & Product
        for elem in root_msi.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "SPACECRAFT_NAME":
                meta["spacecraft_name"] = elem.text
            elif tag == "PRODUCT_TYPE":
                meta["product_type"] = elem.text
            elif tag == "PROCESSING_BASELINE":
                meta["processing_baseline"] = elem.text
            elif tag == "PRODUCT_START_TIME":
                meta["datatake_start_time"] = elem.text
            elif tag == "GENERATION_TIME":
                meta["generation_time"] = elem.text
            elif tag == "Cloud_Coverage_Assessment":
                meta["scene_cloud_percentage"] = float(elem.text)
            elif tag == "BOA_QUANTIFICATION_VALUE":
                meta["quantification_value"] = float(elem.text)

        # Offsets
        offsets = {}
        for elem in root_msi.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "BOA_ADD_OFFSET":
                b_id = elem.attrib.get("band_id")
                if b_id is not None and elem.text is not None:
                    offsets[f"B{int(b_id):02d}"] = float(elem.text)
        meta["boa_add_offsets"] = offsets

        # Granule tile ID & Granule cloud percentage
        for elem in root_tl.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "TILE_ID":
                meta["tile_id"] = elem.text
            elif tag == "CLOUDY_PIXEL_PERCENTAGE":
                meta["granule_cloud_percentage"] = float(elem.text)
            elif tag == "Geoposition" and elem.attrib.get("resolution") == "10":
                meta["tile_ulx"] = float(elem.find("ULX").text)
                meta["tile_uly"] = float(elem.find("ULY").text)
                meta["tile_xdim"] = float(elem.find("XDIM").text)
                meta["tile_ydim"] = float(elem.find("YDIM").text)

    return meta


def extract_selective_safe_files(
    zip_path: Path,
    output_dir: Path,
) -> Dict[str, Path]:
    """
    Selectively extracts only required bands and metadata files:
    - B03 (10m)
    - B08 (10m)
    - B11 (20m)
    - B12 (20m)
    - SCL (20m)
    - MTD_TL.xml
    - MTD_MSIL2A.xml
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: Dict[str, Path] = {}

    target_suffixes = {
        "B03": "_B03_10m.jp2",
        "B08": "_B08_10m.jp2",
        "B11": "_B11_20m.jp2",
        "B12": "_B12_20m.jp2",
        "SCL": "_SCL_20m.jp2",
        "MTD_TL": "MTD_TL.xml",
        "MTD_MSIL2A": "MTD_MSIL2A.xml",
    }

    logger.info(f"Extracting selective SAFE bands from {zip_path.name} to {output_dir}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            fn = member.filename
            for key, suffix in target_suffixes.items():
                if fn.endswith(suffix):
                    target_dest = output_dir / Path(fn).name
                    if not target_dest.is_file() or target_dest.stat().st_size != member.file_size:
                        with open(target_dest, "wb") as f_out, zf.open(member) as f_in:
                            f_out.write(f_in.read())
                        logger.info(f"  Extracted {target_dest.name} ({target_dest.stat().st_size} bytes)")
                    extracted[key] = target_dest

    missing = set(target_suffixes.keys()) - set(extracted.keys())
    if missing:
        raise FileNotFoundError(f"Archive {zip_path.name} missing required components: {missing}")

    return extracted


def create_study_aoi_raster_mask(
    sar_reference_path: Path,
    aoi_wkt: str = STUDY_AREA_AOI_WKT,
) -> np.ndarray:
    """
    Rasterizes canonical Kazipur study AOI polygon onto the SAR reference grid.
    Returns boolean numpy array of shape (1393, 1405).
    """
    sar_ds = gdal.Open(str(sar_reference_path), gdal.GA_ReadOnly)
    w, h = sar_ds.RasterXSize, sar_ds.RasterYSize
    gt = sar_ds.GetGeoTransform()
    proj = sar_ds.GetProjection()
    sar_ds = None

    srs_wgs84 = osr.SpatialReference()
    srs_wgs84.ImportFromEPSG(4326)
    srs_wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    srs_utm = osr.SpatialReference()
    srs_utm.ImportFromWkt(proj)

    geom = ogr.CreateGeometryFromWkt(aoi_wkt)
    geom.AssignSpatialReference(srs_wgs84)
    geom.TransformTo(srs_utm)

    mem_drv = gdal.GetDriverByName("MEM")
    mem_ds = mem_drv.Create("", w, h, 1, gdal.GDT_Byte)
    mem_ds.SetGeoTransform(gt)
    mem_ds.SetProjection(proj)

    ogr_ds = ogr.GetDriverByName("MEM").CreateDataSource("mem_layer")
    ogr_lyr = ogr_ds.CreateLayer("aoi_poly", srs_utm, ogr.wkbPolygon)
    feat = ogr.Feature(ogr_lyr.GetLayerDefn())
    feat.SetGeometry(geom)
    ogr_lyr.CreateFeature(feat)

    gdal.RasterizeLayer(mem_ds, [1], ogr_lyr, burn_values=[1])
    aoi_mask = mem_ds.GetRasterBand(1).ReadAsArray() == 1
    mem_ds = None
    ogr_ds = None

    if np.sum(aoi_mask) != AOI_TARGET_CELLS:
        logger.warning(
            f"AOI cell count ({np.sum(aoi_mask)}) differs from target ({AOI_TARGET_CELLS})."
        )
    return aoi_mask


def write_geotiff(
    arr: np.ndarray,
    out_path: Path,
    dtype: int,
    geo_transform: Tuple[float, float, float, float, float, float] = SAR_GRID_GEO_TRANSFORM,
    projection_wkt: Optional[str] = None,
    nodata_value: Optional[float] = None,
) -> Path:
    """Exports 2D numpy array to standard Deflate-compressed GeoTIFF on canonical SAR grid."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if projection_wkt is None:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(SAR_TARGET_EPSG)
        projection_wkt = srs.ExportToWkt()

    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(
        str(out_path),
        SAR_GRID_WIDTH,
        SAR_GRID_HEIGHT,
        1,
        dtype,
        ["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES"],
    )
    ds.SetGeoTransform(geo_transform)
    ds.SetProjection(projection_wkt)
    band = ds.GetRasterBand(1)
    if nodata_value is not None:
        band.SetNoDataValue(nodata_value)
    band.WriteArray(arr)
    ds.FlushCache()
    ds = None
    return out_path


def process_sentinel2_dataset(
    dataset_name: str,
    zip_path: Path,
    extracted_dir: Path,
    processed_dir: Path,
    sar_ref_path: Path,
    aoi_mask: np.ndarray,
    temporal_delta_days: int,
    sar_pair_date: str,
) -> Dict[str, Any]:
    """
    Executes complete ingestion, calibration, masking and quality assessment
    for a single Sentinel-2 acquisition.
    """
    logger.info(f"============================================================")
    logger.info(f"PROCESSING SENTINEL-2 DATASET: {dataset_name}")
    logger.info(f"Source ZIP: {zip_path}")
    logger.info(f"============================================================")

    # 1. Archive Checksum & Metadata
    sha256_hash = compute_sha256(zip_path)
    metadata = parse_sentinel2_archive_metadata(zip_path)
    metadata["sha256"] = sha256_hash

    # 2. Selective Extraction
    extracted_bands = extract_selective_safe_files(zip_path, extracted_dir)

    # Scaling constants
    quant_val = metadata.get("quantification_value", 10000.0)
    offsets = metadata.get("boa_add_offsets", {})
    offset_b03 = offsets.get("B02", -1000.0)  # Sentinel band_id 2 is B03 (Green)
    offset_b08 = offsets.get("B07", -1000.0)  # Sentinel band_id 7 is B08 (NIR)
    offset_b11 = offsets.get("B11", -1000.0)  # Sentinel band_id 11 is B11 (SWIR-1)
    offset_b12 = offsets.get("B12", -1000.0)  # Sentinel band_id 12 is B12 (SWIR-2)

    prefix = "s2_june07" if ("0607" in zip_path.name or "06-07" in dataset_name or "june" in dataset_name.lower()) else "s2_july17"

    # 3. Spatial Alignment to SAR Grid
    aligned_rasters: Dict[str, Path] = {}

    # B03 (10m -> 20m area-weighted average)
    p_b03 = processed_dir / f"{prefix}_aligned_b03_20m.tif"
    resample_raster_to_grid(
        extracted_bands["B03"],
        p_b03,
        resample_alg=gdal.GRA_Average,
        output_dtype=gdal.GDT_Float32,
    )
    aligned_rasters["B03"] = p_b03

    # B08 (10m -> 20m area-weighted average)
    p_b08 = processed_dir / f"{prefix}_aligned_b08_20m.tif"
    resample_raster_to_grid(
        extracted_bands["B08"],
        p_b08,
        resample_alg=gdal.GRA_Average,
        output_dtype=gdal.GDT_Float32,
    )
    aligned_rasters["B08"] = p_b08

    # B11 (20m -> 20m area-weighted average)
    p_b11 = processed_dir / f"{prefix}_aligned_b11_20m.tif"
    resample_raster_to_grid(
        extracted_bands["B11"],
        p_b11,
        resample_alg=gdal.GRA_Average,
        output_dtype=gdal.GDT_Float32,
    )
    aligned_rasters["B11"] = p_b11

    # B12 (20m -> 20m area-weighted average)
    p_b12 = processed_dir / f"{prefix}_aligned_b12_20m.tif"
    resample_raster_to_grid(
        extracted_bands["B12"],
        p_b12,
        resample_alg=gdal.GRA_Average,
        output_dtype=gdal.GDT_Float32,
    )
    aligned_rasters["B12"] = p_b12

    # SCL (20m -> 20m Nearest Neighbour)
    p_scl = processed_dir / f"{prefix}_aligned_scl.tif"
    resample_raster_to_grid(
        extracted_bands["SCL"],
        p_scl,
        resample_alg=gdal.GRA_NearestNeighbour,
        output_dtype=gdal.GDT_Byte,
        nodata_val=0,
    )
    aligned_rasters["SCL"] = p_scl

    # 4. Radiometric Calibration
    ds_b03 = gdal.Open(str(p_b03))
    refl_b03 = scale_sentinel2_reflectance(ds_b03.GetRasterBand(1).ReadAsArray(), offset_b03, quant_val)
    ds_b03 = None

    ds_b08 = gdal.Open(str(p_b08))
    refl_b08 = scale_sentinel2_reflectance(ds_b08.GetRasterBand(1).ReadAsArray(), offset_b08, quant_val)
    ds_b08 = None

    ds_b11 = gdal.Open(str(p_b11))
    refl_b11 = scale_sentinel2_reflectance(ds_b11.GetRasterBand(1).ReadAsArray(), offset_b11, quant_val)
    ds_b11 = None

    ds_b12 = gdal.Open(str(p_b12))
    refl_b12 = scale_sentinel2_reflectance(ds_b12.GetRasterBand(1).ReadAsArray(), offset_b12, quant_val)
    ds_b12 = None

    ds_scl = gdal.Open(str(p_scl))
    scl_arr = ds_scl.GetRasterBand(1).ReadAsArray()
    ds_scl = None

    # Overwrite the aligned band GeoTIFFs with the calibrated BOA reflectance values
    write_geotiff(refl_b03, p_b03, gdal.GDT_Float32, nodata_value=-9999.0)
    write_geotiff(refl_b08, p_b08, gdal.GDT_Float32, nodata_value=-9999.0)
    write_geotiff(refl_b11, p_b11, gdal.GDT_Float32, nodata_value=-9999.0)
    write_geotiff(refl_b12, p_b12, gdal.GDT_Float32, nodata_value=-9999.0)

    # 5. Spectral Indices
    mndwi = calculate_mndwi(refl_b03, refl_b11)
    awei_nsh = calculate_awei_nsh(refl_b03, refl_b08, refl_b11, refl_b12)

    p_mndwi = processed_dir / f"{prefix}_aligned_mndwi.tif"
    p_awei = processed_dir / f"{prefix}_aligned_awei_nsh.tif"
    write_geotiff(mndwi.astype(np.float32), p_mndwi, gdal.GDT_Float32, nodata_value=-9999.0)
    write_geotiff(awei_nsh.astype(np.float32), p_awei, gdal.GDT_Float32, nodata_value=-9999.0)
    aligned_rasters["MNDWI"] = p_mndwi
    aligned_rasters["AWEI_nsh"] = p_awei

    # 6. SCL Quality & Water Masks
    scl_result = mask_sentinel2_scl(scl_arr)

    # Valid clear mask: Classes 4 (Vegetation), 5 (Not Vegetated), 6 (Water)
    p_valid = processed_dir / f"{prefix}_aligned_valid_mask.tif"
    write_geotiff(scl_result.clear_mask.astype(np.uint8), p_valid, gdal.GDT_Byte, nodata_value=0)
    aligned_rasters["VALID_MASK"] = p_valid

    # Cloud mask: Legacy combined Classes 7, 8, 9, 10
    p_cloud = processed_dir / f"{prefix}_aligned_cloud_mask.tif"
    write_geotiff(scl_result.cloud_cirrus_mask.astype(np.uint8), p_cloud, gdal.GDT_Byte, nodata_value=0)
    aligned_rasters["CLOUD_MASK"] = p_cloud

    # Pure Cloud mask (Diagnostic: Classes 8, 9, 10 - Medium cloud, High cloud, Thin cirrus)
    p_pure_cloud = processed_dir / f"{prefix}_aligned_cloud_pure_mask.tif"
    write_geotiff(scl_result.pure_cloud_mask.astype(np.uint8), p_pure_cloud, gdal.GDT_Byte, nodata_value=0)
    aligned_rasters["CLOUD_PURE_MASK"] = p_pure_cloud

    # Unclassified mask (Diagnostic: Class 7 - Unclassified / Low prob cloud)
    p_unclass = processed_dir / f"{prefix}_aligned_unclassified_mask.tif"
    write_geotiff(scl_result.unclassified_mask.astype(np.uint8), p_unclass, gdal.GDT_Byte, nodata_value=0)
    aligned_rasters["UNCLASSIFIED_MASK"] = p_unclass

    # Cloud shadow mask: Class 3
    p_shadow = processed_dir / f"{prefix}_aligned_shadow_mask.tif"
    write_geotiff(scl_result.cloud_shadow_mask.astype(np.uint8), p_shadow, gdal.GDT_Byte, nodata_value=0)
    aligned_rasters["SHADOW_MASK"] = p_shadow

    # Dark area mask: Class 2 (isolated dark area, not shadow, not water)
    p_dark = processed_dir / f"{prefix}_aligned_dark_mask.tif"
    write_geotiff(scl_result.dark_area_mask.astype(np.uint8), p_dark, gdal.GDT_Byte, nodata_value=0)
    aligned_rasters["DARK_MASK"] = p_dark

    # Multiclass reference water mask
    # 0 = Non-water, 1 = Water, 250 = Snow/Ice, 251 = Defective, 252 = Dark Area, 253 = Shadow, 254 = Cloud, 255 = NoData
    ref_water_mask = np.full(scl_arr.shape, REF_LABEL_NODATA, dtype=np.uint8)

    # Clear observation classification: Water if (MNDWI > 0.0 or SCL == 6)
    clear_water = scl_result.clear_mask & ((mndwi > 0.0) | (scl_arr == 6))
    clear_non_water = scl_result.clear_mask & (~clear_water)

    ref_water_mask[clear_non_water] = REF_LABEL_NON_WATER
    ref_water_mask[clear_water] = REF_LABEL_WATER
    ref_water_mask[scl_result.dark_area_mask] = REF_LABEL_UNCERTAIN_DARK_AREA
    ref_water_mask[scl_result.cloud_shadow_mask] = REF_LABEL_UNCERTAIN_SHADOW
    ref_water_mask[scl_result.cloud_cirrus_mask] = REF_LABEL_UNCERTAIN_CLOUD
    ref_water_mask[scl_result.invalid_defective_mask] = REF_LABEL_UNCERTAIN_INVALID
    ref_water_mask[scl_result.snow_ice_mask] = REF_LABEL_EXCLUDED_SNOW_ICE
    ref_water_mask[scl_result.nodata_mask | np.isnan(refl_b03) | np.isnan(refl_b11)] = REF_LABEL_NODATA

    p_water_mask = processed_dir / f"{prefix}_aligned_water_mask.tif"
    write_geotiff(ref_water_mask, p_water_mask, gdal.GDT_Byte, nodata_value=REF_LABEL_NODATA)
    aligned_rasters["WATER_MASK"] = p_water_mask

    # 7. AOI & Full-Scene Statistics
    aoi_scl = scl_arr[aoi_mask]
    aoi_ref_water = ref_water_mask[aoi_mask]
    aoi_mndwi = mndwi[aoi_mask]
    aoi_awei = awei_nsh[aoi_mask]

    aoi_total = int(len(aoi_scl))
    aoi_water = int(np.sum(aoi_ref_water == REF_LABEL_WATER))
    aoi_non_water = int(np.sum(aoi_ref_water == REF_LABEL_NON_WATER))
    aoi_clear_total = aoi_water + aoi_non_water
    aoi_pure_cloud = int(np.sum(np.isin(aoi_scl, [8, 9, 10])))
    aoi_unclassified = int(np.sum(aoi_scl == 7))
    aoi_cloud_combined = int(np.sum(np.isin(aoi_scl, [7, 8, 9, 10])))
    aoi_shadow = int(np.sum(aoi_scl == 3))
    aoi_dark = int(np.sum(aoi_scl == 2))
    aoi_defective = int(np.sum(aoi_scl == 1))
    aoi_snow = int(np.sum(aoi_scl == 11))
    aoi_nodata = int(np.sum(aoi_scl == 0))

    aoi_clear_pct = round((aoi_clear_total / aoi_total) * 100.0, 2)
    aoi_water_pct = round((aoi_water / aoi_total) * 100.0, 2)
    aoi_non_water_pct = round((aoi_non_water / aoi_total) * 100.0, 2)
    aoi_pure_cloud_pct = round((aoi_pure_cloud / aoi_total) * 100.0, 2)
    aoi_unclassified_pct = round((aoi_unclassified / aoi_total) * 100.0, 2)
    aoi_cloud_combined_pct = round((aoi_cloud_combined / aoi_total) * 100.0, 2)
    aoi_cloud = aoi_cloud_combined
    aoi_cloud_pct = aoi_cloud_combined_pct
    aoi_shadow_pct = round((aoi_shadow / aoi_total) * 100.0, 2)
    aoi_dark_pct = round((aoi_dark / aoi_total) * 100.0, 2)
    aoi_nodata_pct = round((aoi_nodata / aoi_total) * 100.0, 2)

    # Usability Status Determination:
    # If usable clear >= 50% -> READY
    # If usable clear >= 10% -> PARTIALLY_USABLE (suitable for masked pixel-level validation)
    # Else -> BLOCKED
    if aoi_clear_pct >= 50.0:
        quality_status = "READY"
    elif aoi_clear_pct >= 10.0:
        quality_status = "PARTIALLY_USABLE"
    else:
        quality_status = "BLOCKED"

    full_total = int(scl_arr.size)
    full_water = int(np.sum(ref_water_mask == REF_LABEL_WATER))
    full_non_water = int(np.sum(ref_water_mask == REF_LABEL_NON_WATER))
    full_clear_total = full_water + full_non_water
    full_cloud = int(np.sum(np.isin(scl_arr, [7, 8, 9, 10])))
    full_shadow = int(np.sum(scl_arr == 3))
    full_dark = int(np.sum(scl_arr == 2))
    full_nodata = int(np.sum(scl_arr == 0))

    qc_report = {
        "dataset_name": dataset_name,
        "archive_filename": zip_path.name,
        "sha256": sha256_hash,
        "satellite": metadata.get("spacecraft_name", "Sentinel-2A"),
        "processing_baseline": metadata.get("processing_baseline", "05.10"),
        "quantification_value": quant_val,
        "boa_add_offsets": {
            "B03": offset_b03,
            "B08": offset_b08,
            "B11": offset_b11,
            "B12": offset_b12,
        },
        "acquisition_datetime": metadata.get("datatake_start_time"),
        "temporal_pairing": {
            "sar_pair_date": sar_pair_date,
            "delta_t_days": temporal_delta_days,
            "is_simultaneous": False,
            "temporal_uncertainty_note": (
                f"Reference optical image acquired {temporal_delta_days} day(s) from Sentinel-1 SAR acquisition "
                f"({sar_pair_date}). Flood hydrograph changes and river stage fluctuations between acquisitions "
                "must be considered during validation."
            ),
        },
        "aoi_quality_assessment": {
            "study_area": "Jamuna River, Kazipur / Sirajganj, Bangladesh",
            "aoi_wkt": STUDY_AREA_AOI_WKT,
            "status": quality_status,
            "aoi_total_pixels": aoi_total,
            "aoi_swath_coverage_pct": 100.0 if aoi_nodata == 0 else round((1 - aoi_nodata / aoi_total) * 100.0, 2),
            "aoi_usable_clear_pixels": aoi_clear_total,
            "aoi_usable_clear_pct": aoi_clear_pct,
            "aoi_clear_water_pixels": aoi_water,
            "aoi_clear_water_pct": aoi_water_pct,
            "aoi_clear_water_km2": round(aoi_water * 0.0004, 4),
            "aoi_clear_non_water_pixels": aoi_non_water,
            "aoi_clear_non_water_pct": aoi_non_water_pct,
            "aoi_clear_non_water_km2": round(aoi_non_water * 0.0004, 4),
            "aoi_pure_cloud_pixels": aoi_pure_cloud,
            "aoi_pure_cloud_pct": aoi_pure_cloud_pct,
            "aoi_unclassified_pixels": aoi_unclassified,
            "aoi_unclassified_pct": aoi_unclassified_pct,
            "aoi_cloud_pixels": aoi_cloud_combined,
            "aoi_cloud_pct": aoi_cloud_combined_pct,
            "aoi_cloud_and_unclassified_pixels": aoi_cloud_combined,
            "aoi_cloud_and_unclassified_pct": aoi_cloud_combined_pct,
            "aoi_shadow_pixels": aoi_shadow,
            "aoi_shadow_pct": aoi_shadow_pct,
            "aoi_dark_area_pixels": aoi_dark,
            "aoi_dark_area_pct": aoi_dark_pct,
            "aoi_nodata_pixels": aoi_nodata,
            "aoi_nodata_pct": aoi_nodata_pct,
            "mndwi_statistics_clear_water": {
                "mean": float(np.nanmean(aoi_mndwi[aoi_ref_water == REF_LABEL_WATER])),
                "min": float(np.nanmin(aoi_mndwi[aoi_ref_water == REF_LABEL_WATER])),
                "max": float(np.nanmax(aoi_mndwi[aoi_ref_water == REF_LABEL_WATER])),
            },
            "mndwi_statistics_clear_non_water": {
                "mean": float(np.nanmean(aoi_mndwi[aoi_ref_water == REF_LABEL_NON_WATER])),
                "min": float(np.nanmin(aoi_mndwi[aoi_ref_water == REF_LABEL_NON_WATER])),
                "max": float(np.nanmax(aoi_mndwi[aoi_ref_water == REF_LABEL_NON_WATER])),
            },
        },
        "full_scene_statistics": {
            "total_pixels": full_total,
            "usable_clear_pixels": full_clear_total,
            "usable_clear_pct": round((full_clear_total / full_total) * 100.0, 2),
            "water_pixels": full_water,
            "water_pct": round((full_water / full_total) * 100.0, 2),
            "non_water_pixels": full_non_water,
            "non_water_pct": round((full_non_water / full_total) * 100.0, 2),
            "pure_cloud_pixels": int(np.sum(np.isin(scl_arr, [8, 9, 10]))),
            "pure_cloud_pct": round((int(np.sum(np.isin(scl_arr, [8, 9, 10]))) / full_total) * 100.0, 2),
            "unclassified_pixels": int(np.sum(scl_arr == 7)),
            "unclassified_pct": round((int(np.sum(scl_arr == 7)) / full_total) * 100.0, 2),
            "cloud_pixels": int(np.sum(np.isin(scl_arr, [8, 9, 10]))),
            "cloud_pct": round((int(np.sum(np.isin(scl_arr, [8, 9, 10]))) / full_total) * 100.0, 2),
            "cloud_and_unclassified_pixels": int(np.sum(np.isin(scl_arr, [7, 8, 9, 10]))),
            "cloud_and_unclassified_pct": round((int(np.sum(np.isin(scl_arr, [7, 8, 9, 10]))) / full_total) * 100.0, 2),
            "shadow_pixels": full_shadow,
            "shadow_pct": round((full_shadow / full_total) * 100.0, 2),
            "dark_area_pixels": full_dark,
            "dark_area_pct": round((full_dark / full_total) * 100.0, 2),
            "nodata_pixels": full_nodata,
        },
        "aligned_products": {k: str(v) for k, v in aligned_rasters.items()},
    }

    logger.info(f"Completed processing for {dataset_name}. Status: {quality_status}")
    logger.info(f"  AOI Usable clear: {aoi_clear_pct}% ({aoi_clear_total} px)")
    logger.info(f"  AOI Clear water:  {aoi_water_pct}% ({aoi_water} px, {round(aoi_water * 0.0004, 2)} km²)")
    logger.info(f"  AOI Pure Cloud:   {aoi_pure_cloud_pct}% ({aoi_pure_cloud} px)")
    logger.info(f"  AOI Unclassified: {aoi_unclassified_pct}% ({aoi_unclassified} px)")
    logger.info(f"  AOI Cloud+Unclass:{aoi_cloud_combined_pct}% ({aoi_cloud_combined} px)")
    logger.info(f"  AOI Cloud shadow: {aoi_shadow_pct}% ({aoi_shadow} px)")
    logger.info(f"  AOI Dark areas:   {aoi_dark_pct}% ({aoi_dark} px)")

    return qc_report


def run_phase4c1_pipeline() -> Dict[str, Any]:
    """Orchestrates Phase 4C.1 Sentinel-2 real data ingestion pipeline."""
    project_root = find_project_root()
    logger.info(f"Starting Phase 4C.1 Pipeline. Project Root: {project_root}")

    # Paths
    s2_base = project_root / "data" / "reference" / "optical" / "sentinel2"
    june_zip = s2_base / "June_2024" / "S2A_MSIL2A_20240607T043711_N0510_R033_T45RYH_20240607T091101.SAFE.zip"
    july_zip = s2_base / "July_2024" / "S2A_MSIL2A_20240717T043701_N0510_R033_T45RYH_20240717T145054.SAFE.zip"

    extracted_base = s2_base / "extracted"
    june_extracted = extracted_base / "june_2024"
    july_extracted = extracted_base / "july_2024"

    proc_base = project_root / "data" / "processed" / "reference" / "optical" / "sentinel2"
    june_processed = proc_base / "june_2024"
    july_processed = proc_base / "july_2024"

    stats_dir = project_root / "data" / "outputs" / "phase4c1" / "statistics"
    stats_dir.mkdir(parents=True, exist_ok=True)

    sar_ref_path = project_root / "data" / "processed" / "aligned" / "june10_aligned.tif"
    if not sar_ref_path.is_file():
        raise FileNotFoundError(f"Missing canonical SAR reference raster at {sar_ref_path}")

    # Create AOI mask
    aoi_mask = create_study_aoi_raster_mask(sar_ref_path)

    # 1. Process June 07 acquisition (paired with June 10 SAR, delta_t = 3 days)
    june_qc = process_sentinel2_dataset(
        dataset_name="Sentinel-2A MSI L2A 2024-06-07 (T45RYH)",
        zip_path=june_zip,
        extracted_dir=june_extracted,
        processed_dir=june_processed,
        sar_ref_path=sar_ref_path,
        aoi_mask=aoi_mask,
        temporal_delta_days=3,
        sar_pair_date="2024-06-10",
    )

    # 2. Process July 17 acquisition (paired with July 16 SAR, delta_t = 1 day)
    july_qc = process_sentinel2_dataset(
        dataset_name="Sentinel-2A MSI L2A 2024-07-17 (T45RYH)",
        zip_path=july_zip,
        extracted_dir=july_extracted,
        processed_dir=july_processed,
        sar_ref_path=sar_ref_path,
        aoi_mask=aoi_mask,
        temporal_delta_days=1,
        sar_pair_date="2024-07-16",
    )

    # 3. Save JSON reports
    with open(stats_dir / "sentinel2_june07_qc.json", "w", encoding="utf-8") as f:
        json.dump(june_qc, f, indent=2)

    with open(stats_dir / "sentinel2_july17_qc.json", "w", encoding="utf-8") as f:
        json.dump(july_qc, f, indent=2)

    # 4. Save AOI comparison CSV
    comparison_rows = [
        {
            "Metric": "Acquisition Date",
            "June 07, 2024": "2024-06-07T04:37:11Z",
            "July 17, 2024": "2024-07-17T04:37:01Z",
        },
        {
            "Metric": "Paired SAR Date",
            "June 07, 2024": "2024-06-10",
            "July 17, 2024": "2024-07-16",
        },
        {
            "Metric": "Temporal Gap (days)",
            "June 07, 2024": 3,
            "July 17, 2024": 1,
        },
        {
            "Metric": "Processing Baseline",
            "June 07, 2024": june_qc["processing_baseline"],
            "July 17, 2024": july_qc["processing_baseline"],
        },
        {
            "Metric": "AOI Swath Coverage (%)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_swath_coverage_pct"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_swath_coverage_pct"],
        },
        {
            "Metric": "AOI Usable Clear Pixels",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_usable_clear_pixels"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_usable_clear_pixels"],
        },
        {
            "Metric": "AOI Usable Clear (%)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_usable_clear_pct"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_usable_clear_pct"],
        },
        {
            "Metric": "AOI Clear Water Pixels",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_clear_water_pixels"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_clear_water_pixels"],
        },
        {
            "Metric": "AOI Clear Water (km²)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_clear_water_km2"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_clear_water_km2"],
        },
        {
            "Metric": "AOI Clear Land (km²)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_clear_non_water_km2"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_clear_non_water_km2"],
        },
        {
            "Metric": "AOI Pure Cloud Cover (Classes 8-10, %)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_pure_cloud_pct"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_pure_cloud_pct"],
        },
        {
            "Metric": "AOI Unclassified (Class 7, %)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_unclassified_pct"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_unclassified_pct"],
        },
        {
            "Metric": "AOI Combined Cloud & Unclassified (%)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_cloud_and_unclassified_pct"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_cloud_and_unclassified_pct"],
        },
        {
            "Metric": "AOI Cloud Shadow (%)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_shadow_pct"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_shadow_pct"],
        },
        {
            "Metric": "AOI Dark Area Pixels (%)",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["aoi_dark_area_pct"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["aoi_dark_area_pct"],
        },
        {
            "Metric": "Validation Status",
            "June 07, 2024": june_qc["aoi_quality_assessment"]["status"],
            "July 17, 2024": july_qc["aoi_quality_assessment"]["status"],
        },
    ]
    df_cmp = pd.DataFrame(comparison_rows)
    df_cmp.to_csv(stats_dir / "sentinel2_aoi_comparison.csv", index=False)

    # 5. Summary Report
    summary_report = {
        "phase": "4C.1 — Sentinel-2 Real Data Ingestion",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "datasets_processed": 2,
        "results": {
            "june_2024": june_qc,
            "july_2024": july_qc,
        },
    }
    with open(stats_dir / "sentinel2_ingestion_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2)

    # 6. Update reference data registry
    reg_path = project_root / "data" / "metadata" / "reference_data_registry.json"
    registry = ReferenceDataRegistry(reg_path)

    # June entry
    registry.register_dataset({
        "dataset_id": "s2a_msil2a_20240607_t45ryh",
        "dataset_name": "Sentinel-2A MSI L2A 2024-06-07 (T45RYH)",
        "product_name": "Sentinel-2 Level-2A Bottom-Of-Atmosphere Reflectance",
        "category": "optical",
        "provider": "European Space Agency (ESA) / Copernicus",
        "source_identifier": "S2A_MSIL2A_20240607T043711_N0510_R033_T45RYH_20240607T091101.SAFE",
        "source_url_or_citation": "Copernicus Data Space Ecosystem (https://dataspace.copernicus.eu)",
        "acquisition_date": "2024-06-07T04:37:11Z",
        "original_acquisition_date": "2024-06-07T04:37:11Z",
        "processing_level": "Level-2A (BOA Reflectance + SCL)",
        "spatial_extent": STUDY_AREA_AOI_WKT,
        "spatial_extent_wkt": STUDY_AREA_AOI_WKT,
        "crs": f"EPSG:{SAR_TARGET_EPSG}",
        "spatial_resolution": "20m (Aggregated B03/B08 from 10m, Native B11/B12/SCL at 20m)",
        "resolution": 20.0,
        "original_filename": str(june_zip.relative_to(project_root)),
        "local_file_path": str(june_zip),
        "sha256": june_qc["sha256"],
        "processing_history": (
            "Selective SAFE extraction -> GDAL area-weighted resampling to canonical 20m SAR grid (EPSG:32645) -> "
            "BOA reflectance scaling (offset=-1000, scale=10000) -> MNDWI/AWEI calculation -> SCL quality masking"
        ),
        "license_or_usage_conditions": "Copernicus Sentinel Data Terms and Conditions (Open Access)",
        "intended_validation_purpose": (
            "Independent optical surface water extent validation for satellite flood-change mapping "
            "(non-simultaneous reference, delta_t = 3 days)"
        ),
        "quality_information": june_qc["aoi_quality_assessment"],
    }, enforce_provenance=True)

    # July entry
    registry.register_dataset({
        "dataset_id": "s2a_msil2a_20240717_t45ryh",
        "dataset_name": "Sentinel-2A MSI L2A 2024-07-17 (T45RYH)",
        "product_name": "Sentinel-2 Level-2A Bottom-Of-Atmosphere Reflectance",
        "category": "optical",
        "provider": "European Space Agency (ESA) / Copernicus",
        "source_identifier": "S2A_MSIL2A_20240717T043701_N0510_R033_T45RYH_20240717T145054.SAFE",
        "source_url_or_citation": "Copernicus Data Space Ecosystem (https://dataspace.copernicus.eu)",
        "acquisition_date": "2024-07-17T04:37:01Z",
        "original_acquisition_date": "2024-07-17T04:37:01Z",
        "processing_level": "Level-2A (BOA Reflectance + SCL)",
        "spatial_extent": STUDY_AREA_AOI_WKT,
        "spatial_extent_wkt": STUDY_AREA_AOI_WKT,
        "crs": f"EPSG:{SAR_TARGET_EPSG}",
        "spatial_resolution": "20m (Aggregated B03/B08 from 10m, Native B11/B12/SCL at 20m)",
        "resolution": 20.0,
        "original_filename": str(july_zip.relative_to(project_root)),
        "local_file_path": str(july_zip),
        "sha256": july_qc["sha256"],
        "processing_history": (
            "Selective SAFE extraction -> GDAL area-weighted resampling to canonical 20m SAR grid (EPSG:32645) -> "
            "BOA reflectance scaling (offset=-1000, scale=10000) -> MNDWI/AWEI calculation -> SCL quality masking"
        ),
        "license_or_usage_conditions": "Copernicus Sentinel Data Terms and Conditions (Open Access)",
        "intended_validation_purpose": (
            "Independent optical surface water extent validation for satellite flood-change mapping "
            "(non-simultaneous reference, delta_t = 1 day)"
        ),
        "quality_information": july_qc["aoi_quality_assessment"],
    }, enforce_provenance=True)

    # 7. Metadata Report in data/metadata/
    meta_report_path = project_root / "data" / "metadata" / "phase4c1_sentinel2_ingestion_report.json"
    with open(meta_report_path, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2)

    logger.info(f"Phase 4C.1 Pipeline execution finished successfully.")
    return summary_report


if __name__ == "__main__":
    run_phase4c1_pipeline()
