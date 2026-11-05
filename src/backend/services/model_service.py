"""
Model & Explainability Service
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
from src.backend.config import settings
from src.backend import contracts


class ModelService:
    @staticmethod
    def _load_registry() -> Dict[str, Any]:
        registry_path = settings.MODELS_DIR / "model_registry.json"
        with open(registry_path, "r") as f:
            return json.load(f)

    @classmethod
    def list_models(cls) -> List[Dict[str, Any]]:
        reg = cls._load_registry()
        models = []
        for m in reg.get("models", []):
            models.append({
                "model_id": m["model_id"],
                "architecture": "Pure-NumPy Fast Vectorized Random Forest Classifier",
                "n_estimators": m["hyperparameters"]["n_estimators"],
                "max_depth": m["hyperparameters"]["max_depth"],
                "min_samples_leaf": m["hyperparameters"]["min_samples_leaf"],
                "max_features": m["hyperparameters"]["max_features"],
                "optimal_probability_threshold": m["hyperparameters"]["optimal_probability_threshold"],
                "status": m["status"],
                "primary_baseline_reference": "Adaptive Lee 5x5 Dual-AND Otsu (VV & VH)",
                "sha256": m["model_artifact_sha256"],
                "artifact_path": m["model_artifact_path"],
                "created_at": m["creation_date"],
                "purpose": "Continuous candidate water probability layer and explainability diagnostics",
            })
        return models

    @classmethod
    def validate_model_path(cls, path: Path) -> Path:
        """Ensures a model path resolves strictly within the trusted models/phase7a directory."""
        trusted_dir = (settings.PROJECT_ROOT_DIR / "models/phase7a").resolve()
        resolved = Path(path).resolve()
        if not str(resolved).startswith(str(trusted_dir)):
            raise ValueError(
                f"Security violation: path {resolved} is outside trusted directory {trusted_dir}."
            )
        return resolved

    @classmethod
    def load_model(cls, model_id: str):
        """Loads a registered model artifact with strict path traversal prevention."""
        from src.ml.random_forest import RandomForestClassifier
        model_info = cls.get_model(model_id)
        if not model_info:
            raise ValueError(f"Model '{model_id}' is not registered in model catalog.")

        rel_path = model_info["artifact_path"]
        artifact_path = cls.validate_model_path(settings.PROJECT_ROOT_DIR / rel_path)

        if not artifact_path.exists():
            raise FileNotFoundError(f"Model artifact file missing at {artifact_path}.")

        return RandomForestClassifier.load(str(artifact_path))

    @classmethod
    def get_model(cls, model_id: str) -> Optional[Dict[str, Any]]:
        models = cls.list_models()
        for m in models:
            if m["model_id"] == model_id:
                return m
        return None

    @classmethod
    def get_metrics(cls, model_id: str) -> Optional[Dict[str, Any]]:
        if not cls.get_model(model_id):
            return None

        report_path = settings.METADATA_DIR / "phase7a_model_report.json"
        if not report_path.exists():
            return None
        with open(report_path, "r") as f:
            meta = json.load(f)

        eval_data = meta.get("held_out_evaluation", {})
        test_m = eval_data.get("held_out_test_combined", {})
        cm = test_m.get("confusion_matrix", {"tp": 2239, "tn": 932, "fp": 2762, "fn": 191})

        return {
            "model_id": model_id,
            "evaluation_dataset": "Spatial-block held-out evaluation across June and July 2024 observations (N=6,124)",
            "temporal_generalization_status": (
                "UNVERIFIED (Evaluation partitioned spatially across June 10 and July 16, 2024; "
                "temporal generalization to unseen acquisition dates remains unverified)."
            ),
            "operational_status_note": (
                "Model is retained strictly as an auxiliary candidate water probability layer. "
                "Due to low held-out test precision (0.4477) on saturated alluvial sediments, "
                "the deterministic Adaptive Lee 5x5 Dual-AND Otsu engine remains the authoritative primary baseline."
            ),
            "total_test_samples": 6124,
            "decision_threshold": contracts.MODEL_DECISION_THRESHOLD,
            "accuracy": test_m.get("accuracy", 0.5178),
            "precision": test_m.get("precision", 0.4477),
            "recall": test_m.get("recall", 0.9214),
            "f1_score": test_m.get("f1_score", 0.6026),
            "roc_auc": contracts.MODEL_TEST_ROC_AUC,
            "confusion_matrix": {
                "tp": cm.get("tp", 2239),
                "tn": cm.get("tn", 932),
                "fp": cm.get("fp", 2762),
                "fn": cm.get("fn", 191),
            },
            "epoch_breakdown": {
                "June": {"total": 4522, "tp": 1573, "tn": 849, "fp": 1918, "fn": 182},
                "July": {"total": 1602, "tp": 666, "tn": 83, "fp": 844, "fn": 9},
            },
        }

    @classmethod
    def get_features(cls, model_id: str) -> Optional[Dict[str, Any]]:
        if not cls.get_model(model_id):
            return None

        report_path = settings.METADATA_DIR / "phase7a_model_report.json"
        if not report_path.exists():
            return None
        with open(report_path, "r") as f:
            meta = json.load(f)

        gini_dict = {}
        perm_dict = {}
        for item in meta.get("feature_importance_ranking", []):
            fn = item.get("feature_name")
            if fn:
                gini_dict[fn] = float(item.get("gini_importance", 0.0))
                perm_dict[fn] = float(item.get("permutation_importance_mean", 0.0))

        return {
            "model_id": model_id,
            "feature_names": ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"],
            "feature_schema_version": "1.0.0",
            "gini_importance": gini_dict,
            "permutation_importance": perm_dict,
            "feature_redundancy_summary": {
                "collinear_pair": "vv_minus_vh_db vs cross_pol_ratio",
                "exact_formula": "cross_pol_ratio = min(10 ** (vv_minus_vh_db / 10), 100.0)",
                "invertibility_domain": "vv_minus_vh_db < 20.0 dB",
                "spearman_rank_correlation": 1.0,
                "tree_split_impact": "Identical sample ordering causes credit-splitting between logarithmic difference and linear ratio.",
                "mitigation": "Grouped Polarization Attribution (10.67% total attribution).",
            },
        }

    @classmethod
    def get_explanations(cls, model_id: str) -> Optional[Dict[str, Any]]:
        if not cls.get_model(model_id):
            return None

        global_csv = settings.OUTPUTS_DIR / "phase7b/shap/phase7b_global_shap_importance.csv"
        grouped_csv = settings.OUTPUTS_DIR / "phase7b/shap/phase7b_grouped_feature_attribution.csv"
        local_csv = settings.OUTPUTS_DIR / "phase7b/local_explanations/phase7b_local_prediction_explanations.csv"

        df_global = pd.read_csv(global_csv)
        df_grouped = pd.read_csv(grouped_csv)
        df_local = pd.read_csv(local_csv)

        feature_descriptions = {
            "vv_db": "Co-polarized backscatter (surface scattering dominant)",
            "vh_db": "Cross-polarized backscatter (volume/depolarizing scattering)",
            "texture_vh": "Cross-polarization local spatial variance (vegetation/structure)",
            "texture_vv": "Co-polarization local spatial variance (surface roughness)",
            "vv_minus_vh_db": "Polarization difference in decibels",
            "cross_pol_ratio": "Linear polarization ratio (clipped at 100.0)",
        }

        global_ranking = []
        for _, r in df_global.iterrows():
            fn = r["feature_name"]
            global_ranking.append({
                "feature_name": fn,
                "rank": int(r["rank"]),
                "mean_abs_shap": float(r["mean_abs_shap"]),
                "mean_signed_shap": float(r["mean_signed_shap"]),
                "description": feature_descriptions.get(fn, ""),
            })

        grouped_ranking = []
        for _, r in df_grouped.iterrows():
            grouped_ranking.append({
                "group_name": r["feature_group"],
                "rank": int(r["rank"]),
                "constituent_features": r["constituent_features"],
                "mean_abs_attribution": float(r["mean_abs_attribution"]),
                "attribution_percentage": float(r["attribution_fraction_pct"]),
                "mean_signed_attribution": float(r["mean_signed_attribution"]),
            })

        local_cases = []
        for _, r in df_local.iterrows():
            f_attrs = {}
            for col in r.index:
                if col.startswith("shap_"):
                    f_attrs[col.replace("shap_", "")] = float(r[col])

            local_cases.append({
                "case_id": r["case_id"],
                "category": r["category"],
                "epoch": r["epoch"],
                "utm_coordinates": [float(r["utm_x"]), float(r["utm_y"])],
                "optical_reference_label": int(r["optical_reference_label"]),
                "rf_prediction": int(r["rf_prediction"]),
                "rf_probability": float(r["rf_probability"]),
                "base_value": float(r["base_value"]),
                "sum_attributions": float(sum(f_attrs.values())),
                "additivity_error": float(abs((r["base_value"] + sum(f_attrs.values())) - r["rf_probability"])),
                "feature_attributions": f_attrs,
                "description": r["description"],
            })

        return {
            "model_id": model_id,
            "explainability_engine": "Native Pure-NumPy TreePathExplainer",
            "scientific_formulation": "TREE_PATH_ATTRIBUTION_SAABAS",
            "global_base_value_training_background": 0.4905,
            "ensemble_root_base_value": 0.4995,
            "global_importance_ranking": global_ranking,
            "grouped_attributions": grouped_ranking,
            "representative_local_cases": local_cases,
        }

    @classmethod
    def get_diagnostics(cls, model_id: str) -> Optional[Dict[str, Any]]:
        if not cls.get_model(model_id):
            return None

        calib_csv = settings.OUTPUTS_DIR / "phase7b/diagnostics/phase7b_probability_diagnostics.csv"
        df_cal = pd.read_csv(calib_csv)
        bins_data = df_cal.to_dict(orient="records")

        return {
            "model_id": model_id,
            "calibration_status": "UNCALIBRATED",
            "brier_score": 0.2270,
            "expected_calibration_error": 0.0959,
            "calibration_bins": bins_data,
            "decision_margin_interpretation": contracts.DECISION_MARGIN_INTERPRETATION,
            "false_positive_analysis": {
                "total_fp_test_samples": 2762,
                "june_fp_count": 1918,
                "july_fp_count": 844,
                "mean_vv_fp_db": -12.5702,
                "mean_vh_fp_db": -20.4126,
                "mean_vv_tp_db": -14.3511,
                "mean_vv_tn_db": -6.0464,
                "scattering_hypothesis": (
                    "Forward specular scattering on smooth wet sediments and saturated alluvial topsoil "
                    "produces low microwave return mimicking calm open water."
                ),
            },
            "epistemological_disclaimer": contracts.EPISTEMOLOGICAL_DISCLAIMER,
        }
