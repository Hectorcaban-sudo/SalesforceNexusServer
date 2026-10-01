# Changelog

## 1.2.11 — 2026-09-30

### Fix: events stuck after OpenTelemetry removal
- `start_span()` / `inject_trace_context()` now accept the keyword args the worker still passes (`org_id`, `channel`, `carrier`, `span`, `transaction_id`). The previous no-op stub rejected them and aborted processing, so transactions never left queued and logs stopped updating.

### UI
- Toast stack z-index raised so save notifications are not hidden under page chrome.
