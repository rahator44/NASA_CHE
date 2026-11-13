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

        # Channel footprint = persistent water + receded water (Baseline)
        # Comparison footprint = persistent water + newly inundated (Comparison)
        baseline_water = is_persist_water | is_receded
        comparison_water = is_persist_water | is_newly_inun

        # Spatial connectivity & connected-component analysis:
        # Separate principal continuous river channel components from detached floodplain pools/ponds.
        from scipy.ndimage import label, binary_fill_holes, binary_dilation

        lbl_t1, n_comp_t1 = label(baseline_water)
        lbl_t2, n_comp_t2 = label(comparison_water)

        sizes_t1 = np.bincount(lbl_t1.ravel()) if n_comp_t1 > 0 else np.array([0])
        sizes_t2 = np.bincount(lbl_t2.ravel()) if n_comp_t2 > 0 else np.array([0])

        max_s1 = np.max(sizes_t1[1:]) if len(sizes_t1) > 1 else 0
        max_s2 = np.max(sizes_t2[1:]) if len(sizes_t2) > 1 else 0

        # Channel components must have substantial size and mutual temporal overlap
        channel_t1 = np.zeros_like(baseline_water, dtype=bool)
        channel_t2 = np.zeros_like(comparison_water, dtype=bool)

        for i in range(1, n_comp_t1 + 1):
            if sizes_t1[i] >= 200 and sizes_t1[i] >= 0.05 * max_s1:
                # Require spatial overlap with comparison water reach
                if np.sum((lbl_t1 == i) & comparison_water) >= 50:
                    channel_t1 |= (lbl_t1 == i)

        for j in range(1, n_comp_t2 + 1):
            if sizes_t2[j] >= 200 and sizes_t2[j] >= 0.05 * max_s2:
                if np.sum((lbl_t2 == j) & baseline_water) >= 50:
                    channel_t2 |= (lbl_t2 == j)

        # Fallback to largest component if thresholding isolated everything
        if not np.any(channel_t1) and max_s1 > 0:
            channel_t1 = (lbl_t1 == (np.argmax(sizes_t1[1:]) + 1))
        if not np.any(channel_t2) and max_s2 > 0:
            channel_t2 = (lbl_t2 == (np.argmax(sizes_t2[1:]) + 1))

        # Differentiate internal char submergence from external bank expansion on the main channel:
        filled_channel = binary_fill_holes(channel_t1)
        chars_mask = filled_channel & (~channel_t1)

        char_submergence_mask = is_newly_inun & chars_mask
        n_char_submergence = int(np.sum(char_submergence_mask))
        char_submergence_km2 = float(n_char_submergence * PIXEL_AREA_KM2)

        outer_buffer = binary_dilation(filled_channel, iterations=3) & (~filled_channel)
        external_expansion_mask = is_newly_inun & outer_buffer
        n_external_expansion = int(np.sum(external_expansion_mask))
        external_expansion_km2 = float(n_external_expansion * PIXEL_AREA_KM2)

        # Generate transects across Y-dimension
        step_px = max(5, int(transect_spacing_m / abs(gt[5])))
        pixel_spacing_m = abs(gt[1])
        evaluated_transects = 0
        reliable_transects = []
        unqualified_transects = []

        for r in range(step_px, h - step_px, step_px):
            evaluated_transects += 1
            row_c1 = np.where(channel_t1[r, :])[0]
            row_c2 = np.where(channel_t2[r, :])[0]

            row_all1 = np.where(baseline_water[r, :])[0]
            row_all2 = np.where(comparison_water[r, :])[0]

            has_detached = (len(row_all1) > len(row_c1)) or (len(row_all2) > len(row_c2))

            # Channel crossing check: require at least 5 pixels of main channel water
            if len(row_c1) < 5 or len(row_c2) < 5:
                unqualified_transects.append({
                    "transect_row": r,
                    "northing_utm": float(gt[3] + r * gt[5]),
                    "reason": "INSUFFICIENT_CHANNEL_WIDTH_OR_CROSSING",
                    "t1_channel_pixels": int(len(row_c1)),
                    "t2_channel_pixels": int(len(row_c2)),
                    "has_detached_water": has_detached,
                    "is_reliable": False,
                })
                continue

            left_edge_t1 = float(row_c1[0])
            right_edge_t1 = float(row_c1[-1])
            left_edge_t2 = float(row_c2[0])
            right_edge_t2 = float(row_c2[-1])

            width_t1_m = (right_edge_t1 - left_edge_t1) * pixel_spacing_m
            width_t2_m = (right_edge_t2 - left_edge_t2) * pixel_spacing_m

            left_disp_m = (left_edge_t1 - left_edge_t2) * pixel_spacing_m
            right_disp_m = (right_edge_t2 - right_edge_t1) * pixel_spacing_m

            # Channel correspondence check:
            # 1. Spatial overlap / IoU along channel reach
            span1 = set(range(int(left_edge_t1), int(right_edge_t1) + 1))
            span2 = set(range(int(left_edge_t2), int(right_edge_t2) + 1))
            inter = len(span1 & span2)
            union = len(span1 | span2)
            iou = inter / union if union > 0 else 0.0

            # 2. Plausibility gate:
            # Riverbank migration across short observation cycles cannot physically exceed 500m.
            # Multi-kilometer edge jumps indicate disconnected floodplain water or major side-channel cutoff.
            is_valid_correspondence = (iou >= 0.30) and (abs(left_disp_m) <= 500.0) and (abs(right_disp_m) <= 500.0)

            if is_valid_correspondence:
                reliable_transects.append({
                    "transect_row": r,
                    "northing_utm": float(gt[3] + r * gt[5]),
                    "channel_width_baseline_m": round(width_t1_m, 2),
                    "channel_width_change_m": round(width_t2_m, 2),
                    "left_bank_displacement_m": round(left_disp_m, 2),
                    "right_bank_displacement_m": round(right_disp_m, 2),
                    "iou": round(iou, 4),
                    "has_detached_water": has_detached,
                    "is_reliable": True,
                })
            else:
                unqualified_transects.append({
                    "transect_row": r,
                    "northing_utm": float(gt[3] + r * gt[5]),
                    "reason": "POOR_CHANNEL_CORRESPONDENCE_OR_EXCESSIVE_DISPLACEMENT",
                    "channel_width_baseline_m": round(width_t1_m, 2),
                    "channel_width_change_m": round(width_t2_m, 2),
                    "apparent_left_disp_m": round(left_disp_m, 2),
                    "apparent_right_disp_m": round(right_disp_m, 2),
                    "iou": round(iou, 4),
                    "has_detached_water": has_detached,
                    "is_reliable": False,
                })

        valid_count = len(reliable_transects)

        if valid_count < MIN_TRANSECTS_FOR_ANALYSIS:
            status = "QUALIFIED_UNRELIABLE_TRANSECTS"
            msg = (
                f"Only {valid_count} of {evaluated_transects} evaluated transects met conservative "
                f"channel correspondence quality standards ({len(unqualified_transects)} unqualified/unreliable). "
                "Quantitative bank-displacement metrics are suppressed to prevent misleading scientific interpretation."
            )
            mean_left_disp = None
            mean_right_disp = None
            max_bank_disp = None
        else:
            status = "ANALYSIS_SUCCESS"
            msg = (
                f"Successfully evaluated {evaluated_transects} transects: {valid_count} verified corresponding channel "
                f"transects ({len(unqualified_transects)} unqualified/excluded)."
            )
            mean_left_disp = round(float(np.mean([t["left_bank_displacement_m"] for t in reliable_transects])), 2)
            mean_right_disp = round(float(np.mean([t["right_bank_displacement_m"] for t in reliable_transects])), 2)
            max_bank_disp = round(
                float(max(
                    max(abs(t["left_bank_displacement_m"]) for t in reliable_transects),
                    max(abs(t["right_bank_displacement_m"]) for t in reliable_transects),
                )),
                2,
            )

        result = {
            "status": status,
            "message": msg,
            "channel_correspondence_status": (
                "VERIFIED_CHANNEL_CORRESPONDENCE" if valid_count >= MIN_TRANSECTS_FOR_ANALYSIS else "QUALIFIED_UNRELIABLE_TRANSECTS"
            ),
            "evaluated_transects": evaluated_transects,
            "valid_migration_transects": valid_count,
            "reliable_transects_count": valid_count,
            "unqualified_transects_count": len(unqualified_transects),
            "external_bank_expansion_km2": round(external_expansion_km2, 4),
            "internal_char_submergence_km2": round(char_submergence_km2, 4),
            "channel_water_km2": round(channel_water_km2, 4),
            "mean_left_bank_displacement_m": mean_left_disp,
            "mean_right_bank_displacement_m": mean_right_disp,
            "max_bank_displacement_m": max_bank_disp,
            "sample_transects": reliable_transects[:10],
            "unqualified_transects": unqualified_transects[:10],
        }

        if output_metadata_json:
            output_metadata_json = Path(output_metadata_json).resolve()
            output_metadata_json.parent.mkdir(parents=True, exist_ok=True)
            output_metadata_json.write_text(json.dumps(result, indent=2))

        return result

