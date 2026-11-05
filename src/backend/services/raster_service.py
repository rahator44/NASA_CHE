"""
Raster Data Service & XYZ Map Tile Engine
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import io
import math
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from PIL import Image
from osgeo import gdal, osr

gdal.UseExceptions()
osr.UseExceptions()

logger = logging.getLogger(__name__)

from src.backend.config import settings

# Study Area Polygon (EPSG:4326) for AOI-masked tile rendering
STUDY_AREA_AOI_WKT = "POLYGON((89.55 24.58, 89.75 24.58, 89.75 24.76, 89.55 24.76, 89.55 24.58))"
STUDY_AREA_AOI_GEOJSON_VSI = "/vsimem/study_area_aoi.geojson"
STUDY_AREA_AOI_GEOJSON_STR = """{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[89.55, 24.58], [89.75, 24.58], [89.75, 24.76], [89.55, 24.76], [89.55, 24.58]]]
    }
  }]
}"""


# Pre-registered safe raster asset catalog
RASTER_CATALOG: Dict[str, Dict[str, Any]] = {
    # Phase 5: Flood Change Products (with authoritative Study AOI masking)
    "phase5_flood_transitions": {
        "relative_path": "data/processed/phase5/phase5_flood_transitions.tif",
        "layer_name": "Phase 5 Flood Transitions (Categorical)",
        "layer_type": "categorical",
        "aoi_masking": True,
        "description": "Multitemporal flood transition classes within Study AOI: 1=Persistent Water, 2=Newly Inundated, 3=Receded Water, 4=Persistent Non-Water, 5=Indeterminate Noise Floor, 6/255=NoData",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase5_flood_change",
        "palette": {
            1: [8, 81, 156, 240],     # Persistent Water (Navy Blue)
            2: [65, 182, 196, 240],   # Newly Inundated (Cyan)
            3: [254, 153, 41, 240],   # Receded Water (Orange)
            4: [200, 200, 200, 40],   # Persistent Non-Water (Light gray semi-transparent)
            5: [166, 206, 227, 180],  # Indeterminate Noise Floor (Powder Blue)
            6: [0, 0, 0, 0],          # NoData within AOI (Transparent)
            255: [0, 0, 0, 0],        # Outside Study AOI / Border NoData (Transparent)
        }
    },
    "phase5_newly_inundated": {
        "relative_path": "data/processed/phase5/phase5_newly_inundated_candidate.tif",
        "layer_name": "Phase 5 Newly Inundated Candidate Water",
        "layer_type": "categorical",
        "aoi_masking": True,
        "description": "Binary mask of newly inundated flood candidate pixels within Study AOI (1=Newly Inundated)",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase5_flood_change",
        "palette": {
            1: [65, 182, 196, 240],
            0: [0, 0, 0, 0],
            255: [0, 0, 0, 0],
        }
    },
    "phase5_persistent_water": {
        "relative_path": "data/processed/phase5/phase5_persistent_water.tif",
        "layer_name": "Phase 5 Persistent Water Mask",
        "layer_type": "categorical",
        "aoi_masking": True,
        "description": "Binary mask of persistent water present in both June and July within Study AOI",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase5_flood_change",
        "palette": {
            1: [8, 81, 156, 240],
            0: [0, 0, 0, 0],
            255: [0, 0, 0, 0],
        }
    },
    "phase5_receded_water": {
        "relative_path": "data/processed/phase5/phase5_receded_water.tif",
        "layer_name": "Phase 5 Receded Water Mask",
        "layer_type": "categorical",
        "aoi_masking": True,
        "description": "Binary mask of water receded between June and July within Study AOI",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase5_flood_change",
        "palette": {
            1: [254, 153, 41, 240],
            0: [0, 0, 0, 0],
            255: [0, 0, 0, 0],
        }
    },

    # Phase 6 & 6.1: Riverbank Channel Change Zones
    "phase6_channel_change_zones": {
        "relative_path": "data/processed/phase6_1/phase6_1_channel_change_zones.tif",
        "layer_name": "Phase 6.1 Riverbank Channel Change Zones",
        "layer_type": "categorical",
        "aoi_masking": True,
        "description": "Riverbank change zones: 12-class geomorphic codebook (Classes 0-10, 255)",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase6_riverbank_migration",
        "palette": {
            0: [0, 0, 0, 0],          # 0: Persistent Mainland Non-Water (Transparent)
            1: [8, 48, 107, 240],     # 1: Persistent Channel Water (Deep Navy Blue)
            2: [227, 26, 28, 240],    # 2: External Bank Expansion / Erosion Candidate (Bright Red)
            3: [251, 154, 153, 240],  # 3: Internal Char Submergence Candidate (Soft Pink / Coral)
            4: [51, 160, 44, 240],    # 4: Apparent Channel Contraction / Accretion (Forest Green)
            5: [178, 223, 138, 200],  # 5: Persistent Internal Char Islands (Pale Olive Green)
            6: [31, 120, 180, 240],   # 6: Disconnected Floodplain Inundation (Medium Blue)
            7: [166, 206, 227, 180],  # 7: Indeterminate Noise Floor (Powder Blue)
            8: [253, 191, 111, 220],  # 8: Persistent Floodplain Water Bodies (Soft Orange)
            9: [255, 127, 0, 220],    # 9: Receded Floodplain Water (Vivid Orange)
            10: [255, 255, 153, 220], # 10: Persistent Char Water Depressions (Pale Yellow)
            255: [0, 0, 0, 0],        # 255: Source NoData / Border (Transparent)
        }
    },

    # Phase 7A: Random Forest Probability & Classification
    "phase7a_july16_water_probability": {
        "relative_path": "data/processed/phase7a/phase7a_july16_water_probability.tif",
        "layer_name": "Phase 7A July 16 Random Forest Water Probability",
        "layer_type": "continuous",
        "description": "Continuous candidate water probability P(water) in [0.0, 1.0]",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase7a_random_forest",
        "colormap": "blues",
    },
    "phase7a_june10_water_probability": {
        "relative_path": "data/processed/phase7a/phase7a_june10_water_probability.tif",
        "layer_name": "Phase 7A June 10 Random Forest Water Probability",
        "layer_type": "continuous",
        "description": "Continuous candidate water probability P(water) in [0.0, 1.0]",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase7a_random_forest",
        "colormap": "blues",
    },
    "phase7a_july16_rf_water_classification": {
        "relative_path": "data/processed/phase7a/phase7a_july16_rf_water_classification.tif",
        "layer_name": "Phase 7A July 16 RF Water Classification (Threshold 0.35)",
        "layer_type": "categorical",
        "description": "Discrete binary classification at optimal threshold tau*=0.35",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase7a_random_forest",
        "palette": {
            1: [33, 113, 181, 240],
            0: [0, 0, 0, 0],
            255: [0, 0, 0, 0],
        }
    },
    "phase7a_july16_rf_uncertainty": {
        "relative_path": "data/processed/phase7a/phase7a_july16_rf_uncertainty.tif",
        "layer_name": "Phase 7A July 16 Decision Margin Uncertainty",
        "layer_type": "continuous",
        "description": "Decision margin uncertainty proxy: 1.0 - 2*abs(P - 0.5)",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase7a_random_forest",
        "colormap": "magma",
    },

    # Calibrated SAR Backscatter
    "june10_sigma0_vv_db": {
        "relative_path": "data/processed/phase2a/june10_sigma0_vv_db.tif",
        "layer_name": "June 10 Calibrated Sigma0 VV (dB)",
        "layer_type": "continuous",
        "description": "Radiometrically calibrated VV backscatter in decibels",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase2a_backscatter",
        "colormap": "grayscale",
    },
    "july16_sigma0_vv_db": {
        "relative_path": "data/processed/phase2a/july16_sigma0_vv_db.tif",
        "layer_name": "July 16 Calibrated Sigma0 VV (dB)",
        "layer_type": "continuous",
        "description": "Radiometrically calibrated VV backscatter in decibels",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase2a_backscatter",
        "colormap": "grayscale",
    },
    "delta_vv_db": {
        "relative_path": "data/processed/phase2a/delta_vv_db.tif",
        "layer_name": "Delta Sigma0 VV (July - June dB)",
        "layer_type": "continuous",
        "description": "Co-polarized temporal difference in decibels",
        "region_id": "jamuna_sirajganj",
        "analysis_id": "run_phase2a_backscatter",
        "colormap": "diverging",
    },
}


class RasterService:
    @staticmethod
    def list_assets(region_id: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        for asset_id, info in RASTER_CATALOG.items():
            if region_id and info.get("region_id") != region_id:
                continue

            full_path = settings.PROJECT_ROOT_DIR / info["relative_path"]
            if not full_path.exists():
                continue

            meta = RasterService._read_quick_metadata(full_path)
            results.append({
                "asset_id": asset_id,
                "region_id": info["region_id"],
                "analysis_id": info.get("analysis_id"),
                "layer_name": info["layer_name"],
                "layer_type": info["layer_type"],
                "file_format": "GeoTIFF",
                "crs": meta["crs"],
                "bounds_epsg3857": meta["bounds_epsg3857"],
                "bounds_native": meta["bounds_native"],
                "dimensions": meta["dimensions"],
                "pixel_spacing_m": meta["pixel_spacing_m"],
                "nodata_value": meta["nodata_value"],
                "band_count": meta["band_count"],
                "data_type": meta["data_type"],
                "description": info["description"],
            })
        return results

    @staticmethod
    def _read_quick_metadata(path: Path) -> Dict[str, Any]:
        ds = gdal.Open(str(path))
        gt = ds.GetGeoTransform()
        w, h = ds.RasterXSize, ds.RasterYSize
        band = ds.GetRasterBand(1)

        minx = gt[0]
        maxy = gt[3]
        maxx = minx + w * gt[1]
        miny = maxy + h * gt[5]

        # Reproject bounds to EPSG:3857
        s_srs = osr.SpatialReference()
        s_srs.ImportFromWkt(ds.GetProjectionRef())
        s_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        t_srs = osr.SpatialReference()
        t_srs.ImportFromEPSG(3857)
        t_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        ct = osr.CoordinateTransformation(s_srs, t_srs)
        p1 = ct.TransformPoint(minx, miny)
        p2 = ct.TransformPoint(maxx, maxy)

        bounds_3857 = [round(min(p1[0], p2[0]), 2), round(min(p1[1], p2[1]), 2), round(max(p1[0], p2[0]), 2), round(max(p1[1], p2[1]), 2)]

        dtype_name = gdal.GetDataTypeName(band.DataType)
        nodata = band.GetNoDataValue()

        return {
            "crs": s_srs.GetAttrValue("AUTHORITY", 0) + ":" + s_srs.GetAttrValue("AUTHORITY", 1) if s_srs.GetAttrValue("AUTHORITY", 0) else "EPSG:32645",
            "bounds_native": [round(minx, 2), round(miny, 2), round(maxx, 2), round(maxy, 2)],
            "bounds_epsg3857": bounds_3857,
            "dimensions": [h, w],
            "pixel_spacing_m": [abs(round(gt[1], 2)), abs(round(gt[5], 2))],
            "nodata_value": nodata,
            "band_count": ds.RasterCount,
            "data_type": dtype_name,
        }

    @staticmethod
    def _lookup_asset(asset_id: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        if asset_id in RASTER_CATALOG:
            return asset_id, RASTER_CATALOG[asset_id]
        for prefix in ("phase5_", "phase6_", "phase7a_"):
            cand = f"{prefix}{asset_id}"
            if cand in RASTER_CATALOG:
                return cand, RASTER_CATALOG[cand]
        for key in RASTER_CATALOG:
            for prefix in ("phase5_", "phase6_", "phase7a_"):
                if key.startswith(prefix) and key[len(prefix):] == asset_id:
                    return key, RASTER_CATALOG[key]
        return None

    @classmethod
    def get_metadata(cls, asset_id: str) -> Optional[Dict[str, Any]]:
        lookup = cls._lookup_asset(asset_id)
        if not lookup:
            return None
        resolved_id, info = lookup

        full_path = settings.PROJECT_ROOT_DIR / info["relative_path"]
        if not full_path.exists():
            return None

        ds = gdal.Open(str(full_path))
        gt = ds.GetGeoTransform()
        w, h = ds.RasterXSize, ds.RasterYSize
        band = ds.GetRasterBand(1)

        sref = ds.GetSpatialRef()
        crs_str = "EPSG:32645"
        if sref:
            code = sref.GetAuthorityCode(None)
            auth = sref.GetAuthorityName(None) or "EPSG"
            if code:
                crs_str = f"{auth}:{code}"
            else:
                crs_str = sref.GetName() or "EPSG:32645"

        return {
            "asset_id": resolved_id,
            "driver": ds.GetDriver().GetDescription(),
            "width": w,
            "height": h,
            "count": ds.RasterCount,
            "dtype": gdal.GetDataTypeName(band.DataType),
            "nodata": band.GetNoDataValue(),
            "crs": crs_str,
            "transform": [float(x) for x in gt],
            "bounds": {
                "minx": float(gt[0]),
                "miny": float(gt[3] + h * gt[5]),
                "maxx": float(gt[0] + w * gt[1]),
                "maxy": float(gt[3]),
            }
        }

    @classmethod
    def get_statistics(cls, asset_id: str) -> Optional[Dict[str, Any]]:
        lookup = cls._lookup_asset(asset_id)
        if not lookup:
            return None
        resolved_id, info = lookup

        full_path = settings.PROJECT_ROOT_DIR / info["relative_path"]
        if not full_path.exists():
            return None

        ds = gdal.Open(str(full_path))
        band_stats = []

        for b_idx in range(1, ds.RasterCount + 1):
            b = ds.GetRasterBand(b_idx)
            stats = b.GetStatistics(True, True)
            arr = b.ReadAsArray()
            nodata = b.GetNoDataValue()
            if nodata is not None:
                valid_mask = np.isfinite(arr) & (arr != nodata)
            else:
                valid_mask = np.isfinite(arr)

            band_stats.append({
                "band_index": b_idx,
                "min": round(float(stats[0]), 4),
                "max": round(float(stats[1]), 4),
                "mean": round(float(stats[2]), 4),
                "std": round(float(stats[3]), 4),
                "valid_pixel_count": int(np.sum(valid_mask)),
            })

        return {"asset_id": resolved_id, "bands": band_stats}

    @staticmethod
    def _ensure_aoi_geojson_vsi() -> None:
        """Ensure the authoritative Study AOI GeoJSON geometry is available in GDAL /vsimem."""
        if not gdal.VSIStatL(STUDY_AREA_AOI_GEOJSON_VSI):
            gdal.FileFromMemBuffer(STUDY_AREA_AOI_GEOJSON_VSI, STUDY_AREA_AOI_GEOJSON_STR.encode("utf-8"))

    @staticmethod
    def tile_to_3857_bounds(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
        origin_shift = 20037508.342789244
        res = 20037508.342789244 * 2.0 / (256.0 * (2 ** z))
        minx = -origin_shift + x * 256.0 * res
        maxx = -origin_shift + (x + 1) * 256.0 * res
        maxy = origin_shift - y * 256.0 * res
        miny = origin_shift - (y + 1) * 256.0 * res
        return minx, miny, maxx, maxy

    @classmethod
    def render_tile(cls, asset_id: str, z: int, x: int, y: int) -> bytes:
        lookup = cls._lookup_asset(asset_id)
        if not lookup:
            raise ValueError(f"Raster asset '{asset_id}' not found in catalog.")
        resolved_id, info = lookup

        full_path = settings.PROJECT_ROOT_DIR / info["relative_path"]
        if not full_path.exists():
            raise FileNotFoundError(f"Raster asset file for '{asset_id}' not found at {full_path}")

        minx, miny, maxx, maxy = cls.tile_to_3857_bounds(z, x, y)
        tile_bounds = (minx, miny, maxx, maxy)

        # Quick bbox intersection check: legitimate out-of-bounds tiles return transparent PNG
        meta = cls._read_quick_metadata(full_path)
        r_minx, r_miny, r_maxx, r_maxy = meta["bounds_epsg3857"]
        if maxx < r_minx or minx > r_maxx or maxy < r_miny or miny > r_maxy:
            return cls._blank_png_tile()

        # Select resampling: nearest neighbor for categorical, bilinear for continuous
        is_categorical = info.get("layer_type") == "categorical"
        resample_alg = gdal.GRA_NearestNeighbour if is_categorical else gdal.GRA_Bilinear
        use_aoi_mask = bool(info.get("aoi_masking"))

        if use_aoi_mask:
            cls._ensure_aoi_geojson_vsi()

        warp_kwargs: Dict[str, Any] = {
            "format": "MEM",
            "width": 256,
            "height": 256,
            "outputBounds": tile_bounds,
            "dstSRS": "EPSG:3857",
            "resampleAlg": resample_alg,
        }
        if use_aoi_mask:
            warp_kwargs["cutlineDSName"] = STUDY_AREA_AOI_GEOJSON_VSI
            warp_kwargs["dstNodata"] = 255.0 if is_categorical else -9999.0

        options = gdal.WarpOptions(**warp_kwargs)
        out_ds = gdal.Warp("", str(full_path), options=options)
        if not out_ds:
            raise RuntimeError(f"GDAL Warp failed to produce in-memory tile dataset for {asset_id} at z={z}, x={x}, y={y}")

        try:
            arr = out_ds.ReadAsArray()
            out_ds = None
            rgba = cls._colorize_array(arr, info)
            img = Image.fromarray(rgba, mode="RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            logger.error("Tile colorization/encoding failed for %s at %d/%d/%d: %s", asset_id, z, x, y, e, exc_info=True)
            raise RuntimeError(f"Tile encoding failed for {asset_id}: {e}")

    @staticmethod
    def _colorize_array(arr: np.ndarray, info: Dict[str, Any]) -> np.ndarray:
        h, w = arr.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)

        if info.get("layer_type") == "categorical":
            palette = info.get("palette", {})
            for val, color in palette.items():
                rgba[arr == val] = color
        else:
            # Continuous rendering: ensure NoData sentinel <= -9990.0 and non-finites are masked out (alpha = 0)
            cmap_type = info.get("colormap", "blues")
            valid = np.isfinite(arr) & (arr > -9990.0)

            if cmap_type == "blues":
                # Probability [0.0, 1.0]
                norm_vals = np.clip(arr, 0.0, 1.0)
                # Show only candidate water above 0.05
                show_mask = valid & (norm_vals > 0.05)
                rgba[show_mask, 0] = (255 * (1.0 - norm_vals[show_mask] * 0.8)).astype(np.uint8)
                rgba[show_mask, 1] = (255 * (1.0 - norm_vals[show_mask] * 0.5)).astype(np.uint8)
                rgba[show_mask, 2] = 220
                rgba[show_mask, 3] = (norm_vals[show_mask] * 220).astype(np.uint8)
            elif cmap_type == "grayscale":
                # dB: [-25.0, 0.0]
                norm = np.clip((arr - (-25.0)) / 25.0, 0.0, 1.0)
                gray = (norm * 255).astype(np.uint8)
                rgba[valid, 0] = gray[valid]
                rgba[valid, 1] = gray[valid]
                rgba[valid, 2] = gray[valid]
                rgba[valid, 3] = 240
            else:
                valid_vals = arr[valid]
                min_v = np.nanmin(valid_vals) if len(valid_vals) > 0 else 0.0
                max_v = np.nanmax(valid_vals) if len(valid_vals) > 0 else 1.0
                norm = np.clip((arr - min_v) / (max_v - min_v + 1e-6), 0.0, 1.0)
                gray = (norm * 255).astype(np.uint8)
                rgba[valid, 0] = gray[valid]
                rgba[valid, 1] = gray[valid]
                rgba[valid, 2] = gray[valid]
                rgba[valid, 3] = 220

        return rgba

    @staticmethod
    def _blank_png_tile() -> bytes:
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
