# Changelog

## 1.2.7 — 2026-09-29

### SharePoint save / project scope
- New `backend/app/sharepoint_models.py` includes `project_id` on connection, file action, and list action
- Router create paths stamp `project_id` so the project filter no longer hides a just-saved connection
- UI helper `frontend/src/lib/withProject.js` — SharePoint save should send `withProject(form, projectId)`

## 1.2.6 — 2026-09-28

- Dataiku in-process client + warmup
