# Salesforce Nexus AI Server

Version **1.5.0**. Full changelog: [CHANGELOG.md](CHANGELOG.md).

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
  custom streaming channel you configure, per org. Automatically reconnects with exponential
  backoff on any connection loss, and never blocks the web app while doing so — see "Reliability &
  threading" below.
- **Message broker: internal or RabbitMQ** — an in-process async broker by default (zero external
  infra), or a real RabbitMQ server for durability, chosen from Admin Configuration. Both sit behind
  the same interface so nothing else in the app needs to know which one is active. See "Message
  broker" below.
- **Pluggable worker/processor** — `app/worker.py:process_payload()` supports interchangeable
  processing modes, switchable globally from Admin Configuration *or* per subscribed event channel:
  a **local fallback**, a **Dataiku DSS LLM** call (via `dataikuapi`), a **Langflow** flow, an
  **uploaded custom Python script**, **SharePoint Online** file/list actions (GCC High, Microsoft
  Graph), a **Chroma** vector query (see "Chroma" below), a reusable **flow action**, or another
  saved **pipeline** run as a sub-flow (see "Flow actions and sub-pipelines" below). A processor script also gets the triggering org's Salesforce credentials and the rest of
  admin configuration (DSSClient/Langflow/Email) via environment variables, so it can call out to
  Salesforce or send its own email directly (its subprocess timeout is configurable via
  `PROCESSOR_TIMEOUT_SECONDS`, default 20s). See "Custom payload processors", "SharePoint Online",
  and "Per-event processor override" below.
- **Chroma vector search** — admin page for CA certs, embedding models, and Chroma processors; usable
  as a processing mode. See "Chroma" below.
- **REST processors** — call an external system as a processing step. Global and project collections.
  Custom headers, verify-SSL switch, Jinja body template, and a test. See Administration → Processors → REST.
- **Validation rules (GoRules JDM / Zen Engine)** — a *gate*, not a processing mode: assign a
  no-code decision graph to a subscribed event channel to decide whether an event gets processed at
  all before any processing mode runs. See "Rule engine" below.
- **Projects** — group orgs, events, integrations, and SharePoint actions by customer/project.
  Processors and rules can be **global** (edited only under Administration) or project-scoped.
- **Event Flow Designer + walker** — the canvas (`/events/:id/flow`) is the pipeline editor.
  Saving stores `flow_graph` on the event. The worker walks that graph (order, If/Switch
  branches, Stop abort, integrations when their node is visited). Events without a saved graph
  still use the legacy linear path. See "Event Flow Designer" below.
- **SharePoint Online (GCC High)** — multi-connection admin, reusable **File** (upload + metadata +
  check-in) and **List** (create/update) actions with Jinja2 field maps, Graph-backed site/drive/list
  pickers, usable as a **processing mode** *or* as an **integration fan-out** sink. See
  "SharePoint Online" below.
- **Integration body templates** — optional Jinja2 templates for Teams, Slack, Email, Webhook, and
  Custom API message bodies, with a live preview in the Integrations admin UI. See "Integrations"
  below.
- **Direct execute API** — `POST /api/execute/dss-client` and `POST /api/execute/langflow` invoke
  either processor directly with an arbitrary payload, outside the Salesforce pipeline entirely —
  useful for testing a configuration or for another internal system to reuse the same AI processor.
  Unlike the normal pipeline, these surface the real error instead of falling back silently.
- **Execute a saved pipeline** — `POST /api/execute/{project}/pipeline/{pipeline_id}` runs a saved
  pipeline and returns the result. Auth is a login token or `X-Consumer-Key` / `X-Consumer-Secret`.
  Manage clients under Administration → API clients. The call is recorded as a transaction. See
  [docs/EXECUTE_API.md](docs/EXECUTE_API.md). Swagger is at `/docs`.
