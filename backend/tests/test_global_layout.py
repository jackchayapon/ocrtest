import io
import os
from uuid import uuid4
from zipfile import ZipFile

import pytest
from alembic.config import Config
from PIL import Image
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import BACKEND_ROOT
from tests.test_benchmark_pipeline import parts

PIPELINES = ["mint", "hutch_crop", "hutch_full", "benchmark", "thai_ft_v2"]


def test_synchronized_gt_requires_all_fields_and_matching_document(client, document):
    case, fields = layout(client, document)
    run(client, case)
    root = f"/api/test-cases/{case['id']}"
    payload = {"mode": "auto", "global_field_ids": [f["id"] for f in fields], "require_complete_gt": True}
    assert client.post(root + "/evaluate", json=payload).status_code == 422
    client.put(root + f"/global-fields/{fields[0]['id']}/ground-truth", json={"ground_truth_raw": "A\nB"})
    client.put(root + "/ground-truth", json={"ground_truth_raw": "A\nB"})
    assert client.post(root + "/evaluate", json=payload).status_code == 422
    client.put(root + f"/global-fields/{fields[1]['id']}/ground-truth", json={"ground_truth_raw": "C"})
    assert client.post(root + "/evaluate", json=payload).status_code == 422
    client.put(root + "/ground-truth", json={"ground_truth_raw": "A\nB\nC"})
    assert client.post(root + "/evaluate", json={**payload, "global_field_ids": [fields[0]['id']]}).status_code == 422
    result = client.post(root + "/evaluate", json=payload)
    assert result.status_code == 200, result.text
    assert all(r["document_evaluation"] and all(f["evaluation"] for f in r["fields"]) for r in result.json()["runs"])


@pytest.mark.parametrize("whole,sub", [(True, False), (False, True), (True, True), (False, False)])
def test_smart_calculation_data_presence_and_persistence(client, document, whole, sub):
    case, fields = layout(client, document)
    runs = run(client, case)
    root = f"/api/test-cases/{case['id']}"
    prediction = runs[0]["final_text"]
    if whole:
        client.put(root + "/ground-truth", json={"ground_truth_raw": prediction})
    if sub:
        client.put(root + f"/global-fields/{fields[1]['id']}/ground-truth", json={"ground_truth_raw": "shared GT"})
    response = client.post(root + "/evaluate", json={"mode": "auto", "global_field_ids": [f["id"] for f in fields]})
    assert response.status_code == (200 if whole or sub else 422), response.text
    saved = client.get(root).json()
    for result in saved["runs"]:
        assert bool(result["document_evaluation"]) == whole
        assert result["fields"][0]["evaluation"] is None
        assert bool(result["fields"][1]["evaluation"]) == sub
        if whole:
            assert result["document_evaluation"]["prediction"] == result["final_text"]
            assert result["document_evaluation"]["global_field_ids"] == [f["id"] for f in fields]
    if whole and sub:
        old = saved["runs"][0]["document_evaluation"]
        client.put(root + f"/global-fields/{fields[1]['id']}/ground-truth", json={"ground_truth_raw": "edited"})
        edited = client.get(root).json()
        assert edited["runs"][0]["document_evaluation"] == old
        assert edited["runs"][0]["fields"][1]["evaluation"] is None


def layout(client, document, count=2, confirmed=True):
    case = client.post(
        "/api/test-cases", json={"document_id": document["id"], "workflow": "global"}
    ).json()
    fields = [
        {
            "id": str(uuid4()),
            "field_index": i + 1,
            "roi": {"x1": 10 + i * 10, "y1": 20, "x2": 200 + i * 10, "y2": 120},
            "source": "auto" if i == 0 else "manual",
        }
        for i in range(count)
    ]
    response = client.put(
        f"/api/test-cases/{case['id']}/global-fields",
        json={"fields": fields, "confirmed": confirmed},
    )
    assert response.status_code == 200, response.text
    return response.json(), fields


def run(client, case):
    response = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": PIPELINES})
    assert response.status_code == 200, response.text
    assert all(r["status"] == "success" for r in response.json()["runs"]), response.text
    return response.json()["runs"]


