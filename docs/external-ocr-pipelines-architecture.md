# External OCR architecture

The standalone wrapper now implements sequential multi-image Batch for local testing and CDGS handover. OCRLab retains per-Field single-image requests and existing durable checkpoints. The supplied live single-image URL is `https://websolution.cdgs.co.th/paddle/api/v1/openthai-text`. Public Batch routing has not been confirmed. Enabling Batch in OCRLab requires a verified route and an explicit recovery/idempotency design for partially completed requests. See [the handover](../api/openthai2_ocr_text/docs/CDGS_HANDOVER.md).

```mermaid
flowchart LR
  UI[Next.js Pipeline Settings] --> API[OCRLab FastAPI]
  API --> Config[PipelineConfig JSON provider identity]
  API --> Jobs[Existing durable Jobs and checkpoints]
  Jobs --> Manager[PipelineManager]
  Manager --> Internal[Existing Custom and Official adapters]
  Manager --> External[ExternalOCRAdapter]
  External --> HTTP[Shared provider and DNS-pinned HTTP]
  HTTP --> OpenThai[Standalone OpenThai service]
  OpenThai --> Model[Local ONNX CPU models]
  Manager --> Result[Existing PipelineResult and incremental persistence]
  Result --> Views[GT Evaluation History Comparison Export]
```

The mode/source is `external_api`. Existing `pipeline_configs.dynamic_mode` and `source` strings accept it. JSON `integrated_options` stores only provider ID/name, adapter and the public routing fingerprint, with null DET/REC selections. Migration0013 adds a single `external_providers` table for shared public configuration and authenticated encrypted credentials. A separate table is necessary to keep ciphertext and credential lifecycle outside existing PipelineConfig serialization, Job snapshots and exports, and to support shared provider references. No existing application table is altered; no login/session tables exist.

`DynamicPipelineInput` validates a saved provider ID without DET/REC IDs. `DynamicPipelineService` resolves it server-side. `/api/external-pipelines` saves a provider and Pipeline atomically; `/api/external-providers` offers public shared CRUD. Public config serialization exposes `external_provider` identity and keeps integrated model options separate. Existing snapshot/restore functions persist these fields for durable Jobs.

Execution merges immutable environment registrations with enabled database providers, then compares the saved Job fingerprint. Editing a DB provider updates referencing PipelineConfigs for future Jobs atomically, while accepted Job snapshots remain unchanged and fail closed on routing changes. Credential rotation preserves the public fingerprint. Origin changes invalidate the old key and require a different credential. Deleting a referenced provider returns409. Safe run provenance retains provider ID/name/adapter/fingerprint, genuine geometry availability and validated model revision; credentials and upstream envelopes are excluded.

External adapters receive the same canonical PNG crop/ROI as other pipelines. The Backend performs one POST per logical Field execution without automatic retry. Existing checkpoint uniqueness prevents replay of committed outputs. A request interrupted before its output commits can be repeated after worker recovery. Existing GT prefill selects its established Custom DET/REC configuration and keeps its existing behavior.

OpenThai normalization preserves `data.text` and line order. Native polygons are converted with the existing geometry mapper and ROI offset once. Generic text JSON uses a maximum-four-component dotted dictionary path. Aggregate confidence stays null unless explicitly supplied by a configured generic provider. Shared normalization/scoring functions process the final text.

`global_layout_service.reading_lines` recognizes the external crop stage and preserves full provider text ordering, including multi-column order. Text-only outputs have an empty geometry list and a visible geometry-unavailable message in Pipeline preview. Global Field ROI outlines still show the user-selected crop.

The standalone package owns its dependencies, Dockerfile, read-only model snapshot, config, endpoints and tests. OCRLab Railway installs the HTTP adapter dependencies only. Model inference runs in the separately deployed service.
