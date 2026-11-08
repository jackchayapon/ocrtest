"""Configurable stages using the existing Gateway leaf-inference batch contract."""
from urllib.parse import parse_qsl, urlsplit

from app.integrations.model_gateway import GatewayError
from app.pipelines.benchmark import BenchmarkPipelineAdapter
from app.pipelines.hutch_crop import HutchCropPipelineAdapter
from app.pipelines.hutch_fine_tune_v2 import HutchFineTuneV2PipelineAdapter
from app.pipelines.mint import MintPipelineAdapter
from app.services.dynamic_pipeline_service import model_json


def model_request(gateway, model, pngs, request_id):
    if model is None:
        raise GatewayError("Select a model before running this pipeline", "NOT_CONFIGURED")
    parts = urlsplit(model.batch_path)
    request = gateway.build_batch_request(
        pngs=pngs, endpoint=parts.path, version=model.version, request_id=request_id,
    )
    # The registered path is authoritative, including exact version spelling and weight/model keys.
    request["params"] = dict(parse_qsl(parts.query))
    return request


class DynamicDetectionRecognitionAdapter(BenchmarkPipelineAdapter):
    def __init__(self, config, settings):
        super().__init__(config, settings)
        self.detector = config.det_model.name if config.det_model else ""
        self.recognizer = config.rec_model.name if config.rec_model else ""
        self.detection_version = config.det_model.version if config.det_model else ""
        self.recognition_version = config.rec_model.version if config.rec_model else ""

    def batch_request(self, *, pngs, endpoint, version, request_id):
        model = self.config.det_model if endpoint == self.detection_endpoint else self.config.rec_model
        return model_request(self.gateway, model, pngs, request_id)

    async def run(self, **kwargs):
        result = await super().run(**kwargs)
        result.raw_response["composition"] = {
            "ordering": "detection_order",
            "detection": model_json(self.config.det_model),
            "recognition": model_json(self.config.rec_model),
        }
        return result


class DynamicRecognitionAdapter(HutchFineTuneV2PipelineAdapter):
    def __init__(self, config, settings):
        super().__init__(config, settings)
        self.recognizer = config.rec_model.name if config.rec_model else ""

    def build_request(self, crop, request_id):
        return model_request(self.gateway, self.config.rec_model, [crop.png], request_id)

    async def run(self, **kwargs):
        result = await super().run(**kwargs)
        result.raw_response["composition"] = {"recognition": model_json(self.config.rec_model)}
        return result


class DynamicCustomAdapter(MintPipelineAdapter):
    def __init__(self, config, settings):
        super().__init__(config, settings)
        options = config.integrated_options or {}
        self.detector = f"DET V{options.get('version', '6')} {options.get('det_weight', 'baseline')}"
        self.recognizer = f"REC V{options.get('version', '6')} {options.get('rec_weight', 'baseline')}"

    def build_request(self, crop, request_id):
        options = self.config.integrated_options or {}
        return self.gateway.build_request(png=crop.png, endpoint="/api/v1/ocr-results",
            query_params={"engine": "custom", "version": options.get("version", "6"),
                          "det_model": options.get("det_weight", "baseline"),
                          "rec_model": options.get("rec_weight", "baseline")},
            fields={}, request_id=request_id, request_format="multipart")

    async def run(self, **kwargs):
        result = await super().run(**kwargs)
        result.raw_response["composition"] = {"engine": "custom", **(self.config.integrated_options or {})}
        return result


class DynamicOfficialAdapter(HutchCropPipelineAdapter):
    def __init__(self, config, settings):
        super().__init__(config, settings)
        options = dict(config.integrated_options or {})
        if config.execution_mode in ("det_rec", "rec"):
            options = {"paddle_model_defaults": False}
            for kind in ("det", "rec"):
                model = getattr(config, f"{kind}_model")
                if model is not None:
                    options[f"{kind}_version"] = model.version.removeprefix("v")
                    options[f"{kind}_weight"] = "baseline" if model.weight == "default" else model.weight
        self.options = options
        if not options.get("paddle_model_defaults", True):
            self.detector = f"Paddle DET V{options['det_version']} / {options['det_weight']}" if "det_version" in options else "Paddle DET (Gateway environment)"
            self.recognizer = f"Paddle REC V{options['rec_version']} / {options['rec_weight']}" if "rec_version" in options else "Paddle REC (Gateway environment)"
        else:
            self.detector = "Paddle DET (Gateway environment)"
            self.recognizer = "Paddle REC (Gateway environment)"

    def query_params(self):
        options = self.options
        params = {"engine": "paddle"}
        if not options.get("paddle_model_defaults", True):
            for kind in ("det", "rec"):
                if options.get(f"{kind}_version"):
                    params[f"{kind}_version"] = options[f"{kind}_version"]
                    params[f"{kind}_model"] = options[f"{kind}_weight"]
        return params

    def build_request(self, crop, request_id):
        return self.gateway.build_request(png=crop.png, endpoint="/api/v1/ocr-results",
            query_params=self.query_params(), fields=self.model_parameters(),
            request_id=request_id, request_format="multipart")

    async def run(self, **kwargs):
        result = await super().run(**kwargs)
        result.raw_response["composition"] = self.query_params()
        return result