def test_layout_identity_confirmation_history_and_crop_fairness(client, document, gateway):
    case, fields = layout(client, document, confirmed=False)
    url = f"/api/test-cases/{case['id']}"
    assert client.post(url + "/run", json={"pipelines": PIPELINES}).status_code == 409
    assert client.get("/api/history", params={"document": document["id"]}).json() == []
    fields.append(
        {
            **fields[-1],
            "id": str(uuid4()),
            "field_index": 3,
            "source": "manual",
            "roi": {"x1": 30, "y1": 140, "x2": 230, "y2": 190},
        }
    )
    confirmed = client.put(
        url + "/global-fields", json={"fields": fields, "confirmed": True}
    ).json()
    assert [f["id"] for f in confirmed["global_fields"]] == [f["id"] for f in fields]
    before = len(gateway[1])
    runs = run(client, case)
    calls = gateway[1][before:]
    # Five DET/input requests per field; recognition crops are a separate downstream stage.
    inputs = [
        next(data for name, data in parts(r) if name in {"image", "images"})
        for r in calls
        if not r.url.path.endswith("text-recognition-batches")
    ]
    assert len(inputs) == 15
    for index, field in enumerate(fields):
        assert len(set(inputs[index * 5 : (index + 1) * 5])) == 1
        predictions = [
            next(f for f in r["fields"] if f["global_field_id"] == field["id"]) for r in runs
        ]
        assert len({f["diagnostics"]["input_sha256"] for f in predictions}) == 1
        assert (
            len(
                {
                    (f["diagnostics"]["input_width"], f["diagnostics"]["input_height"])
                    for f in predictions
                }
            )
            == 1
        )
        assert all(f["geometry"]["roi"] == field["roi"] for f in predictions)
        assert predictions[2]["diagnostics"]["crop_stage"] == "app_crop"
        assert all(f["evaluation"] is None for f in predictions)
    assert len(client.get("/api/history", params={"document": document["id"]}).json()) == 1
    assert (
        client.put(url + "/global-fields", json={"fields": fields, "confirmed": True}).status_code
        == 409
    )
    reopened = client.get(url).json()
    assert [f["id"] for f in reopened["global_fields"]] == [f["id"] for f in fields]


@pytest.mark.parametrize("mode", ["per_field"])
def test_shared_gt_explicit_evaluation_persistence_and_invalidation(client, document, mode):
    case, fields = layout(client, document)
    runs = run(client, case)
    root = f"/api/test-cases/{case['id']}"
    url = root + f"/global-fields/{fields[1]['id']}"
    assert (
        client.post(
            root + "/evaluate", json={"mode": "per_field", "global_field_ids": [fields[1]["id"]]}
        ).status_code
        == 422
    )
    gt = {"ground_truth_raw": "shared GT"}
    draft = client.put(url + "/ground-truth", json=gt).json()
    assert all(f["evaluation"] is None for r in draft["runs"] for f in r["fields"])
    evaluated = client.post(
        url.split("/global-fields/")[0] + "/evaluate",
        json={"mode": "per_field", "global_field_ids": [url.split("/global-fields/")[1]]},
    )
    assert evaluated.status_code == 200, evaluated.text
    saved = client.get(root).json()
    for result in saved["runs"]:
        f1, f2 = result["fields"]
        assert f1["evaluation"] is None
        assert f2["evaluation"]["mode"] == mode
        assert f2["global_field_id"] == fields[1]["id"]
        assert result["field_summary"]["confirmed_fields"] == 1
    again = client.post(
        url.split("/global-fields/")[0] + "/evaluate",
        json={"mode": "per_field", "global_field_ids": [url.split("/global-fields/")[1]]},
    ).json()
    assert [r["fields"][1]["evaluation"]["events"] for r in again["runs"]] == [
        r["fields"][1]["evaluation"]["events"] for r in saved["runs"]
    ]
    # The legacy field endpoint cannot introduce a second conflicting GT.
    f = runs[0]["fields"][1]
    assert (
        client.put(
            root + f"/runs/{runs[0]['id']}/fields/{f['id']}/ground-truth",
            json={"ground_truth_raw": "conflict", "confirmed": True},
        ).status_code
        == 409
    )
    client.put(url + "/ground-truth", json={"ground_truth_raw": ""})
    assert (
        client.post(
            url.split("/global-fields/")[0] + "/evaluate",
            json={"mode": "per_field", "global_field_ids": [url.split("/global-fields/")[1]]},
        ).status_code
        == 422
    )
    assert all(r["fields"][1]["evaluation"] is None for r in client.get(root).json()["runs"])


