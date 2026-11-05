#!/usr/bin/env python3
"""
Earth Pulse Phase 7B: Explainable AI, SHAP Attribution & Model Interpretability Pipeline
NASA Space Apps Challenge 2026: Dancing with the SARs

Executes Tasks A through J:
1. Environment Audit & Missing-SHAP Dependency Logging.
2. Feature Correlation & Redundancy Analysis (vv_minus_vh_db vs cross_pol_ratio).
3. Global Feature Attribution & Grouped Polarization Decomposition.
4. Local Prediction Explanations for Representative Held-Out Cases.
5. In-depth False-Positive & False-Negative Disagreement Investigation.
6. Transparent Deterministic Baseline Explanation & Side-by-Side Comparison.
7. Probability Calibration Diagnostics & Uncertainty Interpretation.
8. Publication-Quality Figures (9 Maps and Diagnostic Charts).
9. Deliverable Export and Metadata Persistence.
"""

import os
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
import sys
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from osgeo import gdal

gdal.UseExceptions()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ml.random_forest import RandomForestClassifier
from src.ml.explainability import (
    audit_explainability_environment,
    TreePathExplainer,
    investigate_feature_redundancy,
    compute_grouped_attributions,
    evaluate_probability_calibration,
)
from src.ml.registry import ModelRegistry
from src.core.config_loader import load_region_config, load_model_config, load_feature_schema


