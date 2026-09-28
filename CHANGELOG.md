# Changelog

All notable Nexus Server changes since the 1.0 baseline.

## 1.2.5 — 2026-09-28

### Integrations (bugfix)
- A pipeline no longer fans out to every enabled integration
- `dispatch_integrations` requires an explicit ID list; `None` / `[]` fires none
- Walker still passes the single node `refId` for each integration step
- Event `route_integration_ids` empty list means none (no more legacy auto-match-all)

## 1.2.4 — 2026-09-28

- Restored truncated `integrations.py`; module-level `requests_timeout`

## 1.2.3 — 2026-09-28

- Edit / disable / delete scheduled jobs

## 1.2.2 — 2026-09-28

- Checkbox and editor scroll fixes; standalone pipelines

## 1.2.1 — 2026-09-28

- Stash marker cleanup

## 1.2.0 — 2026-09-27

- Scheduled jobs, pipeline catalog, processor modal

## 1.1.1 / 1.1.0 / 1.0.0

- See previous tags for projects, walker, SharePoint, ops baseline
