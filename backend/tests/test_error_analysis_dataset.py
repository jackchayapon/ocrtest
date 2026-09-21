import io
import itertools
from zipfile import ZipFile

import pytest
from PIL import Image
from sqlalchemy import delete, func, select

from app.db.models import OCRErrorEvent, PipelineConfig
from app.services.metrics_service import (
    align_errors,
    error_breakdown,
    levenshtein,
    normalize_text,
    whitespace_tokenizer,
)
from tests.test_api import run


@pytest.mark.parametrize(
    "reference,prediction,kind",
    [
        ("abc", "abc", None),
        ("ก", "ค", "substitution"),
        ("ABCD", "ABD", "deletion"),
        ("ABD", "ABCD", "insertion"),
        ("", "ก", "insertion"),
        ("ก", "", "deletion"),
        ("", "", None),
        ("  e\u0301\r\n ก ", "é ก", None),
    ],
)
def test_alignment_matches_metrics(reference, prediction, kind):
    events = error_breakdown(prediction, reference)
    for level, tokenizer in (("char", list), ("word", whitespace_tokenizer)):
        aligned = [event for event in events if event["error_level"] == level]
        ref, pred = tokenizer(normalize_text(reference)), tokenizer(normalize_text(prediction))
        assert len(aligned) == levenshtein(ref, pred)
        for event in aligned:
            i, j = event["ground_truth_position"], event["ocr_position"]
            assert event["ground_truth_unit"] == (ref[i] if i is not None else None)
            assert event["ocr_unit"] == (pred[j] if j is not None else None)
    chars = [e for e in events if e["error_level"] == "char"]
    assert (chars[0]["error_type"] if chars else None) == kind


def test_alignment_exhaustive_ties_and_long_context():
    words = ["".join(t) for n in range(5) for t in itertools.product("ab", repeat=n)]
    for left, right in itertools.product(words, repeat=2):
        assert len(align_errors(left, right)) == levenshtein(left, right)
    events = align_errors("a" * 100000 + "ก", "a" * 100000 + "ค")
    assert len(events) == 1 and events[0]["ground_truth_position"] == 100000


def test_word_alignment_uses_existing_whitespace_tokens():
    for ref, pred, kind in [
        ("A B", "A C", "substitution"),
        ("A B C", "A C", "deletion"),
        ("A C", "A B C", "insertion"),
        ("บริษัท", "บริสัท", "substitution"),
    ]:
        words = [e for e in error_breakdown(pred, ref) if e["error_level"] == "word"]
        assert len(words) == 1 and words[0]["error_type"] == kind


def test_error_replacement_filters_latest_and_historical_recompute(client, case, document):
    runs = run(client, case)
    url = f"/api/test-cases/{case['id']}/ground-truth"
    for _ in range(2):
        assert (
            client.put(url, json={"ground_truth_raw": "ABC", "confirmed": True}).status_code == 200
        )
    params = dict(
        pipeline="mint", category="thai_text", test_case_id=case["id"], document=document["id"]
    )
    response = client.get("/api/analytics/errors", params=params)
    assert response.status_code == 200, response.text
    groups = response.json()["items"]
    assert sum(row["count"] for row in groups) == levenshtein(
        "ABC", normalize_text(runs[0]["final_text"])
    )
    assert all(
        row["test_case_count"] == 1 and row["cases"][0]["id"] == case["id"] for row in groups
    )
    assert (
        client.get("/api/analytics/errors", params={**params, "category": "blur"}).json()["total"]
        == 0
    )
    for kind in ("substitution", "deletion", "insertion"):
        rows = client.get("/api/analytics/errors", params={**params, "error_type": kind}).json()[
            "items"
        ]
        assert all(row["error_type"] == kind for row in rows)
    for level in ("char", "word"):
        for text_kind in ("raw", "final"):
            rows = client.get(
                "/api/analytics/errors",
                params={**params, "error_level": level, "text_kind": text_kind},
            ).json()["items"]
            tokenize = list if level == "char" else whitespace_tokenizer
            assert sum(row["count"] for row in rows) == levenshtein(
                tokenize("ABC"), tokenize(normalize_text(runs[0][f"{text_kind}_text"]))
            )
    run(client, case)  # Latest run only, never double count reruns.
    assert client.get("/api/analytics/errors", params=params).json()["items"] == groups
    with client.app.state.database.session_factory() as session:
        session.execute(delete(OCRErrorEvent))
        session.commit()
    assert client.get("/api/analytics/errors", params=params).json()["total"] == 0
    for _ in range(2):
        assert client.post(f"/api/test-cases/{case['id']}/errors/recompute").status_code == 200
        assert client.get("/api/analytics/errors", params=params).json()["items"] == groups
    assert client.delete(f"/api/test-cases/{case['id']}").status_code == 204
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OCRErrorEvent)) == 0


def confirm(client, case, text):
    assert (
        client.put(
            f"/api/test-cases/{case['id']}/ground-truth",
            json={"ground_truth_raw": text, "confirmed": True},
        ).status_code
        == 200
    )


