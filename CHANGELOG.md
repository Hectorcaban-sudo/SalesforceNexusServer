# Changelog

## 1.4.0 — 2026-10-08
### Flow designer and transactions
- Publish nodes on the continuing path wait until it finishes; `side` / `isolated` edges run as child transactions.
- Each visited node is recorded as `flow_trace`; Transactions has a **Trace** tab (input/output per node) and the timeline follows the trace.
- Transactions time filter adds Last 7d, Last 30d and a custom date range.
- **Flow action** node in the palette; Templates page (`/templates`) to list, import, edit and delete flow templates.
- Chroma pipeline results are published in the DSS event schema.

### Flow actions
- Reusable flow actions: Salesforce get, Salesforce delete, SharePoint file (optional replace existing), and Chroma.
- A Chroma action calls the saved Chroma processor and returns the hits, including document and metadata, to the next node.
- Flow actions page at `/flow-actions`, under the project navigation.
- Processor mode `flow_action` runs one saved action. Processor mode `pipeline` runs another saved pipeline and returns its result.

### Pipelines
- A pipeline can be created from the Pipelines page with no event. Source shows as standalone.
- NBF ContentDocument template: `examples/nbf_content_document_pipeline.json`. New pipeline can start from that template.

## 1.3.0 — 2026-10-07
### Chroma
- Chroma is now selectable as a processing mode: global mode pill (with processor picker), flow
  designer Processor node, and per-event routing.
- Fixed `/api/chroma/query`: `n_results` is honored and free text is no longer rendered as Jinja.
- `cert_id` validated against path traversal; CA cert PEMs are included in configuration
  export/import.
- Chroma page uses the toast system correctly and reports load/save errors.
- Removed dead `chroma_flow.py`.
- Example transform for publishing Chroma document and metadata in the DSS event schema: `examples/chroma_dss_transform.j2`.
- Chroma processors can be edited and deleted. Add, edit, and test open in dialogs. Administration holds global processors; the project page holds project processors.

### Admin console
- Toasts on saves across the admin console; read-only Processors viewer; two-pane Logs with
  transaction linking; `NEXUS_TRANSACTION_ID` passed to processors with unbuffered stderr.

## Transactions console
Three-pane Transactions page: stream filters (org, channel, time, hide skipped), Event group tabs (Related events / Pipeline run), Inspector (Payload / Result / Error).
