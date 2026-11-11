"""Incremental worker correctness and bounded ORM retention, isolated synthetic DB."""
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import GlobalField, OCRField, OCRJob, PipelineRun, now
from app.db.models import TestCase as Case
from tests.test_ocr_jobs import paused_worker, pipeline


def large_layout(client, document, count, *, prefill=False):
    case = client.post('/api/test-cases', json={'document_id': document['id'], 'workflow': 'global'}).json()
    fields = [{'id': str(uuid4()), 'field_index': i + 1,
               'roi': {'x1': 10, 'y1': 20, 'x2': 250, 'y2': 120}, 'source': 'manual',
               'ground_truth_raw': None if prefill else ''} for i in range(count)]
    # Baseline can profile the previous engine above its admission ceiling without
    # changing production policy; final API-boundary tests exercise real admission.
    with client.app.state.database.session_factory() as session:
        record = session.get(Case, case['id'])
        record.global_fields = [GlobalField(**item) for item in fields]
        record.layout_confirmed_at = now()
        session.commit()
    return case, fields


def test_worker_retention_profile(client, document):
    case, fields = large_layout(client, document, 80)
    ids = [pipeline(client) for _ in range(3)]
    worker, create = paused_worker(client)
    jid = create(case, ids)
    assert worker.claim()[0] == jid
    samples = []

    def committed(session):
        if session.bind is not worker.database.engine:
            return
        samples.append({'objects': len(session.identity_map),
                        'ocr_fields': sum(isinstance(x, OCRField) for x in session.identity_map.values())})
    event.listen(Session, 'after_commit', committed)
    try:
        asyncio.run(worker.execute(jid))
    finally:
        event.remove(Session, 'after_commit', committed)
    job = client.get('/api/ocr-jobs/' + jid).json()
    assert job['status'] == 'completed', job
    assert job['completed_units'] == 240 and job['failed_units'] == 0
    runs = client.get('/api/ocr-jobs/' + jid + '/results').json()['runs']
    assert [r['pipeline_id'] for r in runs] == ids
    assert all(len(r['fields']) == 80 for r in runs)
    assert all({f['global_field_id'] for f in r['fields']} == {f['id'] for f in fields} for r in runs)
    output = os.environ.get('RETENTION_REPORT')
    if output:
        Path(output).write_text(json.dumps({'samples': samples, 'max_retained_fields': max(s['ocr_fields'] for s in samples)}))
    assert max(s['ocr_fields'] for s in samples) <= 1


def test_native_release_is_once_after_closed_images_and_durable_units(client, document, monkeypatch):
    from sqlalchemy import func, select

    from app.services import ocr_jobs
    from app.services.image_service import ImageService
    case, _ = large_layout(client, document, 10)
    ids = [pipeline(client) for _ in range(3)]
    worker, create = paused_worker(client)
    jid = create(case, ids)
    opened, releases = [], []
    original = ImageService.open

    def tracked(data):
        image = original(data)
        opened.append(image)
        return image

    def released():
        assert opened
        for image in opened:
            with pytest.raises(ValueError):
                image.getpixel((0, 0))
        with worker.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(OCRField)) == 30
        releases.append(True)
    monkeypatch.setattr(ImageService, 'open', staticmethod(tracked))
    monkeypatch.setattr(ocr_jobs, 'release_native_memory', released)
    assert worker.claim()[0] == jid
    asyncio.run(worker.execute(jid))
    assert releases == [True]
    assert client.get('/api/ocr-jobs/'+jid).json()['status'] == 'completed'


def test_large_sync_compatibility_route_requires_durable_job_without_inference(client, document, gateway):
    case, _ = large_layout(client, document, 80)
    ids = [pipeline(client) for _ in range(3)]
    response = client.post('/api/test-cases/'+case['id']+'/run', json={'pipelines':ids})
    assert response.status_code == 409 and '/jobs' in response.json()['detail']
    assert not gateway[1]
    assert client.get('/api/test-cases/'+case['id']).json()['runs'] == []


