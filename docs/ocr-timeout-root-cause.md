# OCR request timeout and CORS

Read-only Railway proxy evidence on5November2026 for the reported case confirmed OPTIONS200 and multiple POST `/run` disconnects at300009/300015/300002ms. Railway describes these as “client has closed the request before the server could send a response” (HTTP499). A shorter earlier disconnect also exists. Gateway inference continued after browser disconnection according to the incident evidence. This establishes a long-lived HTTP execution problem; it does not identify which client/intermediary imposes the effective five-minute lifetime.

Production preflight for the new `/jobs` path already returned200 with `Access-Control-Allow-Origin: https://ocrtest-sandy.vercel.app` before deployment. This does not mean the old application has a jobs route: CORSMiddleware can answer OPTIONS for an unmatched path. Normal application validation/error responses and actual job APIs require separate verification.

The missing CORS header on a proxy-generated502 is a secondary symptom consistent with the incident, not proof the allowed-origin list is wrong. FastAPI cannot attach headers to a response generated outside the application. This change keeps explicit allowed origins and makes sanitized application500 responses pass through outer application CORS middleware. It does not claim to repair proxy CORS by middleware.

The fix is short committed202 submission + persisted progress/results, not larger browser/Gateway timeouts. OCR remains bounded and may still take many minutes. No inference-speed claim is made solely because it is queued. Historical422/model-worker causes remain separate and unresolved without upstream error evidence; there is no blind422 retry.
