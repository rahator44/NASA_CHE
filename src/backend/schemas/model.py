"""
Model & Explainability API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class ModelInfoResponse(BaseModel):
    model_id: str
    architecture: str
    n_estimators: int
    max_depth: int
    min_samples_leaf: int
    max_features: str
    optimal_probability_threshold: float
    status: str
    primary_baseline_reference: str
    sha256: str
    artifact_path: str
    created_at: str
    purpose: str


class ModelMetricsResponse(BaseModel):
    model_id: str
    evaluation_dataset: str
    total_test_samples: int
    decision_threshold: float
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float
    confusion_matrix: Dict[str, int]
    epoch_breakdown: Dict[str, Dict[str, int]]


class FeatureImportanceItem(BaseModel):
    feature_name: str
    rank: int
    mean_abs_shap: float
    mean_signed_shap: float
    description: str


class GroupedAttributionItem(BaseModel):
    group_name: str
    rank: int
    constituent_features: str
    mean_abs_attribution: float
    attribution_percentage: float
    mean_signed_attribution: float


class ModelFeaturesResponse(BaseModel):
    model_id: str
    feature_names: List[str]
    feature_schema_version: str
    gini_importance: Dict[str, float]
    permutation_importance: Dict[str, float]
    feature_redundancy_summary: Dict[str, Any]


class LocalExplanationCase(BaseModel):
    case_id: str
    category: str
    epoch: str
    utm_coordinates: List[float]
    optical_reference_label: int
    rf_prediction: int
    rf_probability: float
    base_value: float
    sum_attributions: float
    additivity_error: float
    feature_attributions: Dict[str, float]
    description: str


class ModelExplanationsResponse(BaseModel):
    model_id: str
    explainability_engine: str
    scientific_formulation: str
    global_base_value_training_background: float
    ensemble_root_base_value: float
    global_importance_ranking: List[FeatureImportanceItem]
    grouped_attributions: List[GroupedAttributionItem]
    representative_local_cases: List[LocalExplanationCase]


class ModelDiagnosticsResponse(BaseModel):
    model_id: str
    calibration_status: str = "UNCALIBRATED"
    brier_score: float
    expected_calibration_error: float
    calibration_bins: List[Dict[str, Any]]
    decision_margin_interpretation: str
    false_positive_analysis: Dict[str, Any]
    epistemological_disclaimer: str

