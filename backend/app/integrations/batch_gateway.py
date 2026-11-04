"""Combine concurrent leaf requests, then restore each caller's ordered result slice."""
import asyncio
import json
from copy import deepcopy
from uuid import uuid4

from app.core.batching import IMAGE_BATCH_SIZE
from app.integrations.model_gateway import GatewayError


class BatchGateway:
    def __init__(self, max_images=IMAGE_BATCH_SIZE):
        if not 1 <= max_images <= IMAGE_BATCH_SIZE:
            raise ValueError("Gateway batch size must be between 1 and 30")
        self.max_images = max_images
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
            for start in range(0, len(flat), self.max_images):
                chunk = flat[start:start + self.max_images]
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
                # Copy each owner's result slice, never the entire combined results/raw tensor.
                response = {
                    "meta": deepcopy(template["meta"]),
                    "data": {
                        k: deepcopy(v) for k, v in template["data"].items()
                        if k not in {"result", "results", "predictions", "raw_output"}
                    },
                }
                data = response["data"]
                data["count"] = len(collected[index])
                owned = deepcopy(collected[index])
                if isinstance(template["data"].get("result"), dict):
                    data["result"] = {
                        k: deepcopy(v) for k, v in template["data"]["result"].items()
                        if k != "results"
                    }
                    data["result"]["results"] = owned
                # Leaf adapters expose aliases of the same result list. REC reads
                # the top-level alias; leaving it unsliced breaks multi-image calls.
                data["results"] = owned
                if "predictions" in template["data"]:
                    data["predictions"] = owned
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
