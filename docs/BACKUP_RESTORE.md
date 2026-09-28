# Backup and restore

## What to back up

<<<<<<< Updated upstream
1. Compose volumes: nexus-postgres-data, nexus-data, nexus-logs, nexus-rabbitmq-data, nexus-flowise-data
2. Admin Export configuration JSON (treat as secrets)

## Postgres dump

```bash
docker compose exec -T postgres pg_dump -U nexus nexus > nexus-$(date +%F).sql
docker compose exec -T postgres psql -U nexus nexus < nexus-YYYY-MM-DD.sql
```

## Alembic

`backend/alembic` revision 001 is a no-op baseline while the document store is live. Add CREATE TABLE migrations when SQL tables replace Tinydb, then `alembic upgrade head`.
=======
1. **Compose volumes**
   - `nexus-postgres-data` (if `DATABASE_TYPE=postgres`)
   - `nexus-data` (`/app/data` — Tinydb/SQLite config + processors)
   - `nexus-logs`
   - `nexus-rabbitmq-data` (queues; optional if you accept empty queues after restore)
   - `nexus-flowise-data`

2. **Admin → Export configuration**  
   JSON bundle of projects, orgs, events, pipelines (via event `flow_graph`), integrations, SharePoint, rules, processors. Treat it as a secrets file.

## Postgres dump (Compose)

```bash
docker compose exec -T postgres pg_dump -U nexus nexus > nexus-$(date +%F).sql
```

Restore:

```bash
docker compose exec -T postgres psql -U nexus nexus < nexus-YYYY-MM-DD.sql
```

## Data volume

```bash
docker run --rm -v nexus-data:/data -v "$PWD":/backup alpine tar czf /backup/nexus-data.tgz /data
```

## Schema migrations

Alembic lives in `backend/`. Today revision `001` is a no-op baseline because runtime config is still the document store.

When SQL tables are added:

```bash
cd backend
alembic revision -m "add pipelines table"
alembic upgrade head
```

Test restore on a throwaway Compose stack before relying on it in GCC High.
>>>>>>> Stashed changes
