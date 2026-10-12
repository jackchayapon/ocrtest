# Thai insights / single-sheet Excel validation

Validated locally on 2026-10-12, extending PR #6 / eb3fc4d.

- Complete PostgreSQL pytest: 370 passed / 54 failed. All 54 exact IDs match the
  saved pristine-main baseline; zero added/removed failures. New XLSX tests: 22.
- Complete Playwright: 116 passed / 32 failed (148 tests). Every failing name
  also fails on pristine feature eb3fc4d (111 passed / 35 failed, 146 tests).
  Baseline ran isolated on frontend3200/API8200, adapting only the ignored
  harness CORS port. Three baseline-only real-backend failures are not claimed
  as improvements: port/environment differences prevent causal attribution.
- Final affected Playwright: 8/8 passed after final Thai wording changes.
- Typecheck, ESLint and production build pass. Changed Python Ruff passes;
  whole-repository Ruff retains the documented 11 baseline import-order findings.
- Backend Docker build and container import of openpyxl 3.1.5 pass.
- Actual local synthetic workbook and ZIP downloaded/read back. การบ้าน versus
  การบาน produces one missing U+0E49, CER 1/7; matching OCR yields zero/Exact Match.
- Local model/config catalog remains 32/11. Separate test databases used; no
  production writes, migration or real Gateway inference.

Full suites are NOT green; matching baseline failures are evidence, not waived
release gates. Failure IDs: [regression evidence](thai-excel-regression-evidence.json).
No tests removed/suppressed. No new environment variable or migration.

## Transfer
[Measurements](thai-excel-traffic.json) use the same synthetic20-case fixture.
History remains 7 queries, 40,348 estimated DB bytes / 39,643 HTTP bytes, versus
199,834 / 305,793 full baseline. XLSX uses four scoped reads, 6,787 estimated DB
bytes / 7,796 HTTP bytes. Thai descriptions increase explicitly opened detail
response sizes; no initial History/detail/crop request is added. These are local
DBAPI estimates, not measured Neon billing.

## Release gates
PR branch update is permitted; merge/deployment remains blocked until baseline
failures are resolved/approved and production PITR/storage recovery readiness,
isolated staging, provider deployment/CI checks are verified. Existing unresolved
gates in [release readiness](neon-release-readiness.md) remain in force.

Local browser UI downloads OCRLab_Evaluation.xlsx successfully; readback confirms
the synthetic GT/OCR and CER values. User development frontend3000/backend8000
restored. PostgreSQL upgrade head/current/check: 0010_dynamic_pipelines, no new
upgrade operations. The historical 0007 guard still asserts obsolete head0009
and fails identically to baseline; it was not edited to suppress that failure.
