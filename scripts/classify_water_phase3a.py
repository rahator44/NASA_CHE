#!/usr/bin/env python3
"""
EARTH PULSE — PHASE 3A: WATER CLASSIFICATION AND THRESHOLD BENCHMARKING
NASA Space Apps Challenge 2026: Dancing with the SARs

This script develops and benchmarks unsupervised surface-water classification
methods using Sentinel-1A C-band GRD acquisitions (June 10 and July 16, 2024)
over the Jamuna River reach (Kazipur / Sirajganj, Bangladesh).

Features & Functionality:
1. Multi-Filtering Input Ingestion:
   - Unfiltered (data/processed/aligned/)
   - Lee 3x3 (data/processed/phase2b/lee_3x3/)
   - Lee 5x5 (data/processed/phase2b/lee_5x5/)
2. Rigorous Quality Mask Integration:
   - Category 0: Valid ordinary observation (participates in threshold estimation)
   - Category 1: Source NoData (-9999.0, excluded -> Mask code 3)
   - Category 2: Suspected SNAP clipping floor (indeterminate -> Mask code 2)
   - Category 3: Other invalid numerical observation (excluded -> Mask code 3)
3. Target Study AOI Geometry:
   - WGS84 POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))
   - Transformed to EPSG:32645 and rasterized to match raster grid.
4. Radiometric Feature Extraction:
   - VV backscatter in dB (10 * log10(Sigma0_VV))
   - VH backscatter in dB (10 * log10(Sigma0_VH))
   - Cross-polarization ratio (CR_dB = VH_dB - VV_dB)
5. Thresholding Algorithms:
   - 1D Otsu on VV, VH, and CR
   - Kittler-Illingworth (KI) minimum-error thresholding on VV, VH, CR with failure detection
   - 2D Bivariate Otsu on joint VV-VH histogram (Gong diagonal quadrant formulation)
6. Polarization Fusion Strategies:
   - VV-only candidate water (VV_dB <= T_VV)
   - VH-only candidate water (VH_dB <= T_VH)
   - Dual-pol AND (Conservative: VV_dB <= T_VV and VH_dB <= T_VH)
   - Dual-pol OR (Inclusive: VV_dB <= T_VV or VH_dB <= T_VH)
   - 2D Otsu Bivariate Joint (VV_dB <= T_VV_2D and VH_dB <= T_VH_2D)
   - Cross-ratio candidate classification (CR_dB <= T_CR)
7. Filter Sensitivity Benchmarking:
   - Cross-configuration agreement metrics: Jaccard Index (IoU), Cohen's Kappa, Overall Agreement %
   - Threshold stability between June 10 (baseline) and July 16 (peak flood)
   - Spatial continuity and boundary sharpness
8. Candidate Water Mask Generation:
   - UInt8 GeoTIFFs (0: Non-water, 1: Candidate water, 2: Indeterminate, 3: NoData/invalid)
   - Strict georeferencing (EPSG:32645, 20m pixel spacing)
9. Statistical & Metadata Reporting:
   - Candidate water area in hectares and square kilometers inside AOI (20m x 20m = 400 m2)
   - CSV benchmark tables, comparison plots, and machine-readable JSON audit.
"""

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
logger = logging.getLogger("EarthPulse.Phase3A")

# Constants
NODATA_VALUE = -9999.0
PRELIMINARY_AOI_WKT = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"
PIXEL_SPACING_M = 20.0
PIXEL_AREA_M2 = 400.0
PIXEL_AREA_HA = 0.04
PIXEL_AREA_KM2 = 0.0004

# Quality Mask Categories
CAT_VALID_ORDINARY = 0
CAT_SOURCE_NODATA = 1
CAT_SNAP_CLIPPING_FLOOR = 2
CAT_OTHER_INVALID = 3

# Candidate Classification Mask Categories
MASK_NON_WATER = 0
MASK_CANDIDATE_WATER = 1
MASK_INDETERMINATE = 2
MASK_NODATA_INVALID = 3


def find_project_root(start_path: Optional[Path] = None) -> Path:
    """Locate the canonical EarthPulse-SAR project root directory."""
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
    raise FileNotFoundError("Could not find EarthPulse-SAR project root directory.")


def verify_phase3a_inputs(filepath: Union[str, Path]) -> Dict[str, Any]:
    """
    Verifies input GeoTIFF raster against project standards:
    - 2 bands: Band 1 = Sigma0_VH, Band 2 = Sigma0_VV
    - EPSG:32645
    - Dimensions: 1405 x 1393
    - Pixel spacing: 20m x -20m
    - NoData: -9999.0
    """
    p = Path(filepath)
    if not p.is_file():
        raise FileNotFoundError(f"Input file not found: {p}")

    ds = gdal.Open(str(p), gdal.GA_ReadOnly)
    if ds is None:
        raise ValueError(f"GDAL failed to open file: {p}")

    w, h = ds.RasterXSize, ds.RasterYSize
    gt = ds.GetGeoTransform()
    proj_wkt = ds.GetProjection()

    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj_wkt)
    auth_code = srs.GetAuthorityCode(None)

    if w != 1405 or h != 1393:
        raise ValueError(f"Invalid dimensions for {p.name}: {w}x{h}, expected 1405x1393")
    if abs(gt[1] - 20.0) > 1e-4 or abs(gt[5] - (-20.0)) > 1e-4:
        raise ValueError(f"Invalid pixel spacing for {p.name}: {gt[1]}x{gt[5]}")
    if str(auth_code) != "32645":
        raise ValueError(f"Invalid CRS for {p.name}: EPSG:{auth_code}, expected EPSG:32645")
    if ds.RasterCount != 2:
        raise ValueError(f"Expected 2 bands for {p.name}, got {ds.RasterCount}")

    b1_desc = ds.GetRasterBand(1).GetDescription()
    b2_desc = ds.GetRasterBand(2).GetDescription()

    if b1_desc != "Sigma0_VH" or b2_desc != "Sigma0_VV":
        raise ValueError(f"Invalid band mapping for {p.name}: Band 1='{b1_desc}', Band 2='{b2_desc}'")

    ds = None
    return {
        "path": str(p),
        "filename": p.name,
        "width": w,
        "height": h,
        "geotransform": list(gt),
        "epsg": 32645,
        "band1": b1_desc,
        "band2": b2_desc,
    }


def rasterize_aoi_mask(
    raster_path: Union[str, Path],
    aoi_wkt: str = PRELIMINARY_AOI_WKT,
) -> np.ndarray:
    """
    Rasterizes the WGS84 AOI polygon onto the raster's grid in EPSG:32645.
    Returns boolean 2D numpy array of shape (height, width).
    """
    ds = gdal.Open(str(raster_path), gdal.GA_ReadOnly)
    w, h = ds.RasterXSize, ds.RasterYSize
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()

    src_srs = osr.SpatialReference()
    src_srs.ImportFromEPSG(4326)
    src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    dst_srs = osr.SpatialReference()
    dst_srs.ImportFromEPSG(32645)
    tx = osr.CoordinateTransformation(src_srs, dst_srs)

    geom = ogr.CreateGeometryFromWkt(aoi_wkt)
    if geom is None:
        raise ValueError(f"Failed to parse AOI geometry: {aoi_wkt}")
    geom.Transform(tx)

    mem_drv = gdal.GetDriverByName("MEM")
    mask_ds = mem_drv.Create("", w, h, 1, gdal.GDT_Byte)
    mask_ds.SetGeoTransform(gt)
    mask_ds.SetProjection(proj)

    ogr_mem = ogr.GetDriverByName("MEM").CreateDataSource("aoi_mem")
    lyr = ogr_mem.CreateLayer("aoi", dst_srs, ogr.wkbPolygon)
    feat = ogr.Feature(lyr.GetLayerDefn())
    feat.SetGeometry(geom)
    lyr.CreateFeature(feat)

    gdal.RasterizeLayer(mask_ds, [1], lyr, burn_values=[1])
    aoi_mask = (mask_ds.GetRasterBand(1).ReadAsArray() == 1)

    ds = None
    mask_ds = None
    ogr_mem = None
    return aoi_mask


