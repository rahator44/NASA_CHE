#!/usr/bin/env python3
"""EarthPulse-SAR — Scientific Data Restoration & Verification Tool.

Phase 8.3: Automated GitHub & Google Drive Project Handoff
NASA Space Apps Challenge 2026 — Dancing with the SARs

This utility verifies and restores the large scientific datasets (Sentinel-1 raw,
Sentinel-2 optical, processed GeoTIFFs, model artifacts, and manifests) downloaded
from Google Drive into the EarthPulse-SAR repository structure.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-256 hash of a file efficiently."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


# Mapping from Google Drive staging subfolders to repository destination relative paths
DRIVE_SUBFOLDER_MAP = {
    "01_Sentinel1_Raw": "data/raw/sentinel1",
    "02_Sentinel2_Raw": "data/reference/optical/sentinel2",
    "03_Processed_GeoTIFF": "data",
    "04_Reference_Data": "data/reference",
    "05_Model_Artifacts": "models/phase7a",
    "06_Large_Scientific_Outputs": "data/outputs",
    "07_Manifests_and_Checksums": "data",
}


def load_checksum_database(checksum_path: Path) -> Dict[str, str]:
    """Load reference SHA-256 hashes from checksum CSV."""
    db = {}
    if not checksum_path.exists():
        return db
    with open(checksum_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rel = row.get("relative_path", "").strip()
            sha = row.get("sha256_checksum", "").strip()
            if rel and sha:
                db[rel] = sha
    return db


def load_manifest(manifest_path: Path) -> List[Dict[str, str]]:
    """Load items from file transfer manifest or drive inventory CSV."""
    items = []
    if not manifest_path.exists():
        return items
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append(row)
    return items


def verify_existing_files(
    repo_root: Path, checksum_db: Dict[str, str], verbose: bool = False
) -> Tuple[int, int, int]:
    """Verify hashes of all files present in the repository against the checksum database."""
    verified_count = 0
    mismatch_count = 0
    missing_count = 0

    print(f"[*] Verifying existing repository files against {len(checksum_db)} recorded checksums...")

    for rel_path, expected_sha in checksum_db.items():
        target_file = repo_root / rel_path
        if not target_file.exists():
            missing_count += 1
            if verbose:
                print(f"  [MISSING] {rel_path}")
            continue

        actual_sha = compute_sha256(target_file)
        if actual_sha.lower() == expected_sha.lower():
            verified_count += 1
            if verbose:
                print(f"  [PASS] {rel_path}")
        else:
            mismatch_count += 1
            print(f"  [MISMATCH] {rel_path} (Expected: {expected_sha[:10]}... Got: {actual_sha[:10]}...)")

    return verified_count, mismatch_count, missing_count


def restore_data(
    source_dir: Path,
    repo_root: Path,
    checksum_db: Dict[str, str],
    mode: str = "copy",
    dry_run: bool = False,
    verbose: bool = False,
) -> Tuple[int, int, int]:
    """Restore scientific files from staged Google Drive folder into the repository."""
    restored_count = 0
    error_count = 0
    skipped_count = 0

    print(f"[*] Scanning source drive staging directory: {source_dir}")

    # Walk source directory
    for root, _, files in os.walk(source_dir):
        for fname in files:
            source_file = Path(root) / fname
            rel_to_source = source_file.relative_to(source_dir)
            rel_parts = rel_to_source.parts

            # Check if source_dir is organized with subfolders (01_..., 02_..., etc.)
            subfolder = rel_parts[0] if len(rel_parts) > 1 else ""

            # Determine destination relative path
            dest_rel_path: Optional[Path] = None

            # First, check if rel_to_source directly matches an expected checksum relative path
            as_posix = rel_to_source.as_posix()
            if as_posix in checksum_db:
                dest_rel_path = Path(as_posix)
            elif subfolder.startswith("0") and len(rel_parts) > 1:
                # Stripped path inside subfolder
                inner_path = Path(*rel_parts[1:])
                # Check known mappings
                inner_posix = inner_path.as_posix()
                if inner_posix in checksum_db:
                    dest_rel_path = Path(inner_posix)
                else:
                    # Try reconstructing from DRIVE_SUBFOLDER_MAP
                    base_target = DRIVE_SUBFOLDER_MAP.get(subfolder)
                    if base_target:
                        candidate = Path(base_target) / inner_path
                        if candidate.as_posix() in checksum_db:
                            dest_rel_path = candidate
                        else:
                            # Try matching by filename in checksum_db
                            for db_path in checksum_db:
                                if Path(db_path).name == fname and (subfolder in db_path or inner_posix in db_path):
                                    dest_rel_path = Path(db_path)
                                    break

            if dest_rel_path is None:
                # Match by filename if unambiguous
                matches = [p for p in checksum_db if Path(p).name == fname]
                if len(matches) == 1:
                    dest_rel_path = Path(matches[0])
                else:
                    # Keep path as is relative to source
                    dest_rel_path = rel_to_source

            dest_file = repo_root / dest_rel_path

            # Check expected hash
            expected_sha = checksum_db.get(dest_rel_path.as_posix())
            source_sha = compute_sha256(source_file)

            if expected_sha and source_sha.lower() != expected_sha.lower():
                print(f"  [ERROR] Checksum mismatch in source: {source_file} (Expected {expected_sha[:10]}..., got {source_sha[:10]}...)")
                error_count += 1
                continue

            if dest_file.exists():
                existing_sha = compute_sha256(dest_file)
                if existing_sha.lower() == source_sha.lower():
                    if verbose:
                        print(f"  [IDENTICAL] {dest_rel_path} already intact. Skipping.")
                    skipped_count += 1
                    continue

            if dry_run:
                print(f"  [DRY-RUN] Would restore: {source_file} -> {dest_file} ({mode})")
                restored_count += 1
                continue

            # Ensure parent directory exists
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                if mode == "symlink":
                    if dest_file.exists():
                        dest_file.unlink()
                    dest_file.symlink_to(source_file.resolve())
                elif mode == "hardlink":
                    if dest_file.exists():
                        dest_file.unlink()
                    os.link(source_file, dest_file)
                else:  # copy
                    shutil.copy2(source_file, dest_file)

                # Verify after copy/link
                post_sha = compute_sha256(dest_file)
                if expected_sha and post_sha.lower() != expected_sha.lower():
                    print(f"  [ERROR] Post-copy verification failed for {dest_file}")
                    error_count += 1
                else:
                    if verbose:
                        print(f"  [RESTORED] {dest_rel_path} ({post_sha[:10]}...)")
                    restored_count += 1
            except Exception as e:
                print(f"  [FAIL] Failed to restore {dest_file}: {e}")
                error_count += 1

    return restored_count, error_count, skipped_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EarthPulse-SAR Data Restoration & Verification Tool"
    )
    parser.add_argument(
        "--source-dir",
        "-s",
        type=Path,
        help="Path to downloaded/staged Google Drive folder (EarthPulse-SAR-Scientific-Data)",
    )
    parser.add_argument(
        "--repo-root",
        "-r",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root directory (defaults to parent of tools/)",
    )
    parser.add_argument(
        "--checksums",
        "-c",
        type=Path,
        help="Path to checksum_verification.csv (defaults to data/outputs/phase8_3/checksum_verification.csv)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify repository files against checksums without restoring",
    )
    parser.add_argument(
        "--mode",
        choices=["copy", "symlink", "hardlink"],
        default="copy",
        help="Restoration mode: copy (default), symlink, or hardlink",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate restore actions without modifying files",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed logging per file",
    )

    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    checksum_path = (
        args.checksums
        if args.checksums
        else repo_root / "data/outputs/phase8_3/checksum_verification.csv"
    )

    print("=" * 70)
    print("EARTH PULSE — SCIENTIFIC DATA RESTORATION & VERIFICATION")
    print(f"Repository Root: {repo_root}")
    print(f"Checksum File:   {checksum_path}")
    print("=" * 70)

    if not checksum_path.exists():
        print(f"[ERROR] Checksum file not found at: {checksum_path}")
        return 1

    checksum_db = load_checksum_database(checksum_path)
    print(f"[+] Loaded {len(checksum_db)} entries from checksum database.")

    if args.verify_only:
        verified, mismatch, missing = verify_existing_files(
            repo_root, checksum_db, verbose=args.verbose
        )
        print("-" * 70)
        print("VERIFICATION SUMMARY:")
        print(f"  Intact & Verified: {verified}")
        print(f"  Mismatched:        {mismatch}")
        print(f"  Missing:           {missing}")
        print(f"  Total Checked:     {len(checksum_db)}")
        print("-" * 70)
        return 1 if mismatch > 0 else 0

    if not args.source_dir:
        print("[ERROR] Please provide --source-dir pointing to downloaded Google Drive files, or use --verify-only.")
        return 1

    source_dir = args.source_dir.resolve()
    if not source_dir.exists():
        print(f"[ERROR] Source directory does not exist: {source_dir}")
        return 1

    restored, errors, skipped = restore_data(
        source_dir=source_dir,
        repo_root=repo_root,
        checksum_db=checksum_db,
        mode=args.mode,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    print("-" * 70)
    print("RESTORATION SUMMARY:")
    print(f"  Restored: {restored}")
    print(f"  Skipped (Already Intact): {skipped}")
    print(f"  Errors:   {errors}")
    print("-" * 70)

    if errors > 0:
        print("[FAILED] One or more errors occurred during restoration.")
        return 1

    print("[SUCCESS] Scientific data restoration completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