- **Salesforce publisher** — publishes the processed result back to Salesforce as a new Platform
  Event using the standard REST `sobjects` endpoint (OAuth password or client-credentials flow).
  A manual "publish test event" action is also available from the admin UI.
- **Transaction reprocessing and cancellation** — requeue any single transaction, or bulk-requeue
  every failed one, back through the broker without re-sending anything from Salesforce; or cancel
  any transaction that hasn't finished yet (immediate hard-kill for a running custom script,
  best-effort for everything else — see "Cancelling transactions"). The Transactions page can
  also **group** the list (by org, status, direction, channel, or fan-out group) instead of one
  flat table.
- **Outbound integrations** — fan any processed transaction out to a **webhook** (HMAC-signed),
  **Slack**, **Microsoft Teams**, **Email**, **Snowflake**, **BigQuery**, a generic **custom API**,
  or **SharePoint File/List** actions, each independently scoped by org and trigger (always / on
  success / on failure). Optional **Jinja2 body templates** customize Teams/Slack/Email/Webhook/API
  payloads (with live preview). Every dispatch's real result is captured and shown on hover.
  SSL/TLS certificate verification is disabled on outbound HTTP integration calls by design, to
  support internally-issued or self-signed certificates. See "Integrations" below.
- **Alerts** — get notified (including by **email**) through any configured integration sink when a
  transaction, a Salesforce org's connection, an integration dispatch, or the message broker fails.
  See "Alerts" below.
- **Configuration export/import** — back up Salesforce orgs, event channels, integrations (including
  SharePoint sinks), SharePoint connections/file/list actions, processors, alerts, rules, and admin
  settings to a single JSON file, and restore it (here or on another instance). See "Configuration
  backup" below.
- **Agentforce chat pipeline (Salesforce-side)** — repo-root Apex classes + prompt files pair an
  Agentforce agent with this server's existing platform-event pipeline (submit via a platform
  event, poll for the reply). Reference-only; not part of the running Python/React app. See
  "Salesforce-side reference assets" below.
- **Role-based access control** — three roles (**admin**, **operator**, **viewer**) enforced on
  every mutating API route. Viewers get read-only access to the dashboard/transactions/logs;
  operators can manage orgs/events and reprocess transactions; admins additionally manage users,
  integrations, and global admin configuration.
- **Single sign-on (optional)** — generic OpenID Connect support that works with Okta, Azure AD /
  Entra ID, Auth0, Google Workspace, Keycloak, or any other OIDC-compliant IdP. Disabled by default
  (falls back to local username/password); enable by setting `SSO_ISSUER`/`SSO_CLIENT_ID`. New SSO
  users are auto-provisioned with a configurable default role.
- **OpenTelemetry tracing** — a single trace follows each event through CometD receive → broker →
  worker processing → Salesforce publish → integration fan-out, plus automatic instrumentation of
  every HTTP request and outbound `requests` call. Safe to leave fully unconfigured; export to any
  OTLP collector (Jaeger, Tempo, Honeycomb, Datadog, etc.) via `OTEL_EXPORTER_OTLP_ENDPOINT`, or
  print spans to stdout with `OTEL_CONSOLE_EXPORTER=true`.
- **Admin console (React)** — dashboard, org management, per-org subscribe/publish channel
  configuration, full transaction history with payload/result inspection, a live log viewer, user
  management, integrations, alerts, and a separate **Admin Configuration** section (organized into
  submenus: Processing mode, DSSClient, Langflow, Payload processors, Message broker, Backup) for
  global settings. Every save/create/update/delete action anywhere in the console confirms itself
  with a toast notification instead of leaving you to guess whether it worked.
- **Local storage only** — everything is stored in a local **SQLite** database
  (`backend/data/nexus.db`). No external database required to run this (RabbitMQ is optional, for
  the message broker only).
- **Username/password protected admin** — JWT-based auth, bcrypt-hashed passwords, default
  bootstrap account (`admin` / `admin123` — change this immediately, see below).
