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
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

logger = logging.getLogger("EarthPulse.SceneSelector")

MIN_AOI_COVERAGE_PCT = 95.0
DEFAULT_MIN_DAYS = 6
DEFAULT_MAX_DAYS = 60

REQUIRED_SCENE_FIELDS = (
    "scene_name",
    "acquisition_time",
    "relative_orbit",
    "orbit_direction",
    "polarization",
    "beam_mode",
    "processing_level",
    "aoi_coverage_pct",
)


def validate_relative_orbit(track: Any) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Validate Sentinel-1 relative orbit track number.
    Must be a finite positive whole integer in the range [1, 175].
    Fails closed without throwing uncaught exceptions on NaN, Inf, non-integer floats,
    boolean values, unparseable strings, or out-of-range track numbers.
    Returns:
        (is_valid: bool, track_int: Optional[int], error_message: Optional[str])
    """
    if track is None:
        return False, None, "Relative orbit track is missing (None)"
    if isinstance(track, bool):
        return False, None, "Relative orbit cannot be a boolean value"
    if isinstance(track, (float, np.floating)):
        if math.isnan(track) or math.isinf(track):
            return False, None, f"Relative orbit cannot be NaN or infinite: {track}"
        if not float(track).is_integer():
            return False, None, f"Relative orbit must be a whole integer: {track}"
        track_val = int(track)
    elif isinstance(track, (int, np.integer)):
        track_val = int(track)
    elif isinstance(track, str):
        s = track.strip()
        if not s.isdigit():
            return False, None, f"Relative orbit string must contain only digits: '{track}'"
        track_val = int(s)
    else:
        return False, None, f"Unsupported data type for relative orbit: {type(track).__name__}"

    if not (1 <= track_val <= 175):
        return False, None, f"Relative orbit {track_val} is out of Sentinel-1 range [1, 175]"

    return True, track_val, None


class SceneSelector:
    """
    Evaluates SAR scene suitability and multi-temporal pairing consistency.
    Fails closed on missing or unverified satellite scene metadata.
    """

    @classmethod
    def validate_scene_metadata(cls, scene: Dict[str, Any]) -> List[str]:
        """
        Strict scientific metadata validation for Sentinel-1 scenes.
        Fails closed on missing, ambiguous, or invalid metadata.
        """
        errors = []
        if not isinstance(scene, dict):
            return ["Scene record is not a dictionary"]

        for f in REQUIRED_SCENE_FIELDS:
            if f not in scene or scene[f] is None:
                errors.append(f"Missing required metadata field: '{f}'")

        if errors:
            return errors

        # 1. Scene Name
        name = str(scene.get("scene_name", "")).strip()
        if not name:
            errors.append("Scene name is empty")

        # 2. Acquisition Time (must be parseable ISO datetime)
        acq_time = str(scene.get("acquisition_time", "")).strip()
        try:
            dt = datetime.fromisoformat(acq_time.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                errors.append(f"Acquisition time must be timezone-aware UTC: '{acq_time}'")
        except Exception:
            errors.append(f"Unparseable acquisition timestamp: '{acq_time}'")

        # 3. Relative Orbit (track number)
        track = scene.get("relative_orbit")
        is_valid_track, _, track_err = validate_relative_orbit(track)
        if not is_valid_track:
            errors.append(f"Invalid relative orbit track: {track_err}")

        # 4. Flight Direction
        flight_dir = str(scene.get("orbit_direction", "")).strip().upper()
        if flight_dir not in ("ASCENDING", "DESCENDING"):
            errors.append(f"Invalid orbit direction: '{flight_dir}' (expected ASCENDING or DESCENDING)")

        # 5. Dual Polarization
        pol = str(scene.get("polarization", "")).strip().upper()
        has_dual = ("VV+VH" in pol) or ("VH+VV" in pol) or ("VV" in pol and "VH" in pol)
        if not has_dual:
            errors.append(f"Unsupported polarization: '{pol}' (Earth Pulse requires dual-polarization VV+VH)")

        # 6. Beam Mode
        bm = str(scene.get("beam_mode", "")).strip().upper()
        if bm != "IW":
            errors.append(f"Unsupported beam mode: '{bm}' (expected IW)")

        # 7. Processing Level
        pl = str(scene.get("processing_level", "")).strip().upper()
        if pl not in ("GRD_HD", "GRD"):
            errors.append(f"Unsupported processing level: '{pl}' (expected GRD_HD or GRD)")

        # 8. AOI Spatial Coverage
        cov = scene.get("aoi_coverage_pct")
        try:
            cov_f = float(cov)
            if not np.isfinite(cov_f):
                errors.append(f"Non-finite AOI coverage percentage: {cov}")
            elif cov_f < 0.0 or cov_f > 100.0:
                errors.append(f"Out-of-range AOI coverage percentage: {cov_f:.2f}% (must be 0-100%)")
            elif cov_f < MIN_AOI_COVERAGE_PCT:
                errors.append(f"Insufficient AOI coverage: {cov_f:.2f}% (minimum required: {MIN_AOI_COVERAGE_PCT:.1f}%)")
        except (ValueError, TypeError):
            errors.append(f"Unparseable AOI coverage percentage: {cov}")

        return errors

    @classmethod
    def evaluate_pair_comparability(
        cls,
        scene_1: Dict[str, Any],
        scene_2: Dict[str, Any],
        aoi_wkt: str,
        min_days: int = DEFAULT_MIN_DAYS,
        max_days: Optional[int] = DEFAULT_MAX_DAYS,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Evaluate whether two Sentinel-1 scenes can be scientifically compared.
        Fails closed on missing or unverified metadata without using defaults.
        Returns:
            (is_compatible: bool, rejection_reasons: List[str], metrics: Dict[str, Any])
        """
        rejection_reasons = []

        # Validate individual scenes first — fail closed on missing metadata
        errs_1 = cls.validate_scene_metadata(scene_1)
        errs_2 = cls.validate_scene_metadata(scene_2)
        if errs_1:
            rejection_reasons.extend([f"Scene 1 ({scene_1.get('scene_name', 'unknown')}): {e}" for e in errs_1])
        if errs_2:
            rejection_reasons.extend([f"Scene 2 ({scene_2.get('scene_name', 'unknown')}): {e}" for e in errs_2])

        # 1. Flight Direction Match
        dir_1 = str(scene_1.get("orbit_direction", "")).strip().upper()
        dir_2 = str(scene_2.get("orbit_direction", "")).strip().upper()
        dir_match = bool(dir_1 and dir_2 and dir_1 == dir_2 and dir_1 in ("ASCENDING", "DESCENDING"))
        if not dir_1 or not dir_2:
            rejection_reasons.append("Orbit direction missing in one or both scenes")
        elif dir_1 != dir_2:
            rejection_reasons.append(f"Flight direction mismatch: {dir_1} vs {dir_2}")

        # 2. Relative Orbit Track Match
        track_1 = scene_1.get("relative_orbit")
        track_2 = scene_2.get("relative_orbit")
        v1, int_1, err_1 = validate_relative_orbit(track_1)
        v2, int_2, err_2 = validate_relative_orbit(track_2)
        track_match = bool(v1 and v2 and int_1 == int_2)
        if not v1 or not v2:
            rejection_reasons.append(f"Relative orbit track invalid or missing: scene 1 ({err_1 or 'ok'}), scene 2 ({err_2 or 'ok'})")
        elif not track_match:
            rejection_reasons.append(f"Relative orbit track mismatch: {int_1} vs {int_2}")

        # 3. Dual Polarization Match
        pol_1 = str(scene_1.get("polarization", "")).strip().upper()
        pol_2 = str(scene_2.get("polarization", "")).strip().upper()
        has_dual_1 = ("VV+VH" in pol_1 or "VH+VV" in pol_1 or ("VV" in pol_1 and "VH" in pol_1))
        has_dual_2 = ("VV+VH" in pol_2 or "VH+VV" in pol_2 or ("VV" in pol_2 and "VH" in pol_2))
        pol_match = bool(pol_1 and pol_2 and pol_1 == pol_2 and has_dual_1 and has_dual_2)
        if not pol_1 or not pol_2:
            rejection_reasons.append("Polarization missing in one or both scenes")
        elif pol_1 != pol_2 or not (has_dual_1 and has_dual_2):
            rejection_reasons.append(f"Dual-polarization mismatch: {pol_1} vs {pol_2}")

        # 4. Beam Mode & Processing Level Match
        mode_1 = str(scene_1.get("beam_mode", "")).strip().upper()
        mode_2 = str(scene_2.get("beam_mode", "")).strip().upper()
        level_1 = str(scene_1.get("processing_level", "")).strip().upper()
        level_2 = str(scene_2.get("processing_level", "")).strip().upper()

        if not mode_1 or not mode_2:
            rejection_reasons.append("Beam mode missing in one or both scenes")
        elif mode_1 != mode_2:
            rejection_reasons.append(f"Beam mode mismatch: {mode_1} vs {mode_2}")

        if not level_1 or not level_2:
            rejection_reasons.append("Processing level missing in one or both scenes")
        elif level_1 != level_2:
            rejection_reasons.append(f"Processing level mismatch: {level_1} vs {level_2}")

        # 5. AOI Spatial Coverage
        cov_1 = scene_1.get("aoi_coverage_pct")
        cov_2 = scene_2.get("aoi_coverage_pct")
        try:
            cov_1_f = float(cov_1) if cov_1 is not None else -1.0
        except (ValueError, TypeError):
            cov_1_f = -1.0
        try:
            cov_2_f = float(cov_2) if cov_2 is not None else -1.0
        except (ValueError, TypeError):
            cov_2_f = -1.0

        if cov_1 is None or cov_2 is None:
            rejection_reasons.append("AOI coverage percentage missing in one or both scenes")
        elif cov_1_f < MIN_AOI_COVERAGE_PCT or cov_2_f < MIN_AOI_COVERAGE_PCT:
            rejection_reasons.append(f"Incomplete AOI coverage: {cov_1_f:.1f}% and {cov_2_f:.1f}%")

        # 6. Temporal Baseline
        time_1_str = str(scene_1.get("acquisition_time", "")).strip()
        time_2_str = str(scene_2.get("acquisition_time", "")).strip()
        days_diff = None
        if not time_1_str or not time_2_str:
            rejection_reasons.append("Acquisition timestamp missing in one or both scenes")
        else:
            try:
                t1 = datetime.fromisoformat(time_1_str.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(time_2_str.replace("Z", "+00:00"))
                days_diff = abs((t2 - t1).total_seconds()) / 86400.0
                if days_diff < min_days:
                    rejection_reasons.append(f"Temporal baseline too short: {days_diff:.1f} days < {min_days} days")
                if max_days and days_diff > max_days:
                    rejection_reasons.append(f"Temporal baseline too long: {days_diff:.1f} days > {max_days} days")
            except Exception as e:
                rejection_reasons.append(f"Invalid acquisition timestamp: {e}")

        metrics = {
            "flight_direction_match": dir_match,
            "track_match": track_match,
            "polarization_match": pol_match,
            "beam_mode_match": bool(mode_1 and mode_2 and mode_1 == mode_2),
            "processing_level_match": bool(level_1 and level_2 and level_1 == level_2),
            "temporal_baseline_days": days_diff,
            "coverage_baseline_pct": cov_1_f if cov_1 is not None else None,
            "coverage_change_pct": cov_2_f if cov_2 is not None else None,
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
        # Filter scenes to only those passing individual validation
        valid_scenes = []
        for s in scenes:
            errs = cls.validate_scene_metadata(s)
            if not errs:
                valid_scenes.append(s)
            else:
                logger.debug("Excluded scene '%s' from pair search: %s", s.get("scene_name"), "; ".join(errs))

        # Sort scenes chronologically
        sorted_scenes = sorted(valid_scenes, key=lambda s: s.get("acquisition_time", ""))
        valid_pairs = []

        for i in range(len(sorted_scenes)):
            for j in range(i + 1, len(sorted_scenes)):
                s1 = sorted_scenes[i]
                s2 = sorted_scenes[j]

                is_comp, reasons, metrics = cls.evaluate_pair_comparability(
                    s1, s2, wkt_polygon, min_days=min_days, max_days=max_days
                )
                if is_comp:
                    valid_pairs.append({
                        "baseline": s1,
                        "change": s2,
                        "temporal_baseline_days": metrics.get("temporal_baseline_days"),
                        "metrics": metrics,
                    })

        return valid_pairs

