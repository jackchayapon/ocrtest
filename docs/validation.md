# Final validation record

## Final project review — 2026-09-10

The OCR benchmark MVP remains feature-complete for its current scope. No UI redesign, model behavior or pipeline semantics changed. This pass added API/flow/deployment/Gateway trace documentation, tightened build exclusions, separated runtime dependency pins, removed two unused settings and an exception alias, and cleaned reproducible output. All 159 files in `modelsapi/` have identical before/after SHA-256 fingerprints.

| Final check | Result |
| --- | --- |
| Complete pytest suite with local PostgreSQL repository test | **55 passed**, no failures/skips; two dependency deprecation warnings |
| Ruff | Passed |
| Development dependency install / pip check | Passed; runtime pins and test-tool pins remain consistent |
| Frontend typecheck / lint / production build | Passed |
| Complete Playwright suite on production Docker frontend/backend + local PostgreSQL | **10 passed**, 18.8 seconds |
| Local PostgreSQL schema check | No new upgrade operations detected |
| Neon migration / schema check | `0003_pdf_pages`; no new upgrade operations detected; existing case count unchanged |
| Neon restored after local browser validation | Saved image and page-2 PDF details/original retrieval passed |
| Compose config / backend + frontend image builds | Passed |
| Final stack health | Frontend HTTP 200; API healthy, PostgreSQL connected and local storage ready |
| Runtime contents | Backend has PDFium/OpenCV/NumPy but no pytest/Ruff/tests/reference/env files; frontend has no Playwright/TypeScript/tests/backend/reference/env files |
| API documentation | All 23 OpenAPI path entries documented; local documentation links resolve |
| Secret checks | No known runtime secret found in scanned frontend/source/docs/tests/artifacts or saved run payloads; config URLs/query keys contain no credentials |
| Windows scripts | Syntax validated; existing startup/exit-code checks retained |
| Gateway health / readiness without key | 200 / 401; no real inference attempted |

The first clean-cache pytest invocation exposed an existing configuration assumption: `--basetemp=.pytest_cache/tmp` failed when its parent cache did not exist. It now uses project-local `.pytest_tmp`, which is ignored/excluded; the complete rerun passed. A blank-line lint issue from removing the unused alias was corrected and Ruff rerun successfully. No repeated frontend or browser suite was needed after those backend test/format-only corrections.

### Cleanup and measurements

Removed the old npm cache, stale Next.js output, old Playwright screenshots/results, Python bytecode/test/lint caches, and six one-off translation helper scripts/data files under `.runtime`. Current builds/test evidence were regenerated and retained. Upload storage, all required PNG/JPG/PDF fixtures, node_modules and the working Python virtualenv were retained. No active application source file, feature, migration or required dependency was deleted. Unreferenced source members removed: `Settings.sqlite_path`, `Settings.external_timeout_seconds`, and `PipelineError` alias.

`requirements-runtime-lock.txt` now contains runtime pins; the development lock includes it plus pytest, Ruff, iniconfig, pluggy and Pygments. These five development packages remain installed for tests but are excluded from the backend image. OpenCV/NumPy remain because ImageService imports them; changing crop implementation merely to reduce dependencies was out of scope.

| Major directory | Before bytes | After validation bytes |
| --- | ---: | ---: |
| frontend | 1,333,018,453 | 572,092,445 |
| backend | 315,406,934 | 315,371,224 |
| modelsapi (unchanged reference) | 788,483 | 788,483 |
| docs | 14,661 | 50,286 |
| scripts | 5,997 | 5,997 |
| .runtime | 86,266 | 133,802 |
| **Directory total** | **1,649,320,794** | **888,442,237** |

This checkpoint measures logical file sizes, excluding root-level files; later documentation/log edits add a few KB. Approximate local reduction: **760.88 MB** (decimal). It is not a claim about server disk usage. Installed developer dependencies dominate the retained workspace.

Docker image sizes reported by `docker image inspect .Size`:

| Image | Before bytes | Final bytes |
| --- | ---: | ---: |
| Backend | 179,453,421 | 165,275,217 |
| Frontend | 79,154,717 | 79,249,418 |

Backend image reduction is **14.18 MB**; frontend grew about 0.09 MB. These are Docker-reported image sizes, not compressed registry transfer sizes or deduplicated daemon disk usage. No separate deployment archive was produced. Production images exclude model reference source, weights, host virtualenvs/node_modules, local documents, caches, screenshots and test fixtures; see [deployment classification](deployment.md).

### External status