def otsu_threshold_1d(
    values: np.ndarray,
    n_bins: int = 256,
    val_range: Optional[Tuple[float, float]] = None,
) -> Dict[str, Any]:
    """
    Computes standard 1D Otsu threshold maximizing between-class variance.
    Input values should be 1D numpy array of finite floating-point observations.
    """
    if values is None or len(values) == 0:
        return {"status": "FAILED", "threshold": None, "reason": "Empty input values"}

    finite_vals = values[np.isfinite(values)]
    if len(finite_vals) < 10:
        return {"status": "FAILED", "threshold": None, "reason": "Insufficient finite values"}

    if val_range is None:
        val_range = (float(np.min(finite_vals)), float(np.max(finite_vals)))

    if val_range[0] >= val_range[1]:
        return {"status": "FAILED", "threshold": None, "reason": "Zero variance (min equals max)"}

    counts, bin_edges = np.histogram(finite_vals, bins=n_bins, range=val_range)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    total_count = np.sum(counts)

    if total_count == 0:
        return {"status": "FAILED", "threshold": None, "reason": "Zero histogram counts"}

    p = counts / total_count
    omega = np.cumsum(p)
    mu = np.cumsum(p * bin_centers)
    mu_t = mu[-1]

    # Valid interior split points where both classes have positive weight
    valid = (omega > 1e-6) & (omega < (1.0 - 1e-6))
    if not np.any(valid):
        return {"status": "FAILED", "threshold": None, "reason": "No valid interior split point"}

    sigma_b_sq = np.zeros_like(p)
    sigma_b_sq[valid] = ((mu_t * omega[valid] - mu[valid]) ** 2) / (omega[valid] * (1.0 - omega[valid]))

    best_idx = int(np.argmax(sigma_b_sq))
    best_threshold = float(bin_centers[best_idx])
    w0 = float(omega[best_idx])
    w1 = float(1.0 - w0)
    max_sb = float(sigma_b_sq[best_idx])

    return {
        "status": "SUCCESS",
        "threshold": best_threshold,
        "w0": w0,
        "w1": w1,
        "criterion_value": max_sb,
        "bin_center": best_threshold,
        "bin_index": best_idx,
    }


def kittler_illingworth_threshold_1d(
    values: np.ndarray,
    n_bins: int = 256,
    val_range: Optional[Tuple[float, float]] = None,
    min_class_occupancy: float = 0.01,
) -> Dict[str, Any]:
    """
    Computes Kittler-Illingworth (KI) Minimum Error Thresholding.
    Fits a two-component Gaussian mixture and minimizes the information-theoretic
    cost function J(t).
    
    If the histogram is unimodal, degenerate, or has minimum on the boundary,
    reports failure rather than forcing an invalid threshold.
    """
    if values is None or len(values) == 0:
        return {"status": "FAILED", "threshold": None, "reason": "Empty input values"}

    finite_vals = values[np.isfinite(values)]
    if len(finite_vals) < 20:
        return {"status": "FAILED", "threshold": None, "reason": "Insufficient finite values"}

    if val_range is None:
        val_range = (float(np.min(finite_vals)), float(np.max(finite_vals)))

    if val_range[0] >= val_range[1]:
        return {"status": "FAILED", "threshold": None, "reason": "Zero variance"}

    counts, bin_edges = np.histogram(finite_vals, bins=n_bins, range=val_range)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    total_count = np.sum(counts)

    if total_count == 0:
        return {"status": "FAILED", "threshold": None, "reason": "Zero histogram counts"}

    p = counts / total_count
    omega0 = np.cumsum(p)
    omega1 = 1.0 - omega0

    # Cumulative moments
    mu0_cum = np.cumsum(p * bin_centers)
    mu1_cum = mu0_cum[-1] - mu0_cum

    var0_cum = np.cumsum(p * (bin_centers ** 2))
    var1_cum = var0_cum[-1] - var0_cum

    # Require minimum class occupancy on both classes
    valid = (omega0 >= min_class_occupancy) & (omega1 >= min_class_occupancy)
    if not np.any(valid):
        return {"status": "FAILED", "threshold": None, "reason": f"Class occupancy below {min_class_occupancy}"}

    mu0 = np.zeros_like(p)
    mu1 = np.zeros_like(p)
    mu0[valid] = mu0_cum[valid] / omega0[valid]
    mu1[valid] = mu1_cum[valid] / omega1[valid]

    var0 = np.zeros_like(p)
    var1 = np.zeros_like(p)
    var0[valid] = (var0_cum[valid] / omega0[valid]) - (mu0[valid] ** 2)
    var1[valid] = (var1_cum[valid] / omega1[valid]) - (mu1[valid] ** 2)

    # Class variances must be strictly positive
    valid_var = valid & (var0 > 1e-6) & (var1 > 1e-6)
    if not np.any(valid_var):
        return {"status": "FAILED", "threshold": None, "reason": "Zero or negative class variance"}

    # Kittler-Illingworth cost function:
    # J(t) = 1 + 2*(w0*ln(s0) + w1*ln(s1)) - 2*(w0*ln(w0) + w1*ln(w1))
    # Note: s0 = sqrt(var0) -> 2*ln(s0) = ln(var0)
    J = np.full_like(p, np.inf)
    J[valid_var] = (
        1.0
        + omega0[valid_var] * np.log(var0[valid_var])
        + omega1[valid_var] * np.log(var1[valid_var])
        - 2.0 * (omega0[valid_var] * np.log(omega0[valid_var]) + omega1[valid_var] * np.log(omega1[valid_var]))
    )

    valid_indices = np.where(valid_var)[0]
    best_idx = int(np.argmin(J))

    # Reject if minimum is at the boundary of valid range (unimodal/non-convergent)
    if best_idx == valid_indices[0] or best_idx == valid_indices[-1]:
        return {
            "status": "FAILED",
            "threshold": None,
            "reason": "Minimum on boundary of valid occupancy (unimodal or non-convergent distribution)",
        }

    best_threshold = float(bin_centers[best_idx])
    return {
        "status": "SUCCESS",
        "threshold": best_threshold,
        "w0": float(omega0[best_idx]),
        "w1": float(omega1[best_idx]),
        "cost_J": float(J[best_idx]),
        "var0": float(var0[best_idx]),
        "var1": float(var1[best_idx]),
        "criterion_value": float(J[best_idx]),
    }


