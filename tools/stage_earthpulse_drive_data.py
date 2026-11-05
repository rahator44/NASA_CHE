#!/usr/bin/env python3
"""EarthPulse-SAR — Google Drive Scientific Data Staging Tool.

Phase 8.3: Automated GitHub & Google Drive Project Handoff
NASA Space Apps Challenge 2026 — Dancing with the SARs

This utility reads data/outputs/phase8_3/drive_upload_inventory.csv and stages the
large scientific datasets into the standardized 8-folder Google Drive hierarchy
using hardlinks (0-byte disk overhead) or copies.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import sys
from pathlib import Path


SUBFOLDER_DESCRIPTIONS = {
    "01_Sentinel1_Raw": "Original Sentinel-1 GRD SAR Level-1 archives (June 10 & July 16, 2024)",
    "02_Sentinel2_Raw": "Sentinel-2 MSI Level-2A optical reference archives & extracted JP2 bands",
    "03_Processed_GeoTIFF": "Radiometrically calibrated Sigma0 backscatter rasters and flood maps",
    "04_Reference_Data": "External hydrological and terrain reference datasets",
    "05_Model_Artifacts": "Trained Phase 7A Random Forest model and ML artifacts",
    "06_Large_Scientific_Outputs": "High-resolution change visualization maps (>5MB)",
    "07_Manifests_and_Checksums": "File transfer manifests, SQLite state, and verification hashes",
    "08_Backup_and_Restore": "Automated data restoration scripts, instructions, and SHA-256 baseline",
}


def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def stage_drive_data(
    repo_root: Path,
    staging_dir: Path,
    inventory_path: Path,
    mode: str = "hardlink",
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    print("=" * 70)
    print("EARTH PULSE — GOOGLE DRIVE DATA STAGING")
    print(f"Repository Root:    {repo_root}")
    print(f"Staging Directory:  {staging_dir}")
    print(f"Drive Inventory:    {inventory_path}")
    print(f"Staging Mode:       {mode}")
    print("=" * 70)

    if not inventory_path.exists():
        print(f"[ERROR] Inventory not found at {inventory_path}")
        return 1

    # Create the 8 subdirectories
    for folder_name in SUBFOLDER_DESCRIPTIONS:
        sub_path = staging_dir / folder_name
        if not dry_run:
            sub_path.mkdir(parents=True, exist_ok=True)

    staged_count = 0
    total_bytes = 0
    errors = 0

    with open(inventory_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rel_path = row["relative_path"]
            subfolder = row["drive_subfolder"]
            file_size = int(row["file_size_bytes"])
            expected_sha = row["sha256_checksum"]

            source_file = repo_root / rel_path
            if not source_file.exists():
                print(f"  [MISSING] Source file missing: {source_file}")
                errors += 1
                continue

            # Determine destination path within the subfolder
            # Preserve internal folder hierarchy within the subfolder
            if subfolder == "01_Sentinel1_Raw":
                dest_file = staging_dir / subfolder / source_file.name
            elif subfolder == "02_Sentinel2_Raw":
                # Preserve structure relative to data/reference/optical/sentinel2
                prefix = "data/reference/optical/sentinel2/"
                if rel_path.startswith(prefix):
                    rel_sub = rel_path[len(prefix):]
                else:
                    rel_sub = source_file.name
                dest_file = staging_dir / subfolder / rel_sub
            elif subfolder == "03_Processed_GeoTIFF":
                # Keep relative path under data/
                prefix = "data/"
                if rel_path.startswith(prefix):
                    rel_sub = rel_path[len(prefix):]
                else:
                    rel_sub = source_file.name
                dest_file = staging_dir / subfolder / rel_sub
            elif subfolder == "05_Model_Artifacts":
                dest_file = staging_dir / subfolder / source_file.name
            elif subfolder == "06_Large_Scientific_Outputs":
                dest_file = staging_dir / subfolder / source_file.name
            elif subfolder == "07_Manifests_and_Checksums":
                prefix = "data/"
                if rel_path.startswith(prefix):
                    rel_sub = rel_path[len(prefix):]
                else:
                    rel_sub = source_file.name
                dest_file = staging_dir / subfolder / rel_sub
            else:
                dest_file = staging_dir / subfolder / source_file.name

            if dry_run:
                if verbose:
                    print(f"  [DRY-RUN] {source_file.name} -> {dest_file.relative_to(staging_dir)}")
                staged_count += 1
                total_bytes += file_size
                continue

            dest_file.parent.mkdir(parents=True, exist_ok=True)

            if dest_file.exists():
                dest_file.unlink()

            try:
                if mode == "hardlink":
                    os.link(source_file, dest_file)
                elif mode == "symlink":
                    dest_file.symlink_to(source_file.resolve())
                else:
                    shutil.copy2(source_file, dest_file)

                staged_count += 1
                total_bytes += file_size
                if verbose:
                    print(f"  [STAGED] {dest_file.relative_to(staging_dir)} ({file_size / 1024 / 1024:.2f} MB)")
            except Exception as e:
                print(f"  [ERROR] Staging failed for {rel_path}: {e}")
                errors += 1

    # Stage 08_Backup_and_Restore utilities
    backup_restore_dir = staging_dir / "08_Backup_and_Restore"
    if not dry_run:
        backup_restore_dir.mkdir(parents=True, exist_ok=True)
        # Copy restoration script
        restore_script = repo_root / "tools/restore_earthpulse_data.py"
        if restore_script.exists():
            shutil.copy2(restore_script, backup_restore_dir / "restore_earthpulse_data.py")
            (backup_restore_dir / "restore_earthpulse_data.py").chmod(0o755)

        # Write README_RESTORATION.md
        readme_path = backup_restore_dir / "README_RESTORATION.md"
        with open(readme_path, "w", encoding="utf-8") as rf:
            rf.write("""# EarthPulse-SAR — Scientific Data Restoration Instructions

