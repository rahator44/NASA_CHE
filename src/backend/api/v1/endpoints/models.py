"""
Model & Explainability API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import List
from fastapi import APIRouter, HTTPException
from src.backend.schemas.model import (
    ModelInfoResponse,
    ModelMetricsResponse,
    ModelFeaturesResponse,
    ModelExplanationsResponse,
    ModelDiagnosticsResponse,
)
from src.backend.services.model_service import ModelService

router = APIRouter()


@router.get("/models", response_model=List[ModelInfoResponse], tags=["Models & Explainability"])
def list_models():
    """Lists registered machine learning models and operational baselines."""
    return ModelService.list_models()


@router.get("/models/{model_id}", response_model=ModelInfoResponse, tags=["Models & Explainability"])
def get_model(model_id: str):
    """Retrieves architecture, status, artifact path, and checksum for a registered model."""
    m = ModelService.get_model(model_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    return m


@router.get("/models/{model_id}/metrics", response_model=ModelMetricsResponse, tags=["Models & Explainability"])
def get_model_metrics(model_id: str):
    """Retrieves held-out evaluation metrics, confusion matrix, and epoch breakdowns."""
    metrics = ModelService.get_metrics(model_id)
    if not metrics:
        raise HTTPException(status_code=404, detail=f"Metrics unavailable for model '{model_id}'.")
    return metrics


@router.get("/models/{model_id}/features", response_model=ModelFeaturesResponse, tags=["Models & Explainability"])
def get_model_features(model_id: str):
    """Retrieves feature schema, Gini importance, permutation importance, and redundancy audit."""
    feat = ModelService.get_features(model_id)
    if not feat:
        raise HTTPException(status_code=404, detail=f"Features unavailable for model '{model_id}'.")
    return feat


@router.get("/models/{model_id}/explanations", response_model=ModelExplanationsResponse, tags=["Models & Explainability"])
def get_model_explanations(model_id: str):
    """Retrieves global tree-path attribution rankings, grouped features, and representative local cases."""
    exp = ModelService.get_explanations(model_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Explanations unavailable for model '{model_id}'.")
    return exp


@router.get("/models/{model_id}/diagnostics", response_model=ModelDiagnosticsResponse, tags=["Models & Explainability"])
def get_model_diagnostics(model_id: str):
    """Retrieves calibration statistics, Brier score, ECE, decision margin interpretation, and false positive analysis."""
    diag = ModelService.get_diagnostics(model_id)
    if not diag:
        raise HTTPException(status_code=404, detail=f"Diagnostics unavailable for model '{model_id}'.")
    return diag