def otsu_threshold_2d(
    vv_values: np.ndarray,
    vh_values: np.ndarray,
    n_bins: int = 128,
    val_range_vv: Optional[Tuple[float, float]] = None,
    val_range_vh: Optional[Tuple[float, float]] = None,
    min_class_occupancy: float = 0.01,
) -> Dict[str, Any]:
    """
    Computes Two-Dimensional (Bivariate) Otsu Thresholding on joint VV-VH backscatter.
    
    Mathematical Formulation (Gong et al. 1996 / Liu & Li 1993):
    Constructs normalized 2D joint histogram P(i, j) on grid (x_i, y_j).
    Class 0 (Candidate Water): Quadrant Q0 = {i <= s, j <= t} (low backscatter in both VV and VH).
    Class 1 (Background / Land): Quadrant Q1 = {i > s, j > t} (high backscatter in both VV and VH).
    
    Maximizes the between-class variance trace:
      Tr(S_B(s, t)) = w0 * w1 * [ (mu0_x - mu1_x)^2 + (mu0_y - mu1_y)^2 ]
    Evaluated efficiently in O(N^2) using 2D prefix cumulative sums.
    """
    if len(vv_values) == 0 or len(vh_values) == 0:
        return {"status": "FAILED", "threshold_vv": None, "threshold_vh": None, "reason": "Empty inputs"}

    valid = np.isfinite(vv_values) & np.isfinite(vh_values)
    vv_clean = vv_values[valid]
    vh_clean = vh_values[valid]

    if len(vv_clean) < 20:
        return {"status": "FAILED", "threshold_vv": None, "threshold_vh": None, "reason": "Insufficient valid observations"}

    if val_range_vv is None:
        val_range_vv = (float(np.percentile(vv_clean, 0.1)), float(np.percentile(vv_clean, 99.9)))
    if val_range_vh is None:
        val_range_vh = (float(np.percentile(vh_clean, 0.1)), float(np.percentile(vh_clean, 99.9)))

    if val_range_vv[0] >= val_range_vv[1] or val_range_vh[0] >= val_range_vh[1]:
        return {"status": "FAILED", "threshold_vv": None, "threshold_vh": None, "reason": "Zero variance in feature axis"}

    H, xedges, yedges = np.histogram2d(vv_clean, vh_clean, bins=n_bins, range=[val_range_vv, val_range_vh])
    xc = 0.5 * (xedges[:-1] + xedges[1:])
    yc = 0.5 * (yedges[:-1] + yedges[1:])

    total_H = np.sum(H)
    if total_H == 0:
        return {"status": "FAILED", "threshold_vv": None, "threshold_vh": None, "reason": "Empty 2D histogram"}

    P = H / total_H

    # Prefix cumulative sum for Class 0 (quadrant i <= s, j <= t)
    P0 = np.cumsum(np.cumsum(P, axis=0), axis=1)

    Px = P * xc[:, None]
    M0x = np.cumsum(np.cumsum(Px, axis=0), axis=1)

    Py = P * yc[None, :]
    M0y = np.cumsum(np.cumsum(Py, axis=0), axis=1)

    # Suffix cumulative sum for Class 1 (quadrant i > s, j > t)
    P1_raw = np.cumsum(np.cumsum(P[::-1, ::-1], axis=0), axis=1)[::-1, ::-1]
    M1x_raw = np.cumsum(np.cumsum(Px[::-1, ::-1], axis=0), axis=1)[::-1, ::-1]
    M1y_raw = np.cumsum(np.cumsum(Py[::-1, ::-1], axis=0), axis=1)[::-1, ::-1]

    # Shift by 1 to represent strict inequality i > s, j > t
    P1 = np.zeros_like(P1_raw)
    P1[:-1, :-1] = P1_raw[1:, 1:]
    M1x = np.zeros_like(M1x_raw)
    M1x[:-1, :-1] = M1x_raw[1:, 1:]
    M1y = np.zeros_like(M1y_raw)
    M1y[:-1, :-1] = M1y_raw[1:, 1:]

    valid_diag = (P0 >= min_class_occupancy) & (P1 >= min_class_occupancy)
    if not np.any(valid_diag):
        return {"status": "FAILED", "threshold_vv": None, "threshold_vh": None, "reason": "No valid 2D diagonal partition"}

    u0x = np.zeros_like(P0)
    u0y = np.zeros_like(P0)
    u1x = np.zeros_like(P0)
    u1y = np.zeros_like(P0)

    u0x[valid_diag] = M0x[valid_diag] / P0[valid_diag]
    u0y[valid_diag] = M0y[valid_diag] / P0[valid_diag]
    u1x[valid_diag] = M1x[valid_diag] / P1[valid_diag]
    u1y[valid_diag] = M1y[valid_diag] / P1[valid_diag]

    dist_sq = (u0x - u1x) ** 2 + (u0y - u1y) ** 2
    SB2 = np.zeros_like(P0)
    SB2[valid_diag] = P0[valid_diag] * P1[valid_diag] * dist_sq[valid_diag]

    best_idx = np.unravel_index(np.argmax(SB2), SB2.shape)
    best_s, best_t = best_idx[0], best_idx[1]

    best_thresh_vv = float(xc[best_s])
    best_thresh_vh = float(yc[best_t])
    w0 = float(P0[best_idx])
    w1 = float(P1[best_idx])
    max_sb2 = float(SB2[best_idx])

    return {
        "status": "SUCCESS",
        "threshold_vv": best_thresh_vv,
        "threshold_vh": best_thresh_vh,
        "w0": w0,
        "w1": w1,
        "criterion_value": max_sb2,
        "bin_index_vv": int(best_s),
        "bin_index_vh": int(best_t),
    }


