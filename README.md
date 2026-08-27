# Salesforce Nexus AI Server

An integration server that listens for Salesforce Platform Events over the **CometD / Bayeux
streaming protocol**, hands them off to an internal message broker for processing, and publishes
the results back to Salesforce as a new event — with a React admin console (served by the same
FastAPI app) to configure orgs/channels and monitor every transaction and log line in real time.

```
Salesforce Org A ──┐                                    ┌── Salesforce Org A
Salesforce Org B ──┼─ CometD ─▶ [inbound topic] ─▶ WORKER ─▶ [outbound topic] ─▶ Publisher ─┼── Salesforce Org B
Salesforce Org N ──┘   (subscribe)   (broker)   (internal function)  (broker)   (REST API)   └── Salesforce Org N
                                                                                     ▲
                                                                    React Admin UI ─┘ (config, transactions, logs)
```

## Features

- **Multi-org support** — connect to as many Salesforce instances/orgs as you like, each with its
  own auth credentials, API version, and independent CometD connection.
- **CometD platform event subscriber** (`aiocometd_ng`) — subscribes to any Platform Event / CDC /
  custom streaming channel you configure, per org.
- **Internal message broker** — an in-process async broker (`app/broker.py`) decouples the
  Salesforce listener from the processing logic and the Salesforce publisher. It's written behind
  a small interface so it can be swapped for Kafka/RabbitMQ/SQS later without touching callers.
- **Pluggable worker/processor** — `app/worker.py:process_payload()` is the single place to plug in
  your real business logic or AI model; it receives the raw event payload and returns the result to
  publish back. If a **DSSClient** endpoint is configured (see Admin Configuration below), the
  payload is forwarded there automatically; otherwise a local fallback result is returned.
- **Salesforce publisher** — publishes the processed result back to Salesforce as a new Platform
  Event using the standard REST `sobjects` endpoint (OAuth password or client-credentials flow).
  A manual "publish test event" action is also available from the admin UI.
- **Transaction reprocessing** — requeue any single transaction, or bulk-requeue every failed one,
  back through the broker without re-sending anything from Salesforce.
- **Admin console (React)** — dashboard, org management, per-org subscribe/publish channel
  configuration, full transaction history with payload/result inspection, a live log viewer, and a
  separate **Admin Configuration** section for global settings (currently: DSSClient).
- **Local storage only** — everything is stored in a local **SQLite** database
  (`backend/data/nexus.db`). No external database or message broker required to run this.
- **Username/password protected admin** — JWT-based auth, bcrypt-hashed passwords, default
  bootstrap account (`admin` / `admin123` — change this immediately, see below).
- **Structured logging** — every component logs to a rotating file (`backend/logs/nexus.log`) *and*
  into SQLite, so the admin UI's Logs page can filter/search without touching the filesystem.

## Project layout

```
sfnexus/
├── Dockerfile                    Multi-stage build: React frontend + Python backend
├── docker-compose.yml            One-command startup with persistent volumes
├── .dockerignore
├── .env.example                  Env vars for docker-compose (SECRET_KEY, etc.)
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, lifespan startup, serves the built React app
│   │   ├── config.py            Settings (env-driven)
│   │   ├── database.py          SQLite datastore (table/query-object interface)
│   │   ├── models.py            Pydantic schemas
│   │   ├── auth.py               JWT auth + bcrypt password hashing
│   │   ├── logging_config.py     File + SQLite logging sink
│   │   ├── broker.py             Internal async pub/sub broker (inbound/outbound topics)
│   │   ├── cometd_client.py      Per-org CometD subscription manager
│   │   ├── salesforce_client.py  OAuth login + publish Platform Events via REST
│   │   ├── worker.py             The "internal function": processes inbound events
│   │   │                         (via DSSClient if configured), publishes results, and
│   │   │                         handles transaction reprocessing
│   │   ├── transactions.py       Transaction audit-trail helpers
│   │   └── routers/              /api/auth, /api/orgs, /api/events, /api/transactions,
│   │                             /api/logs, /api/dashboard, /api/admin-config
│   ├── data/                     nexus.db (SQLite) lives here (gitignored)
│   ├── logs/                     Rotating log file lives here (gitignored)
│   ├── requirements.txt
│   └── run.py                    `python run.py` to start the server
└── frontend/
    ├── src/
    │   ├── pages/                Login, Dashboard, Orgs, EventsConfig, Transactions, Logs,
    │   │                         AdminConfig
    │   ├── components/           Layout (sidebar/topbar), shared UI bits
    │   └── lib/api.js            Axios client with JWT handling
    └── dist/                     Production build output (served by FastAPI) — run `npm run build`
```

## Running it

### Option A — Docker (recommended)

```bash
cp .env.example .env          # edit SECRET_KEY at minimum
docker compose up --build
```

That's it — the multi-stage `Dockerfile` builds the React admin console and installs the Python
backend in one image, and `docker-compose.yml` wires up:
- Port **8000** exposed on the host — open **http://localhost:8000**
- Two named volumes (`nexus-data`, `nexus-logs`) so the SQLite database and log files survive
  container restarts and rebuilds
- A container healthcheck against `/api/health`

To run it without Compose:

```bash
docker build -t salesforce-nexus-ai-server .
docker run -d --name nexus \
  -p 8000:8000 \
  -e SECRET_KEY=change_me \
  -v nexus-data:/app/data \
  -v nexus-logs:/app/logs \
  salesforce-nexus-ai-server
```

To update after making code changes: `docker compose up --build` again (or `docker build` +
`docker run` as above) — the named volumes keep your orgs, event configs, transactions, and
DSSClient settings intact across rebuilds.

