"""
Earth Pulse Sensor-Specific Feature Adapters
Separates sensor-specific physics, calibrations, and feature extraction from ML classifiers.
Enforces physical compatibility checks across radar frequencies (C-band vs. L-band).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from scipy.ndimage import uniform_filter


class IncompatibleSensorError(ValueError):
    """Raised when an adapter is presented with incompatible sensor metadata or data."""
    pass


class BaseSensorAdapter(ABC):
    """Abstract base class for SAR sensor-specific feature extraction and calibration."""

    @property
    @abstractmethod
    def sensor_id(self) -> str:
        """Returns the canonical sensor identifier (e.g., 'sentinel1', 'nisar')."""
        pass

    @property
    @abstractmethod
    def supported_band(self) -> str:
        """Returns the supported radar frequency band ('C-band', 'L-band', etc.)."""
        pass

    @abstractmethod
    def check_compatibility(self, metadata: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validates whether the provided dataset metadata is compatible with this adapter.
        Returns (is_compatible, reason_if_incompatible).
        """
        pass

    @abstractmethod
    def extract_features(
        self,
        vv_band: np.ndarray,
        vh_band: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
    ) -> Dict[str, np.ndarray]:
        """
        Extracts standardized model features from calibrated radar backscatter bands.
        """
        pass

    @abstractmethod
    def validate_physics_bounds(self, features: Dict[str, np.ndarray]) -> Dict[str, bool]:
        """
        Checks whether extracted features fall within physically valid bounds for this sensor.
        """
        pass


class Sentinel1GRDAdapter(BaseSensorAdapter):
    """
    Adapter for Copernicus Sentinel-1 C-band Ground Range Detected (GRD) IW acquisitions.
    Extracts the 6 canonical Earth Pulse SAR features:
      1. vv_db (copolarized sigma0 in dB)
      2. vh_db (crosspolarized sigma0 in dB)
      3. vv_minus_vh_db (polarization difference in dB)
      4. cross_pol_ratio (linear power ratio sigma0_VV / sigma0_VH)
      5. texture_vv (local standard deviation of VV in 5x5 window)
      6. texture_vh (local standard deviation of VH in 5x5 window)
    """

    @property
    def sensor_id(self) -> str:
        return "sentinel1"

    @property
    def supported_band(self) -> str:
        return "C-band"

    def check_compatibility(self, metadata: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        sensor = metadata.get("sensor") or metadata.get("sensor_id")
        if sensor and sensor != "sentinel1":
            return False, f"Incompatible sensor '{sensor}'; Sentinel1GRDAdapter requires 'sentinel1'."

        band = metadata.get("band") or metadata.get("frequency_band")
        if band and band != "C-band":
            return False, f"Incompatible frequency band '{band}'; C-band features are not directly interchangeable with {band}."

        polarizations = metadata.get("polarization") or metadata.get("polarizations", [])
        if polarizations:
            pol_upper = [p.upper() for p in polarizations]
            if "VV" not in pol_upper or "VH" not in pol_upper:
                return False, f"Sentinel-1 dual-pol adapter requires both VV and VH polarizations, found: {polarizations}."

        return True, None

    def extract_features(
        self,
        vv_band: np.ndarray,
        vh_band: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
    ) -> Dict[str, np.ndarray]:
        """
        Extracts 6 standardized SAR features from calibrated VV and VH backscatter rasters (in dB).
        """
        if vv_band.shape != vh_band.shape:
            raise ValueError(f"Shape mismatch: VV {vv_band.shape} vs VH {vh_band.shape}")

        # Polarization difference
        diff_db = vv_band - vh_band

        # Cross-pol linear power ratio clipped to [0, 100]
        ratio_linear = np.clip(10.0 ** (diff_db / 10.0), 0.0, 100.0)

        # Local spatial texture (standard deviation in 5x5 window)
        def _calc_texture(arr: np.ndarray, size: int = 5) -> np.ndarray:
            mean = uniform_filter(arr.astype(np.float64), size=size, mode='reflect')
            mean_sq = uniform_filter((arr.astype(np.float64)) ** 2, size=size, mode='reflect')
            variance = np.maximum(0.0, mean_sq - (mean ** 2))
            return np.sqrt(variance).astype(np.float32)

        tex_vv = _calc_texture(vv_band, size=5)
        tex_vh = _calc_texture(vh_band, size=5)

        features = {
            "vv_db": vv_band.astype(np.float32),
            "vh_db": vh_band.astype(np.float32),
            "vv_minus_vh_db": diff_db.astype(np.float32),
            "cross_pol_ratio": ratio_linear.astype(np.float32),
            "texture_vv": tex_vv,
            "texture_vh": tex_vh,
        }

        if valid_mask is not None:
            for k in features:
                features[k][~valid_mask] = np.nan

        return features

    def validate_physics_bounds(self, features: Dict[str, np.ndarray]) -> Dict[str, bool]:
        """
        Validates feature values against empirical physical bounds for Sentinel-1 C-band.
        """
        bounds = {
            "vv_db": (-35.0, 15.0),
            "vh_db": (-40.0, 5.0),
            "vv_minus_vh_db": (-10.0, 30.0),
            "cross_pol_ratio": (0.0, 100.0),
            "texture_vv": (0.0, 20.0),
            "texture_vh": (0.0, 20.0),
        }
        status = {}
        for feat_name, (low, high) in bounds.items():
            if feat_name not in features:
                status[feat_name] = False
                continue
            arr = features[feat_name]
            valid = arr[np.isfinite(arr)]
            if len(valid) == 0:
                status[feat_name] = False
                continue
            # Allow 1% quantile tolerance for extreme speckle spikes
            q01, q99 = np.percentile(valid, [0.1, 99.9])
            status[feat_name] = bool(q01 >= (low - 5.0) and q99 <= (high + 5.0))
        return status


class SensorAdapterRegistry:
    """Registry managing available SAR sensor adapters."""

    def __init__(self):
        self._adapters: Dict[str, BaseSensorAdapter] = {}
        # Register default Sentinel-1 adapter
        self.register_adapter(Sentinel1GRDAdapter())

    def register_adapter(self, adapter: BaseSensorAdapter) -> None:
        self._adapters[adapter.sensor_id] = adapter

    def get_adapter(self, sensor_id: str) -> BaseSensorAdapter:
        if sensor_id not in self._adapters:
            raise IncompatibleSensorError(
                f"No registered adapter for sensor '{sensor_id}'. "
                f"Registered sensors: {list(self._adapters.keys())}."
            )
        return self._adapters[sensor_id]

    def validate_sensor_compatibility(self, metadata: Dict[str, Any]) -> BaseSensorAdapter:
        sensor_id = metadata.get("sensor") or metadata.get("sensor_id")
        if not sensor_id:
            raise IncompatibleSensorError("Metadata lacks 'sensor' or 'sensor_id' specification.")
        adapter = self.get_adapter(sensor_id)
        is_compat, reason = adapter.check_compatibility(metadata)
        if not is_compat:
            raise IncompatibleSensorError(f"Compatibility check failed for sensor '{sensor_id}': {reason}")
        return adapter

