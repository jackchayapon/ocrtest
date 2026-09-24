# Release preparation audit — 2026-09-24

## Scope

Base: `95d9e71d2d97040234e1c0f33426b76cab0b6a60`, following field/ROI commit
`2e268dc98879cc66cd64ebdf389a2c94b68f05a6`. Pre-flight was clean on main;
remote main was `c9c685eb3ae4edfd10583239131116907ded01ba`.

## Conservative cleanup

- Removed unused frontend API wrappers `getHealth` and `getResults`; repository-wide
  references existed only at their declarations. Backend endpoints remain registered.
- Removed `TestToolbar.tsx`: no import, route, test or configuration references;
  the active workspace has its own toolbar implementation.
- Removed unused three-pipeline translation key; corrected Hutch Full explanatory
  copy to Auto full page / Manual crop. No state or adapter logic changed.
- Rewrote README and reconciled detailed docs with five pipelines and migration 0007.

Python AST/reference inventory found single-reference route handlers, which are
registered by decorators and intentionally retained. All other frontend components
had references. Imports are checked with Ruff/ESLint/TypeScript. No TODO/FIXME/HACK,
console.log, debugger or breakpoint candidates were found in application/scripts.

Retained migrations 0001–0007, active tests/fixtures, historical evidence JSON,
framework-generated agent instructions, sample generator/assets, deployment files,
legacy config acceptance and archived-run compatibility. No tracked runtime helpers,
new environment variable, dependency change or migration 0008 is introduced.

No backend source, adapter contracts, ROI state logic, metric normalization,
Dataset labels, authentication or deployment configuration changes are part of cleanup.
Benchmark remains DET V6 / REC V5 without model/engine; Thai FT v2 remains V6/V6
with model=thai_ft_v2. Existing ordering, perspective crop and raw metadata behavior remain.

## Backlog found by audit

1. `MatrixService.eligible` and `ErrorRepository.aggregate` retain an older Hutch Full
   rule accepting only `full_image`. Current `manual_roi` results are consequently
   absent from Matrix/category/error aggregates, although stored results and field
   evaluation remain available. Fix in a separate targeted behavior change with
   historical-stage/latest-run regressions; do not silently change analytics in cleanup.
2. Field summaries currently remain separate from whole-GT dashboards and Dataset.
3. Add distributed execution coordination before multiple backend workers/replicas.
4. Define retention and original-file backup/restore procedures; missing source files
   cannot be regenerated from database records.

## Validation and release evidence

Local validation after cleanup:

- Full backend with isolated PostgreSQL: **136 passed**, two pre-existing dependency
  deprecation warnings. Ruff passed. No meaningful tests removed or added.
- Frontend typecheck, ESLint and production build passed; local standalone output exists.
- Full Playwright: **28 passed**; includes PDF, all five configured pipelines,
  Auto/Manual ROI, Field Check/Confirm, Dataset availability/export and saved views.
- Fresh PostgreSQL database: migrations 0001 → 0007 passed, no schema drift.
- Separate PostgreSQL database: 0006 → 0007 passed; synthetic existing document/case,
  confirmed GT/status preserved; historical roi_source defaults to none; no drift.
- Diff whitespace check passed. Private-environment-value and credential-signature
  scan found no matches in tracked/candidate files. `.env` ignored/untracked and
  `.env.example` secret values empty. Relative documentation paths/anchors resolve.
- No adapter/backend/environment/Docker/Next configuration changes; no migration 0008.

Production preflight (read-only, 2026-09-24):

- Neon connectivity succeeded; revision remains `0006_ocr_error_events`.
  `ocr_fields` and `test_cases.roi_source` are not yet present.
- Existing counts: 165 documents, 166 test cases, 447 pipeline runs, 266 metrics,
  45,334 whole-GT error events. No production data was changed.
- Existing backend health HTTP 200, PostgreSQL connected, storage ready; frontend HTTP 200.
  Production configuration lists the four earlier pipelines, all enabled.
- GitHub reports successful Railway/Vercel statuses for remote commit `c9c685e`.
  Current platform branch/root/watch/auto-deploy and deployment logs are not yet verified.
- Browser tools currently expose no browser sessions, despite the user's manual login.
  Vercel connector returns 403 for the project's team. No Railway/Neon management
  connector is available. Backup/PITR has **not** been verified.
- Production migration, push, new deployments and post-release five-pipeline/feature
  smoke remain pending authenticated platform inspection. Local validation is not
  evidence of a successful production release.
