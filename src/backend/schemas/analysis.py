"""
Analysis Catalogue & Results API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class AnalysisDefinition(BaseModel):
    analysis_id: str
    name: str
    category: str
    description: str
    methodology: str
    scientific_basis: str
    input_requirements: List[str]
    outputs_generated: List[str]
    scientific_limitations: List[str]


class AnalysisListResponse(BaseModel):
    total_analyses: int
    analyses: List[AnalysisDefinition]


class AnalysisRunRecord(BaseModel):
    run_id: str
    analysis_type: str
    region_id: str
    status: str
    executed_at: str
    completed_at: Optional[str] = None
    parameters: Dict[str, Any]
    outputs: Dict[str, Any]
    metadata: Dict[str, Any]


class ResultListResponse(BaseModel):
    total_results: int
    results: List[AnalysisRunRecord]

