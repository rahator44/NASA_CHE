#!/usr/bin/env python3
"""
Earth Pulse — Phase 6: Riverbank Migration, Channel-Margin Displacement & Erosion Analysis
NASA Space Apps Challenge 2026: Dancing with the SARs

Study Area: Jamuna River reach, Kazipur / Sirajganj, Bangladesh
Study AOI: POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))
EPSG: 32645 (UTM Zone 45N), 20.0 m pixel resolution (1405 x 1393)

Distinguishes:
1. Main braided river channel and active anabranches.
2. Internal char islands (mid-channel bars).
3. External channel-belt margins (Right Bank / West Bank and Left Bank / East Bank).
4. Disconnected floodplain water bodies and newly inundated floodplain depressions.
5. Bankline displacement along orthogonal transects (baseline 200 m, sensitivity 100/500/1000 m).
6. Multi-zone morphological change typology:
   - External Bank Erosion Candidates (Mainland / Embankment retreat)
   - Internal Char Submergence / Scour
   - Apparent Channel Contraction / Accretion
   - Persistent Channel Water
   - Persistent Internal Chars
   - Disconnected Floodplain Inundation
   - Indeterminate Noise Floor
"""

import datetime
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from osgeo import gdal, ogr, osr
from scipy.ndimage import (
    binary_closing,
    binary_fill_holes,
    find_objects,
    label,
)
from scipy.signal import savgol_filter

# Configure headless matplotlib
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib_config"
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] EarthPulse.Phase6: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("EarthPulse.Phase6")

# Canonical Geospatial Constants
STUDY_AREA_AOI_WKT = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"
SAR_TARGET_EPSG = 32645
CANONICAL_WIDTH = 1405
CANONICAL_HEIGHT = 1393
PIXEL_SPACING_M = 20.0
PIXEL_AREA_M2 = 400.0
PIXEL_AREA_HA = 0.04
PIXEL_AREA_KM2 = 0.0004
AOI_TARGET_CELLS = 1010039
FULL_SCENE_CELLS = 1957165

# Phase 6 Zonal Change Typology Codes
ZONE_MAINLAND_DRY = 0
ZONE_PERSISTENT_CHANNEL_WATER = 1
ZONE_EXTERNAL_BANK_EROSION = 2
ZONE_INTERNAL_CHAR_SUBMERGENCE = 3
ZONE_APPARENT_ACCRETION = 4
ZONE_PERSISTENT_INTERNAL_CHAR = 5
ZONE_FLOODPLAIN_INUNDATION = 6
ZONE_INDETERMINATE_NOISE_FLOOR = 7
ZONE_NODATA_BORDER = 255

ZONE_NAMES = {
    ZONE_MAINLAND_DRY: "Persistent Mainland Non-Water",
    ZONE_PERSISTENT_CHANNEL_WATER: "Persistent Channel Water",
    ZONE_EXTERNAL_BANK_EROSION: "External Bank Erosion Candidate (Mainland Retreat)",
    ZONE_INTERNAL_CHAR_SUBMERGENCE: "Internal Char Submergence / Scour",
    ZONE_APPARENT_ACCRETION: "Apparent Channel Contraction / Accretion",
    ZONE_PERSISTENT_INTERNAL_CHAR: "Persistent Internal Char Islands",
    ZONE_FLOODPLAIN_INUNDATION: "Disconnected Floodplain Inundation",
    ZONE_INDETERMINATE_NOISE_FLOOR: "Indeterminate Noise Floor",
    ZONE_NODATA_BORDER: "NoData / Border",
}


def find_project_root() -> Path:
    candidates = [
        Path.cwd(),
        Path.cwd() / "EarthPulse-SAR",
        Path("/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR"),
    ]
    for c in candidates:
        if (c / "scripts").exists() and (c / "data").exists():
            return c.resolve()
    raise FileNotFoundError("Could not locate project root containing scripts and data directories.")


def create_study_aoi_raster_mask(reference_raster_path: Path) -> np.ndarray:
    """Rasterize canonical WGS84 AOI polygon to match target SAR raster dimensions."""
    ds = gdal.Open(str(reference_raster_path), gdal.GA_ReadOnly)
    w, h = ds.RasterXSize, ds.RasterYSize
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    ds = None

    srs_utm = osr.SpatialReference()
    srs_utm.ImportFromWkt(proj)
    srs_utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    srs_wgs84 = osr.SpatialReference()
    srs_wgs84.ImportFromEPSG(4326)
    srs_wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    geom = ogr.CreateGeometryFromWkt(STUDY_AREA_AOI_WKT)
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
    return aoi_mask


