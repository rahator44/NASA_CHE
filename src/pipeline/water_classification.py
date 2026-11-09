"""
Dynamic Surface Water Classification Engine for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Authoritative Scientific Methodology:
- Adaptive Lee 5x5 speckle filtering in linear power domain
- Radiometric dB feature transformation: 10 * log10(Sigma0)
- Unsupervised 1D and 2D Otsu thresholding computed dynamically per scene
- Dual-polarization fusion (VV AND VH) for robust water detection
- 4-class mask: 0=Non-water, 1=Water, 2=Indeterminate (clipping floor), 3=NoData/invalid
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

import numpy as np
from osgeo import gdal, osr
from scipy.ndimage import convolve

gdal.UseExceptions()

logger = logging.getLogger("EarthPulse.WaterClassification")

# Constants
NODATA_VALUE = -9999.0
CLIPPING_FLOOR_MIN = 2.50e-11
CLIPPING_FLOOR_MAX = 2.70e-11
PIXEL_SPACING_M = 20.0
PIXEL_AREA_M2 = 400.0
PIXEL_AREA_HA = 0.04
PIXEL_AREA_KM2 = 0.0004

# Quality Mask Categories
CAT_VALID_ORDINARY = 0
CAT_SOURCE_NODATA = 1
CAT_SNAP_CLIPPING_FLOOR = 2
CAT_OTHER_INVALID = 3

# Water Mask Categories
MASK_NON_WATER = 0
MASK_CANDIDATE_WATER = 1
MASK_INDETERMINATE = 2
MASK_NODATA_INVALID = 3


def vectorized_lee_filter(
    block: np.ndarray,
    enl: float = 4.9,
    window_size: int = 5,
    clip_min: float = CLIPPING_FLOOR_MIN,
    clip_max: float = CLIPPING_FLOOR_MAX,
    nodata: float = NODATA_VALUE,
) -> np.ndarray:
    """
    Vectorized standard adaptive Lee filter for 2D linear Sigma0 array.
    Operates strictly in linear power domain.
    Preserves NoData (-9999.0) and SNAP clipping floor (2.55e-11) without contamination.
    """
    if enl <= 0 or np.isnan(enl):
        raise ValueError(f"Invalid ENL for Lee filter: {enl}")
    if window_size % 2 == 0 or window_size < 3:
        raise ValueError(f"Filter window size must be odd integer >= 3, got {window_size}")

    is_nodata = (block == nodata) | np.isnan(block)
    is_clip = (block >= clip_min) & (block <= clip_max)
    is_invalid = is_nodata | is_clip | (block <= 0)

    valid_mask = (~is_invalid).astype(np.float64)
    x = np.where(valid_mask == 1.0, block, 0.0).astype(np.float64)
    x2 = x ** 2

    kernel = np.ones((window_size, window_size), dtype=np.float64)
    n_valid = convolve(valid_mask, kernel, mode="reflect")
    sum_x = convolve(x, kernel, mode="reflect")
    sum_x2 = convolve(x2, kernel, mode="reflect")

    with np.errstate(divide="ignore", invalid="ignore"):
        local_mean = np.where(n_valid > 0, sum_x / n_valid, 0.0)
        local_var = np.where(n_valid > 1, (sum_x2 - n_valid * (local_mean ** 2)) / (n_valid - 1), 0.0)
        local_var = np.maximum(0.0, local_var)
        noise_var = (local_mean ** 2) / enl
        weight = np.where(local_var > 0, np.maximum(0.0, (local_var - noise_var) / local_var), 0.0)
        weight = np.clip(weight, 0.0, 1.0)
        filtered = local_mean + weight * (block.astype(np.float64) - local_mean)

    filtered[is_nodata] = nodata
    filtered[is_clip] = block[is_clip]
    insufficient = (~is_invalid) & (n_valid < 3)
    filtered[insufficient] = block[insufficient]

    return filtered.astype(np.float32)


def otsu_threshold_1d(
    values: np.ndarray,
    n_bins: int = 256,
    val_range: Optional[Tuple[float, float]] = None,
) -> Dict[str, Any]:
    """
    Computes standard 1D Otsu threshold maximizing between-class variance.
    """
    if values is None or len(values) == 0:
        return {"status": "FAILED", "threshold": None, "reason": "Empty values"}

    finite_vals = values[np.isfinite(values)]
    if len(finite_vals) < 10:
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
    omega = np.cumsum(p)
    mu = np.cumsum(p * bin_centers)
    mu_t = mu[-1]

    valid = (omega > 1e-6) & (omega < (1.0 - 1e-6))
    if not np.any(valid):
        return {"status": "FAILED", "threshold": None, "reason": "No valid split"}

    sigma_b_sq = np.zeros_like(p)
    sigma_b_sq[valid] = ((mu_t * omega[valid] - mu[valid]) ** 2) / (omega[valid] * (1.0 - omega[valid]))

    best_idx = int(np.argmax(sigma_b_sq))
    best_threshold = float(bin_centers[best_idx])

    return {
        "status": "SUCCESS",
        "threshold": best_threshold,
        "w0": float(omega[best_idx]),
        "w1": float(1.0 - omega[best_idx]),
        "criterion_value": float(sigma_b_sq[best_idx]),
    }


def otsu_threshold_2d(
    vv_vals: np.ndarray,
    vh_vals: np.ndarray,
    n_bins: int = 64,
) -> Dict[str, Any]:
    """
    2D Bivariate Otsu thresholding on joint (VV, VH) histogram.
    """
    valid = np.isfinite(vv_vals) & np.isfinite(vh_vals)
    x = vv_vals[valid]
    y = vh_vals[valid]
    if len(x) < 50:
        return {"status": "FAILED", "threshold_vv": None, "threshold_vh": None}

    x_range = (float(np.min(x)), float(np.max(x)))
    y_range = (float(np.min(y)), float(np.max(y)))

    H, x_edges, y_edges = np.histogram2d(x, y, bins=n_bins, range=[x_range, y_range])
    x_centers = 0.5 * (x_edges[:-1] + x_edges[1:])
    y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])

    total = np.sum(H)
    if total == 0:
        return {"status": "FAILED", "threshold_vv": None, "threshold_vh": None}

    P = H / total
    # 2D Cumulative sums
    omega = np.cumsum(np.cumsum(P, axis=0), axis=1)

    X_grid, Y_grid = np.meshgrid(x_centers, y_centers, indexing="ij")
    mu_x = np.cumsum(np.cumsum(P * X_grid, axis=0), axis=1)
    mu_y = np.cumsum(np.cumsum(P * Y_grid, axis=0), axis=1)

    mu_tx = mu_x[-1, -1]
    mu_ty = mu_y[-1, -1]

    denom = omega * (1.0 - omega)
    valid_mask = (omega > 0.01) & (omega < 0.99) & (denom > 1e-7)

    with np.errstate(divide="ignore", invalid="ignore"):
        num_x = (mu_x - omega * mu_tx) ** 2
        num_y = (mu_y - omega * mu_ty) ** 2
        trace_sb = np.where(valid_mask, (num_x + num_y) / denom, 0.0)

    best_idx = np.unravel_index(np.argmax(trace_sb), trace_sb.shape)
    best_vv = float(x_centers[best_idx[0]])
    best_vh = float(y_centers[best_idx[1]])

    return {
        "status": "SUCCESS",
        "threshold_vv": best_vv,
        "threshold_vh": best_vh,
        "criterion_value": float(trace_sb[best_idx]),
    }


class DynamicWaterClassifier:
    """
    Executes automated, reproducible surface-water classification on Sentinel-1 SAR imagery.
    """

    def __init__(
        self,
        filter_size: int = 5,
        enl_vh: float = 4.88,
        enl_vv: float = 4.92,
        fusion_strategy: str = "dual_and",
    ):
        self.filter_size = filter_size
        self.enl_vh = enl_vh
        self.enl_vv = enl_vv
        self.fusion_strategy = fusion_strategy

    def classify_scene(
        self,
        input_sar_tif: Path,
        output_mask_tif: Path,
        output_metadata_json: Optional[Path] = None,
        custom_threshold_vv: Optional[float] = None,
        custom_threshold_vh: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Classifies surface water from a 2-band calibrated SAR GeoTIFF (VH, VV).
        """
        input_sar_tif = Path(input_sar_tif).resolve()
        output_mask_tif = Path(output_mask_tif).resolve()
        output_mask_tif.parent.mkdir(parents=True, exist_ok=True)

        ds = gdal.Open(str(input_sar_tif), gdal.GA_ReadOnly)
        if ds is None:
            raise FileNotFoundError(f"Cannot open SAR raster: {input_sar_tif}")

        w, h = ds.RasterXSize, ds.RasterYSize
        gt = ds.GetGeoTransform()
        proj = ds.GetProjection()

        b_vh = ds.GetRasterBand(1).ReadAsArray()
        b_vv = ds.GetRasterBand(2).ReadAsArray()
        ds = None

        # 1. Speckle Filtering (Lee 5x5 in linear domain)
        logger.info("Applying adaptive Lee %dx%d filter to SAR backscatter...", self.filter_size, self.filter_size)
        vh_filtered = vectorized_lee_filter(b_vh, enl=self.enl_vh, window_size=self.filter_size)
        vv_filtered = vectorized_lee_filter(b_vv, enl=self.enl_vv, window_size=self.filter_size)

        # 2. Quality Mask Identification
        is_nodata_vh = (b_vh == NODATA_VALUE) | np.isnan(b_vh)
        is_nodata_vv = (b_vv == NODATA_VALUE) | np.isnan(b_vv)
        is_clip_vh = (b_vh >= CLIPPING_FLOOR_MIN) & (b_vh <= CLIPPING_FLOOR_MAX)
        is_clip_vv = (b_vv >= CLIPPING_FLOOR_MIN) & (b_vv <= CLIPPING_FLOOR_MAX)

        is_nodata = is_nodata_vh | is_nodata_vv
        is_clip = is_clip_vh | is_clip_vv
        is_valid = (~is_nodata) & (~is_clip) & (vh_filtered > 0) & (vv_filtered > 0)

        # 3. Radiometric dB features
        vv_db = np.full((h, w), np.nan, dtype=np.float32)
        vh_db = np.full((h, w), np.nan, dtype=np.float32)
        vv_db[is_valid] = 10.0 * np.log10(vv_filtered[is_valid])
        vh_db[is_valid] = 10.0 * np.log10(vh_filtered[is_valid])

        # 4. Otsu Threshold Calculation (Dynamic per observation)
        valid_vv_db = vv_db[is_valid]
        valid_vh_db = vh_db[is_valid]

        if custom_threshold_vv is not None:
            t_vv = custom_threshold_vv
            otsu_vv_res = {"status": "CUSTOM", "threshold": t_vv}
        else:
            otsu_vv_res = otsu_threshold_1d(valid_vv_db, val_range=(-30.0, 5.0))
            t_vv = otsu_vv_res["threshold"]

        if custom_threshold_vh is not None:
            t_vh = custom_threshold_vh
            otsu_vh_res = {"status": "CUSTOM", "threshold": t_vh}
        else:
            otsu_vh_res = otsu_threshold_1d(valid_vh_db, val_range=(-35.0, 0.0))
            t_vh = otsu_vh_res["threshold"]

        # Compute 2D Otsu for comparative metadata
        otsu_2d_res = otsu_threshold_2d(valid_vv_db, valid_vh_db)

        if t_vv is None or t_vh is None:
            raise RuntimeError(f"Otsu threshold estimation failed: VV={otsu_vv_res}, VH={otsu_vh_res}")

        # 5. Candidate Water Mask Generation (UInt8)
        mask = np.full((h, w), MASK_NON_WATER, dtype=np.uint8)

        if self.fusion_strategy == "dual_and":
            is_water = is_valid & (vv_db <= t_vv) & (vh_db <= t_vh)
        elif self.fusion_strategy == "dual_or":
            is_water = is_valid & ((vv_db <= t_vv) | (vh_db <= t_vh))
        elif self.fusion_strategy == "vv_only":
            is_water = is_valid & (vv_db <= t_vv)
        elif self.fusion_strategy == "vh_only":
            is_water = is_valid & (vh_db <= t_vh)
        else:
            raise ValueError(f"Unknown fusion strategy: {self.fusion_strategy}")

        mask[is_water] = MASK_CANDIDATE_WATER
        mask[is_clip & (~is_nodata)] = MASK_INDETERMINATE
        mask[is_nodata] = MASK_NODATA_INVALID

        # 6. Statistics Calculation
        n_total = int(w * h)
        n_water = int(np.sum(mask == MASK_CANDIDATE_WATER))
        n_non_water = int(np.sum(mask == MASK_NON_WATER))
        n_indeterminate = int(np.sum(mask == MASK_INDETERMINATE))
        n_nodata = int(np.sum(mask == MASK_NODATA_INVALID))
        n_valid_ordinary = n_water + n_non_water

        water_area_ha = float(n_water * PIXEL_AREA_HA)
        water_area_km2 = float(n_water * PIXEL_AREA_KM2)
        total_aoi_km2 = float(n_total * PIXEL_AREA_KM2)
        valid_aoi_km2 = float(n_valid_ordinary * PIXEL_AREA_KM2)
        water_pct_valid = float((n_water / n_valid_ordinary * 100.0) if n_valid_ordinary > 0 else 0.0)

        # 7. Write Mask GeoTIFF
        driver = gdal.GetDriverByName("GTiff")
        out_ds = driver.Create(
            str(output_mask_tif),
            w,
            h,
            1,
            gdal.GDT_Byte,
            ["COMPRESS=LZW", "TILED=YES"],
        )
        out_ds.SetGeoTransform(gt)
        out_ds.SetProjection(proj)
        band = out_ds.GetRasterBand(1)
        band.WriteArray(mask)
        band.SetDescription("Candidate_Water_Mask")
        band.SetNoDataValue(MASK_NODATA_INVALID)
        out_ds.FlushCache()
        out_ds = None

        metadata = {
            "source_raster": str(input_sar_tif),
            "output_mask": str(output_mask_tif),
            "dimensions": [w, h],
            "fusion_strategy": self.fusion_strategy,
            "thresholds": {
                "vv_db": t_vv,
                "vh_db": t_vh,
                "otsu_1d_vv": otsu_vv_res,
                "otsu_1d_vh": otsu_vh_res,
                "otsu_2d": otsu_2d_res,
            },
            "pixel_counts": {
                "total": n_total,
                "candidate_water": n_water,
                "candidate_non_water": n_non_water,
                "indeterminate_clipping": n_indeterminate,
                "nodata_invalid": n_nodata,
                "valid_ordinary": n_valid_ordinary,
            },
            "area_measurements": {
                "water_area_ha": water_area_ha,
                "water_area_km2": water_area_km2,
                "valid_aoi_km2": valid_aoi_km2,
                "total_aoi_km2": total_aoi_km2,
                "water_coverage_pct_of_valid": water_pct_valid,
            },
        }

        if output_metadata_json:
            output_metadata_json = Path(output_metadata_json).resolve()
            output_metadata_json.parent.mkdir(parents=True, exist_ok=True)
            output_metadata_json.write_text(json.dumps(metadata, indent=2))

        return metadata
