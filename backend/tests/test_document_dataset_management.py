import os
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import BACKEND_ROOT
from app.db.models import GlobalField, now
from tests.test_global_layout import layout


def test_document_types_validation_archive_and_history(client, png):
    defaults = client.get("/api/document-types").json()
    assert len(defaults) == 4 and all(t["system"] for t in defaults)
    assert client.delete(f"/api/document-types/{defaults[0]['id']}").status_code == 409
    custom = client.post("/api/document-types", json={"name": "  Receipt ใบเสร็จ  "}).json()
    assert custom["name"] == "Receipt ใบเสร็จ"
    assert client.post("/api/document-types", json={"name": "receipt ใบเสร็จ"}).status_code == 409
    for name in ("   ", "x" * 101):
        assert client.post("/api/document-types", json={"name": name}).status_code == 422
    doc = client.post("/api/documents", files={"file": ("receipt.png", png, "image/png")},
                      data={"document_type_id": custom["id"]}).json()
    assert client.put(f"/api/documents/{doc['id']}/type", json={"document_type_id": defaults[0]["id"]}).json()["document_type_id"] == defaults[0]["id"]
    assert client.put(f"/api/documents/{doc['id']}/type", json={"document_type_id": custom["id"]}).json()["document_type_name"] == custom["name"]
    case, _ = layout(client, doc)
    assert client.delete(f"/api/document-types/{custom['id']}").status_code == 200
    assert custom["id"] not in [t["id"] for t in client.get("/api/document-types").json()]
    saved = client.get(f"/api/test-cases/{case['id']}").json()
    assert saved["document"]["document_type_name"] == custom["name"]
    assert saved["document"]["document_type"] == "image"
    assert client.post("/api/documents", files={"file": ("receipt.png", png, "image/png")},
                       data={"document_type_id": custom["id"]}).status_code == 422


def evaluated(client, document):
    rec = next(m for m in client.get("/api/pipelines/models").json()
               if m["kind"] == "rec" and m["source"] == "custom" and m["weight"] == "thai_ft_v2" and m["version"] == "5")
    created = client.post("/api/pipelines", json={"name":"Hutch fine tune validation", "source":"custom",
        "execution_mode":"rec", "rec_model_id":rec["id"]})
    assert created.status_code == 201, created.text
    pipeline = created.json()["pipeline_id"]
    case, fields = layout(client, document, count=1)
    root = f"/api/test-cases/{case['id']}"
    assert client.post(root + "/run", json={"pipelines": [pipeline]}).status_code == 200
    client.put(root + f"/global-fields/{fields[0]['id']}/ground-truth", json={"ground_truth_raw": "confirmed label"})
    assert client.post(root + "/evaluate", json={"mode": "auto", "global_field_ids": [fields[0]["id"]]}).status_code == 200
    return root, fields[0]["id"]


def test_recent_dataset_exclusion_preserves_gt_source_history(client, document):
    old_root, old_id = evaluated(client, document)
    with client.app.state.database.session_factory() as session:
        session.get(GlobalField, old_id).confirmed_at = now() - timedelta(days=1)
        session.commit()
    root, id = evaluated(client, document)
    items = client.get("/api/dataset/samples").json()["items"]
    assert [i["id"] for i in items] == [id, old_id]
    before = client.get(root).json()
    assert before["history_status"] == "success" and before["ground_truth_raw"] is None
    assert client.delete(f"/api/dataset/items/{id}?kind=field").status_code == 200
    assert [i["id"] for i in client.get("/api/dataset/samples").json()["items"]] == [old_id]
    assert client.post("/api/dataset/export", json={"global_field_ids": [id]}).status_code == 422
    assert client.post("/api/dataset/export", json={"global_field_ids": [old_id]}).status_code == 200
    after = client.get(root).json()
    assert after["runs"] == before["runs"] and after["global_fields"] == before["global_fields"]
    assert client.get(f"/api/documents/{document['id']}/image").status_code == 200
    assert client.get(old_root).status_code == 200


def test_disabled_logs_accept_multilingual_filters(client, document):
    evaluated(client, document)
    for query in ("HUTCH", "fine", "hutch fine", "fixture", "สำเร็", "ocr สำเร็จ"):
        data = client.get("/api/logs", params={"q": query}).json()
        assert data == {"enabled": False, "total": 0, "items": []}, query
    assert client.get("/api/logs", params={"q": "no-such-file-XYZ"}).json()["total"] == 0
    assert client.get("/api/logs", params={"q": "%_"}).json()["total"] == 0


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="local PostgreSQL required")
def test_0009_additive_upgrade_preserves_old_document_and_no_drift():
    url=make_url(os.environ["TEST_DATABASE_URL"])
    assert url.host in {"127.0.0.1", "localhost"} and url.database.endswith("_test")
    engine=create_engine(url)
    schema="releaseb_"+uuid4().hex
    cfg=Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
        connection.exec_driver_sql(f"SET search_path TO {schema}")
        cfg.attributes["connection"]=connection
        command.upgrade(cfg,"0008_global_layout_evaluation")
        id=str(uuid4())
        connection.execute(text("INSERT INTO documents(id,filename,mime_type,width,height,storage_key,created_at) VALUES(:id,'preserved.png','image/png',30,20,:key,now())"),{"id":id,"key":id})
        command.upgrade(cfg,"0009_document_types_dataset")
        assert connection.execute(text("SELECT filename,document_type_id FROM documents WHERE id=:id"),{"id":id}).one()==("preserved.png",None)
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()=="0009_document_types_dataset"
        command.upgrade(cfg,"head")
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()=="0011_gt_prefill"
        assert connection.execute(text("SELECT filename FROM documents WHERE id=:id"),{"id":id}).scalar_one()=="preserved.png"
        previous=connection.dialect.default_schema_name
        connection.dialect.default_schema_name=schema
        try:
            command.check(cfg)
        finally:
            connection.dialect.default_schema_name=previous
    engine.dispose()
