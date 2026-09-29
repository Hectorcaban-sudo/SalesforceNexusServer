# Changelog

## 1.2.7 — 2026-09-29

### SharePoint
- Create connection / file action / list action now stores `project_id` from the selected project
- List/API responses include `project_id` so the project filter no longer hides a just-saved connection

## 1.2.6 — 2026-09-28

### Dataiku Phase A
- Reuse one `DSSClient` + LLM handle in-process
- Background warmup on API start
- `DSS_USE_SUBPROCESS` fallback; `DSS_TIMEOUT_SECONDS` default 180

## 1.2.5 — 2026-09-28

- Integrations fire only when the flow names them

## 1.2.4 — 2026-09-28

- Restored integrations; `requests_timeout` import
