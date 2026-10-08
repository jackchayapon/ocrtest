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

## Initial iteration validation (commit 05a1776)

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

## PR #5 continuation: shared dashboard reads and latest History

The Matrix browser now requests `/api/analytics/summary?dashboard=true` once.
The opt-in response retains summary fields and adds `matrix` and `comparison`.
All three views reuse a request-owned compact cohort and existing calculation
functions. Default Summary/Matrix/Comparison APIs keep their contracts. An older
backend ignoring the flag is supported by falling back to the two separate
Matrix/Comparison reads. No sensitive derived output is cached across requests.
This is one ORM cohort, not an atomic multi-query database snapshot under
READ COMMITTED. Bundled comparison computation timing excludes preloading;
it is a diagnostic timer, not OCR latency or a statistical metric.

History's browser uses `view=summary&latest=true`. The latest opt-in returns one
non-archived run per case/pipeline, ordered by creation time and UUID as a tie
breaker. Case filtering/pagination happens before select-in run loading. Archived
newer runs cannot displace an active older run. Full default History and summary
without latest retain historical attempts. No stored data is deleted.

### Comparable measurements against current main

Each endpoint was sampled three times on fresh isolated PostgreSQL fixtures.
Tables below use warm fetched-value bytes and query counts. Full sample SQL
medians, fetched rows, HTTP bytes and normalized output hashes are in the JSON
artifact. Output hashes agree for unchanged endpoints and combined dashboard
semantics; intentional History projection/attempt omission is tested separately.

| Fixture | Cases / runs / OCR fields | Dashboard SQL main -> PR | Dashboard fetched bytes main -> PR | Latest History fetched bytes main -> PR |
|---|---|---|---|---|
| Small legacy | 30 / 150 / 450 | 25 -> 9 | 783,435 -> 176,780 (77.44% less) | 1,364,920 -> 173,120 (87.32% less) |
| Larger legacy, 3 attempts | 120 / 1,800 / 5,400 | 43 -> 15 | 9,031,875 -> 2,070,490 (77.08% less) | 4,076,960 -> 173,440 (95.75% less) |
| Mixed lean, 3 attempts | 120 / 1,800 / 5,400 | 43 -> 15 | 9,808,515 -> 2,293,610 (76.62% less) | 1,043,664 -> 196,344 (81.19% less) |

Mixed lean includes legacy, global per-field and global whole-document evaluation
in equal case groups, with 240 global fields. Larger legacy dashboard fetched
rows fall from 27,735 to 9,245. Latest History rows fall from 1,540 to 540.
Incrementally versus initial PR commit 05a1776, larger legacy History drops
501,560 -> 173,440 fetched bytes, and the dashboard 6,211,470 -> 2,070,490.

| Larger legacy endpoint | SQL main -> PR | Fetched bytes main -> PR | HTTP bytes main -> PR |
|---|---|---|---|
| Matrix | 14 -> 14 | 3,010,625 -> 2,070,490 | 1,511 -> 1,511 |
| Comparison | 15 -> 15 | 3,010,625 -> 2,070,490 | 18,605 -> 18,605 |
| Errors | 13 -> 13 | 3,009,140 -> 2,203,330 | 51,364 -> 51,364 |
| Dashboard workload | 43 -> 15 | 9,031,875 -> 2,070,490 | 21,247 -> 21,272 |
| Latest History | 7 -> 7 | 4,076,960 -> 173,440 | 4,305,421 -> 281,661 |

Latency is a trade-off, not an unconditional improvement: latest History's
correlated anti-join increases median SQL time 12.51 -> 15.33 ms on larger legacy
and 9.53 -> 15.44 ms on mixed lean; dashboard larger legacy median is
93.10 -> 59.81 ms. These are three-sample local observations, not production
latency guarantees. Dashboard still loads historical eligible runs in memory;
future SQL aggregation/index changes require separate evidence and review.

Catalog cold read remains one query; warm pipeline/model reads become zero.
Eight simultaneous cold model reads execute eight SQL queries on main and one
on this PR (one miss, seven hits), with equal returned JSON. PostgreSQL tests
use two independent app/session-factory instances: a second worker's catalog
may remain stale within its 60-second TTL, but OCR reads current persisted config;
explicit fresh and TTL expiry retrieve the update. Connection termination/recovery,
source PNG cropping, confirmed Thai GT ZIP labels, cache invalidation and
failure isolation are tested without real Gateway calls.

### Deployment readiness boundaries

Local browser smoke exercises actual FastAPI/PostgreSQL with synthetic PNG/PDF
and mock Gateway: CORS preflight, upload/preview, Auto plus Manual source-coordinate
layout, two-pipeline OCR, four GT fields, evaluate, History reopen, shared Matrix,
PDF page 2, batch pages, ZIP integrity/PNG dimensions/Thai labels and config refresh.
Test selectors wait for asynchronous registry loading and choose only their own
pipelines; no assumption of an empty registry or a fixed pipeline count.

