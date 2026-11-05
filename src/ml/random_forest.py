"""
Earth Pulse — Machine Learning Engine: Fast Vectorized Pure-NumPy Random Forest
NASA Space Apps Challenge 2026: Dancing with the SARs

Provides a high-performance, deterministic Decision Tree and Random Forest Classifier
compatible with Scikit-Learn API conventions (fit, predict, predict_proba, feature_importances_).
Optimized for CPU processing via vectorized broadcast threshold search.
Requires only NumPy and joblib.
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np


class DecisionNode:
    """Represents an internal node or leaf in a classification tree."""

    __slots__ = ["feature", "threshold", "left", "right", "prob", "impurity", "n_samples", "is_leaf"]

    def __init__(
        self,
        feature: Optional[int] = None,
        threshold: Optional[float] = None,
        left: Optional["DecisionNode"] = None,
        right: Optional["DecisionNode"] = None,
        prob: float = 0.5,
        impurity: float = 0.0,
        n_samples: int = 0,
        is_leaf: bool = False,
    ):
        self.feature = feature
        self.threshold = threshold
        self.left = left
        self.right = right
        self.prob = prob
        self.impurity = impurity
        self.n_samples = n_samples
        self.is_leaf = is_leaf


class DecisionTreeClassifier:
    """
    Binary Classification Decision Tree using Gini Impurity.
    Supports sample weights, max_depth, min_samples_leaf, and random feature subsets.
    Uses fast vectorized threshold evaluation for high throughput on CPU.
    """

    def __init__(
        self,
        max_depth: int = 10,
        min_samples_leaf: int = 5,
        max_features: Optional[Union[int, float, str]] = "sqrt",
        random_state: Optional[int] = None,
        n_thresholds: int = 10,
    ):
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.random_state = random_state
        self.n_thresholds = n_thresholds
        self.root: Optional[DecisionNode] = None
        self.feature_importances_: Optional[np.ndarray] = None
        self.n_features_: int = 0

    def fit(self, X: np.ndarray, y: np.ndarray, sample_weight: Optional[np.ndarray] = None) -> "DecisionTreeClassifier":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int32)
        n_samples, n_features = X.shape
        self.n_features_ = n_features

        if sample_weight is None:
            w = np.ones(n_samples, dtype=np.float32)
        else:
            w = np.asarray(sample_weight, dtype=np.float32)

        rng = np.random.RandomState(self.random_state)
        self.feature_importances_ = np.zeros(n_features, dtype=np.float64)

        self.root = self._build_node(X, y, w, depth=0, rng=rng)

        total_imp = np.sum(self.feature_importances_)
        if total_imp > 0:
            self.feature_importances_ /= total_imp

        return self

    def _gini(self, y: np.ndarray, w: np.ndarray, total_w: float) -> float:
        if total_w <= 1e-9:
            return 0.0
        w1 = float(np.sum(w[y == 1]))
        p1 = w1 / total_w
        p0 = 1.0 - p1
        return 1.0 - (p1 * p1 + p0 * p0)

    def _build_node(
        self,
        X: np.ndarray,
        y: np.ndarray,
        w: np.ndarray,
        depth: int,
        rng: np.random.RandomState,
    ) -> DecisionNode:
        n_samples = len(y)
        total_w = float(np.sum(w))
        w1 = float(np.sum(w[y == 1]))
        prob = w1 / total_w if total_w > 1e-9 else 0.5
        current_impurity = self._gini(y, w, total_w)

        if (
            depth >= self.max_depth
            or n_samples < 2 * self.min_samples_leaf
            or current_impurity <= 1e-7
            or prob <= 1e-7
            or prob >= (1.0 - 1e-7)
        ):
            return DecisionNode(
                prob=prob,
                impurity=current_impurity,
                n_samples=n_samples,
                is_leaf=True,
            )

        if self.max_features == "sqrt":
            m_feat = max(1, int(math.sqrt(self.n_features_)))
        elif self.max_features == "log2":
            m_feat = max(1, int(math.log2(self.n_features_)))
        elif isinstance(self.max_features, float):
            m_feat = max(1, int(self.max_features * self.n_features_))
        elif isinstance(self.max_features, int):
            m_feat = max(1, min(self.max_features, self.n_features_))
        else:
            m_feat = self.n_features_

        feat_indices = rng.choice(self.n_features_, size=m_feat, replace=False)

        best_gain = -1.0
        best_feat = -1
        best_thresh = 0.0

        # Vectorized candidate search
        wy = w * y

        for feat in feat_indices:
            x_col = X[:, feat]
            x_min, x_max = float(np.min(x_col)), float(np.max(x_col))
            if x_max - x_min <= 1e-7:
                continue

            # Linear candidate thresholds
            thresholds = np.linspace(x_min, x_max, self.n_thresholds + 2, dtype=np.float32)[1:-1]

            # Vectorized evaluation: (N, K)
            left_mask = x_col[:, None] <= thresholds[None, :]
            n_left = np.sum(left_mask, axis=0)
            n_right = n_samples - n_left

            valid_thresh = (n_left >= self.min_samples_leaf) & (n_right >= self.min_samples_leaf)
            if not np.any(valid_thresh):
                continue

            w_left = np.sum(w[:, None] * left_mask, axis=0)
            w_right = total_w - w_left

            w1_left = np.sum(wy[:, None] * left_mask, axis=0)
            w1_right = w1 - w1_left

            p1_l = w1_left / np.maximum(w_left, 1e-9)
            p1_r = w1_right / np.maximum(w_right, 1e-9)

            gini_l = 1.0 - (p1_l**2 + (1.0 - p1_l)**2)
            gini_r = 1.0 - (p1_r**2 + (1.0 - p1_r)**2)

            gains = current_impurity - ((w_left / total_w) * gini_l + (w_right / total_w) * gini_r)
            gains[~valid_thresh] = -1.0

            max_idx = int(np.argmax(gains))
            if gains[max_idx] > best_gain:
                best_gain = float(gains[max_idx])
                best_feat = feat
                best_thresh = float(thresholds[max_idx])

        if best_gain <= 1e-7 or best_feat < 0:
            return DecisionNode(
                prob=prob,
                impurity=current_impurity,
                n_samples=n_samples,
                is_leaf=True,
            )

        self.feature_importances_[best_feat] += best_gain * total_w

        left_mask = X[:, best_feat] <= best_thresh
        right_mask = ~left_mask

        left_child = self._build_node(X[left_mask], y[left_mask], w[left_mask], depth + 1, rng)
        right_child = self._build_node(X[right_mask], y[right_mask], w[right_mask], depth + 1, rng)

        return DecisionNode(
            feature=best_feat,
            threshold=best_thresh,
            left=left_child,
            right=right_child,
            prob=prob,
            impurity=current_impurity,
            n_samples=n_samples,
            is_leaf=False,
        )

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        n_samples = X.shape[0]
        probs = np.empty((n_samples, 2), dtype=np.float32)

        for i in range(n_samples):
            node = self.root
            row = X[i]
            while not node.is_leaf:
                if row[node.feature] <= node.threshold:
                    node = node.left
                else:
                    node = node.right
            p1 = node.prob
            probs[i, 0] = 1.0 - p1
            probs[i, 1] = p1

        return probs

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        probs = self.predict_proba(X)
        return (probs[:, 1] >= threshold).astype(np.int32)


class RandomForestClassifier:
    """
    Ensemble Random Forest Classifier for Binary Water Classification.
    Provides scikit-learn API: fit, predict, predict_proba, feature_importances_.
    """

    def __init__(
        self,
        n_estimators: int = 50,
        max_depth: int = 8,
        min_samples_leaf: int = 10,
        max_features: Optional[Union[int, float, str]] = "sqrt",
        random_state: Optional[int] = 42,
        class_weight: Optional[str] = "balanced",
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.random_state = random_state
        self.class_weight = class_weight

        self.estimators_: List[DecisionTreeClassifier] = []
        self.feature_importances_: Optional[np.ndarray] = None
        self.n_features_: int = 0
        self.classes_ = np.array([0, 1], dtype=np.int32)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RandomForestClassifier":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int32)
        n_samples, n_features = X.shape
        self.n_features_ = n_features
        self.estimators_ = []

        if self.class_weight == "balanced":
            n_0 = max(1, int(np.sum(y == 0)))
            n_1 = max(1, int(np.sum(y == 1)))
            w_0 = n_samples / (2.0 * n_0)
            w_1 = n_samples / (2.0 * n_1)
            sample_weight = np.where(y == 1, w_1, w_0).astype(np.float32)
        else:
            sample_weight = np.ones(n_samples, dtype=np.float32)

        master_rng = np.random.RandomState(self.random_state)
        feature_importances_accum = np.zeros(n_features, dtype=np.float64)

        for _ in range(self.n_estimators):
            tree_seed = int(master_rng.randint(0, 1000000))
            tree_rng = np.random.RandomState(tree_seed)

            # Subsample for tree training: 75% bootstrap size for speed and diversity
            sample_size = int(0.75 * n_samples)
            bootstrap_indices = tree_rng.choice(n_samples, size=sample_size, replace=True)
            X_b = X[bootstrap_indices]
            y_b = y[bootstrap_indices]
            w_b = sample_weight[bootstrap_indices]

            tree = DecisionTreeClassifier(
                max_depth=self.max_depth,
                min_samples_leaf=self.min_samples_leaf,
                max_features=self.max_features,
                random_state=tree_seed,
                n_thresholds=10,
            )
            tree.fit(X_b, y_b, sample_weight=w_b)
            self.estimators_.append(tree)

            if tree.feature_importances_ is not None:
                feature_importances_accum += tree.feature_importances_

        total_imp = np.sum(feature_importances_accum)
        if total_imp > 0:
            self.feature_importances_ = feature_importances_accum / total_imp
        else:
            self.feature_importances_ = np.ones(n_features) / n_features

        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Computes mean predicted probability across all ensemble trees."""
        X = np.asarray(X, dtype=np.float32)
        n_samples = X.shape[0]
        prob_accum = np.zeros((n_samples, 2), dtype=np.float32)

        for tree in self.estimators_:
            prob_accum += tree.predict_proba(X)

        prob_accum /= len(self.estimators_)
        return prob_accum

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Predicts class labels using a specified probability threshold."""
        probs = self.predict_proba(X)
        return (probs[:, 1] >= threshold).astype(np.int32)

    def save(self, filepath: Union[str, Any]) -> None:
        """Serializes model to disk using joblib."""
        payload = {
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "min_samples_leaf": self.min_samples_leaf,
            "max_features": self.max_features,
            "random_state": self.random_state,
            "class_weight": self.class_weight,
            "feature_importances_": self.feature_importances_,
            "n_features_": self.n_features_,
            "estimators_": self.estimators_,
        }
        joblib.dump(payload, filepath, compress=3)

    @classmethod
    def load(cls, filepath: Union[str, Any]) -> "RandomForestClassifier":
        """Loads serialized model from disk using joblib."""
        payload = joblib.load(filepath)
        rf = cls(
            n_estimators=payload["n_estimators"],
            max_depth=payload["max_depth"],
            min_samples_leaf=payload["min_samples_leaf"],
            max_features=payload["max_features"],
            random_state=payload["random_state"],
            class_weight=payload["class_weight"],
        )
        rf.feature_importances_ = payload["feature_importances_"]
        rf.n_features_ = payload["n_features_"]
        rf.estimators_ = payload["estimators_"]
        return rf


def compute_permutation_importance(
    model: RandomForestClassifier,
    X: np.ndarray,
    y: np.ndarray,
    n_repeats: int = 5,
    random_seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes permutation feature importance on held-out validation data.
    Returns (importance_means, importance_stds) based on F1-score drop.
    """
    from scripts.ml_metrics import compute_classification_metrics

    baseline_metrics = compute_classification_metrics(y, model.predict(X))
    baseline_f1 = baseline_metrics["f1_score"]

    n_features = X.shape[1]
    importances = np.zeros((n_features, n_repeats), dtype=np.float64)
    rng = np.random.RandomState(random_seed)

    for f_idx in range(n_features):
        for rep in range(n_repeats):
            X_perm = np.copy(X)
            perm_indices = rng.permutation(X.shape[0])
            X_perm[:, f_idx] = X_perm[perm_indices, f_idx]

            perm_preds = model.predict(X_perm)
            perm_metrics = compute_classification_metrics(y, perm_preds)
            f1_drop = baseline_f1 - perm_metrics["f1_score"]
            importances[f_idx, rep] = max(0.0, f1_drop)

    mean_imp = np.mean(importances, axis=1)
    std_imp = np.std(importances, axis=1)
    return mean_imp, std_imp