@pytest.mark.parametrize('entropy', [False, True])
def test_source_encoding_cache_is_bounded_without_changing_crop_bytes(client, monkeypatch, entropy):
    import hashlib
    import io

    from PIL import Image

    from app.services.image_service import ImageService
    from app.services.pipeline_manager import PipelineManager
    image = Image.frombytes('RGB', (1000, 600), os.urandom(1800000)) if entropy else Image.new('RGB', (1000, 600), 'white')
    encoded = io.BytesIO()
    image.save(encoded, format='PNG')
    image.close()
    response = client.post('/api/documents', files={'file':('cache.png', encoded.getvalue(), 'image/png')})
    assert response.status_code == 201
    document = response.json()
    source = client.app.state.storage.read(document['storage_key'])
    assert (len(source) > 512 * 1024) == entropy
    case, fields = large_layout(client, document, 2)
    fields[0]['roi'] = {'x1':0,'y1':0,'x2':1000,'y2':600}
    with client.app.state.database.session_factory() as session:
        session.get(Case, case['id']).global_fields[0].roi = fields[0]['roi']
        session.commit()
    service = ImageService(client.app.state.settings)
    original = ImageService.canonical_crop
    with service.open(source) as page:
        expected = [original(service, page, field['roi'], encoded_source=source).sha256 for field in fields]
    observed = []

    def crop(self, page, roi, **kwargs):
        assert (kwargs['encoded_source'] is None) == entropy
        return original(self, page, roi, **kwargs)

    async def predict(manager, configs, page, crop, roi, origin):
        observed.append(crop.sha256)
        assert crop.sha256 == hashlib.sha256(crop.png).hexdigest()
        return [PipelineRun(pipeline_id=configs[0].pipeline_id, status='success',
                            final_text='ทดสอบ', confidence=.9, boxes=[], raw_response={})]
    monkeypatch.setattr(ImageService, 'canonical_crop', crop)
    monkeypatch.setattr(PipelineManager, 'run', predict)
    worker, create = paused_worker(client)
    jid = create(case, [pipeline(client) for _ in range(3)])
    assert worker.claim()[0] == jid
    asyncio.run(worker.execute(jid))
    assert observed == expected * 3
    assert client.get('/api/ocr-jobs/'+jid).json()['completed_units'] == 6


@pytest.mark.parametrize('count', [40, 60, 80])
def test_pipeline_first_mapping_bulk_gt_evaluation_and_full_export(client, document, monkeypatch, count):
    from app.services.pipeline_manager import PipelineManager
    case, fields = large_layout(client, document, count)
    ids = [pipeline(client) for _ in range(3)]
    calls = []
    database = client.app.state.database

    async def predict(manager, configs, original, crop, roi, source):
        # No Gateway wait is allowed to hold a worker DB transaction/connection.
        assert database.engine.pool.checkedout() == 0
        calls.append(configs[0].pipeline_id)
        return [PipelineRun(pipeline_id=configs[0].pipeline_id, status='success',
                            final_text='ทดสอบ ABC 123', confidence=.95, boxes=[], raw_response={})]
    monkeypatch.setattr(PipelineManager, 'run', predict)
    worker, create = paused_worker(client)
    jid = create(case, ids)
    assert worker.claim()[0] == jid
    asyncio.run(worker.execute(jid))
    assert calls == [pid for pid in ids for _ in range(count)]
    result = client.get('/api/ocr-jobs/' + jid + '/results').json()['runs']
    assert all([f['global_field_id'] for f in run['fields']] == [f['id'] for f in fields] for run in result)
    assert all(f['geometry']['roi'] == fields[f['field_index']-1]['roi'] for run in result for f in run['fields'])
    root = '/api/test-cases/' + case['id']
    values = [{'id': f['id'], 'ground_truth_raw': 'ทดสอบ ABC 123'} for f in fields]
    saved = client.put(root+'/global-ground-truth', json={'fields': values,
                       'ground_truth_raw': '\n'.join(v['ground_truth_raw'] for v in values), 'evaluation_mode': 'per_field'})
    assert saved.status_code == 200, saved.text
    evaluated = client.post(root+'/evaluate', json={'mode': 'auto', 'global_field_ids': [f['id'] for f in fields], 'require_complete_gt': True})
    assert evaluated.status_code == 200, evaluated.text
    for run in evaluated.json()['runs']:
        assert len(run['fields']) == count
        assert all(f['evaluation']['cer'] == f['evaluation']['wer'] == 0 and f['evaluation']['exact_match'] for f in run['fields'])
    assert calls == [pid for pid in ids for _ in range(count)]  # GT/export never infer.
    response = client.get(root+'/evaluation-report?mode=per_field')
    assert response.status_code == 200
    import io
    from zipfile import ZipFile
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        summaries = [json.loads(archive.read(name)) for name in archive.namelist() if name.endswith('summary.json')]
        assert summaries
    # Unknown identity must roll back the entire bulk edit.
    invalid = client.put(root+'/global-ground-truth', json={'fields': [
        {'id': fields[0]['id'], 'ground_truth_raw': 'must not save'},
        {'id': str(uuid4()), 'ground_truth_raw': 'unknown'}], 'ground_truth_raw': 'must not save', 'evaluation_mode': 'per_field'})
    assert invalid.status_code == 404
    reopened = client.get(root).json()
    assert reopened['global_fields'][0]['ground_truth_raw'] == 'ทดสอบ ABC 123'
    assert all(f['evaluation']['exact_match'] for r in reopened['runs'] for f in r['fields'])


