import io
import json
from datetime import timedelta
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import event, func, select

from app.core.errors import AppError
from app.db.models import Document, GlobalField, OCRErrorEvent, OCRField, PipelineRun, now
from app.db.models import TestCase as Case
from app.services.character_statistics import character_identity, character_statistics
from app.services.field_service import compact_comparison
from app.services.metrics_service import character_text, levenshtein

SENTENCES = [
    "เจ้าหน้าที่เก็บเอกสารไว้บนโต๊ะ",
    "เดี๋ยวฉันจะซื้อตั๋วรถไฟ",
    "ก๋วยเตี๋ยวร้านเจ๊จิ๋มอร่อยมาก",
    "เด็กนักเรียนกำลังทำแบบฝึกหัด",
    "Please verify the applicant's information.",
    "Invoice No. INV-2026-001",
    "ยอดรวม Total Amount 1,250.50 บาท",
    "วันที่ ๐๗/๑๒/๒๕๖๙",
    "O0o๐ I1l S5 B8",
    "",
    "aaaaa aaaaa",
    "repeat repeat repeat",
    "line 1\nline 2",
    "Long paragraph ข้อความยาว " * 180,
]


@pytest.mark.parametrize("gt", SENTENCES)
@pytest.mark.parametrize("operation", ["same", "insert", "delete", "substitute"])
def test_canonical_counts(gt, operation):
    pred = gt
    if operation == "insert":
        pred += "X"
    elif operation == "delete":
        pred = gt[:-1]
    elif operation == "substitute":
        pred = ("X" + gt[1:]) if gt else "X"
    stats = character_statistics(pred, gt)
    assert (
        stats["substitution"] + stats["deletion"] + stats["insertion"] == stats["character_edits"]
    )
    assert sum(c["total"] for c in stats["characters"]) == stats["character_edits"]
    assert stats["character_edits"] == levenshtein(character_text(gt), character_text(pred))
    assert stats["character_edits"] == compact_comparison(pred, gt)["character_edits"]


@pytest.mark.parametrize("char", list("่้๊๋็์ัำิีึืุูกฮ๐๙Az09!?"))
def test_unicode_identity_and_attribution(char):
    missing = character_statistics("", char)
    extra = character_statistics(char, "")
    assert missing["characters"][0]["deletion"] == 1
    assert extra["characters"][0]["insertion"] == 1
    assert missing["characters"][0]["character"] == char
    assert character_identity(char)["code_point"] == f"U+{ord(char):04X}"


def test_nfc_and_single_substitution():
    assert character_statistics("é", "e\u0301")["character_edits"] == 0
    s = character_statistics("B", "A")
    assert s["characters"] == [
        dict(**character_identity("A"), total=1, substitution=1, deletion=0, insertion=0)
    ]
    assert s["confusion_pairs"] == [dict(expected="A", predicted="B", count=1)]


@pytest.fixture
def insights_case(client):
    with client.app.state.database.session_factory() as session:
        doc = Document(
            filename="synthetic-ไทย.png",
            mime_type="image/png",
            width=300,
            height=200,
            storage_key=str(uuid4()) + ".png",
        )
        case = Case(
            document=doc,
            workflow="global",
            evaluation_mode="per_field",
            status="confirmed",
            ground_truth_raw="ก้ A\nLine 2",
            document_gt_confirmed_at=now(),
        )
        g = GlobalField(
            field_index=1,
            roi=dict(x1=10, y1=20, x2=200, y2=100),
            source="manual",
            ground_truth_raw=case.ground_truth_raw,
            confirmed_at=now(),
        )
        case.global_fields = [g]
        session.add(case)
        session.flush()
        created = now() - timedelta(seconds=10)
        for index, (name, pred, archived) in enumerate([
            ("first", "OLD", False),
            ("first", "ก A\nLine 2", False),
            ("hidden", "ก้ B\nLine 2", False),
            ("archived", "BAD", True),
        ]):
            field = OCRField(
                global_field_id=g.id,
                field_index=1,
                geometry={},
                ocr_text=pred,
                ground_truth_raw=g.ground_truth_raw,
                confirmed_at=now(),
                status="success",
                evaluation=compact_comparison(pred, g.ground_truth_raw),
            )
            case.runs.append(
                PipelineRun(
                    created_at=created + timedelta(seconds=index),
                    pipeline_id=name,
                    pipeline_name=name,
                    status="success",
                    final_text=pred,
                    archived=archived,
                    confidence=0.9,
                    fields=[field],
                    document_evaluation=compact_comparison(pred, g.ground_truth_raw),
                    raw_response={"secret_sentinel": "never export", "blob": "x" * 30000},
                    boxes=[{"blob": "y" * 30000}],
                )
            )
            session.flush()
        session.commit()
        return case.id, g.id


