"""
Feature Selection, Redundancy Analysis, and Class Balancing.
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Tuple
import numpy as np


class FeatureAnalyzer:
    """
    Computes multicollinearity, feature importance, and class balancing weights.
    """

    @staticmethod
    def compute_correlation_matrix(
        X: np.ndarray,
        feature_names: List[str],
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculates Pearson cross-correlation matrix across SAR features.
        """
        corr = np.corrcoef(X, rowvar=False)
        result = {}
        for i, name_i in enumerate(feature_names):
            result[name_i] = {}
            for j, name_j in enumerate(feature_names):
                result[name_i][name_j] = float(corr[i, j])
        return result

    @staticmethod
    def compute_class_weights(
        y: np.ndarray,
    ) -> Dict[int, float]:
        """
        Calculates balanced class weights for severe water/land class imbalance.
        w_j = n_samples / (n_classes * n_samples_j)
        """
        classes, counts = np.unique(y, return_counts=True)
        n_samples = len(y)
        n_classes = len(classes)
        weights = {}
        for c, count in zip(classes, counts):
            weights[int(c)] = float(n_samples / (n_classes * count)) if count > 0 else 1.0
        return weights
