"""Pipeline-first durable execution: one prediction and one short transaction.

The existing (run_id, field_index) unique constraint is the replay key. A fenced
transaction inserts the result and advances counters atomically. A fresh Session
per unit releases ORM results/transport evidence before the next Gateway call.
"""
import io
import json
import time
from contextlib import closing
from datetime import timezone
from types import SimpleNamespace

from sqlalchemy import Integer, cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.orm import defer, noload, sessionmaker

from app.db.models import OCRField, OCRJob, PipelineRun, TestCase, now
from app.services.global_layout_service import reading_lines
from app.services.global_order import ordered_detection_boxes
from app.services.gt_prefill_service import DETECTION, RECOGNITION, prefill_pipeline, pristine_gt
from app.services.metrics_service import normalize_text
from app.services.pipeline_manager import PipelineManager

TRACE_KEYS = (
    "input_sha256", "input_width", "input_height", "input_byte_size", "input_format",
    "crop_sha256", "crop_width", "crop_height", "crop_stage", "request_id",
    "gateway_request_id", "gateway_duration_ms", "gateway_service", "gateway_model",
    "detector_model", "recognizer_model", "processing_time_ms", "error_code",
    "error_message", "original_width", "original_height",
)


class IncrementalGlobalJob:
    def __init__(self, cases, checkpoint):
        self.cases, self.checkpoint = cases, checkpoint
        self.job_id, self.owner = checkpoint.job.id, checkpoint.owner
        self.case_id = checkpoint.job.test_case_id
        self.configs = checkpoint.configs
        self.sessions = sessionmaker(cases.repository.session.bind, expire_on_commit=False)

    def fence(self, session):
        from app.services.ocr_jobs import LostLease
        matched = session.execute(update(OCRJob).where(
            OCRJob.id == self.job_id, OCRJob.status == "running",
            OCRJob.lease_owner == self.owner, OCRJob.lease_expires_at > now(),
        ).values(updated_at=now()).execution_options(synchronize_session=False)).rowcount
        if not matched:
            session.rollback()
            raise LostLease()

    def prefill_entry(self, session, field_id):
        return session.scalar(select(OCRJob.prefill_results[field_id]).where(OCRJob.id == self.job_id))

    def save_prefill(self, session, field_id, result):
        # Keep canonical text, not raw responses/polygons. Patch just this JSON
        # entry server-side: no O(n²) download/re-encoding of all earlier drafts.
        payload = {"status": result.status, "final_text": "\n".join(reading_lines(result)), "boxes": []}
        if session.bind.dialect.name == "postgresql":
            value = func.jsonb_set(OCRJob.prefill_results, array([field_id]), cast(payload, JSONB), True)
        else:
            value = func.json_set(OCRJob.prefill_results, '$."' + field_id + '"', func.json(json.dumps(payload)))
        session.execute(update(OCRJob).where(OCRJob.id == self.job_id).values(prefill_results=value)
                        .execution_options(synchronize_session=False))

    def initialize(self):
        with self.sessions() as session:
            self.fence(session)
            case = session.scalar(select(TestCase).where(TestCase.id == self.case_id)
                                  .options(noload(TestCase.runs), noload(TestCase.categories)))
            fields = [SimpleNamespace(id=f.id, field_index=f.field_index, roi=f.roi, source=f.source)
                      for f in sorted(case.global_fields, key=lambda f: f.field_index)]
            prefill = prefill_pipeline(self.configs) if (
                (case.gt_prefill is None and pristine_gt(case)) or
                (case.gt_prefill and case.gt_prefill.get("status") == "pending")) else None
            if prefill:
                case.gt_prefill = {"status": "pending", "det_endpoint": DETECTION, "rec_endpoint": RECOGNITION}
            # Fail missing/unsupported source before creating empty result runs.
            source, _, _ = self.cases.page_image(case.document, case.page_number)
            job = session.get(OCRJob, self.job_id, options=[defer(OCRJob.prefill_results), defer(OCRJob.config_snapshot)])
            run_ids = dict(job.run_ids)
            for config in self.configs:
                if config.pipeline_id not in run_ids:
                    run = PipelineRun(test_case_id=self.case_id, pipeline_id=config.pipeline_id,
                                      pipeline_name=config.name, status="running", crop_stage="global_fields",
                                      boxes=[], raw_response=None)
                    session.add(run)
                    session.flush()
                    run_ids[config.pipeline_id] = run.id
            job.run_ids = run_ids
            # Reconcile persisted rows, including a commit whose acknowledgement
            # was lost. No in-memory counter is treated as authoritative.
            counts = list(session.execute(select(OCRField.pipeline_run_id, func.count(),
                          func.sum(cast(OCRField.status != "success", Integer)))
                          .where(OCRField.pipeline_run_id.in_(list(run_ids.values())))
                          .group_by(OCRField.pipeline_run_id)))
            job.completed_units = sum(row[1] for row in counts)
            job.failed_units = sum(row[2] or 0 for row in counts)
            job.completed_pipelines = sum(row[1] == len(fields) for row in counts)
            session.commit()
            return fields, prefill, run_ids, source

    def existing(self, run_id, field):
        with self.sessions() as session:
            row = session.execute(select(OCRField.status, OCRField.ocr_text).where(
                OCRField.pipeline_run_id == run_id, OCRField.field_index == field.field_index,
                OCRField.global_field_id == field.id)).first()
            return SimpleNamespace(status=row[0], final_text=row[1], boxes=[]) if row else None

    def mark_current(self, pipeline_id, field_index, run_id):
        with self.sessions() as session:
            self.fence(session)
            session.execute(update(OCRJob).where(OCRJob.id == self.job_id).values(
                current_pipeline_id=pipeline_id, current_field_index=field_index))
            if run_id:
                prior = session.scalar(select(PipelineRun.raw_response).where(PipelineRun.id == run_id)) or {}
                if not prior.get("timing", {}).get("started_at"):
                    session.execute(update(PipelineRun).where(PipelineRun.id == run_id).values(
                        raw_response={**prior, "timing": {"started_at": now().isoformat()}}))
            session.commit()

    def persist(self, run_id, field, result, *, prefill=False):
        with self.sessions() as session:
            self.fence(session)
            if run_id is not None:
                existing = session.scalar(select(OCRField.id).where(
                    OCRField.pipeline_run_id == run_id, OCRField.field_index == field.field_index))
                if existing is None:
                    diagnostics = {key: getattr(result, key) for key in TRACE_KEYS}
                    failure = (result.raw_response or {}).get("failure", {})
                    if result.status != "success":
                        diagnostics.update(failure_stage=failure.get("stage", "adapter"),
                                           http_status=failure.get("http_status"))
                    diagnostics.update(boxes=ordered_detection_boxes(result.boxes),
                                       ordering="row_then_left_within_global_field",
                                       raw_text=result.raw_text if result.raw_text is not None else result.final_text or "")
                    session.add(OCRField(pipeline_run_id=run_id, global_field_id=field.id,
                                field_index=field.field_index, geometry={"roi": field.roi},
                                ocr_text="\n".join(reading_lines(result)), confidence=result.confidence,
                                status=result.status, diagnostics=diagnostics))
                    session.flush()
                    session.execute(update(OCRJob).where(OCRJob.id == self.job_id).values(
                        completed_units=OCRJob.completed_units + 1,
                        failed_units=OCRJob.failed_units + int(result.status != "success")))
                    # Persist lightweight provenance once, never an expanding ORM
                    # relationship. Timing is finalized from scalar projections.
                    values = {}
                    if field.field_index == 1:
                        prior = session.scalar(select(PipelineRun.raw_response).where(PipelineRun.id == run_id)) or {}
                        values["raw_response"] = {**(result.raw_response or {}), "timing": prior.get("timing", {})}
                    if result.status != "success":
                        values.update(error_code="FIELD_PIPELINE_ERROR",
                                      error_message="One or more fields failed; successful field predictions remain available")
                    if values:
                        session.execute(update(PipelineRun).where(PipelineRun.id == run_id).values(**values))
            if prefill:
                self.save_prefill(session, field.id, result)
            session.commit()

    def finish_pipeline(self, run_id, elapsed):
        with self.sessions() as session, io.StringIO() as final, io.StringIO() as raw:
            self.fence(session)
            count = failed = confidences = 0
            confidence = compute = duration = 0.0
            has_duration = False
            rows = session.execute(select(OCRField.ocr_text, OCRField.diagnostics["raw_text"].as_string(),
                OCRField.confidence, OCRField.status, OCRField.diagnostics["processing_time_ms"].as_integer(),
                OCRField.diagnostics["gateway_duration_ms"].as_float()).where(
                OCRField.pipeline_run_id == run_id).order_by(OCRField.field_index)
                .execution_options(yield_per=1))
            for text, original, score, status, millis, gateway in rows:
                if count:
                    final.write("\n")
                    raw.write("\n")
                final.write(text or "")
                raw.write(original if original is not None else text or "")
                count += 1
                failed += status != "success"
                if score is not None:
                    confidence += score
                    confidences += 1
                compute += millis or 0
                if gateway is not None:
                    duration += gateway
                    has_duration = True
            prior = session.scalar(select(PipelineRun.raw_response).where(PipelineRun.id == run_id)) or {}
            if prior.get("timing", {}).get("started_at"):
                from datetime import datetime
                elapsed = round((now()-datetime.fromisoformat(prior["timing"]["started_at"])).total_seconds()*1000)
            started = session.scalar(select(OCRJob.started_at).where(OCRJob.id == self.job_id))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            text, original = final.getvalue(), raw.getvalue()
            session.execute(update(PipelineRun).where(PipelineRun.id == run_id).values(
                status="error" if failed else "success", final_text=text,
                raw_text=original if original != text else None, normalized_text=normalize_text(text),
                confidence=confidence / confidences if confidences else None,
                processing_time_ms=elapsed, gateway_duration_ms=duration if has_duration else None,
                raw_response={**prior, "timing": {**prior.get("timing", {}), "semantics": "wall_clock_v1", "wall_time_ms": elapsed,
                              "run_wall_time_ms": round((now()-started).total_seconds()*1000),
                              "total_field_compute_ms": compute}}))
            job_fields = session.scalar(select(OCRJob.total_fields).where(OCRJob.id == self.job_id))
            completed = session.execute(select(OCRField.pipeline_run_id, func.count()).where(
                OCRField.pipeline_run_id.in_(list(self.run_ids.values())))
                .group_by(OCRField.pipeline_run_id)).all()
            session.execute(update(OCRJob).where(OCRJob.id == self.job_id).values(
                completed_pipelines=sum(n == job_fields for _, n in completed)))
            session.commit()

    def finish_prefill(self):
        with self.sessions() as session:
            self.fence(session)
            case = session.scalar(select(TestCase).where(TestCase.id == self.case_id).with_for_update()
                                  .options(noload(TestCase.runs), noload(TestCase.categories)))
            if pristine_gt(case):
                filled = []
                for field in case.global_fields:
                    result = self.prefill_entry(session, field.id)
                    if result and result["status"] == "success":
                        # Old checkpoints may contain original box ordering.
                        text = "\n".join(reading_lines(SimpleNamespace(**result)))
                        if text.strip():
                            field.ground_truth_raw = text
                            field.ground_truth_normalized = normalize_text(text)
                            filled.append(field.id)
                if filled:
                    case.ground_truth_raw = "\n".join(f.ground_truth_raw or "" for f in case.global_fields)
                    case.ground_truth_normalized = normalize_text(case.ground_truth_raw)
                case.gt_prefill = {**case.gt_prefill, "status": "ready" if len(filled) == len(case.global_fields)
                                   else "partial" if filled else "unavailable", "field_ids": filled}
            else:
                case.gt_prefill = {**case.gt_prefill, "status": "skipped"}
            session.commit()

    async def run(self):
        fields, prefill, self.run_ids, source = self.initialize()
        manager = PipelineManager(self.cases.settings)
        with closing(self.cases.images.open(source)) as image:
            # A large lossless source PNG duplicates the decoded page throughout
            # a long Job, even though most Fields only need small crops. Keep
            # cheap compact encodings; recreate large whole-page PNGs only when
            # that Field is needed, using the same lossless encoder/pixel grid.
            if len(source) > 512 * 1024:
                source = None
            configs = list(self.configs)
            if prefill and not any(c.pipeline_id == prefill.pipeline_id for c in configs):
                configs.append(prefill)
            for config in configs:
                started = time.perf_counter()
                run_id = self.run_ids.get(config.pipeline_id)
                for field in fields:
                    is_prefill = prefill is not None and config.pipeline_id == prefill.pipeline_id
                    if run_id:
                        existing = self.existing(run_id, field)
                        if existing:
                            if is_prefill:
                                with self.sessions() as session:
                                    if self.prefill_entry(session, field.id) is None:
                                        self.fence(session)
                                        self.save_prefill(session, field.id, existing)
                                        session.commit()
                            continue
                    elif is_prefill:
                        with self.sessions() as session:
                            if self.prefill_entry(session, field.id) is not None:
                                continue
                    self.mark_current(config.pipeline_id, field.field_index, run_id)
                    crop = self.cases.images.canonical_crop(image, field.roi, share_source=True, encoded_source=source)
                    result = (await manager.run([config], image, crop, field.roi, field.source))[0]
                    self.persist(run_id, field, result, prefill=is_prefill)
                    del result, crop
                if run_id:
                    self.finish_pipeline(run_id, round((time.perf_counter()-started)*1000))
        if prefill:
            self.finish_prefill()
        with self.sessions() as session:
            self.fence(session)
            session.execute(update(TestCase).where(TestCase.id == self.case_id).values(status="tested", updated_at=now()))
            session.commit()