def test_targeted_latest_read_only_details_and_export(client, insights_case):
    case_id, field_id = insights_case
    sqls = []

    def capture(conn, cursor, statement, *args):
        sqls.append(statement)

    engine = client.app.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(
            f"/api/test-cases/{case_id}/error-summary?pipeline_id=first&field_id={field_id}"
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    report = response.json()
    assert len(sqls) == 4
    assert not any("raw_response" in q or "diagnostics" in q or "boxes" in q for q in sqls)
    run = report["pipelines"][0]
    assert run["statistics"]["character_edits"] == 1
    assert run["statistics"]["characters"][0]["character"] == "้"
    assert run["scopes"][0]["details"][0]["line_number"] is None
    assert run["scopes"][0]["roi"] == dict(x1=10, y1=20, x2=200, y2=100)
    assert "ocr_text" not in run["scopes"][0]
    with client.app.state.database.session_factory() as session:
        before = session.scalar(select(func.count()).select_from(OCRErrorEvent))
    result = client.get(f"/api/test-cases/{case_id}/evaluation-report?mode=per_field")
    assert result.status_code == 200
    with ZipFile(io.BytesIO(result.content)) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {
            "summary.json",
            "pipeline_results.csv",
            "character_errors.csv",
            "error_details.json",
            "README.txt",
        }
        details = json.loads(archive.read("error_details.json"))
        assert {r["pipeline_id"] for r in details["pipelines"]} == {"first", "hidden"}
        assert all(r["statistics"]["character_edits"] == 1 for r in details["pipelines"])
        assert details["pipelines"][0]["scopes"][0]["confirmed_ground_truth"] == "ก้ A\nLine 2"
        assert b"secret_sentinel" not in result.content
        assert "never export" not in json.dumps(details)
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OCRErrorEvent)) == before
    whole = client.get(
        f"/api/test-cases/{case_id}/error-summary?pipeline_id=first&mode=whole_document"
    ).json()
    assert whole["pipelines"][0]["statistics"]["character_edits"] == 1
    assert len(whole["pipelines"][0]["scopes"]) == 1


def test_confirmation_stale_failed_and_cross_case_guards(client, insights_case):
    cid, gid = insights_case
    assert client.get(f"/api/test-cases/{cid}/error-summary?pipeline_id=missing").status_code == 404
    assert (
        client.get(
            f"/api/test-cases/{cid}/error-summary?pipeline_id=first&field_id={uuid4()}"
        ).status_code
        == 404
    )
    assert client.get("/api/test-cases/not-a-uuid/evaluation-report").status_code == 422
    with client.app.state.database.session_factory() as s:
        g = s.get(GlobalField, gid)
        g.ground_truth_raw = "Changed GT"
        s.commit()
    report = client.get(f"/api/test-cases/{cid}/error-summary?pipeline_id=first").json()
    assert report["pipelines"][0]["evaluated_scopes"] == 0
    assert not report["pipelines"][0]["statistics"]["characters"]
    with client.app.state.database.session_factory() as s:
        case = s.get(Case, cid)
        case.runs.append(
            PipelineRun(
                pipeline_id="first", pipeline_name="first", status="error", final_text="", fields=[]
            )
        )
        s.commit()
    assert (
        client.get(f"/api/test-cases/{cid}/error-summary?pipeline_id=first").json()["pipelines"][0][
            "status"
        ]
        == "error"
    )


