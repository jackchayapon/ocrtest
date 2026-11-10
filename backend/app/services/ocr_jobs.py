"""PostgreSQL queue, fenced checkpoints and restart-safe single-job consumer.

The event/task is only a wakeup mechanism. PostgreSQL owns execution state.
No idle polling: Railway may sleep when there is no work. Active lease heartbeats
are database traffic, independent of browser traffic.
"""

import asyncio
import contextlib
import logging
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import noload

from app.core.errors import AppError
from app.db.models import OCRJob, OCRModel, PipelineConfig, PipelineRun, TestCase, now

ACTIVE = ("queued", "running")
LEASE_SECONDS = 90
logger = logging.getLogger(__name__)


def snapshot(config):
    values = {
        key: getattr(config, key)
        for key in (
            "pipeline_id",
            "name",
            "base_url",
            "endpoint",
            "http_method",
            "request_format",
            "file_field_name",
            "query_params",
            "enabled",
            "engine",
            "include_roi",
            "execution_mode",
            "source",
            "integrated_options",
        )
    }
    for key in ("det_model", "rec_model"):
        model = getattr(config, key)
        values[key] = (
            {
                k: getattr(model, k)
                for k in (
                    "name",
                    "kind",
                    "source",
                    "version",
                    "weight",
                    "single_path",
                    "batch_path",
                )
            }
            if model
            else None
        )
    return values


def restore_config(values):
    values = dict(values)
    for key in ("det_model", "rec_model"):
        values[key] = OCRModel(**values[key]) if values[key] else None
    return PipelineConfig(**values)


def job_json(job):
    total = job.total_fields * job.total_pipelines
    return {
        key: getattr(job, key)
        for key in (
            "test_case_id",
            "status",
            "pipeline_ids",
            "total_fields",
            "total_pipelines",
            "completed_units",
            "failed_units",
            "completed_pipelines",
            "current_pipeline_id",
            "current_field_index",
            "attempt_count",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
            "heartbeat_at",
            "error_code",
            "safe_error_message",
        )
    } | {
        "job_id": job.id,
        "progress_percent": round(100 * job.completed_units / total, 1) if total else 0,
        "run_ids": list(job.run_ids.values()),
    }


def active_job(session, case_id):
    return session.scalar(
        select(OCRJob).where(OCRJob.test_case_id == case_id, OCRJob.status.in_(ACTIVE))
    )


def has_active_jobs(session, case_ids):
    return (
        session.scalar(
            select(OCRJob.id)
            .where(
                OCRJob.test_case_id.in_(case_ids),
                OCRJob.status.in_(ACTIVE),
            )
            .limit(1)
        )
        is not None
    )


def ensure_not_running(session, case_id):
    # Lock the same case row as enqueue, serializing mutation against submission.
    session.execute(select(TestCase.id).where(TestCase.id == case_id).with_for_update())
    if has_active_jobs(session, [case_id]):
        raise AppError("An OCR job is active for this test case; wait for completion", 409)


