"""
Reliable Satellite Download Manager for Earth Pulse.
NASA Space Apps Challenge 2026: Dancing with the SARs

Features:
- Local cache lookup: never re-downloads existing archives
- Authenticated download streaming with chunked byte writing
- Resume support via HTTP Range headers
- SHA-256 cryptographic verification
- Storage quota enforcement and safe sanitized paths
"""

import os
import sys
import time
import zipfile
import hashlib
import logging
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from urllib.parse import urlparse

# Ensure workspace-vendored packages are accessible if present
_LOCAL_PACKAGES = Path(__file__).resolve().parent.parent.parent / ".packages"
if _LOCAL_PACKAGES.exists() and str(_LOCAL_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_LOCAL_PACKAGES))

from src.core.earthdata_auth import EarthdataSessionManager

logger = logging.getLogger("EarthPulse.DownloadManager")

DEFAULT_CACHE_DIR = Path("data/raw/sentinel1")
CHUNK_SIZE = 1024 * 1024  # 1 MB chunks
MAX_DOWNLOAD_RETRIES = 3
DEFAULT_STORAGE_QUOTA_BYTES = 25 * 1024 * 1024 * 1024  # 25 GB quota

# Permitted trusted domains for satellite data acquisition (including NASA NGAP CDN / S3)
ALLOWED_DOMAIN_SUFFIXES = (
    ".asf.alaska.edu",
    ".earthdata.nasa.gov",
    "asf.alaska.edu",
    "earthdata.nasa.gov",
    ".cloudfront.net",
    "cloudfront.net",
    ".amazonaws.com",
    "amazonaws.com",
)


