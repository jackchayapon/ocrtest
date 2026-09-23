import io
import itertools
import os
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import OCRField, PipelineRun
from app.main import create_app
from app.services.field_service import compare_field, field_summary
from app.services.metrics_service import calculate_metrics, normalize_text
from tests.test_benchmark_pipeline import parts


@pytest.mark.parametrize(
    "gt,ocr,kind",
    [
        ("abc", "abc", None),
        ("ก", "ค", "substitution"),
        ("abcd", "acd", "deletion"),
        ("acd", "abcd", "insertion"),
        ("", "ก", "insertion"),
        ("ก", "", "deletion"),
        ("", "", None),
        (" e\u0301\r\n ไทย ", "é ไทย", None),
    ],
)
def test_field_diff_same_metrics_and_visible_gaps(gt, ocr, kind):
    result = compare_field(ocr, gt)
    assert {key: result[key] for key in ("cer", "wer", "exact_match")} == calculate_metrics(ocr, gt)
    errors = [s for s in result["spans"] if s["kind"] != "equal"]
    assert (errors[0]["kind"] if errors else None) == kind
    assert "".join(s["text"] for s in result["spans"]) == normalize_text(ocr)
    assert "".join(
        s["text"] if s["kind"] == "equal" else s["missing"] or "" for s in result["spans"]
    ) == normalize_text(gt)


def test_field_diff_alignment_exhaustive_and_weighted_totals():
    words = ["".join(p) for n in range(4) for p in itertools.product("ab", repeat=n)]
    for gt, ocr in itertools.product(words, repeat=2):
        spans = compare_field(ocr, gt)["spans"]
        assert "".join(s["text"] for s in spans) == ocr
        assert (
            "".join(s["text"] if s["kind"] == "equal" else s["missing"] or "" for s in spans) == gt
        )
    fields = [
        OCRField(confirmed_at=True, evaluation=compare_field("x", "a")),
        OCRField(confirmed_at=True, evaluation=compare_field("b" * 99, "b" * 99)),
        OCRField(confirmed_at=None, evaluation=compare_field("bad", "ignored")),
    ]
    summary = field_summary(fields)
    assert summary["cer"] == 0.01 and summary["wer"] == 0.5
    assert summary["confirmed_fields"] == 2 and summary["exact_match"] is False
    assert field_summary([])["exact_match"] is None
    assert (
        field_summary([OCRField(confirmed_at=True, evaluation=compare_field("x", ""))])["cer"]
        is None
    )


def test_fields_lifecycle_scoping_preview_replacement_and_history(client, case):
    runs = client.post(
        f"/api/test-cases/{case['id']}/run", json={"pipelines": ["mint", "hutch_crop", "benchmark"]}
    ).json()["runs"]
    run = runs[0]
    f = run["fields"][0]
    assert f["field_index"] == 0 and f["ocr_text"] == run["boxes"][0]["text"]
    assert f["confidence"] == run["boxes"][0]["rec_confidence"]
    assert f["geometry"]["polygon"] == run["boxes"][0]["polygon"]
    url = f"/api/test-cases/{case['id']}/runs/{run['id']}/fields/{f['id']}"
    preview = client.post(url + "/check", json={"ground_truth_raw": "กรุงเทพมหานคร"}).json()
    assert preview["character_edits"] > 0
    assert (
        client.get(f"/api/test-cases/{case['id']}").json()["runs"][0]["fields"][0][
            "ground_truth_raw"
        ]
        is None
    )
    draft = client.put(url + "/ground-truth", json={"ground_truth_raw": "ไทย"}).json()
    assert draft["confirmed_at"] is None and draft["evaluation"] is None
    for _ in range(2):
        response = client.put(
            url + "/ground-truth", json={"ground_truth_raw": "ไทย", "confirmed": True}
        )
        assert response.status_code == 200
        assert response.json()["evaluation"] == compare_field(f["ocr_text"], "ไทย")
    saved = client.get(f"/api/test-cases/{case['id']}").json()
    assert saved["runs"][0]["field_summary"]["confirmed_fields"] == 1
    assert saved["runs"][1]["field_summary"]["confirmed_fields"] == 0
    assert saved["runs"][0]["metrics"] == run["metrics"]  # Whole GT metrics untouched.
    other = url.replace(run["id"], runs[1]["id"])
    assert client.post(other + "/check", json={"ground_truth_raw": "x"}).status_code == 404
    with client.app.state.database.session_factory() as s:
        old = s.get(PipelineRun, run["id"])
        old.fields.clear()
        s.commit()
    assert client.get(f"/api/test-cases/{case['id']}").status_code == 200
    rerun = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": ["mint"]}).json()[
        "runs"
    ][0]
    assert rerun["fields"][0]["id"] != f["id"] and rerun["fields"][0]["ground_truth_raw"] is None
    assert client.delete(f"/api/test-cases/{case['id']}").status_code == 204
    with client.app.state.database.session_factory() as s:
        assert list(s.scalars(select(OCRField))) == []


