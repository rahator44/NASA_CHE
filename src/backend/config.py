"""
Earth Pulse Backend Configuration
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from pathlib import Path
from typing import List, Union, Optional
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl_cache")


def _load_env_file() -> None:
    """
    Loads configuration from .env in PROJECT_ROOT if present.
    Uses python-dotenv if available, with robust manual line-parser fallback.
    Does not overwrite existing explicitly set environment variables.
    """
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except Exception:
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


_load_env_file()


class Settings:
    PROJECT_NAME: str = "Earth Pulse SAR API"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Paths (configurable via environment variables for cloud/production deployment)
    PROJECT_ROOT_DIR: Path = PROJECT_ROOT
    _data_dir_env = os.environ.get("EARTH_PULSE_DATA_DIR")
    DATA_DIR: Path = Path(_data_dir_env).resolve() if _data_dir_env else PROJECT_ROOT / "data"
    CONFIGS_DIR: Path = Path(os.environ.get("EARTH_PULSE_CONFIGS_DIR", PROJECT_ROOT / "configs"))
    METADATA_DIR: Path = DATA_DIR / "metadata"
    OUTPUTS_DIR: Path = DATA_DIR / "outputs"
    PROCESSED_DIR: Path = DATA_DIR / "processed"
    MODELS_DIR: Path = Path(os.environ.get("EARTH_PULSE_MODELS_DIR", PROJECT_ROOT / "models"))
    
    # SQLite Database (persisted under metadata dir or configurable via SQLITE_DB_PATH)
    SQLITE_DB_PATH: Path = Path(os.environ.get("SQLITE_DB_PATH", DATA_DIR / "metadata" / "earth_pulse_jobs.db"))
    
    # External Processing Tools
    SNAP_GPT_PATH: Path = Path(os.environ.get("SNAP_GPT_PATH", Path.home() / "esa-snap" / "bin" / "gpt"))

    # Security & CORS (comma-separated origins via ALLOWED_ORIGINS env var)
    _cors_env = os.environ.get("ALLOWED_ORIGINS")
    ALLOWED_ORIGINS: List[str] = (
        [o.strip() for o in _cors_env.split(",") if o.strip()]
        if _cors_env
        else [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    # Public Execution Safety (Restricted / Demo Mode)
    # Default is TRUE to ensure fail-safe public deployment.
    # When TRUE, unauthenticated public callers cannot submit new analysis jobs
    # that trigger satellite downloads or expensive SNAP processing.
    # Set DEMO_MODE_RESTRICTED_EXECUTION=false only in private/authenticated environments.
    DEMO_MODE_RESTRICTED_EXECUTION: bool = os.environ.get(
        "DEMO_MODE_RESTRICTED_EXECUTION", "true"
    ).lower() in ("true", "1", "yes")
    
    # Tile Rendering Cache
    TILE_SIZE: int = 256
    MAX_ZOOM: int = 18
    MIN_ZOOM: int = 1

    # AOI validation limits (Correction E)
    # Maximum user-submitted polygon area in km². Polygons exceeding this
    # will be rejected before creating a run, to prevent exhausting resources.
    AOI_MAX_AREA_KM2: float = 200.0

    # Jamuna study region outer boundary — loose bounding box for the SRTM/Copernicus DEM
    # coverage and ASF-indexed scenes for the Jamuna Sirajganj region.
    # User AOIs must intersect this region (not be entirely disjoint).
    JAMUNA_STUDY_REGION_WKT: str = (
        "POLYGON((89.0 24.0, 90.5 24.0, 90.5 25.5, 89.0 25.5, 89.0 24.0))"
    )

    def resolve_data_path(self, rel_path: Union[str, Path]) -> Path:
        """
        Centrally and safely resolves a relative scientific asset path against DATA_DIR.
        Handles legacy paths prefixed with 'data/' without duplicating the prefix.
        Prevents directory traversal outside permitted roots.
        """
        p_str = str(rel_path).strip()
        p = Path(p_str)
        if p.is_absolute():
            resolved = p.resolve()
            permitted = [
                self.DATA_DIR.resolve(),
                self.MODELS_DIR.resolve(),
                self.CONFIGS_DIR.resolve(),
                self.PROJECT_ROOT_DIR.resolve(),
            ]
            if not any(resolved == perm or perm in resolved.parents for perm in permitted):
                raise ValueError(f"Path traversal detected: {p_str} is outside permitted storage directories.")
            return resolved

        clean_rel = p_str.lstrip("/")
        if clean_rel == "data":
            target = self.DATA_DIR
        elif clean_rel.startswith("data/"):
            target = self.DATA_DIR / clean_rel[5:]
        elif clean_rel.startswith("models/"):
            target = self.MODELS_DIR / clean_rel[7:]
        elif clean_rel.startswith("configs/"):
            target = self.CONFIGS_DIR / clean_rel[8:]
        else:
            target = self.DATA_DIR / clean_rel

        resolved_target = target.resolve()
        base_dir = self.DATA_DIR.resolve()
        if clean_rel.startswith("models/"):
            base_dir = self.MODELS_DIR.resolve()
        elif clean_rel.startswith("configs/"):
            base_dir = self.CONFIGS_DIR.resolve()

        if resolved_target != base_dir and base_dir not in resolved_target.parents:
            raise ValueError(f"Path traversal detected: {rel_path} escapes permitted directory {base_dir}")

        return resolved_target


settings = Settings()
