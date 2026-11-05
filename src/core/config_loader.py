"""
Earth Pulse Configuration Loader and Schema Validator
Provides unified configuration loading for multi-region, multi-sensor SAR machine learning.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

CONFIG_ROOT = Path(__file__).resolve().parent.parent.parent / "configs"


class ConfigValidationError(ValueError):
    """Raised when a configuration file fails required schema validation."""
    pass


def get_config_root() -> Path:
    """Returns the base configs/ directory path."""
    return CONFIG_ROOT


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Loads and returns parsed YAML file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigValidationError(f"Invalid YAML content in {file_path}, expected dictionary.")
    return data


def load_region_config(region_identifier: str, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Loads and validates a region configuration YAML file.
    Can accept either a region identifier (e.g., 'jamuna_sirajganj') or an explicit file path.
    """
    base = base_dir or (CONFIG_ROOT / "regions")
    if region_identifier.endswith(".yaml") or region_identifier.endswith(".yml"):
        cfg_path = Path(region_identifier)
        if not cfg_path.is_absolute():
            cfg_path = base / cfg_path
    else:
        cfg_path = base / f"{region_identifier}.yaml"

    cfg = load_yaml(cfg_path)
    validate_region_config(cfg, cfg_path)
    return cfg


def validate_region_config(cfg: Dict[str, Any], path_context: Optional[Path] = None) -> None:
    """Validates required keys and structure of a region configuration."""
    required_keys = ["region_id", "region_name", "aoi", "grid", "acquisitions", "reference_labels"]
    for k in required_keys:
        if k not in cfg:
            raise ConfigValidationError(f"Missing required key '{k}' in region config {path_context or ''}")

    aoi = cfg["aoi"]
    if "wkt" not in aoi or "bbox" not in aoi:
        raise ConfigValidationError(f"AOI section must contain 'wkt' and 'bbox' in {path_context or ''}")

    grid = cfg["grid"]
    grid_req = ["crs", "pixel_spacing_m", "raster_width", "raster_height", "origin_x", "origin_y"]
    for gk in grid_req:
        if gk not in grid:
            raise ConfigValidationError(f"Grid section missing required property '{gk}' in {path_context or ''}")

    acquisitions = cfg["acquisitions"]
    if not isinstance(acquisitions, dict) or len(acquisitions) == 0:
        raise ConfigValidationError(f"Region must define at least one acquisition in {path_context or ''}")


def load_sensor_config(sensor_identifier: str, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Loads and validates a sensor configuration YAML file."""
    base = base_dir or (CONFIG_ROOT / "sensors")
    if sensor_identifier.endswith(".yaml") or sensor_identifier.endswith(".yml"):
        cfg_path = Path(sensor_identifier)
        if not cfg_path.is_absolute():
            cfg_path = base / cfg_path
    else:
        cfg_path = base / f"{sensor_identifier}.yaml"

    cfg = load_yaml(cfg_path)
    validate_sensor_config(cfg, cfg_path)
    return cfg


def validate_sensor_config(cfg: Dict[str, Any], path_context: Optional[Path] = None) -> None:
    """Validates required keys of a sensor configuration."""
    req_keys = ["sensor_id", "sensor_name", "radar_properties", "physical_limits", "compatibility"]
    for k in req_keys:
        if k not in cfg:
            raise ConfigValidationError(f"Missing required key '{k}' in sensor config {path_context or ''}")


def load_model_config(model_name: str = "random_forest", base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Loads and validates a model configuration YAML file."""
    base = base_dir or (CONFIG_ROOT / "models")
    if model_name.endswith(".yaml") or model_name.endswith(".yml"):
        cfg_path = Path(model_name)
        if not cfg_path.is_absolute():
            cfg_path = base / cfg_path
    else:
        cfg_path = base / f"{model_name}.yaml"

    cfg = load_yaml(cfg_path)
    req_keys = ["model_type", "hyperparameters", "decision_thresholds", "features_required"]
    for k in req_keys:
        if k not in cfg:
            raise ConfigValidationError(f"Missing required key '{k}' in model config {cfg_path}")
    return cfg


def load_feature_schema(schema_name: str = "sar_features", base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Loads and validates a feature schema configuration YAML file."""
    base = base_dir or (CONFIG_ROOT / "features")
    if schema_name.endswith(".yaml") or schema_name.endswith(".yml"):
        cfg_path = Path(schema_name)
        if not cfg_path.is_absolute():
            cfg_path = base / cfg_path
    else:
        cfg_path = base / f"{schema_name}.yaml"

    cfg = load_yaml(cfg_path)
    if "feature_schema_version" not in cfg or "features" not in cfg:
        raise ConfigValidationError(f"Missing schema version or features in {cfg_path}")
    return cfg

