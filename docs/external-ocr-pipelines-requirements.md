# External OCR Pipeline requirements

The feature adds a standalone OpenThai CPU service under `api/openthai2_ocr_text`, an OCRLab remote adapter under `backend`, and an Internal/External source selector under `frontend`. All changes share one feature branch based on current main `3440dbe98a56f38097c4eecf5413d4439d81aa39`.

| Area | Acceptance |
| --- | --- |
| Standalone API | Independent install, model provisioning, startup, HTTP tests and Docker build context |
| Real inference | Pinned open-source ONNX weights, startup integrity checks, one reusable model, synthetic Thai/English and blank actual HTTP requests |
| Existing models | Current Custom DET/REC and Official/Paddle creation/editing, routing and normalizers continue through their established adapters |
| External settings | Everyone can enter/edit URLs, POST multipart or JSON Base64, image field, bounded response paths and adapter |
| Public Settings | No login, roles, sessions or approval. Shared create/edit/test/enable/disable/delete with write-only masked keys |
| Data | PipelineConfig JSON keeps public identity only; one additive provider table separates encrypted credentials from Job snapshots |
| Scheduling | Existing HTTP202 durable Jobs, Pipeline-first Field execution, incremental persistence and failure isolation |
| Workload | Existing80 Fields×3 selected Pipelines, maximum240 logical units |
| Metrics | Standard PipelineResult text, unchanged normalization/CER/WER/Exact Match, History/Comparison/Export |
| Geometry | Actual supplied polygons mapped from crop to document coordinates once, provider text order retained, text-only status visible |
| Safety | DNS-pinned approved destinations, HTTPS by default, redirect rejection, bounded transfer/deadline, credential isolation |

The latest explicit product correction supersedes administrator/approved-provider-only requirements. All visitors have equal access to shared provider management. Existing environment registrations remain immutable through HTTP; editing one creates a separate database configuration and requires an independently supplied credential. There is no user/account/organization system. Anonymous visitors can disrupt shared configuration or consume provider quotas; this is an accepted product risk, not an access-control claim.

REQ-12 remains out of scope. This release deploys OCRLab only to its existing services; standalone OpenThai and CDGS infrastructure are unchanged. No paid hosting or destructive database changes are authorized.
