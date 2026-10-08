# Changelog

## Unreleased
### Chroma
- Example transform for publishing Chroma document and metadata in the DSS event schema: `examples/chroma_dss_transform.j2`.
- Chroma processors can be edited and deleted. Add, edit, and test open in dialogs. Administration holds global processors; the project page holds project processors.

## 1.3.0 — 2026-10-07
### Chroma
- Chroma is now selectable as a processing mode: global mode pill (with processor picker), flow
  designer Processor node, and per-event routing.
- Fixed `/api/chroma/query`: `n_results` is honored and free text is no longer rendered as Jinja.
- `cert_id` validated against path traversal; CA cert PEMs are included in configuration
  export/import.
- Chroma page uses the toast system correctly and reports load/save errors.
- Removed dead `chroma_flow.py`.

### Admin console
- Toasts on saves across the admin console; read-only Processors viewer; two-pane Logs with
  transaction linking; `NEXUS_TRANSACTION_ID` passed to processors with unbuffered stderr.

## Transactions console
Three-pane Transactions page: stream filters (org, channel, time, hide skipped), Event group tabs (Related events / Pipeline run), Inspector (Payload / Result / Error).