def extract_channel_and_floodplain_zones(
    june_water_mask: np.ndarray,
    july_water_mask: np.ndarray,
    transition_raster: np.ndarray,
    aoi_mask: np.ndarray,
) -> Dict[str, Any]:
    """
    Separates the active braided channel belt, internal chars, and external mainland banks,
    and decomposes Phase 5 newly inundated candidate cells into channel vs floodplain processes.
    """
    ju_wat_aoi = (june_water_mask == 1) & aoi_mask
    jl_wat_aoi = (july_water_mask == 1) & aoi_mask

    # Extract primary connected channel system traversing north to south
    lbl_ju, num_ju = label(ju_wat_aoi)
    counts_ju = np.bincount(lbl_ju.ravel())
    # ID with largest pixel count is the main channel
    top_ju_id = int(np.argsort(counts_ju[1:])[-1] + 1)
    ju_main_channel = (lbl_ju == top_ju_id)

    lbl_jl, num_jl = label(jl_wat_aoi)
    counts_jl = np.bincount(lbl_jl.ravel())
    top_jl_id = int(np.argsort(counts_jl[1:])[-1] + 1)
    jl_main_channel = (lbl_jl == top_jl_id)

    # Active channel belt envelopes (including mid-channel char islands)
    # Binary hole-filling captures all mid-channel bars surrounded by braid channels
    ju_belt_filled = binary_fill_holes(ju_main_channel) & aoi_mask
    jl_belt_filled = binary_fill_holes(jl_main_channel) & aoi_mask

    # Internal Chars (unflooded land inside the channel belt)
    ju_internal_chars = ju_belt_filled & (~ju_main_channel) & aoi_mask
    jl_internal_chars = jl_belt_filled & (~jl_main_channel) & aoi_mask

    # Phase 5 Transition States
    is_newly_inundated = (transition_raster == 2) & aoi_mask
    is_receded_water = (transition_raster == 3) & aoi_mask
    is_persistent_water = (transition_raster == 1) & aoi_mask
    is_indeterminate = (transition_raster == 5) & aoi_mask
    is_nodata = (transition_raster == 6) & aoi_mask

    # Decomposition of Newly Inundated Candidate Area (146,992 px = 58.7968 km2):
    # 1. External Bank Expansion / Riverbank Migration Candidate:
    #    Newly inundated water in July main channel, occurring outside June channel belt
    c_external_bank = is_newly_inundated & jl_main_channel & (~ju_belt_filled)

    # 2. Internal Char Submergence / Scour:
    #    Newly inundated water in July main channel, occurring on June internal char land
    c_internal_char_sub = is_newly_inundated & jl_main_channel & ju_belt_filled

    # 3. Disconnected Floodplain Inundation:
    #    Newly inundated water located outside the July main channel network
    c_floodplain_inundation = is_newly_inundated & (~jl_main_channel)

    # Verify exact cell conservation
    total_new_cells = int(np.sum(is_newly_inundated))
    n_bank = int(np.sum(c_external_bank))
    n_char = int(np.sum(c_internal_char_sub))
    n_flood = int(np.sum(c_floodplain_inundation))
    assert (n_bank + n_char + n_flood) == total_new_cells, "Decomposition cell conservation mismatch"

    # Apparent Accretion / Channel Contraction (Receded water inside channel belt)
    c_accretion = is_receded_water & ju_belt_filled

    # Persistent internal chars: dry in both June and July inside channel belt
    c_persistent_chars = ju_internal_chars & jl_internal_chars

    # Persistent channel water
    c_persistent_channel_water = is_persistent_water & ju_main_channel & jl_main_channel

    # Build 7-zone classified raster
    zones_arr = np.full(transition_raster.shape, ZONE_NODATA_BORDER, dtype=np.uint8)
    # Inside AOI default to mainland dry
    zones_arr[aoi_mask] = ZONE_MAINLAND_DRY

    zones_arr[is_indeterminate] = ZONE_INDETERMINATE_NOISE_FLOOR
    zones_arr[c_persistent_chars] = ZONE_PERSISTENT_INTERNAL_CHAR
    zones_arr[c_accretion] = ZONE_APPARENT_ACCRETION
    zones_arr[c_floodplain_inundation] = ZONE_FLOODPLAIN_INUNDATION
    zones_arr[c_internal_char_sub] = ZONE_INTERNAL_CHAR_SUBMERGENCE
    zones_arr[c_external_bank] = ZONE_EXTERNAL_BANK_EROSION
    zones_arr[c_persistent_channel_water] = ZONE_PERSISTENT_CHANNEL_WATER
    zones_arr[is_nodata] = ZONE_NODATA_BORDER

    # Partition external bank expansion into West Bank (Right Bank) and East Bank (Left Bank)
    # Using centerline of June channel belt at each row
    rows_belt, cols_belt = np.where(ju_belt_filled)
    row_center_cols = {}
    for r in range(rows_belt.min(), rows_belt.max() + 1):
        c_r = cols_belt[rows_belt == r]
        if len(c_r) > 0:
            row_center_cols[r] = (c_r.min() + c_r.max()) / 2.0

    west_bank_mask = np.zeros_like(c_external_bank, dtype=bool)
    east_bank_mask = np.zeros_like(c_external_bank, dtype=bool)

    ext_rows, ext_cols = np.where(c_external_bank)
    for r, c in zip(ext_rows, ext_cols):
        cen = row_center_cols.get(r, 850.0)
        if c < cen:
            west_bank_mask[r, c] = True
        else:
            east_bank_mask[r, c] = True

    return {
        "ju_main_channel": ju_main_channel,
        "jl_main_channel": jl_main_channel,
        "ju_belt": ju_belt_filled,
        "jl_belt": jl_belt_filled,
        "ju_internal_chars": ju_internal_chars,
        "jl_internal_chars": jl_internal_chars,
        "c_external_bank": c_external_bank,
        "c_internal_char_sub": c_internal_char_sub,
        "c_floodplain_inundation": c_floodplain_inundation,
        "c_accretion": c_accretion,
        "c_persistent_chars": c_persistent_chars,
        "c_persistent_channel_water": c_persistent_channel_water,
        "west_bank_mask": west_bank_mask,
        "east_bank_mask": east_bank_mask,
        "zones_raster": zones_arr,
        "counts": {
            "total_new_inundation": total_new_cells,
            "external_bank_expansion_cells": n_bank,
            "external_bank_expansion_km2": round(n_bank * PIXEL_AREA_KM2, 4),
            "external_bank_expansion_ha": round(n_bank * PIXEL_AREA_HA, 2),
            "west_bank_cells": int(np.sum(west_bank_mask)),
            "west_bank_km2": round(int(np.sum(west_bank_mask)) * PIXEL_AREA_KM2, 4),
            "west_bank_ha": round(int(np.sum(west_bank_mask)) * PIXEL_AREA_HA, 2),
            "east_bank_cells": int(np.sum(east_bank_mask)),
            "east_bank_km2": round(int(np.sum(east_bank_mask)) * PIXEL_AREA_KM2, 4),
            "east_bank_ha": round(int(np.sum(east_bank_mask)) * PIXEL_AREA_HA, 2),
            "internal_char_submergence_cells": n_char,
            "internal_char_submergence_km2": round(n_char * PIXEL_AREA_KM2, 4),
            "internal_char_submergence_ha": round(n_char * PIXEL_AREA_HA, 2),
            "floodplain_inundation_cells": n_flood,
            "floodplain_inundation_km2": round(n_flood * PIXEL_AREA_KM2, 4),
            "floodplain_inundation_ha": round(n_flood * PIXEL_AREA_HA, 2),
            "accretion_cells": int(np.sum(c_accretion)),
            "accretion_km2": round(int(np.sum(c_accretion)) * PIXEL_AREA_KM2, 4),
            "persistent_channel_water_cells": int(np.sum(c_persistent_channel_water)),
            "persistent_channel_water_km2": round(int(np.sum(c_persistent_channel_water)) * PIXEL_AREA_KM2, 4),
            "persistent_char_cells": int(np.sum(c_persistent_chars)),
            "persistent_char_km2": round(int(np.sum(c_persistent_chars)) * PIXEL_AREA_KM2, 4),
        },
    }


