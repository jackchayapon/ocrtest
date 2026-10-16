"""Combine concurrent leaf requests, then restore each caller's ordered result slice."""
import asyncio
from copy import deepcopy
import json
from uuid import uuid4

from app.integrations.model_gateway import GatewayError
from app.core.batching import IMAGE_BATCH_SIZE


class BatchGateway:
    def __init__(self):
        self.pending = {}

    async def send(self, gateway, request):
        files = request.get("files")
        if not isinstance(files, list) or not files or any(key != "images" for key, _ in files):
            return await gateway.send(request)
        key = (request["url"], json.dumps(request.get("params", {}), sort_keys=True))
        future = asyncio.get_running_loop().create_future()
        if key not in self.pending:
            self.pending[key] = []
            asyncio.get_running_loop().call_soon(lambda: asyncio.create_task(self.flush(key)))
        self.pending[key].append((gateway, request, future))
        return await future

    async def flush(self, key):
        entries = self.pending.pop(key)
        try:
            # Bound each upstream request even when each ROI contains many REC crops.
            flat = [(entry, part) for entry, (_, request, _) in enumerate(entries) for part in request["files"]]
            collected = [[] for _ in entries]
            template = None
            request_ids = [[] for _ in entries]
            duration = 0
            duration_known = True
            for start in range(0, len(flat), IMAGE_BATCH_SIZE):
                chunk = flat[start:start + IMAGE_BATCH_SIZE]
                request = dict(entries[0][1])
                request["headers"] = {**request["headers"], "X-Request-ID": f"batch_{uuid4().hex}"}
                request["files"] = [("images", (f"crop-{i}.png", part[1][1], part[1][2])) for i, (_, part) in enumerate(chunk)]
                response = await entries[0][0].send(request)
                upstream_id = response.get("meta", {}).get("request_id") or request["headers"]["X-Request-ID"]
                for owner in {owner for owner, _ in chunk}:
                    request_ids[owner].append(upstream_id)
                data = response.get("data", {})
                if not isinstance(data, dict):
                    raise GatewayError("Invalid batch response data", "INVALID_OCR_RESPONSE")
                nested = isinstance(data.get("result"), dict)
                items = data["result"].get("results") if nested else data.get("results")
                if not isinstance(items, list) or len(items) != len(chunk) or data.get("count") != len(chunk):
                    raise GatewayError("Batch result count does not match input images", "INVALID_OCR_RESPONSE")
                template = response
                value = response.get("meta", {}).get("duration_ms")
                if isinstance(value, (int, float)) and value >= 0:
                    duration += value
                else:
                    duration_known = False
                for (owner, _), item in zip(chunk, items):
                    collected[owner].append(item)
            for index, (_, _, future) in enumerate(entries):
                response = deepcopy(template)
                data = response["data"]
                data["count"] = len(collected[index])
                if isinstance(data.get("result"), dict):
                    data["result"]["results"] = collected[index]
                # Leaf adapters expose aliases of the same result list. REC reads
                # the top-level alias; leaving it unsliced breaks multi-image calls.
                data["results"] = collected[index]
                if "predictions" in data:
                    data["predictions"] = collected[index]
                response["meta"]["duration_ms"] = duration / len(entries) if duration_known else None
                response["meta"]["combined_input_count"] = len(flat)
                response["meta"]["batch_request_ids"] = request_ids[index]
                response["meta"]["request_id"] = request_ids[index][0]
                if not future.done():
                    future.set_result(response)
        except Exception as error:
            for _, _, future in entries:
                if not future.done():
                    future.set_exception(error)


class BatchingClient:
    def __init__(self, gateway, batches):
        self.gateway, self.batches = gateway, batches

    def __getattr__(self, name):
        return getattr(self.gateway, name)

    async def send(self, request):
        return await self.batches.send(self.gateway, request)
