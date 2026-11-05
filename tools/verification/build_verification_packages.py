#!/usr/bin/env python3
"""
EarthPulse-SAR Phase 8.5 Scientific Verification Package Builder
NASA Space Apps Challenge 2026 - Dancing with the SARs

This script packages the authoritative scientific data assets into smaller,
independently extractable ZIP files (target <= 75 MB each) for external
reproducibility and audit by ChatGPT.
"""

import os
import sys
import json
import csv
import hashlib
import zipfile
import shutil
from pathlib import Path

PROJECT_ROOT = Path("/home/orr/NewVolume1/Nasa-chlla/EarthPulse-SAR").resolve()
OUTPUT_DIR = Path("/home/orr/NewVolume1/EarthPulse-Scientific-Verification").resolve()
MAX_PACKAGE_SIZE_BYTES = 75 * 1024 * 1024  # 75 MB limit

# Package definitions (10 independently extractable packages, all <= 75 MB)
PACKAGE_SPECS = {
    "EarthPulse_01_Metadata_and_Provenance.zip": {
        "phase": "Phases 1-8.4 Metadata & Configs",
        "description": "Scientific metadata, quality reports, config files, sensor specs, raw archive inventories, and model registries",
        "paths": [
            "data/metadata",
            "configs",
            "models/model_registry.json",
            "data/intermediate/june10_sigma0_vv_vh_tc.data/vector_data/pins.csv",
            "data/intermediate/june10_sigma0_vv_vh_tc.data/vector_data/ground_control_points.csv",
            "data/intermediate/july16_sigma0_vv_vh_tc.data/vector_data/pins.csv",
            "data/intermediate/july16_sigma0_vv_vh_tc.data/vector_data/ground_control_points.csv",
        ],
        "essential": True,
        "category": "Metadata & Provenance"
    },
    "EarthPulse_02_Flood_Detection.zip": {
        "phase": "Phases 3A, 3B, 5",
        "description": "Full-AOI flood masks, candidate masks, flood transitions, persistent and receded water rasters, and area statistics",
        "paths": [
            "data/processed/phase3a_qc",
            "data/processed/phase3b_qc",
            "data/processed/phase5",
            "data/outputs/phase3a",
            "data/outputs/phase3b",
            "data/outputs/phase5",
        ],
        "essential": True,
        "category": "Flood Detection"
    },
    "EarthPulse_03_Riverbank_Analysis.zip": {
        "phase": "Phases 6, 6.1, 6.2",
        "description": "Channel change zones, transect displacement audits, spatial bootstrap intervals, uncertainty budgets, and centerline/transect GeoJSONs",
        "paths": [
            "data/processed/phase6",
            "data/processed/phase6_1",
            "data/outputs/phase6",
            "data/outputs/phase6_1",
            "data/outputs/phase6_2",
        ],
        "essential": True,
        "category": "Riverbank Analysis"
    },
    "EarthPulse_04_Random_Forest.zip": {
        "phase": "Phase 7A",
        "description": "Frozen Random Forest model artifact (.joblib), probability & uncertainty rasters, 31,522-sample training dataset, evaluation metrics, and feature importance",
        "paths": [
            "models/phase7a",
            "data/processed/phase7a",
            "data/outputs/phase7a",
        ],
        "essential": True,
        "category": "Random Forest ML"
    },
    "EarthPulse_05_Explainable_AI.zip": {
        "phase": "Phases 7B, 7B.1",
        "description": "Tree-path Saabas attribution summaries, full-precision local additivity audit, Shapley comparison fixtures, feature redundancy, and waterfall figures",
        "paths": [
            "data/outputs/phase7b",
            "data/outputs/phase7b1",
        ],
        "essential": True,
        "category": "Explainable AI"
    },
    "EarthPulse_06_SAR_Preprocessing_Part_A_June10.zip": {
        "phase": "Phases 1, 2A, 2B (June 10 Core)",
        "description": "June 10 preprocessed SAR data: aligned sigma0, calibrated dB rasters, Lee 5x5 speckle filtered rasters, quality mask, and histograms",
        "paths": [
            "data/processed/aligned/june10_aligned.tif",
            "data/processed/geotiff/june10_sigma0_vv_vh.tif",
            "data/processed/geotiff/june10_sigma0_vv_vh.tif.aux.xml",
            "data/processed/phase2a/june10_sigma0_vv_db.tif",
            "data/processed/phase2a/june10_sigma0_vh_db.tif",
            "data/processed/phase2b/lee_5x5/june10_lee_5x5.tif",
            "data/processed/phase2b/quality_mask/june10_quality_mask.tif",
            "data/outputs/phase2a/histogram_data/june10_vv_histogram.csv",
            "data/outputs/phase2a/histogram_data/june10_vh_histogram.csv",
            "data/outputs/phase2a/histograms/june10_vv_histogram.png",
            "data/outputs/phase2a/histograms/june10_vh_histogram.png",
        ],
        "essential": True,
        "category": "SAR Preprocessing"
    },
    "EarthPulse_06_SAR_Preprocessing_Part_B_July16.zip": {
        "phase": "Phases 1, 2A, 2B (July 16 Core)",
        "description": "July 16 preprocessed SAR data: aligned sigma0, calibrated dB rasters, Lee 5x5 speckle filtered rasters, quality mask, and histograms",
        "paths": [
            "data/processed/aligned/july16_aligned.tif",
            "data/processed/geotiff/july16_sigma0_vv_vh.tif",
            "data/processed/geotiff/july16_sigma0_vv_vh.tif.aux.xml",
            "data/processed/phase2a/july16_sigma0_vv_db.tif",
            "data/processed/phase2a/july16_sigma0_vh_db.tif",
            "data/processed/phase2b/lee_5x5/july16_lee_5x5.tif",
            "data/processed/phase2b/quality_mask/july16_quality_mask.tif",
            "data/outputs/phase2a/histogram_data/july16_vv_histogram.csv",
            "data/outputs/phase2a/histogram_data/july16_vh_histogram.csv",
            "data/outputs/phase2a/histograms/july16_vv_histogram.png",
            "data/outputs/phase2a/histograms/july16_vh_histogram.png",
        ],
        "essential": True,
        "category": "SAR Preprocessing"
    },
    "EarthPulse_06_SAR_Preprocessing_Part_C_Differences_and_QC.zip": {
        "phase": "Phases 2A, 2B (Differences & QC Diagnostics)",
        "description": "SAR backscatter difference rasters (delta VV/VH dB), Lee 3x3 filtered rasters (June 10 & July 16), difference maps, and full QC anomaly diagnostics",
        "paths": [
            "data/processed/phase2a/delta_vv_db.tif",
            "data/processed/phase2a/delta_vh_db.tif",
            "data/processed/phase2b/lee_3x3/june10_lee_3x3.tif",
            "data/processed/phase2b/lee_3x3/july16_lee_3x3.tif",
            "data/outputs/phase2a/difference_maps/delta_vv_map.png",
            "data/outputs/phase2a/difference_maps/delta_vh_map.png",
            "data/outputs/phase2a/histograms/comparative_vv_histogram.png",
            "data/outputs/phase2a/histograms/comparative_vh_histogram.png",
            "data/outputs/phase2a/qc/aoi_channel_statistics.csv",
            "data/outputs/phase2a/qc/extreme_difference_summary.csv",
            "data/outputs/phase2a/qc/low_backscatter_distribution.csv",
            "data/outputs/phase2a/qc/qc_delta_vv_anomaly_map.png",
            "data/outputs/phase2a/qc/qc_delta_vh_anomaly_map.png",
            "data/outputs/phase2a/qc/qc_vv_full_range_histogram.png",
            "data/outputs/phase2a/qc/qc_vv_robust_range_histogram.png",
            "data/outputs/phase2a/qc/qc_vh_full_range_histogram.png",
            "data/outputs/phase2a/qc/qc_vh_robust_range_histogram.png",
        ],
        "essential": True,
        "category": "SAR Preprocessing & QC"
    },
    "EarthPulse_07_Optical_Reference_and_Validation_Part_A.zip": {
        "phase": "Phases 4A, 4C.1 (June 7 Optical)",
        "description": "June 7 Sentinel-2 L2A optical reference rasters: aligned B03, B08, B11, B12, MNDWI, AWEI_nsh, SCL, valid mask, cloud masks, and water mask",
        "paths": [
            "data/processed/reference/optical/sentinel2/june_2024",
        ],
        "essential": True,
        "category": "Optical Reference"
    },
    "EarthPulse_07_Optical_Reference_and_Validation_Part_B.zip": {
        "phase": "Phases 4A, 4C.1, 4D, 4D.1 (July 17 Optical & Validation)",
        "description": "July 17 Sentinel-2 L2A optical reference rasters, plus independent optical-reference validation reports, crosstabulations, and confusion matrices",
        "paths": [
            "data/processed/reference/optical/sentinel2/july_2024",
            "data/outputs/phase4d",
            "data/outputs/phase4d1",
        ],
        "essential": True,
        "category": "Optical Reference & Validation"
    }
}


