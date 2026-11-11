import asyncio
import gzip
import json
from decimal import Decimal
from tempfile import SpooledTemporaryFile

import httpx
import ijson
import pytest

from app.integrations.gateway_response import EnvelopeParser
from app.integrations.model_gateway import GatewayError, ModelGatewayClient, safe_response


def test_bounded_socket_transport_preserves_verified_tls_and_no_implicit_retries(settings):
    import socket
    import ssl

    async def inspect():
        async with ModelGatewayClient(settings)._client() as client:
            pool = client._transport._pool
            assert pool._ssl_context.verify_mode == ssl.CERT_REQUIRED
            assert pool._ssl_context.check_hostname
            assert pool._retries == 0
            assert pool._socket_options == [(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)]
            assert not client.follow_redirects and not client._trust_env
    asyncio.run(inspect())


def test_leaf_clients_reuse_verified_ca_store_without_reusing_connections(settings):
    import ssl

    async def inspect():
        gateway = ModelGatewayClient(settings)
        async with gateway._client() as first, gateway._client() as second:
            one, two = first._transport._pool, second._transport._pool
            assert one is not two
            assert one._ssl_context is two._ssl_context
            assert one._ssl_context.verify_mode == ssl.CERT_REQUIRED
            assert one._ssl_context.check_hostname
            assert one._ssl_context.cert_store_stats()['x509_ca'] > 0
            assert not first.follow_redirects and not second.follow_redirects
    asyncio.run(inspect())


def test_real_loopback_socket_is_bounded_and_large_response_bytes_are_unchanged(settings):
    import hashlib
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    body = b'{"data":{"text":"' + b'ABC123' * 500000 + b'"},"meta":{}}'

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def receive():
        digest = hashlib.sha256()
        async with ModelGatewayClient(settings)._client() as client:
            async with client.stream('GET', f'http://127.0.0.1:{server.server_port}/synthetic') as response:
                transport_socket = response.extensions['network_stream'].get_extra_info('socket')
                # Linux doubles SO_RCVBUF; platform accounting may differ.
                assert 0 < transport_socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF) <= 1024 * 1024
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    assert len(chunk) <= 65536
                    digest.update(chunk)
        assert digest.digest() == hashlib.sha256(body).digest()
    try:
        asyncio.run(receive())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def parse(body, size=7):
    parser = EnvelopeParser(lambda value: safe_response(value, ("private-secret",)))
    try:
        for offset in range(0, len(body), size):
            parser.feed(body[offset:offset + size])
        return parser.finish()
    finally:
        parser.close()


@pytest.mark.parametrize("payload", [
    {"data": {"text": "ก้ ก๊ ก๋ A 123", "score": .95001, "negative": -0.0,
              "huge_integer": 2 ** 100, "nested": [{"x": [1, 2, 3], "flag": True, "empty": None}]},
     "meta": {"request_id": "ours"}},
    {"data": {"image": [[1, 2]], "input_img": {"tensor": [1, 2]},
              "safe": "OCR private-secret", "nested": [{"api_token": "private-secret"}],
              "url": "data:image/png;base64,test"}, "meta": {"duration_ms": 10.1}},
    {"error": {"code": "UPSTREAM_MODEL_ERROR", "details": [{"type": "model_error"}],
               "request_id": "trace"}},
    {"data": {"contract_version": "leaf-inference-v1", "kind": "text_detection_batch",
              "count": 1, "raw_output": [{"dt_polys": [[[1, 2], [3, 4], [5, 6], [7, 8]]],
                                        "dt_scores": [.9], "input_img": [[1, 2]]}]}, "meta": {}},
])
def test_incremental_envelope_matches_original_sanitization(payload):
    body = json.dumps({**payload, "discarded_archive": {"tensor": [1.23] * 1000}}, ensure_ascii=False).encode()
    assert parse(body) == safe_response(payload, ("private-secret",))


def test_skipped_tensors_do_not_attach_but_are_still_validated():
    body = b'{"data":{"image":[' + b'1,' * 10000 + b'0],"text":"saved"},"meta":{}}'
    result = parse(body, 1024)
    assert result == {"data": {"image": "[redacted]", "text": "saved"}, "meta": {}}
    with pytest.raises(ijson.JSONError):
        parse(b'{"data":{},"meta":{},"discarded":[1, INVALID]}')


