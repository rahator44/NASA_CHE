#!/usr/bin/env python3
"""
Independent Scientific Verification Tool: Explainable AI & Tree Attribution Additivity
NASA Space Apps Challenge 2026 — Dancing with the SARs

Verifies the mathematical local additivity of Saabas-style tree-path feature attribution
(base_value + sum(attributions) == rf_probability) and global feature importance.
"""

import sys
import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def verify_explanation_additivity(root_dir: Path) -> int:
    print("=" * 80)
    print("EARTH PULSE INDEPENDENT VERIFICATION: EXPLAINABLE AI & ATTRIBUTION ADDITIVITY")
    print("=" * 80)
    print(f"[*] Target Directory: {root_dir}")

    local_csv = root_dir / "data/outputs/phase7b/local_explanations/phase7b_local_prediction_explanations.csv"
    additivity_csv = root_dir / "data/outputs/phase7b1/phase7b1_local_additivity_audit.csv"
    global_csv = root_dir / "data/outputs/phase7b/shap/phase7b_global_shap_importance.csv"
    grouped_csv = root_dir / "data/outputs/phase7b/shap/phase7b_grouped_feature_attribution.csv"

    failures = 0

    # 1. Local Prediction Attribution Additivity
    print("\n--- 1. Verification of Saabas Tree-Path Local Additivity Property ---")
    print("    Mathematical Identity: Base_Value + sum(phi_i) == P(water)")

    # A. Full Precision Mathematical Verification Audit
    if additivity_csv.exists():
        df_audit = pd.read_csv(additivity_csv)
        max_audit_err = float(df_audit["additivity_error"].max())
        mean_audit_err = float(df_audit["additivity_error"].mean())
        pass_audit = (max_audit_err < 1e-6)
        stat_audit = "PASS" if pass_audit else "FAIL"
        if not pass_audit:
            failures += 1
        print(f"  [{stat_audit}] Full-Precision Float64 Additivity Audit (phase7b1_local_additivity_audit.csv):")
        print(f"         Max Residual Error = {max_audit_err:.2e} | Mean Residual Error = {mean_audit_err:.2e} (Threshold: < 1.00e-06)")

    # B. Representative Display Cases
    if not local_csv.exists():
        print(f"[MISSING] Local explanations CSV not found: {local_csv}")
        return 1

    df_local = pd.read_csv(local_csv)
    shap_cols = [c for c in df_local.columns if c.startswith("shap_")]

    print("\n  Representative Local Prediction Explanation Cases (Display CSV, 4-decimal precision):")
    max_err = 0.0
    for idx, row in df_local.iterrows():
        case_id = row.get("case_id", f"case_{idx}")
        p_rf = float(row.get("rf_probability", 0.0))
        base_val = float(row.get("base_value", 0.4995))
        sum_phi = sum(float(row[c]) for c in shap_cols)
        reconstructed = base_val + sum_phi
        err = abs(reconstructed - p_rf)
        max_err = max(max_err, err)

        # Allow 4-decimal display rounding accumulation (+/- 0.0002)
        is_additive = (err < 2e-4)
        stat = "PASS" if is_additive else "FAIL"
        if not is_additive:
            failures += 1

        print(f"  [{stat}] {case_id:<28} | P(rf)={p_rf:.4f} | Base={base_val:.4f} + Sum(phi)={sum_phi:+.4f} = {reconstructed:.4f} (Err: {err:.2e})")

    print(f"\n  Observed Display Case Residual: {max_err:.2e} (Display rounding tolerance: < 2.00e-04)")

    # 2. Global Feature Importance Ranking
    print("\n--- 2. Global Feature Attribution Ranking & Physical Interpretability ---")
    if not global_csv.exists():
        print(f"[MISSING] Global SHAP CSV missing: {global_csv}")
        failures += 1
    else:
        df_glob = pd.read_csv(global_csv)
        print("  Global Mean Absolute Attribution Ranking:")
        for _, r in df_glob.iterrows():
            print(f"    Rank {int(r['rank'])}: {r['feature_name']:<18} | Mean |Attribution| = {float(r['mean_abs_shap']):.4f} | Mean Signed = {float(r['mean_signed_shap']):+.4f}")

        top_feature = df_glob.iloc[0]["feature_name"]
        match_top = (top_feature == "vv_db")
        stat_top = "PASS" if match_top else "FAIL"
        if not match_top:
            failures += 1
        print(f"  [{stat_top}] Dominant Feature: {top_feature} (Expected: vv_db - specular surface scattering dominance)")

    # 3. Grouped Polarization Attribution
    print("\n--- 3. Grouped Polarization Attribution (Collinearity Mitigation) ---")
    if not grouped_csv.exists():
        print(f"[MISSING] Grouped attribution CSV missing: {grouped_csv}")
        failures += 1
    else:
        df_grp = pd.read_csv(grouped_csv)
        for _, r in df_grp.iterrows():
            print(f"    Group {int(r['rank'])}: {r['feature_group']:<30} | {float(r['attribution_fraction_pct']):>6.2f}% of total attribution | {r['constituent_features']}")

    print("\n" + "=" * 80)
    if failures == 0:
        print("[SUCCESS] All explainability local additivity and feature ranking checks independently verified.")
        return 0
    else:
        print(f"[FAILED] Found {failures} explainability verification discrepancies.")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify EarthPulse explainability tree-path attribution local additivity.")
    parser.add_argument("--root", type=str, default=".", help="Root directory of extracted EarthPulse verification package.")
    args = parser.parse_args()
    sys.exit(verify_explanation_additivity(Path(args.root).resolve()))
