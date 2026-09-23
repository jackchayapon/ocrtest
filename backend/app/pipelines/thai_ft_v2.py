"""Thai FT v2: fixed DET/REC V6 routing, independent of stale per-result labels."""

from app.pipelines.benchmark import BenchmarkPipelineAdapter


class ThaiFTV2PipelineAdapter(BenchmarkPipelineAdapter):
    engine = "det_v6_rec_v6_thai_ft_v2"  # Internal only; never sent to the Gateway.
    recognition_version = 6
    model_variant = "thai_ft_v2"
    detector = "Thai FT v2 DET V6"
    recognizer = "Thai FT v2 REC V6"
