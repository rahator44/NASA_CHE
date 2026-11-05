"""
Job Management API Endpoints
NASA Space Apps Challenge 2026: Dancing with the SARs
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from src.backend.schemas.job import JobCreateRequest, JobResponse, JobListResponse
from src.backend.services.job_service import JobService, ALLOWLISTED_JOB_TYPES

router = APIRouter()


@router.post("/jobs", response_model=JobResponse, status_code=201, tags=["Jobs"])
def create_job(req: JobCreateRequest):
    """
    Submits an allowlisted background processing or audit task.
    Arbitrary shell command execution is strictly blocked; only registered workflows are permitted.
    """
    if req.job_type not in ALLOWLISTED_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Action '{req.job_type}' is not permitted. Allowlisted actions: {list(ALLOWLISTED_JOB_TYPES.keys())}"
        )

    try:
        job = JobService.create_and_execute_job(
            job_type=req.job_type,
            region_id=req.region_id,
            parameters=req.parameters or {},
        )
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job execution failed: {e}")


@router.get("/jobs", response_model=JobListResponse, tags=["Jobs"])
def list_jobs(limit: int = Query(50, ge=1, le=100)):
    """Lists recent jobs tracked in the SQLite database."""
    jobs = JobService.list_jobs(limit=limit)
    return JobListResponse(total_jobs=len(jobs), jobs=jobs)


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
def get_job(job_id: str):
    """Retrieves status, progress percentage, execution timestamps, and output references for a job."""
    job = JobService.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job