@pytest.mark.parametrize("body", [b'{"data":{', b'{"data":{},"meta":{}} trailing', b'{}{}', b'\xff'])
def test_malformed_or_incomplete_json_remains_invalid(body):
    with pytest.raises((ijson.JSONError, UnicodeDecodeError)):
        parse(body)


def test_number_types_and_duplicate_keys_match_json_contract():
    result = parse(b'{"data":{"x":1,"x":2,"f":0.12345678901234567,"overflow":1e999},"meta":{}}')
    assert result["data"] == {"x": 2, "f": 0.12345678901234567, "overflow": None}
    assert not any(isinstance(v, Decimal) for v in result["data"].values())


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks, self.reads, self.closed = chunks, 0, False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("declared", [True, False])
def test_oversized_response_stops_reading_and_closes(settings, monkeypatch, declared):
    settings.model_gateway_max_response_mb = 1
    stream = Stream([b'{"archive":"'] + [b'x' * 65536] * 32 + [b'"}'])
    headers = {"Content-Length": "2097166"} if declared else {}
    monkeypatch.setattr(ModelGatewayClient, "_client", lambda self: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, headers=headers, stream=stream))))
    client = ModelGatewayClient(settings)
    with pytest.raises(GatewayError) as exc:
        asyncio.run(client.send(client.build_batch_request(
            pngs=[b"png"], endpoint="/api/v1/text-recognition-batches", version=5, request_id="test")))
    assert exc.value.code == "RESPONSE_TOO_LARGE"
    assert stream.reads == 0 if declared else stream.reads < len(stream.chunks)
    assert stream.closed


def test_compressed_response_is_limited_by_decoded_bytes(settings, monkeypatch):
    settings.model_gateway_max_response_mb = 1
    encoded = gzip.compress(b'{"data":{"text":"' + b'x' * (2 * 1024 * 1024) + b'"},"meta":{}}')
    stream = Stream([encoded])
    monkeypatch.setattr(ModelGatewayClient, "_client", lambda self: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={
            "Content-Encoding": "gzip", "Content-Length": str(len(encoded))}, stream=stream))))
    client = ModelGatewayClient(settings)
    with pytest.raises(GatewayError) as exc:
        asyncio.run(client.send(client.build_batch_request(
            pngs=[b"png"], endpoint="/api/v1/text-recognition-batches", version=5, request_id="test")))
    assert exc.value.code == "RESPONSE_TOO_LARGE"
    assert stream.closed


@pytest.mark.parametrize("outcome", ["success", "invalid", "cancelled", "disk_full"])
def test_temporary_response_buffer_is_closed_on_every_exit(settings, monkeypatch, outcome):
    buffers = []

    def temporary(**kwargs):
        buffer = SpooledTemporaryFile(**kwargs)
        buffers.append(buffer)
        if outcome == "disk_full":
            buffer.write = lambda _: (_ for _ in ()).throw(OSError("private filesystem details"))
        return buffer

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"archive":"' + b'x' * 1200000
            if outcome == "cancelled":
                raise asyncio.CancelledError()
            yield b'", "data": {}, "meta": {}}' if outcome != "invalid" else b'INVALID}'

    monkeypatch.setattr("app.integrations.model_gateway.SpooledTemporaryFile", temporary)
    stream = Body()
    monkeypatch.setattr(ModelGatewayClient, "_client", lambda self: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))))
    client = ModelGatewayClient(settings)
    request = client.build_batch_request(pngs=[b"png"], endpoint="/api/v1/text-recognition-batches", version=5, request_id="test")
    if outcome == "success":
        assert asyncio.run(client.send(request)) == {"data": {}, "meta": {}}
    elif outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(client.send(request))
    else:
        with pytest.raises(GatewayError) as exc:
            asyncio.run(client.send(request))
        assert exc.value.code == ("RESPONSE_BUFFER_UNAVAILABLE" if outcome == "disk_full" else "INVALID_RESPONSE")
        assert "private filesystem" not in str(exc.value)
    assert buffers and all(buffer.closed for buffer in buffers)
    if outcome != "disk_full":
        assert buffers[0]._rolled  # Exercise the on-disk lifetime, not just the BytesIO path.
