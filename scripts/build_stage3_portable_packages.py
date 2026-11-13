#!/usr/bin/env python3
"""
Earth Pulse — Portable Packaging Script
NASA Space Apps Challenge 2026: Dancing with the SARs

Builds:
  1. EARTH_PULSE_PORTABLE_DEMO_DATA.zip
     Layout: data/runs/... directly at the archive root (no EarthPulse-SAR/ prefix)
     Contains: 56 verified scientific assets across both authoritative runs (2024 & 2025),
               docs/DEMO_DATA_MANIFEST.json, and INSTALL.txt.
     Integrity: Validates every scientific file against SHA-256 checksums.

  2. EARTH_PULSE_COMPLETE_APP_SOURCE_REVIEW.zip
     Layout: EarthPulse-SAR/... as top-level folder
     Contains: Complete application source, configs, models, tests, frontend
               (including frontend/scripts/run-tests.mjs and browser_smoke_test.py),
               clean seeded database (0 historical jobs), and .gitignore.
"""

import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT.parent
UPLOAD_DIR = WORKSPACE_ROOT / "EarthPulse-Upload-Ready"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DOWNLOADS_DIR = Path("/home/orr/Downloads")

DEMO_ZIP_NAME = "EARTH_PULSE_PORTABLE_DEMO_DATA.zip"
SOURCE_ZIP_NAME = "EARTH_PULSE_COMPLETE_APP_SOURCE_REVIEW.zip"

