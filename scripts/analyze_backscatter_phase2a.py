#!/usr/bin/env python3
"""
Earth Pulse — Phase 2A: Radiometric Analysis & Backscatter Characterization
NASA Space Apps Challenge 2026: Dancing with the SARs

This script implements Phase 2A:
1. Pre-analysis thermal-noise verification (preventing double correction).
2. Linear Sigma0 to decibel (dB) conversion (masked against zero/negative/NoData).
3. Statistical characterization for all 4 channels (June 10 VV/VH, July 16 VV/VH).
4. Individual and comparative backscatter histograms (PNG plots and CSV tables).
5. Backscatter temporal difference rasters and spatial difference maps (July 16 - June 10).
6. Preliminary Kazipur AOI valid-data assessment.
7. Machine-readable audit reporting.

Strictly preserves original and Phase 1 files.
Does NOT perform water classification or flood thresholding.
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.pyplot as plt
import numpy as np
from osgeo import gdal, ogr, osr

# Configure GDAL memory and exceptions
gdal.UseExceptions()
gdal.SetCacheMax(128 * 1024 * 1024)  # 128 MB cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("EarthPulse.Phase2A")

NODATA_VALUE = -9999.0
PRELIMINARY_AOI_WKT = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"


def find_project_root(start_path: Optional[Path] = None) -> Path:
    """Locate the canonical EarthPulse-SAR project root directory."""
    candidates = []
    if start_path:
        candidates.append(Path(start_path).resolve())
    if "EARTHPULSE_ROOT" in os.environ:
        candidates.append(Path(os.environ["EARTHPULSE_ROOT"]).resolve())

    cwd = Path.cwd().resolve()
    candidates.append(cwd)
    if (cwd / "EarthPulse-SAR").is_dir():
        candidates.append(cwd / "EarthPulse-SAR")

    script_dir = Path(__file__).resolve().parent
    candidates.append(script_dir.parent)

    for candidate in candidates:
        if (candidate / "data" / "processed" / "aligned").is_dir() or (candidate / "data" / "raw" / "sentinel1").is_dir():
            return candidate

    return script_dir.parent


def compute_sha256(filepath: str) -> str:
    """Compute SHA-256 checksum of a file in 8MB chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


# =========================================================================
# PART 1: PRE-ANALYSIS SCIENTIFIC CHECKS
# =========================================================================

def verify_thermal_noise_correction(raw_sentinel_dir: str) -> Dict[str, Any]:
    """
    Inspect the thermalNoiseCorrectionPerformed metadata tag in the original
    Sentinel-1 SAFE annotation XML files to ensure Level-1 IPF processing did
    NOT apply thermal noise correction prior to SNAP's ThermalNoiseRemoval.
    """
    if not os.path.isdir(raw_sentinel_dir):
        raise FileNotFoundError(f"Raw Sentinel-1 directory not found: {raw_sentinel_dir}")

    zip_files = sorted(Path(raw_sentinel_dir).glob("*.zip"))
    if not zip_files:
        raise FileNotFoundError(f"No Sentinel-1 ZIP archives found in: {raw_sentinel_dir}")

    verification_records = {}

    for zp in zip_files:
        zp_str = str(zp)
        file_records = []
        with zipfile.ZipFile(zp_str, "r") as z:
            annot_files = [n for n in z.namelist() if "/annotation/s1a" in n and n.endswith(".xml")]
            if not annot_files:
                raise ValueError(f"No annotation XML files found inside {zp.name}")

            for an in annot_files:
                tree = ET.fromstring(z.read(an))
                tn_tag = None
                for elem in tree.iter():
                    if elem.tag.endswith("thermalNoiseCorrectionPerformed"):
                        tn_tag = elem.text.strip().lower()
                        break

                if tn_tag is None:
                    raise ValueError(f"Tag 'thermalNoiseCorrectionPerformed' missing in {an} of {zp.name}")

                is_performed = (tn_tag == "true")
                file_records.append({
                    "annotation_file": an,
                    "thermalNoiseCorrectionPerformed": is_performed,
                })

                if is_performed:
                    raise RuntimeError(
                        f"CRITICAL DOUBLE-CORRECTION HAZARD: Archive {zp.name} has "
                        f"thermalNoiseCorrectionPerformed = true. SNAP also applied "
                        f"ThermalNoiseRemoval. Stopping scientific processing to prevent corrupted backscatter."
                    )

        verification_records[zp.name] = file_records

    logger.info("Thermal noise verification PASSED: All SAFE archives have thermalNoiseCorrectionPerformed = false. No double correction.")
    return {
        "status": "VERIFIED_NOT_DUPLICATED",
        "description": "Level-1 IPF processing left thermal noise correction unperformed; SNAP applied it exactly once.",
        "records": verification_records,
    }


