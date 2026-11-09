#!/usr/bin/env python3
"""
Packaging Script: Builds the Final EARTH_PULSE_DYNAMIC_BACKEND_REVIEW.zip.
NASA Space Apps Challenge 2026: Dancing with the SARs

Includes:
- Updated Python source (src/)
- Canonical graphs (graphs/)
- Technical reports & documentation (docs/)
- Configurations (configs/)
- Automated test suites (tests/)
- Model registry and frozen model artifact (models/)
- Verification tools & demonstration scripts (tools/, scripts/)
- Small scientific metadata & compact demo run outputs (data/runs/, data/metadata/)
- requirements.txt and README

Excludes:
- Credentials (.env, .netrc, tokens)
- Raw satellite archives (data/raw/, *.zip, *.SAFE)
- Large multi-gigabyte intermediate rasters (*.tif, *.img, *.dim)
- Python bytecode (__pycache__, *.pyc)
- .packages/ and .git/
"""

import os
import sys
import zipfile
import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path("/home/orr/NewVolume1/EarthPulse-Upload-Ready")
TARGET_ZIP = OUTPUT_DIR / "EARTH_PULSE_DYNAMIC_BACKEND_REVIEW.zip"

EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    ".packages",
    "__pycache__",
    "raw",
    "intermediate",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".swp",
    ".tmp",
    ".part",
    ".tif",
    ".tiff",
    ".img",
    ".dim",
    ".zip",
    ".SAFE",
}

EXCLUDE_FILES = {
    ".netrc",
    ".earthdata-token",
    "credentials.json",
}


def should_include_file(p: Path) -> bool:
    # Exclude credentials
    if p.name in EXCLUDE_FILES or p.name.endswith(".env") or "earthdata" in p.name.lower() and p.suffix == ".env":
        return False

    # Exclude extensions
    if p.suffix in EXCLUDE_EXTENSIONS:
        return False

    # Exclude directories
    for part in p.parts:
        if part in EXCLUDE_DIRS:
            return False

    return True


def build_review_zip():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if TARGET_ZIP.exists():
        TARGET_ZIP.unlink()

    print(f"Building review package: {TARGET_ZIP}")
    included_count = 0
    total_bytes = 0

    with zipfile.ZipFile(TARGET_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Add root project files
        for root_file in ["requirements.txt", "README.md", ".gitignore"]:
            rf_path = PROJECT_ROOT / root_file
            if rf_path.exists():
                arcname = f"EarthPulse-SAR/{root_file}"
                zf.write(rf_path, arcname=arcname)
                included_count += 1
                total_bytes += rf_path.stat().st_size

        # Walk specified source directories
        included_top_dirs = [
            "src",
            "configs",
            "graphs",
            "docs",
            "models",
            "tests",
            "tools",
            "scripts",
            "data/metadata",
            "data/outputs",
            "data/runs",
        ]

        for d_name in included_top_dirs:
            dir_path = PROJECT_ROOT / d_name
            if not dir_path.exists():
                continue

            for file_path in dir_path.rglob("*"):
                if file_path.is_file() and should_include_file(file_path):
                    rel_path = file_path.relative_to(PROJECT_ROOT)
                    arcname = f"EarthPulse-SAR/{rel_path}"
                    zf.write(file_path, arcname=arcname)
                    included_count += 1
                    total_bytes += file_path.stat().st_size

    # Verify integrity
    print(f"Verifying ZIP integrity...")
    with zipfile.ZipFile(TARGET_ZIP, "r") as zf:
        bad_file = zf.testzip()
        if bad_file:
            raise RuntimeError(f"Corrupt file inside review ZIP: {bad_file}")
        namelist = zf.namelist()

    zip_size = TARGET_ZIP.stat().st_size
    h = hashlib.sha256()
    with open(TARGET_ZIP, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    zip_sha256 = h.hexdigest()

    print("=" * 70)
    print("EARTH PULSE — FINAL REVIEW ARCHIVE VERIFICATION")
    print("=" * 70)
    print(f"Archive Path:       {TARGET_ZIP}")
    print(f"Archive Size:       {zip_size / (1024 * 1024):.2f} MB ({zip_size:,} bytes)")
    print(f"Files Packaged:     {included_count} files ({len(namelist)} archive entries)")
    print(f"Uncompressed Size:  {total_bytes / (1024 * 1024):.2f} MB ({total_bytes:,} bytes)")
    print(f"SHA-256 Checksum:   {zip_sha256}")
    print("ZIP Integrity Test: PASSED (0 checksum errors)")
    print("=" * 70)

    # Key contents verification
    required_entries = [
        "EarthPulse-SAR/src/acquisition/asf_client.py",
        "EarthPulse-SAR/src/pipeline/water_classification.py",
        "EarthPulse-SAR/src/pipeline/change_detection.py",
        "EarthPulse-SAR/src/pipeline/time_series.py",
        "EarthPulse-SAR/src/pipeline/visualization.py",
        "EarthPulse-SAR/src/backend/api/v1/endpoints/dynamic_analysis.py",
        "EarthPulse-SAR/models/phase7a/phase7a_random_forest_model.joblib",
        "EarthPulse-SAR/tests/test_scientific_visualization.py",
        "EarthPulse-SAR/docs/EARTH_PULSE_DYNAMIC_ANALYSIS_ARCHITECTURE.md",
        "EarthPulse-SAR/docs/EARTH_PULSE_DYNAMIC_SCIENTIFIC_VALIDATION.md",
        "EarthPulse-SAR/docs/EARTH_PULSE_DYNAMIC_BACKEND_HANDOFF.md",
    ]
    for req in required_entries:
        assert req in namelist, f"Missing required file in ZIP: {req}"

    print("All required core components and documentation verified inside archive.")


if __name__ == "__main__":
    build_review_zip()