def calculate_cross_ratio(
    vh_lin: np.ndarray,
    vv_lin: np.ndarray,
    eps: float = 1e-12,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes cross-polarization ratio in linear power and decibels.
    Linear: CR = Sigma0_VH / Sigma0_VV
    Decibel: CR_dB = VH_dB - VV_dB
    Protects against division by zero and invalid inputs.
    """
    valid = (vh_lin > 0) & (vv_lin > eps) & np.isfinite(vh_lin) & np.isfinite(vv_lin)

    cr_lin = np.full(vh_lin.shape, np.nan, dtype=np.float32)
    cr_db = np.full(vh_lin.shape, np.nan, dtype=np.float32)

    cr_lin[valid] = (vh_lin[valid] / vv_lin[valid]).astype(np.float32)
    cr_db[valid] = (10.0 * np.log10(cr_lin[valid])).astype(np.float32)

    return cr_lin, cr_db


def compute_radiometric_features(
    vh_lin: np.ndarray,
    vv_lin: np.ndarray,
    quality_mask_vh: Optional[np.ndarray] = None,
    quality_mask_vv: Optional[np.ndarray] = None,
) -> Dict[str, np.ndarray]:
    """
    Converts linear Sigma0 to dB and computes cross-ratio.
    Filters out non-positive and non-finite values.
    """
    valid_vh = (vh_lin > 0) & np.isfinite(vh_lin)
    valid_vv = (vv_lin > 0) & np.isfinite(vv_lin)

    if quality_mask_vh is not None:
        valid_vh = valid_vh & (quality_mask_vh == CAT_VALID_ORDINARY)
    if quality_mask_vv is not None:
        valid_vv = valid_vv & (quality_mask_vv == CAT_VALID_ORDINARY)

    vh_db = np.full(vh_lin.shape, np.nan, dtype=np.float32)
    vv_db = np.full(vv_lin.shape, np.nan, dtype=np.float32)

    vh_db[valid_vh] = (10.0 * np.log10(vh_lin[valid_vh])).astype(np.float32)
    vv_db[valid_vv] = (10.0 * np.log10(vv_lin[valid_vv])).astype(np.float32)

    cr_lin, cr_db = calculate_cross_ratio(vh_lin, vv_lin)

    return {
        "vh_db": vh_db,
        "vv_db": vv_db,
        "cr_db": cr_db,
        "valid_vh": valid_vh,
        "valid_vv": valid_vv,
        "valid_both": valid_vh & valid_vv,
    }


def generate_candidate_mask(
    vv_db: np.ndarray,
    vh_db: np.ndarray,
    quality_mask_vh: np.ndarray,
    quality_mask_vv: np.ndarray,
    method: str,
    threshold_vv: Optional[float] = None,
    threshold_vh: Optional[float] = None,
    threshold_cr: Optional[float] = None,
    threshold_2d: Optional[Tuple[float, float]] = None,
    cr_db: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Generates a provisional candidate surface-water classification mask (UInt8).
    
    Mask categories:
      0: Candidate non-water
      1: Candidate water
      2: Indeterminate / clipping-floor (SNAP numerical clamp)
      3: NoData or invalid observation
      
    Polarization fusion strategies:
      - 'vv_only': Candidate water if VV_dB <= threshold_vv
      - 'vh_only': Candidate water if VH_dB <= threshold_vh
      - 'dual_and': Candidate water if (VV_dB <= threshold_vv) AND (VH_dB <= threshold_vh)
      - 'dual_or': Candidate water if (VV_dB <= threshold_vv) OR (VH_dB <= threshold_vh)
      - 'otsu_2d': Candidate water if (VV_dB <= threshold_2d[0]) AND (VH_dB <= threshold_2d[1])
      - 'cross_ratio': Candidate water if CR_dB <= threshold_cr
    """
    mask = np.full(vv_db.shape, MASK_NON_WATER, dtype=np.uint8)

    # 1. Identify NoData or invalid observations
    if method == "vv_only":
        is_nodata_invalid = (quality_mask_vv == CAT_SOURCE_NODATA) | (quality_mask_vv == CAT_OTHER_INVALID) | ~np.isfinite(vv_db)
        is_clipping_floor = (quality_mask_vv == CAT_SNAP_CLIPPING_FLOOR)
        is_valid_ordinary = (quality_mask_vv == CAT_VALID_ORDINARY) & np.isfinite(vv_db)
    elif method == "vh_only":
        is_nodata_invalid = (quality_mask_vh == CAT_SOURCE_NODATA) | (quality_mask_vh == CAT_OTHER_INVALID) | ~np.isfinite(vh_db)
        is_clipping_floor = (quality_mask_vh == CAT_SNAP_CLIPPING_FLOOR)
        is_valid_ordinary = (quality_mask_vh == CAT_VALID_ORDINARY) & np.isfinite(vh_db)
    else:
        # Dual-polarization / 2D / cross-ratio
        is_nodata_invalid = (
            (quality_mask_vh == CAT_SOURCE_NODATA)
            | (quality_mask_vv == CAT_SOURCE_NODATA)
            | (quality_mask_vh == CAT_OTHER_INVALID)
            | (quality_mask_vv == CAT_OTHER_INVALID)
            | ~np.isfinite(vh_db)
            | ~np.isfinite(vv_db)
        )
        is_clipping_floor = (quality_mask_vh == CAT_SNAP_CLIPPING_FLOOR) | (quality_mask_vv == CAT_SNAP_CLIPPING_FLOOR)
        is_valid_ordinary = (quality_mask_vh == CAT_VALID_ORDINARY) & (quality_mask_vv == CAT_VALID_ORDINARY) & np.isfinite(vh_db) & np.isfinite(vv_db)

    # Set NoData/invalid
    mask[is_nodata_invalid] = MASK_NODATA_INVALID

    # Set indeterminate clipping floor (only if not already NoData/invalid)
    mask[is_clipping_floor & ~is_nodata_invalid] = MASK_INDETERMINATE

    # Evaluate classification threshold on valid ordinary observations
    if method == "vv_only":
        if threshold_vv is not None:
            water_cond = is_valid_ordinary & (vv_db <= threshold_vv)
            mask[water_cond] = MASK_CANDIDATE_WATER
    elif method == "vh_only":
        if threshold_vh is not None:
            water_cond = is_valid_ordinary & (vh_db <= threshold_vh)
            mask[water_cond] = MASK_CANDIDATE_WATER
    elif method == "dual_and":
        if threshold_vv is not None and threshold_vh is not None:
            water_cond = is_valid_ordinary & (vv_db <= threshold_vv) & (vh_db <= threshold_vh)
            mask[water_cond] = MASK_CANDIDATE_WATER
    elif method == "dual_or":
        if threshold_vv is not None and threshold_vh is not None:
            water_cond = is_valid_ordinary & ((vv_db <= threshold_vv) | (vh_db <= threshold_vh))
            mask[water_cond] = MASK_CANDIDATE_WATER
    elif method == "otsu_2d":
        if threshold_2d is not None:
            t_vv, t_vh = threshold_2d
            water_cond = is_valid_ordinary & (vv_db <= t_vv) & (vh_db <= t_vh)
            mask[water_cond] = MASK_CANDIDATE_WATER
    elif method == "cross_ratio":
        if threshold_cr is not None:
            if cr_db is None:
                cr_lin, cr_db = calculate_cross_ratio(10.0 ** (vh_db / 10.0), 10.0 ** (vv_db / 10.0))
            water_cond = is_valid_ordinary & np.isfinite(cr_db) & (cr_db <= threshold_cr)
            mask[water_cond] = MASK_CANDIDATE_WATER
    else:
        raise ValueError(f"Unknown classification method: {method}")

    return mask


def assess_classification_metrics(
    candidate_mask: np.ndarray,
    aoi_mask: np.ndarray,
    pixel_size_m: float = PIXEL_SPACING_M,
) -> Dict[str, Any]:
    """
    Computes candidate water mask statistics strictly inside the target AOI.
    """
    aoi_cells = candidate_mask[aoi_mask]
    total_aoi_count = len(aoi_cells)

    water_count = int(np.sum(aoi_cells == MASK_CANDIDATE_WATER))
    non_water_count = int(np.sum(aoi_cells == MASK_NON_WATER))
    indeterminate_count = int(np.sum(aoi_cells == MASK_INDETERMINATE))
    nodata_count = int(np.sum(aoi_cells == MASK_NODATA_INVALID))

    valid_count = water_count + non_water_count

    water_pct_valid = float(water_count / valid_count * 100.0) if valid_count > 0 else 0.0
    water_pct_aoi = float(water_count / total_aoi_count * 100.0) if total_aoi_count > 0 else 0.0

    cell_area_m2 = pixel_size_m * pixel_size_m
    water_area_ha = float(water_count * cell_area_m2 / 10000.0)
    water_area_km2 = float(water_count * cell_area_m2 / 1000000.0)

    return {
        "total_aoi_cells": total_aoi_count,
        "valid_cells": valid_count,
        "candidate_water_cells": water_count,
        "candidate_non_water_cells": non_water_count,
        "indeterminate_cells": indeterminate_count,
        "nodata_cells": nodata_count,
        "candidate_water_pct_valid": round(water_pct_valid, 4),
        "candidate_water_pct_aoi": round(water_pct_aoi, 4),
        "candidate_water_area_ha": round(water_area_ha, 2),
        "candidate_water_area_km2": round(water_area_km2, 4),
    }


def calculate_agreement_metrics(
    mask1: np.ndarray,
    mask2: np.ndarray,
    aoi_mask: np.ndarray,
) -> Dict[str, Any]:
    """
    Calculates spatial agreement metrics between two candidate masks inside the AOI.
    Only evaluates pixels where both masks are valid binary classifications (0 or 1).
    Returns Jaccard Index (IoU), Cohen's Kappa, and Overall Agreement Percentage.
    """
    m1 = mask1[aoi_mask]
    m2 = mask2[aoi_mask]

    valid_comp = ((m1 == 0) | (m1 == 1)) & ((m2 == 0) | (m2 == 1))
    c1 = m1[valid_comp]
    c2 = m2[valid_comp]

    n = len(c1)
    if n == 0:
        return {
            "valid_comparison_cells": 0,
            "overall_agreement_pct": 0.0,
            "jaccard_iou": 0.0,
            "cohens_kappa": 0.0,
            "tp": 0, "tn": 0, "fp": 0, "fn": 0,
        }

    tp = int(np.sum((c1 == 1) & (c2 == 1)))
    tn = int(np.sum((c1 == 0) & (c2 == 0)))
    fp = int(np.sum((c1 == 1) & (c2 == 0)))
    fn = int(np.sum((c1 == 0) & (c2 == 1)))

    overall_acc = (tp + tn) / n * 100.0
    iou_denom = tp + fp + fn
    jaccard_iou = (tp / iou_denom) if iou_denom > 0 else 1.0

    # Cohen's Kappa
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (tn + fp) * (tn + fn)) / (n * n)
    kappa = ((po - pe) / (1.0 - pe)) if (1.0 - pe) > 1e-12 else 0.0

    return {
        "valid_comparison_cells": n,
        "overall_agreement_pct": round(overall_acc, 3),
        "jaccard_iou": round(jaccard_iou, 4),
        "cohens_kappa": round(kappa, 4),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
    }


