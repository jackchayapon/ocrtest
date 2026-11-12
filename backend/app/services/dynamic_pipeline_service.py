from uuid import uuid4

from sqlalchemy import or_, select

from app.core.errors import AppError
from app.db.models import OCRModel, PipelineConfig
from app.repositories.benchmark_repository import BenchmarkRepository


def model_json(model):
    if model is None:
        return None
    return {key: getattr(model, key) for key in (
        "id", "name", "kind", "source", "version", "weight", "single_path", "batch_path"
    )}


class DynamicPipelineService:
    def __init__(self, session, settings=None):
        self.session = session
        self.settings = settings

    def models(self):
        return list(self.session.scalars(select(OCRModel).order_by(OCRModel.source, OCRModel.kind, OCRModel.name)))

    def model(self, model_id):
        model = self.session.get(OCRModel, str(model_id))
        if model is None:
            raise AppError("OCR model not found", 404)
        return model

    def save_model(self, data, model_id=None):
        model = self.model(model_id) if model_id else OCRModel()
        users = list(self.session.scalars(select(PipelineConfig).where(or_(
            PipelineConfig.det_model_id == model.id, PipelineConfig.rec_model_id == model.id
        )))) if model_id else []
        if users and (model.kind != data.kind or model.source != data.source):
            raise AppError("Cannot change source or DET/REC type while a pipeline uses this model", 409)
        for key, value in data.model_dump().items():
            setattr(model, key, value)
        for pipeline in users:
            pipeline.last_connection_status = None
        self.session.add(model)
        self.session.commit()
        return model

    def save_pipeline(self, data, pipeline_id=None, provider=None):
        pipeline = BenchmarkRepository(self.session).config(pipeline_id) if pipeline_id else PipelineConfig(
            pipeline_id="dynamic_" + uuid4().hex, request_format="multipart", file_field_name="images",
        )
        if pipeline_id and pipeline.execution_mode is None:
            raise AppError("Use the original settings for built-in pipelines", 422)
        rec = self.model(data.rec_model_id) if data.rec_model_id else None
        det = self.model(data.det_model_id) if data.det_model_id else None
        for model, kind in ((rec, "rec"), (det, "det")):
            if model and (model.kind != kind or model.source != data.source):
                raise AppError("Model type and Custom/Official source must match the pipeline", 422)
        pipeline.name, pipeline.source, pipeline.execution_mode = data.name, data.source, data.execution_mode
        pipeline.enabled = data.enabled
        pipeline.det_model, pipeline.rec_model = det, rec
        pipeline.integrated_options = dict(version=data.version, det_weight=data.det_weight, rec_weight=data.rec_weight) if data.execution_mode == "integrated" else None
        if data.execution_mode == "external_api":
            from app.integrations.external_ocr import get_provider
            provider = provider or get_provider(self.settings, data.provider_id)
            pipeline.integrated_options = provider.identity(data.provider_id)
            pipeline.endpoint = ""
            pipeline.base_url = ""
            pipeline.request_format = provider.request_format
            pipeline.file_field_name = provider.image_field
        if data.source == "official" and data.execution_mode == "integrated":
            pipeline.integrated_options = dict(paddle_model_defaults=data.paddle_model_defaults,
                det_version=data.det_version, rec_version=data.rec_version,
                det_weight=data.det_weight, rec_weight=data.rec_weight)
        pipeline.engine = "external_api" if data.execution_mode == "external_api" else "dynamic"
        pipeline.last_connection_status = None
        self.session.add(pipeline)
        self.session.commit()
        return pipeline
