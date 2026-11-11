import asyncio
import io
from uuid import uuid4

import pytest
from PIL import Image

from app.core.config import WORKLOAD_LIMITS, Settings
from app.core.errors import AppError
from app.core.workload import WorkloadGuard
from app.db.models import OCRJob
from app.pipelines.benchmark import BenchmarkPipelineAdapter
from app.services.image_service import ImageService
from app.services.ocr_jobs import enqueue
from app.services.pdf_service import PdfService
from app.services.test_case_service import TestCaseService as CaseService
from tests.test_ocr_jobs import pipeline
from tests.test_pdf import pdf_fixture


def encoded(size):
    with Image.new("RGB", size, "white") as image, io.BytesIO() as buffer:
        image.save(buffer, "PNG")
        return buffer.getvalue()


def test_old_environment_cannot_expand_release_ceiling(monkeypatch):
    for key in WORKLOAD_LIMITS:
        monkeypatch.setenv(key.upper(), str(8 if "concurrent" in key else
                                         30 if key == "ocr_gateway_batch_size" else
                                         64 if key == "model_gateway_max_response_mb" else
                                         20 if key == "max_upload_mb" else
                                         500 if key == "max_pdf_pages" else 40_000_000))
    settings = Settings(_env_file=None)
    assert {key: getattr(settings, key) for key in WORKLOAD_LIMITS} == WORKLOAD_LIMITS
    assert Settings(_env_file=None, max_image_pixels=100).max_image_pixels == 100


@pytest.mark.parametrize("entry", ["upload", "open", "inspect"])
def test_40mp_rejected_before_decode(settings, monkeypatch, entry):
    # Header-only compressed fixture; load is forbidden after the fixture is prepared.
    data = encoded((8000, 5000))
    monkeypatch.setattr(Image.Image, "load", lambda *_a, **_k: pytest.fail("decoded rejected image"))
    images = ImageService(settings)
    with pytest.raises(AppError) as error:
        if entry == "upload":
            images.decode_upload(data, "image/png")
        else:
            getattr(images, entry)(data)
    assert error.value.status_code == 413


def test_boundary_and_no_implicit_resize(settings):
    data = encoded((1000, 2000))
    png, width, height = ImageService(settings).decode_upload(data, "image/png")
    assert (width, height) == (1000, 2000)
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == (1000, 2000)


def test_pdf_rejected_before_bitmap_and_page_count(settings, monkeypatch):
    import pypdfium2 as pdfium
    monkeypatch.setattr(pdfium.PdfPage, "render", lambda *_a, **_k: pytest.fail("rasterized rejected PDF"))
    for data in (pdf_fixture(1, width=5000), pdf_fixture(21)):
        with pytest.raises(AppError) as error:
            PdfService(settings).render(data, 1)
        assert error.value.status_code == 413
    assert PdfService(settings).render(pdf_fixture(1), 1, validate_only=True) is None


def test_old_source_reprocessing_rejected_without_losing_history(client, document, case, monkeypatch):
    storage = client.app.state.storage
    storage.put(document["storage_key"], encoded((8000, 5000)))
    monkeypatch.setattr(storage, "read_bounded", lambda *_a, **_k: pytest.fail("read complete rejected source"))
    assert client.get(f"/api/test-cases/{case['id']}/results").status_code == 200
    assert client.get(f"/api/documents/{document['id']}").status_code == 200
    assert client.get(f"/api/documents/{document['id']}/crop?x1=0&y1=0&x2=20&y2=20").status_code == 413
    pid = pipeline(client)
    response = client.post(f"/api/test-cases/{case['id']}/jobs", json={
        "pipelines": [pid], "idempotency_key": str(uuid4())})
    assert response.status_code == 413
    with client.app.state.database.session_factory() as session:
        from sqlalchemy import func, select
        assert session.scalar(select(func.count()).select_from(OCRJob)) == 0
    assert storage.exists(document["storage_key"])


def test_queue_full_preserves_idempotency(client, case):
    pid = pipeline(client)
    cases_data = [case] + [client.post("/api/test-cases", json={
        "document_id": case["document_id"]}).json() for _ in range(4)]
    with client.app.state.database.session_factory() as session:
        for i in range(5):
            # Deliberately paused queued state; no worker wake is issued.
            session.add(OCRJob(test_case_id=cases_data[i]["id"], idempotency_key=str(i),
                               pipeline_ids=[pid], config_snapshot=[], status="queued",
                               total_fields=1, total_pipelines=1))
        session.commit()
        cases = CaseService(session, client.app.state.settings, client.app.state.storage)
        assert enqueue(cases, case["id"], [pid], "0").idempotency_key == "0"
        # A distinct case must not add a sixth active entry.
        other = client.post("/api/test-cases", json={"document_id": case["document_id"]}).json()
        with pytest.raises(AppError) as error:
            enqueue(cases, other["id"], [pid], "new")
        assert error.value.status_code == 429


def test_large_line_batches_bounded_without_dropping_or_reordering(settings):
    from tests.test_benchmark_pipeline import config
    adapter = BenchmarkPipelineAdapter(config(), settings)
    page = [[0, 0], [4000, 0], [4000, 2000], [0, 2000]]
    tiny = [[0, 0], [20, 0], [20, 10], [0, 10]]
    polygons = [page] * 3 + [tiny] * 31
    batches = list(adapter.line_batches(polygons))
    assert [len(batch) for batch in batches] == [1, 1, 1, 30, 1]
    assert [p for batch in batches for p in batch] == polygons


