"""Error alignment is a requested read operation, never a persisted event stream."""
from collections import defaultdict

from app.schemas.contracts import BenchmarkFilters
from app.services.matrix_service import MatrixService
from app.services.metrics_service import error_breakdown


class ErrorRepository:
    def __init__(self, session):
        self.session = session

    def aggregate(self, filters, limit, offset):
        service = MatrixService(self.session)
        cases = service.repository.cases(BenchmarkFilters(pipeline=filters.pipeline,
            category=filters.category, document=filters.document), analytics=True, texts=True, test_case_id=filters.test_case_id)
        groups = defaultdict(lambda: {'count': 0, 'cases': {}})
        for case, run in service.latest(cases, filters.pipeline):
            if filters.test_case_id and case.id != str(filters.test_case_id):
                continue
            if service.evaluation(case, run) is None:
                continue
            if case.workflow == 'global' and case.evaluation_mode == 'per_field':
                texts = [(f.ocr_text, f.ground_truth_raw) for f in run.fields if f.confirmed_at and f.evaluation]
            else:
                prediction = run.raw_text if filters.text_kind == 'raw' and run.raw_text is not None else run.final_text
                texts = [(prediction, case.ground_truth_raw)]
            for prediction, truth in texts:
                for event in error_breakdown(prediction or '', truth or ''):
                    if event['error_level'] != filters.error_level or (filters.error_type and event['error_type'] != filters.error_type):
                        continue
                    key = (run.pipeline_id, event['error_type'], event['ground_truth_unit'], event['ocr_unit'])
                    g = groups[key]
                    g['count'] += 1
                    g['cases'][case.id] = case
        ordered = sorted(groups, key=lambda k: (-groups[k]['count'], tuple(v or '' for v in k)))
        items = []
        for key in ordered[offset:offset + limit]:
            group = groups[key]
            items.append(dict(pipeline_id=key[0], error_type=key[1], ground_truth_unit=key[2],
                ocr_unit=key[3], count=group['count'], test_case_count=len(group['cases']),
                cases=[dict(id=c.id, document_id=c.document_id, filename=c.document.filename,
                    page_number=c.page_number, categories=[t.code for t in c.categories])
                    for c in sorted(group['cases'].values(), key=lambda c: c.id)[:20]]))
        return dict(total=len(groups), items=items, limit=limit, offset=offset)
