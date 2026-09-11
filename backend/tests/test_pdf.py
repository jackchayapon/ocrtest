import io
from hashlib import sha256

import httpx
import pytest
from PIL import Image

from app.core.errors import AppError
from app.services.pdf_service import PdfService
from tests.test_gateway_and_fairness import envelope, multipart


def pdf_fixture(pages=2, width=360, height=480):
    """Small, deterministic vector PDF; different dimensions/content on page two."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    kids = []
    for i in range(pages):
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        w, h = width + i * 72, height + i * 36
        content = f"0.2 0.3 {0.4 + i * 0.2} rg 30 50 200 100 re f\nBT /F1 18 Tf 30 220 Td (PDF PAGE {i + 1}) Tj ET".encode()
        objects.extend(
            [
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents {page_id + 1} 0 R >>".encode(),
                f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
            ]
        )
    objects[1] = f"<< /Type /Pages /Count {pages} /Kids [{' '.join(kids)}] >>".encode()
    result = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(result)
    result += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    result += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        result
        + f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )


@pytest.mark.parametrize("pages", [1, 2])
def test_pdf_upload_page_render_and_original_storage(client, pages):
    original = pdf_fixture(pages)
    upload = client.post(
        "/api/documents", files={"file": ("example.pdf", original, "application/pdf")}
    )
    assert upload.status_code == 201
    doc = upload.json()
    assert doc["document_type"] == "pdf" and doc["page_count"] == pages
    assert doc["pdf_render_dpi"] == 200 and doc["page_number"] == 1
    assert client.app.state.storage.read(doc["storage_key"]) == original
    assert doc["sha256"] == sha256(original).hexdigest()
    for number in range(1, pages + 1):
        image = client.get(f"/api/documents/{doc['id']}/pages/{number}/image")
        assert image.status_code == 200 and "no-store" in image.headers["cache-control"]
        metadata = client.get(f"/api/documents/{doc['id']}", params={"page_number": number}).json()
        with Image.open(io.BytesIO(image.content)) as raster:
            assert raster.size == (metadata["width"], metadata["height"])
        assert metadata["page_number"] == number
        assert (
            client.get(f"/api/documents/{doc['id']}/pages/{number}/image").content == image.content
        )
    assert len(list(client.app.state.storage.root.iterdir())) == 1, (
        "Only the original PDF is stored"
    )


def test_pdf_page_roi_persistence_and_three_real_adapter_contracts(client, gateway):
    behavior, calls = gateway
    doc = client.post(
        "/api/documents", files={"file": ("two.pdf", pdf_fixture(), "application/pdf")}
    ).json()
    # Page two is wider than page one; ROI validation must use page two's dimensions.
    roi = {"x1": 1050, "y1": 100, "x2": 1150, "y2": 250}
    response = client.post(
        "/api/test-cases",
        json={"document_id": doc["id"], "page_number": 2, "roi": roi, "ground_truth_raw": "ไทย"},
    )
    assert response.status_code == 201
    case = response.json()
    assert case["page_number"] == 2 and case["document"]["width"] == 1200
    assert client.get(f"/api/test-cases/{case['id']}").json()["page_number"] == 2
    behavior["handler"] = lambda request: httpx.Response(
        200, json=envelope(request.url.params["engine"])
    )
    pipelines = ["mint", "hutch_crop", "hutch_full"]
    runs = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": pipelines}).json()[
        "runs"
    ]
    assert [r["status"] for r in runs] == ["success", "success", "success"]
    assert runs[2]["input_width"] == 1200
    assert runs[2]["status"] == "success"
    assert runs[2]["input_sha256"] == sha256(client.get(f"/api/documents/{doc['id']}/pages/2/image").content).hexdigest()
    inputs = [multipart(request)["image"] for request in calls]
    assert inputs[0] == inputs[1]
    assert inputs[2] != inputs[0]
    assert inputs[2] == client.get(f"/api/documents/{doc['id']}/pages/2/image").content
    assert runs[2]["roi"] is None
    assert {r["crop_sha256"] for r in runs[:2]} == {sha256(inputs[0]).hexdigest()}
    assert {r["crop_width"] for r in runs[:2]} == {100}
    assert [r["crop_stage"] for r in runs] == ["app_crop", "app_crop", "full_image"]
    crop = client.get(f"/api/documents/{doc['id']}/crop", params={**roi, "page_number": 2})
    assert crop.content == inputs[0]
    for request in calls[1:]:
        assert multipart(request)["text_det_unclip_ratio"] == b"1.7"
    # Render DPI is pinned on upload, unaffected by later environment/config changes.
    client.app.state.settings.pdf_render_dpi = 100
    assert (
        client.get(f"/api/documents/{doc['id']}/crop", params={**roi, "page_number": 2}).content
        == inputs[0]
    )
    assert client.put(f"/api/test-cases/{case['id']}", json={"page_number": 1}).status_code == 422
    assert client.get("/api/history").json()[0]["page_number"] == 2


@pytest.mark.parametrize("number", [0, -1, 3, 1.5, True])
def test_pdf_invalid_page_number(client, number):
    doc = client.post(
        "/api/documents", files={"file": ("two.pdf", pdf_fixture(), "application/pdf")}
    ).json()
    assert (
        client.post(
            "/api/test-cases", json={"document_id": doc["id"], "page_number": number}
        ).status_code
        == 422
    )
    if type(number) is int:
        assert client.get(f"/api/documents/{doc['id']}/pages/{number}/image").status_code == 422


@pytest.mark.parametrize("data", [b"%PDF-broken", b"not a pdf", pdf_fixture(0)])
def test_pdf_invalid_or_empty(client, data):
    response = client.post(
        "/api/documents", files={"file": ("broken.pdf", data, "application/pdf")}
    )
    assert response.status_code in (415, 422)
    assert "PDF" in response.json()["detail"]
    assert not list(client.app.state.storage.root.iterdir())


def test_pdf_limits_password_and_render_errors(settings, monkeypatch):
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    service = PdfService(settings)
    settings.max_pdf_pages = 1
    with pytest.raises(AppError, match="จำนวนหน้า"):
        service.render(pdf_fixture(), 1)
    settings.max_pdf_pages = 500
    with pytest.raises(AppError, match="ขนาดหน้า"):
        service.render(pdf_fixture(1, width=100000), 1)
    with pytest.raises(AppError, match="ขนาดใหญ่"):
        service.render(b"%PDF-" + b" " * (settings.max_upload_mb * 1024 * 1024), 1)
    with monkeypatch.context() as scoped:
        scoped.setattr(raw, "FPDF_GetSecurityHandlerRevision", lambda doc: 4)
        with pytest.raises(AppError, match="รหัสผ่าน"):
            service.render(pdf_fixture(), 1)

    def fail(*args, **kwargs):
        raise pdfium.PdfiumError("private parser details", err_code=raw.FPDF_ERR_PASSWORD)

    with monkeypatch.context() as scoped:
        scoped.setattr(pdfium, "PdfDocument", fail)
        with pytest.raises(AppError, match="รหัสผ่าน"):
            service.render(pdf_fixture(), 1)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            pdfium.PdfPage,
            "render",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("private details")),
        )
        with pytest.raises(AppError, match="ไม่สามารถแสดง"):
            service.render(pdf_fixture(), 1)


def test_pdf_auto_roi_uses_selected_page_image(client, gateway):
    behavior, calls = gateway
    doc = client.post(
        "/api/documents", files={"file": ("two.pdf", pdf_fixture(), "application/pdf")}
    ).json()
    behavior["handler"] = lambda request: httpx.Response(
        200, json={"data": {"regions": [{"bbox_ratio": [0, 0, 1, 1]}]}, "meta": {}}
    )
    result = client.post(f"/api/documents/{doc['id']}/auto-rois", json={"page_number": 2}).json()
    assert result["regions"][0]["roi"]["x2"] == 1200
    assert (
        multipart(calls[0])["image"]
        == client.get(f"/api/documents/{doc['id']}/pages/2/image").content
    )
    assert "page_number" not in multipart(calls[0])


def test_image_cannot_have_pdf_page(client, png):
    doc = client.post("/api/documents", files={"file": ("image.png", png, "image/png")}).json()
    assert doc["page_count"] == 1 and doc["page_number"] is None
    assert (
        client.post(
            "/api/test-cases", json={"document_id": doc["id"], "page_number": 1}
        ).status_code
        == 422
    )