def test_guard_bounded_requests_polling_and_release(settings):
    async def scenario():
        lock, started, finish = asyncio.Lock(), asyncio.Event(), asyncio.Event()
        calls = []

        async def app(scope, receive, send):
            calls.append(scope["path"])
            if scope["path"] == "/api/documents":
                started.set()
                await finish.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        guard = WorkloadGuard(app, lock, settings)

        async def invoke(path, headers=()):
            messages = []
            async def send(message):
                messages.append(message)
            async def receive():
                return {"type": "http.request", "body": b""}
            await guard({"type": "http", "path": path, "method": "POST", "headers": headers}, receive, send)
            return messages[0]["status"]

        first = asyncio.create_task(invoke("/api/documents"))
        await started.wait()
        second = asyncio.create_task(invoke("/api/documents"))
        await asyncio.sleep(.01)
        assert await invoke("/api/documents") == 429
        assert await invoke("/api/ocr-jobs/read-only/results") == 200
        finish.set()
        assert await first == await second == 200 and not lock.locked()
        assert await invoke("/api/documents", [(b"content-length", b"999999999")]) == 413
        assert calls.count("/api/documents") == 2
    asyncio.run(scenario())


def test_policy_visible(client):
    value = client.get("/api/upload-config").json()
    assert value["max_image_pixels"] == 2_000_000
    assert value["max_upload_mb"] == 10 and value["max_pdf_pages"] == 20
    assert value["ocr_active_jobs"] == value["ocr_max_concurrent_tasks"] == 1
    assert value["ocr_queue_capacity"] == 5
    assert value["max_job_fields"] == 80 and value["max_job_pipelines"] == 3
    assert value["max_job_units"] == 240


def test_new_job_limits_preserve_historical_state():
    from types import SimpleNamespace

    from pydantic import ValidationError

    from app.schemas.contracts import RunRequest
    with pytest.raises(ValidationError):
        RunRequest(pipelines=[f"p{i}" for i in range(4)])
    historical = SimpleNamespace(workflow="global", global_fields=[object()] * 81)
    with pytest.raises(AppError) as error:
        CaseService.validate_workload(historical, ["p1"])
    assert error.value.status_code == 413
    assert len(historical.global_fields) == 81


def test_guard_releases_slot_after_cancellation(settings):
    async def scenario():
        lock, started = asyncio.Lock(), asyncio.Event()
        async def app(scope, receive, send):
            started.set()
            await asyncio.Event().wait()
        async def receive():
            return {"type": "http.request", "body": b""}
        async def send(message):
            pass
        guard = WorkloadGuard(app, lock, settings)
        task = asyncio.create_task(guard({"type": "http", "path": "/api/documents",
                                         "method": "POST", "headers": []}, receive, send))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not lock.locked() and guard.waiters[lock] == 0
    asyncio.run(scenario())


def test_default_pdf_a4_raster_is_explicit_and_bounded():
    settings = Settings(_env_file=None)
    assert settings.pdf_render_dpi == 140
    page = PdfService(settings).render(pdf_fixture(1, width=595, height=842), 1)
    assert (page.width, page.height) == (1157, 1638)
    assert page.width * page.height <= settings.max_image_pixels


def test_product_budget_accepts_eighty_fields_three_pipelines_and_rejects_excess():
    from types import SimpleNamespace
    case = SimpleNamespace(workflow="global", global_fields=[object()] * 80)
    CaseService.validate_workload(case, ["one", "two", "three"])
    with pytest.raises(AppError) as error:
        CaseService.validate_workload(case, ["one", "two", "three", "four"])
    assert error.value.status_code == 413 and "3 Pipelines" in error.value.message
    case.global_fields.append(object())
    with pytest.raises(AppError) as error:
        CaseService.validate_workload(case, ["one"])
    assert error.value.status_code == 413 and "80 Fields" in error.value.message


@pytest.mark.parametrize("regions", [128, 129, 256])
def test_detection_limit_accepts_all_supported_lines_or_rejects_without_rec(settings, monkeypatch, regions):
    from app.integrations.model_gateway import GatewayError
    from tests.test_benchmark_pipeline import config
    images = ImageService(settings)
    sent = []

    async def send(request):
        sent.append(request)
        if len(sent) == 1:
            return {"data": {"kind": "text_detection_batch", "contract_version": "leaf-inference-v1", "count": 1,
                             "result": {"results": [{"dt_polys": [[[0, 0], [20, 0], [20, 10], [0, 10]]] * regions,
                                                     "dt_scores": [.9] * regions}]}}, "meta": {}}
        return {"data": {"count": len(request["files"]), "results": [{"text": "line", "confidence": .9} for _ in request["files"]]}, "meta": {}}

    adapter = BenchmarkPipelineAdapter(config(), settings)
    monkeypatch.setattr(adapter.gateway, "send", send)
    with Image.new("RGB", (40, 30), "white") as original:
        crop = images.canonical_crop(original, None)
        if regions <= 128:
            result = asyncio.run(adapter.run(original_image=original, cropped_image=crop))
            assert len(result.boxes) == regions and result.final_text.splitlines() == ["line"] * regions
        else:
            with pytest.raises(GatewayError) as error:
                asyncio.run(adapter.run(original_image=original, cropped_image=crop))
            assert error.value.code == "INVALID_OCR_RESPONSE" and len(sent) == 1


def test_recognition_text_limit_rejects_instead_of_truncating():
    from app.integrations.model_gateway import GatewayError
    from app.pipelines.normalizers import bounded_text
    text = "ก" * 32768
    assert bounded_text(text) == text
    with pytest.raises(GatewayError) as error:
        bounded_text(text + "ก")
    assert error.value.code == "INVALID_OCR_RESPONSE"
