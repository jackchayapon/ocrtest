# Neon read-transfer optimization

## Scope and evidence

This draft optimizes reads on the existing application, based on main at
`f9765f6c3b01bca1341c1d273155ca5cd70aa488`. No OCR adapter, metric formula,
Ground Truth rule, dataset label, migration, deployment setting, or production
record is changed. There is no production deployment in this task.

The reported historical 6.37 GB transfer / 45.58 MB storage is user-provided
context, not an independently verified measurement. Small stored data can still
produce large cumulative read traffic. The controlled audit found these costs:

- Repeated pipeline/model/category/document-type catalogs query PostgreSQL on
  every GET, even when unchanged.
- History eagerly fetches raw upstream JSON, boxes and field diagnostics that
  the list does not render. Legacy rows can be much larger than lean rows.
- Analytics loads unused columns and embedded pipeline model definitions.
- Per-case error analysis previously fetched the whole cohort before filtering.
- Browser callers can repeat identical GETs; superseded History/Matrix loads
  previously remained active.

Raw numeric before/after samples are in [the synthetic measurement artifact](neon-network-transfer-measurements.json).

These are demonstrated contributors, not proof of the complete historical bill.
No connection-pool leak was established. Existing `pool_pre_ping=True`, session
lifetime and pool defaults are retained; no speculative indexes/pool tuning.
Startup seeding and analytics aggregation algorithms are unchanged.

## Controlled PostgreSQL measurement

Synthetic fixture: 30 cases, 150 runs, 450 OCR fields, five configured pipelines.
Legacy variant includes 4 KB/run upstream JSON and 2 KB/field diagnostics; lean
variant uses compact retained data. Both use identical values, ordering and
requests before/after. Three sequential GETs per endpoint; table shows the
second (warm) request. Original source/GT/OCR content is never logged.

| GET | SQL before -> after | Rows before -> after | Estimated fetched-value bytes before -> after |
| --- | ---: | ---: | ---: |
| Pipelines | 1 -> 0 | 5 -> 0 | 1,485 -> 0 |
| Models | 1 -> 0 | 28 -> 0 | 5,884 -> 0 |
| Categories | 1 -> 0 | 14 -> 0 | 940 -> 0 |
| Document types | 1 -> 0 | 4 -> 0 | 488 -> 0 |
| History, default/full, legacy | 7 -> 7 | 540 -> 540 | 1,364,920 -> 1,364,920 |
| History, summary, legacy | 7 -> 7 | 540 -> 540 | 1,364,920 -> 173,120 |
| History, summary, lean | 7 -> 7 | 540 -> 540 | 338,720 -> 173,120 |
| Matrix / summary | 8 -> 8 | 815 -> 815 | 261,145 -> 176,780 |
| Analytics pipeline options | 2 -> 2 | 155 -> 155 | 8,235 -> 7,110 |
| Category analytics | 9 -> 9 | 829 -> 829 | 262,085 -> 177,720 |
| Comparison | 9 -> 9 | 815 -> 815 | 261,145 -> 176,780 |
| Error analytics, all cases | 7 -> 7 | 810 -> 810 | 259,660 -> 187,520 |
| Error analytics, one case | 7 -> 7 | 810 -> 27 | 259,660 -> 6,250 |

Bytes above are UTF-8 serialized representations of fetched DBAPI values,
**not PostgreSQL wire bytes, response body size, or Neon billed transfer**. They
exclude SQL parameters, protocol/TLS overhead, other requests and writes. The
script separately records HTTP response bytes and query durations. Equality
checks cover the existing analytics output; summary History intentionally omits
three payloads. This does not establish a production monthly saving or guarantee
that the <500 MB/month target will be met.

## Implementation and consistency

### Catalog caching

Backend caches only four serialized catalogs in process memory, for 60 seconds.
A cold request still performs its original query; subsequent warm hits do not
check out a DB connection. Two of three sequential probe reads were hits (a
controlled 2/3 hit ratio, not a production hit ratio). Concurrent misses share a
loader. Values are copied; ORM/session objects are never cached.

Successful ORM commits invalidate relevant catalogs on that worker. Rollback
never publishes uncommitted configuration. Versioned loaders cannot repopulate
an invalidated entry. Cache locks are not held during database access.

Multiple workers have independent caches. Ordinary cross-worker/cross-device
reads can be stale up to 60 seconds. `?fresh=true` bypasses the worker entry.
After a successful catalog mutation the browser invalidates its catalog memory
and sends `fresh=true` on subsequent misses for that page session, preserving
read-after-write across workers. OCR execution always reads current DB config,
not this cache. Raw SQL/bulk writes outside ORM CRUD rely on TTL expiration.

Browser catalog cache lasts 10 seconds, in memory only. Thus an unrelated browser
may retain an ordinary stale catalog for approximately 70 seconds in the worst
case. No user OCR/GT/history response is retained after its in-flight request;
no localStorage, IndexedDB or persistent offline cache is introduced. GET keys
normalize query ordering. Failed reads are retryable. Writes detach old in-flight
GETs. Requests with independent AbortSignals/custom headers bypass sharing.
History/Matrix effect cleanup cancels superseded requests.

