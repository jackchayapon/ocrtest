import asyncio
import gc
import weakref

import pytest

from app.integrations.batch_gateway import BatchGateway
from app.integrations.model_gateway import GatewayError


@pytest.mark.parametrize('failure', [False, True])
def test_finished_batch_upload_owners_are_released_without_cyclic_gc(failure):
    class Owner:
        pass

    class Gateway:
        async def send(self, request):
            if failure:
                raise GatewayError('synthetic', 'HTTP_503', 'upstream-id', 503,
                                   details=[{'code': 'SAFE_CODE'}], retry_after=.75)
            return {'data': {'count': 1, 'results': [{'rec_text': 'ทดสอบ', 'rec_score': .9}]},
                    'meta': {'request_id': 'upstream-id', 'duration_ms': 1}}

    async def exercise():
        batch, references = BatchGateway(1), []
        for _ in range(20):
            owner = Owner()
            references.append(weakref.ref(owner))
            request = {'url': 'http://synthetic.invalid', 'params': {}, 'headers': {},
                       'files': [('images', ('synthetic.png', owner, 'image/png'))]}
            if failure:
                with pytest.raises(GatewayError) as raised:
                    await batch.send(Gateway(), request)
                assert (raised.value.code, raised.value.request_id, raised.value.http_status) == ('HTTP_503', 'upstream-id', 503)
                assert raised.value.details == [{'code': 'SAFE_CODE'}] and raised.value.retry_after == .75
                del raised
            else:
                result = await batch.send(Gateway(), request)
                assert result['data']['results'][0]['rec_text'] == 'ทดสอบ'
                assert result['meta']['request_id'] == 'upstream-id'
                del result
            del owner, request
        # Allow already-scheduled completion callbacks to finish; no GC or
        # artificial inference delay is needed to release completed uploads.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not batch.pending
        assert all(reference() is None for reference in references)

    enabled = gc.isenabled()
    gc.disable()
    try:
        asyncio.run(exercise())
    finally:
        if enabled:
            gc.enable()
