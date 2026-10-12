# Character Insights validation (2026-10-12)

Baseline: main 2e7385a21f78fb2eddae1d6cec2a6dbbd3b62cd4, freshly fetched again on resumption.
Feature work is isolated in feature/ocr-character-error-insights; original workspace preserved.

## Traffic measurement

Reproduce with backend/.venv/Scripts/python.exe scripts/measure_character_insights.py after setting TEST_DATABASE_URL to a localhost PostgreSQL *_test database. The script creates a NEW retained database and never loads .env or calls a Gateway.

Fixture: 20 cases, 5 pipelines, 3 runs/pipeline, 3 fields, mixed legacy/global and synthetic legacy diagnostic payloads. Median of three requests. Fetched bytes estimate UTF-8 DBAPI values; they exclude wire protocol/TLS and are NOT Neon billing.

| Operation | SQL queries | Estimated DB bytes | HTTP bytes | Median ms | API requests |
|---|---:|---:|---:|---:|---:|
| A_history_before | 7 | 199834 | 305793 | 55.8 | 1 |
| A_history_after | 7 | 40348 | 39643 | 23.26 | 1 |
| B_overlay_source_baseline | 7 | 208268 | 355061 | 36.46 | 1 |
| B_overlay_after | 4 | 1846 | 6105 | 7.77 | 1 |
| C_evaluation_before_and_after | 7 | 208268 | 355061 | 36.24 | 1 |
| D_expand_before_loaded_alignment | 0 | 0 | 0 | 0 | 0 |
| D_expand_after | 4 | 779 | 2856 | 6.73 | 1 |
| E_export_source_baseline | 7 | 208268 | 355061 | 36.93 | 1 |
| E_export_after | 4 | 6758 | 4875 | 8.84 | 1 |

Important interpretation:
- A retains 7 queries; no extra per-row reads. History initially also requests the unchanged pipeline catalog once; that identical request is excluded from this endpoint comparison.
- B/E baseline is the unchanged full-case source endpoint, not a previous implementation of overlays or ZIP export (neither existed). Do not interpret ZIP compression as a database billing saving.
- C is unchanged; no character detail request is added when opening Evaluation.
- D adds one explicit four-query request for server-authoritative character statistics. Previously the UI only had loaded spans; it had no character-statistics endpoint. Closed summaries use those spans for totals, with zero extra requests. Character selection fetches another bounded filtered response.
- Reads are case-scoped, latest-only; detail avoids raw responses/boxes/diagnostics. No persisted error events or export records.
- Raw numeric evidence: [character-insights-traffic.json](character-insights-traffic.json).

## Regression evidence

Pristine-main backend baseline: 261 passed, 54 failed. The final feature run is recorded below; compare exact failure IDs in [character-insights-baseline-failures.txt](character-insights-baseline-failures.txt). These pre-existing failures include obsolete static-pipeline seed expectations and an old migration-head assertion. They were not suppressed, deleted or described as new regressions.

Browser suites: character-insights, global-comparison, character-description, error-analysis-lines, highlight-units, read-coordinator, lean-bulk, zz-network-live, comparison-dashboard.
New tests cover lazy requests, selected pipeline only, exact PDF page/ROI query, original crop, zoom/pan/Ctrl-wheel, nested Escape and focus, default Highlight and toggle, GT invalidation and hidden-pipeline export routing.
Backend tests inspect actual ZIP members, Thai data, latest/archived isolation, canonical counts, NFC, formula safety, no event writes, no whole text reads for field requests, null evaluation state, and explicit unavailable exports.

The existing zz-network-live assertion expected /ground-truth with no query. Main's GlobalWorkspace already routes OCR completion to /ground-truth?edit=1. Only that assertion was corrected; subsequent upload/ROI/OCR/GT/History/Matrix assertions remain intact.

## Scope and limitations

No production database or deployment changes. No migration or new environment variables. Real Gateway inference and production billing are not tested by this feature validation. Existing baseline backend failures remain a repository-level limitation; this Draft PR is not a clean full-suite release certification.
Multiline line attribution remains explicitly unavailable, previews are field/page geometry, and exports are bounded to one case/page. See [feature guide](character-insights.md).

## Final results

- Backend full suite including local PostgreSQL: **348 passed, 54 failed, 2 warnings**. Exactly the same 54 failure IDs as pristine main (261 passed/54 failed); **87 new tests pass**, no new failing test IDs.
- Feature + network-targeted suite: **117 passed**.
- Relevant Playwright suite: **74/74 passed**, including original PDF/image source pixels, Dataset ZIP, field GT, History and Matrix.
- TypeScript, ESLint, production build: **PASS**.
- Ruff on all changed Python files: **PASS**. Whole backend retains **11 pre-existing import-order findings**.
- git diff --check: **PASS**.
- Exact private-secret-value scan of tracked/new repository files: **PASS**, no values logged. .env ignored/untracked.
- No migration, production write, real OCR rerun, deployment or merge performed.

The full repository suite is not green because of the documented baseline failures. Review this as a Draft feature PR; repairing obsolete baseline fixtures is a separate follow-up.