@pytest.mark.parametrize("source", ["auto", "manual", "none"])
def test_explicit_roi_origin_pipeline_inputs(client, document, gateway, source):
    roi = dict(x1=40, y1=30, x2=270, y2=150)
    case = client.post(
        "/api/test-cases", json=dict(document_id=document["id"], roi=roi, roi_source=source)
    ).json()
    runs = client.post(
        f"/api/test-cases/{case['id']}/run",
        json={"pipelines": ["mint", "hutch_crop", "hutch_full", "benchmark"]},
    ).json()["runs"]
    assert all(r["status"] == "success" for r in runs)
    assert runs[0]["crop_sha256"] == runs[1]["crop_sha256"] == runs[3]["crop_sha256"]
    full = runs[2]
    assert (full["input_width"], full["input_height"]) == (
        (230, 120) if source == "manual" else (300, 200)
    )
    assert full["roi"] == (roi if source == "manual" else None)
    if source == "manual":
        assert full["crop_sha256"] == runs[0]["crop_sha256"]
    sent = [req for req in gateway[1] if req.url.path.endswith("/ocr-results")]
    sizes = []
    for req in sent:
        with Image.open(io.BytesIO(dict(parts(req))["image"])) as image:
            sizes.append(image.size)
    assert sizes == [(230, 120), (230, 120), (230, 120) if source == "manual" else (300, 200)]
    assert (
        client.put(
            f"/api/test-cases/{case['id']}/roi",
            json={"roi": roi, "roi_source": "manual" if source != "manual" else "auto"},
        ).status_code
        == 409
    )


def test_roi_source_validation_and_no_roi_full_page(client, document):
    assert (
        client.post(
            "/api/test-cases", json={"document_id": document["id"], "roi_source": "auto"}
        ).status_code
        == 422
    )
    case = client.post("/api/test-cases", json={"document_id": document["id"]}).json()
    run = client.post(
        f"/api/test-cases/{case['id']}/run", json={"pipelines": ["hutch_full"]}
    ).json()["runs"][0]
    assert run["input_width"] == 300 and run["roi"] is None


def test_reported_stale_dataset_source_and_recovery(client, case, document, png):
    client.put(
        f"/api/test-cases/{case['id']}/ground-truth",
        json={"ground_truth_raw": "ไทย\t label\nnext", "confirmed": True},
    )
    client.app.state.storage.delete(document["storage_key"])
    samples = client.get("/api/dataset/samples").json()["items"]
    assert samples[0]["source_available"] is False
    error = client.post("/api/dataset/export", json={"test_case_ids": [case["id"]]})
    assert (
        error.status_code == 409
        and case["id"] in error.json()["detail"]
        and "storage" in error.json()["detail"]
    )
    client.app.state.storage.put(document["storage_key"], png)
    assert client.get("/api/dataset/samples").json()["items"][0]["source_available"] is True
    result = client.post("/api/dataset/export", json={"test_case_ids": [case["id"]]})
    assert result.status_code == 200 and result.headers["content-type"] == "application/zip"
    with ZipFile(io.BytesIO(result.content)) as z:
        assert z.testzip() is None
        assert z.namelist() == ["dataset/images/000001.png", "dataset/label.txt"]
        assert z.read("dataset/label.txt").decode() == "images/000001.png\tไทย\\t label\\nnext\n"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Isolated PostgreSQL required")
def test_postgresql_field_roundtrip(tmp_path, png, gateway):
    settings = Settings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        storage_path=tmp_path,
        model_gateway_api_key="test-gateway-secret",
    )
    with TestClient(create_app(settings)) as c:
        doc = c.post("/api/documents", files={"file": ("field.png", png, "image/png")}).json()
        case = c.post(
            "/api/test-cases",
            json={
                "document_id": doc["id"],
                "roi": dict(x1=0, y1=0, x2=200, y2=100),
                "roi_source": "manual",
            },
        ).json()
        run = c.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": ["mint"]}).json()[
            "runs"
        ][0]
        field = run["fields"][0]
        url = f"/api/test-cases/{case['id']}/runs/{run['id']}/fields/{field['id']}/ground-truth"
        assert c.put(url, json={"ground_truth_raw": "ไทย", "confirmed": True}).status_code == 200
        saved = c.get(f"/api/test-cases/{case['id']}").json()
        assert (
            saved["roi_source"] == "manual"
            and saved["runs"][0]["fields"][0]["ground_truth_raw"] == "ไทย"
        )