RUNS_TO_PACK = ["run_20261110_221732_1f2e94", "run_20261111_164348_f3c2b8"]
EXCLUDE_RAW_PATTERNS = ["raw_snap_"]  # Exclude ~38MB SNAP intermediates


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_portable_demo_data_zip() -> Path:
    print("\n" + "=" * 70)
    print("BUILDING PORTABLE DEMO DATA ZIP")
    print("=" * 70)

    target_zip = WORKSPACE_ROOT / DEMO_ZIP_NAME
    if target_zip.exists():
        target_zip.unlink()

    # Load manifest for verification
    manifest_path = REPO_ROOT / "docs" / "DEMO_DATA_MANIFEST.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    with open(manifest_path) as mf:
        manifest_data = json.load(mf)

    # Collect run files
    packed_files = []
    scientific_file_count = 0

    for run_id in RUNS_TO_PACK:
        run_dir = REPO_ROOT / "data" / "runs" / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")

        expected_files = {item["path"]: item for item in manifest_data["runs"][run_id]["files"]}

        for file_path in sorted(run_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if any(pat in file_path.name for pat in EXCLUDE_RAW_PATTERNS):
                continue

            rel_to_run = file_path.relative_to(run_dir).as_posix()
            if rel_to_run not in expected_files:
                raise ValueError(f"Unexpected file in {run_id}: {rel_to_run}")

            # Verify byte-for-byte SHA-256
            actual_sha = sha256_file(file_path)
            expected_sha = expected_files[rel_to_run]["sha256"]
            if actual_sha != expected_sha:
                raise ValueError(f"Checksum mismatch for {file_path}: {actual_sha} != {expected_sha}")

            # Layout: data/runs/... directly at ZIP root (NO EarthPulse-SAR/ prefix!)
            archive_path = f"data/runs/{run_id}/{rel_to_run}"
            packed_files.append((file_path, archive_path))
            scientific_file_count += 1

    if scientific_file_count != 56:
        raise ValueError(f"Expected 56 scientific files, but collected {scientific_file_count}")

    # Add manifest at docs/DEMO_DATA_MANIFEST.json
    packed_files.append((manifest_path, "docs/DEMO_DATA_MANIFEST.json"))

    # Add INSTALL.txt at ZIP root
    install_txt_path = REPO_ROOT / "INSTALL.txt"
    if not install_txt_path.exists():
        raise FileNotFoundError(f"Missing INSTALL.txt: {install_txt_path}")
    packed_files.append((install_txt_path, "INSTALL.txt"))

    packed_files.sort(key=lambda x: x[1])

    # Write zip archive
    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for disk_path, arcname in packed_files:
            zf.write(disk_path, arcname=arcname)

    # Integrity verification
    with zipfile.ZipFile(target_zip, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"Corrupted entry in demo data zip: {bad}")
        names = zf.namelist()

    # Verify no EarthPulse-SAR/ prefix
    for n in names:
        if n.startswith("EarthPulse-SAR/"):
            raise ValueError(f"Detected prohibited 'EarthPulse-SAR/' prefix in demo data ZIP: {n}")

    zip_size = target_zip.stat().st_size
    zip_sha = sha256_file(target_zip)

    # Mirror to Upload-Ready
    mirror_path = UPLOAD_DIR / DEMO_ZIP_NAME
    shutil.copy2(target_zip, mirror_path)

    print(f"Archive created: {target_zip}")
    print(f"  Entries:       {len(names)} (56 scientific files + manifest + INSTALL.txt)")
    print(f"  Size:          {zip_size:,} bytes ({zip_size / 1024 / 1024:.2f} MB)")
    print(f"  SHA-256:       {zip_sha}")
    print(f"  Root layout:   data/runs/..., docs/..., INSTALL.txt")

    return target_zip


def build_complete_app_source_zip() -> Path:
    print("\n" + "=" * 70)
    print("BUILDING COMPLETE APPLICATION SOURCE ZIP")
    print("=" * 70)

    target_zip = WORKSPACE_ROOT / SOURCE_ZIP_NAME
    if target_zip.exists():
        target_zip.unlink()

    src_includes = [
        "LICENSE", ".env.example", ".gitignore", "README.md", "INSTALL.txt", "requirements.txt",
        "Dockerfile", "docker-compose.yml", ".github/",
        "docs/", "frontend/", "graphs/", "models/", "configs/", "src/", "tests/", "scripts/",
        "data/metadata/earth_pulse_jobs.db",
        "data/metadata/earth_pulse_project_state.json",
    ]

    EXCLUDED_DIR_NAMES = {
        "node_modules", "dist", ".test_build", ".vite", ".pytest_cache",
        ".git", "__pycache__", ".venv"
    }

    def should_include(rel: str) -> bool:
        parts = rel.split("/")
        # If any part of the path is an excluded directory name, skip
        if any(p in EXCLUDED_DIR_NAMES for p in parts):
            return False
        # Data directories: only metadata files allowed
        if rel.startswith("data/") and not rel.startswith("data/metadata/"):
            return False
        for inc in src_includes:
            if rel == inc.rstrip("/") or rel.startswith(inc.rstrip("/")):
                return True
        return False

    src_files = []
    for root, dirs, files in os.walk(REPO_ROOT):
        # Don't recurse into data except metadata
        if Path(root) == REPO_ROOT:
            if "data" in dirs:
                dirs.remove("data")
            if ".git" in dirs:
                dirs.remove(".git")

        # Prune excluded directory names everywhere
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIR_NAMES]

        for f in files:
            full = Path(root) / f
            rel = full.relative_to(REPO_ROOT).as_posix()
            if should_include(rel):
                src_files.append((full, f"EarthPulse-SAR/{rel}"))

    # Explicitly include the clean metadata files
    for rel in ["data/metadata/earth_pulse_jobs.db", "data/metadata/earth_pulse_project_state.json"]:
        p = REPO_ROOT / rel
        if p.exists():
            src_files.append((p, f"EarthPulse-SAR/{rel}"))

    src_files = sorted(set(src_files), key=lambda x: x[1])

    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for disk_path, arcname in src_files:
            zf.write(disk_path, arcname=arcname)

    with zipfile.ZipFile(target_zip, "r") as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"Corrupted entry in source zip: {bad}")
        names = zf.namelist()

    zip_size = target_zip.stat().st_size
    zip_sha = sha256_file(target_zip)

    mirror_path = UPLOAD_DIR / SOURCE_ZIP_NAME
    shutil.copy2(target_zip, mirror_path)

    print(f"Archive created: {target_zip}")
    print(f"  Entries:       {len(names)}")
    print(f"  Size:          {zip_size:,} bytes ({zip_size / 1024 / 1024:.2f} MB)")
    print(f"  SHA-256:       {zip_sha}")

    return target_zip


if __name__ == "__main__":
    demo_zip = build_portable_demo_data_zip()
    source_zip = build_complete_app_source_zip()

    # Also copy to Downloads if permitted
    try:
        shutil.copy2(demo_zip, DOWNLOADS_DIR / DEMO_ZIP_NAME)
        shutil.copy2(source_zip, DOWNLOADS_DIR / SOURCE_ZIP_NAME)
        print("\nSuccessfully copied both archives to /home/orr/Downloads/")
    except Exception as e:
        print(f"\nNote: Direct copy to {DOWNLOADS_DIR} requires elevation: {e}")
