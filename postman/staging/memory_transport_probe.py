"""Synthetic, network-free transport allocation probe. Never reads a private .env.

Run in a fresh local container with the same CPU/memory limits for each revision.
--heap enables tracemalloc; do not compare its latency with uninstrumented runs.
"""

import argparse
import asyncio
import hashlib
import json
import os
import threading
import time
import tracemalloc
from pathlib import Path

import httpx
from app.core.config import Settings
from app.integrations.batch_gateway import BatchGateway
from app.integrations.model_gateway import ModelGatewayClient


def snapshot():
    status = Path("/proc/self/status").read_text().splitlines()
    cg = Path("/sys/fs/cgroup")
    return {
        "time": time.monotonic(),
        "rss": int(next(x.split()[1] for x in status if x.startswith("VmRSS:"))) * 1024,
        "memory_current": int((cg / "memory.current").read_text()),
        "memory_peak": int((cg / "memory.peak").read_text()),
        "memory_stat": {k: int(v) for k, v in (line.split() for line in (cg / "memory.stat").read_text().splitlines())},
        "memory_events": {k: int(v) for k, v in (line.split() for line in (cg / "memory.events").read_text().splitlines())},
        "swap_current": int((cg / "memory.swap.current").read_text()),
        "swap_max": (cg / "memory.swap.max").read_text().strip(),
    }


async def main(args):
    samples, sizes = [], []
    stopped = threading.Event()

    def sample():
        while not stopped.wait(.02):
            samples.append(snapshot())

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    if args.heap:
        tracemalloc.start(1)
    allocations = []
    if args.heap:
        from app.integrations import batch_gateway, model_gateway

        def instrument(owner, name):
            original = getattr(owner, name)
            depth = 0

            def measured(*values, **kwargs):
                nonlocal depth
                outer = depth == 0
                before = tracemalloc.get_traced_memory()[0] if outer else 0
                depth += 1
                try:
                    result = original(*values, **kwargs)
                    if outer:
                        current, peak = tracemalloc.get_traced_memory()
                        allocations.append({"phase": name, "retained_delta": current - before,
                            "heap_current": current, "heap_peak": peak})
                    return result
                finally:
                    depth -= 1
            setattr(owner, name, measured)

        instrument(model_gateway.json, "loads")
        instrument(model_gateway, "safe_response")
        instrument(batch_gateway, "deepcopy")
        try:
            from app.integrations.gateway_response import EnvelopeParser
            instrument(EnvelopeParser, "finish")
        except ImportError:
            pass  # Baseline revision predates the incremental parser.
    # The tensor is streamed; the probe never constructs the complete JSON body.
    numeric = b"0.1234567," * 1000

    class ResponseStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            parts = [b'{"data":{"contract_version":"leaf-inference-v1","kind":"text_recognition_batch","count":4,"raw_output":',
                     json.dumps([{"rec_text": f"ก้ ABC {i}", "rec_score": .95} for i in range(4)], ensure_ascii=False).encode(),
                     b'},"meta":{"request_id":"synthetic","duration_ms":10},"transport_tensor":[']
            size = 0
            for part in parts:
                size += len(part)
                yield part
            for _ in range(args.numeric_groups):
                size += len(numeric)
                yield numeric
            yield b"0]}"
            sizes.append(size + 3)

    async def one(index):
        client = ModelGatewayClient(Settings(_env_file=None, database_url="sqlite://",
            model_gateway_base_url="https://synthetic.invalid", model_gateway_api_key="synthetic-only"))
        client._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=ResponseStream())))
        batch = BatchGateway()
        return await batch.send(client, client.build_batch_request(pngs=[b"png"] * 4,
            endpoint="/api/v1/text-recognition-batches", version=5, request_id=f"synthetic-{index}"))

    started = time.perf_counter()
    outputs = await asyncio.gather(*(one(i) for i in range(4)))
    elapsed = time.perf_counter() - started
    assert [[r["rec_text"] for r in result["data"]["results"]] for result in outputs] == [[f"ก้ ABC {i}" for i in range(4)]] * 4
    # Each caller owns its records, and aliases within a caller remain consistent.
    outputs[0]["data"]["results"][0]["rec_text"] = "changed"
    assert outputs[1]["data"]["results"][0]["rec_text"] == "ก้ ABC 0"
    heap = None
    if args.heap:
        current, peak = tracemalloc.get_traced_memory()
        heap = {"current": current, "peak": peak, "sites": [
            {"site": str(s.traceback[0]), "bytes": s.size, "count": s.count}
            for s in tracemalloc.take_snapshot().statistics("lineno")[:12]]}
        tracemalloc.stop()
    stopped.set()
    thread.join()
    final = snapshot()
    samples.append(final)
    report = {
        "scope": "isolated synthetic transport + batch slice; not model inference capacity",
        "pid": os.getpid(), "seconds": elapsed, "heap_instrumented": args.heap,
        "response_bytes": sizes, "output_count": 16,
        "prediction_sha256": hashlib.sha256(json.dumps(outputs, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "peak_rss": max(r["rss"] for r in samples),
        "peak_cgroup_sample": max(r["memory_current"] for r in samples),
        "kernel_memory_peak": final["memory_peak"], "final": final,
        "at_sampled_peak": max(samples, key=lambda r: r["memory_current"]), "heap": heap,
        "allocation_phases": allocations,
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("seconds", "peak_rss", "peak_cgroup_sample", "kernel_memory_peak", "heap_instrumented")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--numeric-groups", type=int, default=1332)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 1 <= args.numeric_groups <= 1332:
        parser.error("numeric-groups must be between 1 and 1332")
    asyncio.run(main(args))
