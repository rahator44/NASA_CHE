"""
Earth Pulse Explainable AI (XAI) & SAR Model Interpretability Engine
Provides tree-path feature attribution, Shapley value diagnostics, grouped polarization attribution,
false-positive error analysis, and rule-based deterministic baseline comparisons.
"""

from dataclasses import dataclass, asdict
import itertools
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

# Authoritative 6-feature SAR order defined in configs/features/sar_features.yaml
AUTHORITATIVE_FEATURE_ORDER: List[str] = [
    "vv_db",
    "vh_db",
    "vv_minus_vh_db",
    "cross_pol_ratio",
    "texture_vv",
    "texture_vh",
]


def validate_feature_schema(
    feature_names: List[str],
    expected_features: Optional[List[str]] = None,
) -> None:
    """
    Validates that input features match the authoritative SAR feature schema.
    Raises ValueError for missing, unexpected, or incorrectly ordered features.
    """
    expected = expected_features or AUTHORITATIVE_FEATURE_ORDER
    if len(feature_names) != len(expected):
        raise ValueError(
            f"Feature count mismatch: expected {len(expected)} features, got {len(feature_names)}. "
            f"Expected features: {expected}, got: {feature_names}"
        )
    missing = set(expected) - set(feature_names)
    unexpected = set(feature_names) - set(expected)
    if missing or unexpected:
        err_msgs = []
        if missing:
            err_msgs.append(f"Missing required features: {sorted(missing)}")
        if unexpected:
            err_msgs.append(f"Unexpected features found: {sorted(unexpected)}")
        raise ValueError(f"{'; '.join(err_msgs)}. Expected: {expected}")
    if feature_names != expected:
        raise ValueError(
            f"Incorrect feature ordering. Expected: {expected}, but received: {feature_names}"
        )


def audit_explainability_environment() -> Dict[str, Any]:
    """
    Audits the current Python environment for explainability libraries.
    Explicitly documents third-party SHAP library availability or blocked status.
    """
    env_info = {
        "python_version": None,
        "packages": {},
        "shap_available": False,
        "shap_status": "BLOCKED_DEPENDENCY_MISSING",
        "scikit_learn_available": False,
        "primary_explainer_engine": "Native Pure-NumPy TreePathExplainer (Exact Lundberg/Saabas Formulation)",
        "notes": (
            "Third-party 'shap' package is not installed. Per strict project governance, "
            "package installation is prohibited. Native pure-NumPy tree-path Shapley attributions "
            "and model-agnostic diagnostics are executed using verified dependencies (numpy, scipy, pandas, matplotlib)."
        )
    }

    import sys
    env_info["python_version"] = sys.version.split()[0]

    for pkg in ["shap", "sklearn", "numpy", "pandas", "matplotlib", "scipy", "joblib"]:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "available")
            env_info["packages"][pkg] = {"installed": True, "version": str(ver)}
            if pkg == "shap":
                env_info["shap_available"] = True
                env_info["shap_status"] = "AVAILABLE"
            elif pkg == "sklearn":
                env_info["scikit_learn_available"] = True
        except ImportError:
            env_info["packages"][pkg] = {"installed": False, "version": None}

    return env_info