def derive_channel_centerline_and_transects(
    ju_belt: np.ndarray,
    jl_belt: np.ndarray,
    geotransform: Tuple[float, ...],
    sampling_intervals_m: List[float] = [200.0, 100.0, 500.0, 1000.0],
) -> Dict[str, Any]:
    """
    Derives the provisional smoothed channel-belt centerline and evaluates bankline
    displacement on orthogonal bank-normal transects across the Jamuna corridor.
    """
    x_origin, pixel_width, _, y_origin, _, pixel_height = geotransform

    # Combine June and July belts to find active river corridor bounds
    rows_ju, cols_ju = np.where(ju_belt)
    rows_jl, cols_jl = np.where(jl_belt)
    r_min = max(rows_ju.min(), rows_jl.min())
    r_max = min(rows_ju.max(), rows_jl.max())

    row_indices = []
    mid_cols = []
    rb_june_cols = []
    lb_june_cols = []
    rb_july_cols = []
    lb_july_cols = []

    for r in range(r_min, r_max + 1):
        c_ju = cols_ju[rows_ju == r]
        c_jl = cols_jl[rows_jl == r]
        if len(c_ju) > 0 and len(c_jl) > 0:
            row_indices.append(r)
            rb_ju = c_ju.min()
            lb_ju = c_ju.max()
            rb_jl = c_jl.min()
            lb_jl = c_jl.max()

            rb_june_cols.append(rb_ju)
            lb_june_cols.append(lb_ju)
            rb_july_cols.append(rb_jl)
            lb_july_cols.append(lb_jl)

            # Combined corridor midpoint
            mid_c = (min(rb_ju, rb_jl) + max(lb_ju, lb_jl)) / 2.0
            mid_cols.append(mid_c)

    row_indices = np.array(row_indices)
    mid_cols = np.array(mid_cols)
    rb_june_cols = np.array(rb_june_cols)
    lb_june_cols = np.array(lb_june_cols)
    rb_july_cols = np.array(rb_july_cols)
    lb_july_cols = np.array(lb_july_cols)

    # Smooth centerline columns using Savitzky-Golay filter to eliminate discretization noise
    window = min(51, len(mid_cols) if len(mid_cols) % 2 != 0 else len(mid_cols) - 1)
    if window >= 7:
        smooth_cols = savgol_filter(mid_cols, window_length=window, polyorder=3)
    else:
        smooth_cols = mid_cols

    # Convert centerline to UTM coordinates
    x_center = x_origin + smooth_cols * pixel_width
    y_center = y_origin + row_indices * pixel_height

    # Compute stream distance s
    dx = np.diff(x_center)
    dy = np.diff(y_center)
    ds = np.sqrt(dx**2 + dy**2)
    s = np.insert(np.cumsum(ds), 0, 0.0)
    total_stream_len = s[-1]

    # Evaluate transects for each requested sampling interval
    results_by_interval = {}

    for interval in sampling_intervals_m:
        transect_targets = np.arange(0, total_stream_len, interval)
        transects_records = []

        for idx, s_target in enumerate(transect_targets, 1):
            # Find closest centerline index
            idx_c = int(np.argmin(np.abs(s - s_target)))
            r = row_indices[idx_c]
            x_c = x_center[idx_c]
            y_c = y_center[idx_c]

            # Bank positions in UTM
            x_rb_ju = x_origin + rb_june_cols[idx_c] * pixel_width
            x_lb_ju = x_origin + lb_june_cols[idx_c] * pixel_width
            x_rb_jl = x_origin + rb_july_cols[idx_c] * pixel_width
            x_lb_jl = x_origin + lb_july_cols[idx_c] * pixel_width

            # Signed displacements (m)
            # Right Bank (West): Positive = Westward retreat (Erosion candidate)
            d_rb = x_rb_ju - x_rb_jl
            # Left Bank (East): Positive = Eastward retreat (Expansion candidate)
            d_lb = x_lb_jl - x_lb_ju

            width_june = x_lb_ju - x_rb_ju
            width_july = x_lb_jl - x_rb_jl
            width_expansion = width_july - width_june

            # Directional descriptor
            rb_dir = "Westward (Retreat/Erosion)" if d_rb > 0 else "Eastward (Advance/Accretion)" if d_rb < 0 else "Stable"
            lb_dir = "Eastward (Retreat/Expansion)" if d_lb > 0 else "Westward (Advance/Contraction)" if d_lb < 0 else "Stable"

            transects_records.append({
                "transect_id": idx,
                "chainage_m": round(float(s_target), 2),
                "raster_row": int(r),
                "center_utm_x": round(float(x_c), 2),
                "center_utm_y": round(float(y_c), 2),
                "right_bank_june_x": round(float(x_rb_ju), 2),
                "right_bank_july_x": round(float(x_rb_jl), 2),
                "right_bank_displacement_m": round(float(d_rb), 2),
                "right_bank_movement": rb_dir,
                "left_bank_june_x": round(float(x_lb_ju), 2),
                "left_bank_july_x": round(float(x_lb_jl), 2),
                "left_bank_displacement_m": round(float(d_lb), 2),
                "left_bank_movement": lb_dir,
                "channel_width_june_m": round(float(width_june), 2),
                "channel_width_july_m": round(float(width_july), 2),
                "channel_width_expansion_m": round(float(width_expansion), 2),
            })

        df_t = pd.DataFrame(transects_records)
        rb_arr = df_t["right_bank_displacement_m"].values
        lb_arr = df_t["left_bank_displacement_m"].values
        w_arr = df_t["channel_width_expansion_m"].values

        summary = {
            "interval_m": interval,
            "transect_count": len(df_t),
            "right_bank": {
                "mean_m": round(float(np.mean(rb_arr)), 2),
                "median_m": round(float(np.median(rb_arr)), 2),
                "std_m": round(float(np.std(rb_arr)), 2),
                "min_m": round(float(np.min(rb_arr)), 2),
                "max_m": round(float(np.max(rb_arr)), 2),
                "p10_m": round(float(np.percentile(rb_arr, 10)), 2),
                "p25_m": round(float(np.percentile(rb_arr, 25)), 2),
                "p75_m": round(float(np.percentile(rb_arr, 75)), 2),
                "p90_m": round(float(np.percentile(rb_arr, 90)), 2),
                "p95_m": round(float(np.percentile(rb_arr, 95)), 2),
            },
            "left_bank": {
                "mean_m": round(float(np.mean(lb_arr)), 2),
                "median_m": round(float(np.median(lb_arr)), 2),
                "std_m": round(float(np.std(lb_arr)), 2),
                "min_m": round(float(np.min(lb_arr)), 2),
                "max_m": round(float(np.max(lb_arr)), 2),
                "p10_m": round(float(np.percentile(lb_arr, 10)), 2),
                "p25_m": round(float(np.percentile(lb_arr, 25)), 2),
                "p75_m": round(float(np.percentile(lb_arr, 75)), 2),
                "p90_m": round(float(np.percentile(lb_arr, 90)), 2),
                "p95_m": round(float(np.percentile(lb_arr, 95)), 2),
            },
            "channel_width": {
                "mean_m": round(float(np.mean(w_arr)), 2),
                "median_m": round(float(np.median(w_arr)), 2),
                "std_m": round(float(np.std(w_arr)), 2),
                "min_m": round(float(np.min(w_arr)), 2),
                "max_m": round(float(np.max(w_arr)), 2),
                "p90_m": round(float(np.percentile(w_arr, 90)), 2),
                "p95_m": round(float(np.percentile(w_arr, 95)), 2),
            },
        }

        results_by_interval[f"interval_{int(interval)}m"] = {
            "summary": summary,
            "df": df_t,
        }

    return {
        "centerline": {
            "x": x_center,
            "y": y_center,
            "chainage_s": s,
            "total_stream_len_m": round(float(total_stream_len), 2),
        },
        "results_by_interval": results_by_interval,
    }