def enqueue(cases, case_id, pipeline_ids, key):
    session = cases.repository.session
    case = session.scalar(
        select(TestCase)
        .where(TestCase.id == case_id)
        .options(noload(TestCase.runs), noload(TestCase.categories))
        .with_for_update()
    )
    if case is None:
        raise AppError("Test case not found", 404)
    existing = session.scalar(
        select(OCRJob).where(OCRJob.test_case_id == case_id, OCRJob.idempotency_key == key)
    )
    if existing:
        if existing.pipeline_ids != pipeline_ids:
            raise AppError("Idempotency key was already used with different pipelines", 409)
        return existing
    existing = active_job(session, case_id)
    if existing:
        if existing.pipeline_ids != pipeline_ids:
            raise AppError("Another OCR job is active for this test case", 409)
        return existing
    cases.validate_workload(case, pipeline_ids)
    configured = {
        c.pipeline_id: c
        for c in session.scalars(
            select(PipelineConfig).where(
                PipelineConfig.pipeline_id.in_(pipeline_ids),
                PipelineConfig.execution_mode.is_not(None),
            )
        )
    }
    if any(p not in configured for p in pipeline_ids):
        raise AppError("Pipeline not found", 404)
    configs = [configured[p] for p in pipeline_ids]
    if any(not c.enabled for c in configs):
        raise AppError("Selected pipeline is disabled", 409)
    if case.workflow == "global" and (not case.layout_confirmed_at or not case.global_fields):
        raise AppError("Confirm a non-empty Global Layout before running OCR", 409)
    # Validate availability only; image decoding/inference belongs to the worker.
    if not cases.storage.exists(case.document.storage_key):
        raise AppError("Stored image is unavailable", 404)
    cases.validate_processing_source(case.document, case.page_number)
    # Serialize global queue admission across PostgreSQL sessions/replicas. Existing
    # idempotency matches above remain readable even while the queue is full.
    if session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(1967472013)"))
    if session.scalar(select(func.count()).select_from(OCRJob).where(OCRJob.status.in_(ACTIVE))) >= 5:
        raise AppError("คิว OCR เต็ม กรุณาลองใหม่ภายหลัง / OCR queue full; retry later", 429)
    if case.workflow == "global":
        case.layout_locked_at = now()
    job = OCRJob(
        test_case_id=case_id,
        pipeline_ids=pipeline_ids,
        idempotency_key=key,
        config_snapshot=[snapshot(c) for c in configs],
        total_fields=len(case.global_fields) if case.workflow == "global" else 1,
        total_pipelines=len(configs),
    )
    session.add(job)
    session.commit()
    return job


class LostLease(Exception):
    pass


class Checkpoint:
    def __init__(self, session, job, owner):
        self.session, self.job, self.owner = session, job, owner
        self.configs = [restore_config(c) for c in job.config_snapshot]
        self.prefill = {k: SimpleNamespace(**v) for k, v in job.prefill_results.items()}

    def fence(self):
        # A replacement owner must commit its claim before this can succeed again.
        matched = self.session.execute(
            update(OCRJob)
            .where(
                OCRJob.id == self.job.id,
                OCRJob.status == "running",
                OCRJob.lease_owner == self.owner,
                OCRJob.lease_expires_at > now(),
            )
            .values(updated_at=now())
            .execution_options(synchronize_session=False)
        ).rowcount
        if not matched:
            self.session.rollback()
            raise LostLease()

    def save(self, parents, prefill=None):
        self.fence()
        self.job.run_ids = {p.pipeline_id: p.id for p in parents}
        if prefill is not None:
            self.job.prefill_results = {
                k: {"status": v.status, "final_text": v.final_text, "boxes": v.boxes}
                for k, v in prefill.items()
            }
        if parents and parents[0].crop_stage == "global_fields":
            fields = [f for p in parents for f in p.fields]
            self.job.completed_units = len(fields)
            self.job.failed_units = sum(f.status != "success" for f in fields)
            self.job.completed_pipelines = sum(
                len(p.fields) == self.job.total_fields for p in parents
            )
        else:
            self.job.completed_units = len(parents)
            self.job.failed_units = sum(p.status != "success" for p in parents)
            self.job.completed_pipelines = len(parents)
        self.job.updated_at = now()
        self.session.commit()


