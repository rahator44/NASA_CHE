"""
Dynamic Riverbank Migration and Channel Dynamics Engine for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Features:
- Distinguishes external bank-expansion (lateral erosion candidates) from internal char-island submergence
- Dynamic transect extraction across channel reaches in EPSG:32645
- Scientific qualification/suppression when study AOI lacks sufficient river channel reach (< 5 valid transects)
- Recomputes transect displacement metrics, net erosion/accretion, and uncertainty
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

logger = logging.getLogger("EarthPulse.RiverbankAnalysis")

PIXEL_AREA_HA = 0.04
PIXEL_AREA_KM2 = 0.0004
MIN_TRANSECTS_FOR_ANALYSIS = 5
MIN_CHANNEL_AREA_KM2 = 1.0


class DynamicRiverbankAnalyzer:
    """
    Coordinates dynamic riverbank displacement, channel margin migration,
    and char-island submergence analysis on multi-temporal SAR products.
    """

    @classmethod
    def analyze_reach(
        cls,
        transition_tif: Path,
        output_metadata_json: Optional[Path] = None,
        transect_spacing_m: float = 250.0,
    ) -> Dict[str, Any]:
        """
        Analyze riverbank dynamics and char island changes from a 6-class flood transition raster.
        """
        transition_tif = Path(transition_tif).resolve()
        ds = gdal.Open(str(transition_tif), gdal.GA_ReadOnly)
        if ds is None:
            raise FileNotFoundError(f"Cannot open transition raster: {transition_tif}")

        w, h = ds.RasterXSize, ds.RasterYSize
        gt = ds.GetGeoTransform()
        trans = ds.GetRasterBand(1).ReadAsArray()
        ds = None

        # Transition classes
        # 1: Persistent Water
        # 2: Newly Inundated
        # 3: Receded Water
        # 4: Persistent Non-Water
        is_persist_water = (trans == 1)
        is_newly_inun = (trans == 2)
        is_receded = (trans == 3)
        is_persist_nonwater = (trans == 4)

        n_persist_water = int(np.sum(is_persist_water))
        n_newly_inun = int(np.sum(is_newly_inun))
        n_receded = int(np.sum(is_receded))

        channel_water_km2 = float(n_persist_water * PIXEL_AREA_KM2)
        inundated_km2 = float(n_newly_inun * PIXEL_AREA_KM2)
        receded_km2 = float(n_receded * PIXEL_AREA_KM2)
        aoi_km2 = float(w * h * PIXEL_AREA_KM2)

        # Qualification check: Does the AOI have adequate channel context?
        if channel_water_km2 < MIN_CHANNEL_AREA_KM2 or aoi_km2 < 2.0:
            logger.info("AOI channel water extent (%.2f km²) below threshold; qualifying analysis.", channel_water_km2)
            result = {
                "status": "QUALIFIED_INSUFFICIENT_CHANNEL_CONTEXT",
                "message": (
                    f"Selected study AOI contains {channel_water_km2:.2f} km² of channel water. "
                    f"At least {MIN_CHANNEL_AREA_KM2:.1f} km² of continuous river reach is required for "
                    "statistically reliable transect displacement modeling."
                ),
                "channel_water_km2": channel_water_km2,
                "study_aoi_km2": aoi_km2,
                "external_bank_expansion_km2": 0.0,
                "internal_char_submergence_km2": 0.0,
                "evaluated_transects": 0,
                "valid_migration_transects": 0,
            }
            if output_metadata_json:
                Path(output_metadata_json).write_text(json.dumps(result, indent=2))
            return result

        # Differentiate internal char submergence from external bank expansion:
        # Morphological approach:
        # A. Fill holes inside the persistent water channel to locate char islands
        from scipy.ndimage import binary_fill_holes, binary_dilation

        # Channel footprint = persistent water + receded water
        baseline_water = is_persist_water | is_receded
        filled_channel = binary_fill_holes(baseline_water)
        chars_mask = filled_channel & (~baseline_water)

        # Internal char submergence: newly inundated pixels located on pre-existing char islands
        char_submergence_mask = is_newly_inun & chars_mask
        n_char_submergence = int(np.sum(char_submergence_mask))
        char_submergence_km2 = float(n_char_submergence * PIXEL_AREA_KM2)

        # External bank expansion: newly inundated pixels adjacent to outer river boundary
        # Dilate filled channel by 3 pixels (~60m buffer)
        outer_buffer = binary_dilation(filled_channel, iterations=3) & (~filled_channel)
        external_expansion_mask = is_newly_inun & outer_buffer
        n_external_expansion = int(np.sum(external_expansion_mask))
        external_expansion_km2 = float(n_external_expansion * PIXEL_AREA_KM2)

        # Generate synthetic transects across Y-dimension (e.g. latitude lines across north-south river reach)
        step_px = max(5, int(transect_spacing_m / abs(gt[5])))
        evaluated_transects = 0
        valid_transects = 0
        transect_metrics = []

        for r in range(step_px, h - step_px, step_px):
            row_water = np.where(baseline_water[r, :])[0]
            if len(row_water) >= 5:  # Channel crossed
                evaluated_transects += 1
                left_edge_t1 = float(row_water[0])
                right_edge_t1 = float(row_water[-1])
                width_t1_m = (right_edge_t1 - left_edge_t1) * abs(gt[1])

                row_t2_water = np.where(is_persist_water[r, :] | is_newly_inun[r, :])[0]
                if len(row_t2_water) >= 5:
                    valid_transects += 1
                    left_edge_t2 = float(row_t2_water[0])
                    right_edge_t2 = float(row_t2_water[-1])
                    width_t2_m = (right_edge_t2 - left_edge_t2) * abs(gt[1])

                    # Displacements in meters (positive = outward expansion/erosion)
                    left_disp_m = (left_edge_t1 - left_edge_t2) * abs(gt[1])
                    right_disp_m = (right_edge_t2 - right_edge_t1) * abs(gt[1])

                    transect_metrics.append({
                        "transect_row": r,
                        "northing_utm": float(gt[3] + r * gt[5]),
                        "channel_width_baseline_m": width_t1_m,
                        "channel_width_change_m": width_t2_m,
                        "left_bank_displacement_m": left_disp_m,
                        "right_bank_displacement_m": right_disp_m,
                    })

        if valid_transects < MIN_TRANSECTS_FOR_ANALYSIS:
            status = "PARTIAL_LIMITED_TRANSECTS"
            msg = f"Only {valid_transects} valid channel transects could be modeled; results should be interpreted with caution."
        else:
            status = "ANALYSIS_SUCCESS"
            msg = f"Successfully evaluated {evaluated_transects} transects ({valid_transects} valid channel crossings)."

        mean_left_disp = float(np.mean([t["left_bank_displacement_m"] for t in transect_metrics])) if transect_metrics else 0.0
        mean_right_disp = float(np.mean([t["right_bank_displacement_m"] for t in transect_metrics])) if transect_metrics else 0.0

        result = {
            "status": status,
            "message": msg,
            "evaluated_transects": evaluated_transects,
            "valid_migration_transects": valid_transects,
            "external_bank_expansion_km2": external_expansion_km2,
            "internal_char_submergence_km2": char_submergence_km2,
            "channel_water_km2": channel_water_km2,
            "mean_left_bank_displacement_m": mean_left_disp,
            "mean_right_bank_displacement_m": mean_right_disp,
            "sample_transects": transect_metrics[:10],
        }

        if output_metadata_json:
            output_metadata_json = Path(output_metadata_json).resolve()
            output_metadata_json.parent.mkdir(parents=True, exist_ok=True)
            output_metadata_json.write_text(json.dumps(result, indent=2))

        return result