Neon is live-configured and verified. No real Gateway key exists in the inspected active settings or process/user/machine environment. Reference `.env.runtime` is absent and example keys are placeholders. Live health succeeds but readiness requires authentication. Only obtaining the deployment owner's public key and verifying deployed Mint/Paddle inference remain external blockers. See [source-backed Gateway trace](model-gateway.md). Historical credential statuses below apply only to those earlier checkpoints.

## PDF + Thai update — 2026-09-09

The existing application now supports on-demand PDF pages and Thai UI. Validation was completed against the Docker production frontend/backend. The backend's configured database is now **Neon PostgreSQL**; the local PostgreSQL service remains available for isolated repository tests. The older baseline below predates these changes and its credential status is historical.

| Check | Result |
| --- | --- |
| Complete backend suite, including local PostgreSQL integration | **55 passed, 0 failed, 0 skipped**; two dependency deprecation warnings |
| Ruff | Passed |
| Frontend typecheck / lint / production build | Passed |
| Final Playwright suite | **10 passed** in 49.1 seconds |
| PNG and JPG workflows | Passed separately: upload, ROI, three mocks, GT, save, History and detail |
| Multi-page PDF workflow | Passed: page 1 preview, page 2, ROI, GT, three mocks, metrics, confirmation and History reopening on page 2 |
| Page switching | Clears transient ROI, unsaved GT, suggestions and results; saved cases remain unchanged |
| Responsive Thai workspace | Loaded canvas/crop checked at 1440, 1024 and 768 pixels; mobile check at 390 pixels; no horizontal overflow or clipped buttons |
| Thai PDF errors | Exact corrupt/unsupported messages and browser upload-size validation passed |
| PDF backend errors / limits | Invalid pages, corrupt/empty PDFs, size/page limits, encryption and renderer failures covered |
| PDF crop fairness | Captured multipart PNG bytes, dimensions and SHA-256 match across all three adapters |
| Migration / schema drift | `alembic upgrade head` succeeds at `0003_pdf_pages`; `alembic check` reports no new operations |
| Live Neon persistence | Direct query confirms PDF page 2, raster 1200 × 1434, page count 2 and pinned 200 DPI; image cases remain present |
| Docker | Backend with pypdfium2 and updated frontend built; all three services healthy |
| Final health | API HTTP 200, database connected, local storage ready; frontend HTTP 200 |

The suite increased from 41 to 55 backend tests through 14 PDF cases. The browser suite now has five PDF/error/responsive tests and five image/general tests, including separate PNG and JPG workflows. The stronger screenshot checks found and fixed a 768-pixel grid minimum-width issue caused by the canvas's initial intrinsic size. Screenshots now wait for the viewer and crop image to load.

Rendering uses pypdfium2 5.13.0 at a default 200 DPI, pinned per uploaded document. Original PDFs alone are stored permanently; native render handles and in-memory page/crop buffers are closed/released. Auto ROI sends the selected page only. Pipeline boundaries and Hutch parameters `1.7`, `0.25`, `0.6` are unchanged. Internal pipeline/category/status identifiers remain unchanged. Technical diagnostics are collapsed by default.

No files under `modelsapi/` were modified. No unrelated code was removed. Real OCR remains unverified because the Gateway API key is absent; mock runs are explicitly labeled. **Live Neon connectivity, migration and saved-page persistence are now verified**, so Neon credentials are no longer an outstanding blocker in this workspace.

Evidence: `frontend/test-results/thai-pdf-{1440,1024,768}.png`, `frontend/test-results/pdf-page-two-thai.png`, and image workflow screenshots/metadata. Test artifacts may be replaced by subsequent runs.

## Previous image-only deployment baseline

Validated on 2026-09-09 on Windows with Docker Desktop, local PostgreSQL 17, Python 3.12 and Node 24. No external Model API source was changed. This session changed only development/deployment configuration, documentation and browser assertions.

## Results

| Check | Result |
| --- | --- |
| Backend pytest with `TEST_DATABASE_URL` | **41 passed**, no skips; two dependency deprecation warnings |
| Ruff | Passed |
| Frontend typecheck / ESLint / production build | Passed |
| Playwright against Docker production frontend/backend | **4 passed** |
| Final complete mock workflow after documentation | **1 passed**; confirmed case reopened through History |
| Backend and frontend Docker builds | Passed; existing dependency/build layers reused |
| Compose configuration and startup | Passed; PostgreSQL/backend healthy, frontend HTTP 200 |
| FastAPI `/api/health` | HTTP 200; PostgreSQL connected, local storage ready |
| Native `scripts/dev.ps1` | Both servers reached HTTP 200; occupied-port rejection passed |
| `scripts/check.ps1 -Browser` | Passed, including PostgreSQL integration test |
| Frontend → backend | Browser workflow and CORS preflight passed |
| Container storage | UID 10001, writable `/app/storage/uploads`; original/crop retrieval passed |
| Persistence after backend container recreation | Confirmed case, predictions, original image and crop remained available |
| Repeated mock run | Same raw/final text, confidence, boxes, time, crop dimensions and hashes |

