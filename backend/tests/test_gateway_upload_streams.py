import asyncio
from hashlib import sha256
from io import BytesIO

import httpx
import pytest

from app.integrations import model_gateway
from app.integrations.model_gateway import GatewayError, ModelGatewayClient


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("failure", [None, "connection", "cancel"])
def test_upload_chunks_preserve_exact_wire_contract_and_close_owned_files(settings, monkeypatch, batch, failure):
    owned = []
    class Owned(BytesIO):
        def __init__(self, value):
            super().__init__(value)
            owned.append(self)
    monkeypatch.setattr(model_gateway, "BytesIO", Owned)
    gateway = ModelGatewayClient(settings)
    blob = b"synthetic lossless input\0" * 50000
    request = (gateway.build_batch_request(pngs=[blob, blob], endpoint="/api/v1/text-detection-batches",
                                          version=6, request_id="upload-test") if batch
               else gateway.build_request(png=blob, endpoint="/api/v1/ocr-results", query_params={"engine":"custom"},
                                          fields={"threshold":.25}, request_id="upload-test"))
    request["headers"]["Content-Type"] = "multipart/form-data; boundary=ocrlab-fixed-boundary"
    expected = httpx.Request(**request)
    reference = b"".join(expected.stream)
    chunks = []
    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, incoming):
            digest = sha256()
            size = 0
            async for chunk in incoming.stream:
                chunks.append(len(chunk))
                digest.update(chunk)
                size += len(chunk)
            assert digest.digest() == sha256(reference).digest()
            assert size == len(reference) == int(incoming.headers["Content-Length"])
            assert incoming.url.query == expected.url.query
            assert not any(stream.closed for stream in owned)
            if failure == "connection":
                raise httpx.ReadError("synthetic disconnect")
            if failure == "cancel":
                raise asyncio.CancelledError()
            return httpx.Response(200,json={"data":{"text":"synthetic"},"meta":{}})
    monkeypatch.setattr(gateway,"_client",lambda: httpx.AsyncClient(transport=Transport()))
    if failure:
        with pytest.raises(asyncio.CancelledError if failure=="cancel" else GatewayError):
            asyncio.run(gateway.send(request))
    else:
        assert asyncio.run(gateway.send(request))["data"]["text"] == "synthetic"
    assert max(chunks) <= 65536
    assert len(owned) == (2 if batch else 1) and all(stream.closed for stream in owned)
    files = list(request["files"].values()) if not batch else [part for _,part in request["files"]]
    assert all(part[1] is blob for part in files)  # Original requests remain retryable.


def test_stream_helper_keeps_caller_owned_handles_open():
    from contextlib import ExitStack
    external = BytesIO(b"synthetic")
    request = {"files":{"image":("crop.png",external,"image/png")}}
    with ExitStack() as scope:
        streamed = model_gateway.streamed_uploads(request,scope)
        assert streamed["files"]["image"][1] is external
    assert not external.closed
    external.close()