def is_trusted_url(url: str) -> bool:
    """
    Validate that download URL points strictly to official NASA ASF DAAC or Earthdata domains.
    Prevents SSRF, credential exfiltration, and untrusted file downloads.
    Requires HTTPS scheme — HTTP is not permitted for authenticated satellite downloads.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
        # Correction F: HTTPS required for authenticated downloads (HTTP rejected)
        if parsed.scheme.lower() != "https":
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        return any(
            hostname == s or hostname.endswith("." + s.lstrip("."))
            for s in ALLOWED_DOMAIN_SUFFIXES
        )
    except Exception:
        return False


class DownloadManager:
    """
    Manages downloading, local caching, and integrity verification for satellite products.
    """

    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        max_quota_bytes: int = DEFAULT_STORAGE_QUOTA_BYTES,
    ):
        self.cache_dir = Path(cache_dir)
        self.max_quota_bytes = max_quota_bytes
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def check_storage_quota(self, required_bytes: int = 1_500_000_000) -> None:
        """
        Enforce disk space and quota limits before initiating multi-gigabyte downloads.
        """
        # Check cache directory size against configured quota
        current_usage = sum(
            f.stat().st_size
            for f in self.cache_dir.glob("**/*")
            if f.is_file()
        )
        if current_usage + required_bytes > self.max_quota_bytes:
            raise OSError(
                f"Storage quota exceeded: current={current_usage / 1e9:.2f} GB, "
                f"required={required_bytes / 1e9:.2f} GB, max quota={self.max_quota_bytes / 1e9:.2f} GB"
            )

        # Check actual host filesystem free disk space
        try:
            total, used, free = shutil.disk_usage(self.cache_dir)
            min_free_required = required_bytes + 1_000_000_000  # 1 GB headroom
            if free < min_free_required:
                raise OSError(
                    f"Insufficient filesystem space: free={free / 1e9:.2f} GB, "
                    f"required headroom={min_free_required / 1e9:.2f} GB"
                )
        except Exception as e:
            if isinstance(e, OSError) and "space" in str(e).lower():
                raise
            logger.debug("Filesystem free space check could not be completed: %s", e)

    def get_local_cached_file(self, scene_name: str) -> Optional[Path]:
        """
        Check if scene archive already exists locally in cache or raw directories.
        Validates archive integrity (valid zip file or valid SAFE directory).
        """
        # Sanitize scene name against path traversal
        clean_name = Path(scene_name).name.replace(".zip", "").replace(".SAFE", "")
        clean_name = "".join(c for c in clean_name if c.isalnum() or c in ("_", "-"))

        repo_root = Path(__file__).resolve().parent.parent.parent
        candidate_paths = [
            self.cache_dir / f"{clean_name}.zip",
            self.cache_dir / clean_name,
            self.cache_dir / f"{clean_name}.SAFE",
            repo_root / "data" / "raw" / "sentinel1_2025" / f"{clean_name}.zip",
            repo_root / "data" / "raw" / "sentinel1_2025" / clean_name,
            repo_root / "data" / "raw" / "sentinel1_2025" / f"{clean_name}.SAFE",
            repo_root / "data" / "raw" / "sentinel1" / f"{clean_name}.zip",
            repo_root / "data" / "raw" / "sentinel1" / clean_name,
            repo_root / "data" / "raw" / "sentinel1" / f"{clean_name}.SAFE",
            Path("data/raw/sentinel1_2025") / f"{clean_name}.zip",
            Path("data/raw/sentinel1_2025") / clean_name,
            Path("data/raw/sentinel1_2025") / f"{clean_name}.SAFE",
            Path("data/raw/sentinel1") / f"{clean_name}.zip",
            Path("data/raw/sentinel1") / clean_name,
            Path("data/raw/sentinel1") / f"{clean_name}.SAFE",
        ]
        for p in candidate_paths:
            if not p.exists():
                continue
            # If candidate is a zip file
            if p.is_file() and p.suffix.lower() == ".zip":
                if p.stat().st_size > 100_000 and zipfile.is_zipfile(p):
                    try:
                        with zipfile.ZipFile(p, "r") as zf:
                            if zf.testzip() is None:
                                return p.resolve()
                    except Exception:
                        pass
            # If candidate is a directory (SAFE format)
            elif p.is_dir():
                manifest = p / "manifest.safe"
                if manifest.exists() and manifest.stat().st_size > 0:
                    return p.resolve()
            elif p.is_file() and p.stat().st_size > 100_000:
                if zipfile.is_zipfile(p):
                    try:
                        with zipfile.ZipFile(p, "r") as zf:
                            if zf.testzip() is None:
                                return p.resolve()
                    except Exception:
                        pass
        return None

    def download_product(
        self,
        url: str,
        scene_name: str,
        expected_sha256: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Download a satellite product archive with caching, resumption, and checksum verification.
        """
        # Sanitize scene name against directory traversal
        safe_scene_name = Path(scene_name).name.replace(".zip", "").replace(".SAFE", "")
        safe_scene_name = "".join(c for c in safe_scene_name if c.isalnum() or c in ("_", "-"))

        cached = self.get_local_cached_file(safe_scene_name)
        if cached:
            logger.info("Product '%s' found in local cache: %s", safe_scene_name, cached)
            return {
                "success": True,
                "cached": True,
                "downloaded": False,
                "local_path": str(cached),
                "file_size": cached.stat().st_size,
            }

        # 1. Enforce trusted NASA/ASF domain policy
        if not is_trusted_url(url):
            raise ValueError(
                f"Untrusted download URL domain: '{url}'. "
                "Satellite downloads are strictly restricted to official NASA ASF DAAC domains (*.asf.alaska.edu, *.earthdata.nasa.gov)."
            )

        # 2. Check storage quota and filesystem space
        self.check_storage_quota(required_bytes=1_500_000_000)

        # Target file path
        target_path = self.cache_dir / f"{safe_scene_name}.zip"
        part_path = self.cache_dir / f"{safe_scene_name}.zip.part"

        session = EarthdataSessionManager.get_requests_session()

        for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
            try:
                headers = {}
                existing_bytes = 0
                if part_path.exists():
                    existing_bytes = part_path.stat().st_size
                    headers["Range"] = f"bytes={existing_bytes}-"

                logger.info("Downloading %s (attempt %d/%d, resume from %d bytes)...", safe_scene_name, attempt, MAX_DOWNLOAD_RETRIES, existing_bytes)

                # Correction F: validate HTTP redirects stay within trusted domains
                # Use allow_redirects=False, manually follow each hop, verifying every redirect URL.
                resp = session.get(url, headers=headers, stream=True, timeout=30, allow_redirects=False)
                redirect_hops = 0
                while resp.status_code in (301, 302, 303, 307, 308) and redirect_hops < 10:
                    redirect_url = resp.headers.get("Location", "")
                    if not redirect_url:
                        raise ValueError("Redirect response missing Location header.")
                    if not is_trusted_url(redirect_url):
                        raise ValueError(
                            f"Redirect to untrusted domain rejected: '{redirect_url}'. "
                            "Only official NASA/ASF domains are permitted."
                        )
                    logger.debug("Following redirect %d: %s", redirect_hops + 1, redirect_url)
                    resp = session.get(redirect_url, headers=headers, stream=True, timeout=30, allow_redirects=False)
                    redirect_hops += 1

                if resp.status_code not in (200, 206):
                    raise RuntimeError(f"HTTP {resp.status_code} from DAAC: {resp.text[:200]}")

                if resp.status_code == 206:
                    content_range = resp.headers.get("Content-Range", "")
                    m_range = re.search(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", content_range, re.IGNORECASE)
                    if m_range:
                        range_start = int(m_range.group(1))
                        if range_start != existing_bytes:
                            logger.warning(
                                "Content-Range start (%d) does not match existing bytes (%d). "
                                "Deleting partial file and resetting.",
                                range_start, existing_bytes
                            )
                            part_path.unlink(missing_ok=True)
                            existing_bytes = 0
                            mode = "wb"
                        else:
                            mode = "ab"
                    else:
                        logger.warning("HTTP 206 received without valid Content-Range header: '%s'. Resetting.", content_range)
                        part_path.unlink(missing_ok=True)
                        existing_bytes = 0
                        mode = "wb"
                    total_size = int(resp.headers.get("content-length", 0)) + existing_bytes
                else:
                    # Correction F: HTTP 200 means server did not honor the Range header — full content returned.
                    # Log a warning so the operator knows resumption was not honored.
                    if existing_bytes > 0:
                        logger.warning(
                            "Server returned HTTP 200 instead of 206 — Range header was not honored. "
                            "Partial download at %d bytes discarded; downloading full file from byte 0.",
                            existing_bytes
                        )
                        part_path.unlink(missing_ok=True)
                    mode = "wb"
                    existing_bytes = 0
                    total_size = int(resp.headers.get("content-length", 0))

                with open(part_path, mode) as f:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            existing_bytes += len(chunk)
                            if progress_callback:
                                progress_callback(existing_bytes, total_size)

                # Rename part to target
                part_path.rename(target_path)
                logger.info("Download completed successfully: %s", target_path)

                # Validate archive structure and integrity
                if not zipfile.is_zipfile(target_path):
                    target_path.unlink(missing_ok=True)
                    raise ValueError(f"Downloaded file '{target_path.name}' is not a valid zip archive.")

                with zipfile.ZipFile(target_path, "r") as zf:
                    corrupt_member = zf.testzip()
                    if corrupt_member is not None:
                        target_path.unlink(missing_ok=True)
                        raise ValueError(f"Corrupt file member '{corrupt_member}' detected in zip archive '{target_path.name}'.")

                # Optional SHA256 check
                computed_sha256 = None
                if expected_sha256:
                    h = hashlib.sha256()
                    with open(target_path, "rb") as f:
                        while b := f.read(CHUNK_SIZE):
                            h.update(b)
                    computed_sha256 = h.hexdigest()
                    if computed_sha256.lower() != expected_sha256.lower():
                        target_path.unlink()
                        raise ValueError(f"Checksum mismatch for {scene_name}: expected {expected_sha256}, got {computed_sha256}")

                return {
                    "success": True,
                    "cached": False,
                    "downloaded": True,
                    "local_path": str(target_path),
                    "file_size": target_path.stat().st_size,
                    "sha256": computed_sha256,
                }

            except Exception as e:
                logger.warning("Download attempt %d failed: %s", attempt, e)
                if attempt == MAX_DOWNLOAD_RETRIES:
                    return {
                        "success": False,
                        "cached": False,
                        "downloaded": False,
                        "error": str(e),
                    }
                time.sleep(2 * attempt)

        return {"success": False, "error": "Max retries exceeded"}