def verify_aligned_inputs(june_path: str, july_path: str) -> Dict[str, Any]:
    """Verify that Phase 1 aligned rasters meet all strict structural criteria."""
    for p in [june_path, july_path]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Aligned input raster not found: {p}")

        ds = gdal.Open(p, gdal.GA_ReadOnly)
        if ds is None:
            raise RuntimeError(f"GDAL could not open input raster: {p}")

        if ds.RasterCount != 2:
            raise ValueError(f"Expected 2 bands in {p}, found {ds.RasterCount}")
        if ds.RasterXSize != 1405 or ds.RasterYSize != 1393:
            raise ValueError(f"Dimensions mismatch in {p}: expected 1405x1393, got {ds.RasterXSize}x{ds.RasterYSize}")

        b1 = ds.GetRasterBand(1)
        b2 = ds.GetRasterBand(2)
        if gdal.GetDataTypeName(b1.DataType) != "Float32" or gdal.GetDataTypeName(b2.DataType) != "Float32":
            raise ValueError(f"Data type must be Float32 in {p}")
        if b1.GetDescription() != "Sigma0_VH":
            raise ValueError(f"Band 1 description must be 'Sigma0_VH' in {p}, got '{b1.GetDescription()}'")
        if b2.GetDescription() != "Sigma0_VV":
            raise ValueError(f"Band 2 description must be 'Sigma0_VV' in {p}, got '{b2.GetDescription()}'")
        if b1.GetNoDataValue() != NODATA_VALUE or b2.GetNoDataValue() != NODATA_VALUE:
            raise ValueError(f"NoData value must be {NODATA_VALUE} in {p}")

        srs = osr.SpatialReference()
        srs.ImportFromWkt(ds.GetProjection())
        if srs.GetAttrValue("AUTHORITY", 1) != "32645":
            raise ValueError(f"CRS must be EPSG:32645 in {p}, got {srs.GetAttrValue('AUTHORITY', 1)}")
        ds = None

    ds1 = gdal.Open(june_path, gdal.GA_ReadOnly)
    ds2 = gdal.Open(july_path, gdal.GA_ReadOnly)
    gt1 = ds1.GetGeoTransform()
    gt2 = ds2.GetGeoTransform()
    if gt1 != gt2:
        raise ValueError(f"GeoTransforms are not identical between June 10 and July 16: {gt1} vs {gt2}")

    return {
        "status": "VERIFIED_COMPLIANT",
        "dimensions": [1405, 1393],
        "crs": "EPSG:32645",
        "geotransform": gt1,
        "bands": {1: "Sigma0_VH", 2: "Sigma0_VV"},
        "nodata": NODATA_VALUE,
    }


# =========================================================================
# PART 2: LINEAR TO dB CONVERSION
# =========================================================================

