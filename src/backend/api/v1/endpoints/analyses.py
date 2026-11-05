"""
Analyses Catalogue & Results API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Optional
import json
from fastapi import APIRouter, HTTPException
from src.backend.schemas.analysis import AnalysisListResponse, AnalysisDefinition, ResultListResponse, AnalysisRunRecord
from src.backend.database.database import get_db_connection

router = APIRouter()

ANALYSIS_CATALOGUE = [
    {
        "analysis_id": "flood_change_detection",
        "name": "SAR Flood Inundation & Surface-Water Transition Engine",
        "category": "Hydrological Hazard",
        "description": "Multi-temporal surface water transition mapping over the common valid domain using Adaptive Lee 5x5 Dual-AND Otsu.",
        "methodology": "Dual-AND polarization thresholding with spatial exclusion of radar shadow, layover, and ambiguous speckle noise.",
        "scientific_basis": "Empirical histogram bimodal Otsu thresholding calibrated separately on pre-monsoon and monsoon crest scenes.",
        "input_requirements": ["Sentinel-1 June 10 aligned", "Sentinel-1 July 16 aligned", "Quality masks"],
        "outputs_generated": ["phase5_flood_transitions.tif", "phase5_newly_inundated_candidate.tif", "phase5_cluster_statistics.csv"],
        "scientific_limitations": [
            "Cannot differentiate wind-roughened turbid flood margins without multi-temporal confirmation",
            "Radar shadow on steep embankments is excluded via indeterminate noise floor mask",
        ],
    },
    {
        "analysis_id": "riverbank_migration_displacement",
        "name": "Fluvial Riverbank Migration & Channel-Margin Displacement Engine",
        "category": "Fluvial Geomorphology",
        "description": "Automated 200m-spaced normal transect intersection analysis quantifying lateral channel belt expansion and char submergence.",
        "methodology": "Stream centerline generation, orthogonal transect sampling, and edge detection on filtered SAR waterlines.",
        "scientific_basis": "Quadrature error propagation accounting for pixel discretization (8.16m), orbit co-registration (5.66m), and water edge speckle (28.28m).",
        "input_requirements": ["June channel belt", "July channel belt", "Provisional stream centerline"],
        "outputs_generated": ["phase6_1_riverbank_transects.geojson", "phase6_1_channel_change_zones.tif", "phase6_2_bank_displacement_statistics.csv"],
        "scientific_limitations": [
            "Displacements reflect short-term flood stage response, not long-term subaerial cut-bank erosion rates",
            "Provisional detection range spans 35m to 85m depending on bank gradient and material consolidation",
        ],
    },
    {
        "analysis_id": "random_forest_classification",
        "name": "Supervised Pure-NumPy Random Forest Candidate Water Probability",
        "category": "Machine Learning",
        "description": "40-tree ensemble soft voting generating continuous candidate water probability layers alongside discrete decisions at tau*=0.35.",
        "methodology": "Bootstrap sub-bagging (75%), sqrt(D)=2 feature subsampling per split, and vectorized Gini impurity gain.",
        "scientific_basis": "Retained strictly as an auxiliary continuous probability layer; primary operational baseline remains adaptive Otsu.",
        "input_requirements": ["6 SAR backscatter & spatial texture features"],
        "outputs_generated": ["phase7a_random_forest_model.joblib", "phase7a_july16_water_probability.tif", "phase7a_training_samples.csv"],
        "scientific_limitations": [
            "High false positive rate on moist char sandbars due to forward specular scattering",
            "Raw ensemble probabilities are uncalibrated (Brier score 0.2270, ECE 0.0959)",
        ],
    },
    {
        "analysis_id": "model_explainability_attribution",
        "name": "Saabas Path-Dependent Tree Feature Attribution",
        "category": "Explainable AI",
        "description": "Decomposes model predictions into additive feature contributions along traversed decision tree pathways.",
        "methodology": "Pure-NumPy TreePathExplainer accumulating incremental probability shifts along observed single paths.",
        "scientific_basis": "Satisfies exact path efficiency (phi_0 + sum(phi_j) = f(x)); diverges from coalition-averaged Shapley values due to branch ordering.",
        "input_requirements": ["Registered Random Forest model", "Background evaluation samples"],
        "outputs_generated": ["phase7b_global_shap_importance.csv", "phase7b_grouped_feature_attribution.csv", "phase7b_local_prediction_explanations.csv"],
        "scientific_limitations": [
            "Tree-path attribution is path-dependent; does not average over all 2^D feature coalitions",
            "Credit-splitting between vv_minus_vh_db and cross_pol_ratio resolved via Grouped Polarization Attribution",
        ],
    },
    {
        "analysis_id": "scientific_uncertainty_audit",
        "name": "Multi-Phase Scientific Uncertainty & Validation Audit",
        "category": "Quality Assurance & Epistemology",
        "description": "Independent verification of sample accounting, confusion matrices, and empirical vs theoretical error budgets.",
        "methodology": "Cross-phase raster reconciliation, independent Sentinel-2 optical validation, and spatial block bootstrap.",
        "scientific_basis": "Strict distinction between empirically observed correlations and in-situ causal certainties.",
        "input_requirements": ["All Phase 1-7B deliverables"],
        "outputs_generated": ["phase7b1_integrity_audit.json", "phase7b1_backend_errata.json", "8 audit CSV tables"],
        "scientific_limitations": [
            "Ground-truth soil moisture measurements are unavailable; physical interpretations remain supported hypotheses",
        ],
    },
]


@router.get("/analyses", response_model=AnalysisListResponse, tags=["Analyses"])
def list_analyses():
    """Lists all available scientific analysis modules."""
    return AnalysisListResponse(total_analyses=len(ANALYSIS_CATALOGUE), analyses=ANALYSIS_CATALOGUE)


@router.get("/regions/{region_id}/analyses", response_model=AnalysisListResponse, tags=["Analyses"])
def get_region_analyses(region_id: str):
    """Lists analyses applicable to the specified region."""
    return AnalysisListResponse(total_analyses=len(ANALYSIS_CATALOGUE), analyses=ANALYSIS_CATALOGUE)


@router.get("/analyses/{analysis_id}/summary", response_model=AnalysisDefinition, tags=["Analyses"])
def get_analysis_summary(analysis_id: str):
    """Retrieves methodology, scientific basis, and limitations for a specified analysis."""
    for a in ANALYSIS_CATALOGUE:
        if a["analysis_id"] == analysis_id:
            return a
    raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")


@router.get("/regions/{region_id}/results", response_model=ResultListResponse, tags=["Analyses"])
def list_region_results(region_id: str):
    """Lists all completed analysis run results stored in the SQLite catalog."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT run_id, analysis_type, region_id, status, executed_at, completed_at, parameters, outputs, metadata
            FROM analysis_runs
            WHERE region_id = ?
            ORDER BY executed_at DESC
        """, (region_id,))
        rows = cursor.fetchall()

    results = []
    for r in rows:
        results.append({
            "run_id": r["run_id"],
            "analysis_type": r["analysis_type"],
            "region_id": r["region_id"],
            "status": r["status"],
            "executed_at": r["executed_at"],
            "completed_at": r["completed_at"],
            "parameters": json.loads(r["parameters"]) if r["parameters"] else {},
            "outputs": json.loads(r["outputs"]) if r["outputs"] else {},
            "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
        })

    return ResultListResponse(total_results=len(results), results=results)


@router.get("/results/{result_id}", response_model=AnalysisRunRecord, tags=["Analyses"])
def get_result(result_id: str):
    """Retrieves detailed record for a completed analysis run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT run_id, analysis_type, region_id, status, executed_at, completed_at, parameters, outputs, metadata
            FROM analysis_runs
            WHERE run_id = ?
        """, (result_id,))
        r = cursor.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail=f"Result '{result_id}' not found.")

    return {
        "run_id": r["run_id"],
        "analysis_type": r["analysis_type"],
        "region_id": r["region_id"],
        "status": r["status"],
        "executed_at": r["executed_at"],
        "completed_at": r["completed_at"],
        "parameters": json.loads(r["parameters"]) if r["parameters"] else {},
        "outputs": json.loads(r["outputs"]) if r["outputs"] else {},
        "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
    }

