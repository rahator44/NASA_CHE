"""
Sentinel-1 Scene Selection & Comparability Evaluation Engine.
NASA Space Apps Challenge 2026: Dancing with the SARs

Enforces scientific comparability rules between SAR acquisitions:
- Identical orbital track (relative orbit number)
- Identical flight direction (ASCENDING vs DESCENDING)
- Identical polarization mode (VV+VH dual-pol required)
- Identical beam mode (IW) and processing level (GRD_HD)
- High spatial coverage of target AOI (>= 95%)
- Appropriate temporal baseline (min 6 days, max 60-120 days)
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger("EarthPulse.SceneSelector")

MIN_AOI_COVERAGE_PCT = 95.0
DEFAULT_MIN_DAYS = 6
DEFAULT_MAX_DAYS = 60


class SceneSelector:
    """
    Evaluates SAR scene suitability and multi-temporal pairing consistency.
    """

    @classmethod
    def evaluate_pair_comparability(
        cls,
        scene_1: Dict[str, Any],
        scene_2: Dict[str, Any],
        aoi_wkt: str,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Evaluate whether two Sentinel-1 scenes can be scientifically compared.
        Returns:
            (is_compatible: bool, rejection_reasons: List[str], metrics: Dict[str, Any])
        """
        rejection_reasons = []

        # 1. Flight Direction Match
        dir_1 = str(scene_1.get("orbit_direction", "")).upper()
        dir_2 = str(scene_2.get("orbit_direction", "")).upper()
        dir_match = (dir_1 == dir_2) and bool(dir_1)
        if not dir_match:
            rejection_reasons.append(f"Flight direction mismatch: {dir_1} vs {dir_2}")

        # 2. Relative Orbit Track Match
        track_1 = scene_1.get("relative_orbit")
        track_2 = scene_2.get("relative_orbit")
        track_match = (track_1 == track_2) and (track_1 is not None)
        if not track_match:
            rejection_reasons.append(f"Relative orbit track mismatch: {track_1} vs {track_2}")

        # 3. Dual Polarization Match
        pol_1 = str(scene_1.get("polarization", "")).upper()
        pol_2 = str(scene_2.get("polarization", "")).upper()
        pol_match = (pol_1 == pol_2)
        has_dual = ("VV+VH" in pol_1 or ("VV" in pol_1 and "VH" in pol_1))
        if not pol_match or not has_dual:
            rejection_reasons.append(f"Dual-polarization mismatch: {pol_1} vs {pol_2} (requires VV+VH)")

        # 4. Beam Mode & Processing Level Match
        mode_1 = scene_1.get("beam_mode", "IW")
        mode_2 = scene_2.get("beam_mode", "IW")
        level_1 = scene_1.get("processing_level", "GRD_HD")
        level_2 = scene_2.get("processing_level", "GRD_HD")

        if mode_1 != mode_2:
            rejection_reasons.append(f"Beam mode mismatch: {mode_1} vs {mode_2}")
        if level_1 != level_2:
            rejection_reasons.append(f"Processing level mismatch: {level_1} vs {level_2}")

        # 5. AOI Spatial Coverage
        cov_1 = float(scene_1.get("aoi_coverage_pct", 100.0))
        cov_2 = float(scene_2.get("aoi_coverage_pct", 100.0))
        if cov_1 < MIN_AOI_COVERAGE_PCT or cov_2 < MIN_AOI_COVERAGE_PCT:
            rejection_reasons.append(f"Incomplete AOI coverage: {cov_1:.1f}% and {cov_2:.1f}%")

        # 6. Temporal Baseline
        time_1_str = scene_1.get("acquisition_time", "")
        time_2_str = scene_2.get("acquisition_time", "")
        days_diff = None
        try:
            t1 = datetime.fromisoformat(time_1_str.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(time_2_str.replace("Z", "+00:00"))
            days_diff = abs((t2 - t1).total_seconds()) / 86400.0
        except Exception:
            pass

        metrics = {
            "flight_direction_match": dir_match,
            "track_match": track_match,
            "polarization_match": pol_match and has_dual,
            "beam_mode_match": mode_1 == mode_2,
            "processing_level_match": level_1 == level_2,
            "temporal_baseline_days": days_diff,
            "coverage_baseline_pct": cov_1,
            "coverage_change_pct": cov_2,
        }

        is_compatible = (len(rejection_reasons) == 0)
        return is_compatible, rejection_reasons, metrics

    @classmethod
    def find_all_compatible_pairs(
        cls,
        scenes: List[Dict[str, Any]],
        wkt_polygon: str,
        min_days: int = DEFAULT_MIN_DAYS,
        max_days: int = DEFAULT_MAX_DAYS,
    ) -> List[Dict[str, Any]]:
        """
        Screen all candidate pairs from a scene list and return valid pairs.
        """
        # Sort scenes chronologically
        sorted_scenes = sorted(scenes, key=lambda s: s.get("acquisition_time", ""))
        valid_pairs = []

        for i in range(len(sorted_scenes)):
            for j in range(i + 1, len(sorted_scenes)):
                s1 = sorted_scenes[i]
                s2 = sorted_scenes[j]

                is_comp, reasons, metrics = cls.evaluate_pair_comparability(s1, s2, wkt_polygon)
                days = metrics.get("temporal_baseline_days")

                if days is not None:
                    if days < min_days:
                        continue
                    if max_days and days > max_days:
                        continue

                if is_comp:
                    valid_pairs.append({
                        "baseline": s1,
                        "change": s2,
                        "temporal_baseline_days": days,
                        "metrics": metrics,
                    })

        return valid_pairs

