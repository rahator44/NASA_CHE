"""
Job Management API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    job_type: str = Field(..., description="Allowlisted job action (e.g. audit_environment, verify_dataset_integrity, generate_flood_summary, generate_riverbank_summary, run_model_explainability_audit)")
    region_id: str = Field(default="jamuna_sirajganj")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)


class JobResponse(BaseModel):
    job_id: str
    job_type: str
    region_id: str
    status: str
    progress_pct: float
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_summary: Optional[str] = None
    output_references: Optional[Dict[str, Any]] = None
    provenance_links: Optional[Dict[str, Any]] = None


class JobListResponse(BaseModel):
    total_jobs: int
    jobs: List[JobResponse]