The baseline increased from 40 to 41 backend tests because the existing metric suite now includes a long, nearly identical text regression test. The warnings concern Starlette/httpx and AnyIO deprecations; no tests were skipped or failed in the complete validation run.

## Clean PostgreSQL migration

Created a new empty local database, `ocr_benchmark_clean_20260909`, without deleting existing data. Ran `alembic upgrade head`, then `alembic check`: **No new upgrade operations detected**. Revision: `0002_gateway_crop_trace`.

Verified `documents`, `test_cases`, `pipeline_runs`, `metrics`, `categories`, `test_case_categories`, `pipeline_configs` and `alembic_version`. Verified Gateway/local request IDs, service/model metadata, Gateway duration, original/crop dimensions, ROI, crop hash, input size/format, crop stage, error code and mock marker columns.

Production remains SQLAlchemy 2 + psycopg 3 + Alembic against Neon through `DATABASE_URL`. A blank development URL selects local PostgreSQL, not SQLite. Isolated unit tests explicitly use temporary SQLite databases; the repository integration test uses a separate PostgreSQL test database.

## Crop fairness and browser workflow

The HTTP contract test captures all three multipart uploads and proves identical PNG bytes, dimensions and SHA-256. It also proves that only Hutch Full crops during adapter invocation, and rejects a prebuilt crop for that adapter. Both Hutch requests explicitly send `1.7`, `0.25`, `0.6` for unclip, detection and box thresholds.

The saved synthetic browser benchmark produced a **770 × 130** crop. All three hashes were:

```text
feb40e483ab30ba3b32e5b21c54dffafc233cb0571b082c697d6010972e09348
```

Mint and Hutch Crop used `pre_adapter`; Hutch Full used `inside_adapter`. Downloaded crop bytes were independently hashed after container recreation and matched the stored hash.

Playwright covers upload/preview, reverse-direction ROI drawing, zoom invariance, ROI movement/resizing, all three pipelines, GT confirmation without changing predictions, accuracy/confidence, OCR box selection, saved detail reopening through History, Matrix, Category Analytics, settings and mobile width. Auto ROI failure preserves manual work; selectable suggestions are tested with an explicit browser fixture.

Additional assertions verify raw OCR, model/dimension/encoding/time/request-ID fields, and both **SAME INPUT** and **DIFFERENT INPUT**. The latter uses a browser-only altered response; stored hashes remain unchanged. Mock Gateway IDs/durations remain null instead of fabricated measurements.

## External dependencies and privacy

- Gateway health: HTTP 200. Readiness: HTTP 401 `AUTHENTICATION_REQUIRED`. The application's integration status reports connected/not-authenticated without crashing.
- API key absent: **Mint and Hutch real OCR NOT VERIFIED — API KEY REQUIRED**. No real document inference was attempted.
- Neon: **integration implemented; live validation pending DATABASE_URL**. No Neon credentials were present.
- Mocks are deterministic, visibly labeled **MOCK MODE**, and never substituted for failed real calls.
- Frontend environment contains neither `DATABASE_URL` nor `MODEL_GATEWAY_API_KEY`. Docker build contexts exclude `.env` files; frontend source uses only the public backend URL.
- Privacy tests cover raw-response redaction, secret/text logging protections, no embedded image payloads in persisted OCR responses, temporary-file cleanup, and `Cache-Control: private, no-store`.

## Deployment polish and cleanup

Fixed `dev.ps1` to check dependencies, test ports directly (the Windows port inventory missed Docker bindings), pin port 3000, wait for readiness, propagate failures and terminate only its own processes on failed startup. Native success and occupied-port failure paths were exercised.

Compose now forwards both documented image dimension limits. README documents prerequisites, environments, migrations, native/Docker startup, real/mock configuration, tests and exact pipeline boundaries. There were no incomplete application files and no unquestionably unused generated files to delete. Cleanup list: **none**. `modelsapi/` remains untouched.

Local evidence: `.runtime/docker-build-final.log`, `.runtime/check-final.log`, and `frontend/test-results/` screenshots/benchmark metadata. Test artifacts are local outputs and may be replaced by subsequent test runs.
