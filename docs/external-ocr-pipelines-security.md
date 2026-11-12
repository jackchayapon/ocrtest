# External OCR security boundary

OCRLab intentionally has a public shared workspace without login, accounts, roles, sessions, ownership or approval. Every visitor can create/edit/test/disable/delete shared External API configurations. `EXTERNAL_OCR_PROVIDERS` and `EXTERNAL_OCR_SECRET_*` remain backward-compatible server registrations; HTTP cannot overwrite them or copy their secrets. Editing one creates a separate DB provider and requires a newly supplied key.

Shared credentials use server-side Fernet authenticated encryption with `EXTERNAL_OCR_ENCRYPTION_KEYS` (one key, or a comma-separated new/old key ring of up to three). Ciphertext binds the provider ID and canonical endpoint origin. GET returns only `api_key_configured`, never plaintext or ciphertext. Replace/remove are explicit write actions. Changing origin cannot keep or resubmit the old key. Public config fields cannot contain the active credential. Browser inputs use `type=password`, stay in transient component state and are cleared after submissions; no browser storage or frontend encryption is used.

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

The shared application can consume provider quotas through explicit Jobs. Additional process-local shared ceilings are30 configuration writes/minute,20 connection checks/minute,600 inference requests/minute,50 DB providers and2 active External HTTP requests with no unbounded connection queue. Configuration bodies are limited to64KiB and10seconds total. JSON responses are checked for at most50,000 events and32 container levels before allocating the final Python graph. Existing80 Fields×3 selected Pipelines, single executor, queue and image/crop limits remain unchanged.

These fixed-window budgets apply to the existing single-process/single-replica deployment and reset on restart; they are not distributed abuse prevention. Anonymous visitors can replace/delete shared configurations, disrupt others' work, exfiltrate shared document contents to their chosen **public** provider, or consume shared provider quotas. SSRF protection prevents access to private infrastructure but does not prevent these intentional public-workspace capabilities. Use synthetic/non-sensitive demonstration data and provider-side budget controls. No authorization or abuse-proofing claim is made.

Do not lose or overwrite the server encryption key: database backups alone cannot decrypt credentials. Rotation installs `new,old`, replaces each saved credential, verifies it, then removes the old key after all ciphertext has migrated. Missing/wrong keys fail closed. Application rollback retains the additive table and encryption keys; do not run a production downgrade that drops saved providers. See [release and recovery](external-ocr-shared-release.md).