class TreePathExplainer:
    """
    Computes exact, additive tree-path feature attributions for Pure-NumPy Random Forest models.
    Implements path-dependent feature conditioning (Saabas, 2014; Lundberg et al., 2020 tree-path formulation).
    Satisfies exact efficiency/additivity along the observed decision path:
        phi_0 + sum_{j=1}^D phi_j(x) = f(x) = P(Class=1 | x)

    Scientific Distinction (Phase 7B.1 Audit & Phase 8.7 Formulation):
        Tree-path attribution computes the telescoping sum of marginal probability shifts along
        the single branch traversed by sample x. While strictly additive, it differs from exact
        coalition-averaged Shapley values (which average over all 2^D feature subsets and permutations)
        because node testing order induces path dependency.
        
        Background-baseline mode centers Saabas tree-path contributions against the verified background
        mean attribution vector:
            Base_bg = E_bg[P(x)]
            phi_j^bg(x) = phi_j^root(x) - E_bg[phi_j^root]
        guaranteeing exact additivity: Base_bg + sum(phi_j^bg(x)) = P(x).
    """

    def __init__(
        self,
        model: Any,
        background_X: Optional[np.ndarray] = None,
        feature_names: Optional[List[str]] = None,
        validate_features: bool = True,
        allow_custom_schema: bool = False,
    ):
        self.model = model
        if feature_names is None:
            self.feature_names = list(AUTHORITATIVE_FEATURE_ORDER)
        else:
            if allow_custom_schema:
                # Explicit separated custom-schema mode for small-tree scientific test fixtures
                self.feature_names = list(feature_names)
            else:
                # Enforce authoritative 6-feature SAR schema
                validate_feature_schema(feature_names)
                self.feature_names = list(feature_names)

        self.n_features = len(self.feature_names)

        # Baseline 1: Ensemble root probability baseline (exact telescoping property)
        root_probs = [float(t.root.prob) for t in self.model.estimators_]
        self.root_base_value = float(np.mean(root_probs))
        self.base_value = self.root_base_value

        # Baseline 2: Background dataset empirical baseline (background-centered formulation)
        self.background_base_value: Optional[float] = None
        self.background_mean_attributions: Optional[np.ndarray] = None
        if background_X is not None and len(background_X) > 0:
            self.set_background(background_X)

    def set_background(self, background_X: np.ndarray) -> None:
        """
        Sets the verified background dataset and precomputes mean tree-path feature attributions
        and empirical background mean prediction probability for background-centered explanations.
        """
        bg_f32 = np.asarray(background_X, dtype=np.float32)
        if bg_f32.ndim != 2 or bg_f32.shape[1] != self.n_features:
            raise ValueError(f"Background dataset must have shape (N, {self.n_features}), got {bg_f32.shape}")

        n_bg = len(bg_f32)
        accum_attrs = np.zeros(self.n_features, dtype=np.float64)
        for x in bg_f32:
            _, attr = self._explain_instance_raw(x)
            accum_attrs += attr

        self.background_mean_attributions = accum_attrs / n_bg
        self.background_base_value = self.root_base_value + float(np.sum(self.background_mean_attributions))
        self.base_value = self.background_base_value

    def _explain_tree(self, tree: Any, x: np.ndarray) -> Tuple[float, np.ndarray]:
        """
        Traverses a single decision tree, accumulating incremental probability changes per feature.
        Uses float32 inference representation for feature values to ensure exact branch agreement with
        RandomForestClassifier.predict_proba.
        """
        x_infer = np.asarray(x, dtype=np.float32).ravel()
        attr = np.zeros(self.n_features, dtype=np.float64)
        node = tree.root
        base_val = float(node.prob)

        while not node.is_leaf:
            f_idx = node.feature
            thresh = node.threshold
            prev_prob = float(node.prob)

            if x_infer[f_idx] <= thresh:
                node = node.left
            else:
                node = node.right

            attr[f_idx] += (float(node.prob) - prev_prob)

        return base_val, attr

    def _explain_instance_raw(self, x_infer: np.ndarray) -> Tuple[float, np.ndarray]:
        """Traverses all ensemble trees for instance x_infer, returning mean root base and mean attributions."""
        n_trees = len(self.model.estimators_)
        accum_attr = np.zeros(self.n_features, dtype=np.float64)
        accum_base = 0.0

        for tree in self.model.estimators_:
            b, a = self._explain_tree(tree, x_infer)
            accum_base += b
            accum_attr += a

        return accum_base / n_trees, accum_attr / n_trees

    def explain_instance(self, x: np.ndarray, baseline_mode: str = "ensemble_root") -> Dict[str, Any]:
        """
        Computes additive feature attributions for a single instance x.
        Ensures x is cast to np.float32 matching model inference representation.
        Supports both baseline definitions:
          - 'ensemble_root': Mean root probability across ensemble trees (exact telescoping property)
          - 'background': Background-centered tree-path contributions using verified background dataset
        """
        x_infer = np.asarray(x, dtype=np.float32).ravel()
        if len(x_infer) != self.n_features:
            raise ValueError(f"Expected {self.n_features} features, got {len(x_infer)}")

        mean_base_root, mean_attr_root = self._explain_instance_raw(x_infer)
        pred_prob = float(self.model.predict_proba(x_infer.reshape(1, -1))[0, 1])

        if baseline_mode == "background":
            if self.background_base_value is None or self.background_mean_attributions is None:
                raise ValueError(
                    "Baseline mode 'background' requested, but no background dataset was provided. "
                    "Initialize TreePathExplainer with background_X or call set_background(X)."
                )
            base_val = self.background_base_value
            attr_arr = mean_attr_root - self.background_mean_attributions
        elif baseline_mode == "ensemble_root":
            base_val = mean_base_root
            attr_arr = mean_attr_root
        else:
            raise ValueError(f"Unsupported baseline_mode '{baseline_mode}'. Must be 'ensemble_root' or 'background'.")

        # Exact additivity check
        sum_attr = float(np.sum(attr_arr))
        additivity_diff = abs((base_val + sum_attr) - pred_prob)

        return {
            "base_value": float(base_val),
            "prediction_probability": pred_prob,
            "attributions": {name: float(attr_arr[i]) for i, name in enumerate(self.feature_names)},
            "attributions_array": attr_arr,
            "sum_attributions": sum_attr,
            "additivity_error": additivity_diff,
            "is_additive": bool(additivity_diff < 1e-5),
            "baseline_mode": baseline_mode,
        }

    def explain_dataset(self, X: np.ndarray, baseline_mode: str = "ensemble_root") -> Dict[str, Any]:
        """
        Computes attributions across an entire batch of instances.
        Returns matrix of attributions of shape (N, D).
        """
        X_arr = np.asarray(X, dtype=np.float64)
        N, D = X_arr.shape
        if D != self.n_features:
            raise ValueError(f"Expected {self.n_features} columns, got {D}")

        phi_matrix = np.zeros((N, D), dtype=np.float64)
        base_vals = np.zeros(N, dtype=np.float64)
        preds = np.zeros(N, dtype=np.float64)

        for i in range(N):
            res = self.explain_instance(X_arr[i], baseline_mode=baseline_mode)
            phi_matrix[i, :] = res["attributions_array"]
            base_vals[i] = res["base_value"]
            preds[i] = res["prediction_probability"]

        # Mean absolute importance
        mean_abs_importance = np.mean(np.abs(phi_matrix), axis=0)
        mean_signed_importance = np.mean(phi_matrix, axis=0)

        importance_df = pd.DataFrame({
            "feature_name": self.feature_names,
            "mean_abs_shap": mean_abs_importance,
            "mean_signed_shap": mean_signed_importance,
        }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
        importance_df["rank"] = range(1, len(importance_df) + 1)

        return {
            "shap_values": phi_matrix,
            "base_values": base_vals,
            "prediction_probabilities": preds,
            "importance_ranking": importance_df,
            "global_base_value": float(np.mean(base_vals)),
            "baseline_mode": baseline_mode,
        }

        return {
            "shap_values": phi_matrix,
            "base_values": base_vals,
            "prediction_probabilities": preds,
            "importance_ranking": importance_df,
            "global_base_value": float(np.mean(base_vals)),
        }


def investigate_feature_redundancy(df: pd.DataFrame, feature_cols: List[str]) -> Dict[str, Any]:
    """
    Quantifies mathematical redundancy and collinearity between features,
    specifically focusing on vv_minus_vh_db vs. cross_pol_ratio.
    """
    pearson_matrix = df[feature_cols].corr(method="pearson")
    spearman_matrix = df[feature_cols].corr(method="spearman")

    p_corr, p_pval = pearsonr(df["vv_minus_vh_db"], df["cross_pol_ratio"])
    s_corr, s_pval = spearmanr(df["vv_minus_vh_db"], df["cross_pol_ratio"])

    # Physical and mathematical diagnosis
    redundancy_verdict = (
        "STRICT_MONOTONIC_REDUNDANCY: cross_pol_ratio is defined as clip(10 ** (vv_minus_vh_db / 10), 0, 100). "
        "The Spearman rank correlation is 1.0000 across unclipped domains. In a tree ensemble, splits on "
        "cross_pol_ratio and vv_minus_vh_db partition the sample space along identical ordering, causing "
        "credit-splitting in tree-path attributions."
    )

    return {
        "pearson_correlation_matrix": pearson_matrix,
        "spearman_correlation_matrix": spearman_matrix,
        "vv_minus_vh_vs_cross_pol_ratio": {
            "pearson_r": float(p_corr),
            "pearson_pvalue": float(p_pval),
            "spearman_r": float(s_corr),
            "spearman_pvalue": float(s_pval),
            "verdict": redundancy_verdict,
        }
    }


def compute_grouped_attributions(
    shap_matrix: np.ndarray,
    feature_names: List[str]
) -> pd.DataFrame:
    """
    Aggregates correlated features into physically meaningful groups:
      1. Radiometric Backscatter: [vv_db, vh_db]
      2. Polarization Ratio: [vv_minus_vh_db, cross_pol_ratio]
      3. Spatial Texture: [texture_vv, texture_vh]
    """
    f_map = {name: i for i, name in enumerate(feature_names)}

    groups = {
        "radiometric_backscatter": ["vv_db", "vh_db"],
        "polarization_ratio_group": ["vv_minus_vh_db", "cross_pol_ratio"],
        "spatial_texture_group": ["texture_vv", "texture_vh"],
    }

    grouped_abs_mean = {}
    grouped_signed_mean = {}

    for g_name, feats in groups.items():
        indices = [f_map[f] for f in feats if f in f_map]
        sub_matrix = shap_matrix[:, indices]
        # Sum signed attributions per instance, then compute mean absolute impact
        group_instance_sum = np.sum(sub_matrix, axis=1)
        grouped_abs_mean[g_name] = float(np.mean(np.abs(group_instance_sum)))
        grouped_signed_mean[g_name] = float(np.mean(group_instance_sum))

    total_abs = sum(grouped_abs_mean.values())
    df_grouped = pd.DataFrame([
        {
            "feature_group": g_name,
            "constituent_features": ", ".join(groups[g_name]),
            "mean_abs_attribution": grouped_abs_mean[g_name],
            "attribution_fraction_pct": round((grouped_abs_mean[g_name] / total_abs) * 100.0, 2) if total_abs > 0 else 0.0,
            "mean_signed_attribution": round(grouped_signed_mean[g_name], 4),
        }
        for g_name in groups
    ]).sort_values("mean_abs_attribution", ascending=False).reset_index(drop=True)

    df_grouped["rank"] = range(1, len(df_grouped) + 1)
    return df_grouped


def evaluate_probability_calibration(
    probabilities: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> Dict[str, Any]:
    """
    Computes reliability diagram statistics and Brier score.
    Distinguishes model probability from physical certainty.
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2.0
    bin_counts = np.zeros(n_bins, dtype=int)
    bin_mean_pred = np.zeros(n_bins, dtype=float)
    bin_empirical_pos = np.zeros(n_bins, dtype=float)

    for i in range(n_bins):
        mask = (probabilities >= bins[i]) & (probabilities < bins[i + 1])
        if i == n_bins - 1:
            mask = mask | (probabilities == bins[i + 1])
        
        count = int(np.sum(mask))
        bin_counts[i] = count
        if count > 0:
            bin_mean_pred[i] = float(np.mean(probabilities[mask]))
            bin_empirical_pos[i] = float(np.mean(labels[mask]))
        else:
            bin_mean_pred[i] = float(bin_centers[i])
            bin_empirical_pos[i] = float(bin_centers[i])

    brier_score = float(np.mean((probabilities - labels) ** 2))
    
    # Expected Calibration Error (ECE)
    valid_samples = len(probabilities)
    ece = float(np.sum((bin_counts / valid_samples) * np.abs(bin_mean_pred - bin_empirical_pos)))

    df_bins = pd.DataFrame({
        "bin_lower": bins[:-1],
        "bin_upper": bins[1:],
        "sample_count": bin_counts,
        "mean_predicted_prob": np.round(bin_mean_pred, 4),
        "empirical_water_fraction": np.round(bin_empirical_pos, 4),
        "calibration_gap": np.round(bin_mean_pred - bin_empirical_pos, 4),
    })

    return {
        "brier_score": round(brier_score, 4),
        "expected_calibration_error": round(ece, 4),
        "calibration_bins_df": df_bins,
    }


def tree_conditional_expectation(node: Any, x: np.ndarray, coalition_features: Any) -> float:
    """
    Recursively computes conditional expectation E[f(x) | x_S] down a decision tree node.
    coalition_features: set or frozenset of feature indices whose values are known.
    Features outside the coalition are marginalized across subtrees weighted by sample count.
    """
    if node.is_leaf:
        return float(node.prob)

    f_idx = node.feature
    if f_idx in coalition_features:
        if x[f_idx] <= node.threshold:
            return tree_conditional_expectation(node.left, x, coalition_features)
        else:
            return tree_conditional_expectation(node.right, x, coalition_features)
    else:
        n_l = getattr(node.left, "n_samples", 1) if node.left else 1
        n_r = getattr(node.right, "n_samples", 1) if node.right else 1
        n_total = n_l + n_r
        w_l = n_l / n_total if n_total > 0 else 0.5
        w_r = n_r / n_total if n_total > 0 else 0.5
        e_l = tree_conditional_expectation(node.left, x, coalition_features)
        e_r = tree_conditional_expectation(node.right, x, coalition_features)
        return float(w_l * e_l + w_r * e_r)


def compute_exact_tree_shapley(tree: Any, x: np.ndarray, n_features: int) -> Tuple[float, np.ndarray]:
    r"""
    Computes exact coalition-averaged Shapley values for a decision tree over all 2^D coalitions.
    Evaluates:
        phi_i = sum_{S subseteq F \ {i}} [ |S|!(|F|-|S|-1)! / |F|! ] * [ v(S cup {i}) - v(S) ]
    where v(S) = E[f(x) | x_S] is evaluated via path-weight tree conditioning.
    """
    x_arr = np.asarray(x, dtype=np.float64).ravel()
    features = list(range(n_features))
    shapley_values = np.zeros(n_features, dtype=np.float64)
    v_cache: Dict[frozenset, float] = {}

    def get_v(S_set: frozenset) -> float:
        if S_set not in v_cache:
            v_cache[S_set] = tree_conditional_expectation(tree.root, x_arr, S_set)
        return v_cache[S_set]

    v_empty = get_v(frozenset())

    for i in features:
        other_features = [f for f in features if f != i]
        phi_i = 0.0
        for r in range(len(other_features) + 1):
            weight = math.factorial(r) * math.factorial(n_features - r - 1) / math.factorial(n_features)
            for S in itertools.combinations(other_features, r):
                S_frozenset = frozenset(S)
                v_with = get_v(S_frozenset | frozenset([i]))
                v_without = get_v(S_frozenset)
                phi_i += weight * (v_with - v_without)
        shapley_values[i] = phi_i

    return float(v_empty), shapley_values


def compute_exact_ensemble_shapley(model: Any, x: np.ndarray, n_features: int) -> Tuple[float, np.ndarray]:
    """
    Computes exact coalition-averaged Shapley values across an ensemble of decision trees.
    Linearity of Shapley values guarantees phi_ensemble = mean_t(phi_t).
    """
    x_arr = np.asarray(x, dtype=np.float64).ravel()
    n_trees = len(model.estimators_)
    accum_base = 0.0
    accum_shapley = np.zeros(n_features, dtype=np.float64)

    for tree in model.estimators_:
        base_t, shap_t = compute_exact_tree_shapley(tree, x_arr, n_features)
        accum_base += base_t
        accum_shapley += shap_t

    return float(accum_base / n_trees), accum_shapley / n_trees


def explain_prediction_records(
    explainer: TreePathExplainer,
    records: List[Any],
    region_id: Optional[str] = None,
    model_version: Optional[str] = None,
) -> pd.DataFrame:
    """
    Produces structured explanation records from a list of PredictionRecord objects.
    Validates region and model metadata to preserve multi-region decoupling.
    """
    rows = []
    for rec in records:
        rec_dict = rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)
        if region_id and rec_dict.get("region_id") != region_id:
            raise ValueError(f"Record region_id '{rec_dict.get('region_id')}' mismatches requested '{region_id}'")
        if model_version and rec_dict.get("model_version") != model_version:
            raise ValueError(f"Record model_version '{rec_dict.get('model_version')}' mismatches requested '{model_version}'")

        feat_vals = np.array(rec_dict["feature_values"], dtype=np.float64)
        explanation = explainer.explain_instance(feat_vals)

        row = {
            "model_version": rec_dict["model_version"],
            "region_id": rec_dict["region_id"],
            "dataset_id": rec_dict["dataset_id"],
            "pixel_row": rec_dict.get("pixel_row"),
            "pixel_col": rec_dict.get("pixel_col"),
            "utm_x": rec_dict.get("utm_x"),
            "utm_y": rec_dict.get("utm_y"),
            "prediction_probability": explanation["prediction_probability"],
            "base_value": explanation["base_value"],
            "sum_attributions": explanation["sum_attributions"],
            "additivity_error": explanation["additivity_error"],
            "is_additive": explanation["is_additive"],
        }
        for fn in explainer.feature_names:
            row[f"shap_{fn}"] = explanation["attributions"].get(fn, 0.0)
        rows.append(row)

    return pd.DataFrame(rows)

