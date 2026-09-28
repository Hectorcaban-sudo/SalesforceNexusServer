# Changelog

All notable Nexus Server changes since the 1.0 baseline.

## 1.2.4 — 2026-09-28

### Integrations
- Restored `backend/app/integrations.py` after it was accidentally truncated to two lines on GitHub
- Import `requests_timeout` at module level so Teams, Slack, custom API, and webhook sinks no longer raise `NameError: requests_timeout is not defined`

## 1.2.3 — 2026-09-28

### Scheduled jobs management
- Edit existing jobs (name, org, SOQL, cron, pipelines, enabled)
- Enable / disable without deleting (APScheduler reloads)
- Delete from the list (operator role; was admin-only)
- Run still available on each row

## 1.2.2 — 2026-09-28

### UX
- Processor Python editor pane scrolls (textarea owns wheel)
- Checkboxes/radios no longer inherit `input { width: 100% }`

### Standalone pipelines
- Create a pipeline with no Salesforce subscribe event (`POST /api/pipeline-catalog`)
- `GET` / `PUT /api/pipeline-catalog/{id}` for load/save graph
- Route `/pipelines/:pipelineId/flow`
- Scheduled job modal: **+ Standalone pipeline**

## 1.2.1 — 2026-09-28

- Removed leftover git stash conflict markers from merged files

## 1.2.0 — 2026-09-27

- APScheduler scheduled jobs (SOQL + cron → inbound walker)
- Pipelines catalog
- Processor modal with Python syntax highlighting
- `apscheduler==3.10.4`

## 1.1.1 — 2026-09-27

- Processor/rule list includes `project_id`; view globals; validate/save source

## 1.1.0 — 2026-09-27

- Phase A processor editor and application versioning

## 1.0.0 — 2026-09-27

- Projects and global library
- Multi-pipeline events and visual flow walker
- Schema validation, Jinja transform, publish field map
- SharePoint GCC High file/list processors
- Integrations (Teams and other sinks), circuit breaker
- /healthz /readyz, structured logs, Compose stack
- Dashboard, notifications, help, transactions pipeline column
- Dataiku DSS test chat
