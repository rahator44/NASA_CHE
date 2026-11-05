#!/usr/bin/env python3
"""
Independent Scientific Verification Tool: Riverbank Migration & Geomorphology
NASA Space Apps Challenge 2026 — Dancing with the SARs

Verifies transect displacement audit classifications, empirical statistics,
and 95% spatial block bootstrap confidence intervals from Phase 6.1 and 6.2.
"""

import sys
import argparse
from pathlib import Path
import pandas as pd


def verify_riverbank_statistics(root_dir: Path) -> int:
    print("=" * 80)
    print("EARTH PULSE INDEPENDENT VERIFICATION: RIVERBANK MIGRATION & UNCERTAINTY")
    print("=" * 80)
    print(f"[*] Target Directory: {root_dir}")

    audit_csv = root_dir / "data/outputs/phase6_1/statistics/phase6_1_transect_displacement_audit.csv"
    ci_csv = root_dir / "data/outputs/phase6_2/statistics/phase6_2_spatial_bootstrap_intervals.csv"
    zones_csv = root_dir / "data/outputs/phase6_1/statistics/phase6_1_area_reconciliation.csv"

    failures = 0

    # 1. Audited Transects Count & Classification Breakdown
    print("\n--- 1. Verification of Transect Displacement Population Audit ---")
    if not audit_csv.exists():
        print(f"[MISSING] Audit CSV not found: {audit_csv}")
        return 1

    df_audit = pd.read_csv(audit_csv)
    total_eval = len(df_audit)
    expected_total = 154

    status_counts = df_audit["confidence_status"].value_counts().to_dict()
    valid_count = status_counts.get("VALID_LOCAL_MIGRATION", 0)
    edge_count = status_counts.get("AMBIGUOUS_EDGE_EFFECT", 0)
    anabranch_count = status_counts.get("ANABRANCH_ACTIVATION", 0)
    expansion_count = status_counts.get("MAJOR_CHANNEL_EXPANSION", 0)
    outside_valid = edge_count + anabranch_count + expansion_count

    expected_valid = 122
    expected_outside = 32

    pass_total = (total_eval == expected_total)
    pass_valid = (valid_count == expected_valid)
    pass_outside = (outside_valid == expected_outside)

    status_pop = "PASS" if (pass_total and pass_valid and pass_outside) else "FAIL"
    if status_pop != "PASS":
        failures += 1

    print(f"[{status_pop}] Total Audited Transects Evaluated: {total_eval} (Expected: {expected_total})")
    print(f"       * Valid Local Migration: {valid_count} (Expected: {expected_valid}, {valid_count/total_eval*100:.2f}%)")
    print(f"       * Outside Valid-Local: {outside_valid} (Expected: {expected_outside})")
    print(f"         - Ambiguous Edge Effects: {edge_count} (Expected: 23)")
    print(f"         - Anabranch Activations: {anabranch_count} (Expected: 5)")
    print(f"         - Major Channel Expansion: {expansion_count} (Expected: 4)")

    # 2. Empirical Displacement Statistics (Valid Local Transects)
    print("\n--- 2. Empirical Lateral Displacement Across 122 Valid Local Transects ---")
    df_valid = df_audit[df_audit["confidence_status"] == "VALID_LOCAL_MIGRATION"]
    west_mean = round(float(df_valid["right_bank_displacement_m"].mean()), 2)
    east_mean = round(float(df_valid["left_bank_displacement_m"].mean()), 2)
    width_mean = round(float(df_valid["channel_width_expansion_m"].mean()), 2)
    west_med = round(float(df_valid["right_bank_displacement_m"].median()), 2)
    east_med = round(float(df_valid["left_bank_displacement_m"].median()), 2)
    width_med = round(float(df_valid["channel_width_expansion_m"].median()), 2)

    # Authoritative empirical statistics from 122 valid rows
    exp_w_mean, exp_w_med = 130.00, 40.00
    exp_e_mean, exp_e_med = 160.66, 90.00
    exp_wd_mean, exp_wd_med = 290.66, 180.00

    match_stats = (
        abs(west_mean - exp_w_mean) < 0.05 and abs(west_med - exp_w_med) < 0.05 and
        abs(east_mean - exp_e_mean) < 0.05 and abs(east_med - exp_e_med) < 0.05 and
        abs(width_mean - exp_wd_mean) < 0.05 and abs(width_med - exp_wd_med) < 0.05
    )
    stat_emp = "PASS" if match_stats else "FAIL"
    if not match_stats:
        failures += 1

    print(f"[{stat_emp}] Observed Empirical Stats across {len(df_valid)} valid rows:")
    print(f"       * Right Bank (West / Mainland): mean = {west_mean:.2f} m, median = {west_med:.2f} m (Expected: {exp_w_mean:.2f} m, {exp_w_med:.2f} m)")
    print(f"       * Left Bank (East / Chars):     mean = {east_mean:.2f} m, median = {east_med:.2f} m (Expected: {exp_e_mean:.2f} m, {exp_e_med:.2f} m)")
    print(f"       * Channel Width Expansion:      mean = {width_mean:.2f} m, median = {width_med:.2f} m (Expected: {exp_wd_mean:.2f} m, {exp_wd_med:.2f} m)")

    # 3. 95% Spatial Block Bootstrap Confidence Intervals
    print("\n--- 3. Authoritative 95% Spatial Block Bootstrap Confidence Intervals ---")
    if not ci_csv.exists():
        print(f"[MISSING] Bootstrap CI CSV not found: {ci_csv}")
        failures += 1
    else:
        df_ci = pd.read_csv(ci_csv)
        print("  Spatial Block Bootstrap (Block Size: 5 transects / 1.0 km, Iterations: 2,000):")

        expected_cis = {
            ("Right Bank (West / Mainland)", "Median Displacement"): (20.0, 80.0),
            ("Left Bank (East / Chars)", "Median Displacement"): (20.0, 150.0),
            ("Channel Width Expansion", "Median Displacement"): (120.0, 320.0),
        }

        for (feat, stat), (exp_l, exp_u) in expected_cis.items():
            row = df_ci[(df_ci["target_feature"] == feat) & (df_ci["statistic"] == stat)]
            if len(row) == 0:
                print(f"[FAIL] Missing CI row for {feat} - {stat}")
                failures += 1
                continue
            r = row.iloc[0]
            obs_l = float(r["ci_95_lower_m"])
            obs_u = float(r["ci_95_upper_m"])
            match = (obs_l == exp_l) and (obs_u == exp_u)
            stat_ci = "PASS" if match else "FAIL"
            if not match:
                failures += 1
            print(f"  [{stat_ci}] {feat:<28} {stat:<22}: 95% CI = [{obs_l:>6.2f}, {obs_u:>6.2f}] m (Expected: [{exp_l}, {exp_u}] m)")

    # 4. Phase 6.1 General Fluvial Change Zones
    print("\n--- 4. Fluvial Change Zones & Area Reconciliation ---")
    if not zones_csv.exists():
        print(f"[MISSING] Area reconciliation CSV not found: {zones_csv}")
        failures += 1
    else:
        df_zones = pd.read_csv(zones_csv)
        expected_zones = {
            2: ("External Bank Expansion / Erosion Candidate", 21.9400, 2194.00, 54850),
            3: ("Internal Char Submergence Candidate", 23.2100, 2321.00, 58025),
            4: ("Apparent Channel Contraction / Accretion Candidate", 0.4148, 41.48, 1037),
            6: ("Disconnected Floodplain Inundation", 13.6468, 1364.68, 34117),
        }

        for code, (name, exp_km2, exp_ha, exp_px) in expected_zones.items():
            row = df_zones[df_zones["zone_code"] == code]
            if len(row) == 0:
                print(f"[FAIL] Missing zone code {code}")
                failures += 1
                continue
            r = row.iloc[0]
            obs_km2 = float(r["area_km2"])
            obs_ha = float(r["area_ha"])
            obs_px = int(r["pixel_count"])

            match = (obs_km2 == exp_km2) and (obs_ha == exp_ha) and (obs_px == exp_px)
            stat_z = "PASS" if match else "FAIL"
            if not match:
                failures += 1
            print(f"  [{stat_z}] Zone {code}: {name:<45} | {obs_px:>6,} px ({obs_ha:>7.2f} ha, {obs_km2:>7.4f} km²)")

    print("\n" + "=" * 80)
    if failures == 0:
        print("[SUCCESS] All riverbank geomorphic classifications and bootstrap intervals independently verified.")
        return 0
    else:
        print(f"[FAILED] Found {failures} riverbank verification discrepancies.")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify EarthPulse riverbank migration transects and uncertainty statistics.")
    parser.add_argument("--root", type=str, default=".", help="Root directory of extracted EarthPulse verification package.")
    args = parser.parse_args()
    sys.exit(verify_riverbank_statistics(Path(args.root).resolve()))

