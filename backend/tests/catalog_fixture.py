"""Explicit current-schema catalog for historical workflow regression tests.

Names/IDs are test aliases, not startup defaults. All execution uses the real
dynamic adapters and registered model paths; no manager or inference patches.
"""
from uuid import uuid4

from sqlalchemy import select

from app.db.models import OCRModel, PipelineConfig


def register_catalog(client):
    with client.app.state.database.session_factory() as session:
        def model(kind, version, variant=None):
            stem = 'text-detection' if kind == 'det' else 'text-recognition'
            query = f'version={version}' + (f'&model={variant}' if variant else '')
            item = OCRModel(id=str(uuid4()), name=f'Test {kind} V{version}', kind=kind,
                            source='custom', version=str(version), weight=variant or 'baseline',
                            single_path=f'/api/v1/{stem}s?{query}',
                            batch_path=f'/api/v1/{stem}-batches?{query}')
            session.add(item)
            return item
        det, rec = model('det', 6), model('rec', 5)
        ft_det, ft_rec = model('det', 6, 'thai_ft_v2'), model('rec', 6, 'thai_ft_v2')
        rec_only = model('rec', 5, 'thai_ft_v2')
        specs = [
            ('mint', 'Mint Custom OCR', 'custom', 'integrated', None, None),
            ('hutch_crop', 'Hutch Crop', 'official', 'integrated', None, None),
            ('hutch_full', 'Hutch Full', 'official', 'integrated', None, None),
            ('benchmark', 'Benchmark', 'custom', 'det_rec', det, rec),
            ('thai_ft_v2', 'Thai FT v2', 'custom', 'det_rec', ft_det, ft_rec),
            ('hutch_fine_tune_v2', 'Hutch fine tune v2', 'custom', 'rec', None, rec_only),
        ]
        for pid, name, source, mode, detector, recognizer in specs:
            if session.scalar(select(PipelineConfig).where(PipelineConfig.pipeline_id == pid)) is not None:
                continue
            query = {'engine': 'custom' if source == 'custom' else 'paddle'}
            endpoint, field = '/api/v1/ocr-results', 'image'
            if mode != 'integrated':
                selected = detector or recognizer
                endpoint, encoded_query = selected.batch_path.split('?')
                query = dict(pair.split('=') for pair in encoded_query.split('&'))
                field = 'images'
            session.add(PipelineConfig(pipeline_id=pid, name=name, source=source,
                execution_mode=mode, enabled=True, engine='dynamic', endpoint=endpoint,
                query_params=query, request_format='multipart', file_field_name=field,
                det_model=detector, rec_model=recognizer,
                integrated_options={'paddle_model_defaults': True} if source == 'official'
                else {'version':'6','det_weight':'baseline','rec_weight':'baseline'} if mode == 'integrated' else None))
        session.commit()
