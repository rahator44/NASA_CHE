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
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
from osgeo import gdal, osr

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

        # Validate acquisition timestamps and ensure no duplicates
        parsed_times = []
        for r in mask_records:
            t_str = str(r.get("acquisition_time", "")).strip()
            if not t_str:
                raise ValueError("Observation in time series is missing 'acquisition_time'.")
            try:
                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
            except Exception as e:
                raise ValueError(f"Invalid acquisition timestamp in time series: '{t_str}': {e}")
            parsed_times.append(dt)

        if len(set(parsed_times)) < len(parsed_times):
            raise ValueError("Duplicate acquisition timestamps detected in time-series sequence.")

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

        if not proj:
            raise ValueError(f"Reference mask '{first_path.name}' lacks a spatial reference system (CRS).")

        ref_srs = osr.SpatialReference()
        if ref_srs.ImportFromWkt(proj) != 0 or not ref_srs.IsProjected():
            raise ValueError(f"Reference mask '{first_path.name}' has non-projected or invalid CRS.")

        # Verify reference grid orientation, pixel resolution, and rotation/skew
        if abs(gt[2]) > 1e-6 or abs(gt[4]) > 1e-6:
            raise ValueError(f"Reference mask '{first_path.name}' has non-zero rotation/skew affine terms: {gt}")

        pixel_area_m2 = abs(gt[1] * gt[5])
        if abs(pixel_area_m2 - 400.0) > 2.0:
            raise ValueError(
                f"Reference mask '{first_path.name}' resolution ({abs(gt[1])}m x {abs(gt[5])}m) "
                f"does not conform to Earth Pulse 20m grid standard (expected 400.0 m², got {pixel_area_m2:.2f} m²)."
            )

        ds_init = None

        n_obs = len(sorted_records)
        water_counts = np.zeros((h, w), dtype=np.uint16)
        valid_counts = np.zeros((h, w), dtype=np.uint16)

        timeline = []
        # Store per-observation boolean arrays for common-domain calculation
        obs_water_arrays: List[np.ndarray] = []
        obs_valid_arrays: List[np.ndarray] = []

        allowed_categories = {MASK_NON_WATER, MASK_CANDIDATE_WATER, MASK_INDETERMINATE, MASK_NODATA_INVALID}

        for idx, rec in enumerate(sorted_records):
            p = Path(rec["mask_tif"]).resolve()
            ds = gdal.Open(str(p), gdal.GA_ReadOnly)
            if ds is None:
                raise FileNotFoundError(f"Cannot open mask in sequence: {p}")

            # Strict spatial alignment validation inside time-series processing
            curr_w, curr_h = ds.RasterXSize, ds.RasterYSize
            if (curr_w, curr_h) != (w, h):
                raise ValueError(
                    f"Raster dimension mismatch in time series: mask '{p.name}' ({curr_w}x{curr_h}) "
                    f"does not match sequence reference ({w}x{h})"
                )

            curr_gt = ds.GetGeoTransform()
            # Strict absolute tolerance comparison (rtol=0.0, atol=1e-6)
            # Prevents 1m - 5m origin displacements from being accepted by NumPy's default rtol=1e-5
            if not np.allclose(curr_gt, gt, rtol=0.0, atol=1e-6):
                raise ValueError(
                    f"Raster geotransform mismatch in time series: mask '{p.name}' grid does not align with reference grid "
                    f"(curr_gt={curr_gt}, ref_gt={gt})"
                )

            if abs(curr_gt[2]) > 1e-6 or abs(curr_gt[4]) > 1e-6:
                raise ValueError(f"Mask '{p.name}' has non-zero rotation/skew affine terms: {curr_gt}")

            curr_proj = ds.GetProjection()
            if not curr_proj:
                raise ValueError(f"Mask '{p.name}' is missing CRS projection.")

            curr_srs = osr.SpatialReference()
            if curr_srs.ImportFromWkt(curr_proj) != 0 or not curr_srs.IsProjected():
                raise ValueError(f"Mask '{p.name}' has non-projected or unparseable CRS.")

            if not ref_srs.IsSame(curr_srs):
                ref_code = ref_srs.GetAuthorityCode(None)
                curr_code = curr_srs.GetAuthorityCode(None)
                if ref_code is None or curr_code is None or str(ref_code) != str(curr_code):
                    raise ValueError(
                        f"Raster CRS mismatch in time series: mask '{p.name}' (EPSG:{curr_code}) "
                        f"does not match sequence reference (EPSG:{ref_code})"
                    )

            arr = ds.GetRasterBand(1).ReadAsArray()
            ds = None

            # Validate categorical mask values
            unique_vals = set(np.unique(arr))
            if not unique_vals.issubset(allowed_categories):
                raise ValueError(
                    f"Mask '{p.name}' contains invalid categorical values: {unique_vals - allowed_categories}. "
                    f"Expected subset of {allowed_categories}."
                )

            is_water = (arr == MASK_CANDIDATE_WATER)
            is_valid = (arr == MASK_NON_WATER) | is_water

            water_counts[is_water] += 1
            valid_counts[is_valid] += 1

            obs_water_arrays.append(is_water)
            obs_valid_arrays.append(is_valid)

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
                # Independent observation: water area within THIS scene's own valid mask
                "water_area_ha": water_ha,
                "water_area_km2": water_km2,
                "water_extent_independent_km2": water_km2,
                "water_pct_of_valid": pct_valid,
                "metric_note": (
                    "water_extent_independent_km2: water area over this scene's own valid pixels only. "
                    "Common-domain comparisons are in step_changes[].change_common_domain_km2."
                ),
            })

        # Calculate step changes between consecutive observations
        # IMPORTANT: Two distinct metrics are computed and labelled separately:
        #   1. water_extent_independent_km2  — each scene's water area within its own valid mask (independent observation)
        #   2. water_extent_common_domain_km2 — each scene's water area restricted to pixels valid in BOTH scenes simultaneously
        #   3. change_common_domain_km2       — Δwater over the common valid domain (comparable to transition raster result)
        # This distinction is scientifically necessary because each scene's valid mask differs,
        # so naive subtraction of independent water extents does not equal the common-domain change.
        step_changes = []
        for i in range(1, len(timeline)):
            t_prev = timeline[i - 1]
            t_curr = timeline[i]

            # Independent-observation difference (scenes have different valid masks, so this is NOT
            # the same as the common-domain pixel-transition count)
            delta_independent_km2 = t_curr["water_extent_independent_km2"] - t_prev["water_extent_independent_km2"]

            # Common-domain change: restrict to pixels valid in BOTH scenes simultaneously.
            # This is the scientifically correct comparison and matches the transition-raster result.
            common_valid = obs_valid_arrays[i - 1] & obs_valid_arrays[i]
            common_valid_pixels = int(np.sum(common_valid))
            common_valid_km2 = float(common_valid_pixels * PIXEL_AREA_KM2)

            water_prev_common = int(np.sum(obs_water_arrays[i - 1] & common_valid))
            water_curr_common = int(np.sum(obs_water_arrays[i] & common_valid))
            change_common_km2 = float((water_curr_common - water_prev_common) * PIXEL_AREA_KM2)

            delta_pct = t_curr["water_pct_of_valid"] - t_prev["water_pct_of_valid"]

            event_type = "STABLE"
            if change_common_km2 > 5.0:
                event_type = "RAPID_EXPANSION"
            elif change_common_km2 < -5.0:
                event_type = "RAPID_RECESSION"

            step_changes.append({
                "from_date": t_prev["acquisition_time"],
                "to_date": t_curr["acquisition_time"],
                # Independent observation metric (labeled to prevent confusion)
                "delta_independent_observation_km2": float(delta_independent_km2),
                "delta_independent_observation_label": (
                    "Independent-observation difference: each scene's water extent minus previous, "
                    "each measured over its own valid mask. NOT a pixel-exact transition count."
                ),
                # Common-domain metric (scientifically rigorous)
                "common_valid_domain_pixels": common_valid_pixels,
                "common_valid_domain_km2": common_valid_km2,
                "water_prev_common_domain_km2": float(water_prev_common * PIXEL_AREA_KM2),
                "water_curr_common_domain_km2": float(water_curr_common * PIXEL_AREA_KM2),
                "change_common_domain_km2": change_common_km2,
                "change_common_domain_label": (
                    "Change computed only over pixels valid in BOTH scenes simultaneously. "
                    "Matches transition-raster newly-inundated minus receded pixel count."
                ),
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