### Compact retrieval

`GET /api/history?view=summary` is opt-in; frontend lists use it. Its shape stays
compatible, but `runs[].boxes=[]`, `runs[].raw_response=null`, and
`runs[].fields[].diagnostics=null` mean omitted list payloads. Default History and
Test Detail retain full payloads. The list retains OCR/GT, field geometry,
metrics/status and pagination. SQL deferral uses `raiseload` to catch accidental
N+1 fetches rather than silently retrieving large columns.

Analytics selects only columns actually used. Error analysis includes text;
per-case filtering now occurs in SQL. Cohort selection, latest-run rules,
CER/WER/confidence/latency statistics and sorting are unchanged. Analytics still
fetches cohort rows; this is not a rewrite to SQL-side aggregation.

### Optional diagnostics

`DB_DIAGNOSTICS=false` by default. Enable only for a controlled audit. Numeric
`db_read` logs include route template (router-relative), HTTP status, SQL count,
query duration, fetched rows/estimated bytes, checkouts, connects, cache hits and
misses. No SQL, parameters, URLs with secrets, document content, GT or tokens are
logged. Instrumentation preserves cursor results. Streaming responses are only
scoped through response creation; do not treat these logs as a complete streamed
batch measurement. Cache hit GETs open no session. Reconnect after a killed idle
connection is tested against isolated PostgreSQL.

## Reproduce safely

Use an explicit disposable **local** PostgreSQL database ending `_test`.
Never use the old/production Neon URL for automated tests or probes.

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://postgres@127.0.0.1:5432/ocr_traffic_test"
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m pytest backend/tests/test_network_optimization.py backend/tests/test_network_optimization_postgres.py -q
backend/.venv/Scripts/python scripts/measure_db_traffic.py .runtime/traffic.json --postgres
backend/.venv/Scripts/python scripts/measure_db_traffic.py .runtime/traffic-lean.json --postgres --lean
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test:e2e -- tests/read-coordinator.spec.ts
cd ..
./scripts/e2e.ps1
```

Probe/PG regression guard accepts localhost only and creates a new randomly
named test database. It retains that database for inspection; it does not reset
existing databases. Probe uses synthetic records and never calls real OCR.
`--backend-root <isolated-baseline-backend>` supports a baseline checkout with the
same numeric diagnostic helper for comparable measurements. Default probe uses
temporary SQLite; results above specifically used PostgreSQL.

## Validation and known baseline failures

- Complete backend with PostgreSQL: **243 passed, 54 failed**. Unmodified baseline:
  **219 passed, 54 failed**; normalized failing test IDs are identical. Twenty-four
  new backend tests pass, including PostgreSQL persistence, real source-crop ZIP
  labels, current dynamic pipeline CRUD and connection recovery.
- Full Playwright: **99 passed, 32 failed**. Baseline full run: **96 passed,
  31 failed**; baseline harness had reused synthetic DB state. The apparent extra
  legacy batch-retry failure was reproduced at the same disabled Run button on a
  new empty baseline DB; it depends on missing configured pipelines, not this change.
  Four new request-coordination tests pass. Existing failures involve legacy
  fixed pipeline seeding, obsolete logs/compatibility assertions and related UI
  preconditions; no tests were deleted or weakened.
- Typecheck, ESLint and production build pass. Full Ruff reports 11 existing
  import-order issues outside this change (baseline: 12); changed Python files are checked
  separately. Full-suite failures are not represented as green release gates.
- Isolated PostgreSQL clean-head/schema-drift and additive 0009 upgrade tests:
  **2 passed**. No migration added. Head remains `0010_dynamic_pipelines`.

A legacy `PUT /pipelines/{id}` compatibility path references a removed adapter
registry; current dynamic UI uses `/definition`. It is an existing issue to fix
separately, not changed to hide failures in this optimization.

## Staging, actual usage and rollback

No confirmed isolated staging environment or Neon usage API was available, so no
staging/production deployment or actual billed-usage measurement was performed.
Before deploying a preview, verify its backend, storage and database are isolated;
a frontend preview pointing at production is not an isolated test environment.

For approved isolated staging: provision a separate PostgreSQL/Neon branch and
storage, configure existing backend env vars privately, apply existing migrations,
build this branch, and set preview `NEXT_PUBLIC_API_BASE_URL` to that isolated
backend. Recheck upload/OCR/GT/History/Matrix/analytics/dataset and catalog CRUD,
including two workers, fresh reads, expiration and connection recovery. Use
synthetic documents. Do not run destructive tests against old Neon.

With authorized Neon dashboard access, record actual transfer for equal before /
after windows, request frequency and dataset size; separate cold/warm and worker
counts. Budget is the sum of endpoint frequency times measured traffic plus
writes/protocol/background traffic. Do not substitute the table's fetched-value
estimates for billed monthly usage. Revisit SQL aggregation/indexes only if these
measurements identify a remaining bottleneck.

Rollback is a normal revert of this branch's code change, followed by the usual
approved deployment. No database rollback or historical-data deletion is needed.
Keep this PR **Draft**, resolve baseline-suite gates before merge/release, and do
not claim production traffic is fixed before actual deployment/verification.