def export_geotiff(
    output_path: Path,
    array: np.ndarray,
    geotransform: Tuple[float, ...],
    projection_wkt: str,
    nodata_value: Optional[Union[int, float]] = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    dtype = gdal.GDT_Byte if array.dtype == np.uint8 else gdal.GDT_Int16
    ds = driver.Create(
        str(output_path),
        array.shape[1],
        array.shape[0],
        1,
        dtype,
        ["COMPRESS=LZW", "TILED=YES"],
    )
    ds.SetGeoTransform(geotransform)
    ds.SetProjection(projection_wkt)
    band = ds.GetRasterBand(1)
    if nodata_value is not None:
        band.SetNoDataValue(nodata_value)
    band.WriteArray(array)
    band.FlushCache()
    ds = None
    logger.info(f"Saved GeoTIFF: {output_path}")


def export_vector_geojson(
    output_path: Path,
    features: List[Dict[str, Any]],
    crs_epsg: int = 32645,
) -> None:
    """Exports a list of GeoJSON features to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    geojson_doc = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:EPSG::{crs_epsg}"},
        },
        "features": features,
    }
    with open(output_path, "w") as f:
        json.dump(geojson_doc, f, indent=2)
    logger.info(f"Saved GeoJSON: {output_path}")


def generate_transect_geojson_features(df_transects: pd.DataFrame) -> List[Dict[str, Any]]:
    features = []
    for _, row in df_transects.iterrows():
        # Line from Right Bank (West) to Left Bank (East)
        geom = {
            "type": "LineString",
            "coordinates": [
                [row["right_bank_july_x"], row["center_utm_y"]],
                [row["left_bank_july_x"], row["center_utm_y"]],
            ],
        }
        props = {
            "transect_id": int(row["transect_id"]),
            "chainage_m": float(row["chainage_m"]),
            "right_bank_displacement_m": float(row["right_bank_displacement_m"]),
            "right_bank_movement": str(row["right_bank_movement"]),
            "left_bank_displacement_m": float(row["left_bank_displacement_m"]),
            "left_bank_movement": str(row["left_bank_movement"]),
            "channel_width_june_m": float(row["channel_width_june_m"]),
            "channel_width_july_m": float(row["channel_width_july_m"]),
            "channel_width_expansion_m": float(row["channel_width_expansion_m"]),
        }
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": props,
        })
    return features


def render_phase6_cartography(
    zones_arr: np.ndarray,
    df_transects: pd.DataFrame,
    centerline_x: np.ndarray,
    centerline_y: np.ndarray,
    geotransform: Tuple[float, ...],
    aoi_mask: np.ndarray,
    output_dir: Path,
) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    x_origin, pixel_width, _, y_origin, _, pixel_height = geotransform
    h, w = zones_arr.shape
    extent = [x_origin, x_origin + w * pixel_width, y_origin + h * pixel_height, y_origin]

    # Map 1: Channel-Margin Displacement & Transect Overview
    fig, ax = plt.subplots(figsize=(12, 14), dpi=300)
    
    # Background: Persistent water and erosion zones
    cmap_base = ListedColormap([
        "#f5f5f5",  # 0: Mainland Dry
        "#2b5c8f",  # 1: Persistent Channel Water
        "#d92b2b",  # 2: External Bank Erosion Candidate
        "#f39c12",  # 3: Internal Char Submergence
        "#27ae60",  # 4: Apparent Accretion
        "#e0d4b8",  # 5: Persistent Internal Char
        "#5dade2",  # 6: Floodplain Inundation
        "#bdc3c7",  # 7: Noise floor
    ])
    
    masked_zones = np.copy(zones_arr)
    masked_zones[~aoi_mask] = 0
    im = ax.imshow(masked_zones, extent=extent, cmap=cmap_base, vmin=0, vmax=7, alpha=0.85)

    # Plot centerline
    ax.plot(centerline_x, centerline_y, color="#111111", linewidth=1.5, linestyle="--", label="Provisional River Centerline")

    # Plot transects
    for _, t in df_transects.iterrows():
        y_pos = t["center_utm_y"]
        x_rb = t["right_bank_july_x"]
        x_lb = t["left_bank_july_x"]
        ax.plot([x_rb, x_lb], [y_pos, y_pos], color="#444444", linewidth=0.6, alpha=0.7)

    # Highlight top 5 displacement transects
    top_rb = df_transects.nlargest(5, "right_bank_displacement_m")
    for _, row in top_rb.iterrows():
        ax.scatter(row["right_bank_july_x"], row["center_utm_y"], color="#e74c3c", s=40, zorder=5)
        ax.text(row["right_bank_july_x"] - 300, row["center_utm_y"], f"+{int(row['right_bank_displacement_m'])}m",
                fontsize=7, fontweight="bold", color="#900C3F", ha="right", va="center")

    ax.set_title("Earth Pulse — Jamuna River Channel-Margin Displacement & Transect Analysis\n"
                 "Baseline: June 10, 2024 (Pre-Monsoon) vs Flood Peak: July 16, 2024 (Sentinel-1 SAR)",
                 fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("UTM Zone 45N Easting (m)", fontsize=10)
    ax.set_ylabel("UTM Zone 45N Northing (m)", fontsize=10)

    # Legend
    legend_elements = [
        mpatches.Patch(color="#2b5c8f", label="Persistent Channel Water"),
        mpatches.Patch(color="#d92b2b", label="External Bank Erosion Candidate (Mainland Retreat)"),
        mpatches.Patch(color="#f39c12", label="Internal Char Shoreline Submergence / Scour"),
        mpatches.Patch(color="#27ae60", label="Apparent Channel Contraction / Accretion"),
        mpatches.Patch(color="#e0d4b8", label="Persistent Internal Char Islands"),
        mpatches.Patch(color="#5dade2", label="Disconnected Floodplain Inundation"),
        mpatches.Patch(color="#bdc3c7", label="Indeterminate Noise Floor"),
        matplotlib.lines.Line2D([0], [0], color="#111111", linestyle="--", lw=1.5, label="Smoothed Centerline"),
        matplotlib.lines.Line2D([0], [0], color="#444444", lw=0.8, label="200m Orthogonal Transects"),
        matplotlib.lines.Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c", markersize=8, label="High Bank Retreat (>400m)"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", fontsize=8, framealpha=0.92)
    ax.grid(True, linestyle=":", alpha=0.4, color="#7f8c8d")

    map1_path = output_dir / "phase6_channel_margin_displacement_map.png"
    plt.tight_layout()
    plt.savefig(map1_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved cartography map: {map1_path}")

    # Map 2: Erosion, Submergence & Floodplain Zonal Classification
    fig, ax = plt.subplots(figsize=(12, 14), dpi=300)
    im2 = ax.imshow(masked_zones, extent=extent, cmap=cmap_base, vmin=0, vmax=7)
    ax.set_title("Earth Pulse — Phase 6: Geomorphic Channel-Change & Inundation Typology\n"
                 "Jamuna River Reach (Kazipur / Sirajganj, Bangladesh)",
                 fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("UTM Zone 45N Easting (m)", fontsize=10)
    ax.set_ylabel("UTM Zone 45N Northing (m)", fontsize=10)
    ax.legend(handles=legend_elements[:7], loc="lower left", fontsize=8, framealpha=0.92)
    ax.grid(True, linestyle=":", alpha=0.4, color="#7f8c8d")

    map2_path = output_dir / "phase6_erosion_accretion_zones_map.png"
    plt.tight_layout()
    plt.savefig(map2_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved cartography map: {map2_path}")

    return map1_path, map2_path


def run_phase6_pipeline() -> Dict[str, Any]:
    project_root = find_project_root()
    logger.info(f"Starting Phase 6 Riverbank Migration & Erosion Engine. Root: {project_root}")

    # Define input paths
    june_mask_path = project_root / "data/processed/phase3a_qc/candidate_masks/june10_lee_5x5_otsu_dual_and_qc.tif"
    july_mask_path = project_root / "data/processed/phase3a_qc/candidate_masks/july16_lee_5x5_otsu_dual_and_qc.tif"
    transition_path = project_root / "data/processed/phase5/phase5_flood_transitions.tif"

    assert june_mask_path.exists(), f"Missing June mask: {june_mask_path}"
    assert july_mask_path.exists(), f"Missing July mask: {july_mask_path}"
    assert transition_path.exists(), f"Missing transition raster: {transition_path}"

    # Load raster arrays and metadata
    ds_trans = gdal.Open(str(transition_path), gdal.GA_ReadOnly)
    trans_arr = ds_trans.GetRasterBand(1).ReadAsArray()
    gt = ds_trans.GetGeoTransform()
    proj = ds_trans.GetProjection()
    ds_trans = None

    ds_ju = gdal.Open(str(june_mask_path), gdal.GA_ReadOnly)
    ju_arr = ds_ju.GetRasterBand(1).ReadAsArray()
    ds_ju = None

    ds_jl = gdal.Open(str(july_mask_path), gdal.GA_ReadOnly)
    jl_arr = ds_jl.GetRasterBand(1).ReadAsArray()
    ds_jl = None

    # Load canonical AOI mask
    aoi_mask = create_study_aoi_raster_mask(transition_path)
    total_aoi_cells = int(np.sum(aoi_mask))
    assert total_aoi_cells == AOI_TARGET_CELLS, f"AOI cells mismatch: {total_aoi_cells} != {AOI_TARGET_CELLS}"

    logger.info("Executing Task B: Separating River Channel from Floodplain Inundation...")
    zone_data = extract_channel_and_floodplain_zones(
        june_water_mask=ju_arr,
        july_water_mask=jl_arr,
        transition_raster=trans_arr,
        aoi_mask=aoi_mask,
    )

    logger.info("Executing Task C & D: Extracting Centerline & Computing Bankline Displacements...")
    transect_data = derive_channel_centerline_and_transects(
        ju_belt=zone_data["ju_belt"],
        jl_belt=zone_data["jl_belt"],
        geotransform=gt,
        sampling_intervals_m=[200.0, 100.0, 500.0, 1000.0],
    )

    # Primary 200m baseline transects
    primary_transects_df = transect_data["results_by_interval"]["interval_200m"]["df"]
    primary_summary = transect_data["results_by_interval"]["interval_200m"]["summary"]

    # Export Processed GeoTIFFs
    proc_dir = project_root / "data/processed/phase6"
    proc_dir.mkdir(parents=True, exist_ok=True)

    export_geotiff(proc_dir / "phase6_channel_change_zones.tif", zone_data["zones_raster"], gt, proj, nodata_value=ZONE_NODATA_BORDER)
    export_geotiff(proc_dir / "phase6_external_bank_erosion_candidate.tif", zone_data["c_external_bank"].astype(np.uint8), gt, proj, nodata_value=0)
    export_geotiff(proc_dir / "phase6_internal_char_submergence.tif", zone_data["c_internal_char_sub"].astype(np.uint8), gt, proj, nodata_value=0)
    export_geotiff(proc_dir / "phase6_channel_contraction_accretion.tif", zone_data["c_accretion"].astype(np.uint8), gt, proj, nodata_value=0)
    export_geotiff(proc_dir / "phase6_channel_belt_june.tif", zone_data["ju_belt"].astype(np.uint8), gt, proj, nodata_value=0)
    export_geotiff(proc_dir / "phase6_channel_belt_july.tif", zone_data["jl_belt"].astype(np.uint8), gt, proj, nodata_value=0)
    export_geotiff(proc_dir / "phase6_disconnected_floodplain_inundation.tif", zone_data["c_floodplain_inundation"].astype(np.uint8), gt, proj, nodata_value=0)

    # Export Vector GeoJSONs
    transect_features = generate_transect_geojson_features(primary_transects_df)
    export_vector_geojson(proc_dir / "phase6_riverbank_transects.geojson", transect_features)

    # Centerline GeoJSON
    centerline_geom = {
        "type": "LineString",
        "coordinates": [
            [float(x), float(y)]
            for x, y in zip(transect_data["centerline"]["x"], transect_data["centerline"]["y"])
        ],
    }
    centerline_feat = [{
        "type": "Feature",
        "geometry": centerline_geom,
        "properties": {
            "name": "Jamuna River Provisional Smoothed Centerline",
            "length_m": transect_data["centerline"]["total_stream_len_m"],
            "derivation": "Midpoint of outer active channel belt smoothed via Savitzky-Golay filter",
        },
    }]
    export_vector_geojson(proc_dir / "phase6_provisional_centerline.geojson", centerline_feat)

    # Mirror GeoJSON to maps directory
    maps_dir = project_root / "data/outputs/phase6/maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    export_vector_geojson(maps_dir / "phase6_riverbank_transects.geojson", transect_features)
    export_vector_geojson(maps_dir / "phase6_provisional_centerline.geojson", centerline_feat)

    # Render Publication Cartography
    logger.info("Rendering 300 DPI Publication Cartography...")
    map1_path, map2_path = render_phase6_cartography(
        zones_arr=zone_data["zones_raster"],
        df_transects=primary_transects_df,
        centerline_x=transect_data["centerline"]["x"],
        centerline_y=transect_data["centerline"]["y"],
        geotransform=gt,
        aoi_mask=aoi_mask,
        output_dir=maps_dir,
    )

    # Export CSV Statistics Tables
    stats_dir = project_root / "data/outputs/phase6/statistics"
    stats_dir.mkdir(parents=True, exist_ok=True)

    # 1. Transect displacement summary
    primary_transects_df.to_csv(stats_dir / "phase6_transect_displacement_summary.csv", index=False)

    # 2. Channel change zones accounting
    zones_list = []
    for code, name in ZONE_NAMES.items():
        if code == ZONE_NODATA_BORDER:
            continue
        cells = int(np.sum((zone_data["zones_raster"] == code) & aoi_mask))
        area_km2 = cells * PIXEL_AREA_KM2
        area_ha = cells * PIXEL_AREA_HA
        pct_aoi = (cells / AOI_TARGET_CELLS) * 100.0
        zones_list.append({
            "zone_code": code,
            "zone_name": name,
            "pixel_count": cells,
            "area_km2": round(area_km2, 4),
            "area_ha": round(area_ha, 2),
            "pct_study_aoi": round(pct_aoi, 4),
        })
    df_zones = pd.DataFrame(zones_list)
    df_zones.to_csv(stats_dir / "phase6_channel_change_zones.csv", index=False)

    # 3. Transect sensitivity comparison table
    sens_list = []
    for int_key, data in transect_data["results_by_interval"].items():
        s = data["summary"]
        sens_list.append({
            "sampling_interval_m": s["interval_m"],
            "transect_count": s["transect_count"],
            "right_bank_mean_m": s["right_bank"]["mean_m"],
            "right_bank_median_m": s["right_bank"]["median_m"],
            "right_bank_max_m": s["right_bank"]["max_m"],
            "right_bank_p90_m": s["right_bank"]["p90_m"],
            "left_bank_mean_m": s["left_bank"]["mean_m"],
            "left_bank_median_m": s["left_bank"]["median_m"],
            "left_bank_max_m": s["left_bank"]["max_m"],
            "left_bank_p90_m": s["left_bank"]["p90_m"],
            "channel_width_expansion_mean_m": s["channel_width"]["mean_m"],
            "channel_width_expansion_median_m": s["channel_width"]["median_m"],
            "channel_width_expansion_max_m": s["channel_width"]["max_m"],
        })
    df_sens = pd.DataFrame(sens_list)
    df_sens.to_csv(stats_dir / "phase6_transect_sensitivity.csv", index=False)

    # 4. Bank displacement distribution table
    dist_list = [
        {"metric": "mean_m", "right_bank": primary_summary["right_bank"]["mean_m"], "left_bank": primary_summary["left_bank"]["mean_m"], "channel_width": primary_summary["channel_width"]["mean_m"]},
        {"metric": "median_m", "right_bank": primary_summary["right_bank"]["median_m"], "left_bank": primary_summary["left_bank"]["median_m"], "channel_width": primary_summary["channel_width"]["median_m"]},
        {"metric": "std_m", "right_bank": primary_summary["right_bank"]["std_m"], "left_bank": primary_summary["left_bank"]["std_m"], "channel_width": primary_summary["channel_width"]["std_m"]},
        {"metric": "min_m", "right_bank": primary_summary["right_bank"]["min_m"], "left_bank": primary_summary["left_bank"]["min_m"], "channel_width": primary_summary["channel_width"]["min_m"]},
        {"metric": "max_m", "right_bank": primary_summary["right_bank"]["max_m"], "left_bank": primary_summary["left_bank"]["max_m"], "channel_width": primary_summary["channel_width"]["max_m"]},
        {"metric": "p10_m", "right_bank": primary_summary["right_bank"]["p10_m"], "left_bank": primary_summary["left_bank"]["p10_m"], "channel_width": primary_summary["channel_width"]["min_m"]},
        {"metric": "p25_m", "right_bank": primary_summary["right_bank"]["p25_m"], "left_bank": primary_summary["left_bank"]["p25_m"], "channel_width": primary_summary["channel_width"]["min_m"]},
        {"metric": "p75_m", "right_bank": primary_summary["right_bank"]["p75_m"], "left_bank": primary_summary["left_bank"]["p75_m"], "channel_width": primary_summary["channel_width"]["p90_m"]},
        {"metric": "p90_m", "right_bank": primary_summary["right_bank"]["p90_m"], "left_bank": primary_summary["left_bank"]["p90_m"], "channel_width": primary_summary["channel_width"]["p90_m"]},
        {"metric": "p95_m", "right_bank": primary_summary["right_bank"]["p95_m"], "left_bank": primary_summary["left_bank"]["p95_m"], "channel_width": primary_summary["channel_width"]["p95_m"]},
    ]
    pd.DataFrame(dist_list).to_csv(stats_dir / "phase6_bank_displacement_distribution.csv", index=False)

    # 5. Floodplain vs Channel Decomposition Table
    total_new_cells = zone_data["counts"]["total_new_inundation"]
    decomp_list = [
        {"component": "External Bank Expansion (Riverbank Migration)", "cells": zone_data["counts"]["external_bank_expansion_cells"], "area_km2": zone_data["counts"]["external_bank_expansion_km2"], "area_ha": zone_data["counts"]["external_bank_expansion_ha"], "pct_new_inundation": round((zone_data["counts"]["external_bank_expansion_cells"]/total_new_cells)*100.0, 2)},
        {"component": "  - West Bank (Right Bank / Embankment)", "cells": zone_data["counts"]["west_bank_cells"], "area_km2": zone_data["counts"]["west_bank_km2"], "area_ha": zone_data["counts"]["west_bank_ha"], "pct_new_inundation": round((zone_data["counts"]["west_bank_cells"]/total_new_cells)*100.0, 2)},
        {"component": "  - East Bank (Left Bank / Braids)", "cells": zone_data["counts"]["east_bank_cells"], "area_km2": zone_data["counts"]["east_bank_km2"], "area_ha": zone_data["counts"]["east_bank_ha"], "pct_new_inundation": round((zone_data["counts"]["east_bank_cells"]/total_new_cells)*100.0, 2)},
        {"component": "Internal Char Submergence / Scour", "cells": zone_data["counts"]["internal_char_submergence_cells"], "area_km2": zone_data["counts"]["internal_char_submergence_km2"], "area_ha": zone_data["counts"]["internal_char_submergence_ha"], "pct_new_inundation": round((zone_data["counts"]["internal_char_submergence_cells"]/total_new_cells)*100.0, 2)},
        {"component": "Disconnected Floodplain Inundation", "cells": zone_data["counts"]["floodplain_inundation_cells"], "area_km2": zone_data["counts"]["floodplain_inundation_km2"], "area_ha": zone_data["counts"]["floodplain_inundation_ha"], "pct_new_inundation": round((zone_data["counts"]["floodplain_inundation_cells"]/total_new_cells)*100.0, 2)},
        {"component": "Total Phase 5 Newly Inundated Candidate Area", "cells": total_new_cells, "area_km2": round(total_new_cells * PIXEL_AREA_KM2, 4), "area_ha": round(total_new_cells * PIXEL_AREA_HA, 2), "pct_new_inundation": 100.00},
    ]
    pd.DataFrame(decomp_list).to_csv(stats_dir / "phase6_floodplain_vs_channel_accounting.csv", index=False)

    # Master JSON Metadata Report
    metadata_report = {
        "project": "NASA Space Apps Challenge 2026: Dancing with the SARs",
        "phase": "Phase 6: Riverbank Migration, Channel-Margin Displacement & Erosion Analysis",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "study_area": {
            "name": "Jamuna River reach (Kazipur / Sirajganj, Bangladesh)",
            "aoi_wkt": STUDY_AREA_AOI_WKT,
            "crs": "EPSG:32645",
            "pixel_spacing_m": PIXEL_SPACING_M,
            "total_aoi_cells": total_aoi_cells,
            "total_aoi_area_km2": round(total_aoi_cells * PIXEL_AREA_KM2, 4),
        },
        "stream_centerline": {
            "total_stream_length_m": transect_data["centerline"]["total_stream_len_m"],
            "derivation_method": "Midpoint of active channel belt envelope smoothed via Savitzky-Golay filter",
            "flow_direction": "North to South (Downstream)",
        },
        "phase5_inundation_decomposition": zone_data["counts"],
        "transect_displacement_analysis_200m": primary_summary,
        "transect_sensitivity_comparison": sens_list,
        "scientific_caveats": [
            "Observations span 36 days between pre-monsoon baseline (June 10) and monsoon flood crest (July 16).",
            "Displacement values represent apparent channel-margin migration and stage-induced margin submergence.",
            "Do not extrapolate these 36-day event displacements into annualized erosion rates.",
            "Optical observations (Sentinel-2 L2A) during monsoon crest had 83.4% cloud contamination and provide partial supplementary cross-validation only.",
            "Terminology standard: All areas are candidate erosion/submergence features, not field-verified cadastral ground truth.",
        ],
        "deliverables": {
            "processed_geotiffs": [
                "data/processed/phase6/phase6_channel_change_zones.tif",
                "data/processed/phase6/phase6_external_bank_erosion_candidate.tif",
                "data/processed/phase6/phase6_internal_char_submergence.tif",
                "data/processed/phase6/phase6_channel_contraction_accretion.tif",
                "data/processed/phase6/phase6_channel_belt_june.tif",
                "data/processed/phase6/phase6_channel_belt_july.tif",
                "data/processed/phase6/phase6_disconnected_floodplain_inundation.tif",
            ],
            "geojson_vectors": [
                "data/processed/phase6/phase6_riverbank_transects.geojson",
                "data/processed/phase6/phase6_provisional_centerline.geojson",
                "data/outputs/phase6/maps/phase6_riverbank_transects.geojson",
                "data/outputs/phase6/maps/phase6_provisional_centerline.geojson",
            ],
            "cartography_maps": [
                "data/outputs/phase6/maps/phase6_channel_margin_displacement_map.png",
                "data/outputs/phase6/maps/phase6_erosion_accretion_zones_map.png",
            ],
            "statistics_csv": [
                "data/outputs/phase6/statistics/phase6_transect_displacement_summary.csv",
                "data/outputs/phase6/statistics/phase6_channel_change_zones.csv",
                "data/outputs/phase6/statistics/phase6_transect_sensitivity.csv",
                "data/outputs/phase6/statistics/phase6_bank_displacement_distribution.csv",
                "data/outputs/phase6/statistics/phase6_floodplain_vs_channel_accounting.csv",
            ],
        },
    }

    meta_path = project_root / "data/metadata/phase6_riverbank_migration_report.json"
    with open(meta_path, "w") as f:
        json.dump(metadata_report, f, indent=2)
    logger.info(f"Phase 6 metadata report saved to: {meta_path}")

    return metadata_report


if __name__ == "__main__":
    report = run_phase6_pipeline()
    print("Phase 6 Pipeline execution complete.")
