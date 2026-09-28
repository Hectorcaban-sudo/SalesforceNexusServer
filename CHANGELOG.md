# Changelog

All notable Nexus Server changes since the 1.0 baseline.

## 1.2.3 — 2026-09-28

### Scheduled jobs management
- Edit existing jobs (name, org, SOQL, cron, pipelines, enabled)
- Enable / disable without deleting (APScheduler reloads)
- Delete from the list (operator role; was admin-only)
- Run still available on each row

## 1.2.2 — 2026-09-28

### UX
- Processor Python editor pane scrolls (textarea owns wheel)
- Checkboxes/radios no longer inherit `input { width: 100% }` (fixes giant empty squares on Scheduled jobs)

### Standalone pipelines
- Create a pipeline with no Salesforce subscribe event (`POST /api/pipeline-catalog`)
- `GET` / `PUT /api/pipeline-catalog/{id}` for load/save graph
- Route `/pipelines/:pipelineId/flow`
- Scheduled job modal: **+ Standalone pipeline**
- Catalog Open flow uses the standalone route when `event_id` is empty

## 1.2.1 — 2026-09-28

- Removed leftover git stash conflict markers (`<<<<<<<`) from merged files (main, scheduler, health, metrics, Alembic, catalog, schedules, processors UI, highlighter, backup doc, event_service, sharepoint_runtime)

## 1.2.0 — 2026-09-27

### Scheduled jobs
- APScheduler cron engine (`backend/app/scheduler.py`)
- Admin screen: SOQL + cron + target pipeline IDs
- Tick runs SOQL on the selected org and publishes one inbound message per record (or one batch)
- Same graph walker as CometD events
- `apscheduler==3.10.4` in `backend/requirements.txt`

### Pipelines catalog
- Project page listing every flow (event-backed and later standalone)
- Filter by org; Open flow

### Processor editor
- View/edit as a modal with lightweight Python syntax colors (keywords, strings, comments)
- Validate (`ast.parse`) and save project processors; globals remain read-only on the project screen

## 1.1.1 — 2026-09-27

- Processor and rule list responses include `project_id` (uploads stay on the selected project)
- View global processors from Admin as well as the project library
- Validate / save processor source endpoints

## 1.1.0 — 2026-09-27

- Phase A in-app Python viewer/editor for custom processors
- Application versioning (`VERSION`, `CHANGELOG.md`, health payload version)

## 1.0.0 — 2026-09-27

### Multi-tenant projects
- Projects table; default project bootstrapped for existing orgs/events/integrations
- Project-scoped events, integrations, SharePoint, alerts, processors, rules
- Global processor/rule library (null `project_id`), shown read-only on project screens
- Project switcher in the header; nav grouped under Monitor / Project / Administration
- Transactions and logs include project
- Export/import includes projects and associations

### Events and flows
- Events catalog grouped by Salesforce org
- Multiple named pipelines per subscribe event (serial execution, child transactions)
- Visual flow designer (React Flow): source, schema, rule, processor, transform, publish map, publish, integration, alert, if/else, switch, stop
- Graph persisted as `flow_graph` JSON (layout included)
- Real walker is the runtime (not flattened event fields alone)
- Save flow as template; export PDF; dry-run test
- Stop-without-processor marks the transaction terminal (no stuck queued)
- Pipeline name + description

### Subscribe / publish quality
- Per-event JSON Schema + sample import; reject-on-fail option
- Publish field mapping and Jinja2 result transform from processor output
- Multi integration hooks per event / walker node

### SharePoint (GCC High)
- Tenant connections in Admin (client credentials); Test connection
- File processor (create file, folder, metadata) and list processor (create/update)
- Manual site/drive/list IDs when Graph search returns 403
- Reuse the org’s Salesforce session (no second simple_salesforce login)
- Integration-style fan-out targets as well as processor modes

### Integrations
- Teams and other sinks; Jinja/body transform for cards
- Project-scoped alerts fired through integrations
- Per-sink circuit breaker and dead-letter after N retries

### Operations / production baseline
- `/healthz` liveness vs `/readyz` readiness (Salesforce outage does not fail liveness)
- Explicit outbound timeouts
- Structured JSON logs (correlation, project, event/job, status, latency)
- Queue / walker metrics; `/metrics` Prometheus text
- Docker Compose: Postgres, RabbitMQ, Nexus network, resource limits, volumes
- Alembic baseline + backup/restore notes
- Thin routers; event service; SharePoint/integration/worker service extraction (partial)

### UI shell
- Dashboard aligned to projects / pipelines / schedules
- Notification bell and help icon (docs URL in Admin)
- Transactions screen shows pipeline
- Collapsible left nav sections

### Dataiku
- `/api/execute/dss-client` test chat on the DSS admin tab; reply text with optional raw JSON

## Unreleased / follow-ups

- Full domain-folder layout (`app/domains/...`) for every feature
- Persistent notification inbox (mark-all-read policy)
- Designer load path for standalone pipelines on GitHub (local already patched)
- SQL tables replacing the document store (Alembic 001 is still a no-op)
