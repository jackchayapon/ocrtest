from uuid import uuid4

from app.services.line_evaluation import line_evaluations


def test_line_metrics_preserve_blanks_crlf_and_extra_lines():
    scores = line_evaluations("A\r\n\r\nC\nextra", "A\n\nC")
    assert len(scores) == 4
    assert all(row["exact_match"] for row in scores[:3])
    assert not scores[3]["exact_match"]
    assert scores[3]["character_edits"] == 5
    missing = line_evaluations("A", "A\nB\n")
    assert len(missing) == 3
    assert missing[1]["cer"] == 1
    assert missing[2]["exact_match"]


def test_full_image_line_metrics_persist(client, document, registered_catalog):
    from tests.test_global_layout import run

    case = client.post('/api/test-cases', json={
        'document_id': document['id'], 'workflow': 'global',
    }).json()
    root = f"/api/test-cases/{case['id']}"
    field_id = str(uuid4())
    response = client.put(root + '/global-fields', json={'confirmed': True, 'fields': [{
        'id': field_id, 'field_index': 1, 'source': 'manual',
        'roi': {'x1': 0, 'y1': 0, 'x2': document['width'], 'y2': document['height']},
        'ground_truth_raw': 'A\n\nB',
    }]})
    assert response.status_code == 200
    run(client, case)
    result = client.post(root + '/evaluate', json={
        'mode': 'auto', 'global_field_ids': [field_id], 'require_complete_gt': True,
    })
    assert result.status_code == 200, result.text
    saved = client.get(root).json()
    assert len(saved['global_fields']) == 1
    for prediction in saved['runs']:
        scores = prediction['document_evaluation']['line_evaluations']
        assert scores == line_evaluations(prediction['final_text'], 'A\n\nB', detail=True)
