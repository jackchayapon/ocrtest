from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import PipelineRun, TestCase as CaseRecord
from tests.test_global_layout import run


def setup_case(client, document, settings):
    case = client.post('/api/test-cases', json={'document_id': document['id'], 'workflow': 'global'}).json()
    root = f"/api/test-cases/{case['id']}"
    field = dict(id=str(uuid4()), field_index=1, source='manual', ground_truth_raw='',
                 roi=dict(x1=0, y1=0, x2=document['width'], y2=document['height']))
    assert client.put(root+'/global-fields', json=dict(fields=[field], confirmed=True)).status_code == 200
    runs = run(client, case)
    engine = create_engine(settings.database_url.get_secret_value())
    with Session(engine) as session:
        r = session.get(PipelineRun, runs[0]['id'])
        r.final_text = 'B\nA\nextra'
        r.fields[0].ocr_text = r.final_text
        r.fields[0].diagnostics = {'boxes': [dict(bbox=[0, 40, 100, 60], text='B'),
              dict(bbox=[0, 0, 100, 20], text='A'), dict(bbox=[0, 80, 100, 100], text='extra')]}
        session.get(CaseRecord, case['id']).gt_prefill = {'reference_boxes': {field['id']: [
            dict(bbox=[0, 0, 100, 20], text='A'), dict(bbox=[0, 40, 100, 60], text='B')]}}
        session.commit()
    engine.dispose()
    gt = 'A\nB\nmissing'
    assert client.put(root+'/global-ground-truth', json=dict(fields=[dict(id=field['id'], ground_truth_raw=gt)],
        ground_truth_raw=gt, evaluation_mode='whole_document')).status_code == 200
    payload = dict(run_id=runs[0]['id'], confirmed_gt=True, references=[
        dict(id='gt-0', text='A', roi=dict(x1=0, y1=0, x2=100, y2=20)),
        dict(id='gt-1', text='B', roi=dict(x1=0, y1=40, x2=100, y2=60)),
        dict(id='gt-2', text='missing', roi=None)])
    return root, field, runs[0]['id'], payload


def test_confirmation_persists_and_evaluation_uses_mapping(client, document, registered_catalog, settings, gateway):
    root, field, run_id, payload = setup_case(client, document, settings)
    calls = len(gateway[1])
    response = client.put(root+'/full-image-alignment', json=payload)
    assert response.status_code == 200, response.text
    stored = client.get(root).json()['full_image_alignment'][run_id]
    assert stored['references'][2]['roi'] is None
    assert stored['prediction'] == 'A\nB\n\nextra'
    response = client.post(root+'/evaluate', json=dict(mode='auto', global_field_ids=[field['id']], require_complete_gt=True))
    assert response.status_code == 200, response.text
    result = next(r for r in response.json()['runs'] if r['id'] == run_id)
    from app.services.field_service import compact_comparison
    expected = compact_comparison('A\nB\n\nextra', 'A\nB\nmissing')
    assert result['final_text'] == 'B\nA\nextra'
    assert result['document_evaluation']['prediction'] == stored['prediction']
    assert result['document_evaluation']['cer'] == expected['cer']
    assert result['fields'][0]['evaluation']['cer'] == expected['cer']
    assert len(result['document_evaluation']['line_evaluations']) == 4
    refreshed = next(r for r in client.get(root).json()['runs'] if r['id'] == run_id)
    assert refreshed['document_evaluation']['cer'] == expected['cer']
    insights = client.get(root+'/error-summary', params=dict(pipeline_id=result['pipeline_id'], mode='whole_document'))
    assert insights.status_code == 200, insights.text
    assert insights.json()['pipelines'][0]['scopes'][0]['display_ocr_text'] == stored['prediction']
    assert len(gateway[1]) == calls
    changed = 'Changed\nB\nmissing'
    client.put(root+'/global-ground-truth', json=dict(fields=[dict(id=field['id'], ground_truth_raw=changed)], ground_truth_raw=changed, evaluation_mode='whole_document'))
    assert client.post(root+'/evaluate', json=dict(mode='whole_document')).status_code == 409
    assert client.delete(root+'/full-image-alignment/'+run_id).status_code == 200
    assert client.post(root+'/evaluate', json=dict(mode='whole_document')).status_code == 200


def test_manual_pairing_null_roi_and_incomplete_det_text(client, document, registered_catalog, settings):
    root, field, run_id, payload = setup_case(client, document, settings)
    saved = client.get(root).json()
    r = next(r for r in saved['runs'] if r['id'] == run_id)
    payload['overrides'] = [dict(box_id=r['fields'][0]['id']+':1', reference_id='gt-0')]
    assert client.put(root+'/full-image-alignment', json=payload).status_code == 200
    engine = create_engine(settings.database_url.get_secret_value())
    with Session(engine) as session:
        session.get(PipelineRun, run_id).final_text += '\nunboxed text'
        session.commit()
    engine.dispose()
    assert client.put(root+'/full-image-alignment', json=payload).status_code == 422


