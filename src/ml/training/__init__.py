"""
Model Training & Experimentation Package.
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from src.ml.training.dataset_splitter import SpatialTemporalSplitter
from src.ml.training.feature_selection import FeatureAnalyzer
from src.ml.training.trainer import (
    ModelTrainer,
    compute_binary_classification_metrics,
)

__all__ = [
    "SpatialTemporalSplitter",
    "FeatureAnalyzer",
    "ModelTrainer",
    "compute_binary_classification_metrics",
]