def test_field_dataset_exact_source_crop_confirmed_gt_and_missing_source(
    client, document, settings, png
):
    case, fields = layout(client, document)
    run(client, case)
    url = f"/api/test-cases/{case['id']}/global-fields/{fields[0]['id']}"
    gt = "ไทย spaces\tline\nend\\"
    client.put(url + "/ground-truth", json={"ground_truth_raw": gt})
    assert (
        client.post("/api/dataset/export", json={"global_field_ids": [fields[0]["id"]]}).status_code
        == 422
    )
    assert (
        client.post(
            url.split("/global-fields/")[0] + "/evaluate",
            json={"mode": "per_field", "global_field_ids": [url.split("/global-fields/")[1]]},
        ).status_code
        == 200
    )
    samples = client.get("/api/dataset/samples", params={"document": document["id"]}).json()
    assert samples["total"] == 1 and samples["items"][0]["global_field_id"] == fields[0]["id"]
    response = client.post("/api/dataset/export", json={"global_field_ids": [fields[0]["id"]]})
    assert response.status_code == 200, response.text
    z = ZipFile(io.BytesIO(response.content))
    assert z.testzip() is None
    assert (
        z.read("dataset/label.txt").decode() == "images/000001.png\tไทย spaces\\tline\\nend\\\\\n"
    )
    with (
        Image.open(io.BytesIO(png)) as original,
        Image.open(io.BytesIO(z.read("dataset/images/000001.png"))) as crop,
    ):
        assert crop.tobytes() == original.crop((10, 20, 200, 120)).tobytes()
    (settings.storage_path / document["storage_key"]).unlink()
    assert client.get("/api/dataset/samples").json()["items"][0]["source_available"] is False
    assert (
        client.post("/api/dataset/export", json={"global_field_ids": [fields[0]["id"]]}).status_code
        == 409
    )


def test_identity_ownership_delete_add_and_clamping(client, document):
    case, fields = layout(client, document, confirmed=False)
    other, _ = layout(client, document, count=1)
    root = f"/api/test-cases/{case['id']}"
    assert (
        client.put(
            f"/api/test-cases/{other['id']}/global-fields", json={"fields": fields}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/test-cases/{other['id']}/evaluate",
            json={"mode": "per_field", "global_field_ids": [fields[0]["id"]]},
        ).status_code
        == 404
    )
    fields[0]["roi"]["x2"] = 999
    changed = client.put(root + "/global-fields", json={"fields": fields, "confirmed": True}).json()
    assert changed["global_fields"][0]["roi"]["x2"] == 300
    fields = fields[1:] + [
        {
            **fields[1],
            "id": str(uuid4()),
            "field_index": 3,
            "roi": {"x1": 30, "y1": 140, "x2": 230, "y2": 190},
        }
    ]
    changed = client.put(root + "/global-fields", json={"fields": fields, "confirmed": True}).json()
    assert [f["field_index"] for f in changed["global_fields"]] == [1, 2]
    assert [f["id"] for f in changed["global_fields"]] == [f["id"] for f in fields]


def test_detector_order_is_not_global_identity_and_failure_isolation(client, document, gateway):
    import httpx

    from tests.upstream_fixture import response as upstream_response

    def handler(request):
        value = upstream_response(request)
        if request.url.params.get("engine") == "custom":
            payload = value.json()
            payload["data"]["lines"].reverse()
            return httpx.Response(200, json=payload)
        if request.url.params.get("model") == "thai_ft_v2":
            return httpx.Response(503, json={"error": {"code": "SERVICE_UNAVAILABLE"}})
        return value

    gateway[0]["handler"] = handler
    case, fields = layout(client, document)
    response = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": PIPELINES})
    assert response.status_code == 200
    runs = response.json()["runs"]
    for result in runs:
        assert [f["global_field_id"] for f in result["fields"]] == [f["id"] for f in fields]
        assert all(
            f["status"] == ("error" if result["pipeline_id"] == "thai_ft_v2" else "success")
            for f in result["fields"]
        )
    mint = next(r for r in runs if r["pipeline_id"] == "mint")
    assert mint["fields"][0]["diagnostics"]["raw_response"]["data"]["lines"][0]["text"] == "ABCD"
    assert mint["fields"][0]["ocr_text"].endswith("ABCD")


@pytest.mark.parametrize(
    "gt,kind", [("ABXD", "substitution"), ("ABD", "insertion"), ("ABXCD", "deletion")]
)
@pytest.mark.parametrize("mode", ["per_field", "whole_document"])
def test_field_alignment(client, document, gt, kind, mode):
    case, fields = layout(client, document, count=1)
    run(client, case)
    root = f"/api/test-cases/{case['id']}"
    url = root + f"/global-fields/{fields[0]['id']}"
    prediction = client.get(root).json()["runs"][0]["fields"][0]["ocr_text"]
    gt = prediction.replace("ABCD", gt)
    assert (
        client.put(
            (url if mode == "per_field" else root) + "/ground-truth", json={"ground_truth_raw": gt}
        ).status_code
        == 200
    )
    payload = {"mode": mode}
    if mode == "per_field":
        payload["global_field_ids"] = [fields[0]["id"]]
    saved = client.post(root + "/evaluate", json=payload).json()
    mint = next(r for r in saved["runs"] if r["pipeline_id"] == "mint")
    value = mint["fields"][0]["evaluation"] if mode == "per_field" else mint["document_evaluation"]
    assert any(s["kind"] == kind for s in value["spans"])