@pytest.mark.parametrize('point', ['before_gateway', 'await_gateway', 'after_inference', 'during_commit', 'after_checkpoint', 'between_pipelines'])
def test_interruption_boundaries_preserve_committed_units(client, document, monkeypatch, point):
    from sqlalchemy import select
    from sqlalchemy.exc import OperationalError

    from app.services.incremental_global import IncrementalGlobalJob
    from app.services.ocr_jobs import JobWorker, LostLease
    from app.services.pipeline_manager import PipelineManager
    case, _ = large_layout(client, document, 10)
    ids = [pipeline(client) for _ in range(3)]
    worker, create = paused_worker(client)
    jid = create(case, ids)
    assert worker.claim()[0] == jid
    original_run, original_persist = PipelineManager.run, IncrementalGlobalJob.persist
    original_finish, original_commit = IncrementalGlobalJob.finish_pipeline, Session.commit
    raised = False
    calls = 0

    async def infer(manager, *args, **kwargs):
        nonlocal raised, calls
        calls += 1
        if point in ('before_gateway', 'await_gateway') and calls == 8 and not raised:
            raised = True
            if point == 'await_gateway':
                await asyncio.sleep(0)
            raise asyncio.CancelledError()
        return await original_run(manager, *args, **kwargs)

    def persist(engine, run_id, field, result, **kwargs):
        nonlocal raised
        if point == 'after_inference' and run_id and field.field_index == 8 and not raised:
            raised = True
            raise asyncio.CancelledError()
        original_persist(engine, run_id, field, result, **kwargs)
        if point == 'after_checkpoint' and run_id and field.field_index == 8 and not raised:
            raised = True
            raise OperationalError('synthetic lost commit acknowledgement', {}, Exception('synthetic'))

    def flushed(session, *_):
        if point == 'during_commit' and session.bind is worker.database.engine:
            if any(isinstance(obj, OCRField) and obj.field_index == 8 for obj in session.new):
                session.info['interrupt_unit'] = True

    def commit(session):
        nonlocal raised
        if session.info.get('interrupt_unit') and not raised:
            raised = True
            raise OperationalError('synthetic commit disconnect', {}, Exception('synthetic'))
        return original_commit(session)

    def finish(engine, run_id, elapsed):
        nonlocal raised
        original_finish(engine, run_id, elapsed)
        if point == 'between_pipelines' and not raised:
            raised = True
            raise asyncio.CancelledError()

    monkeypatch.setattr(PipelineManager, 'run', infer)
    monkeypatch.setattr(IncrementalGlobalJob, 'persist', persist)
    monkeypatch.setattr(IncrementalGlobalJob, 'finish_pipeline', finish)
    monkeypatch.setattr(Session, 'commit', commit)
    event.listen(Session, 'after_flush', flushed)
    try:
        with pytest.raises((asyncio.CancelledError, LostLease)):
            asyncio.run(worker.execute(jid))
    finally:
        event.remove(Session, 'after_flush', flushed)
    assert raised
    with worker.database.session_factory() as session:
        previous = set(session.scalars(select(OCRField.id)))
        assert len(previous) == (10 if point == 'between_pipelines' else 8 if point == 'after_checkpoint' else 7)
        job = session.get(OCRJob, jid)
        assert job.completed_units == len(previous)
        job.lease_expires_at = now()-timedelta(seconds=1)
        session.commit()
    replacement = JobWorker(worker.database, worker.settings, worker.storage, asyncio.Lock())
    assert replacement.claim()[0] == jid
    asyncio.run(replacement.execute(jid))
    final = client.get('/api/ocr-jobs/'+jid).json()
    assert final['status'] == 'completed' and final['completed_units'] == 30 and final['attempt_count'] == 2
    with worker.database.session_factory() as session:
        all_ids = set(session.scalars(select(OCRField.id)))
        assert len(all_ids) == 30 and previous.issubset(all_ids)


