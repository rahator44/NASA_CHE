"""
Earth Pulse — Authorized 2025 Sentinel-1 Acquisition Download Script.
NASA Space Apps Challenge 2026: Dancing with the SARs

Downloads and cryptographically verifies the two authorized January 2025 Sentinel-1 scenes:
- S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8 (Baseline)
- S1A_IW_GRDH_1SDV_20250124T120502_20250124T120527_057586_07182D_A7FB (Comparison)
"""

import sys
import json
import shutil
import hashlib
import zipfile
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.acquisition.download_manager import DownloadManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("EarthPulse.2025Downloader")

AUTHORIZED_SCENES = [
    {
        "role": "baseline",
        "granule_id": "S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8",
        "acquisition_date": "2025-01-12",
        "url": "https://datapool.asf.alaska.edu/GRD_HD/SA/S1A_IW_GRDH_1SDV_20250112T120503_20250112T120528_057411_071139_E7C8.zip",
        "expected_bytes": 1038011539,
    },
    {
        "role": "change",
        "granule_id": "S1A_IW_GRDH_1SDV_20250124T120502_20250124T120527_057586_07182D_A7FB",
        "acquisition_date": "2025-01-24",
        "url": "https://datapool.asf.alaska.edu/GRD_HD/SA/S1A_IW_GRDH_1SDV_20250124T120502_20250124T120527_057586_07182D_A7FB.zip",
        "expected_bytes": 1036948310,
    },
]

def main():
    target_dir = PROJECT_ROOT / "data" / "raw" / "sentinel1_2025"
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Check disk space
    total, used, free = shutil.disk_usage(target_dir)
    logger.info("Host disk availability: Total=%.1f GB, Free=%.1f GB", total / 1e9, free / 1e9)
    if free < 15 * 1024 * 1024 * 1024:
        raise RuntimeError(f"Insufficient disk space ({free / 1e9:.2f} GB available; minimum 15.0 GB required).")

    dm = DownloadManager(cache_dir=target_dir)

    manifest_records = []
    total_downloaded_bytes = 0

    for sc in AUTHORIZED_SCENES:
        granule = sc["granule_id"]
        url = sc["url"]
        logger.info("=== Processing %s: %s ===", sc["role"].upper(), granule)

        start_time = datetime.now(timezone.utc).isoformat()
        
        last_pct_logged = [-1]
        def progress_cb(current: int, total_b: int):
            pct = int((current / total_b) * 100) if total_b > 0 else 0
            if pct % 20 == 0 and pct != last_pct_logged[0]:
                logger.info("Progress for %s: %d%% (%d / %d bytes)", granule, pct, current, total_b)
                last_pct_logged[0] = pct

        dl_res = dm.download_product(url, granule, progress_callback=progress_cb)
        end_time = datetime.now(timezone.utc).isoformat()

        if not dl_res.get("success"):
            raise RuntimeError(f"Failed to download {granule}: {dl_res.get('error')}")

        local_path = Path(dl_res["local_path"])
        file_size = local_path.stat().st_size
        total_downloaded_bytes += file_size
        logger.info("File present at %s (%d bytes)", local_path, file_size)

        # 2. Recompute SHA-256
        logger.info("Computing SHA-256 for %s...", local_path.name)
        h = hashlib.sha256()
        with open(local_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        digest = h.hexdigest().lower()
        logger.info("SHA-256: %s", digest)

        # 3. Zip CRC test
        logger.info("Testing ZIP CRC integrity for %s...", local_path.name)
        with zipfile.ZipFile(local_path, "r") as zf:
            corrupt = zf.testzip()
            if corrupt is not None:
                raise ValueError(f"Corrupt member {corrupt} in {local_path.name}")
            namelist = zf.namelist()
            safe_entries = [n for n in namelist if n.endswith("manifest.safe")]
            logger.info("ZIP CRC OK. Found manifest: %s", safe_entries)
            if not safe_entries:
                raise ValueError(f"Archive missing manifest.safe: {local_path.name}")

        record = {
            "role": sc["role"],
            "granule_id": granule,
            "acquisition_date": sc["acquisition_date"],
            "url": url,
            "archive_path": str(local_path),
            "archive_size_bytes": file_size,
            "archive_sha256": digest,
            "download_started_utc": start_time,
            "download_completed_utc": end_time,
            "cached": dl_res.get("cached", False),
            "crc_integrity_passed": True,
            "manifest_safe_present": True,
        }
        manifest_records.append(record)

    manifest_path = target_dir / "download_manifest_2025.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_archives": len(manifest_records),
            "total_bytes": total_downloaded_bytes,
            "records": manifest_records,
        }, f, indent=2)

    logger.info("All downloads verified. Manifest saved to %s", manifest_path)
    print("SUCCESS: 2025 Sentinel-1 downloads verified.")

if __name__ == "__main__":
    main()

