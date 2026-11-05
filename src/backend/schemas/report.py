"""
Report & Aggregated Statistics API Schemas
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class ReportSummary(BaseModel):
    report_id: str
    phase: str
    title: str
    category: str
    filename: str
    format: str
    status: str
    deliverables_count: int


class ReportDetailResponse(BaseModel):
    report_id: str
    title: str
    phase: str
    metadata: Dict[str, Any]
    summary_findings: Dict[str, Any]
    associated_artifacts: List[str]


class RegionStatisticsResponse(BaseModel):
    region_id: str
    summary_timestamp: str
    flood_statistics: Dict[str, Any]
    riverbank_statistics: Dict[str, Any]
    model_statistics: Dict[str, Any]
    optical_validation_agreement_pct: float
    authoritative_baseline_agreement_pct: float

