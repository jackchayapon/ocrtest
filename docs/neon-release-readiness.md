# Network-transfer PR #5 release readiness

## Current gate: BLOCKED ? ACTION REQUIRED

No production deployment or merge is authorized by this report. The task requires
isolated staging verification and final user approval. The existing GitHub auto-
deploy path works, but it does not itself prove database/storage/backend isolation.

## Verified deployment metadata (read-only)

GitHub reports Vercel Preview success for optimization commit
`c78718f398a69d9445618ea9fc470d0101c009c9`:
https://ocrtest-i4upg3ng6-jackchayapon-s-projects.vercel.app
GitHub deployment ID: `6934931941`; Vercel details ID:
`4qoGy1uCi7UMPXwamgxQYWHzvmQX`. Read-only preview access returns HTTP 200.
This is NOT verified isolated staging; no uploads/OCR/GT mutations ran there.

GitHub reports Vercel and Railway success for current main
`f9765f6c3b01bca1341c1d273155ca5cd70aa488`:
- Vercel GitHub deployment `6929341780`, details `2d9WrHPLPSaokXK2v1dm6x7GmoMV`.
- Railway GitHub deployment `6932323416`; project
  `8cedfe1f-bfcd-4712-a4f0-6fed98130e69`, service
  `dc3bec1b-632a-4edb-813f-5c55d3505dba`, environment
  `5c48a7f7-fc51-4514-95e9-3dbe8b686d59`, deployment
  `809c3453-fbd1-48fe-95f7-379d836df153`.

These IDs are GitHub deployment evidence, not independent provider runtime SHA
attestation. Read-only production health is HTTP 200: PostgreSQL connected and
local storage ready. OPTIONS /api/documents from the existing Vercel production
origin returns 200 with the exact allow-origin, no redirect and Content-Type
allowed. An unapproved origin returns 400 and no allow-origin. No production
Upload/OCR/GT/Dataset mutation has been made in this task.

## Access and isolation blockers

The Vercel connector can list project `ocrtest`
(`prj_qK2ocGOCmZIuMcuZV3W8CVWcfzSB`, team `team_648pA3tZQrlLBHw5IOuQTunI`)
but get-project under `jackchayapon-s-projects` returns HTTP 403, forbidden.
No authenticated Vercel/Railway/Neon CLI is available. Railway/Neon connectors
are unavailable in the session, and the browser runtime fails to initialize.
No platform token value was retrieved or printed.

No separate Railway staging service, Neon branch/database, storage volume or
preview API URL mapping was verified. Actual environment values, startup/root/
watch paths, provider runtime/PORT/timeouts, production DB revision and backup/
PITR state remain unverified. Actual Neon billed Network Transfer could not be
verified. Synthetic fetched-value estimates do not prove the 5 GB quota issue
permanently resolved or a monthly target met.

## Concrete next steps for the authorized operator

1. Reconnect Vercel with read/config access to `jackchayapon-s-projects`; provide
   authenticated Railway/Neon access, or create isolated resources in those
   dashboards and supply their non-secret environment names and public URLs.
   Do not send secret values in chat.
2. Use a separate Railway environment/service AND writable storage, separate
   PostgreSQL/Neon database branch and private env values. Record IDs and verify
   DATABASE_URL points to that isolated database before any mutation tests.
3. Configure this branch's Vercel Preview NEXT_PUBLIC_API_BASE_URL to the staging
   backend and its CORS_ORIGINS to the exact preview origin. Rebuild preview;
   these public values are embedded at build time. Use existing supported config
   names; no new application variable is necessary.
4. Deploy the reviewed branch via the existing GitHub integration to those
   isolated targets. Verify health, startup/migrations, limits/timeouts, then
   PNG/JPEG/PDF, crop/page/batch, single/multi OCR, GT/evaluation and dataset ZIP.
   Use synthetic inputs and a safe test Gateway configuration; no destructive
   fixtures against production. Record actual request/errors and deployment SHAs.
5. Measure equal baseline/optimized workloads and Neon transfer windows on the
   isolated database. Include protocol/background overhead when measurable;
   cold/warm and multiple-worker cache behavior must be recorded separately.
6. Verify production schema compatibility (this PR adds no migration; expected
   existing head is 0010_dynamic_pipelines), backup/PITR AND storage recovery,
   current healthy backend/frontend revisions, then seek final release approval.
