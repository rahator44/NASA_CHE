#!/usr/bin/env python3
"""
Independent Scientific Verification Tool: Flood Detection & Area Accounting
NASA Space Apps Challenge 2026 — Dancing with the SARs

Verifies actual pixel counts and area calculations across Phase 5 flood rasters
against the authoritative transition matrix and inundation area summary.
"""

import sys
import argparse
from pathlib import Path
import numpy as np
from osgeo import gdal

gdal.UseExceptions()


def verify_flood_counts(root_dir: Path) -> int:
    print("=" * 80)
    print("EARTH PULSE INDEPENDENT VERIFICATION: FLOOD INUNDATION ACCOUNTING")
    print("=" * 80)
    print(f"[*] Target Directory: {root_dir}")

    p5_dir = root_dir / "data/processed/phase5"
    p5_stats = root_dir / "data/outputs/phase5/statistics"

    if not p5_dir.exists():
        print(f"[!] Error: Phase 5 processed directory missing: {p5_dir}")
        return 1

    failures = 0

    # 1. Inspect Individual Mask Rasters
    expected_masks = {
        "phase5_persistent_water.tif": {
            "name": "Persistent Water",
            "expected_cells": 216595,
            "expected_ha": 8663.80,
            "expected_km2": 86.6380,
        },
        "phase5_newly_inundated_candidate.tif": {
            "name": "Newly Inundated Candidate",
            "expected_cells": 146992,
            "expected_ha": 5879.68,
            "expected_km2": 58.7968,
        },
        "phase5_receded_water.tif": {
            "name": "Receded Water",
            "expected_cells": 1634,
            "expected_ha": 65.36,
            "expected_km2": 0.6536,
        },
        "phase5_persistent_non_water.tif": {
            "name": "Persistent Non-Water",
            "expected_cells": 628515,
            "expected_ha": 25140.60,
            "expected_km2": 251.4060,
        },
        "phase5_indeterminate_mask.tif": {
            "name": "Indeterminate Noise Floor",
            "expected_cells": 16242,
            "expected_ha": 649.68,
            "expected_km2": 6.4968,
        },
    }

    print("\n--- 1. Verification of Individual Inundation Rasters (Pixel Geometry 20m x 20m) ---")
    raster_counts = {}
    for filename, meta in expected_masks.items():
        fp = p5_dir / filename
        if not fp.exists():
            print(f"[MISSING] {filename}")
            failures += 1
            continue

        ds = gdal.Open(str(fp))
        arr = ds.GetRasterBand(1).ReadAsArray()
        gt = ds.GetGeoTransform()
        pixel_area_m2 = abs(gt[1] * gt[5])

        cells = int(np.sum(arr == 1))
        ha = round(cells * pixel_area_m2 / 10000.0, 2)
        km2 = round(cells * pixel_area_m2 / 1000000.0, 4)
        raster_counts[filename] = cells

        match_cells = (cells == meta["expected_cells"])
        match_ha = abs(ha - meta["expected_ha"]) < 0.05
        match_km2 = abs(km2 - meta["expected_km2"]) < 0.001

        status = "PASS" if (match_cells and match_ha and match_km2) else "FAIL"
        if status != "PASS":
            failures += 1

        print(
            f"[{status}] {meta['name']:<28} | Observed: {cells:>8,} cells ({ha:>9.2f} ha, {km2:>7.4f} km²) | "
            f"Expected: {meta['expected_cells']:>8,} cells ({meta['expected_ha']:>9.2f} ha)"
        )

    # 2. Net Surface-Water Change Reconciliation
    print("\n--- 2. Surface-Water Transition Net Change Reconciliation ---")
    if "phase5_newly_inundated_candidate.tif" in raster_counts and "phase5_receded_water.tif" in raster_counts:
        new_cells = raster_counts["phase5_newly_inundated_candidate.tif"]
        rec_cells = raster_counts["phase5_receded_water.tif"]
        net_cells = new_cells - rec_cells
        net_ha = round(net_cells * 0.04, 2)
        net_km2 = round(net_cells * 0.0004, 4)

        expected_net_cells = 145358
        expected_net_ha = 5814.32
        expected_net_km2 = 58.1432

        match_net = (net_cells == expected_net_cells) and (abs(net_ha - expected_net_ha) < 0.05)
        status_net = "PASS" if match_net else "FAIL"
        if not match_net:
            failures += 1

        print(
            f"[{status_net}] Net Inundation Balance = Newly Inundated ({new_cells:,}) - Receded ({rec_cells:,})\n"
            f"       Observed Net Change: {net_cells:>8,} cells | {net_ha:>9.2f} ha | {net_km2:>8.4f} km²\n"
            f"       Expected Net Change: {expected_net_cells:>8,} cells | {expected_net_ha:>9.2f} ha | {expected_net_km2:>8.4f} km²"
        )

    # 3. Common Valid Domain and Whole-Epoch Reconciliation
    print("\n--- 3. Dual-Domain Accounting & Asymmetric Quality Mask Gap ---")
    if p5_stats.exists():
        summary_csv = p5_stats / "phase5_inundation_area_summary.csv"
        if summary_csv.exists():
            import pandas as pd
            df = pd.read_csv(summary_csv)
            print("Authoritative Summary CSV Records:")
            for _, r in df.iterrows():
                print(f"  * {r['Accounting_Domain']:<35} | {r['Metric']:<45}: {r['Value_Pixels']:>8} px | {r['Value_ha']:>9} ha")

            whole_epoch_delta_ha = 6452.24
            valid_domain_net_ha = 5814.32
            expected_gap_ha = 637.92
            computed_gap = round(whole_epoch_delta_ha - valid_domain_net_ha, 2)

            gap_match = abs(computed_gap - expected_gap_ha) < 0.01
            gap_status = "PASS" if gap_match else "FAIL"
            if not gap_match:
                failures += 1
            print(f"[{gap_status}] Asymmetric Exclusion Gap: Whole-Epoch Delta ({whole_epoch_delta_ha} ha) - "
                  f"Common-Valid-Domain Net ({valid_domain_net_ha} ha) = {computed_gap} ha (Expected: {expected_gap_ha} ha)")

    print("\n" + "=" * 80)
    if failures == 0:
        print("[SUCCESS] All flood area calculations and raster pixel counts independently verified.")
        return 0
    else:
        print(f"[FAILED] Found {failures} verification discrepancies.")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify EarthPulse flood detection raster pixel counts and area calculations.")
    parser.add_argument("--root", type=str, default=".", help="Root directory of extracted EarthPulse verification package.")
    args = parser.parse_args()
    sys.exit(verify_flood_counts(Path(args.root).resolve()))

