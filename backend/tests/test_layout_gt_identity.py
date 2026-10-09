from uuid import uuid4

from tests.test_global_layout import layout


def added_field():
    return dict(id=str(uuid4()), field_index=3, source="manual",
                roi=dict(x1=5, y1=1, x2=100, y2=10), ground_truth_raw=None)


def test_insert_and_delete_keep_gt_by_id_not_display_number(client, document):
    case, fields = layout(client, document)
    root = f"/api/test-cases/{case['id']}"
    for field, text in zip(fields, ["first\nsecond line", "last"]):
        assert client.put(root + f"/global-fields/{field['id']}/ground-truth", json={"ground_truth_raw": text}).status_code == 200
    added = added_field()
    response = client.put(root + "/global-fields", json={"fields": [*fields, added], "confirmed": True})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert [(f["id"], f["field_index"], f["ground_truth_raw"]) for f in saved["global_fields"]] == [
        (added["id"], 1, None), (fields[0]["id"], 2, "first\nsecond line"), (fields[1]["id"], 3, "last"),
    ]
    assert saved["ground_truth_raw"] == "\nfirst\nsecond line\nlast"
    response = client.put(root + "/global-fields", json={"fields": [fields[1], added], "confirmed": False})
    assert response.status_code == 200, response.text
    assert response.json()["ground_truth_raw"] == "\nlast"


def test_revision_copies_gt_with_each_field_and_leaves_history_unchanged(client, document):
    case, fields = layout(client, document)
    root = f"/api/test-cases/{case['id']}"
    for field, text in zip(fields, ["saved draft", "saved GT\nline two"]):
        client.put(root + f"/global-fields/{field['id']}/ground-truth", json={"ground_truth_raw": text})
    pipeline = client.post("/api/pipelines", json={"name":"OCR", "source":"official", "execution_mode":"integrated"}).json()
    assert client.post(root + "/run", json={"pipelines":[pipeline["pipeline_id"]]}).status_code == 200
    original = client.get(root).json()
    revision = client.post("/api/test-cases", json={"document_id":document["id"], "workflow":"global"}).json()
    copied = [{**field, "id":str(uuid4()), "ground_truth_raw": old["ground_truth_raw"]}
              for field, old in zip(fields, original["global_fields"])]
    response = client.put(f"/api/test-cases/{revision['id']}/global-fields", json={"fields":[*copied, added_field()], "confirmed":True})
    assert response.status_code == 200, response.text
    new = response.json()
    assert [f["ground_truth_raw"] for f in new["global_fields"]] == [None, "saved draft", "saved GT\nline two"]
    assert new["ground_truth_raw"] == "\nsaved draft\nsaved GT\nline two"
    assert new["runs"] == [] and new["document_gt_confirmed_at"] is None
    assert all(f["confirmed_at"] is None for f in new["global_fields"])
    assert client.get(root).json() == original