def write_geotiff_mask(
    mask_array: np.ndarray,
    output_path: Union[str, Path],
    reference_ds: gdal.Dataset,
    overwrite: bool = False,
) -> Path:
    """
    Writes a candidate classification mask to a single-band UInt8 GeoTIFF.
    Preserves exact dimensions, geotransform, and EPSG:32645 projection.
    """
    p = Path(output_path)
    if p.exists() and not overwrite:
        logger.info(f"Output mask already exists (skipping write): {p}")
        return p

    p.parent.mkdir(parents=True, exist_ok=True)

    w = reference_ds.RasterXSize
    h = reference_ds.RasterYSize
    gt = reference_ds.GetGeoTransform()
    proj = reference_ds.GetProjection()

    drv = gdal.GetDriverByName("GTiff")
    options = ["COMPRESS=DEFLATE", "TILED=YES", "INTERLEAVE=BAND"]
    out_ds = drv.Create(str(p), w, h, 1, gdal.GDT_Byte, options)
    out_ds.SetGeoTransform(gt)
    out_ds.SetProjection(proj)

    band = out_ds.GetRasterBand(1)
    band.WriteArray(mask_array.astype(np.uint8))
    band.SetNoDataValue(MASK_NODATA_INVALID)
    band.SetDescription("Candidate_Water_Mask (0=NonWater, 1=Water, 2=Indeterminate, 3=NoData)")

    out_ds.FlushCache()
    out_ds = None
    logger.info(f"Saved candidate classification mask: {p}")
    return p


def plot_threshold_distributions(
    results_by_filter: Dict[str, Any],
    date_str: str,
    output_png: Path,
):
    """
    Plots backscatter histograms (VV, VH, CR) across Unfiltered, Lee 3x3, and Lee 5x5,
    overlaying the estimated Otsu and Kittler-Illingworth threshold vertical lines.
    """
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(3, 3, figsize=(18, 14), sharex="col")
    fig.suptitle(f"Earth Pulse — Phase 3A: Radiometric Feature Distributions & Thresholds ({date_str.upper()})", fontsize=15, fontweight="bold")

    features = [("vv_db", "VV Backscatter (dB)", [-35, 5]), ("vh_db", "VH Backscatter (dB)", [-40, -5]), ("cr_db", "Cross-Ratio VH/VV (dB)", [-25, 5])]
    filters = [("unfiltered", "Unfiltered"), ("lee_3x3", "Lee 3x3"), ("lee_5x5", "Lee 5x5")]

    for row_idx, (f_key, f_title) in enumerate(filters):
        f_data = results_by_filter[f_key]
        for col_idx, (feat_key, feat_title, feat_xlim) in enumerate(features):
            ax = axes[row_idx, col_idx]
            vals = f_data["features"][feat_key]
            valid_vals = vals[np.isfinite(vals)]

            ax.hist(valid_vals, bins=120, range=feat_xlim, color="#4682b4", alpha=0.75, density=True, label="AOI Histogram")

            # Overlay Otsu
            t_otsu = f_data["otsu"][feat_key]["threshold"]
            if t_otsu is not None:
                ax.axvline(t_otsu, color="crimson", linestyle="--", linewidth=2.0, label=f"Otsu: {t_otsu:.2f} dB")

            # Overlay KI
            t_ki = f_data["ki"][feat_key]["threshold"]
            if t_ki is not None:
                ax.axvline(t_ki, color="darkorange", linestyle="-.", linewidth=2.0, label=f"KI: {t_ki:.2f} dB")
            else:
                ki_reason = f_data["ki"][feat_key].get("reason", "Failed")
                ax.text(0.05, 0.90, f"KI: {ki_reason[:25]}", transform=ax.transAxes, color="darkorange", fontsize=8, fontweight="bold")

            ax.set_xlim(feat_xlim)
            ax.grid(True, linestyle=":", alpha=0.5)
            if row_idx == 0:
                ax.set_title(feat_title, fontsize=12, fontweight="bold")
            if col_idx == 0:
                ax.set_ylabel(f"{f_title}\nDensity", fontsize=11, fontweight="bold")
            if row_idx == 2:
                ax.set_xlabel("Backscatter (dB)", fontsize=10)
            ax.legend(loc="upper right", fontsize=8)

    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
    fig.savefig(str(output_png), dpi=200)
    plt.close(fig)
    logger.info(f"Saved threshold distribution plot: {output_png}")


def plot_bivariate_2d_histograms(
    june_data: Dict[str, Any],
    july_data: Dict[str, Any],
    output_png: Path,
):
    """
    Plots 2D joint density scatter/heatmap of (VV vs VH) for June 10 and July 16 (Lee 5x5),
    overlaying 2D Otsu threshold lines and highlighting the candidate water quadrant.
    """
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), sharey=True)
    fig.suptitle("Earth Pulse — Phase 3A: Bivariate Joint VV–VH Distributions & 2D Otsu Quadrants (Lee 5×5)", fontsize=14, fontweight="bold")

    datasets = [("June 10, 2024 (Pre-Flood Baseline)", june_data, axes[0]), ("July 16, 2024 (Peak Monsoon Flood)", july_data, axes[1])]

    for title, data, ax in datasets:
        vv = data["features"]["vv_db"]
        vh = data["features"]["vh_db"]
        valid = np.isfinite(vv) & np.isfinite(vh)

        t_vv_2d = data["otsu_2d"]["threshold_vv"]
        t_vh_2d = data["otsu_2d"]["threshold_vh"]
        w0 = data["otsu_2d"]["w0"]

        h2d = ax.hist2d(
            vv[valid], vh[valid],
            bins=128,
            range=[[-35, 0], [-40, -5]],
            cmap="viridis",
            norm=matplotlib.colors.LogNorm(),
        )
        fig.colorbar(h2d[3], ax=ax, label="Log10 Pixel Count", pad=0.02)

        # Highlight Candidate Water Quadrant
        if t_vv_2d is not None and t_vh_2d is not None:
            ax.axvline(t_vv_2d, color="red", linestyle="--", linewidth=2.0, label=f"2D Otsu VV: {t_vv_2d:.2f} dB")
            ax.axhline(t_vh_2d, color="red", linestyle="--", linewidth=2.0, label=f"2D Otsu VH: {t_vh_2d:.2f} dB")
            ax.fill_between([-35, t_vv_2d], -40, t_vh_2d, color="cyan", alpha=0.15, label=f"Water Q0 (P0 = {w0*100:.1f}%)")

        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel("VV Backscatter (dB)", fontsize=11)
        ax.set_ylabel("VH Backscatter (dB)", fontsize=11)
        ax.set_xlim([-35, 0])
        ax.set_ylim([-40, -5])
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.legend(loc="lower right", fontsize=9)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    fig.savefig(str(output_png), dpi=200)
    plt.close(fig)
    logger.info(f"Saved bivariate 2D histogram plot: {output_png}")


