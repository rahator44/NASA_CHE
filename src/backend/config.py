"""
Earth Pulse Backend Configuration
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from pathlib import Path
from typing import List
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl_cache")

class Settings:
    PROJECT_NAME: str = "Earth Pulse SAR API"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Paths
    PROJECT_ROOT_DIR: Path = PROJECT_ROOT
    DATA_DIR: Path = PROJECT_ROOT / "data"
    CONFIGS_DIR: Path = PROJECT_ROOT / "configs"
    METADATA_DIR: Path = PROJECT_ROOT / "data/metadata"
    OUTPUTS_DIR: Path = PROJECT_ROOT / "data/outputs"
    PROCESSED_DIR: Path = PROJECT_ROOT / "data/processed"
    MODELS_DIR: Path = PROJECT_ROOT / "models"
    
    # SQLite Database
    SQLITE_DB_PATH: Path = PROJECT_ROOT / "data/metadata/earth_pulse_jobs.db"
    
    # Security & CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    
    # Tile Rendering Cache
    TILE_SIZE: int = 256
    MAX_ZOOM: int = 18
    MIN_ZOOM: int = 1

settings = Settings()