- **Structured, rolling logging** — every component logs to a **daily-rotating file**
  (`backend/logs/nexus.log`, configurable — size-based rotation is also available) *and* into
  SQLite, so the admin UI's two-pane **Logs** page can filter by org, level, logger, a time window,
  and free-text search — without touching the filesystem. Click a line to see its full message and
  context in the detail pane. **Custom processor scripts** are included — anything they print to
  stderr shows up here too, tagged with the processor's name and (when the run was triggered by a
  transaction) that transaction's id, so a log line can jump straight back to the transaction that
  produced it, and a transaction's Inspector can jump straight to its own filtered log view.
- **Optional publishing** — a subscribed event channel can be configured to process without
  automatically publishing the result back to Salesforce (still runs through the configured
  processor, integrations, and alerts) — useful for one-way "listen and notify" event types.
- **Toast notifications** — every create/update/delete/toggle action across the admin console (not
  just Transactions) shows a bottom-corner toast confirming success or surfacing the server's error
  message, so a save failure is never silent. See "Admin console (React)" below.
- **Cross-linked Transactions ↔ Logs** — jump from a transaction's Inspector straight to its log
  lines (`View logs`, filtered to that `transaction_id`), or from a log line's context back to the
  transaction that produced it (`Open transaction`) — including custom-processor **stderr** output,
  which is tagged with the triggering transaction's id via `NEXUS_TRANSACTION_ID` so it shows up in
  that filtered view too. See "Custom payload processors" below.

## Project layout

```
sfnexus/
├── Dockerfile                    Multi-stage build: React frontend + Python backend (Linux)
├── docker-compose.yml            One-command startup with persistent volumes (Linux)
├── Dockerfile.windows            Native Windows container build (Windows Server 2022)
├── docker-compose.windows.yml    One-command startup on Windows containers
├── docs/WINDOWS_DEPLOYMENT.md    Windows Server 2022 host setup + deployment guide
├── docs/EXECUTE_API.md           Pipeline execute endpoint and consumer key auth
├── .dockerignore
├── .env.example                  Env vars for docker-compose (SECRET_KEY, etc.)
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, lifespan startup, serves the built React app
│   │   ├── config.py            Settings (env-driven)
│   │   ├── database.py          SQLite datastore (table/query-object interface)
│   │   ├── models.py            Pydantic schemas
│   │   ├── auth.py               JWT auth, bcrypt password hashing, RBAC (require_role)
│   │   ├── sso.py                 Generic OIDC SSO (login/callback, auto-provisioning)
│   │   ├── tracing.py             OpenTelemetry setup + span helper
│   │   ├── logging_config.py     File + SQLite logging sink
│   │   ├── broker.py             Message broker: internal in-process queues or RabbitMQ (aio-pika)
│   │   ├── cometd_client.py      Per-org CometD subscription manager with auto-reconnect/backoff
│   │   ├── salesforce_client.py  OAuth login + publish Platform Events via REST
│   │   ├── integrations.py        Outbound fan-out: webhook/Slack/Teams/Email/Snowflake/BigQuery/
│   │   │                         custom API/SharePoint (+ optional Jinja2 body templates)
│   │   ├── template_renderer.py   Shared Jinja2 renderer for integration bodies & SharePoint maps
│   │   ├── sharepoint.py          SharePoint Online (GCC High) Graph client + file/list runners
│   │   ├── processors.py          Uploaded Python processor storage + isolated subprocess execution
│   │   │                         (with org/admin-config context passed via env vars)
│   │   ├── rules.py                GoRules JDM decision graph storage + evaluation (Zen Engine)
│   │   ├── alerts.py               Alert rules - fire on success/failure, deliver via an integration sink
│   │   ├── flow_walker.py         Walks a saved Event Flow graph (if/switch/stop/hooks, node trace)
│   │   ├── flow_actions.py        Reusable flow actions (Salesforce get/delete, SharePoint file, Chroma)
│   │   ├── flow_actions_mode.py   Installs processing mode "flow_action"
│   │   ├── pipeline_mode.py       Installs processing mode "pipeline" (run another pipeline)
│   │   ├── chroma_runner.py / chroma_mode.py   Chroma query + processing mode
│   │   ├── projects.py            Multi-project scoping + default project bootstrap
│   │   ├── worker.py             The "internal function": processes inbound events
│   │   │                         (via DSSClient/Langflow/custom script/SharePoint/rule gate),
│   │   │                         walks flow_graph when present, otherwise fans out via
│   │   │                         legacy route_* fields, and handles reprocessing
│   │   ├── transactions.py       Transaction audit-trail helpers
│   │   └── routers/              /api/auth, /api/orgs, /api/events, /api/transactions,
│   │                             /api/logs, /api/dashboard, /api/admin-config, /api/users,
│   │                             /api/integrations, /api/processors, /api/alerts, /api/execute,
│   │                             /api/rules, /api/sharepoint, /api/api-clients
│   ├── dev_tools/
│   │   └── fake_oidc_provider.py  Local fake IdP for testing SSO without a real provider
│   ├── data/                     nexus.db (SQLite) lives here (gitignored)
│   ├── logs/                     Rotating log file lives here (gitignored)
│   ├── requirements.txt
│   └── run.py                    `python run.py` to start the server
└── frontend/
    ├── src/
    │   ├── pages/                Login, SsoCallback, Dashboard, Orgs, EventsConfig,
    │   │                         EventFlowDesigner (React Flow), Transactions (grouping),
    │   │                         Logs, AdminConfig, Users, Integrations, Alerts, SharePoint,
    │   │                         ApiClients
    │   ├── components/           Layout (role-gated sidebar/topbar), shared UI bits
    │   └── lib/                  api.js (JWT client), AuthContext.jsx (role-aware auth state)
    └── dist/                     Production build output (served by FastAPI) — run `npm run build`
```

