from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import defer

from app.api.dependencies import CaseServiceDep, SessionDep
from app.core.errors import AppError
from app.db.models import OCRJob
from app.schemas.contracts import RunRequest
from app.services.json_response import bounded_json_response
from app.services.ocr_jobs import enqueue, job_json
from app.services.serializers import run_json

router = APIRouter()


class JobRequest(RunRequest):
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


@router.post("/test-cases/{case_id}/jobs", status_code=202)
async def create_job(case_id: UUID, data: JobRequest, service: CaseServiceDep, request: Request):
    if not request.app.state.settings.ocr_jobs_enabled:
        raise AppError("Background OCR worker is not enabled", 503)
    job = enqueue(service, str(case_id), data.pipelines, data.idempotency_key)
    request.app.state.job_worker.wake.set()
    return job_json(job)


@router.get("/test-cases/{case_id}/jobs")
def case_job(case_id: UUID, session: SessionDep):
    job = session.scalar(
        select(OCRJob)
        .where(OCRJob.test_case_id == str(case_id))
        .options(defer(OCRJob.config_snapshot), defer(OCRJob.prefill_results))
        .order_by(OCRJob.created_at.desc())
        .limit(1)
    )
    return job_json(job) if job else None


@router.get("/ocr-jobs/{job_id}")
def get_job(job_id: UUID, session: SessionDep):
    job = session.get(
        OCRJob, str(job_id), options=[defer(OCRJob.config_snapshot), defer(OCRJob.prefill_results)]
    )
    if job is None:
        raise AppError("OCR job not found", 404)
    return job_json(job)


@router.get("/ocr-jobs/{job_id}/results")
def results(job_id: UUID, session: SessionDep):
    from app.db.models import PipelineRun

    job = session.get(OCRJob, str(job_id))
    if job is None:
        raise AppError("OCR job not found", 404)
    runs = [session.get(PipelineRun, job.run_ids[p]) for p in job.pipeline_ids if p in job.run_ids]
    return bounded_json_response({"test_case_id": job.test_case_id, "runs": [run_json(r, detail=True) for r in runs if r]})
