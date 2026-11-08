def test_dynamic_availability_update_preserves_definition_and_historical_results(client, case):
    created = client.post('/api/pipelines', json=dict(name='Review pipeline', source='custom', execution_mode='integrated', version='6', det_weight='baseline', rec_weight='thai_ft_v1'))
    assert created.status_code == 201
    pipeline = created.json()
    pid = pipeline['pipeline_id']
    runs = client.post(f"/api/test-cases/{case['id']}/run", json={'pipelines': [pid]}).json()['runs']
    changed = client.put(f'/api/pipelines/{pid}', json={'enabled': False, 'name': 'Renamed'})
    assert changed.status_code == 200, changed.text
    assert changed.json()['enabled'] is False and changed.json()['name'] == 'Renamed'
    assert changed.json()['integrated_options'] == pipeline['integrated_options']
    assert client.get(f"/api/test-cases/{case['id']}").json()['runs'] == runs
    assert client.put(f'/api/pipelines/{pid}', json={'endpoint': '/other'}).status_code == 422
    assert client.put(f'/api/pipelines/{pid}', json={'enabled': True}).status_code == 200
    assert client.post(f'/api/pipelines/{pid}/test-connection').json()['status'] == 'gateway_connected'
