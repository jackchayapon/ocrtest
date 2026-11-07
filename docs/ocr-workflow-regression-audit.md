# OCR workflow regression audit — 7 November 2026

Base main: `695bf4b0f3355653ea4c82102e6586debaac9c2b` (PR11/PR12).
Branch: `fix/ocr-workflow-regression-audit`. No database migration or model-registry change.

## Confirmed root causes

1. **DET HTTP200 / FIELD_PIPELINE_ERROR:** read-only production diagnostics grouped154 affected Field failures as `INVALID_OCR_RESPONSE`, message `Batch result count does not match input images`. The shared client removed `raw_output` assuming structured aliases existed. Controlled synthetic CDGS requests on7November confirmed DET and REC currently return `leaf-inference-v1` predictions **only inside `data.raw_output`**, with `count` and model selection. Removing that sole representation loses all predictions before batch slicing, prevents REC after DET, and explains these contract failures. This does not explain every historical upstream error.
2. **HTTP429:**19 stored failures for one affected pipeline were `RATE_LIMIT_EXCEEDED`;5 were distinct upstream model errors. Previously no bounded429 retry existed. The client now respects numeric/HTTP-date Retry-After, exponential delay with jitter, at most2 retries and30seconds elapsed retry budget. A delay outside that budget returns a truthful rate-limit failure instead of retrying early.422 is never retried. Existing bounded task/batch admission is unchanged; no DET cache was introduced.
3. **Terminal navigation:** the old UI handled only `completed`, removed its local reference immediately, and did not validate results. It now verifies persisted usable results before navigating for completed/partial jobs, retains the reference, acknowledges opening only when GT has loaded, and prevents repeated automatic navigation per job. Failed/cancelled jobs never become success merely at100%.
4. **Preview state:** viewport dimensions were part of the manual-view identity, so a resize invalidated manual zoom/pan. Identity now uses source/page and source dimensions, with optional per-tab view recovery. Fit/reset remains explicit; a different source fits independently.
5. **Field focus:** the parent map referred to layout-list rows, not GT inputs. GT now owns immutable-ID input refs and its scroll container; a preview click focuses without scrolling the whole page. Typing/focus from GT changes selection without resetting zoom or caret.

## Requirement outcomes and regression guards

| Requirement | Implementation / evidence |
|---|---|
| REQ-01 | Source-specific view persistence; viewport resizing does not discard manual zoom. Fit/zoom/100%/reset and explicit image-load recovery remain available; Crop Preview adds100%/reset/retry. Desktop/mobile/image/PDF checks required below. |
| REQ-02 | Global normal outline1.25screen pixels, selected2; editable ROI1.5. `strokeScaleEnabled=false`; source coordinates unchanged. |
| REQ-03 | Separate outline, label and selected-field visibility controls; selected editable ROI label follows the same label control. |
| REQ-04 | Selected violet/fill, normal blue, missing-GT red, OCR failure amber/dashed; text labels distinguish missing GT from OCR error. |
| REQ-05 | Persisted results validated before completed/partial navigation; warning at GT for partial results; retained results link and local ID; failed/cancelled remain actionable. |
| REQ-06 | Queued/running/terminal copy, successful versus failed units, completed pipelines, elapsed wall time and server update timestamp are distinct. Progress remains checkpoint-derived. |
| REQ-07 | Missing-field input/preview indicators derive from current draft GT and update immediately; existing Whole/Sub-field synchronization is retained. No automatic confirmation. |
| REQ-08 |38-field browser fixture verifies preview→GT focus/local scrolling and GT→preview selection; manual scale survives resize/reload. |
| REQ-09 | Reuse existing native result dialog for a specific field as well as whole pipeline; GT and safe failure code retained, Escape/close/focus return supported. No inference from inspection. |
| REQ-10 | Existing code-point metrics/alignment unchanged. Grapheme display retains missing-mark/deletion evidence; isolated combining marks use dotted-circle display and erroneous spaces/tabs/newlines get visible glyphs. |
| REQ-11 | Existing concise default summaries and on-demand full detail retained; no duplicate full error panels added and no evidence discarded. |
| REQ-12 | **OUT OF SCOPE** — not implemented. |
| REQ-13 | PostgreSQL jobs/leases/heartbeat/checkpoints/idempotency retained. Poll/result guards remain compact; no synchronous browser `/run` restored. Missing source fails safely.494-unit isolated acceptance required below. |
| REQ-14 | Safe allowlisted diagnostic toggle implemented, no OCR request. **Internal-only access BLOCKED:** current production has no authentication/roles. The UI explicitly states this is not access control; no secret-environment/raw-response viewer or misleading permission claim. |

## Compatibility and privacy

Current registered DET/REC paths are authoritative. Benchmark remains DET6/REC5 without model/engine parameters; Thai FT v2 remains DET6/REC6 with `model=thai_ft_v2`. Mint/Hutch routing, ROI, metric normalization/edit totals/confidence, persisted GT, Dataset labels, compact History and deployment settings are unchanged.