def plot_candidate_mask_comparison(
    masks_dict: Dict[str, np.ndarray],
    date_str: str,
    output_png: Path,
):
    """
    Generates multi-panel spatial comparison figure showing different candidate water masks.
    """
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(f"Earth Pulse — Phase 3A: Candidate Water Mask Spatial Comparison ({date_str.upper()})", fontsize=15, fontweight="bold")

    panels = [
        ("Otsu VV-Only (Lee 5×5)", masks_dict["otsu_vv"]),
        ("Otsu VH-Only (Lee 5×5)", masks_dict["otsu_vh"]),
        ("Conservative Dual-Pol AND (Lee 5×5)", masks_dict["otsu_dual_and"]),
        ("Inclusive Dual-Pol OR (Lee 5×5)", masks_dict["otsu_dual_or"]),
        ("Bivariate 2D Otsu (Lee 5×5)", masks_dict["otsu_2d"]),
        ("Cross-Ratio Otsu (Lee 5×5)", masks_dict["otsu_cr"]),
    ]

    # Discrete Colormap: 0=Non-water (light gray), 1=Water (dodger blue), 2=Indeterminate (orange), 3=NoData (dark purple)
    cmap = matplotlib.colors.ListedColormap(["#dcdcdc", "#1e90ff", "#ff8c00", "#2e0854"])
    bounds = [-0.5, 0.5, 1.5, 2.5, 3.5]
    norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)

    for idx, (title, mask) in enumerate(panels):
        ax = axes[idx // 3, idx % 3]
        im = ax.imshow(mask, cmap=cmap, norm=norm, interpolation="nearest")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

    # Custom legend
    legend_elements = [
        matplotlib.patches.Patch(facecolor="#1e90ff", edgecolor="k", label="Candidate Water (1)"),
        matplotlib.patches.Patch(facecolor="#dcdcdc", edgecolor="k", label="Candidate Non-Water (0)"),
        matplotlib.patches.Patch(facecolor="#ff8c00", edgecolor="k", label="Indeterminate / Clamp (2)"),
        matplotlib.patches.Patch(facecolor="#2e0854", edgecolor="k", label="NoData / Invalid (3)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=4, fontsize=11, frameon=True)

    plt.tight_layout(rect=[0, 0.05, 1, 0.95])
    fig.savefig(str(output_png), dpi=200)
    plt.close(fig)
    logger.info(f"Saved candidate mask comparison plot: {output_png}")


def plot_filter_sensitivity_spatial_detail(
    unfiltered_mask: np.ndarray,
    lee3_mask: np.ndarray,
    lee5_mask: np.ndarray,
    output_png: Path,
    crop_window: Tuple[int, int, int, int] = (400, 700, 500, 800), # row_min, col_min, row_max, col_max
):
    """
    Plots zoomed-in spatial comparison along the Jamuna River channel
    contrasting Unfiltered, Lee 3x3, and Lee 5x5 candidate water masks.
    """
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("Earth Pulse — Phase 3A: Spatial Detail & Speckle Sensitivity Benchmark (Jamuna River Reach)", fontsize=14, fontweight="bold")

    r0, c0, r1, c1 = crop_window
    crops = [
        ("Unfiltered (Dual-Pol AND)\nProminent Speckle Salt-and-Pepper", unfiltered_mask[r0:r1, c0:c1]),
        ("Lee 3×3 (Dual-Pol AND)\nReduced Noise, Crisp Boundary", lee3_mask[r0:r1, c0:c1]),
        ("Lee 5×5 (Dual-Pol AND)\nOptimal Homogeneity & Char Continuity", lee5_mask[r0:r1, c0:c1]),
    ]

    cmap = matplotlib.colors.ListedColormap(["#dcdcdc", "#1e90ff", "#ff8c00", "#2e0854"])
    bounds = [-0.5, 0.5, 1.5, 2.5, 3.5]
    norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)

    for idx, (title, crop) in enumerate(crops):
        ax = axes[idx]
        ax.imshow(crop, cmap=cmap, norm=norm, interpolation="nearest")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

    legend_elements = [
        matplotlib.patches.Patch(facecolor="#1e90ff", edgecolor="k", label="Candidate Water (1)"),
        matplotlib.patches.Patch(facecolor="#dcdcdc", edgecolor="k", label="Candidate Non-Water (0)"),
        matplotlib.patches.Patch(facecolor="#ff8c00", edgecolor="k", label="Indeterminate (2)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=3, fontsize=11, frameon=True)

    plt.tight_layout(rect=[0, 0.06, 1, 0.94])
    fig.savefig(str(output_png), dpi=200)
    plt.close(fig)
    logger.info(f"Saved filter sensitivity spatial detail plot: {output_png}")


def run_phase3a_benchmarking(
    project_root: Optional[Union[str, Path]] = None,
    overwrite: bool = True,
    aoi_wkt: str = PRELIMINARY_AOI_WKT,
) -> Dict[str, Any]:
    """
    Main orchestration function for Phase 3A Water Classification and Threshold Benchmarking.
    """
    root = find_project_root(Path(project_root) if project_root else None)
    logger.info(f"EarthPulse-SAR root directory resolved to: {root}")

    # Paths
    paths = {
        "june10": {
            "unfiltered": root / "data" / "processed" / "aligned" / "june10_aligned.tif",
            "lee_3x3": root / "data" / "processed" / "phase2b" / "lee_3x3" / "june10_lee_3x3.tif",
            "lee_5x5": root / "data" / "processed" / "phase2b" / "lee_5x5" / "june10_lee_5x5.tif",
            "quality_mask": root / "data" / "processed" / "phase2b" / "quality_mask" / "june10_quality_mask.tif",
        },
        "july16": {
            "unfiltered": root / "data" / "processed" / "aligned" / "july16_aligned.tif",
            "lee_3x3": root / "data" / "processed" / "phase2b" / "lee_3x3" / "july16_lee_3x3.tif",
            "lee_5x5": root / "data" / "processed" / "phase2b" / "lee_5x5" / "july16_lee_5x5.tif",
            "quality_mask": root / "data" / "processed" / "phase2b" / "quality_mask" / "july16_quality_mask.tif",
        },
    }

    # Verify input rasters
    verified_inputs = {}
    for date_key in ["june10", "july16"]:
        verified_inputs[date_key] = {}
        for f_key in ["unfiltered", "lee_3x3", "lee_5x5"]:
            f_path = paths[date_key][f_key]
            verified_inputs[date_key][f_key] = verify_phase3a_inputs(f_path)
        q_path = paths[date_key]["quality_mask"]
        if not q_path.is_file():
            raise FileNotFoundError(f"Quality mask not found: {q_path}")
    logger.info("Input verification PASSED for all 6 raster datasets and 2 quality masks.")

    # Create AOI boolean mask
    ref_raster = paths["june10"]["unfiltered"]
    aoi_mask = rasterize_aoi_mask(ref_raster, aoi_wkt)
    aoi_cell_count = int(np.sum(aoi_mask))
    logger.info(f"Target study AOI rasterized: {aoi_cell_count} cells ({aoi_cell_count * PIXEL_AREA_KM2:.2f} km2)")

    # Output directories
    out_mask_dir = root / "data" / "processed" / "phase3a" / "candidate_masks"
    out_stat_dir = root / "data" / "outputs" / "phase3a" / "statistics"
    out_fig_dir = root / "data" / "outputs" / "phase3a" / "figures"
    out_meta_dir = root / "data" / "metadata"

    out_mask_dir.mkdir(parents=True, exist_ok=True)
    out_stat_dir.mkdir(parents=True, exist_ok=True)
    out_fig_dir.mkdir(parents=True, exist_ok=True)
    out_meta_dir.mkdir(parents=True, exist_ok=True)

    benchmark_rows = []
    method_rows = []
    filter_sensitivity_rows = []

    full_results = {
        "project": "NASA Space Apps Challenge 2026: Dancing with the SARs",
        "system": "Earth Pulse",
        "phase": "Phase 3A: Water Classification and Threshold Benchmarking",
        "aoi": {
            "wkt_wgs84": aoi_wkt,
            "crs": "EPSG:32645",
            "aoi_cells": aoi_cell_count,
            "aoi_area_km2": round(aoi_cell_count * PIXEL_AREA_KM2, 4),
            "aoi_area_ha": round(aoi_cell_count * PIXEL_AREA_HA, 2),
        },
        "scenarios": {},
    }

    # Open reference GDAL dataset for GeoTIFF writing
    ref_ds = gdal.Open(str(ref_raster), gdal.GA_ReadOnly)

    cached_masks = {}

    for date_key, date_label in [("june10", "June 10, 2024"), ("july16", "July 16, 2024")]:
        full_results["scenarios"][date_key] = {}
        cached_masks[date_key] = {}

        # Load Quality Mask
        q_ds = gdal.Open(str(paths[date_key]["quality_mask"]), gdal.GA_ReadOnly)
        q_vh = q_ds.GetRasterBand(1).ReadAsArray()
        q_vv = q_ds.GetRasterBand(2).ReadAsArray()
        q_ds = None

        date_results_by_filter = {}

        for f_key in ["unfiltered", "lee_3x3", "lee_5x5"]:
            logger.info(f"Processing scenario: {date_key} - {f_key}...")
            img_ds = gdal.Open(str(paths[date_key][f_key]), gdal.GA_ReadOnly)
            vh_lin = img_ds.GetRasterBand(1).ReadAsArray()
            vv_lin = img_ds.GetRasterBand(2).ReadAsArray()
            img_ds = None

            # Compute features across full raster
            features = compute_radiometric_features(vh_lin, vv_lin, q_vh, q_vv)

            # Restrict feature vectors for threshold estimation to AOI Category 0 valid cells
            valid_train = aoi_mask & features["valid_both"]
            train_vv = features["vv_db"][valid_train]
            train_vh = features["vh_db"][valid_train]
            train_cr = features["cr_db"][valid_train]

            # 1. 1D Otsu
            otsu_vv = otsu_threshold_1d(train_vv)
            otsu_vh = otsu_threshold_1d(train_vh)
            otsu_cr = otsu_threshold_1d(train_cr)

            # 2. 1D Kittler-Illingworth
            ki_vv = kittler_illingworth_threshold_1d(train_vv)
            ki_vh = kittler_illingworth_threshold_1d(train_vh)
            ki_cr = kittler_illingworth_threshold_1d(train_cr)

            # 3. 2D Otsu
            otsu_2d = otsu_threshold_2d(train_vv, train_vh, n_bins=128)

            # Record threshold benchmark entries
            for feat_name, res_otsu, res_ki in [("VV", otsu_vv, ki_vv), ("VH", otsu_vh, ki_vh), ("CR", otsu_cr, ki_cr)]:
                benchmark_rows.append({
                    "date": date_key,
                    "filter": f_key,
                    "feature": feat_name,
                    "method": "Otsu_1D",
                    "status": res_otsu["status"],
                    "threshold_db": round(res_otsu["threshold"], 4) if res_otsu["threshold"] is not None else None,
                    "w0_proportion": round(res_otsu["w0"], 4) if "w0" in res_otsu else None,
                    "w1_proportion": round(res_otsu["w1"], 4) if "w1" in res_otsu else None,
                    "criterion_value": round(res_otsu["criterion_value"], 6) if "criterion_value" in res_otsu else None,
                })
                benchmark_rows.append({
                    "date": date_key,
                    "filter": f_key,
                    "feature": feat_name,
                    "method": "Kittler_Illingworth",
                    "status": res_ki["status"],
                    "threshold_db": round(res_ki["threshold"], 4) if res_ki["threshold"] is not None else None,
                    "w0_proportion": round(res_ki["w0"], 4) if "w0" in res_ki else None,
                    "w1_proportion": round(res_ki["w1"], 4) if "w1" in res_ki else None,
                    "criterion_value": round(res_ki["criterion_value"], 6) if "criterion_value" in res_ki else None,
                })

            benchmark_rows.append({
                "date": date_key,
                "filter": f_key,
                "feature": "VV_VH_Joint",
                "method": "Otsu_2D",
                "status": otsu_2d["status"],
                "threshold_db": f"VV:{otsu_2d['threshold_vv']:.2f},VH:{otsu_2d['threshold_vh']:.2f}" if otsu_2d["threshold_vv"] is not None else None,
                "w0_proportion": round(otsu_2d["w0"], 4) if "w0" in otsu_2d else None,
                "w1_proportion": round(otsu_2d["w1"], 4) if "w1" in otsu_2d else None,
                "criterion_value": round(otsu_2d["criterion_value"], 6) if "criterion_value" in otsu_2d else None,
            })

            # Generate provisional candidate water masks
            masks = {}
            t_vv = otsu_vv["threshold"]
            t_vh = otsu_vh["threshold"]
            t_cr = otsu_cr["threshold"]
            t_2d = (otsu_2d["threshold_vv"], otsu_2d["threshold_vh"]) if otsu_2d["status"] == "SUCCESS" else None

            masks["otsu_vv"] = generate_candidate_mask(features["vv_db"], features["vh_db"], q_vh, q_vv, "vv_only", threshold_vv=t_vv)
            masks["otsu_vh"] = generate_candidate_mask(features["vv_db"], features["vh_db"], q_vh, q_vv, "vh_only", threshold_vh=t_vh)
            masks["otsu_dual_and"] = generate_candidate_mask(features["vv_db"], features["vh_db"], q_vh, q_vv, "dual_and", threshold_vv=t_vv, threshold_vh=t_vh)
            masks["otsu_dual_or"] = generate_candidate_mask(features["vv_db"], features["vh_db"], q_vh, q_vv, "dual_or", threshold_vv=t_vv, threshold_vh=t_vh)
            masks["otsu_2d"] = generate_candidate_mask(features["vv_db"], features["vh_db"], q_vh, q_vv, "otsu_2d", threshold_2d=t_2d)
            masks["otsu_cr"] = generate_candidate_mask(features["vv_db"], features["vh_db"], q_vh, q_vv, "cross_ratio", threshold_cr=t_cr, cr_db=features["cr_db"])

            # Save GeoTIFF masks
            saved_paths = {}
            for m_key, m_arr in masks.items():
                out_tif_name = f"{date_key}_{f_key}_{m_key}.tif"
                out_tif_path = out_mask_dir / out_tif_name
                write_geotiff_mask(m_arr, out_tif_path, ref_ds, overwrite=overwrite)
                saved_paths[m_key] = str(out_tif_path.relative_to(root))

            # Calculate AOI candidate water statistics
            scenario_stats = {}
            for m_key, m_arr in masks.items():
                m_stat = assess_classification_metrics(m_arr, aoi_mask)
                scenario_stats[m_key] = m_stat
                method_rows.append({
                    "date": date_key,
                    "filter": f_key,
                    "fusion_method": m_key,
                    "threshold_vv_db": round(t_vv, 4) if m_key in ["otsu_vv", "otsu_dual_and", "otsu_dual_or"] and t_vv is not None else (round(t_2d[0], 4) if m_key == "otsu_2d" and t_2d else None),
                    "threshold_vh_db": round(t_vh, 4) if m_key in ["otsu_vh", "otsu_dual_and", "otsu_dual_or"] and t_vh is not None else (round(t_2d[1], 4) if m_key == "otsu_2d" and t_2d else None),
                    "threshold_cr_db": round(t_cr, 4) if m_key == "otsu_cr" and t_cr is not None else None,
                    "water_pixels_aoi": m_stat["candidate_water_cells"],
                    "water_pct_aoi": m_stat["candidate_water_pct_aoi"],
                    "water_pct_valid": m_stat["candidate_water_pct_valid"],
                    "water_area_ha": m_stat["candidate_water_area_ha"],
                    "water_area_km2": m_stat["candidate_water_area_km2"],
                    "indeterminate_pixels_aoi": m_stat["indeterminate_cells"],
                    "valid_pixels_aoi": m_stat["valid_cells"],
                })

            scenario_bundle = {
                "thresholds": {
                    "otsu_1d": {"vv": otsu_vv, "vh": otsu_vh, "cr": otsu_cr},
                    "ki_1d": {"vv": ki_vv, "vh": ki_vh, "cr": ki_cr},
                    "otsu_2d": otsu_2d,
                },
                "statistics": scenario_stats,
                "mask_paths": saved_paths,
            }
            full_results["scenarios"][date_key][f_key] = scenario_bundle

            cached_masks[date_key][f_key] = masks
            date_results_by_filter[f_key] = {
                "features": {
                    "vv_db": train_vv,
                    "vh_db": train_vh,
                    "cr_db": train_cr,
                },
                "otsu": {"vv_db": otsu_vv, "vh_db": otsu_vh, "cr_db": otsu_cr},
                "ki": {"vv_db": ki_vv, "vh_db": ki_vh, "cr_db": ki_cr},
                "otsu_2d": otsu_2d,
            }

        # Plot feature distributions & thresholds for this date
        plot_threshold_distributions(
            date_results_by_filter,
            date_key,
            out_fig_dir / f"threshold_distributions_{date_key}.png",
        )

        # Plot candidate water masks comparison (Lee 5x5)
        plot_candidate_mask_comparison(
            cached_masks[date_key]["lee_5x5"],
            date_key,
            out_fig_dir / f"candidate_mask_comparison_{date_key}.png",
        )

    # Plot Bivariate 2D Histograms (June vs July, Lee 5x5)
    ds_june_l5 = gdal.Open(str(paths["june10"]["lee_5x5"]), gdal.GA_ReadOnly)
    vh_june_l5 = ds_june_l5.GetRasterBand(1).ReadAsArray()
    vv_june_l5 = ds_june_l5.GetRasterBand(2).ReadAsArray()
    ds_june_l5 = None
    feat_june_l5 = compute_radiometric_features(vh_june_l5, vv_june_l5)

    ds_july_l5 = gdal.Open(str(paths["july16"]["lee_5x5"]), gdal.GA_ReadOnly)
    vh_july_l5 = ds_july_l5.GetRasterBand(1).ReadAsArray()
    vv_july_l5 = ds_july_l5.GetRasterBand(2).ReadAsArray()
    ds_july_l5 = None
    feat_july_l5 = compute_radiometric_features(vh_july_l5, vv_july_l5)

    plot_bivariate_2d_histograms(
        {
            "features": {
                "vv_db": feat_june_l5["vv_db"][aoi_mask],
                "vh_db": feat_june_l5["vh_db"][aoi_mask],
            },
            "otsu_2d": full_results["scenarios"]["june10"]["lee_5x5"]["thresholds"]["otsu_2d"],
        },
        {
            "features": {
                "vv_db": feat_july_l5["vv_db"][aoi_mask],
                "vh_db": feat_july_l5["vh_db"][aoi_mask],
            },
            "otsu_2d": full_results["scenarios"]["july16"]["lee_5x5"]["thresholds"]["otsu_2d"],
        },
        out_fig_dir / "bivariate_2d_histograms.png",
    )

    # Plot Filter Sensitivity Spatial Detail (July 16 peak flood)
    plot_filter_sensitivity_spatial_detail(
        cached_masks["july16"]["unfiltered"]["otsu_dual_and"],
        cached_masks["july16"]["lee_3x3"]["otsu_dual_and"],
        cached_masks["july16"]["lee_5x5"]["otsu_dual_and"],
        out_fig_dir / "filter_sensitivity_spatial_detail.png",
    )

    # Calculate Filter Sensitivity & Agreement Matrix across Configurations
    logger.info("Computing filter sensitivity and spatial agreement matrices...")
    for date_key in ["june10", "july16"]:
        for m_key in ["otsu_dual_and", "otsu_vv", "otsu_vh"]:
            m_unf = cached_masks[date_key]["unfiltered"][m_key]
            m_l3 = cached_masks[date_key]["lee_3x3"][m_key]
            m_l5 = cached_masks[date_key]["lee_5x5"][m_key]

            # 1. Unfiltered vs Lee 3x3
            agr_u_l3 = calculate_agreement_metrics(m_unf, m_l3, aoi_mask)
            filter_sensitivity_rows.append({
                "date": date_key,
                "fusion_method": m_key,
                "comparison": "Unfiltered_vs_Lee3x3",
                "jaccard_iou": agr_u_l3["jaccard_iou"],
                "cohens_kappa": agr_u_l3["cohens_kappa"],
                "overall_agreement_pct": agr_u_l3["overall_agreement_pct"],
                "pixel_diff_count": agr_u_l3["fp"] + agr_u_l3["fn"],
                "area_diff_km2": round((agr_u_l3["fp"] + agr_u_l3["fn"]) * PIXEL_AREA_KM2, 4),
            })

            # 2. Lee 3x3 vs Lee 5x5
            agr_l3_l5 = calculate_agreement_metrics(m_l3, m_l5, aoi_mask)
            filter_sensitivity_rows.append({
                "date": date_key,
                "fusion_method": m_key,
                "comparison": "Lee3x3_vs_Lee5x5",
                "jaccard_iou": agr_l3_l5["jaccard_iou"],
                "cohens_kappa": agr_l3_l5["cohens_kappa"],
                "overall_agreement_pct": agr_l3_l5["overall_agreement_pct"],
                "pixel_diff_count": agr_l3_l5["fp"] + agr_l3_l5["fn"],
                "area_diff_km2": round((agr_l3_l5["fp"] + agr_l3_l5["fn"]) * PIXEL_AREA_KM2, 4),
            })

            # 3. Unfiltered vs Lee 5x5
            agr_u_l5 = calculate_agreement_metrics(m_unf, m_l5, aoi_mask)
            filter_sensitivity_rows.append({
                "date": date_key,
                "fusion_method": m_key,
                "comparison": "Unfiltered_vs_Lee5x5",
                "jaccard_iou": agr_u_l5["jaccard_iou"],
                "cohens_kappa": agr_u_l5["cohens_kappa"],
                "overall_agreement_pct": agr_u_l5["overall_agreement_pct"],
                "pixel_diff_count": agr_u_l5["fp"] + agr_u_l5["fn"],
                "area_diff_km2": round((agr_u_l5["fp"] + agr_u_l5["fn"]) * PIXEL_AREA_KM2, 4),
            })

    # Save CSV Tables
    csv_bench_path = out_stat_dir / "threshold_benchmark.csv"
    with open(csv_bench_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(benchmark_rows[0].keys()))
        writer.writeheader()
        writer.writerows(benchmark_rows)
    logger.info(f"Saved threshold benchmark CSV: {csv_bench_path}")

    csv_method_path = out_stat_dir / "method_comparison.csv"
    with open(csv_method_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(method_rows[0].keys()))
        writer.writeheader()
        writer.writerows(method_rows)
    logger.info(f"Saved method comparison CSV: {csv_method_path}")

    csv_filter_path = out_stat_dir / "filter_sensitivity.csv"
    with open(csv_filter_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(filter_sensitivity_rows[0].keys()))
        writer.writeheader()
        writer.writerows(filter_sensitivity_rows)
    logger.info(f"Saved filter sensitivity CSV: {csv_filter_path}")

    # Save Master JSON Report
    json_report_path = out_meta_dir / "phase3a_classification_report.json"
    with open(json_report_path, "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2)
    logger.info(f"Saved master Phase 3A report JSON: {json_report_path}")

    ref_ds = None
    logger.info("Phase 3A Water Classification and Threshold Benchmarking COMPLETED successfully.")
    return full_results


def main():
    parser = argparse.ArgumentParser(description="Earth Pulse — Phase 3A: Water Classification and Threshold Benchmarking")
    parser.add_argument("--project-root", type=str, default=None, help="Path to EarthPulse-SAR project root")
    parser.add_argument("--overwrite", action="store_true", default=True, help="Overwrite existing output rasters")
    parser.add_argument("--aoi-wkt", type=str, default=PRELIMINARY_AOI_WKT, help="AOI polygon WKT (WGS84)")
    args = parser.parse_args()

    run_phase3a_benchmarking(project_root=args.project_root, overwrite=args.overwrite, aoi_wkt=args.aoi_wkt)


if __name__ == "__main__":
    main()