def test_dataset_eligibility_export_pairing_escaping_and_source(client, case, document, png):
    assert client.get("/api/dataset/samples").json()["total"] == 0
    assert (
        client.post("/api/dataset/export", json={"test_case_ids": [case["id"]]}).status_code == 422
    )
    text = "บริษัท\tA\nB\rC\\n"
    confirm(client, case, text)
    other = client.post(
        "/api/test-cases",
        json={"document_id": document["id"], "roi": {"x1": 0, "y1": 0, "x2": 30, "y2": 20}},
    ).json()
    confirm(client, other, "other label")
    eligible = client.get(
        "/api/dataset/samples", params={"category": "thai_text", "document": document["id"]}
    ).json()
    assert eligible["total"] == 1 and eligible["items"][0]["ground_truth_raw"] == text
    ids = [case["id"], other["id"]]
    first = client.post("/api/dataset/export", json={"test_case_ids": ids})
    second = client.post("/api/dataset/export", json={"test_case_ids": ids[::-1]})
    assert first.status_code == 200, first.text if first.status_code != 200 else ""
    assert first.content == second.content and "no-store" in first.headers["cache-control"]
    with ZipFile(io.BytesIO(first.content)) as zip:
        assert len(zip.namelist()) == 3
        labels = zip.read("dataset/label.txt").decode("utf-8").splitlines()
        for index, (record, label) in enumerate(
            sorted(
                [(case, "บริษัท\\tA\\nB\\rC\\\\n"), (other, "other label")], key=lambda x: x[0]["id"]
            ),
            1,
        ):
            name = f"images/{index:06d}.png"
            assert labels[index - 1] == f"{name}\t{label}"
            with (
                Image.open(io.BytesIO(zip.read(f"dataset/{name}"))) as crop,
                Image.open(io.BytesIO(png)) as source,
            ):
                roi = record["roi"]
                expected = source.crop(tuple(roi[k] for k in ("x1", "y1", "x2", "y2")))
                assert crop.size == expected.size and crop.tobytes() == expected.tobytes()
    # Editing confirmed GT removes eligibility until confirmed again.
    client.put(f"/api/test-cases/{case['id']}/ground-truth", json={"ground_truth_raw": "changed"})
    assert client.post("/api/dataset/export", json={"test_case_ids": ids}).status_code == 422


def test_dataset_invalid_ids_missing_roi_and_missing_source(client, case, document):
    assert (
        client.post("/api/dataset/export", json={"test_case_ids": ["../../private"]}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/dataset/export", json={"test_case_ids": [case["id"], case["id"]]}
        ).status_code
        == 422
    )
    no_roi = client.post("/api/test-cases", json={"document_id": document["id"]}).json()
    confirm(client, no_roi, "label")
    assert (
        client.post("/api/dataset/export", json={"test_case_ids": [no_roi["id"]]}).status_code
        == 422
    )
    assert client.get("/api/dataset/samples").json()["total"] == 0
    confirm(client, case, "label")
    client.app.state.storage.delete(document["storage_key"])
    assert (
        client.post("/api/dataset/export", json={"test_case_ids": [case["id"]]}).status_code == 404
    )


def test_future_config_is_iterable_without_invented_adapter(client, case):
    with client.app.state.database.session_factory() as session:
        session.add(PipelineConfig(pipeline_id="future", name="Future", enabled=False))
        session.commit()
    assert len(client.get("/api/pipelines").json()) == 5
    response = client.post(
        f"/api/test-cases/{case['id']}/run",
        json={"pipelines": ["mint", "hutch_crop", "hutch_full", "future"]},
    )
    assert response.status_code == 200, response.text
    assert [r["status"] for r in response.json()["runs"]] == [
        "success",
        "success",
        "success",
        "error",
    ]
    assert response.json()["runs"][-1]["error_code"] == "ADAPTER_NOT_CONFIGURED"
    assert client.get("/api/matrix", params={"pipeline": "future"}).json()[0]["tests"] == 1


def test_dataset_pdf_selected_page_and_roi_edit_invalidates_confirmation(client):
    from tests.test_pdf import pdf_fixture

    doc = client.post(
        "/api/documents", files={"file": ("source.pdf", pdf_fixture(), "application/pdf")}
    ).json()
    roi = {"x1": 50, "y1": 60, "x2": 350, "y2": 460}
    case = client.post(
        "/api/test-cases", json={"document_id": doc["id"], "page_number": 2, "roi": roi}
    ).json()
    confirm(client, case, "page two")
    result = client.post("/api/dataset/export", json={"test_case_ids": [case["id"]]})
    assert result.status_code == 200
    full = client.get(f"/api/documents/{doc['id']}/pages/2/image")
    with (
        ZipFile(io.BytesIO(result.content)) as archive,
        Image.open(io.BytesIO(full.content)) as original,
    ):
        with Image.open(io.BytesIO(archive.read("dataset/images/000001.png"))) as crop:
            assert crop.size == (300, 400)
            assert crop.tobytes() == original.crop((50, 60, 350, 460)).tobytes()
    client.put(f"/api/test-cases/{case['id']}/roi", json={"roi": {**roi, "x1": 51}})
    assert client.get("/api/dataset/samples").json()["total"] == 0
