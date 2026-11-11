import asyncio
import json

import pytest
from starlette.responses import JSONResponse

from app.services import json_response


def test_large_json_is_complete_byte_equivalent_bounded_without_whole_body_buffer():
    value = {"fields": [{"text": 'กิ่ "\\\n ABC 123 ' * 3000, "index": i} for i in range(80)]}
    response = json_response.bounded_json_response(value)
    assert not hasattr(response, 'body')
    chunks = []

    async def consume():
        async for chunk in response.body_iterator:
            assert len(chunk) <= 65536
            chunks.append(chunk)
    asyncio.run(consume())
    body = b"".join(chunks)
    assert body == JSONResponse(value).body
    assert json.loads(body) == value
    assert int(response.headers["content-length"]) == len(body)
    assert response.body_iterator.ag_frame is None


def test_invalid_json_fails_before_success_headers_are_created():
    with pytest.raises(ValueError):
        json_response.bounded_json_response({'text': 'x' * 600000, 'bad': float('nan')})


@pytest.mark.parametrize('after_first_body', [False, True])
def test_disconnect_closes_encoder_even_before_first_chunk(after_first_body):
    from starlette.requests import ClientDisconnect
    response = json_response.bounded_json_response({'text': 'ก' * 600000})

    async def send(message):
        if message['type'] == ('http.response.body' if after_first_body else 'http.response.start'):
            raise OSError('synthetic disconnected client')

    async def receive():
        return {'type': 'http.disconnect'}
    with pytest.raises(ClientDisconnect):
        asyncio.run(response({'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, send))
    assert response.body_iterator.ag_frame is None


def test_queue_capacity_429_has_bounded_retry_hint(client, document):
    from tests.test_global_layout import layout
    from tests.test_ocr_jobs import paused_worker, pipeline
    pid = pipeline(client)
    _, create = paused_worker(client)
    cases = [layout(client, document)[0] for _ in range(6)]
    for case in cases[:5]:
        create(case, [pid])
    response = client.post('/api/test-cases/'+cases[5]['id']+'/jobs',
                           json={'pipelines': [pid], 'idempotency_key': 'sixth'})
    assert response.status_code == 429 and response.headers['retry-after'] == '5'