### Option B — run directly with Python/Node

#### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env          # edit SECRET_KEY at minimum
python run.py
```

The API + admin UI will be available at **http://localhost:8000**.
On first startup, a default admin account is created: **admin / admin123** — the login screen
reminds you to change it; do so from the admin UI or `POST /api/auth/change-password`.

#### 2. Frontend (only needed if you're changing the UI)

A production build is already included in `frontend/dist/` and is served directly by FastAPI, so
you don't need Node.js just to run the server. If you want to modify the React app:

```bash
cd frontend
npm install
npm run dev        # dev server on :5173 with API proxy to :8000
# ...make changes...
npm run build       # rebuilds frontend/dist, which FastAPI serves automatically
```

### 3. Connect a Salesforce org

1. In the admin UI, go to **Salesforce Orgs → Add org** and fill in:
   - Login URL (`https://login.salesforce.com` for production/dev, or your My Domain / sandbox URL)
   - A **Connected App** Client ID + Secret (Setup → App Manager → New Connected App, with OAuth
     enabled and the `api` + `eventbus` scopes)
   - Username / password / security token (for the password OAuth flow)
2. Click **Test** to confirm the credentials work.
3. Go to **Event Configuration → Add channel** and add:
   - A **subscribe** channel, e.g. `/event/My_Custom_Event__e`, to receive events from this org
   - A **publish** channel, e.g. `My_Custom_Event__e`, so processed results are sent back
4. The server automatically (re)connects via CometD whenever org/channel configuration changes —
   no restart needed. Watch the **Dashboard** and **Logs** pages for connection status and traffic.

> **Note on network access:** CometD and the OAuth token endpoint both require outbound HTTPS
> access to your Salesforce instance's host. If you're running this behind a restrictive egress
> proxy/firewall, allow-list your Salesforce login/instance domains.

## Admin Configuration: DSSClient

The **Admin Configuration** section (separate from per-org Salesforce connections) currently holds
one named configuration block, **DSSClient**: `url`, `project_name`, `llm`, and `api_key`.

- Saving it is an **upsert** — the first save creates the record, every save after that updates it
  in place; the API key field is never blanked out by leaving it empty on a later save (same
  pattern as Salesforce org secrets).
- It's stored in the `admin_settings` SQLite table and is read fresh on every event by
  `worker.py:process_payload()`.
- When a URL is set, every inbound event is POSTed to that URL as
  `{"project": project_name, "llm": llm, "input": payload}` with an `Authorization: Bearer <api_key>`
  header, and the JSON response becomes the processing result published back to Salesforce. If the
  call fails, or no URL is configured, a local fallback result is used instead so the pipeline
  never breaks because of a downstream outage.

## Configuration durability

Every configuration change made in the admin UI — Salesforce orgs, event channels, admin users,
DSSClient settings — is written straight to the local SQLite database (`backend/data/nexus.db`) on
every create/update/delete call. SQLite commits each write immediately, so a change is durable the
moment the API call returns, even if the process is killed immediately afterward (verified by
hard-killing the server mid-session and confirming all config survives a restart).

## Reprocessing transactions

Any transaction can be re-driven back through the internal broker from the **Transactions** page:

- **Per-transaction "Reprocess"** (row action or in the detail view) — requeues that exact
  transaction. The system is smart about where to put it back in the pipeline:
  - A **publish** transaction (including manual test publishes) is requeued directly onto the
    outbound topic to retry sending it to Salesforce.
  - A **subscribe** transaction that already finished processing but failed only at the final
    publish-back step is requeued onto the outbound topic using its existing processed result
    (it is not reprocessed twice).
  - A **subscribe** transaction that never finished processing is requeued onto the inbound topic
    to run through `process_payload()` again from scratch.
- **"Reprocess all failed"** (toolbar button, optionally scoped to the org filter) — bulk-requeues
  every transaction currently in a `failed` state in one click.

Each transaction record tracks an `attempts` counter so you can see retry history at a glance, and
every reprocess action is written to the system log.

## A note on the CometD library

This project targets **`aiocometd_ng`** (an actively-maintained fork of the original `aiocometd`,
needed on newer Python versions where the original package can be difficult to install).
`backend/app/cometd_client.py` imports from `aiocometd_ng` first and falls back to `aiocometd` if
that's what you have installed instead — the two share the same `Client`/`AuthExtension` API,
with one difference to be aware of if you're modifying this code: the `Client` constructor takes
`connection_types` (plural), not `connection_type`.

If you hit `'str' object is not callable` (or any other odd error) when subscribing, it usually
means something that should be a callable — most commonly the `auth=` argument, or one of
`AuthExtension.incoming` / `.outgoing` / `.authenticate` — has been replaced with a plain string
somewhere. Double check that `auth=` is given an *instance* of an `AuthExtension` subclass (not a
token string), and that none of its methods have been accidentally shadowed by a same-named
instance attribute.

## Customizing the processing logic

All business logic (or a call out to an AI model) lives in one place:

```python
# backend/app/worker.py
def process_payload(payload: dict) -> dict:
    ...  # replace this with your real logic
    return {"status": "ok", "summary": "...", "echo": payload}
```

Whatever dict this returns is what gets published back to Salesforce on the org's configured
**publish** channel.

## Security notes

- Change `SECRET_KEY` in `.env` before deploying.
- Change the default `admin` password immediately after first login.
- Client secrets, passwords, and security tokens are stored in TinyDB (local file) and are only
  ever returned to the browser masked (`••••••••`); the admin UI never re-displays a stored secret.
  For a hardened production deployment, consider encrypting `backend/data/nexus_db.json` at rest
  or moving secrets to a proper secrets manager.
