# Railway / Render recovery plan

Current live frontend remains https://ocrtest-sandy.vercel.app and uses NEXT_PUBLIC_API_BASE_URL to call Railway. No Vercel API target, production environment or deployment was changed during candidate preparation.

## Railway first

Keep the existing service if the corrected candidate meets acceptance. Baseline deployment is432a98fb-8c9e-4fa9-bdb3-2e6e4cbf66cd at commit67df434dabed0eeb70a38009fc33fde0e12eba41, 1 replica, CPU1, memory0.512GB, sleep enabled. Source is main, root/backend, watch/backend/**. Record current values again immediately before any future release.

Temporary staging cost was authorized, but Railway rejected creation of an isolated project: `Free plan resource provision limit exceeded. Please upgrade to provision more resources!` No paid plan upgrade is authorized or performed. Existing production was not repurposed as staging. The quota/billing gate prevents a cloud-parity test; it is not evidence that the fixed application is intrinsically unstable on Railway.

## Render candidate

[render.yaml](../render.yaml) is a pre-production fallback blueprint: native Python3.12, root/backend, pinned runtime requirements, verified app.main:app entry point, one Uvicorn worker, 0.0.0.0:$PORT, /api/health and disabled automatic deploys. DATABASE_URL/key/CORS require private entry. Initially use an isolated test database only; do not connect production Neon or point Vercel at it before acceptance.

No Render credentials/connected service were available for deployment. Blueprint validation in an authenticated Render account and real runtime tests remain required. A prepared blueprint is not a deployed or verified service.

Render Free also loses local files on restart/redeploy/spin-down and cannot attach persistent disks. See [Free service limitations](https://render.com/docs/free) and [persistent disks](https://render.com/docs/disks). Changing hosts alone does not satisfy upload durability or solve a memory-heavy payload.

For cost review only, current [Render pricing](https://render.com/pricing) lists512MB/0.5CPU at$7/month and2GB/1CPU at$25/month; persistent disk is$0.25/GB/month. The cheaper paid compute does not match Railway's CPU1, and no paid option was activated. At the measured candidate raw peak465.6MB, a hypothetical25% raw-memory headroom target would require about621MB usable memory; this arithmetic is not a tested minimum or an instruction to upgrade. 512MB completed the bounded workload, with cache/accounting caveats documented separately.

## Database and storage gates

No schema migration is required: head0011_gt_prefill, clean isolated PostgreSQL upgrade and Alembic check pass. Production records must remain untouched. Before cutover, verify the live revision read-only, available Neon recovery/PITR metadata, connection limits and compatibility of old/new writers. No recovery window has been newly certified by this candidate work.

Railway currently has no uploads volume; no durable storage credentials were available. No old files are claimed recovered. The latest user instruction accepts loss of disposable ephemeral uploads during deployment, so recovering those files is not a release prerequisite. This does not authorize intentional deletion of files/records or mounting over an existing path. A future volume/object-storage choice and its costs/access must be approved and restore-tested before claiming restart persistence. Local Docker volume preservation is not proof of production durability.

## Release and rollback

1. Finish candidate regression and specified local acceptance, verify checks and rollback compatibility, then release under the latest accepted ephemeral-storage risk. Extra cloud staging quota is not an automatic blocker; no subscription upgrade is authorized.
2. Test accepted code against isolated DB/storage with safe resource headroom; verify live supported DET/REC and ROI flow with synthetic data.
3. Before deployment, record provider deployment IDs, source SHA, Vercel API target, database revision, recovery metadata and storage backup/restore evidence.
4. For Railway, merge only after acceptance and observe Git auto-deploy; do not create duplicate deploys. Validate health/DB/storage and real GUI smoke.
5. Use Render only if Railway is unsuitable after the fix and Render passes the same gates. Keep Neon and Railway for rollback; do not run incompatible writers or startup migrations.
6. Only after Render acceptance, update existing Vercel Production NEXT_PUBLIC_API_BASE_URL and Render CORS, deploy, then verify browser requests target Render.
7. If cutover fails, restore the previous accepted Vercel target/deployment and compatible backend where safe. Provider rollback does not recover lost ephemeral uploads.

No provider cutover, production migration, plan purchase or storage mount was performed by this preparation.
