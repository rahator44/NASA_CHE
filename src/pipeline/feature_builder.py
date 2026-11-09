"""
SAR Feature Extraction Pipeline for Machine Learning Inference and Training.
NASA Space Apps Challenge 2026: Dancing with the SARs

Authoritative Features (in strict order):
1. vv_db: Copolarized backscatter in dB (10 * log10(Sigma0_VV))
2. vh_db: Crosspolarized backscatter in dB (10 * log10(Sigma0_VH))
3. vv_minus_vh_db: Difference in dB (vv_db - vh_db)
4. cross_pol_ratio: Linear power ratio (10^(vv_minus_vh_db / 10))
5. texture_vv: Local 5x5 window standard deviation of vv_db
6. texture_vh: Local 5x5 window standard deviation of vh_db
"""

import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

import numpy as np
from osgeo import gdal
from src.ml.adapters import Sentinel1GRDAdapter

gdal.UseExceptions()

logger = logging.getLogger("EarthPulse.FeatureBuilder")

FEATURE_NAMES = [
    "vv_db",
    "vh_db",
    "vv_minus_vh_db",
    "cross_pol_ratio",
    "texture_vv",
    "texture_vh",
]

NODATA_VALUE = -9999.0
CLIPPING_FLOOR_MIN = 2.50e-11
CLIPPING_FLOOR_MAX = 2.70e-11


class SARFeatureBuilder:
    """
    Builds aligned 6-feature tensors from calibrated Sentinel-1 rasters for Random Forest inference.
    """

    def __init__(self):
        self.adapter = Sentinel1GRDAdapter()

    def extract_from_raster(
        self,
        calibrated_tif: Path,
    ) -> Dict[str, Any]:
        """
        Extracts feature dictionary and 2D arrays from a 2-band calibrated GeoTIFF (VH, VV).
        """
        calibrated_tif = Path(calibrated_tif).resolve()
        ds = gdal.Open(str(calibrated_tif), gdal.GA_ReadOnly)
        if ds is None:
            raise FileNotFoundError(f"Cannot open raster: {calibrated_tif}")

        w, h = ds.RasterXSize, ds.RasterYSize
        gt = ds.GetGeoTransform()
        proj = ds.GetProjection()

        b_vh = ds.GetRasterBand(1).ReadAsArray()
        b_vv = ds.GetRasterBand(2).ReadAsArray()
        ds = None

        # Determine if raster is in linear power or dB
        # Linear sigma0 is typically in range 0.0001 to 2.0; dB is typically -35 to +5
        # If mean is positive and < 2.0, it is linear
        finite_vh = b_vh[(b_vh != NODATA_VALUE) & np.isfinite(b_vh) & (b_vh > 0)]
        is_linear = np.median(finite_vh) < 2.0 if len(finite_vh) > 0 else True

        is_nodata = (b_vh == NODATA_VALUE) | (b_vv == NODATA_VALUE) | np.isnan(b_vh) | np.isnan(b_vv)
        is_clip = (b_vh >= CLIPPING_FLOOR_MIN) & (b_vh <= CLIPPING_FLOOR_MAX)
        valid_mask = (~is_nodata) & (~is_clip) & (b_vh > 0) & (b_vv > 0)

        if is_linear:
            # Convert linear to dB
            vh_db = np.full((h, w), np.nan, dtype=np.float32)
            vv_db = np.full((h, w), np.nan, dtype=np.float32)
            vh_db[valid_mask] = 10.0 * np.log10(b_vh[valid_mask])
            vv_db[valid_mask] = 10.0 * np.log10(b_vv[valid_mask])
        else:
            vh_db = b_vh.astype(np.float32)
            vv_db = b_vv.astype(np.float32)

        feature_maps = self.adapter.extract_features(vv_db, vh_db, valid_mask=valid_mask)
        physics_check = self.adapter.validate_physics_bounds(feature_maps)

        return {
            "feature_maps": feature_maps,
            "feature_names": FEATURE_NAMES,
            "valid_mask": valid_mask,
            "dimensions": [w, h],
            "geotransform": list(gt),
            "projection": proj,
            "physics_bounds_valid": physics_check,
            "all_features_physically_valid": all(physics_check.values()),
        }

    def prepare_feature_matrix(
        self,
        calibrated_tif: Path,
        max_samples: Optional[int] = None,
        random_seed: int = 42,
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Prepares a 2D feature matrix (N, 6) of valid pixels for model inference.
        Returns (X, pixel_coords, metadata).
        """
        extracted = self.extract_from_raster(calibrated_tif)
        valid_mask = extracted["valid_mask"]
        h, w = extracted["dimensions"][1], extracted["dimensions"][0]

        valid_rows, valid_cols = np.where(valid_mask)
        n_valid = len(valid_rows)

        if n_valid == 0:
            raise ValueError(f"No valid ordinary pixels found in raster {calibrated_tif}")

        # Stack features in canonical order
        feature_maps = extracted["feature_maps"]
        X_full = np.column_stack([feature_maps[feat][valid_mask] for feat in FEATURE_NAMES])
        coords = np.column_stack([valid_rows, valid_cols])

        if max_samples and max_samples < n_valid:
            rng = np.random.RandomState(random_seed)
            indices = rng.choice(n_valid, size=max_samples, replace=False)
            indices.sort()
            X_sample = X_full[indices]
            coords_sample = coords[indices]
            return X_sample, coords_sample, extracted

        return X_full, coords, extracted