## Running it

### Option A — Docker (recommended)

```bash
cp .env.example .env          # edit SECRET_KEY at minimum
docker compose up --build
```

That's it — the multi-stage `Dockerfile` builds the React admin console and installs the Python
backend in one image. Current `docker-compose.yml` (network name **Nexus**, ports on `0.0.0.0`) wires up:
- **nexus** — port **8000** — http://localhost:8000
- **postgres** — port **5432**
- **rabbitmq** — ports **5672** (AMQP) and **15672** (management UI)
- **flowise** (optional) — port **3000** — see `docs/FLOWISE.md`
- Named volumes for app data/logs, Postgres, RabbitMQ, and Flowise
- Windows rebuild via WSL: `deploy-wsl.bat` / `stop-wsl.bat`

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

**Hosting on Windows Server 2022?** Use `Dockerfile.windows` and `docker-compose.windows.yml`
instead — a native Windows container image (not the Linux image above run under WSL2). See
[docs/WINDOWS_DEPLOYMENT.md](docs/WINDOWS_DEPLOYMENT.md) for full host setup, build, and run
instructions specific to Windows containers.

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
   - Username and password (or client credentials)
2. Add subscribe and publish channels for that org under Events & flows.
3. The org connects over CometD. Status shows on the Orgs page.

## Execute a pipeline

`POST /api/execute/{project}/pipeline/{pipeline_id}` runs a saved pipeline and returns the result.
Auth is a login token or `X-Consumer-Key` and `X-Consumer-Secret`. Create clients under
Administration → API clients. The secret is shown once. The call is recorded as a transaction.
Full notes: [docs/EXECUTE_API.md](docs/EXECUTE_API.md). Swagger UI is at `/docs`.

## Version

Current version is **1.5.0**. See [CHANGELOG.md](CHANGELOG.md).
