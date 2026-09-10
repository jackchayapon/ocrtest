from statistics import fmean

from app.repositories.benchmark_repository import BenchmarkRepository


def mean_present(values):
    present = [value for value in values if value is not None]
    return fmean(present) if present else None


class MatrixService:
    """Each case/pipeline contributes its latest run, including failures; reruns never add weight."""

    def __init__(self, session):
        self.repository = BenchmarkRepository(session)

    @staticmethod
    def eligible(run):
        return not run.archived and not (
            run.pipeline_id == "hutch_full" and run.crop_stage != "external_hutch"
        )

    def aggregate(self, cases, pipeline=None):
        rows = []
        for config in self.repository.configs():
            if pipeline and pipeline != config.pipeline_id:
                continue
            runs = []
            for case in cases:
                matching = [
                    run
                    for run in case.runs
                    if run.pipeline_id == config.pipeline_id
                    and self.eligible(run)
                ]
                if matching:
                    runs.append(max(matching, key=lambda run: (run.created_at, run.id)))
            successful = [run for run in runs if run.status == "success"]
            metrics = [
                metric
                for run in successful
                for metric in run.metric_records
                if metric.text_kind == "final"
            ]
            rows.append(
                {
                    "pipeline_id": config.pipeline_id,
                    "pipeline_name": config.name,
                    "tests": len(runs),
                    "successful_runs": len(successful),
                    "failed_runs": len(runs) - len(successful),
                    "evaluated_runs": len(metrics),
                    "cer": mean_present(metric.cer for metric in metrics),
                    "wer": mean_present(metric.wer for metric in metrics),
                    "exact_match_rate": mean_present(
                        float(metric.exact_match) for metric in metrics
                    ),
                    "avg_time_ms": mean_present(run.processing_time_ms for run in successful),
                    "avg_gateway_time_ms": mean_present(
                        run.gateway_duration_ms for run in successful
                    ),
                    "avg_confidence": mean_present(run.confidence for run in successful),
                }
            )
        return rows

    def matrix(self, filters):
        return self.aggregate(self.repository.cases(filters), filters.pipeline)

    def categories(self, filters):
        cases = self.repository.cases(filters)
        output = []
        for category in self.repository.categories():
            if filters.category and category.code != filters.category:
                continue
            selected = [
                case
                for case in cases
                if any(item.code == category.code for item in case.categories)
                and (
                    not case.runs
                    or any(
                        self.eligible(run)
                        and (not filters.pipeline or run.pipeline_id == filters.pipeline)
                        for run in case.runs
                    )
                )
            ]
            output.append(
                {
                    "code": category.code,
                    "display_name": category.display_name,
                    "test_cases": len(selected),
                    "pipelines": self.aggregate(selected, filters.pipeline),
                }
            )
        return output
