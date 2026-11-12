# Shared External API release and recovery

This Part2 correction follows the explicit public shared-workspace requirement. No administrator authentication, user management or approval was added. Part1 under `api/openthai2_ocr_text/` is unchanged and must not run or deploy as part of this release.

Before: Public Settings selected environment-approved providers and could not edit endpoints or credentials. After: anyone can enter an endpoint, POST format/image field, adapter and safe dotted response paths; choose no auth, Bearer, X-API-Key or the supported custom headers; replace/clear a masked write-only key; save/edit/test/enable/disable/delete shared Pipelines. Existing environment credentials cannot be transferred to editable destinations. Test Connection checks readiness only, never inference.

## Persistence and release order

Migration0013 adds only `external_providers`, with public JSON config, encrypted credential, enabled flag, revision and timestamps. PipelineConfig keeps its existing public identity JSON and durable Job behavior. Existing tables/data are not rewritten. Local PostgreSQL clean/additive migrations and schema-drift tests must pass before release. An encryption key must be installed privately on the existing Railway service, with no frontend public secret and no insecure fallback.

Keep the existing Vercel production domain on its previous build while Backend rolls out. Temporarily disable automatic production-domain assignment, merge the verified PR normally, verify Railway health/source SHA and migration, then promote the matching staged Vercel production build. Restore the original automatic-domain setting afterward. This is the documented [Vercel staged promotion workflow](https://vercel.com/docs/deployments/promoting-a-deployment). Do not create a new project, change a plan, increase resources or deploy the standalone API.

Production smoke is non-destructive: public health/catalog/CORS reads and a Chromium Settings form check with editable endpoint and masked blank key, plus local form validation without saving a provider or starting inference. No provisioned External endpoint is assumed. External execution is verified locally with upstream doubles; real external availability/quality is not claimed. Existing private documents/uploads are not accessed. The Backend migration adds an empty shared table; all previous records remain intact.

## Rollback

Prior main: `3440dbe98a56f38097c4eecf5413d4439d81aa39`. Prior Railway deployment: `1c9c0a42-7130-4b2b-8ac6-5e99cf91122b`; prior Vercel: `dpl_4ap3CoTyRVAxKhKmNuQetZ9xerbE`. On a critical regression, stop promotion, preserve logs safely and drain queued Jobs. Frontend can restore its prior deployment immediately. **Do not blindly redeploy the old Backend image:** its Alembic distribution does not know0013 and startup would reject the current revision. Build a recovery commit from prior application code while retaining the reviewed0013 migration file, then deploy that commit through normal controls. Keep the additive table and encryption key; no version-table edits or production downgrade/drop are needed. Verify startup against a local database already at0013 first. Previously saved External Pipelines may be unavailable to the older application; their configuration/credentials remain for roll-forward. Existing ephemeral uploads cannot be recovered by a code rollback.

The new encryption-key backup must remain encrypted and ignored by Git. Preserve the server key separately from the database, test recovery privately and keep every key still needed for stored ciphertext. This release does not claim a complete production database/upload backup, durable uploads or disaster recovery. Existing ephemeral uploads and public shared data/configuration access remain accepted risks.

## Validation evidence

Final test counts, exit codes and deployment versions are recorded after execution in the release handoff. Local evidence lives under ignored `.runtime/shared-external/`; it must not be committed. Full Backend and Playwright, an independent mixed External/Internal browser workflow, TypeScript, ESLint, production build, Ruff, schema checks, diff review and secret scans are required. Existing migration preservation assertions are retained and their expected head changes to0013. No old tests are skipped or weakened to pass.

The40/60/80-field resource matrix is historical evidence and is not rerun here. This change preserves the existing executor/workload limits and adds bounded External parsing/concurrency. It does not establish live provider capacity or a new512MB capacity guarantee. REQ12 remains out of scope.
