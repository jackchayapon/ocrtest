"""Preview/upload contention with local synthetic sources; no model requests."""
import asyncio
import io
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import func, select
from starlette.requests import ClientDisconnect

from app.db.models import Document
from app.services.pdf_service import PdfService
from app.services.preview_service import CACHE_BYTES, PreviewResponse, PreviewService
from tests.test_pdf import pdf_fixture


def test_png_read_survives_worker_lock_without_decode(client, document, monkeypatch, gateway):
    expected = client.app.state.storage.read(document['storage_key'])
    lock = client.app.state.image_lock
    client.portal.call(lock.acquire)
    monkeypatch.setattr(Image.Image, 'load', lambda *_a, **_k: pytest.fail('decoded a stored preview'))
    try:
        result = client.get(document['image_url'])
        assert result.status_code == 200 and result.content == expected
        assert client.get('/api/documents/'+document['id']).status_code == 200
        assert lock.locked()
        assert client.get('/api/documents/'+document['id']+'/crop?x1=0&y1=0&x2=10&y2=10').status_code == 429
    finally:
        client.portal.call(lock.release)
    assert gateway[1] == []


def test_pdf_cache_keeps_exact_selected_page_during_worker_and_missing_source_is_404(client, monkeypatch, gateway):
    data = pdf_fixture(3, width=200, height=250)
    doc = client.post('/api/documents', files={'file':('synthetic.pdf',data,'application/pdf')}).json()
    url = f"/api/documents/{doc['id']}/pages/2/image"
    expected = PdfService(client.app.state.settings).render(data, 2, doc['pdf_render_dpi'])
    prime = client.get(url)
    assert prime.status_code == 200 and prime.content == expected.png
    client.portal.call(client.app.state.image_lock.acquire)
    monkeypatch.setattr(PdfService, 'render', lambda *_a, **_k: pytest.fail('rasterized during active OCR'))
    try:
        response = client.get(url)
        assert response.status_code == 200 and response.content == expected.png
        metadata = client.get(f"/api/documents/{doc['id']}?page_number=2")
        assert metadata.status_code == 200
        assert (metadata.json()['width'], metadata.json()['height']) == (expected.width, expected.height)
        assert metadata.json()['page_number'] == 2
        uncached = client.get(f"/api/documents/{doc['id']}/pages/3/image")
        assert uncached.status_code == 429 and uncached.headers['Retry-After'] == '5'
        client.app.state.storage.delete(doc['storage_key'])
        assert client.get(url).status_code == 404
    finally:
        client.portal.call(client.app.state.image_lock.release)
    assert gateway[1] == []


def test_upload_rejection_is_explicitly_safe_and_never_creates_document(client, png, gateway):
    def count():
        with client.app.state.database.session_factory() as session:
            return session.scalar(select(func.count()).select_from(Document))
    before = count()
    client.portal.call(client.app.state.image_lock.acquire)
    try:
        rejected = client.post('/api/documents', files={'file':('synthetic.png',png,'image/png')},
                               headers={'Origin':'http://localhost:3000'})
        assert rejected.status_code == 429 and count() == before
        assert rejected.headers['Retry-After'] == '5'
        assert rejected.headers['X-OCRLab-Retry-Safe'] == 'pre-admission'
        assert 'X-OCRLab-Retry-Safe' in rejected.headers['Access-Control-Expose-Headers']
    finally:
        client.portal.call(client.app.state.image_lock.release)
    assert client.post('/api/documents', files={'file':('synthetic.png',png,'image/png')}).status_code == 201
    assert count() == before+1 and gateway[1] == []


def test_disposable_preview_cache_is_bounded_and_does_not_modify_source(tmp_path):
    original = tmp_path/'original.pdf'
    original.write_bytes(b'owned original')
    previews = PreviewService(SimpleNamespace(storage=SimpleNamespace(root=tmp_path)))
    for index in range(20):
        previews.store(tmp_path/'.preview-cache'/f'{index:064x}.png', b'x'*(512*1024))
    files = list((tmp_path/'.preview-cache').glob('*.png'))
    assert len(files) <= 16 and sum(p.stat().st_size for p in files) <= CACHE_BYTES
    assert original.read_bytes() == b'owned original'


def test_stream_disconnect_closes_source_and_releases_preview_lock():
    async def run():
        source, lock = io.BytesIO(b'x'*150000), asyncio.Lock()
        response = PreviewResponse(source, lock)
        async def send(message):
            if message['type'] == 'http.response.body':
                assert len(message['body']) <= 65536
                raise OSError('synthetic disconnect')
        async def receive():
            return {'type':'http.request','body':b''}
        with pytest.raises(ClientDisconnect):
            await response({'type':'http','asgi':{'spec_version':'2.4'}}, receive, send)
        assert source.closed and not lock.locked()
    asyncio.run(run())


def test_unwritable_optional_cache_does_not_modify_source(tmp_path, monkeypatch):
    import app.services.preview_service as module
    original = tmp_path/'source.pdf'
    original.write_bytes(b'owned source')
    previews = PreviewService(SimpleNamespace(storage=SimpleNamespace(root=tmp_path)))
    def failed_write(*_a, **_kw):
        raise OSError('synthetic disk full')
    monkeypatch.setattr(module, 'NamedTemporaryFile', failed_write)
    previews.store(tmp_path/'.preview-cache'/'page.png', b'preview')
    assert original.read_bytes() == b'owned source'
    assert not list((tmp_path/'.preview-cache').iterdir())
