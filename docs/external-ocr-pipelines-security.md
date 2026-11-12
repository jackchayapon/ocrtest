# External OCR security boundary

OCRLab has a public shared workspace. Visitors can read/edit shared records and select approved pipelines. The operator maintains `EXTERNAL_OCR_PROVIDERS` in Backend environment configuration. Provider credentials reside in dedicated `EXTERNAL_OCR_SECRET_*` variables. The public definition schema forbids endpoint, token and arbitrary header fields. Arbitrary provider registration through public HTTP is rejected.

Example local configuration uses a synthetic secret configured independently on the standalone service.

```ini
EXTERNAL_OCR_DEVELOPMENT=true
EXTERNAL_OCR_PROVIDERS={"openthai":{"name":"OpenThai Local","endpoint":"http://127.0.0.1:8091/api/v1/ocr-text","readiness_url":"http://127.0.0.1:8091/api/v1/readiness","request_format":"multipart","image_field":"image","response_adapter":"openthai_v1","auth_mode":"bearer","credential_env":"EXTERNAL_OCR_SECRET_OPENTHAI"}}
EXTERNAL_OCR_SECRET_OPENTHAI=<private-service-key>
```

For a deployed approved HTTPS endpoint, leave `EXTERNAL_OCR_DEVELOPMENT=false`. URLs require absolute exact paths, HTTPS and absence of credentials, query strings, fragments or control characters. The development flag admits loopback HTTP and loopback IPs only as an explicit server configuration exception. Private, link-local, metadata, multicast, reserved and IPv6 transition addresses are blocked. Internal production networking can use an approved HTTPS proxy with a globally routable destination. This initial adapter keeps private-address access disabled in production.

Each actual TCP connection resolves the approved hostname again. Every DNS answer must be allowed. The transport connects to the validated IP address while preserving original HTTP Host and TLS SNI/certificate validation. Redirects are rejected, proxy environment variables are ignored and no automatic retries occur. The transport hook uses pinned httpx0.28.1/httpcore1.0.9 internals and requires regression review on dependency upgrades.

Provider response reads have a byte cap, Content-Length early rejection, identity encoding and an overall deadline. Request inputs use the existing crop/upload ceiling. Multipart streams reuse canonical bytes through a file cursor. JSON Base64 is an explicit opt-in provider contract with bounded input overhead. Deeply nested/invalid JSON and schema/geometry mismatches produce sanitized per-pipeline errors. Allowed auth modes are none, Bearer, X-API-Key and custom header from `X-API-Key`, `X-Auth-Token`, `Api-Key`.

Secrets are excluded from config JSON, Job snapshots, provenance, errors and logs. Raw/JSON-decoded provider responses containing the configured credential are rejected before persistence. Only bounded safe upstream request IDs and numeric timing enter diagnostics. API text and geometry remain document data governed by the existing public-workspace policy.

Connection testing sends GET only to the registered same-origin readiness URL. Responses distinguish configuration-only, reachable and provider-reported ready. Inference success requires a deliberate OCR Job. An upstream error never triggers a fallback request to another destination.

The shared public application can consume approved service quotas through explicit Jobs. Operators must apply ingress rate/connection controls and provider budget limits suitable for the intended deployment. This feature supplies an endpoint/credential administrative boundary through server configuration. The workspace's broader public data access policy remains documented separately.
