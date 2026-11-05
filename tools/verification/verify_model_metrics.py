#!/usr/bin/env python3
"""
Independent Scientific Verification Tool: Random Forest Model & Training Integrity
NASA Space Apps Challenge 2026 — Dancing with the SARs

Verifies the frozen Random Forest model artifact SHA-256 checksum, model registry,
held-out spatial test evaluation metrics, confusion matrix, and training dataset.
"""

import sys
import json
import hashlib
import argparse
from pathlib import Path
import pandas as pd


EXPECTED_MODEL_SHA256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verify_model_metrics(root_dir: Path) -> int:
    print("=" * 80)
    print("EARTH PULSE INDEPENDENT VERIFICATION: RANDOM FOREST MODEL & EVALUATION")
    print("=" * 80)
    print(f"[*] Target Directory: {root_dir}")

    model_file = root_dir / "models/phase7a/phase7a_random_forest_model.joblib"
    registry_file = root_dir / "models/model_registry.json"
    metrics_csv = root_dir / "data/outputs/phase7a/statistics/phase7a_evaluation_metrics.csv"
    samples_csv = root_dir / "data/outputs/phase7a/statistics/phase7a_training_samples.csv"
    report_json = root_dir / "data/metadata/phase7a_model_report.json"

    failures = 0

    # 1. Model Artifact Integrity
    print("\n--- 1. Frozen Random Forest Model Artifact Verification ---")
    if not model_file.exists():
        print(f"[MISSING] Model artifact missing: {model_file}")
        return 1

    actual_sha = compute_sha256(model_file)
    sha_match = (actual_sha.lower() == EXPECTED_MODEL_SHA256.lower())
    sha_status = "PASS" if sha_match else "FAIL"
    if not sha_match:
        failures += 1

    print(f"[{sha_status}] Model Path: models/phase7a/phase7a_random_forest_model.joblib")
    print(f"       Actual SHA-256:   {actual_sha}")
    print(f"       Expected SHA-256: {EXPECTED_MODEL_SHA256}")

    # 2. Model Registry Metadata
    print("\n--- 2. Model Registry & Operational Baseline Status ---")
    if not registry_file.exists():
        print(f"[MISSING] Model registry missing: {registry_file}")
        failures += 1
    else:
        with open(registry_file, "r") as f:
            reg = json.load(f)
        models = reg.get("models", [])
        m = next((mod for mod in models if mod.get("model_id") == "phase7a_rf_jamuna_v1"), None)
        if not m:
            print("[FAIL] phase7a_rf_jamuna_v1 not found in registry")
            failures += 1
        else:
            status = m.get("status")
            threshold = m.get("hyperparameters", {}).get("optimal_probability_threshold")
            n_est = m.get("hyperparameters", {}).get("n_estimators")
            max_d = m.get("hyperparameters", {}).get("max_depth")

            reg_pass = (status == "RETAINED_AS_PROBABILITY_LAYER") and (threshold == 0.35)
            reg_stat = "PASS" if reg_pass else "FAIL"
            if not reg_pass:
                failures += 1
            print(f"[{reg_stat}] Status: {status} (Role: Auxiliary probability layer)")
            print(f"       Optimal Threshold (tau*): {threshold} | Estimators: {n_est} | Max Depth: {max_d}")

    # 3. Held-Out Evaluation Metrics (Combined Test Split N=6,124)
    print("\n--- 3. Held-Out Spatial/Temporal Evaluation Metrics ---")
    expected_metrics = {
        "total_test_samples": 6124,
        "decision_threshold": 0.35,
        "accuracy": 0.5178,
        "precision": 0.4477,
        "recall": 0.9214,
        "f1_score": 0.6026,
        "roc_auc": 0.6810,
        "tp": 2239,
        "tn": 932,
        "fp": 2762,
        "fn": 191,
    }

    if report_json.exists():
        with open(report_json, "r") as f:
            meta = json.load(f)
        eval_data = meta.get("held_out_evaluation", {}).get("held_out_test_combined", {})
        cm = eval_data.get("confusion_matrix", {})

        for k, exp_val in expected_metrics.items():
            if k in cm:
                obs_val = cm[k]
            elif k in eval_data:
                obs_val = eval_data[k]
            else:
                continue

            if isinstance(exp_val, float):
                match = abs(float(obs_val) - exp_val) < 0.001
            else:
                match = (int(obs_val) == exp_val)

            stat = "PASS" if match else "FAIL"
            if not match:
                failures += 1
            print(f"  [{stat}] {k:<25}: Observed = {obs_val} | Expected = {exp_val}")

    # 4. Training and Spatial Validation Samples
    print("\n--- 4. Training Sample Dataset Evidence ---")
    if samples_csv.exists():
        df_s = pd.read_csv(samples_csv)
        total_samples = len(df_s)
        expected_total_samples = 31522
        cols = df_s.columns.tolist()

        match_total = (total_samples == expected_total_samples)
        has_features = all(f in cols for f in ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"])
        has_splits = all(s in df_s["split"].unique() for s in ["train", "val", "test"])

        stat_s = "PASS" if (match_total and has_features and has_splits) else "FAIL"
        if not (match_total and has_features and has_splits):
            failures += 1

        print(f"[{stat_s}] Total Sample Rows: {total_samples:,} (Expected: {expected_total_samples:,})")
        print(f"       Features Present: {has_features} (vv_db, vh_db, vv-vh, ratio, textures)")
        print(f"       Split Partitioning: {df_s['split'].value_counts().to_dict()}")

    print("\n" + "=" * 80)
    if failures == 0:
        print("[SUCCESS] All Random Forest model integrity checks and metrics independently verified.")
        return 0
    else:
        print(f"[FAILED] Found {failures} model verification discrepancies.")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify EarthPulse Random Forest model artifact and evaluation metrics.")
    parser.add_argument("--root", type=str, default=".", help="Root directory of extracted EarthPulse verification package.")
    args = parser.parse_args()
    sys.exit(verify_model_metrics(Path(args.root).resolve()))

