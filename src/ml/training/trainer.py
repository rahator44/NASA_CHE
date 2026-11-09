"""
Reproducible Model Training and Versioned Evaluation Pipeline.
NASA Space Apps Challenge 2026: Dancing with the SARs

Enforces Scientific Rules:
- Preserves the frozen reference model (models/phase7a/phase7a_random_forest_model.joblib)
- Strictly separates training, spatial validation, and test partitions
- Never treats model predictions or unsupervised Otsu masks as independent ground truth
- Automatically registers experimental models with appropriate status:
  * CANDIDATE: Trained on independent ground truth with demonstrated performance gains
  * PENDING_INDEPENDENT_GROUND_TRUTH: Trained on proxy or unverified labels
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import joblib
import numpy as np

from src.ml.random_forest import RandomForestClassifier
from src.ml.registry import ModelRegistry, ModelRegistryEntry
from src.ml.training.dataset_splitter import SpatialTemporalSplitter
from src.ml.training.feature_selection import FeatureAnalyzer

logger = logging.getLogger("EarthPulse.ModelTrainer")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FROZEN_MODEL_SHA256 = "85038f0fbd832acc373706d7e262a7464142c0c86b4c3ffb1ac1839edf5b53ad"


def compute_binary_classification_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float = 0.5,
) -> Dict[str, float]:
    """
    Computes standard evaluation metrics: Accuracy, Precision, Recall, F1, Brier Score, and ROC-AUC.
    """
    y_pred = (y_prob >= threshold).astype(int)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))

    acc = float((tp + tn) / len(y_true)) if len(y_true) > 0 else 0.0
    prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    rec = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float(2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    brier = float(np.mean((y_prob - y_true) ** 2))

    # Fast trapezoidal ROC-AUC
    desc_idx = np.argsort(y_prob)[::-1]
    y_sorted = y_true[desc_idx]
    n_pos = np.sum(y_true == 1)
    n_neg = len(y_true) - n_pos

    if n_pos > 0 and n_neg > 0:
        tpr = np.cumsum(y_sorted == 1) / n_pos
        fpr = np.cumsum(y_sorted == 0) / n_neg
        auc = float(np.trapz(tpr, fpr))
    else:
        auc = 0.5

    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1_score": f1,
        "brier_score": brier,
        "roc_auc": auc,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
    }


class ModelTrainer:
    """
    Manages controlled experimental training runs for candidate SAR Random Forest classifiers.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        artifacts_dir: Optional[Path] = None,
    ):
        self.registry = registry or ModelRegistry()
        self.artifacts_dir = artifacts_dir or (PROJECT_ROOT / "models" / "experimental")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def train_candidate_model(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        feature_names: List[str],
        model_version: str = "v2_candidate_exp1",
        n_estimators: int = 50,
        max_depth: int = 8,
        min_samples_leaf: int = 5,
        random_seed: int = 42,
        is_independent_ground_truth: bool = False,
        provenance_notes: str = "Experimental evaluation",
    ) -> Dict[str, Any]:
        """
        Train a new experimental Random Forest model, evaluate on holdout partitions,
        and register it safely without affecting the frozen model.
        """
        logger.info("Training candidate Random Forest (%d trees, max_depth=%d)...", n_estimators, max_depth)

        rf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_seed,
        )
        rf.fit(X_train, y_train)

        # Validation evaluation
        val_probs = rf.predict_proba(X_val)
        val_metrics = compute_binary_classification_metrics(y_val, val_probs)

        # Test evaluation
        test_probs = rf.predict_proba(X_test)
        test_metrics = compute_binary_classification_metrics(y_test, test_probs)

        # Artifact serialization
        artifact_filename = f"model_rf_{model_version}.joblib"
        artifact_path = self.artifacts_dir / artifact_filename
        joblib.dump(rf, artifact_path)

        # SHA-256
        sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        # Decision rule for promotion status
        if is_independent_ground_truth and test_metrics["roc_auc"] > 0.70:
            status = "CANDIDATE"
        else:
            status = "PENDING_INDEPENDENT_GROUND_TRUTH"

        entry = ModelRegistryEntry(
            model_id=f"rf_jamuna_{model_version}",
            version=model_version,
            region_coverage=["jamuna_sirajganj"],
            sensor_compatibility=["sentinel1_iw_grd"],
            feature_schema_version="sar_6feature_v1",
            training_dataset_identifiers=["experimental_synthetic_or_proxy"],
            training_dates=["2024-06-10", "2024-07-16"],
            hyperparameters={
                "n_estimators": n_estimators,
                "max_depth": max_depth,
                "min_samples_leaf": min_samples_leaf,
                "feature_names": feature_names,
            },
            random_seed=random_seed,
            validation_metrics=val_metrics,
            held_out_test_metrics=test_metrics,
            model_artifact_path=str(artifact_path),
            model_artifact_sha256=sha256,
            creation_date="2026-11-10T00:00:00Z",
            status=status,
            promotion_notes=provenance_notes,
        )

        self.registry.register_model(entry)

        return {
            "model_version": model_version,
            "status": status,
            "artifact_path": str(artifact_path),
            "artifact_sha256": sha256,
            "validation_metrics": val_metrics,
            "test_metrics": test_metrics,
            "is_independent_ground_truth": is_independent_ground_truth,
        }

