# Backup and restore

## What to back up

1. Compose volumes: nexus-postgres-data, nexus-data, nexus-logs, nexus-rabbitmq-data, nexus-flowise-data
2. Admin Export configuration JSON (treat as secrets)

## Postgres dump

```bash
docker compose exec -T postgres pg_dump -U nexus nexus > nexus-$(date +%F).sql
docker compose exec -T postgres psql -U nexus nexus < nexus-YYYY-MM-DD.sql
```

## Alembic

`backend/alembic` revision 001 is a no-op baseline while the document store is live. Add CREATE TABLE migrations when SQL tables replace Tinydb, then `alembic upgrade head`.
