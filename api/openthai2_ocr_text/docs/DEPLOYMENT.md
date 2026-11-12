# CDGS infrastructure handover

Build from `api/openthai2_ocr_text` as a standalone Docker context. Provision the pinned snapshot before starting the container.

```sh
python scripts/download_model.py
docker compose build
docker compose up -d
docker compose ps
curl http://127.0.0.1:8091/health
```

Compose binds8091 to loopback, mounts model files read-only, runs UID10001, drops capabilities and uses a read-only filesystem with32 MiB temporary space. Ensure the snapshot directories are traversable and files readable by UID10001. Set a private `OPENTHAI_API_KEY` before exposing readiness/inference. The container image contains application/dependencies. The mounted snapshot remains independently versioned.

One process, one slot, `threads=1` and one CPU are initial settings. Compose assigns1536 MiB locally as a provisional isolation limit. This allocation requires infrastructure-owner approval on the CDGS server and shared-host capacity assessment. Measure representative documents and long-running RSS/cgroup peaks before sizing production. Additional worker processes each load their own networks. `OPENTHAI_WORKERS` currently accepts1 to enforce the initial deployment envelope.

The infrastructure owner must provide a port allocation, CPU/RAM budget, a snapshot path with permissions, supervisor/log retention, secret storage, firewall policy, TLS hostname and approved public route. Independently supervise this process alongside existing CDGS processes.

An Nginx location can be added by the infrastructure owner after route approval. This example maps the same versioned prefix and preserves multipart data.

```nginx
location /openthai/api/v1/ {
    client_max_body_size 11m;
    client_body_timeout 15s;
    proxy_connect_timeout 5s;
    proxy_read_timeout 125s;
    proxy_send_timeout 30s;
    proxy_pass http://127.0.0.1:8091/api/v1/;
}
```

The example route is proposed. HTTPS termination, per-client rate limits and concurrent connection limits belong at the approved reverse proxy. Keep8091 private. Configure liveness against `/health` and authorized readiness against `/api/v1/readiness`. Healthchecks alone do not execute inference.

Rotate a credential by provisioning a new private server value and updating the corresponding OCRLab credential environment reference during a maintenance window. Only one active key is supported by this initial service. Restart the independent container to reload configuration. Existing requests can be interrupted and callers receive a provider failure. OCRLab preserves committed checkpoints through its existing recovery mechanism. In-flight inference can be repeated after interruption.

For rollback, retain the previous image digest and matching read-only snapshot. Stop/drain requests, restore that pair and recheck readiness plus a deliberate synthetic inference. Server registry changes invalidate existing OCRLab pipeline fingerprints until reviewed and saved again. Database migrations are unnecessary for this integration.