def test_pipeline_swaps_keep_gt_fixed_and_do_not_change_other_pipelines(client, document, registered_catalog, settings):
    root, field, run_id, payload = setup_case(client, document, settings)
    payload['references'][:2] = reversed(payload['references'][:2])
    assert client.put(root+'/full-image-alignment', json=payload).status_code == 409
    payload['references'][:2] = reversed(payload['references'][:2])
    before = client.get(root).json()
    target_before = next(r for r in before['runs'] if r['id'] == run_id)
    fid = target_before['fields'][0]['id']
    payload['overrides'] = [dict(box_id=fid+':0', reference_id='gt-1'), dict(box_id=fid+':1', reference_id='gt-0'), dict(box_id=fid+':2', reference_id=None)]
    response = client.put(root+'/full-image-alignment', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['ground_truth_raw'] == 'A\nB\nmissing'
    evaluated = client.post(root+'/evaluate', json=dict(mode='auto', global_field_ids=[field['id']], require_complete_gt=True))
    assert evaluated.status_code == 200, evaluated.text
    for run_result in evaluated.json()['runs']:
        reference = 'A\nB\nmissing'
        assert run_result['document_evaluation']['ground_truth_raw'] == reference
        if run_result['id'] != run_id:
            assert not run_result['document_evaluation']['alignment_applied']
    target = next(r for r in evaluated.json()['runs'] if r['id'] == run_id)
    assert target['fields'][0]['diagnostics'] == target_before['fields'][0]['diagnostics']
    assert target['document_evaluation']['prediction'] == 'A\nB\n\nextra'
    for mode in ['whole_document', 'per_field']:
        insights = client.get(root+'/error-summary', params=dict(pipeline_id=target['pipeline_id'], mode=mode))
        assert insights.status_code == 200, insights.text
        scope = insights.json()['pipelines'][0]['scopes'][0]
        assert scope['state'] == 'ready'
        assert scope['display_ground_truth'] == 'A\nB\nmissing'


def test_no_geometry_keeps_original_prediction(client, document, registered_catalog, settings):
    root, field, run_id, payload = setup_case(client, document, settings)
    engine = create_engine(settings.database_url.get_secret_value())
    with Session(engine) as session:
        session.get(PipelineRun, run_id).fields[0].diagnostics = {'boxes': []}
        session.commit()
    engine.dispose()
    check = next(c for c in client.get(root+'/alignment-review').json()['pipelines'] if c['run_id'] == run_id)
    assert not check['ready'] and check['reason'] == 'geometry_unavailable'
    response = client.put(root+'/full-image-alignment', json={**payload, 'text_only': True})
    assert response.status_code == 200, response.text
    assert response.json()['full_image_alignment'][run_id]['prediction'] == 'B\nA\nextra'
    check = next(c for c in client.get(root+'/alignment-review').json()['pipelines'] if c['run_id'] == run_id)
    assert check['ready'] and check['reason'] == 'text_only_confirmed'


def test_auto_references_use_gt_geometry_not_target_pipeline(client, document, registered_catalog, settings):
    root, field, run_id, payload = setup_case(client, document, settings)
    engine = create_engine(settings.database_url.get_secret_value())
    with Session(engine) as session:
        case = session.get(CaseRecord, root.rsplit('/', 1)[1])
        case.gt_prefill = {'status': 'ready', 'reference_boxes': {field['id']: [
            {'bbox': [10, 40, 90, 60], 'text': 'B'}, {'bbox': [10, 0, 90, 20], 'text': 'A'}]}}
        session.commit()
    engine.dispose()
    response = client.get(root+'/full-image-alignment')
    assert response.status_code == 200, response.text
    refs = response.json()['references']
    assert refs[0]['roi'] == dict(x1=10, y1=0, x2=90, y2=20)
    assert refs[1]['roi'] == dict(x1=10, y1=40, x2=90, y2=60)
    assert refs[2]['roi'] is None
    # The API rejects even a permutation of the fixed GT rectangles.
    refs[0]['roi'], refs[1]['roi'] = refs[1]['roi'], refs[0]['roi']
    response = client.put(root+'/full-image-alignment', json={**payload, 'references': refs})
    assert response.status_code == 409, response.text


def test_missing_gt_geometry_is_not_fabricated_from_pipeline(client, document, registered_catalog, settings):
    root, _, _, _ = setup_case(client, document, settings)
    engine = create_engine(settings.database_url.get_secret_value())
    with Session(engine) as session:
        session.get(CaseRecord, root.rsplit('/', 1)[1]).gt_prefill = None
        session.commit()
    engine.dispose()
    response = client.get(root+'/full-image-alignment')
    assert response.status_code == 200
    assert not response.json()['geometry_available']
    assert all(r['roi'] is None for r in response.json()['references'])


def test_25_gt_24_detections_pad_middle_as_locked_empty_and_score_deletion(client, document, registered_catalog, settings):
    root, field, run_id, _ = setup_case(client, document, settings)
    lines = [f'line {i+1}' for i in range(25)]
    boxes = [dict(bbox=[0, i*6, 100, i*6+4], text=text) for i, text in enumerate(lines)]
    detected = [box for i, box in enumerate(boxes) if i != 20]
    original = '\n'.join(box['text'] for box in detected)
    engine = create_engine(settings.database_url.get_secret_value())
    with Session(engine) as session:
        case = session.get(CaseRecord, root.rsplit('/', 1)[1])
        case.gt_prefill = {'reference_boxes': {field['id']: boxes}}
        target = session.get(PipelineRun, run_id)
        target.final_text = target.fields[0].ocr_text = original
        target.fields[0].diagnostics = {'boxes': detected}
        box_id = target.fields[0].id
        session.commit()
    engine.dispose()
    gt = '\n'.join(lines)
    assert client.put(root+'/global-ground-truth', json=dict(fields=[dict(id=field['id'], ground_truth_raw=gt)], ground_truth_raw=gt, evaluation_mode='whole_document')).status_code == 200
    refs = client.get(root+'/full-image-alignment').json()['references']
    payload = dict(run_id=run_id, references=refs, confirmed_gt=True)
    check = next(c for c in client.get(root+'/alignment-review').json()['pipelines'] if c['run_id'] == run_id)
    assert not check['ready'] and check['reason'] == 'confirm_gaps'
    response = client.put(root+'/full-image-alignment', json=payload)
    assert response.status_code == 200, response.text
    snapshot = response.json()['full_image_alignment'][run_id]
    check = next(c for c in client.get(root+'/alignment-review').json()['pipelines'] if c['run_id'] == run_id)
    assert check['ready'] and check['reason'] == 'gaps_confirmed'
    assert len(snapshot['rows']) == 25
    assert snapshot['prediction'].split('\n')[20] == ''
    assert snapshot['prediction'].split('\n')[21:] == lines[21:]
    assert snapshot['placeholders'] == [dict(reference_id='gt-20', field_index=21, text='', locked=True, roi=refs[20]['roi'])]
    assert snapshot['line_confidences'][20] is None
    assert client.put(root+'/full-image-alignment', json={**payload, 'overrides': [dict(box_id=box_id+':20', reference_id='gt-20')]}).status_code == 422
    evaluated = client.post(root+'/evaluate', json=dict(mode='auto', global_field_ids=[field['id']], require_complete_gt=True))
    assert evaluated.status_code == 200, evaluated.text
    target = next(r for r in evaluated.json()['runs'] if r['id'] == run_id)
    scores = target['document_evaluation']['line_evaluations']
    assert len(scores) == 25
    assert scores[20]['cer'] == scores[20]['wer'] == 1
    assert scores[21]['cer'] == scores[21]['wer'] == 0
    assert target['final_text'] == original
    assert len(target['fields'][0]['diagnostics']['boxes']) == 24


def test_review_gate_checks_every_pipeline_before_scores_and_blocks_mismatched_confirmation(client, document, registered_catalog, settings):
    root, field, run_id, _ = setup_case(client, document, settings)
    engine = create_engine(settings.database_url.get_secret_value())
    with Session(engine) as session:
        case = session.get(CaseRecord, root.rsplit('/', 1)[1])
        boxes = [dict(bbox=[0,0,100,20],text='A'),dict(bbox=[0,40,100,60],text='B')]
        for r in case.runs:
            if r.id == run_id:
                r.fields[0].diagnostics = {'boxes': list(reversed(boxes))}
                r.final_text = r.fields[0].ocr_text = 'B\nA'
            else:
                r.fields[0].diagnostics = {'boxes': boxes}
                r.final_text = r.fields[0].ocr_text = 'A\nB'
        session.commit()
    engine.dispose()
    client.put(root+'/global-ground-truth', json=dict(fields=[dict(id=field['id'],ground_truth_raw='A\nB')],ground_truth_raw='A\nB',evaluation_mode='whole_document'))
    review = client.get(root+'/alignment-review').json()
    assert not review['ready']
    assert [c['run_id'] for c in review['pipelines'] if not c['ready']] == [run_id]
    request = dict(mode='auto',global_field_ids=[field['id']],require_complete_gt=True,require_spatial_review=True)
    assert client.post(root+'/evaluate',json=request).status_code == 409
    refs = client.get(root+'/full-image-alignment').json()['references']
    case = client.get(root).json()
    fid = next(r for r in case['runs'] if r['id']==run_id)['fields'][0]['id']
    wrong = dict(run_id=run_id,references=refs,confirmed_gt=True,overrides=[dict(box_id=fid+':0',reference_id='gt-0'),dict(box_id=fid+':1',reference_id='gt-1')])
    assert client.put(root+'/full-image-alignment',json=wrong).status_code == 200
    assert client.post(root+'/evaluate',json=request).status_code == 409
    wrong['overrides'] = [dict(box_id=fid+':0',reference_id='gt-1'),dict(box_id=fid+':1',reference_id='gt-0')]
    assert client.put(root+'/full-image-alignment',json=wrong).status_code == 200
    assert client.get(root+'/alignment-review').json()['ready']
    evaluated = client.post(root+'/evaluate',json=request)
    assert evaluated.status_code == 200, evaluated.text
    assert all(r['document_evaluation']['cer']==0 for r in evaluated.json()['runs'])