def convert_linear_array_to_db(linear_arr: np.ndarray, nodata: float = NODATA_VALUE) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convert a linear Sigma0 numpy array to decibels (dB):
    sigma0_db = 10 * log10(sigma0_linear)
    Valid pixels: finite, > 0.0, and != nodata.
    Invalid pixels remain nodata.
    """
    valid_mask = (linear_arr > 0.0) & (linear_arr != nodata) & np.isfinite(linear_arr)
    db_arr = np.full_like(linear_arr, nodata, dtype=np.float32)
    db_arr[valid_mask] = 10.0 * np.log10(linear_arr[valid_mask])
    return db_arr, valid_mask


def create_db_raster(
    src_aligned_path: str,
    band_idx: int,
    out_db_path: str,
    band_desc: str,
    overwrite: bool = False,
    block_size: int = 512,
) -> Dict[str, Any]:
    """
    Create a single-band GeoTIFF in decibels (dB) from an aligned multi-band raster:
    - Reads in memory-conscious blocks.
    - Applies 10 * log10(x) for x > 0.
    - Sets NoData = -9999.0.
    - Writes tiled DEFLATE GeoTIFF with predictor 3.
    """
    if os.path.exists(out_db_path) and not overwrite:
        raise FileExistsError(f"Output raster already exists: {out_db_path}. Set overwrite=True.")

    src_ds = gdal.Open(src_aligned_path, gdal.GA_ReadOnly)
    w = src_ds.RasterXSize
    h = src_ds.RasterYSize
    gt = src_ds.GetGeoTransform()
    proj = src_ds.GetProjection()

    os.makedirs(os.path.dirname(os.path.abspath(out_db_path)), exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    creation_options = [
        "TILED=YES",
        "COMPRESS=DEFLATE",
        "PREDICTOR=3",
        "BIGTIFF=IF_SAFER",
        "BLOCKXSIZE=256",
        "BLOCKYSIZE=256",
    ]

    out_ds = driver.Create(out_db_path, w, h, 1, gdal.GDT_Float32, options=creation_options)
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(proj)

    dst_band = out_ds.GetRasterBand(1)
    dst_band.SetDescription(band_desc)
    dst_band.SetNoDataValue(NODATA_VALUE)

    src_band = src_ds.GetRasterBand(band_idx)

    valid_count = 0
    nodata_count = 0

    for y in range(0, h, block_size):
        rows = min(block_size, h - y)
        for x in range(0, w, block_size):
            cols = min(block_size, w - x)
            chunk = src_band.ReadAsArray(x, y, cols, rows)
            db_chunk, valid_mask = convert_linear_array_to_db(chunk, NODATA_VALUE)

            valid_count += int(np.sum(valid_mask))
            nodata_count += int(np.sum(~valid_mask))
            dst_band.WriteArray(db_chunk, x, y)

    out_ds.SetMetadata({
        "CALIBRATION": "Sigma0_dB = 10 * log10(Sigma0_linear)",
        "BAND": band_desc,
        "NODATA_VALUE": str(NODATA_VALUE),
        "SOURCE_ALIGNED": os.path.basename(src_aligned_path),
        "SOURCE_BAND_INDEX": str(band_idx),
    })

    out_ds.FlushCache()
    out_ds = None
    src_ds = None

    logger.info(f"Generated dB raster: {out_db_path} ({valid_count:,} valid pixels)")
    return {
        "output_path": out_db_path,
        "sha256": compute_sha256(out_db_path),
        "valid_pixels": valid_count,
        "nodata_pixels": nodata_count,
    }


# =========================================================================
# PART 3: STATISTICAL CHARACTERIZATION
# =========================================================================

def compute_channel_statistics(
    db_raster_path: str,
    linear_raster_path: str,
    linear_band_idx: int,
    block_size: int = 512,
) -> Dict[str, Any]:
    """
    Calculate thorough radiometric statistics for valid pixels:
    - Min, max, mean, median, stddev.
    - Percentiles: 5th, 10th, 25th, 50th, 75th, 90th, 95th, 99th.
    - Reference linear Sigma0 statistics.
    Uses memory-conscious block-reading to collect valid 1D values (approx 5.5MB)
    allowing exact NumPy percentile computation without approximation.
    """
    ds_db = gdal.Open(db_raster_path, gdal.GA_ReadOnly)
    w = ds_db.RasterXSize
    h = ds_db.RasterYSize
    total_pixels = w * h

    ds_lin = gdal.Open(linear_raster_path, gdal.GA_ReadOnly)
    b_lin = ds_lin.GetRasterBand(linear_band_idx)
    b_db = ds_db.GetRasterBand(1)

    db_valid_chunks = []
    lin_valid_chunks = []

    for y in range(0, h, block_size):
        rows = min(block_size, h - y)
        for x in range(0, w, block_size):
            cols = min(block_size, w - x)
            db_c = b_db.ReadAsArray(x, y, cols, rows)
            lin_c = b_lin.ReadAsArray(x, y, cols, rows)

            mask = (db_c != NODATA_VALUE) & np.isfinite(db_c)
            if np.any(mask):
                db_valid_chunks.append(db_c[mask])
                lin_valid_chunks.append(lin_c[mask])

    ds_db = None
    ds_lin = None

    db_vals = np.concatenate(db_valid_chunks)
    lin_vals = np.concatenate(lin_valid_chunks)

    valid_count = int(len(db_vals))
    invalid_count = total_pixels - valid_count

    percentile_levels = [5, 10, 25, 50, 75, 90, 95, 99]
    db_pcts = np.percentile(db_vals, percentile_levels, method="linear")
    lin_pcts = np.percentile(lin_vals, percentile_levels, method="linear")

    pct_dict = {f"p{lvl}": float(val) for lvl, val in zip(percentile_levels, db_pcts)}
    lin_pct_dict = {f"p{lvl}": float(val) for lvl, val in zip(percentile_levels, lin_pcts)}

    stats = {
        "raster_file": os.path.basename(db_raster_path),
        "total_pixels": total_pixels,
        "valid_pixels": valid_count,
        "invalid_pixels": invalid_count,
        "valid_percentage": round(valid_count / total_pixels * 100, 4),
        "decibel_stats": {
            "min_db": float(np.min(db_vals)),
            "max_db": float(np.max(db_vals)),
            "mean_db": float(np.mean(db_vals)),
            "median_db": float(np.median(db_vals)),
            "stddev_db": float(np.std(db_vals, ddof=1)),
            "percentiles_db": pct_dict,
        },
        "linear_sigma0_reference": {
            "min_linear": float(np.min(lin_vals)),
            "max_linear": float(np.max(lin_vals)),
            "mean_linear": float(np.mean(lin_vals)),
            "median_linear": float(np.median(lin_vals)),
            "stddev_linear": float(np.std(lin_vals, ddof=1)),
            "percentiles_linear": lin_pct_dict,
        },
    }
    return stats


# =========================================================================
# PART 4: HISTOGRAM GENERATION
# =========================================================================

def generate_histograms_and_tables(
    june_db_path: str,
    july_db_path: str,
    pol_name: str,
    plots_dir: str,
    data_dir: str,
    bins: int = 120,
) -> Dict[str, Any]:
    """
    Generate individual and comparative backscatter histograms:
    - Extracts valid dB pixels.
    - Establishes unified consistent bin edges across both dates.
    - Saves individual and comparative plots (PNG).
    - Saves histogram tables (CSV) with bin_left, bin_right, bin_center, count, density.
    """
    os.makedirs(plots_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    ds_j = gdal.Open(june_db_path, gdal.GA_ReadOnly)
    ds_y = gdal.Open(july_db_path, gdal.GA_ReadOnly)

    j_arr = ds_j.GetRasterBand(1).ReadAsArray()
    y_arr = ds_y.GetRasterBand(1).ReadAsArray()

    j_vals = j_arr[(j_arr != NODATA_VALUE) & np.isfinite(j_arr)]
    y_vals = y_arr[(y_arr != NODATA_VALUE) & np.isfinite(y_arr)]

    ds_j = None
    ds_y = None

    # Consistent bin edges spanning the full range of both acquisitions
    min_val = min(float(np.min(j_vals)), float(np.min(y_vals)))
    max_val = max(float(np.max(j_vals)), float(np.max(y_vals)))
    # Add small epsilon to upper edge so maximum value falls into the last bin
    bin_edges = np.linspace(min_val, max_val + 1e-4, bins + 1)

    hist_j, _ = np.histogram(j_vals, bins=bin_edges)
    hist_y, _ = np.histogram(y_vals, bins=bin_edges)

    bin_width = bin_edges[1] - bin_edges[0]
    dens_j = hist_j / (len(j_vals) * bin_width)
    dens_y = hist_y / (len(y_vals) * bin_width)

    # 1. Save CSV data tables
    csv_paths = {}
    for date_label, counts, density, vals in [("june10", hist_j, dens_j, j_vals), ("july16", hist_y, dens_y, y_vals)]:
        csv_file = os.path.join(data_dir, f"{date_label}_{pol_name.lower()}_histogram.csv")
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["bin_left_db", "bin_right_db", "bin_center_db", "pixel_count", "density_probability"])
            for idx in range(len(counts)):
                b_l = round(bin_edges[idx], 4)
                b_r = round(bin_edges[idx + 1], 4)
                b_c = round((b_l + b_r) / 2.0, 4)
                writer.writerow([b_l, b_r, b_c, int(counts[idx]), float(density[idx])])
        csv_paths[date_label] = csv_file

    # 2. Plot individual histograms
    plot_files = {}
    for date_label, counts, vals, color in [
        ("June 10, 2024", hist_j, j_vals, "#1f77b4"),
        ("July 16, 2024", hist_y, y_vals, "#d62728"),
    ]:
        tag = date_label.split(",")[0].replace(" ", "").lower()
        fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
        centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
        ax.bar(centers, counts, width=bin_width * 0.9, color=color, alpha=0.75, edgecolor="none")
        ax.set_title(f"Earth Pulse — Sentinel-1A {pol_name.upper()} Backscatter Distribution\n{date_label} (N = {len(vals):,})")
        ax.set_xlabel(r"$\sigma^0$ Backscatter [dB]")
        ax.set_ylabel("Pixel Frequency")
        ax.grid(True, linestyle="--", alpha=0.5)

        # Annotate median and mean
        med = np.median(vals)
        mean_v = np.mean(vals)
        ax.axvline(med, color="black", linestyle="--", linewidth=1.2, label=f"Median: {med:.2f} dB")
        ax.axvline(mean_v, color="blue", linestyle=":", linewidth=1.2, label=f"Mean: {mean_v:.2f} dB")
        ax.legend()

        p_path = os.path.join(plots_dir, f"{tag}_{pol_name.lower()}_histogram.png")
        fig.tight_layout()
        fig.savefig(p_path)
        plt.close(fig)
        plot_files[tag] = p_path

    # 3. Plot comparative normalized density histogram
    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=300)
    centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    ax.step(centers, dens_j, where="mid", color="#1f77b4", linewidth=2.0, label=f"June 10, 2024 Baseline (N={len(j_vals):,})")
    ax.fill_between(centers, dens_j, step="mid", color="#1f77b4", alpha=0.25)

    ax.step(centers, dens_y, where="mid", color="#d62728", linewidth=2.0, label=f"July 16, 2024 Flood Peak (N={len(y_vals):,})")
    ax.fill_between(centers, dens_y, step="mid", color="#d62728", alpha=0.25)

    ax.set_title(f"Earth Pulse — Comparative Backscatter Density ({pol_name.upper()})\nJamuna River Study Reach (Kazipur / Sirajganj, Bangladesh)")
    ax.set_xlabel(r"$\sigma^0$ Backscatter [dB]")
    ax.set_ylabel("Probability Density")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper left")

    comp_path = os.path.join(plots_dir, f"comparative_{pol_name.lower()}_histogram.png")
    fig.tight_layout()
    fig.savefig(comp_path)
    plt.close(fig)
    plot_files["comparative"] = comp_path

    logger.info(f"Generated {pol_name} histograms (plots: {plots_dir}, tables: {data_dir})")
    return {
        "polarization": pol_name,
        "bin_edges": [float(bin_edges[0]), float(bin_edges[-1])],
        "bin_count": bins,
        "bin_width_db": round(float(bin_width), 4),
        "plots": plot_files,
        "csv_tables": csv_paths,
    }


# =========================================================================
# PART 5: BACKSCATTER DIFFERENCE ANALYSIS
# =========================================================================

def compute_difference_raster(
    june_db_path: str,
    july_db_path: str,
    out_diff_path: str,
    band_desc: str,
    overwrite: bool = False,
    block_size: int = 512,
) -> Dict[str, Any]:
    """
    Calculate backscatter temporal difference raster:
    Delta_dB = July16_dB - June10_dB
    Calculated ONLY where BOTH acquisitions have valid pixels.
    Negative difference = backscatter decreased in July.
    Positive difference = backscatter increased in July.
    """
    if os.path.exists(out_diff_path) and not overwrite:
        raise FileExistsError(f"Output raster already exists: {out_diff_path}. Set overwrite=True.")

    ds_j = gdal.Open(june_db_path, gdal.GA_ReadOnly)
    ds_y = gdal.Open(july_db_path, gdal.GA_ReadOnly)

    w = ds_j.RasterXSize
    h = ds_j.RasterYSize
    gt = ds_j.GetGeoTransform()
    proj = ds_j.GetProjection()

    os.makedirs(os.path.dirname(os.path.abspath(out_diff_path)), exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    creation_options = [
        "TILED=YES",
        "COMPRESS=DEFLATE",
        "PREDICTOR=3",
        "BIGTIFF=IF_SAFER",
        "BLOCKXSIZE=256",
        "BLOCKYSIZE=256",
    ]

    out_ds = driver.Create(out_diff_path, w, h, 1, gdal.GDT_Float32, options=creation_options)
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(proj)

    dst_band = out_ds.GetRasterBand(1)
    dst_band.SetDescription(band_desc)
    dst_band.SetNoDataValue(NODATA_VALUE)

    b_j = ds_j.GetRasterBand(1)
    b_y = ds_y.GetRasterBand(1)

    diff_valid_chunks = []
    valid_common_count = 0
    nodata_count = 0

    for y in range(0, h, block_size):
        rows = min(block_size, h - y)
        for x in range(0, w, block_size):
            cols = min(block_size, w - x)
            j_c = b_j.ReadAsArray(x, y, cols, rows)
            y_c = b_y.ReadAsArray(x, y, cols, rows)

            common_mask = (j_c != NODATA_VALUE) & (y_c != NODATA_VALUE) & np.isfinite(j_c) & np.isfinite(y_c)
            diff_chunk = np.full_like(j_c, NODATA_VALUE, dtype=np.float32)
            diff_chunk[common_mask] = y_c[common_mask] - j_c[common_mask]

            valid_common_count += int(np.sum(common_mask))
            nodata_count += int(np.sum(~common_mask))
            dst_band.WriteArray(diff_chunk, x, y)

            if np.any(common_mask):
                diff_valid_chunks.append(diff_chunk[common_mask])

    out_ds.SetMetadata({
        "DESCRIPTION": "Earth Pulse Phase 2A: Temporal Backscatter Difference",
        "FORMULA": "Delta_dB = July16_dB - June10_dB",
        "POLARIZATION": band_desc,
        "NODATA_VALUE": str(NODATA_VALUE),
        "INTERPRETATION": "Negative = backscatter decrease; Positive = backscatter increase.",
    })

    out_ds.FlushCache()
    out_ds = None
    ds_j = None
    ds_y = None

    diff_vals = np.concatenate(diff_valid_chunks)
    pcts = np.percentile(diff_vals, [5, 10, 25, 50, 75, 90, 95, 99], method="linear")

    logger.info(f"Generated difference raster: {out_diff_path} (Common valid: {valid_common_count:,})")
    return {
        "output_path": out_diff_path,
        "sha256": compute_sha256(out_diff_path),
        "valid_common_pixels": valid_common_count,
        "nodata_pixels": nodata_count,
        "statistics": {
            "min_db": float(np.min(diff_vals)),
            "max_db": float(np.max(diff_vals)),
            "mean_db": float(np.mean(diff_vals)),
            "median_db": float(np.median(diff_vals)),
            "stddev_db": float(np.std(diff_vals, ddof=1)),
            "percentiles_db": {
                "p5": float(pcts[0]),
                "p10": float(pcts[1]),
                "p25": float(pcts[2]),
                "p50": float(pcts[3]),
                "p75": float(pcts[4]),
                "p90": float(pcts[5]),
                "p95": float(pcts[6]),
                "p99": float(pcts[7]),
            },
        },
    }


def generate_difference_map_png(
    diff_raster_path: str,
    pol_name: str,
    out_png_path: str,
    clip_db: float = 12.0,
) -> str:
    """Render high-resolution spatial backscatter difference map."""
    os.makedirs(os.path.dirname(os.path.abspath(out_png_path)), exist_ok=True)
    ds = gdal.Open(diff_raster_path, gdal.GA_ReadOnly)
    arr = ds.GetRasterBand(1).ReadAsArray()
    gt = ds.GetGeoTransform()
    ds = None

    mask = (arr == NODATA_VALUE) | (~np.isfinite(arr))
    masked_diff = np.ma.masked_array(arr, mask=mask)

    # Compute bounding box in UTM km
    w, h = arr.shape[1], arr.shape[0]
    extent = [gt[0] / 1000.0, (gt[0] + gt[1] * w) / 1000.0, (gt[3] + gt[5] * h) / 1000.0, gt[3] / 1000.0]

    fig, ax = plt.subplots(figsize=(10, 9), dpi=300)
    # Diverging colormap: Blue = Backscatter drop (inundation/smoothing), Red = Increase
    cmap = plt.cm.get_cmap("RdBu", 256)
    im = ax.imshow(
        masked_diff,
        cmap=cmap,
        vmin=-clip_db,
        vmax=clip_db,
        extent=extent,
        origin="upper",
    )

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(r"Temporal Backscatter Change $\Delta\sigma^0$ [dB] (July 16 − June 10)", fontsize=11)

    ax.set_title(
        f"Earth Pulse — Sentinel-1A {pol_name.upper()} Backscatter Difference Map\n"
        f"Jamuna River Study Area (Kazipur / Sirajganj, Bangladesh)",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xlabel("UTM Easting [km] (Zone 45N)", fontsize=10)
    ax.set_ylabel("UTM Northing [km] (Zone 45N)", fontsize=10)
    ax.grid(True, linestyle=":", alpha=0.5)

    # Add interpretive caption
    ax.text(
        0.02,
        0.02,
        "Blue: Decreased backscatter (water expansion / specular drop)\nRed: Increased backscatter (roughness / vegetation structure)",
        transform=ax.transAxes,
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    fig.tight_layout()
    fig.savefig(out_png_path)
    plt.close(fig)

    logger.info(f"Saved difference map plot: {out_png_path}")
    return out_png_path


# =========================================================================
# PART 6: AOI VALID-DATA ASSESSMENT
# =========================================================================

def assess_aoi_valid_data(
    june_aligned_path: str,
    july_aligned_path: str,
    aoi_wkt: str = PRELIMINARY_AOI_WKT,
) -> Dict[str, Any]:
    """
    Perform preliminary Kazipur AOI polygon valid-data coverage assessment:
    - Transforms WGS84 polygon to EPSG:32645.
    - Rasterizes AOI mask to match aligned raster grid.
    - Computes total AOI cells, June valid cells, July valid cells, common valid cells,
      percentage coverage, and valid area in km2.
    """
    ds_june = gdal.Open(june_aligned_path, gdal.GA_ReadOnly)
    ds_july = gdal.Open(july_aligned_path, gdal.GA_ReadOnly)

    w = ds_june.RasterXSize
    h = ds_june.RasterYSize
    gt = ds_june.GetGeoTransform()

    src_srs = osr.SpatialReference()
    src_srs.ImportFromEPSG(4326)
    src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    dst_srs = osr.SpatialReference()
    dst_srs.ImportFromEPSG(32645)
    tx = osr.CoordinateTransformation(src_srs, dst_srs)

    geom = ogr.CreateGeometryFromWkt(aoi_wkt)
    if geom is None:
        raise ValueError(f"Invalid AOI WKT geometry: {aoi_wkt}")
    geom.Transform(tx)

    # Rasterize AOI into memory raster
    mask_ds = gdal.GetDriverByName("MEM").Create("", w, h, 1, gdal.GDT_Byte)
    mask_ds.SetGeoTransform(gt)
    mask_ds.SetProjection(ds_june.GetProjection())

    mem_ds = ogr.GetDriverByName("MEM").CreateDataSource("aoi_mem")
    mem_lyr = mem_ds.CreateLayer("aoi", dst_srs, ogr.wkbPolygon)
    feat = ogr.Feature(mem_lyr.GetLayerDefn())
    feat.SetGeometry(geom)
    mem_lyr.CreateFeature(feat)

    gdal.RasterizeLayer(mask_ds, [1], mem_lyr, burn_values=[1])
    aoi_mask = (mask_ds.GetRasterBand(1).ReadAsArray() == 1)

    total_aoi_cells = int(np.sum(aoi_mask))
    pixel_area_m2 = gt[1] * abs(gt[5])
    pixel_area_km2 = pixel_area_m2 / 1e6

    # June valid
    j1 = ds_june.GetRasterBand(1).ReadAsArray()
    j2 = ds_june.GetRasterBand(2).ReadAsArray()
    june_valid = (j1 != NODATA_VALUE) & (j1 > 0.0) & np.isfinite(j1) & (j2 != NODATA_VALUE) & (j2 > 0.0) & np.isfinite(j2)

    # July valid
    y1 = ds_july.GetRasterBand(1).ReadAsArray()
    y2 = ds_july.GetRasterBand(2).ReadAsArray()
    july_valid = (y1 != NODATA_VALUE) & (y1 > 0.0) & np.isfinite(y1) & (y2 != NODATA_VALUE) & (y2 > 0.0) & np.isfinite(y2)

    ds_june = None
    ds_july = None

    june_aoi_valid = int(np.sum(june_valid & aoi_mask))
    july_aoi_valid = int(np.sum(july_valid & aoi_mask))
    common_aoi_valid = int(np.sum(june_valid & july_valid & aoi_mask))

    return {
        "status": "PRELIMINARY_AOI_ASSESSED",
        "aoi_wkt_wgs84": aoi_wkt,
        "aoi_transformed_envelope_utm45n": [round(c, 3) for c in geom.GetEnvelope()],
        "total_aoi_grid_cells": total_aoi_cells,
        "total_aoi_area_km2": round(total_aoi_cells * pixel_area_km2, 4),
        "june10_valid_aoi_cells": june_aoi_valid,
        "june10_valid_aoi_pct": round(june_aoi_valid / total_aoi_cells * 100, 4) if total_aoi_cells > 0 else 0.0,
        "july16_valid_aoi_cells": july_aoi_valid,
        "july16_valid_aoi_pct": round(july_aoi_valid / total_aoi_cells * 100, 4) if total_aoi_cells > 0 else 0.0,
        "common_valid_aoi_cells": common_aoi_valid,
        "common_valid_aoi_pct": round(common_aoi_valid / total_aoi_cells * 100, 4) if total_aoi_cells > 0 else 0.0,
        "common_valid_aoi_area_km2": round(common_aoi_valid * pixel_area_km2, 4),
    }


# =========================================================================
# PART 7: ORCHESTRATION PIPELINE
# =========================================================================

def run_phase2a_pipeline(
    project_root: Optional[Path] = None,
    overwrite: bool = False,
    block_size: int = 512,
) -> Dict[str, Any]:
    """Execute complete Phase 2A Radiometric Analysis pipeline."""
    start_time = time.time()
    root = find_project_root(project_root)
    logger.info(f"Operating from project root: {root}")

    # Paths
    raw_dir = str(root / "data" / "raw" / "sentinel1")
    aligned_dir = root / "data" / "processed" / "aligned"
    june_aligned = str(aligned_dir / "june10_aligned.tif")
    july_aligned = str(aligned_dir / "july16_aligned.tif")

    proc_dir = root / "data" / "processed" / "phase2a"
    out_hist_dir = str(root / "data" / "outputs" / "phase2a" / "histograms")
    out_hist_data_dir = str(root / "data" / "outputs" / "phase2a" / "histogram_data")
    out_diff_maps_dir = str(root / "data" / "outputs" / "phase2a" / "difference_maps")
    report_path = str(root / "data" / "metadata" / "phase2a_analysis_report.json")

    # Output dB rasters
    june_vh_db = str(proc_dir / "june10_sigma0_vh_db.tif")
    june_vv_db = str(proc_dir / "june10_sigma0_vv_db.tif")
    july_vh_db = str(proc_dir / "july16_sigma0_vh_db.tif")
    july_vv_db = str(proc_dir / "july16_sigma0_vv_db.tif")

    # Output diff rasters
    delta_vh_db = str(proc_dir / "delta_vh_db.tif")
    delta_vv_db = str(proc_dir / "delta_vv_db.tif")

    # Check overwrite protection
    if not overwrite:
        for out_f in [june_vh_db, june_vv_db, july_vh_db, july_vv_db, delta_vh_db, delta_vv_db]:
            if os.path.exists(out_f):
                raise FileExistsError(f"Output raster already exists: {out_f}. Set overwrite=True.")

    # 1. Thermal-noise verification
    logger.info("Verifying thermal-noise correction status on original satellite SAFE annotations...")
    tn_status = verify_thermal_noise_correction(raw_dir)

    # 2. Input verification
    logger.info("Validating Phase 1 harmonized GeoTIFF structures...")
    input_verification = verify_aligned_inputs(june_aligned, july_aligned)

    # 3. Linear to dB conversion
    logger.info("Generating dB rasters for June 10 and July 16 (VH and VV)...")
    db_outputs = {
        "june10_vh": create_db_raster(june_aligned, 1, june_vh_db, "Sigma0_VH_dB", overwrite, block_size),
        "june10_vv": create_db_raster(june_aligned, 2, june_vv_db, "Sigma0_VV_dB", overwrite, block_size),
        "july16_vh": create_db_raster(july_aligned, 1, july_vh_db, "Sigma0_VH_dB", overwrite, block_size),
        "july16_vv": create_db_raster(july_aligned, 2, july_vv_db, "Sigma0_VV_dB", overwrite, block_size),
    }

    # 4. Statistical characterization
    logger.info("Computing radiometric statistics for all 4 channels...")
    channel_statistics = {
        "june10_vh": compute_channel_statistics(june_vh_db, june_aligned, 1, block_size),
        "june10_vv": compute_channel_statistics(june_vv_db, june_aligned, 2, block_size),
        "july16_vh": compute_channel_statistics(july_vh_db, july_aligned, 1, block_size),
        "july16_vv": compute_channel_statistics(july_vv_db, july_aligned, 2, block_size),
    }

    # 5. Histograms and CSV tables
    logger.info("Generating backscatter histograms and CSV data tables...")
    hist_results = {
        "VH": generate_histograms_and_tables(june_vh_db, july_vh_db, "VH", out_hist_dir, out_hist_data_dir),
        "VV": generate_histograms_and_tables(june_vv_db, july_vv_db, "VV", out_hist_dir, out_hist_data_dir),
    }

    # 6. Backscatter difference analysis
    logger.info("Calculating temporal backscatter differences (July 16 − June 10)...")
    diff_results = {
        "delta_vh": compute_difference_raster(june_vh_db, july_vh_db, delta_vh_db, "Delta_Sigma0_VH_dB", overwrite, block_size),
        "delta_vv": compute_difference_raster(june_vv_db, july_vv_db, delta_vv_db, "Delta_Sigma0_VV_dB", overwrite, block_size),
    }

    logger.info("Generating spatial difference maps (PNG)...")
    diff_map_pngs = {
        "delta_vh_map": generate_difference_map_png(delta_vh_db, "VH", os.path.join(out_diff_maps_dir, "delta_vh_map.png")),
        "delta_vv_map": generate_difference_map_png(delta_vv_db, "VV", os.path.join(out_diff_maps_dir, "delta_vv_map.png")),
    }

    # 7. AOI valid-data assessment
    logger.info("Evaluating valid-data coverage inside preliminary Kazipur AOI...")
    aoi_metrics = assess_aoi_valid_data(june_aligned, july_aligned, PRELIMINARY_AOI_WKT)

    duration = round(time.time() - start_time, 2)
    logger.info(f"Phase 2A pipeline completed in {duration} seconds.")

    # 8. Compile comprehensive report
    report = {
        "pipeline": "Earth Pulse Phase 2A: Radiometric Analysis & Backscatter Characterization",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_seconds": duration,
        "project_root": str(root),
        "thermal_noise_verification": tn_status,
        "input_verification": input_verification,
        "inputs": {
            "june10_aligned": {"path": june_aligned, "sha256": compute_sha256(june_aligned)},
            "july16_aligned": {"path": july_aligned, "sha256": compute_sha256(july_aligned)},
        },
        "decibel_conversion_formula": "Sigma0_dB = 10 * log10(Sigma0_linear)",
        "db_raster_outputs": {
            "june10_vh": db_outputs["june10_vh"],
            "june10_vv": db_outputs["june10_vv"],
            "july16_vh": db_outputs["july16_vh"],
            "july16_vv": db_outputs["july16_vv"],
        },
        "statistical_characterization": channel_statistics,
        "histogram_analysis": hist_results,
        "difference_analysis": {
            "formula": "Delta_dB = July16_dB - June10_dB",
            "delta_vh": diff_results["delta_vh"],
            "delta_vv": diff_results["delta_vv"],
            "difference_maps": diff_map_pngs,
        },
        "aoi_coverage_assessment": aoi_metrics,
        "scientific_limitations": [
            "Bilinear resampling on July 16 introduces minor subpixel smoothing.",
            "Speckle noise is unmitigated in this phase (filtering scheduled for Phase 2B).",
            "Backscatter difference measures radiometric surface change; it does not constitute validated flood classification.",
            "Decibel values do not follow strict Gaussian distributions due to heterogeneous land cover and surface roughness.",
            "Preliminary Kazipur AOI is illustrative and subject to hydrological boundary refinement.",
        ],
    }

    os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Saved machine-readable audit report: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Earth Pulse Phase 2A: Radiometric Analysis & Backscatter Characterization"
    )
    parser.add_argument("--project-root", type=str, help="Project root directory")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing phase 2a outputs")
    parser.add_argument("--block-size", type=int, default=512, help="Block size for windowed processing")

    args = parser.parse_args()

    try:
        report = run_phase2a_pipeline(
            project_root=Path(args.project_root) if args.project_root else None,
            overwrite=args.overwrite,
            block_size=args.block_size,
        )
        print("\n--- PHASE 2A RADIOMETRIC ANALYSIS SUMMARY ---")
        print("Status: SUCCESS")
        print(f"Thermal-noise verification: {report['thermal_noise_verification']['status']}")
        print(f"June 10 VH Mean: {report['statistical_characterization']['june10_vh']['decibel_stats']['mean_db']:.2f} dB")
        print(f"July 16 VH Mean: {report['statistical_characterization']['july16_vh']['decibel_stats']['mean_db']:.2f} dB")
        print(f"June 10 VV Mean: {report['statistical_characterization']['june10_vv']['decibel_stats']['mean_db']:.2f} dB")
        print(f"July 16 VV Mean: {report['statistical_characterization']['july16_vv']['decibel_stats']['mean_db']:.2f} dB")
        print(f"Mean Delta VV: {report['difference_analysis']['delta_vv']['statistics']['mean_db']:.2f} dB")
        print(f"Mean Delta VH: {report['difference_analysis']['delta_vh']['statistics']['mean_db']:.2f} dB")
        print(f"AOI Common Valid Cells: {report['aoi_coverage_assessment']['common_valid_aoi_cells']:,} ({report['aoi_coverage_assessment']['common_valid_aoi_pct']}%)")
        print(f"Report: data/metadata/phase2a_analysis_report.json")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Phase 2A execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
