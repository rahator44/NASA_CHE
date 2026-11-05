"""
Scientific Reports & Aggregated Statistics API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import List
from fastapi import APIRouter, HTTPException
from src.backend.schemas.report import ReportSummary, ReportDetailResponse, RegionStatisticsResponse
from src.backend.services.report_service import ReportService

router = APIRouter()


@router.get("/reports", response_model=List[ReportSummary], tags=["Reports"])
def list_reports():
    """Lists registered project reports and scientific validation summaries."""
    return ReportService.list_reports()


@router.get("/reports/{report_id}", response_model=ReportDetailResponse, tags=["Reports"])
def get_report(report_id: str):
    """Retrieves full scientific findings, methodology, and artifact links for a report."""
    rep = ReportService.get_report_detail(report_id)
    if not rep:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found.")
    return rep


@router.get("/regions/{region_id}/statistics", response_model=RegionStatisticsResponse, tags=["Reports"])
def get_region_statistics(region_id: str):
    """Retrieves high-level aggregated statistics combining flood areas, riverbank displacement, and ML metrics."""
    try:
        return ReportService.get_region_statistics(region_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Statistics unavailable for region '{region_id}': {e}")

