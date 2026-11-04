import pytest
from sqlalchemy import event

from app.db.models import GlobalField, OCRField, PipelineRun, now
from app.db.models import TestCase as Case


@pytest.mark.parametrize("count", [1, 50])
def test_dataset_page_bulk_loads_only_labels_and_source_metadata(client, document, count):
    with client.app.state.database.session_factory() as session:
        for i in range(count):
            case = Case(document_id=document["id"], workflow="global", layout_confirmed_at=now())
            case.global_fields = [GlobalField(field_index=1, source="manual",
                roi={"x1": 1, "y1": 2, "x2": 50, "y2": 40},
                ground_truth_raw=f"confirmed-{i}", ground_truth_normalized=f"confirmed-{i}",
                confirmed_at=now())]
            case.runs = [PipelineRun(pipeline_id="synthetic", pipeline_name="Synthetic", status="success",
                raw_response={"archive": "x" * 10000}, final_text="not a label",
                fields=[OCRField(field_index=1, ocr_text="not a label", geometry={},
                                 diagnostics={"archive": "x" * 10000})])]
            session.add(case)
        session.commit()
    statements = []
    engine = client.app.state.database.engine

    def collect(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", collect)
    try:
        response = client.get("/api/dataset/samples", params={"limit": 50, "document": document["id"]})
    finally:
        event.remove(engine, "before_cursor_execute", collect)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == count and len(body["items"]) == count
    assert {i["ground_truth_raw"] for i in body["items"]} == {f"confirmed-{i}" for i in range(count)}
    assert all(i["source_available"] and i["global_field_id"] for i in body["items"])
    assert len(statements) <= 8, statements
    assert all("pipeline_runs" not in s and "ocr_fields" not in s and "raw_response" not in s for s in statements)
    assert "archive" not in response.text and "not a label" not in response.text