class JobWorker:
    def __init__(self, database, settings, storage, lock, resource_lock=None):
        self.database, self.settings, self.storage, self.lock = database, settings, storage, lock
        self.owner = str(uuid4())
        self.resource_lock = resource_lock or asyncio.Lock()
        self.wake = asyncio.Event()
        self.wake.set()  # Drain persisted jobs on startup, including expired leases.

    def claim(self):
        with self.database.session_factory() as session, session.begin():
            if session.bind.dialect.name == "postgresql":
                if not session.scalar(text("SELECT pg_try_advisory_xact_lock(1967472012)")):
                    return None, 10
            stamp = now()
            live = session.scalar(
                select(OCRJob)
                .where(OCRJob.status == "running", OCRJob.lease_expires_at > stamp)
                .order_by(OCRJob.lease_expires_at)
                .limit(1)
            )
            if live:
                return None, 10
            job = session.scalar(
                select(OCRJob)
                .where(
                    or_(
                        OCRJob.status == "queued",
                        and_(
                            OCRJob.status == "running",
                            OCRJob.lease_expires_at <= stamp,
                        ),
                    )
                )
                .order_by(OCRJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None, None
            job.status, job.lease_owner = "running", self.owner
            job.lease_expires_at = stamp + timedelta(seconds=LEASE_SECONDS)
            job.heartbeat_at = job.updated_at = stamp
            job.started_at = job.started_at or stamp
            job.attempt_count += 1
            return job.id, None

    def heartbeat(self, job_id):
        with self.database.session_factory() as session, session.begin():
            stamp = now()
            count = session.execute(
                update(OCRJob)
                .where(
                    OCRJob.id == job_id,
                    OCRJob.lease_owner == self.owner,
                    OCRJob.status == "running",
                    OCRJob.lease_expires_at > stamp,
                )
                .values(
                    heartbeat_at=stamp, lease_expires_at=stamp + timedelta(seconds=LEASE_SECONDS)
                )
            ).rowcount
            if not count:
                raise LostLease()

    async def keep_lease(self, job_id):
        while True:
            await asyncio.sleep(10)
            await asyncio.to_thread(self.heartbeat, job_id)

    async def execute(self, job_id):
        from app.services.test_case_service import TestCaseService

        with self.database.session_factory() as session:
            job = session.get(OCRJob, job_id)
            checkpoint = Checkpoint(session, job, self.owner)
            cases = TestCaseService(session, self.settings, self.storage)
            try:
                await cases.run(job.test_case_id, job.pipeline_ids, checkpoint=checkpoint)
                checkpoint.fence()
                total = job.total_fields * job.total_pipelines
                if job.completed_units != total:
                    raise RuntimeError("Incomplete checkpoint count")
                job.status = (
                    "completed"
                    if not job.failed_units
                    else "failed"
                    if job.failed_units == total
                    else "partial_success"
                )
                job.finished_at = job.updated_at = now()
                job.lease_owner = job.lease_expires_at = None
                session.commit()
            except (asyncio.CancelledError, LostLease):
                session.rollback()
                raise
            except SQLAlchemyError:
                # A disconnect may make COMMIT's outcome ambiguous. Reclaim from DB
                # after lease expiry; never blindly append a second set of results.
                session.rollback()
                raise LostLease() from None
            except Exception as exc:
                session.rollback()
                checkpoint.fence()
                session.refresh(job)
                for run_id in job.run_ids.values():
                    parent = session.get(PipelineRun, run_id)
                    if parent is not None and parent.status == "running":
                        parent.status = "error"
                        parent.error_code = "OCR_JOB_INCOMPLETE"
                        parent.error_message = "Job stopped before every field completed; saved predictions remain available"
                job.status = "failed"
                job.error_code = "OCR_JOB_FAILED"
                # Never persist exception text: may contain document data or credentials.
                job.safe_error_message = (
                    "OCR job could not complete; saved partial results remain available"
                )
                job.finished_at = job.updated_at = now()
                job.lease_owner = job.lease_expires_at = None
                session.commit()
                logger.warning("ocr_job_failed job_id=%s category=%s", job_id, type(exc).__name__)

    async def run(self):
        while True:
            await self.wake.wait()
            self.wake.clear()
            try:
                job_id, retry_after = await asyncio.to_thread(self.claim)
                if job_id:
                    execution = asyncio.create_task(self.execute_guarded(job_id))
                    heartbeat = asyncio.create_task(self.keep_lease(job_id))
                    try:
                        done, _ = await asyncio.wait(
                            (execution, heartbeat), return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in done:
                            await task
                    finally:
                        for task in (execution, heartbeat):
                            task.cancel()
                        for task in (execution, heartbeat):
                            with contextlib.suppress(asyncio.CancelledError, Exception):
                                await task
                    self.wake.set()
                elif retry_after:
                    await asyncio.sleep(retry_after)
                    self.wake.set()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("ocr_worker_retry category=%s", type(exc).__name__)
                await asyncio.sleep(10)
                self.wake.set()

    async def execute_guarded(self, job_id):
        # Match API allocation -> OCR lock order; claiming an empty queue uses no image slot.
        async with self.resource_lock, self.lock:
            await self.execute(job_id)