def test_historical_case_not_converted(client, case):
    assert client.get(f"/api/test-cases/{case['id']}").json()["global_fields"] == []
    assert (
        client.put(f"/api/test-cases/{case['id']}/global-fields", json={"fields": []}).status_code
        == 409
    )


def test_geometry_order_reorder_identity_and_historical_lock(client, document):
    case, _ = layout(client, document, count=1, confirmed=False)
    root = f"/api/test-cases/{case['id']}"
    boxes = [(10, 130, 80, 190), (190, 23, 280, 80), (10, 20, 90, 80)]
    fields = [
        {
            "id": str(uuid4()),
            "field_index": i + 1,
            "roi": dict(zip(("x1", "y1", "x2", "y2"), box)),
            "source": "auto",
        }
        for i, box in enumerate(boxes)
    ]
    result = client.put(root + "/global-fields", json={"fields": fields, "confirmed": True}).json()
    assert [f["id"] for f in result["global_fields"]] == [fields[i]["id"] for i in (2, 1, 0)]
    assert [f["field_index"] for f in result["global_fields"]] == [1, 2, 3]
    fields[0]["roi"] = {"x1": 1, "y1": 2, "x2": 80, "y2": 12}
    reordered = client.put(
        root + "/global-fields", json={"fields": list(reversed(fields)), "confirmed": True}
    ).json()
    assert [f["id"] for f in reordered["global_fields"]] == [fields[i]["id"] for i in (0, 2, 1)]
    assert client.post(root + "/run", json={"pipelines": ["mint"]}).status_code == 200
    assert client.put(root + "/global-fields", json={"fields": fields}).status_code == 409
    assert client.get(root).json()["global_fields"] == reordered["global_fields"]


def test_canonical_document_joins_uuid_mapping_not_prediction_order():
    from types import SimpleNamespace as Row

    from app.services.global_order import canonical_document_text

    fields = [Row(id="c", field_index=3), Row(id="a", field_index=1), Row(id="b", field_index=2)]
    predictions = [
        Row(global_field_id="b", ocr_text="Date"),
        Row(global_field_id="c", ocr_text="Address"),
        Row(global_field_id="a", ocr_text="Company"),
    ]
    assert canonical_document_text(fields, predictions) == "Company\nDate\nAddress"


def test_whole_document_explicit_evaluation_invalidation_and_no_dataset_labels(client, document):
    case, fields = layout(client, document)
    runs = run(client, case)
    root = f"/api/test-cases/{case['id']}"
    payload = {"mode": "whole_document"}
    assert client.post(root + "/evaluate", json=payload).status_code == 422
    mint = next(r for r in runs if r["pipeline_id"] == "mint")
    gt = mint["final_text"]
    assert "\n".join(f["ocr_text"] for f in mint["fields"]) == gt
    draft = client.put(
        root + "/ground-truth", json={"ground_truth_raw": gt, "confirmed": True}
    ).json()
    assert draft["document_gt_confirmed_at"] is None
    assert all(r["document_evaluation"] is None and r["metrics"] is None for r in draft["runs"])
    response = client.post(root + "/evaluate", json=payload)
    assert response.status_code == 200, response.text
    saved = client.get(root).json()
    assert saved["evaluation_mode"] == "whole_document" and saved["ground_truth_raw"] == gt
    for r in saved["runs"]:
        value = r["document_evaluation"]
        assert value["mode"] == "whole_document" and value["prediction"] == r["final_text"]
        assert value["global_field_ids"] == [f["id"] for f in fields]
    mint = next(r for r in saved["runs"] if r["pipeline_id"] == "mint")
    assert mint["metrics"]["cer"] == 0 and mint["document_evaluation"]["exact_match"]
    assert (
        client.get("/api/dataset/samples", params={"document": document["id"]}).json()["total"] == 0
    )
    assert (
        client.post("/api/dataset/export", json={"global_field_ids": [fields[0]["id"]]}).status_code
        == 422
    )
    assert client.get(root).json()["runs"] == saved["runs"]  # Read never creates evaluation.
    edited = client.put(root + "/ground-truth", json={"ground_truth_raw": ""}).json()
    assert all(r["document_evaluation"] is None and r["metrics"] is None for r in edited["runs"])
    assert client.post(root + "/evaluate", json=payload).status_code == 422