def test_dataset_reuses_one_page_and_preserves_every_crop(client, document, monkeypatch):
    import io
    from zipfile import ZipFile

    from PIL import Image

    from app.services.image_service import ImageService
    case, fields = large_layout(client, document, 40)
    with client.app.state.database.session_factory() as session:
        record = session.get(Case, case['id'])
        for field in record.global_fields:
            field.ground_truth_raw = field.ground_truth_normalized = 'ทดสอบ ABC'
            field.confirmed_at = now()
        session.commit()
    opened = []
    original = ImageService.open
    def tracked(data):
        image = original(data)
        opened.append(image)
        return image
    monkeypatch.setattr(ImageService, 'open', staticmethod(tracked))
    response = client.post('/api/dataset/export', json={'global_field_ids':[f['id'] for f in fields]})
    assert response.status_code == 200
    assert len(opened) == 1
    with pytest.raises(ValueError):
        opened[0].getpixel((0,0))  # Native owner is closed even though test holds it.
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert len([n for n in archive.namelist() if n.endswith('.png')]) == 40
        with Image.open(io.BytesIO(client.app.state.storage.read(document['storage_key']))) as image:
            expected = image.crop((10,20,250,120)).tobytes()
        for name in (n for n in archive.namelist() if n.endswith('.png')):
            with Image.open(io.BytesIO(archive.read(name))) as crop:
                assert crop.tobytes() == expected


def test_large_export_returns_freed_native_pages_before_zip_without_changing_pixels(client, monkeypatch):
    import io
    from zipfile import ZipFile

    from PIL import Image

    from app.services import dataset_service
    source = Image.frombytes('RGB', (1000, 300), os.urandom(900000))
    encoded = io.BytesIO()
    source.save(encoded, format='PNG')
    document = client.post('/api/documents', files={'file': ('entropy.png', encoded.getvalue(), 'image/png')}).json()
    case, fields = large_layout(client, document, 2)
    with client.app.state.database.session_factory() as session:
        record = session.get(Case, case['id'])
        record.global_fields[0].roi = {'x1': 0, 'y1': 0, 'x2': 1000, 'y2': 300}
        for field in record.global_fields:
            field.ground_truth_raw = field.ground_truth_normalized = 'ทดสอบ'
            field.confirmed_at = now()
        session.commit()
    calls = []
    monkeypatch.setattr(dataset_service, 'release_native_memory', lambda: calls.append('release'))
    response = client.post('/api/dataset/export', json={'global_field_ids': [f['id'] for f in fields]})
    assert response.status_code == 200
    # One large source and one large crop; the small crop adds no allocator hint.
    assert calls == ['release', 'release']
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        with Image.open(io.BytesIO(archive.read('dataset/images/000001.png'))) as exported:
            assert exported.size == source.size and exported.tobytes() == source.tobytes()
    source.close()