def run_phase7b_pipeline():
    print("=" * 80)
    print("EARTH PULSE — PHASE 7B: EXPLAINABLE AI & SAR MODEL INTERPRETABILITY")
    print("NASA Space Apps Challenge 2026: Dancing with the SARs")
    print("=" * 80)

    # ---------------------------------------------------------
    # Task A: Environment Audit
    # ---------------------------------------------------------
    print("\n[Step 1/9] Auditing Explainability Environment (Task A)...")
    env_audit = audit_explainability_environment()
    print(f"  Python Version:     {env_audit['python_version']}")
    print(f"  SHAP Package:       {env_audit['packages']['shap']}")
    print(f"  SHAP Status:        {env_audit['shap_status']}")
    print(f"  Scikit-Learn:       {env_audit['packages']['sklearn']}")
    print(f"  NumPy Version:      {env_audit['packages']['numpy']['version']}")
    print(f"  Explainer Engine:   {env_audit['primary_explainer_engine']}")

    # ---------------------------------------------------------
    # Load Model, Datasets & Metadata
    # ---------------------------------------------------------
    print("\n[Step 2/9] Loading Registered Model & Feature Schema (Task B)...")
    registry = ModelRegistry()
    model_entry = registry.get_model("phase7a_rf_jamuna_v1")
    if not model_entry:
        raise RuntimeError("Model 'phase7a_rf_jamuna_v1' not found in model registry.")

    print(f"  Model ID:           {model_entry.model_id}")
    print(f"  Model Status:       {model_entry.status}")
    print(f"  Artifact Path:      {model_entry.model_artifact_path}")
    print(f"  Optimal Threshold:  {model_entry.hyperparameters.get('optimal_probability_threshold', 0.35)}")

    model_path = PROJECT_ROOT / model_entry.model_artifact_path
    rf_model = RandomForestClassifier.load(model_path)
    print(f"  Loaded Ensemble:    {len(rf_model.estimators_)} trees, max_depth={rf_model.max_depth}")

    feature_schema_cfg = load_feature_schema("sar_features")
    feature_names = [f["name"] for f in feature_schema_cfg["features"]]
    print(f"  Feature Schema:     {feature_names}")

    # Load dataset samples
    samples_path = PROJECT_ROOT / "data/outputs/phase7a/statistics/phase7a_training_samples.csv"
    df_all = pd.read_csv(samples_path)
    df_train = df_all[df_all["split"] == "train"].copy()
    df_test = df_all[df_all["split"] == "test"].copy()
    print(f"  Training Samples:   {len(df_train):,} rows")
    print(f"  Held-Out Test:      {len(df_test):,} rows")

    # ---------------------------------------------------------
    # Task B: Feature Correlation & Redundancy Audit
    # ---------------------------------------------------------
    print("\n[Step 3/9] Auditing Feature Redundancy & Polarization Relationships (Task B)...")
    redundancy_res = investigate_feature_redundancy(df_all, feature_names)
    p_corr = redundancy_res["vv_minus_vh_vs_cross_pol_ratio"]["pearson_r"]
    s_corr = redundancy_res["vv_minus_vh_vs_cross_pol_ratio"]["spearman_r"]
    print(f"  Pearson Correlation (vv_minus_vh_db vs cross_pol_ratio):  {p_corr:.4f}")
    print(f"  Spearman Correlation (vv_minus_vh_db vs cross_pol_ratio): {s_corr:.4f}")
    print(f"  Verdict: {redundancy_res['vv_minus_vh_vs_cross_pol_ratio']['verdict']}")

    # Save feature correlation table
    corr_df = redundancy_res["spearman_correlation_matrix"].round(4)
    corr_csv_path = PROJECT_ROOT / "data/outputs/phase7b/shap/phase7b_feature_correlation.csv"
    corr_df.to_csv(corr_csv_path)
    print(f"  Saved: {corr_csv_path.name}")

    # ---------------------------------------------------------
    # Task C: Global Explainability & Grouped Attribution
    # ---------------------------------------------------------
    print("\n[Step 4/9] Computing Global Tree-Path Attributions & Grouped Attributions (Task C)...")
    X_train = df_train[feature_names].values
    X_test = df_test[feature_names].values

    explainer = TreePathExplainer(rf_model, background_X=X_train, feature_names=feature_names)
    print(f"  Global Base Value (phi_0): {explainer.base_value:.4f}")

    # Explain held-out test observations
    test_explanations = explainer.explain_dataset(X_test)
    shap_matrix = test_explanations["shap_values"]
    df_importance = test_explanations["importance_ranking"]
    print("\n  Global Feature Importance Ranking (Mean |SHAP|):")
    for _, row in df_importance.iterrows():
        print(f"    Rank {int(row['rank'])}: {row['feature_name']:16s} Mean|SHAP|={row['mean_abs_shap']:.4f} Signed={row['mean_signed_shap']:+.4f}")

    importance_csv_path = PROJECT_ROOT / "data/outputs/phase7b/shap/phase7b_global_shap_importance.csv"
    df_importance.to_csv(importance_csv_path, index=False)
    print(f"  Saved: {importance_csv_path.name}")

    # Grouped attribution
    df_grouped = compute_grouped_attributions(shap_matrix, feature_names)
    print("\n  Grouped Feature Attributions:")
    for _, row in df_grouped.iterrows():
        print(f"    Rank {int(row['rank'])}: {row['feature_group']:28s} Mean|SHAP|={row['mean_abs_attribution']:.4f} ({row['attribution_fraction_pct']:.1f}%)")

    grouped_csv_path = PROJECT_ROOT / "data/outputs/phase7b/shap/phase7b_grouped_feature_attribution.csv"
    df_grouped.to_csv(grouped_csv_path, index=False)
    print(f"  Saved: {grouped_csv_path.name}")

    # ---------------------------------------------------------
    # Task D: Local Prediction Explanations
    # ---------------------------------------------------------
    print("\n[Step 5/9] Generating Local Explanations for Representative Held-Out Cases (Task D)...")
    threshold = 0.35
    df_test = df_test.reset_index(drop=True)
    df_test["rf_prob"] = test_explanations["prediction_probabilities"]
    df_test["rf_pred"] = (df_test["rf_prob"] >= threshold).astype(int)

    # Classify cases
    # TP: label=1, pred=1
    # TN: label=0, pred=0
    # FP: label=0, pred=1 (Optical Disagreement)
    # FN: label=1, pred=0 (Optical Disagreement)
    conditions = [
        (df_test["label"] == 1) & (df_test["rf_pred"] == 1),
        (df_test["label"] == 0) & (df_test["rf_pred"] == 0),
        (df_test["label"] == 0) & (df_test["rf_pred"] == 1),
        (df_test["label"] == 1) & (df_test["rf_pred"] == 0),
    ]
    categories = ["TRUE_POSITIVE", "TRUE_NEGATIVE", "OPTICAL_DISAGREEMENT_FP", "OPTICAL_DISAGREEMENT_FN"]
    df_test["category"] = np.select(conditions, categories, default="UNKNOWN")

    # Select representative examples deterministically
    representative_cases = []
    case_specs = [
        ("TRUE_POSITIVE", "June", "Deep River Channel (Pre-Monsoon Low Flow)", "High Confidence"),
        ("TRUE_POSITIVE", "July", "Inundated Floodplain / Anabranch (Monsoon Crest)", "High Confidence"),
        ("TRUE_NEGATIVE", "June", "Mainland Agricultural Field (Dry Bare Soil)", "High Confidence"),
        ("TRUE_NEGATIVE", "July", "High-Elevation Settlement Embankment", "High Confidence"),
        ("OPTICAL_DISAGREEMENT_FP", "June", "Moist Char Sandbar (Smooth Specular Surface)", "False Alarm"),
        ("OPTICAL_DISAGREEMENT_FP", "July", "Monsoon Waterlogged Agriculture (Low Backscatter)", "False Alarm"),
        ("OPTICAL_DISAGREEMENT_FN", "June", "Shallow Sandbar Channel (Rough / Mixed Pixel)", "Missed Water"),
        ("OPTICAL_DISAGREEMENT_FN", "July", "Turbid Flood Edge (Wind Roughened)", "Missed Water"),
    ]

    local_rows = []
    for cat, epoch, desc, conf_type in case_specs:
        subset = df_test[(df_test["category"] == cat) & (df_test["epoch"] == epoch)]
        if len(subset) == 0:
            subset = df_test[df_test["category"] == cat]
        
        # Pick median probability or extreme probability depending on spec
        if "High Confidence" in conf_type:
            idx = subset["rf_prob"].idxmax() if "POSITIVE" in cat or "FP" in cat else subset["rf_prob"].idxmin()
        else:
            # Pick representative median
            med_prob = subset["rf_prob"].median()
            idx = (subset["rf_prob"] - med_prob).abs().idxmin()

        sample = subset.loc[idx]
        sample_feat = sample[feature_names].values.astype(float)
        loc_res = explainer.explain_instance(sample_feat)

        row_dict = {
            "case_id": f"CASE_{len(local_rows)+1:02d}_{cat}",
            "epoch": sample["epoch"],
            "block_id": sample["block_id"],
            "pixel_row": int(sample["row"]),
            "pixel_col": int(sample["col"]),
            "utm_x": round(float(sample["utm_x"]), 2),
            "utm_y": round(float(sample["utm_y"]), 2),
            "optical_reference_label": int(sample["label"]),
            "rf_prediction": int(sample["rf_pred"]),
            "rf_probability": round(float(sample["rf_prob"]), 4),
            "base_value": round(float(loc_res["base_value"]), 4),
            "category": cat,
            "description": desc,
            "confidence_type": conf_type,
        }
        for fn in feature_names:
            row_dict[f"feat_{fn}"] = round(float(sample[fn]), 4)
            row_dict[f"shap_{fn}"] = round(float(loc_res["attributions"][fn]), 4)

        local_rows.append(row_dict)
        representative_cases.append((sample, loc_res, desc))

    df_local = pd.DataFrame(local_rows)
    local_csv_path = PROJECT_ROOT / "data/outputs/phase7b/local_explanations/phase7b_local_prediction_explanations.csv"
    df_local.to_csv(local_csv_path, index=False)
    print(f"  Extracted {len(local_rows)} representative local explanation cases.")
    print(f"  Saved: {local_csv_path.name}")

    # ---------------------------------------------------------
    # Task E: False-Positive & False-Negative Error Investigation
    # ---------------------------------------------------------
    print("\n[Step 6/9] Investigating False-Positive & False-Negative Disagreements (Task E)...")
    fp_subset = df_test[df_test["category"] == "OPTICAL_DISAGREEMENT_FP"]
    fn_subset = df_test[df_test["category"] == "OPTICAL_DISAGREEMENT_FN"]
    tp_subset = df_test[df_test["category"] == "TRUE_POSITIVE"]
    tn_subset = df_test[df_test["category"] == "TRUE_NEGATIVE"]

    def _get_feature_stats(subset: pd.DataFrame, name: str) -> Dict[str, Any]:
        stats = {"category": name, "count": len(subset)}
        for fn in feature_names:
            stats[f"{fn}_mean"] = round(float(subset[fn].mean()), 4)
            stats[f"{fn}_std"] = round(float(subset[fn].std()), 4)
            stats[f"{fn}_median"] = round(float(subset[fn].median()), 4)
            stats[f"{fn}_p10"] = round(float(subset[fn].quantile(0.10)), 4)
            stats[f"{fn}_p90"] = round(float(subset[fn].quantile(0.90)), 4)
        return stats

    fp_stats = pd.DataFrame([
        _get_feature_stats(fp_subset, "FP_All_Optical_Disagreements"),
        _get_feature_stats(fp_subset[fp_subset['epoch'] == 'June'], "FP_June_PreMonsoon"),
        _get_feature_stats(fp_subset[fp_subset['epoch'] == 'July'], "FP_July_MonsoonPeak"),
        _get_feature_stats(tp_subset, "TP_True_Water_Reference"),
        _get_feature_stats(tn_subset, "TN_True_NonWater_Reference"),
    ])
    fp_csv_path = PROJECT_ROOT / "data/outputs/phase7b/diagnostics/phase7b_false_positive_analysis.csv"
    fp_stats.to_csv(fp_csv_path, index=False)
    print(f"  FP Count: {len(fp_subset)} (June: {len(fp_subset[fp_subset['epoch']=='June'])}, July: {len(fp_subset[fp_subset['epoch']=='July'])})")
    print(f"  Saved: {fp_csv_path.name}")

    fn_stats = pd.DataFrame([
        _get_feature_stats(fn_subset, "FN_All_Missed_Water"),
        _get_feature_stats(fn_subset[fn_subset['epoch'] == 'June'], "FN_June_PreMonsoon"),
        _get_feature_stats(fn_subset[fn_subset['epoch'] == 'July'], "FN_July_MonsoonPeak"),
    ])
    fn_csv_path = PROJECT_ROOT / "data/outputs/phase7b/diagnostics/phase7b_false_negative_analysis.csv"
    fn_stats.to_csv(fn_csv_path, index=False)
    print(f"  FN Count: {len(fn_subset)} (June: {len(fn_subset[fn_subset['epoch']=='June'])}, July: {len(fn_subset[fn_subset['epoch']=='July'])})")
    print(f"  Saved: {fn_csv_path.name}")

    # ---------------------------------------------------------
    # Task F: Deterministic Baseline Explanation & Comparison
    # ---------------------------------------------------------
    print("\n[Step 7/9] Comparing Random Forest vs. Deterministic Otsu Baseline (Task F)...")
    # Apply Otsu rule on exact test samples
    # Rule: (vv_db < -16.0) AND (vh_db < -23.5)
    df_test["otsu_pred"] = ((df_test["vv_db"] < -16.0) & (df_test["vh_db"] < -23.5)).astype(int)

    rf_water_otsu_water = int(np.sum((df_test["rf_pred"] == 1) & (df_test["otsu_pred"] == 1)))
    rf_land_otsu_land = int(np.sum((df_test["rf_pred"] == 0) & (df_test["otsu_pred"] == 0)))
    rf_water_otsu_land = int(np.sum((df_test["rf_pred"] == 1) & (df_test["otsu_pred"] == 0)))
    rf_land_otsu_water = int(np.sum((df_test["rf_pred"] == 0) & (df_test["otsu_pred"] == 1)))

    total_test = len(df_test)
    agreement_pct = round(((rf_water_otsu_water + rf_land_otsu_land) / total_test) * 100.0, 2)
    disagreement_pct = round(100.0 - agreement_pct, 2)

    df_disagree = pd.DataFrame([
        {"comparison": "Total Evaluated Pixels", "count": total_test, "pct": 100.0},
        {"comparison": "Both Models Predict Water", "count": rf_water_otsu_water, "pct": round(rf_water_otsu_water/total_test*100, 2)},
        {"comparison": "Both Models Predict Non-Water", "count": rf_land_otsu_land, "pct": round(rf_land_otsu_land/total_test*100, 2)},
        {"comparison": "RF Predicts Water / Otsu Predicts Non-Water", "count": rf_water_otsu_land, "pct": round(rf_water_otsu_land/total_test*100, 2)},
        {"comparison": "RF Predicts Non-Water / Otsu Predicts Water", "count": rf_land_otsu_water, "pct": round(rf_land_otsu_water/total_test*100, 2)},
        {"comparison": "Overall Spatial Agreement", "count": rf_water_otsu_water + rf_land_otsu_land, "pct": agreement_pct},
        {"comparison": "Overall Spatial Disagreement", "count": rf_water_otsu_land + rf_land_otsu_water, "pct": disagreement_pct},
    ])
    disagree_csv_path = PROJECT_ROOT / "data/outputs/phase7b/diagnostics/phase7b_model_disagreement_summary.csv"
    df_disagree.to_csv(disagree_csv_path, index=False)
    print(f"  Model Spatial Agreement: {agreement_pct}% (Disagreement: {disagreement_pct}%)")
    print(f"  RF-Water / Otsu-Land Disagreement: {rf_water_otsu_land} pixels ({rf_water_otsu_land/total_test*100:.1f}%)")
    print(f"  Saved: {disagree_csv_path.name}")

    # ---------------------------------------------------------
    # Task G: Probability & Uncertainty Diagnostics
    # ---------------------------------------------------------
    print("\n[Step 8/9] Evaluating Probability Calibration Diagnostics (Task G)...")
    calib_res = evaluate_probability_calibration(df_test["rf_prob"].values, df_test["label"].values, n_bins=10)
    print(f"  Brier Score:                     {calib_res['brier_score']}")
    print(f"  Expected Calibration Error (ECE): {calib_res['expected_calibration_error']}")
    
    calib_csv_path = PROJECT_ROOT / "data/outputs/phase7b/diagnostics/phase7b_probability_diagnostics.csv"
    calib_res["calibration_bins_df"].to_csv(calib_csv_path, index=False)
    print(f"  Saved: {calib_csv_path.name}")

    # ---------------------------------------------------------
    # Task I: Publication Visualizations (9 Figures)
    # ---------------------------------------------------------
    print("\n[Step 9/9] Rendering 9 Publication-Quality Figures (Task I)...")
    maps_dir = PROJECT_ROOT / "data/outputs/phase7b/maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    # 1. Global SHAP Beeswarm / Feature Distribution Plot
    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
    y_pos = np.arange(len(feature_names))
    sorted_features = df_importance["feature_name"].tolist()[::-1]
    sorted_indices = [feature_names.index(fn) for fn in sorted_features]
    
    # Subsample 1,000 points for clear beeswarm display
    sample_sub_idx = np.random.RandomState(42).choice(len(df_test), size=min(1000, len(df_test)), replace=False)
    for i, f_idx in enumerate(sorted_indices):
        fn = feature_names[f_idx]
        shap_vals = shap_matrix[sample_sub_idx, f_idx]
        f_vals = X_test[sample_sub_idx, f_idx]
        # Normalize feature values to [0, 1] for colormap
        f_norm = (f_vals - np.percentile(f_vals, 5)) / (np.percentile(f_vals, 95) - np.percentile(f_vals, 5) + 1e-6)
        f_norm = np.clip(f_norm, 0, 1)
        jitter = np.random.normal(0, 0.08, size=len(shap_vals))
        sc = ax.scatter(shap_vals, i + jitter, c=f_norm, cmap="coolwarm", alpha=0.6, s=18, edgecolors="none")

    ax.set_yticks(range(len(sorted_features)))
    ax.set_yticklabels(sorted_features, fontsize=11, fontweight="bold")
    ax.axvline(0, color="black", linestyle="--", alpha=0.7, linewidth=1.2)
    ax.set_xlabel("SHAP Feature Attribution (Impact on Candidate Water Probability)", fontsize=11)
    ax.set_title("Global SHAP Feature Attribution Distribution (Held-Out Test Set, Jamuna Reach)", fontsize=12, fontweight="bold", pad=12)
    cbar = plt.colorbar(sc, ax=ax, orientation="vertical", pad=0.02)
    cbar.set_label("Relative Feature Value (Low = Blue, High = Red)", fontsize=10)
    plt.tight_layout()
    fig1_path = maps_dir / "phase7b_global_shap_beeswarm.png"
    fig.savefig(fig1_path)
    plt.close(fig)
    print(f"  [1/9] Generated: {fig1_path.name}")

    # 2. Global Feature Importance Ranking Bar Chart
    fig, ax = plt.subplots(figsize=(9, 5), dpi=300)
    bars = ax.barh(df_importance["feature_name"][::-1], df_importance["mean_abs_shap"][::-1], color="#1f77b4", edgecolor="black", alpha=0.85)
    ax.set_xlabel("Mean Absolute SHAP Value (Average Magnitude of Impact)", fontsize=11)
    ax.set_title("Global SAR Feature Importance Ranking (Tree-Path Attribution)", fontsize=12, fontweight="bold", pad=12)
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.002, bar.get_y() + bar.get_height()/2, f"{w:.4f}", va="center", ha="left", fontsize=9, fontweight="bold")
    ax.set_xlim(0, max(df_importance["mean_abs_shap"]) * 1.15)
    plt.tight_layout()
    fig2_path = maps_dir / "phase7b_global_feature_importance.png"
    fig.savefig(fig2_path)
    plt.close(fig)
    print(f"  [2/9] Generated: {fig2_path.name}")

    # 3. Polarization Feature Dependence (VV vs. VH vs. SHAP)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), dpi=300)
    # VV backscatter vs. VV SHAP
    sc1 = ax1.scatter(df_test["vv_db"].iloc[sample_sub_idx], shap_matrix[sample_sub_idx, 0], c=df_test["label"].iloc[sample_sub_idx], cmap="bwr", alpha=0.7, s=20)
    ax1.axhline(0, color="gray", linestyle="--")
    ax1.axvline(-16.0, color="red", linestyle=":", label="Otsu Threshold (-16.0 dB)")
    ax1.set_xlabel("VV Backscatter [dB]", fontsize=10)
    ax1.set_ylabel("SHAP Attribution for VV", fontsize=10)
    ax1.set_title("VV Feature Dependence (Blue=Non-Water, Red=Water)", fontsize=11, fontweight="bold")
    ax1.legend()

    # VH backscatter vs. VH SHAP
    sc2 = ax2.scatter(df_test["vh_db"].iloc[sample_sub_idx], shap_matrix[sample_sub_idx, 1], c=df_test["label"].iloc[sample_sub_idx], cmap="bwr", alpha=0.7, s=20)
    ax2.axhline(0, color="gray", linestyle="--")
    ax2.axvline(-23.5, color="red", linestyle=":", label="Otsu Threshold (-23.5 dB)")
    ax2.set_xlabel("VH Backscatter [dB]", fontsize=10)
    ax2.set_ylabel("SHAP Attribution for VH", fontsize=10)
    ax2.set_title("VH Feature Dependence (Blue=Non-Water, Red=Water)", fontsize=11, fontweight="bold")
    ax2.legend()
    plt.tight_layout()
    fig3_path = maps_dir / "phase7b_polarization_dependence.png"
    fig.savefig(fig3_path)
    plt.close(fig)
    print(f"  [3/9] Generated: {fig3_path.name}")

    # 4. Texture Feature Dependence
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), dpi=300)
    ax1.scatter(df_test["texture_vv"].iloc[sample_sub_idx], shap_matrix[sample_sub_idx, 4], c="#2ca02c", alpha=0.6, s=20)
    ax1.axhline(0, color="gray", linestyle="--")
    ax1.set_xlabel("Local Texture VV (Std Dev in 5x5) [dB]", fontsize=10)
    ax1.set_ylabel("SHAP Attribution for Texture VV", fontsize=10)
    ax1.set_title("Spatial Texture VV Dependence", fontsize=11, fontweight="bold")

    ax2.scatter(df_test["texture_vh"].iloc[sample_sub_idx], shap_matrix[sample_sub_idx, 5], c="#d62728", alpha=0.6, s=20)
    ax2.axhline(0, color="gray", linestyle="--")
    ax2.set_xlabel("Local Texture VH (Std Dev in 5x5) [dB]", fontsize=10)
    ax2.set_ylabel("SHAP Attribution for Texture VH", fontsize=10)
    ax2.set_title("Spatial Texture VH Dependence", fontsize=11, fontweight="bold")
    plt.tight_layout()
    fig4_path = maps_dir / "phase7b_texture_dependence.png"
    fig.savefig(fig4_path)
    plt.close(fig)
    print(f"  [4/9] Generated: {fig4_path.name}")

    # 5. Local Prediction Waterfall Examples (4 Panels: TP, TN, FP, FN)
    fig, axs = plt.subplots(2, 2, figsize=(14, 10), dpi=300)
    panels = [
        (axs[0, 0], local_rows[0], "Panel A: True Positive (Deep Channel)"),
        (axs[0, 1], local_rows[2], "Panel B: True Negative (Dry Mainland)"),
        (axs[1, 0], local_rows[4], "Panel C: Optical Disagreement FP (Moist Sandbar)"),
        (axs[1, 1], local_rows[6], "Panel D: Optical Disagreement FN (Shallow Channel)"),
    ]

    for ax, row, title in panels:
        feats_disp = feature_names[::-1]
        shap_vals_disp = [row[f"shap_{fn}"] for fn in feats_disp]
        colors = ["#d62728" if v >= 0 else "#1f77b4" for v in shap_vals_disp]
        bars = ax.barh(feats_disp, shap_vals_disp, color=colors, alpha=0.85, edgecolor="black")
        ax.axvline(0, color="black", linestyle="--", linewidth=1)
        ax.set_title(f"{title}\nP(Water)={row['rf_probability']:.3f} | Base={row['base_value']:.3f}", fontsize=10, fontweight="bold")
        ax.set_xlabel("Feature Contribution (SHAP value)", fontsize=9)
        for b in bars:
            w = b.get_width()
            offset = 0.005 if w >= 0 else -0.005
            ha = "left" if w >= 0 else "right"
            ax.text(w + offset, b.get_y() + b.get_height()/2, f"{w:+.3f}", va="center", ha=ha, fontsize=8)

    plt.suptitle("Local Prediction Feature Attributions for Representative Cases (Jamuna Reach)", fontsize=13, fontweight="bold", y=0.99)
    plt.tight_layout()
    fig5_path = maps_dir / "phase7b_local_waterfall_examples.png"
    fig.savefig(fig5_path)
    plt.close(fig)
    print(f"  [5/9] Generated: {fig5_path.name}")

    # 6. False-Positive Explanation Comparison
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), dpi=300)
    # Compare VV distribution of FP vs TP vs TN
    ax1.hist(tn_subset["vv_db"], bins=30, alpha=0.5, label=f"TN Non-Water (N={len(tn_subset)})", color="gray", density=True)
    ax1.hist(fp_subset["vv_db"], bins=30, alpha=0.6, label=f"FP Disagreement (N={len(fp_subset)})", color="orange", density=True)
    ax1.hist(tp_subset["vv_db"], bins=30, alpha=0.6, label=f"TP Water (N={len(tp_subset)})", color="blue", density=True)
    ax1.set_xlabel("VV Backscatter [dB]", fontsize=10)
    ax1.set_ylabel("Probability Density", fontsize=10)
    ax1.set_title("VV Backscatter Overlap: FP Overlaps True Water", fontsize=11, fontweight="bold")
    ax1.legend()

    # Compare VH distribution of FP vs TP vs TN
    ax2.hist(tn_subset["vh_db"], bins=30, alpha=0.5, label=f"TN Non-Water (N={len(tn_subset)})", color="gray", density=True)
    ax2.hist(fp_subset["vh_db"], bins=30, alpha=0.6, label=f"FP Disagreement (N={len(fp_subset)})", color="orange", density=True)
    ax2.hist(tp_subset["vh_db"], bins=30, alpha=0.6, label=f"TP Water (N={len(tp_subset)})", color="blue", density=True)
    ax2.set_xlabel("VH Backscatter [dB]", fontsize=10)
    ax2.set_ylabel("Probability Density", fontsize=10)
    ax2.set_title("VH Backscatter Overlap: FP Low Depolarization", fontsize=11, fontweight="bold")
    ax2.legend()
    plt.tight_layout()
    fig6_path = maps_dir / "phase7b_false_positive_comparison.png"
    fig.savefig(fig6_path)
    plt.close(fig)
    print(f"  [6/9] Generated: {fig6_path.name}")

    # 7. False-Negative Explanation Comparison (Missed Water)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), dpi=300)
    ax1.boxplot([tp_subset["vv_db"], fn_subset["vv_db"]], tick_labels=["True Positives (Water)", "False Negatives (Missed)"], patch_artist=True)
    ax1.set_ylabel("VV Backscatter [dB]", fontsize=10)
    ax1.set_title("VV Backscatter: Missed Water Exhibits Higher Returns", fontsize=11, fontweight="bold")

    ax2.boxplot([tp_subset["texture_vv"], fn_subset["texture_vv"]], tick_labels=["True Positives (Water)", "False Negatives (Missed)"], patch_artist=True)
    ax2.set_ylabel("Texture VV [dB]", fontsize=10)
    ax2.set_title("Spatial Texture: Missed Water Exhibits Elevated Roughness", fontsize=11, fontweight="bold")
    plt.tight_layout()
    fig7_path = maps_dir / "phase7b_false_negative_comparison.png"
    fig.savefig(fig7_path)
    plt.close(fig)
    print(f"  [7/9] Generated: {fig7_path.name}")

    # 8. Spatial Disagreement Map: RF vs. Deterministic Otsu (Using Spatial Coordinates)
    fig, ax = plt.subplots(figsize=(8, 10), dpi=300)
    # Scatter plot of test sample locations colored by agreement state
    agree_mask = (df_test["rf_pred"] == df_test["otsu_pred"])
    rf_only_water = (df_test["rf_pred"] == 1) & (df_test["otsu_pred"] == 0)
    otsu_only_water = (df_test["rf_pred"] == 0) & (df_test["otsu_pred"] == 1)

    ax.scatter(df_test["utm_x"][agree_mask], df_test["utm_y"][agree_mask], c="#bdbdbd", s=4, alpha=0.4, label=f"Both Agree ({agreement_pct}%)")
    ax.scatter(df_test["utm_x"][rf_only_water], df_test["utm_y"][rf_only_water], c="#ff7f0e", s=10, alpha=0.8, label=f"RF Water / Otsu Land ({rf_water_otsu_land} px)")
    ax.scatter(df_test["utm_x"][otsu_only_water], df_test["utm_y"][otsu_only_water], c="#1f77b4", s=14, alpha=0.9, marker="^", label=f"Otsu Water / RF Land ({rf_land_otsu_water} px)")

    ax.set_xlabel("UTM Easting (m, EPSG:32645)", fontsize=10)
    ax.set_ylabel("UTM Northing (m, EPSG:32645)", fontsize=10)
    ax.set_title("Model Spatial Agreement & Disagreement Map\nRandom Forest vs. Lee 5x5 Dual-AND Otsu Baseline (Jamuna Reach)", fontsize=11, fontweight="bold")
    ax.legend(loc="lower right", fontsize=9, framealpha=0.9)
    plt.tight_layout()
    fig8_path = maps_dir / "phase7b_rf_vs_otsu_disagreement_map.png"
    fig.savefig(fig8_path)
    plt.close(fig)
    print(f"  [8/9] Generated: {fig8_path.name}")

    # 9. Prediction Probability and Uncertainty Reliability Diagram
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), dpi=300)
    # Reliability curve
    bins_df = calib_res["calibration_bins_df"]
    ax1.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfect Calibration")
    ax1.plot(bins_df["mean_predicted_prob"], bins_df["empirical_water_fraction"], marker="o", color="#2ca02c", linewidth=2, label=f"Random Forest (ECE={calib_res['expected_calibration_error']})")
    ax1.axvline(0.35, color="red", linestyle=":", label="Decision Threshold (0.35)")
    ax1.set_xlabel("Mean Predicted Probability P(Water)", fontsize=10)
    ax1.set_ylabel("Empirical Optical Water Fraction", fontsize=10)
    ax1.set_title("Reliability Diagram (Probability vs. Optical Agreement)", fontsize=11, fontweight="bold")
    ax1.legend()

    # Uncertainty distribution: 1.0 - 2 * |P - 0.5|
    uncertainty_vals = 1.0 - 2.0 * np.abs(df_test["rf_prob"].values - 0.5)
    ax2.hist(uncertainty_vals[df_test["label"]==1], bins=25, alpha=0.6, color="blue", label="True Water Pixels", density=True)
    ax2.hist(uncertainty_vals[df_test["label"]==0], bins=25, alpha=0.6, color="orange", label="True Non-Water Pixels", density=True)
    ax2.set_xlabel("Classification Uncertainty: 1.0 - 2*|P - 0.5|", fontsize=10)
    ax2.set_ylabel("Probability Density", fontsize=10)
    ax2.set_title("Uncertainty Distribution by Reference Class", fontsize=11, fontweight="bold")
    ax2.legend()
    plt.tight_layout()
    fig9_path = maps_dir / "phase7b_probability_uncertainty_map.png"
    fig.savefig(fig9_path)
    plt.close(fig)
    print(f"  [9/9] Generated: {fig9_path.name}")

    # ---------------------------------------------------------
    # Master Metadata Report
    # ---------------------------------------------------------
    master_report = {
        "project": "NASA Space Apps Challenge 2026: Dancing with the SARs",
        "phase": "Phase 7B: Explainable AI, SHAP Attribution & SAR Model Interpretability",
        "model_identifier": model_entry.model_id,
        "model_registry_status": model_entry.status,
        "operational_baseline": "deterministic_lee_5x5_dual_and_otsu",
        "environment_audit": env_audit,
        "redundancy_analysis": {
            "pearson_r": p_corr,
            "spearman_r": s_corr,
            "verdict": redundancy_res["vv_minus_vh_vs_cross_pol_ratio"]["verdict"],
        },
        "global_importance_ranking": df_importance.to_dict(orient="records"),
        "grouped_attributions": df_grouped.to_dict(orient="records"),
        "local_explanations_count": len(local_rows),
        "false_positive_analysis": {
            "total_fp_test_count": len(fp_subset),
            "june_fp_count": int(np.sum(fp_subset["epoch"] == "June")),
            "july_fp_count": int(np.sum(fp_subset["epoch"] == "July")),
            "fp_vv_mean": float(fp_subset["vv_db"].mean()),
            "fp_vh_mean": float(fp_subset["vh_db"].mean()),
            "tp_vv_mean": float(tp_subset["vv_db"].mean()),
            "tn_vv_mean": float(tn_subset["vv_db"].mean()),
        },
        "model_comparison_with_otsu": {
            "total_test_pixels": total_test,
            "spatial_agreement_pct": agreement_pct,
            "both_water_count": rf_water_otsu_water,
            "both_nonwater_count": rf_land_otsu_land,
            "rf_only_water_count": rf_water_otsu_land,
            "otsu_only_water_count": rf_land_otsu_water,
        },
        "probability_calibration": {
            "brier_score": calib_res["brier_score"],
            "expected_calibration_error": calib_res["expected_calibration_error"],
        },
        "artifacts_generated": [
            str(corr_csv_path.relative_to(PROJECT_ROOT)),
            str(importance_csv_path.relative_to(PROJECT_ROOT)),
            str(grouped_csv_path.relative_to(PROJECT_ROOT)),
            str(local_csv_path.relative_to(PROJECT_ROOT)),
            str(fp_csv_path.relative_to(PROJECT_ROOT)),
            str(fn_csv_path.relative_to(PROJECT_ROOT)),
            str(disagree_csv_path.relative_to(PROJECT_ROOT)),
            str(calib_csv_path.relative_to(PROJECT_ROOT)),
            str(fig1_path.relative_to(PROJECT_ROOT)),
            str(fig2_path.relative_to(PROJECT_ROOT)),
            str(fig3_path.relative_to(PROJECT_ROOT)),
            str(fig4_path.relative_to(PROJECT_ROOT)),
            str(fig5_path.relative_to(PROJECT_ROOT)),
            str(fig6_path.relative_to(PROJECT_ROOT)),
            str(fig7_path.relative_to(PROJECT_ROOT)),
            str(fig8_path.relative_to(PROJECT_ROOT)),
            str(fig9_path.relative_to(PROJECT_ROOT)),
        ]
    }

    report_path = PROJECT_ROOT / "data/metadata/phase7b_explainability_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(master_report, f, indent=2)
    print(f"\nSaved Master Phase 7B Explainability Report to: {report_path}")
    print("=" * 80)
    print("PHASE 7B PIPELINE EXECUTION COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    run_phase7b_pipeline()
