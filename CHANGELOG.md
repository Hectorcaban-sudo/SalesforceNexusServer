# Changelog

## 1.2.10 — 2026-09-30

### Processors
- Harden POST `/api/processors` upload (safe filename, empty-file 400, store errors returned as detail)

### OpenTelemetry
- Removed OTEL packages from requirements
- `tracing.py` is a no-op stub so worker/CometD imports still work
- FastAPI OTEL instrumentor no longer wraps the app (it could break multipart uploads)