def test_selected_prefill_checkpoint_recovery_never_repeats_committed_inference(client, document, gateway, monkeypatch):
    from sqlalchemy import select

    from app.services.gt_prefill_service import prefill_pipeline
    from app.services.incremental_global import IncrementalGlobalJob
    from app.services.ocr_jobs import JobWorker
    from tests.test_gt_prefill import batch_response
    case, fields = large_layout(client, document, 10, prefill=True)
    config = prefill_pipeline([])
    config.pipeline_id = 'dynamic_prefill_selected'
    with client.app.state.database.session_factory() as session:
        session.add(config)
        session.commit()
    gateway[0]['handler'] = batch_response
    worker, create = paused_worker(client)
    jid = create(case, [config.pipeline_id])
    assert worker.claim()[0] == jid
    original = IncrementalGlobalJob.persist
    def interrupted(engine, run_id, field, result, **kwargs):
        original(engine, run_id, field, result, **kwargs)
        if field.field_index == 8:
            raise asyncio.CancelledError()
    monkeypatch.setattr(IncrementalGlobalJob, 'persist', interrupted)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(worker.execute(jid))
    with worker.database.session_factory() as session:
        job = session.get(OCRJob, jid)
        assert len(job.prefill_results) == 8
        # Compatibility with older partially saved prefill maps: reconstruct
        # one draft from its committed OCRField without calling DET/REC again.
        job.prefill_results = {k:v for k,v in job.prefill_results.items() if k != fields[0]['id']}
        job.lease_expires_at = now()-timedelta(seconds=1)
        previous = set(session.scalars(select(OCRField.id)))
        session.commit()
    monkeypatch.setattr(IncrementalGlobalJob, 'persist', original)
    replacement = JobWorker(worker.database, worker.settings, worker.storage, asyncio.Lock())
    assert replacement.claim()[0] == jid
    asyncio.run(replacement.execute(jid))
    final = client.get('/api/ocr-jobs/'+jid).json()
    assert final['status'] == 'completed' and final['completed_units'] == 10
    saved = client.get('/api/test-cases/'+case['id']).json()
    assert saved['gt_prefill']['status'] == 'ready'
    assert all(f['ground_truth_raw'] == 'draft 0\nsecond line' and not f['confirmed_at'] for f in saved['global_fields'])
    assert len([r for r in gateway[1] if r.url.path.endswith('-batches')]) == 20
    with worker.database.session_factory() as session:
        assert previous.issubset(set(session.scalars(select(OCRField.id))))


def test_global_all_failed_is_not_success_even_at_one_hundred_percent(client, document, gateway):
    import httpx
    case, fields = large_layout(client, document, 40)
    ids = [pipeline(client) for _ in range(3)]
    gateway[0]['handler'] = lambda request: httpx.Response(422, json={'error': {'code': 'SYNTHETIC_MODEL_FAILURE'}})
    worker, create = paused_worker(client)
    jid = create(case, ids)
    assert worker.claim()[0] == jid
    asyncio.run(worker.execute(jid))
    final = client.get('/api/ocr-jobs/'+jid).json()
    assert final['status'] == 'failed' and final['progress_percent'] == 100
    assert final['completed_units'] == final['failed_units'] == 120
    runs = client.get('/api/ocr-jobs/'+jid+'/results').json()['runs']
    assert len(runs) == 3 and all(r['status']=='error' and len(r['fields']) == 40 for r in runs)
    assert all(f['status'] == 'error' and f['diagnostics']['http_status'] == 422 and not f['evaluation'] for r in runs for f in r['fields'])
    # No retry on contract/model422; no hidden prefill or fabricated predictions.
    assert len(gateway[1]) == 120
    root = '/api/test-cases/'+case['id']
    assert client.put(root+'/global-ground-truth', json={'fields': [
        {'id':f['id'],'ground_truth_raw':'ทดสอบ'} for f in fields],
        'ground_truth_raw':'\n'.join(['ทดสอบ']*40),'evaluation_mode':'per_field'}).status_code == 200
    assert client.post(root+'/evaluate', json={'mode':'auto','global_field_ids':[f['id'] for f in fields],
                                             'require_complete_gt':True}).status_code == 409


def test_previously_accepted_legacy_six_pipeline_snapshot_recovers_without_new_admission(client, case):
    from sqlalchemy import select

    from app.db.models import PipelineConfig
    from app.services.ocr_jobs import snapshot
    ids = [pipeline(client) for _ in range(6)]
    worker, create = paused_worker(client)
    jid = create(case, ids[:3])
    # Simulate a durable pre-upgrade Job, not a new request bypassing validation.
    with worker.database.session_factory() as session:
        job = session.get(OCRJob, jid)
        job.pipeline_ids = ids
        job.config_snapshot = [snapshot(session.scalar(select(PipelineConfig).where(PipelineConfig.pipeline_id == pid))) for pid in ids]
        job.total_pipelines = 6
        session.commit()
    assert worker.claim()[0] == jid
    asyncio.run(worker.execute(jid))
    job = client.get('/api/ocr-jobs/'+jid).json()
    assert job['status'] == 'completed' and job['completed_pipelines'] == 6
    runs = client.get('/api/ocr-jobs/'+jid+'/results').json()['runs']
    assert [r['pipeline_id'] for r in runs] == ids and all(r['status']=='success' for r in runs)
    rejected = client.post('/api/test-cases/'+case['id']+'/jobs', json={'pipelines':ids,'idempotency_key':'new-six-forbidden'})
    assert rejected.status_code == 422
