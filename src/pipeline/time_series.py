"""
Multi-Temporal Time-Series Analysis Engine for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Features:
- Mode A (2-date comparison) and Mode B (multi-date >= 3 chronological acquisitions)
- Chronological trajectory of surface water area (ha, km2, %)
- Step-change transition analysis between consecutive observations
- Inundation frequency mapping (% of valid observations under water)
- Separation into:
  1. Persistent Water Core (water frequency >= 90%)
  2. Dynamic Flood Pulse / Seasonal Transition (10% <= frequency < 90%)
  3. Persistent Non-Water / Uplands (frequency < 10%)
- Detection of maximum flood crest and dry-season low-water observation
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

logger = logging.getLogger("EarthPulse.TimeSeries")

PIXEL_AREA_HA = 0.04
PIXEL_AREA_KM2 = 0.0004
MASK_NON_WATER = 0
MASK_CANDIDATE_WATER = 1
MASK_INDETERMINATE = 2
MASK_NODATA_INVALID = 3


class MultiDateTimeSeriesAnalyzer:
    """
    Coordinates chronological multi-observation SAR analysis.
    """

    @classmethod
    def analyze_sequence(
        cls,
        mask_records: List[Dict[str, Any]],
        output_frequency_tif: Optional[Path] = None,
        output_metadata_json: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Analyzes a chronological sequence of candidate water masks.
        Each record should contain:
          - "acquisition_time": ISO8601 string
          - "mask_tif": Path to candidate water mask GeoTIFF
        """
        if len(mask_records) < 2:
            raise ValueError(f"At least 2 observations required for time-series analysis, got {len(mask_records)}")

        # Sort chronologically by acquisition_time
        sorted_records = sorted(mask_records, key=lambda x: str(x.get("acquisition_time", "")))

        # Load first mask to determine dimensions and georeferencing
        first_path = Path(sorted_records[0]["mask_tif"]).resolve()
        ds_init = gdal.Open(str(first_path), gdal.GA_ReadOnly)
        if ds_init is None:
            raise FileNotFoundError(f"Cannot open mask: {first_path}")

        w, h = ds_init.RasterXSize, ds_init.RasterYSize
        gt = ds_init.GetGeoTransform()
        proj = ds_init.GetProjection()
        ds_init = None

        n_obs = len(sorted_records)
        water_counts = np.zeros((h, w), dtype=np.uint16)
        valid_counts = np.zeros((h, w), dtype=np.uint16)

        timeline = []

        for idx, rec in enumerate(sorted_records):
            p = Path(rec["mask_tif"]).resolve()
            ds = gdal.Open(str(p), gdal.GA_ReadOnly)
            if ds is None:
                raise FileNotFoundError(f"Cannot open mask in sequence: {p}")

            arr = ds.GetRasterBand(1).ReadAsArray()
            ds = None

            is_water = (arr == MASK_CANDIDATE_WATER)
            is_valid = (arr == MASK_NON_WATER) | is_water

            water_counts[is_water] += 1
            valid_counts[is_valid] += 1

            n_water = int(np.sum(is_water))
            n_valid = int(np.sum(is_valid))
            water_ha = float(n_water * PIXEL_AREA_HA)
            water_km2 = float(n_water * PIXEL_AREA_KM2)
            pct_valid = float((n_water / n_valid * 100.0) if n_valid > 0 else 0.0)

            timeline.append({
                "sequence_index": idx,
                "acquisition_time": rec.get("acquisition_time"),
                "scene_name": rec.get("scene_name", p.stem),
                "mask_tif": str(p),
                "water_pixels": n_water,
                "valid_pixels": n_valid,
                "water_area_ha": water_ha,
                "water_area_km2": water_km2,
                "water_pct_of_valid": pct_valid,
            })

        # Calculate step changes between consecutive observations
        step_changes = []
        for i in range(1, len(timeline)):
            t_prev = timeline[i - 1]
            t_curr = timeline[i]
            delta_km2 = t_curr["water_area_km2"] - t_prev["water_area_km2"]
            delta_pct = t_curr["water_pct_of_valid"] - t_prev["water_pct_of_valid"]

            event_type = "STABLE"
            if delta_km2 > 5.0:
                event_type = "RAPID_EXPANSION"
            elif delta_km2 < -5.0:
                event_type = "RAPID_RECESSION"

            step_changes.append({
                "from_date": t_prev["acquisition_time"],
                "to_date": t_curr["acquisition_time"],
                "delta_water_km2": float(delta_km2),
                "delta_pct_points": float(delta_pct),
                "event_type": event_type,
            })

        # Find crest and trough
        crest_obs = max(timeline, key=lambda x: x["water_area_km2"])
        trough_obs = min(timeline, key=lambda x: x["water_area_km2"])

        # Inundation frequency array (%)
        with np.errstate(divide="ignore", invalid="ignore"):
            freq_pct = np.where(valid_counts > 0, (water_counts.astype(np.float32) / valid_counts.astype(np.float32)) * 100.0, 0.0)

        # Regimes
        is_core = freq_pct >= 90.0
        is_pulse = (freq_pct >= 10.0) & (freq_pct < 90.0)
        is_dry = (freq_pct < 10.0) & (valid_counts > 0)

        core_km2 = float(np.sum(is_core) * PIXEL_AREA_KM2)
        pulse_km2 = float(np.sum(is_pulse) * PIXEL_AREA_KM2)
        dry_km2 = float(np.sum(is_dry) * PIXEL_AREA_KM2)

        # Write Inundation Frequency GeoTIFF
        if output_frequency_tif:
            output_frequency_tif = Path(output_frequency_tif).resolve()
            output_frequency_tif.parent.mkdir(parents=True, exist_ok=True)
            driver = gdal.GetDriverByName("GTiff")
            out_ds = driver.Create(
                str(output_frequency_tif),
                w,
                h,
                1,
                gdal.GDT_Float32,
                ["COMPRESS=LZW", "TILED=YES"],
            )
            out_ds.SetGeoTransform(gt)
            out_ds.SetProjection(proj)
            b = out_ds.GetRasterBand(1)
            b.WriteArray(freq_pct)
            b.SetDescription("Inundation_Frequency_Percentage")
            b.SetNoDataValue(-9999.0)
            out_ds.FlushCache()
            out_ds = None

        result = {
            "mode": "MODE_A_TWO_DATE" if n_obs == 2 else "MODE_B_MULTI_ACQUISITION",
            "observation_count": n_obs,
            "start_time": timeline[0]["acquisition_time"],
            "end_time": timeline[-1]["acquisition_time"],
            "timeline": timeline,
            "step_changes": step_changes,
            "maximum_flood_observation": crest_obs,
            "minimum_water_observation": trough_obs,
            "regimes_km2": {
                "persistent_core_water_ge_90pct": core_km2,
                "dynamic_flood_pulse_10_to_90pct": pulse_km2,
                "persistent_non_water_lt_10pct": dry_km2,
            },
            "output_frequency_raster": str(output_frequency_tif) if output_frequency_tif else None,
        }

        if output_metadata_json:
            output_metadata_json = Path(output_metadata_json).resolve()
            output_metadata_json.parent.mkdir(parents=True, exist_ok=True)
            output_metadata_json.write_text(json.dumps(result, indent=2))

        return result