NASA Space Apps Challenge 2026 — Dancing with the SARs

This directory contains automated utilities to restore the complete ~5.6 GB scientific dataset into the EarthPulse-SAR repository.

## Quickstart

From your local EarthPulse-SAR repository root:

```bash
# 1. Verify existing repository files against SHA-256 database
python3 tools/restore_earthpulse_data.py --verify-only

# 2. Dry run restore from downloaded Google Drive folder
python3 tools/restore_earthpulse_data.py --source-dir /path/to/EarthPulse-SAR-Scientific-Data --dry-run

# 3. Perform full restoration (copying files to original data paths)
python3 tools/restore_earthpulse_data.py --source-dir /path/to/EarthPulse-SAR-Scientific-Data --mode copy

# 4. Or use symlinks / hardlinks on Linux/macOS to save disk space
python3 tools/restore_earthpulse_data.py --source-dir /path/to/EarthPulse-SAR-Scientific-Data --mode hardlink
```

## Directory Structure
- `01_Sentinel1_Raw/` -> `data/raw/sentinel1/`
- `02_Sentinel2_Raw/` -> `data/reference/optical/sentinel2/`
- `03_Processed_GeoTIFF/` -> `data/intermediate/` and `data/processed/`
- `04_Reference_Data/` -> `data/reference/`
- `05_Model_Artifacts/` -> `models/phase7a/`
- `06_Large_Scientific_Outputs/` -> `data/outputs/`
- `07_Manifests_and_Checksums/` -> `data/`
- `08_Backup_and_Restore/` -> Restoration tools and verification hashes
""")

        # Generate sha256 checksums file for drive files
        hashes_file = backup_restore_dir / "verification_hashes.sha256"
        with open(hashes_file, "w", encoding="utf-8") as hf:
            with open(inventory_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    hf.write(f"{row['sha256_checksum']}  {row['relative_path']}\n")

    print("-" * 70)
    print("STAGING SUMMARY:")
    print(f"  Total Files Staged: {staged_count}")
    print(f"  Total Data Volume:  {total_bytes / 1024 / 1024 / 1024:.2f} GB ({total_bytes} bytes)")
    print(f"  Errors Encountered: {errors}")
    print("-" * 70)

    return 1 if errors > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage EarthPulse Scientific Data for Google Drive")
    parser.add_argument(
        "--staging-dir",
        "-d",
        type=Path,
        default=Path("/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR-Scientific-Data"),
        help="Destination directory for staging Google Drive files",
    )
    parser.add_argument(
        "--repo-root",
        "-r",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="EarthPulse-SAR repository root",
    )
    parser.add_argument(
        "--inventory",
        "-i",
        type=Path,
        help="Path to drive_upload_inventory.csv",
    )
    parser.add_argument(
        "--mode",
        choices=["hardlink", "symlink", "copy"],
        default="hardlink",
        help="Staging mode: hardlink (default, 0 extra disk), symlink, or copy",
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run simulation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    inventory_path = (
        args.inventory
        if args.inventory
        else repo_root / "data/outputs/phase8_3/drive_upload_inventory.csv"
    )

    return stage_drive_data(
        repo_root=repo_root,
        staging_dir=args.staging_dir.resolve(),
        inventory_path=inventory_path,
        mode=args.mode,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
