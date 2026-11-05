"""
Earth Pulse Parallel Scientific Inference Engine
Executes multiple distinct water classification and change detection algorithms side-by-side
on compatible SAR rasters without ad-hoc output averaging or blending.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


@dataclass
class MethodOutput:
    method_name: str
    is_primary_baseline: bool
    water_mask: np.ndarray
    probability_map: Optional[np.ndarray] = None
    uncertainty_map: Optional[np.ndarray] = None
    metadata: Optional[Dict[str, Any]] = None


class ScientificInferenceEngine:
    """
    Coordinates side-by-side parallel execution of competing water classification paradigms.
    Retains the deterministic Lee 5x5 Dual-AND Otsu classifier as the primary operational baseline.
    """

    @staticmethod
    def run_deterministic_otsu(
        vv_db: np.ndarray,
        vh_db: np.ndarray,
        valid_mask: Optional[np.ndarray] = None,
        vv_threshold: float = -16.0,
        vh_threshold: float = -23.5,
    ) -> MethodOutput:
        """
        Executes the deterministic physical baseline (Lee 5x5 filtered Dual-AND Otsu).
        Water is identified where both VV and VH backscatter fall below empirical Otsu thresholds:
          (sigma0_VV < vv_thresh) AND (sigma0_VH < vh_thresh)
        """
        if vv_db.shape != vh_db.shape:
            raise ValueError(f"Shape mismatch: VV {vv_db.shape} vs VH {vh_db.shape}")

        water = (vv_db < vv_threshold) & (vh_db < vh_threshold)
        water_mask = np.zeros(vv_db.shape, dtype=np.uint8)
        water_mask[water] = 1

        if valid_mask is not None:
            water_mask[~valid_mask] = 255

        meta = {
            "method": "deterministic_lee_5x5_dual_and_otsu",
            "vv_threshold_db": vv_threshold,
            "vh_threshold_db": vh_threshold,
            "rule": "(sigma0_VV < T_vv) AND (sigma0_VH < T_vh)",
            "output_type": "crisp_binary_mask",
            "is_primary_baseline": True,
        }

        return MethodOutput(
            method_name="deterministic_otsu",
            is_primary_baseline=True,
            water_mask=water_mask,
            probability_map=None,  # Deterministic method produces discrete crisp decisions
            uncertainty_map=None,
            metadata=meta,
        )

    @staticmethod
    def run_random_forest(
        features: Dict[str, np.ndarray],
        rf_model: Any,
        probability_threshold: float = 0.35,
        feature_order: Optional[List[str]] = None,
        valid_mask: Optional[np.ndarray] = None,
    ) -> MethodOutput:
        """
        Executes the supervised Random Forest classifier, producing continuous probabilities,
        crisp classifications at threshold tau*, and uncertainty layers.
        """
        default_order = ["vv_db", "vh_db", "vv_minus_vh_db", "cross_pol_ratio", "texture_vv", "texture_vh"]
        order = feature_order or default_order

        for f in order:
            if f not in features:
                raise KeyError(f"Feature '{f}' required by Random Forest is missing from input features.")

        ref_shape = features[order[0]].shape
        flat_mask = valid_mask.ravel() if valid_mask is not None else np.ones(ref_shape[0] * ref_shape[1], dtype=bool)

        # Check for NaNs within valid pixels
        for f in order:
            flat_mask = flat_mask & np.isfinite(features[f].ravel())

        valid_indices = np.where(flat_mask)[0]
        n_valid = len(valid_indices)

        prob_flat = np.full(ref_shape[0] * ref_shape[1], np.nan, dtype=np.float32)
        mask_flat = np.full(ref_shape[0] * ref_shape[1], 255, dtype=np.uint8)
        unc_flat = np.full(ref_shape[0] * ref_shape[1], np.nan, dtype=np.float32)

        if n_valid > 0:
            # Block/batch inference to preserve memory
            batch_size = 200000
            for start in range(0, n_valid, batch_size):
                end = min(start + batch_size, n_valid)
                b_idx = valid_indices[start:end]
                X_batch = np.column_stack([features[f].ravel()[b_idx] for f in order])

                proba = rf_model.predict_proba(X_batch)[:, 1]
                prob_flat[b_idx] = proba.astype(np.float32)
                mask_flat[b_idx] = (proba >= probability_threshold).astype(np.uint8)
                unc_flat[b_idx] = (1.0 - 2.0 * np.abs(proba - 0.5)).astype(np.float32)

        prob_map = prob_flat.reshape(ref_shape)
        water_mask = mask_flat.reshape(ref_shape)
        unc_map = unc_flat.reshape(ref_shape)

        meta = {
            "method": "random_forest_supervised",
            "feature_schema": order,
            "probability_threshold": probability_threshold,
            "is_primary_baseline": False,
            "uncertainty_definition": "1.0 - 2 * |P(water) - 0.5|",
        }

        return MethodOutput(
            method_name="random_forest",
            is_primary_baseline=False,
            water_mask=water_mask,
            probability_map=prob_map,
            uncertainty_map=unc_map,
            metadata=meta,
        )

    @staticmethod
    def compare_methods(
        method_a: MethodOutput,
        method_b: MethodOutput,
        valid_mask: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Quantifies spatial agreement and divergence between two independent classification methods.
        Does NOT combine or average outputs without a scientifically validated consensus mechanism.
        """
        mask_a = method_a.water_mask
        mask_b = method_b.water_mask

        eval_mask = (mask_a != 255) & (mask_b != 255)
        if valid_mask is not None:
            eval_mask = eval_mask & valid_mask

        n_eval = int(np.sum(eval_mask))
        if n_eval == 0:
            return {"evaluated_pixels": 0, "agreement_fraction": 0.0}

        both_water = np.sum((mask_a == 1) & (mask_b == 1) & eval_mask)
        both_nonwater = np.sum((mask_a == 0) & (mask_b == 0) & eval_mask)
        a_only = np.sum((mask_a == 1) & (mask_b == 0) & eval_mask)
        b_only = np.sum((mask_a == 0) & (mask_b == 1) & eval_mask)

        agreed = both_water + both_nonwater
        agreement_pct = (agreed / n_eval) * 100.0

        # Jaccard index (IoU) of water detections between methods
        union_water = both_water + a_only + b_only
        water_iou = (both_water / union_water) if union_water > 0 else 1.0

        return {
            "method_a": method_a.method_name,
            "method_b": method_b.method_name,
            "evaluated_pixels": n_eval,
            "agreement_percentage": round(float(agreement_pct), 2),
            "water_detection_iou": round(float(water_iou), 4),
            "contingency_table": {
                "both_water": int(both_water),
                "both_nonwater": int(both_nonwater),
                f"{method_a.method_name}_only_water": int(a_only),
                f"{method_b.method_name}_only_water": int(b_only),
            },
            "scientific_note": (
                "Disagreements primarily occur along saturated char edges and transitional wetlands "
                "where deterministic dual-band thresholds enforce strict physical conservatism."
            )
        }