def compute_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_files_for_package(package_name: str, spec: dict):
    file_list = []
    for item in spec["paths"]:
        full_path = PROJECT_ROOT / item
        if not full_path.exists():
            print(f"  [WARN] Path does not exist: {item}")
            continue
        if full_path.is_file():
            rel = full_path.relative_to(PROJECT_ROOT).as_posix()
            file_list.append((rel, full_path))
        elif full_path.is_dir():
            for root, _, files in os.walk(full_path):
                for f in sorted(files):
                    fp = Path(root) / f
                    rel = fp.relative_to(PROJECT_ROOT).as_posix()
                    file_list.append((rel, fp))
    # Remove duplicates while preserving order
    seen = set()
    unique_list = []
    for rel, fp in file_list:
        if rel not in seen:
            seen.add(rel)
            unique_list.append((rel, fp))
    return unique_list


def main():
    print("=" * 80)
    print("EarthPulse-SAR Phase 8.5 Verification Package Builder")
    print(f"Source Root: {PROJECT_ROOT}")
    print(f"Destination: {OUTPUT_DIR}")
    print("=" * 80)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tools_dest = OUTPUT_DIR / "tools"
    tools_dest.mkdir(parents=True, exist_ok=True)

    # Copy verification tools to destination tools directory
    verification_tools = [
        "verify_flood_counts.py",
        "verify_riverbank_statistics.py",
        "verify_model_metrics.py",
        "verify_explanation_additivity.py",
        "verify_raster_metadata.py"
    ]
    tools_src = PROJECT_ROOT / "tools" / "verification"
    for tool in verification_tools:
        src = tools_src / tool
        if src.exists():
            shutil.copy2(src, tools_dest / tool)
            print(f"Copied verification tool: {tool} -> {tools_dest / tool}")

    # Build packages
    manifest_records = []
    scientific_file_index = []
    checksum_lines = []
    global_seen_files = {}

    for pkg_name, spec in PACKAGE_SPECS.items():
        print(f"\nProcessing package: {pkg_name} ({spec['phase']})...")
        pkg_files = collect_files_for_package(pkg_name, spec)
        print(f"  Files collected: {len(pkg_files)}")

        zip_dest = OUTPUT_DIR / pkg_name
        total_uncompressed = 0

        with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, fp in pkg_files:
                zf.write(fp, rel)
                sz = fp.stat().st_size
                total_uncompressed += sz

                # Compute checksum if not already computed
                if rel not in global_seen_files:
                    file_hash = compute_sha256(fp)
                    global_seen_files[rel] = (file_hash, sz)
                    checksum_lines.append(f"{file_hash}  {rel}\n")
                else:
                    file_hash, _ = global_seen_files[rel]

                scientific_file_index.append({
                    "relative_path": rel,
                    "package_name": pkg_name,
                    "category": spec["category"],
                    "file_size_bytes": sz,
                    "sha256": file_hash,
                    "scientific_phase": spec["phase"],
                    "essential_for_review": "YES" if spec["essential"] else "NO"
                })

        # Verify ZIP integrity
        with zipfile.ZipFile(zip_dest, "r") as zf:
            bad_file = zf.testzip()
            if bad_file:
                print(f"  [ERROR] Corrupted file in {pkg_name}: {bad_file}")
                sys.exit(1)
            infolist = zf.infolist()
            archive_file_count = len(infolist)

        pkg_size = zip_dest.stat().st_size
        pkg_hash = compute_sha256(zip_dest)

        print(f"  ZIP created: {pkg_size / 1024 / 1024:.2f} MB | {archive_file_count} files | Hash: {pkg_hash[:16]}...")
        if pkg_size > MAX_PACKAGE_SIZE_BYTES:
            print(f"  [CRITICAL ERROR] Package {pkg_name} exceeds 75 MB limit ({pkg_size} bytes)")
            sys.exit(1)
        else:
            print(f"  [OK] Package size <= 75 MB limit.")

        manifest_records.append({
            "package_name": pkg_name,
            "scientific_phase": spec["phase"],
            "category": spec["category"],
            "description": spec["description"],
            "archive_size_bytes": pkg_size,
            "archive_size_mb": round(pkg_size / 1024 / 1024, 2),
            "uncompressed_size_bytes": total_uncompressed,
            "uncompressed_size_mb": round(total_uncompressed / 1024 / 1024, 2),
            "file_count": archive_file_count,
            "sha256": pkg_hash,
            "compression_ratio": round(total_uncompressed / pkg_size, 2) if pkg_size > 0 else 1.0,
            "status": "PASS_75MB_LIMIT"
        })

    # Write PACKAGE_MANIFEST.json
    manifest_path = OUTPUT_DIR / "PACKAGE_MANIFEST.json"
    manifest_data = {
        "project": "EarthPulse-SAR",
        "nasa_space_apps_challenge": "2026 - Dancing with the SARs",
        "phase": "Phase 8.5 Scientific Verification Package",
        "study_area": "Jamuna River, Kazipur / Sirajganj, Bangladesh",
        "authoritative_model_id": "phase7a_rf_jamuna_v1",
        "authoritative_model_status": "RETAINED_AS_PROBABILITY_LAYER",
        "authoritative_model_sha256": "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad",
        "total_packages": len(manifest_records),
        "total_compressed_size_bytes": sum(m["archive_size_bytes"] for m in manifest_records),
        "total_compressed_size_mb": round(sum(m["archive_size_bytes"] for m in manifest_records) / 1024 / 1024, 2),
        "total_uncompressed_size_bytes": sum(m["uncompressed_size_bytes"] for m in manifest_records),
        "total_uncompressed_size_mb": round(sum(m["uncompressed_size_bytes"] for m in manifest_records) / 1024 / 1024, 2),
        "total_unique_source_files": len(global_seen_files),
        "packages": manifest_records
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)
    print(f"\nWrote package manifest: {manifest_path}")

    # Write SCIENTIFIC_FILE_INDEX.csv
    csv_path = OUTPUT_DIR / "SCIENTIFIC_FILE_INDEX.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "relative_path", "package_name", "category", "file_size_bytes",
            "sha256", "scientific_phase", "essential_for_review"
        ])
        writer.writeheader()
        writer.writerows(scientific_file_index)
    print(f"Wrote file index: {csv_path} ({len(scientific_file_index)} records)")

    # Write ORIGINAL_SOURCE_CHECKSUMS.sha256
    checksums_path = OUTPUT_DIR / "ORIGINAL_SOURCE_CHECKSUMS.sha256"
    checksum_lines.sort(key=lambda x: x.split("  ")[1])
    with open(checksums_path, "w") as f:
        f.writelines(checksum_lines)
    print(f"Wrote source checksums: {checksums_path} ({len(checksum_lines)} unique source files)")

    print("\nAll packages built and verified successfully!")


if __name__ == "__main__":
    main()
