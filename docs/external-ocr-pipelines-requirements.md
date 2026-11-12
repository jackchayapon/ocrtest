# External OCR Pipeline requirements

The feature adds a standalone OpenThai CPU service under `api/openthai2_ocr_text`, an OCRLab remote adapter under `backend`, and an Internal/External source selector under `frontend`. All changes share one feature branch based on current main `3440dbe98a56f38097c4eecf5413d4439d81aa39`.

| Area | Acceptance |
| --- | --- |
| Standalone API | Independent install, model provisioning, startup, HTTP tests and Docker build context |
| Real inference | Pinned open-source ONNX weights, startup integrity checks, one reusable model, synthetic Thai/English and blank actual HTTP requests |
| Existing models | Current Custom DET/REC and Official/Paddle creation/editing, routing and normalizers continue through their established adapters |
| External settings | Operator-approved providers, POST multipart or JSON Base64, validated response adapters, environment credential references |
| Public Settings | Users select approved providers, name/enable pipelines, test saved readiness and update selections |
| Data | Existing PipelineConfig JSON storage, stable Pipeline IDs, existing Job snapshots, persisted safe provider fingerprint and model revision |
| Scheduling | Existing HTTP202 durable Jobs, Pipeline-first Field execution, incremental persistence and failure isolation |
| Workload | Existing80 Fields×3 selected Pipelines, maximum240 logical units |
| Metrics | Standard PipelineResult text, unchanged normalization/CER/WER/Exact Match, History/Comparison/Export |
| Geometry | Actual supplied polygons mapped from crop to document coordinates once, provider text order retained, text-only status visible |
| Safety | DNS-pinned approved destinations, HTTPS by default, redirect rejection, bounded transfer/deadline, credential isolation |

Server-operator registration is the administrative workflow for endpoint and credential changes. Public browser requests contain an approved provider ID and presentation options. Provider configuration and credential updates require control over server environment and the standard infrastructure release process.

REQ-12 remains out of scope. CDGS production/Gateway configuration, hosting plans, production secrets and production data operations require separate authorization.