7. Preserve Draft until verification is complete. Main auto-deploy may trigger
   both services concurrently; the task's backend-before-frontend order requires
   a confirmed hold/release mechanism or an explicitly approved alternative.
   Do not assume a main push enforces that order.

## Rollback plan prepared before release

Keep production main `f9765f6c3b01bca1341c1d273155ca5cd70aa488` and the deployment
IDs above as the candidate known-good revisions. Re-verify their current status
and backup/storage recovery immediately before release. If a severe regression
occurs, stop mutation tests; the authorized operator redeploys that backend
revision and restores the corresponding Vercel production revision, then checks
health, CORS and saved-data reads. Use provider rollback/redeploy capabilities
or normal revert commits through the supported GitHub workflow, never force
push/reset. Reverts must preserve unrelated newer main commits.

No DB downgrade/reset/truncate or historical document/GT/metric deletion is needed
for this read-only optimization. Restart clears process-local catalog cache;
request-local derived results have no cross-request cache. Preserve uploaded
source files and volumes. Do not recreate files or labels for missing sources.

## Local validation evidence

See [optimization report](neon-network-transfer.md) and
[measurement artifact](neon-network-transfer-measurements.json) for the complete
suite results, exact failed IDs, baseline reproduction, numerical samples and
limitations. Release-critical local smokes use actual browser/FastAPI/PostgreSQL,
new loopback test databases and intercepted Gateway HTTP. They are not staging
or production verification.

## Request/timeout audit

Browser multipart fetch leaves Content-Type to the browser boundary, uses no-store
and does not send the server Gateway key. POST upload/OCR mutations are not
automatically retried. Identical ordinary GETs are coordinated; catalog values
expire after 10 seconds in-browser and 60 seconds per backend process. Ordinary
cross-worker catalogs may be bounded stale; mutation fresh reads/TTL and current
OCR DB config are tested. Derived History/analytics/GT results have no persistent
cross-request cache. UI aborts do not guarantee already-started SQL cancellation.

Upload service reads at most MAX_UPLOAD_MB plus one byte for rejection; existing
upload config/default is 20 MB. Browser fetch has no dedicated upload deadline.
Gateway timeout defaults to 240 seconds; HTTP redirects/environment proxy use
are disabled in the Gateway client. Provider upload/body/response timeouts and
memory limits cannot be inferred from local success and remain staging checks.
Production preflight permits Content-Type; no browser Gateway Authorization
header is necessary. Failed requests remain errors, not mock-success fallback.

## Final current-checkout results

- Backend: **250 passed / 54 failed**; unmodified main application baseline
  **219 passed / the same 54 exact failing IDs**. Main source was verified against
  origin/main for 128 application files (line endings normalized). Initial harness
  attempts hit existing temporary-directory permissions; complete reruns use new
  explicit local basetemp paths, no directory deletion or test suppression.
- Full Playwright: **103 passed / 32 failed (135 tests)**; baseline **99 passed /
  32 failed (131 tests)**. All exact failure IDs match. Both full suites started
  with new empty isolated DBs, removing the previous retained-registry caveat.
  Four release-critical real-backend smoke tests pass in each full suite. Four
  extra request-coordination tests account for this branch's higher total.
- PNG/JPEG/PDF upload/preview, Auto and Manual layout, source coordinates,
  single/multiple pipeline OCR, bounding boxes/text, field and whole GT,
  repeated GT/NFC, reload/History/Matrix, PDF batch/page selection and source-crop
  Dataset ZIP/Thai labels/hash pairing plus idempotent bulk exclusion pass locally.
- Typecheck, ESLint, production build, diff/secret/link checks pass. Whole Ruff
  retains 11 pre-existing findings; changed Python files passed. Clean-head and
  additive-upgrade/schema-drift PostgreSQL guards: **2 passed**. Head remains
  0010_dynamic_pipelines, no migration/new env/application behavior change.

Read-only production health/preflight pass and GitHub auto-deploy metadata is
recorded above. No staging mutation, production mutation, merge or deployment
was executed. GitHub branch pushes may trigger frontend Preview; that is not
an isolated full-stack staging test. Baseline failures remain documented, not
removed/weakened or automatically deemed harmless. See exact IDs in the artifact.