def test_legacy_without_events_empty_prediction_and_formula_csv(client):
    from app.services.evaluation_insights_service import safe_csv

    with client.app.state.database.session_factory() as s:
        case = Case(
            document=Document(
                filename="legacy.png",
                mime_type="image/png",
                width=10,
                height=10,
                storage_key=str(uuid4()),
            ),
            workflow="legacy",
            ground_truth_raw="=ไทย",
            status="confirmed",
        )
        case.runs = [
            PipelineRun(
                pipeline_id="legacy", pipeline_name="=FORMULA", status="success", final_text=""
            )
        ]
        s.add(case)
        s.commit()
        cid = case.id
    r = client.get(f"/api/test-cases/{cid}/error-summary?pipeline_id=legacy")
    assert r.json()["pipelines"][0]["statistics"]["deletion"] == 4
    z = client.get(f"/api/test-cases/{cid}/evaluation-report")
    with ZipFile(io.BytesIO(z.content)) as a:
        assert "'=FORMULA" in a.read("pipeline_results.csv").decode("utf-8-sig")
    assert safe_csv(" \t=2+2").startswith("'")
    assert safe_csv("normal Thai ไทย") == "normal Thai ไทย"
    with pytest.raises(AppError):
        character_statistics("x" * 40001, "")


def test_compact_history_has_no_text_or_alignment(client, insights_case):
    case_id, _ = insights_case
    response = client.get("/api/history?view=summary&latest=true&compact=true")
    assert response.status_code == 200, response.text
    row = next(r for r in response.json() if r["id"] == case_id)
    assert row["history_status"] == "success"
    assert row["has_ground_truth"] is True
    assert len(row["runs"]) == 2
    assert row["global_fields"][0]["confirmed_at"]
    assert not any(
        key in response.text
        for key in (
            "ocr_text",
            "ground_truth_raw",
            "diagnostics",
            "evaluation",
            "boxes",
            "secret_sentinel",
        )
    )
    # Backward-compatible opt-in: other summary clients still receive their old shape.
    normal = client.get("/api/history?view=summary&latest=true").json()
    assert next(r for r in normal if r["id"] == case_id)["ground_truth_raw"]


def test_compact_history_null_evaluation_and_field_projection(client, insights_case):
    cid, gid = insights_case
    with client.app.state.database.session_factory() as session:
        case = session.get(Case, cid)
        for run in case.runs:
            run.document_evaluation = None
            for field in run.fields:
                field.evaluation = None
        session.commit()
    compact = client.get("/api/history?view=summary&latest=true&compact=true").json()
    assert next(c for c in compact if c["id"] == cid)["history_status"] == "no_gt"
    queries = []

    def capture(conn, cursor, statement, *args):
        queries.append(statement)

    engine = client.app.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(
            f"/api/test-cases/{cid}/error-summary?pipeline_id=first&field_id={gid}"
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert not any(
        "pipeline_runs.final_text" in q or "test_cases.ground_truth_raw" in q for q in queries
    )
    assert response.json()["pipelines"][0]["scopes"][0]["state"] == "outdated"

def test_export_retains_confirmed_text_when_alignment_unavailable(client, insights_case):
    cid, _ = insights_case
    with client.app.state.database.session_factory() as session:
        case = session.get(Case, cid)
        for run in case.runs:
            for field in run.fields:
                field.confidence = 0.42
                field.evaluation = None
        session.commit()
    response = client.get(f"/api/test-cases/{cid}/evaluation-report")
    assert response.status_code == 200
    with ZipFile(io.BytesIO(response.content)) as archive:
        report = json.loads(archive.read("error_details.json"))
        scope = report["pipelines"][0]["scopes"][0]
        assert scope["state"] == "outdated"
        assert scope["confirmed_ground_truth"]
        assert scope["ocr_text"]
        assert scope["confidence"] == 0.42
        assert report["pipelines"][0]["confidence"] == 0.9
        assert scope["metrics"] is None
