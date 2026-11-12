"""Local-only browser entry point; no OpenThai or CDGS service is started."""
import httpx

from app.integrations.external_ocr import ExternalClient
from tests.e2e_app import app as app


def response(request):
    assert request.url.host == "shared-synthetic.invalid"
    if request.method == "GET":
        return httpx.Response(200, json={"status": "ready"})
    assert request.method == "POST" and request.headers["Authorization"] == "Bearer synthetic-browser-key"
    return httpx.Response(200, json={"text": "ไทย ABC", "confidence": 0.9})


ExternalClient.client = lambda self: httpx.AsyncClient(transport=httpx.MockTransport(response),
    trust_env=False, follow_redirects=False)
