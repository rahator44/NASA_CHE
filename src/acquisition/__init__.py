"""
Earth Pulse Acquisition Package.
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from src.core.earthdata_auth import (
    EarthdataSessionManager,
    audit_earthdata_configuration,
    get_stored_token,
    save_token,
    get_netrc_credentials,
    save_netrc_credentials,
)
from src.acquisition.asf_client import ASFClient
from src.acquisition.scene_selector import SceneSelector
from src.acquisition.download_manager import DownloadManager

__all__ = [
    "EarthdataSessionManager",
    "audit_earthdata_configuration",
    "get_stored_token",
    "save_token",
    "get_netrc_credentials",
    "save_netrc_credentials",
    "ASFClient",
    "SceneSelector",
    "DownloadManager",
]
