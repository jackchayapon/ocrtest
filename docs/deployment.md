# Deployment and migration

## Existing release path

Local validation -> explicit source/test/docs commit -> normal GitHub main push -> existing Railway backend and Vercel frontend integrations. Both integrations reported successful deployments for Release A `941d356`. Verify fresh statuses for every release; this does not prove dashboard watch-path settings. Do not create duplicate manual deployments when auto-deploy is active.

Backend health: https://ocrtest-production-095b.up.railway.app/api/health

Frontend: https://ocrtest-sandy.vercel.app

## Environment and storage

Backend names: DATABASE_URL, MODEL_GATEWAY_BASE_URL, MODEL_GATEWAY_API_KEY, MODEL_GATEWAY_TIMEOUT_SECONDS, MODEL_GATEWAY_MAX_RESPONSE_MB, CORS_ORIGINS, STORAGE_MODE, STORAGE_PATH, MAX_UPLOAD_MB, MAX_IMAGE_PIXELS, MAX_IMAGE_DIMENSION, PDF_RENDER_DPI, MAX_PDF_PAGES.

Frontend public name: NEXT_PUBLIC_API_BASE_URL. This is embedded at build time; backend credentials must never be passed to frontend builds. The current features add no environment variables. Use private platform values, never credentials in commands/docs/logs. Gateway token quotes are optional in private dotenv; ordinary tokens can be unquoted with no spaces around `=`.

Retain the persistent uploads volume and writable non-root container ownership. Neon records cannot reconstruct lost originals. Back up database and storage together. Next uses standalone output for Docker/local builds and native packaging on Vercel.

## Migration procedure

Read the pending migration and confirm the intended database through the existing private environment. Validate first on isolated local PostgreSQL. Verify connectivity/current revision, available backup/PITR capabilities and existing record counts without printing connection strings. Release B adds `0009_document_types_dataset` (filename `0009_document_types_dataset_management.py`); the shorter revision fits Alembic's existing version column.

Before pushing code that needs the new schema:

```powershell
cd backend
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
```

Use the intended DATABASE_URL only through the secure environment. Verify head and existing data afterwards. Current head is `0010_dynamic_pipelines`; startup checks migrations and seeds the registry/default metadata while preserving the current Dynamic Pipeline architecture. It does not recreate retired static Pipeline configs. Never reset/drop/truncate production, edit historical revisions or apply a speculative downgrade. If migration fails, stop before pushing.

For the Stage B analytics/UI release, schema remains 0010: verify production revision through a read-only transaction before implementation and immediately before push. No migration is needed. Production verification is GET/SELECT-only; skip the synthetic mutation smoke below for this release. Check raw latest eligible run count against Matrix/summary, provenance/ties, ≥5 timing/ranking, historical labels and URL scope. Keep screenshots under ignored `.runtime/` and never publish document/GT content.

## Validation and smoke

Run targeted pytest/Playwright for affected behavior plus Ruff, TypeScript, ESLint, build and diff/secret checks. Only run a full regression when changes or failures justify it. Keep .env, .runtime, generated test outputs, screenshots and source documents out of Git.

After push, verify Railway/Vercel statuses for the exact commit, then health (database connected/storage ready), pipeline registration and frontend load. A short synthetic smoke covers document type create/archive, type persistence, one selected successful OCR result/evaluation, History success, latest-first Dataset and safe exclusion, partial log search, and desktop/mobile rendering. Reuse saved synthetic results for non-OCR checks; do not repeatedly call models.

On a serious error stop further release actions, inspect non-sensitive logs and identify the cause. Keep a healthy earlier release deployed if the next release is blocked. Never claim backup or deployment verification that was unavailable.

## Operational limits

Run one backend worker/instance until cross-process job locks are implemented. Long PDF batches use an active NDJSON connection; after disconnect check History before retrying. Logs omit OCR/GT and secrets but need an operator retention policy. Production access control is supplied by the deployment/network; this app has no login layer.

## Network-transfer PR #5 approval gates

For this release, use the [specific readiness/rollback checklist](neon-release-readiness.md).
GitHub auto-deploy evidence is recorded there. Preview build success does not
prove isolated backend/database/storage. Complete isolated staging verification
and obtain final user approval before production merge/deployment; keep PR #5
Draft while gates remain blocked. This PR requires no new migration.