Existing CORS permits content-type and GET/POST/PUT/DELETE/OPTIONS. Existing limits
are upload 20 MB, image 40 million pixels, PDF 200 DPI/500 pages, Gateway timeout
240 seconds and response limit 64 MB. PostgreSQL connect_timeout 10 seconds,
pool_pre_ping and existing 5 + 10 pool defaults are unchanged. Docker launches
uvicorn on port 8000; existing lifespan migration/seeding is unchanged. Vercel
public API URL is a build-time frontend value; conditional standalone output is
unchanged. No committed railway.json/vercel.json establishes provider dashboard
root/watch/startup settings; actual cloud configuration remains unverified.

No isolated staging or authenticated Neon usage dashboard was available.
No staging deployment, production database access or real OCR was performed.
Actual monthly transfer and a <=500 MB/month target cannot be inferred from these
synthetic estimates. Request/abort coordination does not guarantee cancellation
of an already running SQL statement. Diagnostics remain opt-in/default off.

Reproduce the larger and mixed fixtures with the existing secure local test URL:

```powershell
backend/.venv/Scripts/python scripts/measure_db_traffic.py .runtime/large.json --postgres --cases 120 --runs-per-pipeline 3
backend/.venv/Scripts/python scripts/measure_db_traffic.py .runtime/mixed.json --postgres --lean --mixed --cases 120 --runs-per-pipeline 3
```

All test databases are newly created localhost *_test databases. Main comparisons
use archived f9765f6 code with numeric instrumentation, no product modifications;
baseline browser uses Webpack for an external node_modules junction, while this
branch uses its normal Turbopack production build. Baseline smoke copies change
only expected separate dashboard reads, interpreter location and isolated CORS
port. No production credentials or sensitive output are present in artifacts.

## Final continuation validation

- Backend including isolated PostgreSQL: **250 passed / 54 failed**; fresh main
  **219 passed / identical 54 failing IDs**. Thirty-one optimization/PG tests pass;
  another 40 migration/current pipeline/metric/batch guards pass.
- Complete final Playwright: **102 passed / 31 failed (133 total)**.
  Fresh main with two copied smoke tests: 96 passed / 33 failed (129 total).
  First equivalent full branch run: 100 passed / 33 failed, matching the same
  32 existing failures plus the asynchronous-registry smoke fixture issue.
  After waiting for registry loading and explicitly selecting test-owned configs,
  baseline targeted smokes are 2/2 and both final branch smokes pass.
  The final full rerun retains its isolated DB: the empty-registry batch retry case
  passes because prior test configs exist. This is a fixture-state difference,
  not a product fix. Final failing IDs are a subset of main failures; exact
  lists and this qualification are retained in the measurement artifact.
- Typecheck, ESLint, production build, changed-file Ruff, diff/secret/link checks
  pass. Whole Ruff has 11 existing import-order violations (main 12).
- Alembic clean-head/additive upgrade/schema-drift guards pass; head remains
  `0010_dynamic_pipelines`. No migration, required env variable or deployment
  configuration is added.

No existing test was deleted or weakened. Suitable for draft review, **not a
 green merge/release gate**. Resolve baseline tests and verify isolated staging
and actual transfer before release.

## Staging/production gate continuation

See [release readiness and rollback](neon-release-readiness.md) for verified GitHub
auto-deployment metadata, current read-only health/CORS evidence, access blockers
and the isolated-staging procedure. No new optimization or product behavior
change was needed in this continuation. Two additional release-critical browser
smokes cover JPEG and PDF page manual crops, exact dataset/source PNG hash pairing,
repeated GT/NFC, whole/per-field evaluation and idempotent bulk exclusion.

### Current release-gate verification

Fresh complete suites: backend **250 passed/54 failed** vs pristine main
**219 passed/same 54 failing IDs**; full Playwright **103 passed/32 failed (135)**
vs main **99 passed/same 32 failing IDs (131)**. Both browser suites start with
new empty test DBs; all four current real-backend critical smokes pass in each.
Typecheck/ESLint/build pass; clean-head/additive-upgrade/drift guards 2/2 pass.
No application code or migration change was needed. See release readiness for
staging/production blockers; no merge or production deployment took place.

The large controlled workload was remeasured in this session: dashboard 43 ->15
SQL, 27,735 ->9,245 rows, 9,031,875 ->2,070,490 fetched-value bytes and HTTP
21,248 ->21,272 bytes. Median SQL time is 94.77 ->27.18 ms. Latest History is
7 ->7 SQL, 1,540 ->540 rows, 4,076,960 ->173,440 fetched bytes and HTTP
4,305,421 ->281,661 bytes, with median SQL 12.73 ->15.01 ms. Eight concurrent
cold catalog reads execute 8 ->1 SQL. Semantic dashboard output hashes match.
These local three-sample observations are not wire bytes, Neon billing or cloud
latency guarantees. Raw samples are appended under release_verification.
