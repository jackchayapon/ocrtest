# OCR job recovery and release operations

1. Read `/api/ocr-jobs/{id}` and its results. A failed browser connection is not a failed job. Do not resubmit a new run merely because polling failed.
2. On graceful shutdown, the consumer cancels/awaits owned coroutine work. It does not mark interrupted work completed or immediately release its lease while execution may still unwind.
3. On process death, PostgreSQL retains the running job/checkpoints. A replacement process waits for the90-second lease to expire, claims transactionally, and resumes missing units. Heartbeat loss cancels the current attempt; SQL fencing prevents stale commits.
4. A safe retry can repeat uncommitted external calls. Already-checkpointed successful/error fields and their IDs remain unchanged. No duplicate history parent or Metrics row is appended for a resumed job.
5. A missing source file is not recoverable from database text/geometry. The job fails safely with saved partial results available. Restore/re-upload source files if needed; never manufacture images or labels.

## Migration and rollout

`0012_ocr_jobs` creates a new table/indexes only. Existing0011 readers/writers remain compatible while running. Review generated migration SQL, test0011→0012 and clean upgrades/no drift, and verify production recovery evidence before release. The backend's existing lifespan runs the normal Alembic upgrade before constructing its job consumer and before serving requests. No worker can start against an unupgraded schema. Do not reset/drop/truncate production or downgrade the new table during rollback.

Release the backend in a separate PR before the frontend: automatic Vercel/Railway builds may finish in either order. Confirm backend migration/health and a bounded actual Job API canary first; only then merge the frontend-only PR. This keeps the old UI compatible until the Job API is ready, without changing deployment settings or public API URL.

The current Railway backend auto-deploys main changes under/backend/**. Frontend production targets Vercel and retains the same Railway API URL. Inspect deployment source SHAs/status and avoid duplicate deployments. Do not create paid services, disable sleep, or mount over existing storage as part of this change.

Before migration, a separately authorized production logical backup may be exported read-only using a consistent snapshot, encrypted to the local Windows user and restored into an isolated local database for verification. Such a backup is private and must not be committed. This does not certify Neon account PITR or back up Railway ephemeral uploads. Never report unverified restore windows as available.

## Rollback

Stop new submissions via the existing service's optional `OCR_JOBS_ENABLED=false` setting only when a deliberate rollback is approved. Record queued/running job IDs first. An unmodified0011 image cannot run its startup Alembic command against an unknown0012 revision: do not blindly select that older image. Use a compatibility rollback build of original main plus the0012 migration script, paired with the original frontend; leave the additive table and completed records intact. The compatibility build was tested locally: health200 and all40 persisted fields readable on0012. Its source is retained as the migration-only commit preceding the backend implementation. It does not consume jobs. Recover outstanding jobs only with the compatible consumer and available original source. Do not delete jobs/results or create a second unrestricted consumer to clear a queue.

Intentional kill/restart testing belongs only to isolated local containers. Production canary is bounded synthetic work; never kill production to prove recovery.