The raw-only compatibility path copies **only** DET polygons/scores or REC text/score/model into the existing result contract, preserving list order. It rejects mismatched counts/missing required keys and drops images/tensors/input paths/font objects. Existing structured results remain authoritative. Failures carry stage, status and correlation IDs; field logs contain IDs/codes only, never document/OCR/GT, unrestricted exceptions or credentials. No cross-user diagnostic search is added.

## Validation record

Baseline artifacts are retained under ignored `.runtime/jobs/`. Baseline full backend466passed/55failures; baseline full Playwright128passed/34failures, plus final focused9passed after that run. Existing failures must not be relabeled passed or disabled.

Current execution artifacts are isolated under ignored `.runtime/audit/`. Full results, failure-set comparison, resource/recovery evidence and final release state are appended after execution. Synthetic live Job API against the affected DET6thai_ft_v2/REC5thai_ft_v6 pair already completed2/2 fields with real boxes/confidence/traces and confirmed ThaiGT CER0/WER0/ExactMatchtrue. It uses an isolated local DB/storage, not production user records or a shared-Gateway stress test.

### Executed final results

- Backend535cases: **480passed/55unchanged baseline failures/0skipped**; no new failure IDs. Fourteen new compatibility/rate-limit/stage cases pass.
- Complete Playwright171cases: **137passed/34unchanged baseline failures**; no new failure titles. Focused final36/36 also passes. The earlier169-case run exposed one stale assertion forbidding Reset in read-only GT; it now explicitly requires Reset while still forbidding ROI-edit/delete tools. The complete suite was rerun, not merely relabeled passed.
- TypeScript, ESLint and Next production build pass. Standalone output exists. Changed Python files RuffPASS; whole-repo7pre-existing import findings remain (one changed-file baseline import was corrected). No tests removed/disabled.
- New isolated PostgreSQL database upgraded clean→0011→0012; Alembic check reports no drift. No new migration, schema rewrite, environment variable or deployment configuration change.
- Local512000000bytes/1CPU, **38fields×13pipelines**:494correct and unique persisted outputs,494confidence/traces,380real DET geometries (recognition-only fields have no fabricated geometry),971.57seconds,282mock Gatewaycalls.330seconds without backendHTTP; controlled worker replacement plus subsequent kill resulted in attempt3 and preserved all104checkpoint IDs observed before the kill. Final resource snapshots: RSS309313536bytes, cgroup477556736bytes (includes cache), noOOM/oom_kill. These are synthetic size-matched REC responses, not a shared-CDGS capacity certificate. Cgroup headroom remains limited.
- Real CDGS via isolated local FastAPI Job API: **both** affected configurations pass2/2fields: DET6baseline→REC5thai_ft_v6 and DET6thai_ft_v2→REC5thai_ft_v6. Actual boxes/confidence/traces and confirmed ThaiGT CER0/WER0/ExactMatchtrue. No model records in production changed and no production document used as payload.
- Browser regression covers partial/failed/cancelled states, persisted-result-read retry before navigation, refresh/idempotency,38-field bidirectional focus/local scrolling, zoom retention, independent label controls, modal field/whole identity/Escape/focus return, Thai combining/deletion evidence, image/PDF/GT/History/Comparison/Dataset/Excel/ZIP workflows. Separate local mobile source404→retry→portraitFit/100%/Reset check passes without OCR. Early standalone harness await/float-comparison mistakes were fixed; they were not product failures.
- Exact private key/DB URL/password scanPASS (values withheld); `.env` and `.runtime` ignored/untracked, diff check and docs linksPASS. Metrics/normalization/Dataset labels/authentication/provider settings unchanged.
- Safe aggregate evidence: [workflow audit results](../postman/staging/workflow-audit-results.json). Private logs/XML/connection files stay in ignored runtime storage.

### Release state

Backend fix commit `47ac5e9`; frontend fix commit `7b6e2c8`. Production is **unchanged**, not claimed verified for this fix. A read-only check confirmed currently available sources among the latest Dataset samples and no Railway volume. Permission for encrypted original-source backup/local restore/restore-after-deploy is pending. Do not merge an auto-deploying change until that source-preservation gate is resolved. Internal-only debug permissions also remain explicitly unsupported without an actual access-control mechanism; the implemented toggle exposes only existing safe case diagnostics and does not claim authorization.

YouTube meeting page could not be retrieved by the available web tool; this implementation uses the supplied explicit requirements rather than inventing a transcript.

## Deployment safety

No new required environment variable, paid resource, schema migration, secret change or destructive operation. Deployment remains gated on regression/494-unit acceptance. Current production before this change: Vercel READY on695bf4b; Railway deployed64c23a7 (frontend-only merge skipped), observed SLEEPING, not evidence of a crash. No intentional production restart is used for recovery testing.

Uploads remain ephemeral on Railway container replacement. Historical missing originals cannot be reconstructed from DB records. A7November release must report actual available-source protection/recovery status; no blanket source-preservation claim. Previously authorized encrypted DB backup/local restore from5November is retained, but is not a current storage backup or verified Neon PITR. Historical worker/container termination and upstream model errors remain unconfirmed unless provider evidence identifies them.
