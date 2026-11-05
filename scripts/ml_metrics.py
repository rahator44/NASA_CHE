"""
Earth Pulse — Machine Learning Evaluation Metrics
NASA Space Apps Challenge 2026: Dancing with the SARs

Provides mathematical implementations of classification metrics,
including Confusion Matrix, Precision, Recall, F1, IoU, Specificity,
Balanced Accuracy, ROC-AUC, PR-AUC, and Brier Score in pure NumPy.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np

# Compatible trapezoid integration
try:
    _trapezoid = np.trapezoid
except AttributeError:
    try:
        from scipy.integrate import trapezoid as _trapezoid
    except ImportError:
        _trapezoid = getattr(np, "trapz")


def compute_confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, int]:
    """Computes binary confusion matrix counts."""
    y_true = np.asarray(y_true, dtype=np.int32)
    y_pred = np.asarray(y_pred, dtype=np.int32)

    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))

    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "total": len(y_true)}


def compute_roc_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Computes Area Under the Receiver Operating Characteristic Curve (ROC-AUC)."""
    y_true = np.asarray(y_true, dtype=np.int32)
    y_prob = np.asarray(y_prob, dtype=np.float64)

    n_pos = np.sum(y_true == 1)
    n_neg = np.sum(y_true == 0)
    if n_pos == 0 or n_neg == 0:
        return 0.5

    # Sort descending by predicted probability
    order = np.argsort(-y_prob)
    y_true_sorted = y_true[order]

    # Cumulative true positives and false positives
    tps = np.cumsum(y_true_sorted == 1)
    fps = np.cumsum(y_true_sorted == 0)

    tpr = tps / n_pos
    fpr = fps / n_neg

    # Prepend (0, 0) for trapezoidal integration
    tpr = np.concatenate(([0.0], tpr))
    fpr = np.concatenate(([0.0], fpr))

    return float(_trapezoid(tpr, fpr))


def compute_pr_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Computes Area Under the Precision-Recall Curve (PR-AUC) via trapezoidal rule."""
    y_true = np.asarray(y_true, dtype=np.int32)
    y_prob = np.asarray(y_prob, dtype=np.float64)

    n_pos = np.sum(y_true == 1)
    if n_pos == 0:
        return 0.0

    order = np.argsort(-y_prob)
    y_true_sorted = y_true[order]

    tps = np.cumsum(y_true_sorted == 1)
    fps = np.cumsum(y_true_sorted == 0)

    recalls = tps / n_pos
    precisions = tps / (tps + fps)

    # Prepend baseline recall=0, precision=1
    recalls = np.concatenate(([0.0], recalls))
    precisions = np.concatenate(([1.0], precisions))

    # Note: recalls goes from 0 to 1, integrate precisions over recalls
    return float(_trapezoid(precisions, recalls))


def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Computes Mean Squared Error between predicted probabilities and binary labels."""
    y_true = np.asarray(y_true, dtype=np.float64)
    y_prob = np.asarray(y_prob, dtype=np.float64)
    return float(np.mean((y_prob - y_true) ** 2))


def compute_classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Computes full suite of classification and agreement metrics."""
    cm = compute_confusion_matrix(y_true, y_pred)
    tp, fp, tn, fn = cm["tp"], cm["fp"], cm["tn"], cm["fn"]
    total = cm["total"]

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1_score = 2.0 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0
    balanced_acc = 0.5 * (recall + specificity)
    accuracy = (tp + tn) / total if total > 0 else 0.0

    metrics = {
        "confusion_matrix": cm,
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1_score": round(float(f1_score), 4),
        "iou": round(float(iou), 4),
        "specificity": round(float(specificity), 4),
        "balanced_accuracy": round(float(balanced_acc), 4),
        "accuracy": round(float(accuracy), 4),
    }

    if y_prob is not None:
        metrics["roc_auc"] = round(compute_roc_auc(y_true, y_prob), 4)
        metrics["pr_auc"] = round(compute_pr_auc(y_true, y_prob), 4)
        metrics["brier_score"] = round(compute_brier_score(y_true, y_prob), 4)

    return metrics