def test_field_edit_invalidates_only_its_evaluation_and_modes_remain_independent(client, document):
    case, fields = layout(client, document)
    run(client, case)
    root = f"/api/test-cases/{case['id']}"
    for field in fields:
        assert (
            client.put(
                root + f"/global-fields/{field['id']}/ground-truth",
                json={"ground_truth_raw": "GT " + field["id"]},
            ).status_code
            == 200
        )
    evaluated = client.post(
        root + "/evaluate",
        json={"mode": "per_field", "global_field_ids": [f["id"] for f in fields]},
    ).json()
    assert all(r["field_summary"]["confirmed_fields"] == 2 for r in evaluated["runs"])
    client.put(root + "/ground-truth", json={"ground_truth_raw": "document GT"})
    whole = client.post(root + "/evaluate", json={"mode": "whole_document"}).json()
    edited = client.put(
        root + f"/global-fields/{fields[1]['id']}/ground-truth",
        json={"ground_truth_raw": "changed"},
    ).json()
    for before, after in zip(evaluated["runs"], edited["runs"]):
        assert after["fields"][0]["evaluation"] == before["fields"][0]["evaluation"]
        assert after["fields"][1]["evaluation"] is None
    assert [r["document_evaluation"] for r in edited["runs"]] == [
        r["document_evaluation"] for r in whole["runs"]
    ]
    switched = client.put(root + "/evaluation-mode", json={"mode": "per_field"}).json()
    assert all(r["metrics"]["cer"] == r["field_summary"]["cer"] for r in switched["runs"])


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Requires disposable local PostgreSQL"
)
def test_postgresql_0007_upgrade_preserves_history_and_has_no_drift():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    assert url.host in {"localhost", "127.0.0.1"} and url.database.endswith("_test")
    engine = create_engine(url)
    schema = "global_migration_" + uuid4().hex
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    with engine.begin() as connection:
        # Unique disposable schema; never reset an existing database or touch production.
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
        connection.exec_driver_sql(f"SET search_path TO {schema}")
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0007_fields_roi_source")
        doc, case, run_id, field_id = [str(uuid4()) for _ in range(4)]
        connection.execute(
            text(
                "INSERT INTO documents(id,filename,mime_type,width,height,storage_key,created_at) VALUES(:id,'historical.png','image/png',100,100,:key,now())"
            ),
            {"id": doc, "key": doc + ".png"},
        )
        connection.execute(
            text(
                "INSERT INTO test_cases(id,document_id,status,ground_truth_raw,created_at,updated_at) VALUES(:id,:doc,'confirmed','preserved GT',now(),now())"
            ),
            {"id": case, "doc": doc},
        )
        connection.execute(
            text(
                "INSERT INTO pipeline_runs(id,test_case_id,pipeline_id,pipeline_name,status,raw_text,final_text,boxes,crop_stage,created_at) VALUES(:id,:case,'hutch_full','Hutch Full','success','original','original','[]','full_image',now())"
            ),
            {"id": run_id, "case": case},
        )
        connection.execute(
            text(
                "INSERT INTO ocr_fields(id,pipeline_run_id,field_index,geometry,ocr_text,ground_truth_raw,evaluation,created_at,updated_at) VALUES(:id,:run,0,'{}','original','legacy GT',CAST(:evaluation AS json),now(),now())"
            ),
            {"id": field_id, "run": run_id, "evaluation": '{"cer":0.25}'},
        )
        command.upgrade(cfg, "head")
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0012_ocr_jobs"
        )
        assert connection.execute(
            text("SELECT workflow,ground_truth_raw FROM test_cases")
        ).one() == ("legacy", "preserved GT")
        assert (
            connection.execute(text("SELECT crop_stage FROM pipeline_runs")).scalar_one()
            == "full_image"
        )
        old = connection.execute(
            text("SELECT global_field_id,ground_truth_raw,evaluation FROM ocr_fields")
        ).one()
        assert old[0] is None and old[1] == "legacy GT" and old[2] == {"cer": 0.25}
        assert "global_fields" in inspect(connection).get_table_names(schema=schema)
        assert "global_subfields" not in inspect(connection).get_table_names(schema=schema)
        # Alembic's default schema inspector must target this isolated schema too.
        previous = connection.dialect.default_schema_name
        connection.dialect.default_schema_name = schema
        try:
            command.check(cfg)
        finally:
            connection.dialect.default_schema_name = previous
    engine.dispose()
