# Standalone deployment

The infrastructure team updates its existing OpenThai service from `api/openthai2_ocr_text/` on the same server infrastructure as CDGS Gateway. Preserve the existing service/container identity and supervisor. Build context, model provisioning and runtime remain independent of OCRLab.

Follow [the CDGS handover](CDGS_HANDOVER.md) for owner-run Linux commands, source verification, routing, smoke tests and rollback. The packaged Compose file has one service named `openthai`. Reuse the current Compose project and service identity after verifying them. For another supervisor or service name, reconcile the existing configuration before replacement.

The tested envelope is Python3.12, ONNX Runtime CPU,1CPU,1536MiB,1worker,1executor/native slot,UID10001,read-only filesystem/model mount,32MiB temporary storage,dropped capabilities and loopback8091. Owner approval and shared-host capacity checks precede deployment. [Measured limits](BATCH_BENCHMARKS.md).

Configure a required private `OPENTHAI_API_KEY`. Compose rejects an unset/empty value. Direct startup with missing/unusable authentication leaves liveness available, skips model loading and returns503 `AUTH_NOT_CONFIGURED` from protected APIs. Readiness monitoring must check authorized readiness and a deliberate synthetic inference. Public `/health` alone does not establish model readiness.

The intended public Single path is `/paddle/api/v1/openthai-text`, mapped to `/api/v1/ocr-text`. Public Batch `/paddle/api/v1/openthai-text-batches` remains **NOT DEPLOYED / PENDING CDGS**, with intended mapping to `/api/v1/ocr-text-batches`. Proxy implementation and current mapping require owner verification. Preserve TLS, private ports, credential matching, body limits, deadlines and per-client abuse controls using the existing proxy technology.
