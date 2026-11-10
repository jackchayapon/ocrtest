import httpx

from tests.test_global_layout import layout


def test_det_200_malformed_contract_preserves_field_stage_and_request(client, document, gateway):
    models = client.get('/api/pipelines/models').json()
    det = next(m for m in models if m['source']=='custom' and m['kind']=='det' and m['version']=='6')
    rec = next(m for m in models if m['source']=='custom' and m['kind']=='rec' and m['version']=='5')
    pid=client.post('/api/pipelines',json={'name':'Malformed contract','source':'custom','execution_mode':'det_rec','det_model_id':det['id'],'rec_model_id':rec['id']}).json()['pipeline_id']
    case, _ = layout(client, document)
    original=gateway[0]['handler']
    def respond(request):
        if request.url.path.endswith('/text-detection-batches'):
            return httpx.Response(200,json={'data':{'contract_version':'leaf-inference-v1','kind':'text_detection_batch','count':2,'raw_output':[]},'meta':{'request_id':'det-malformed-test'}})
        return original(request)
    gateway[0]['handler']=respond
    run=client.post(f"/api/test-cases/{case['id']}/run",json={'pipelines':[pid]}).json()['runs'][0]
    assert run['error_code']=='FIELD_PIPELINE_ERROR'
    for field in run['fields']:
        assert field['status']=='error'
        assert field['diagnostics']['failure_stage']=='detection_contract'
        assert field['diagnostics']['http_status']==200
        assert field['diagnostics']['gateway_request_id']=='det-malformed-test'
    assert not any(r.url.path.endswith('/text-recognition-batches') for r in gateway[1])
