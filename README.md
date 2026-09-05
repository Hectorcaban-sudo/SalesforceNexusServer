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
  custom streaming channel you configure, per org. Automatically reconnects with exponential
  backoff on any connection loss, and never blocks the web app while doing so — see "Reliability &
  threading" below.
- **Message broker: internal or RabbitMQ** — an in-process async broker by default (zero external
  infra), or a real RabbitMQ server for durability, chosen from Admin Configuration. Both sit behind
  the same interface so nothing else in the app needs to know which one is active. See "Message
  broker" below.
- **Pluggable worker/processor** — `app/worker.py:process_payload()` supports four interchangeable
  processing modes, switchable globally from Admin Configuration *or* per subscribed event channel:
  a **local fallback**, a **Dataiku DSS LLM** call (via `dataikuapi`), a **Langflow** flow, or an
  **uploaded custom Python script**. A processor script also gets the triggering org's Salesforce
  credentials and the rest of admin configuration (DSSClient/Langflow/Email) via environment
  variables, so it can call out to Salesforce or send its own email directly (its subprocess
  timeout is configurable via `PROCESSOR_TIMEOUT_SECONDS`, default 20s). See "Custom payload
  processors" and "Per-event processor override" below.
- **Validation rules (GoRules JDM / Zen Engine)** — a *gate*, not a processing mode: assign a
  no-code decision graph to a subscribed event channel to decide whether an event gets processed at
  all before any processing mode runs. See "Rule engine" below.
- **Graphical event routing** — for any subscribed event channel, visually select (checkboxes) which
  publish channels, integration hooks, *and* alert rules the processed result should fan out to,
  instead of one implicit default channel. See "Event routing" below.
- **Direct execute API** — `POST /api/execute/dss-client` and `POST /api/execute/langflow` invoke
  either processor directly with an arbitrary payload, outside the Salesforce pipeline entirely —
  useful for testing a configuration or for another internal system to reuse the same AI processor.
  Unlike the normal pipeline, these surface the real error instead of falling back silently.
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
  **Slack**, **Microsoft Teams**, **Snowflake**, **BigQuery**, or a generic **custom API**, each
  independently scoped by org and trigger (always / on success / on failure). Every dispatch's real
  result (HTTP response body, rows inserted, etc.) is captured and shown on hover wherever it's
  logged. SSL/TLS certificate verification is disabled on every outbound integration call by
  design, to support internally-issued or self-signed certificates. See "Integrations" below.
- **Alerts** — get notified (including by **email**) through any configured integration sink when a
  transaction, a Salesforce org's connection, an integration dispatch, or the message broker fails.
  See "Alerts" below.
- **Configuration export/import** — back up every Salesforce org, event channel, and integration to
  a single JSON file, and restore it (here or on another instance). See "Configuration backup"
  below.
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
  global settings.
- **Local storage only** — everything is stored in a local **SQLite** database
  (`backend/data/nexus.db`). No external database required to run this (RabbitMQ is optional, for
  the message broker only).
- **Username/password protected admin** — JWT-based auth, bcrypt-hashed passwords, default
  bootstrap account (`admin` / `admin123` — change this immediately, see below).
- **Structured, rolling logging** — every component logs to a **daily-rotating file**
  (`backend/logs/nexus.log`, configurable — size-based rotation is also available) *and* into
  SQLite, so the admin UI's Logs page can filter/search without touching the filesystem. **Custom
  processor scripts** are included — anything they print to stderr shows up here too, tagged with
  the processor's name. Click any log row to see the full entry (message + context) in a modal.
- **Optional publishing** — a subscribed event channel can be configured to process without
  automatically publishing the result back to Salesforce (still runs through the configured
  processor, integrations, and alerts) — useful for one-way "listen and notify" event types.

## Project layout

```
sfnexus/
├── Dockerfile                    Multi-stage build: React frontend + Python backend (Linux)
├── docker-compose.yml            One-command startup with persistent volumes (Linux)
├── Dockerfile.windows            Native Windows container build (Windows Server 2022)
├── docker-compose.windows.yml    One-command startup on Windows containers
├── docs/WINDOWS_DEPLOYMENT.md    Windows Server 2022 host setup + deployment guide
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
│   │   ├── integrations.py        Outbound fan-out: webhook/Slack/Teams/Email/Snowflake/BigQuery/custom
│   │   ├── processors.py          Uploaded Python processor storage + isolated subprocess execution
│   │   │                         (with org/admin-config context passed via env vars)
│   │   ├── rules.py                GoRules JDM decision graph storage + evaluation (Zen Engine)
│   │   ├── alerts.py               Alert rules - fire on success/failure, deliver via an integration sink
│   │   ├── worker.py             The "internal function": processes inbound events
│   │   │                         (via DSSClient/Langflow/custom script/rule engine if configured),
│   │   │                         fans results out to selected publish channels + integrations +
│   │   │                         alerts, and handles reprocessing
│   │   ├── transactions.py       Transaction audit-trail helpers
│   │   └── routers/              /api/auth, /api/orgs, /api/events, /api/transactions,
│   │                             /api/logs, /api/dashboard, /api/admin-config, /api/users,
│   │                             /api/integrations, /api/processors, /api/alerts, /api/execute,
│   │                             /api/rules
│   ├── dev_tools/
│   │   └── fake_oidc_provider.py  Local fake IdP for testing SSO without a real provider
│   ├── data/                     nexus.db (SQLite) lives here (gitignored)
│   ├── logs/                     Rotating log file lives here (gitignored)
│   ├── requirements.txt
│   └── run.py                    `python run.py` to start the server
└── frontend/
    ├── src/
    │   ├── pages/                Login, SsoCallback, Dashboard, Orgs, EventsConfig,
    │   │                         Transactions (with grouping), Logs (with hover popups),
    │   │                         AdminConfig (submenu tabs), Users, Integrations, Alerts
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

## Server configuration (uvicorn)

`run.py` reads its bind address/port/reload/log-level from environment variables (see
`.env.example`): `UVICORN_HOST`, `UVICORN_PORT`, `UVICORN_RELOAD`, `UVICORN_LOG_LEVEL`. There's also
`UVICORN_WORKERS`, but **leave it at the default of 1** — every background task this app runs
(CometD listeners per org, broker consumers, the in-process message broker itself) lives in a
single process's memory, so more than one uvicorn worker means every Salesforce org gets listened
to multiple times over and every event gets processed and published multiple times. If you need to
scale beyond one process, run multiple independent *instances* behind a load balancer, each pointed
at the same RabbitMQ broker and database — not multiple workers inside one instance. Setting
`UVICORN_WORKERS` above 1 logs a warning and is forced back to 1.

## Roles & access control (RBAC)

Three roles, enforced server-side on every route (not just hidden in the UI):

| Role | Can do |
|---|---|
| **viewer** | Dashboard, transactions, logs — read-only |
| **operator** | Everything a viewer can, plus create/edit Salesforce orgs and event channels, manually publish test events, reprocess transactions |
| **admin** | Everything an operator can, plus delete orgs/event channels, manage users, manage integrations, manage Admin Configuration (DSSClient) |

Manage users from **Users** in the admin console (admin role required), or via the API
(`GET/POST/PUT/DELETE /api/users`). You can't delete or demote your own account — have another
admin do it if needed.

## Database backends

SQLite (the default, zero-setup, a single local file) is what you get out of the box, but the
storage layer also supports **PostgreSQL**, **SQL Server**, and **Oracle** — the same document-style
interface every part of the app uses (`table.get(...)`, `.search()`, `.update()`, etc.) runs
identically against all four via SQLAlchemy Core underneath, storing each logical table as an
auto-incrementing id plus a JSON-blob column. This trades a little raw query performance (filtering
happens in Python, not via each database's native JSON query features) for something more valuable
here: one code path that behaves identically everywhere.

**This can't be switched live** — the database is where every other setting (including which
database to use!) would normally live, so which one to connect to has to be knowable *before* any
connection is made, which means it can only come from the environment. Admin Configuration →
**Database** is a config-builder and connection-tester, not a live-apply control: pick a backend,
fill in connection details, hit **Test connection** to verify it works, then **Save** writes
`DATABASE_TYPE`/`DATABASE_HOST`/etc. to the backend's `.env` file for you (if it's writable —
otherwise it tells you the exact environment variables to set by hand) and always requires a
restart to take effect.

| `DATABASE_TYPE` | Driver needed | Notes |
|---|---|---|
| `sqlite` (default) | none (stdlib) | Local file at `DB_PATH` |
| `postgres` | `psycopg2-binary` | Verified against a real PostgreSQL 16 server — full CRUD, restart persistence, and direct inspection of the underlying tables all confirmed working |
| `sqlserver` | `pyodbc` + the OS-level "ODBC Driver 18 for SQL Server" package | Implemented via the same SQLAlchemy dialect approach as Postgres, but **not verified against a real SQL Server instance** — no such server was available to test against |
| `oracle` | `oracledb` (pure Python "thin" mode, no separate Instant Client) | Same caveat as SQL Server — implemented, not verified against a real Oracle instance |

Uncomment the driver you need in `requirements.txt` before switching (they're commented out by
default so a plain SQLite install doesn't pull in three database drivers it'll never use).

## Single sign-on (SSO)

SSO is optional and off by default. To enable it, set these (in `.env` or your environment) to
match your identity provider's OIDC app registration:

```
SSO_ISSUER=https://your-tenant.okta.com          # or Azure AD, Auth0, Google Workspace, etc.
SSO_CLIENT_ID=...
SSO_CLIENT_SECRET=...
SSO_REDIRECT_URI=http://localhost:8000/api/auth/sso/callback
SSO_DEFAULT_ROLE=viewer                           # role assigned to first-time SSO logins
```

Register `SSO_REDIRECT_URI` as an allowed redirect URI in your IdP's app settings. Once configured,
a "Continue with single sign-on" button appears automatically on the login page. New SSO users are
created on first login with `SSO_DEFAULT_ROLE`; promote them from the Users page afterward.
Local username/password accounts keep working alongside SSO.

A minimal fake OIDC provider for local testing (no real IdP needed) lives at
`backend/dev_tools/fake_oidc_provider.py` — run it, point `SSO_ISSUER` at
`http://127.0.0.1:9999`, and the whole login flow works end-to-end against it.

## Security: audit logging and authentication monitoring

The **Security** page (admin role required) has two views, both aimed at supporting technical
audit/access-control practices relevant to frameworks like CMMC Level 2 / NIST 800-171 — **this is
software capability, not a compliance certification**; actual compliance requires a full assessment
across policies, documentation, and controls well beyond what any single tool provides.

**Admin action audit log** — every state-changing (create/update/delete) call to the admin API is
recorded automatically: who made it, from where, what it was, and what the server responded.
Captured by `AuditMiddleware` at the HTTP layer, so no individual router has to remember to log
anything — new admin endpoints get audited for free.

**Authentication monitoring** — every login attempt (success, failure, blocked-while-locked),
account lockout/unlock, password change, and SSO login is recorded to a separate `auth_events` log.
This is also the basis for **account lockout**: after `MAX_FAILED_LOGIN_ATTEMPTS` (default 5)
consecutive failed attempts, an account is locked for `LOCKOUT_DURATION_SECONDS` (default 900s/15
minutes) — the correct password is rejected (`423 Locked`) even during the lockout window, closing
the brute-force gap that would otherwise exist. An admin can unlock an account early from the
Security page or the Users page, which also resets the failed-attempt counter. Verified end-to-end:
repeated failed logins correctly trigger a lockout, the correct password is correctly rejected while
locked, and it's correctly accepted once the window expires (or immediately after an admin unlocks
it) — with a complete, accurate trail of every step in `auth_events`.

## Tracing (OpenTelemetry)

Tracing is always initialized but exports nowhere by default (near-zero overhead, no collector
required to run the app). To see traces:

- **Console** (quick local debugging): `OTEL_CONSOLE_EXPORTER=true`
- **A real collector** (Jaeger, Grafana Tempo, Honeycomb, Datadog agent, etc.):
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318`

Every inbound event gets **one connected trace** — a single trace ID — across
`cometd.receive_event` → (`worker.rule_gate` if a validation rule is assigned) →
`worker.process_payload` → `worker.publish_to_salesforce` → `integration.<type>` (per sink), plus
automatic spans for every HTTP request the API serves and every outbound `requests` call (Salesforce
OAuth/publish, DSSClient calls, webhook/Slack/Teams calls). Open that trace in your collector and
you see the whole journey of one event from the moment CometD received it through to every place it
ended up, instead of separate unrelated traces per stage.

This required explicit trace-context propagation across every broker hop (`tracing.py:
inject_trace_context()`/`extract_trace_context()`, using the standard W3C traceparent format) —
OpenTelemetry's automatic context propagation only works within a single async call chain, and this
pipeline deliberately crosses the broker (in-process queue or RabbitMQ) between CometD receipt,
processing, and publishing, each potentially running in a different asyncio task at a different
point in time. Without that propagation, each stage would start its own disconnected trace instead
of continuing the same one - this is exactly what `inject_trace_context`/`start_span(..., carrier=)`
exist to fix, and it's verified (see the test suite notes in the repo history) by capturing real
spans and confirming they share one `trace_id` all the way from CometD receipt through integration
fan-out.

## Integrations (outbound fan-out)

From **Integrations** in the admin console (admin role required — viewing the list only needs any
authenticated role), **add, edit, or delete** any number of sinks that every processed transaction
is fanned out to, independent of the Salesforce publish step (the sink's type is fixed once
created; everything else — name, config, trigger, org scope, alert-only flag — can be edited later):

- **Webhook** — POSTs the full transaction JSON to a URL you provide; optionally HMAC-signs the
  body (`X-Nexus-Signature: sha256=...`) if you set a signing secret.
- **Slack** / **Microsoft Teams** — posts a formatted status card to an incoming webhook URL.
- **Email** — sends an email via the SMTP server configured in Admin Configuration → Email (see
  below), to one or more recipients you specify, with an optional custom subject.
- **Snowflake** / **BigQuery** — inserts a row per transaction into a table you specify. These use
  optional client libraries not installed by default — if you enable one, add it to your
  environment: `pip install snowflake-connector-python` or `pip install google-cloud-bigquery`
  (BigQuery uses Application Default Credentials; no key needs to be pasted into the UI).
- **Custom API** — a generic HTTP call (method, URL, and an `Authorization` header you choose) for
  any other SaaS's event API.

Each integration has a **trigger** (`always`, `on_success`, `on_failure`) and an optional **org
scope** (leave blank to apply to every org). Use the **Test** button on any integration to send a
synthetic transaction through it immediately and confirm it's wired up correctly. A failing
integration never affects the Salesforce publish outcome or blocks other integrations — failures
are logged and shown as the integration's last status.

**TLS/SSL certificate verification is disabled on every outbound integration call** (webhook,
Slack, Teams, custom API — `verify=False`; Snowflake — `insecure_mode=True`), to support internally
issued or self-signed certificates common on internal endpoints. This is a deliberate default, not
a bug; if you need strict verification for a particular sink, that's the one thing you'd need to
re-enable in `integrations.py` for that specific sender function.

## Custom payload processors

From **Admin Configuration** (admin role required), upload a Python script as an alternative to
DSSClient or the local fallback for `process_payload()`. Contract:

```python
import sys, json

def process(payload: dict) -> dict:
    print(f"Received: {list(payload.keys())}", file=sys.stderr)  # shows up in System Logs automatically
    # your logic here
    return {"status": "ok", "echo": payload}

if __name__ == "__main__":
    input_payload = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(process(input_payload)))
```

- Read one JSON object from stdin, print one JSON object to stdout.
- Print any log/diagnostic messages to **stderr** — every line is mirrored into the **System Logs**
  page automatically (tagged with the processor's name as its logger, e.g.
  `nexus.processor.My Processor`), whether the run succeeds or fails.
- A non-zero exit code, invalid JSON on stdout, or exceeding a 20-second timeout is treated as a
  processing failure (and falls back to local processing so the pipeline never breaks).
- Use the **Test** button to run it against a sample payload before activating it.
- Only one processor is "active" at a time globally, selected from Admin Configuration's mode
  selector — or pin a specific processor to an individual event channel (see "Per-event processor
  override" below).
- **Download / override** — download any processor's current .py file (e.g. to edit locally or put
  under version control), and upload a new version back to the *same* processor id to replace its
  code in place — anything already pointing at it (the global mode, or a per-event override) picks
  up the new code immediately with no reconfiguration needed. Uploading resets its test history
  since the old pass/fail no longer describes what's running now.

**Security note:** uploaded scripts run in an isolated subprocess (not `exec()`'d in-process), so
they can't directly touch the running server's memory or already-loaded secrets — but they do run
with the same OS-level filesystem/network permissions as the server process. This is not a security
sandbox. Uploading a processor script is admin-only and should be treated like deploying new server
code: only from sources you trust.

### Context available to a processor: org settings, admin config, email

A processor can read two environment variables to interact with the rest of the system without any
imports:

- `NEXUS_ORG` — the Salesforce org that triggered this event: `login_url`, `auth_type`,
  `client_id`/`client_secret`, `username`/`password`/`security_token`, `api_version`. `"{}"` if
  there's no org context (e.g. a manual test run with no org selected).
- `NEXUS_ADMIN_CONFIG` — `{"dss_client": {...}, "langflow": {...}, "email": {...},
  "processing_mode": {...}}`, the same (unmasked) configuration the built-in processing modes use.

```python
import os, json
org = json.loads(os.environ.get("NEXUS_ORG", "{}"))
admin_config = json.loads(os.environ.get("NEXUS_ADMIN_CONFIG", "{}"))
# e.g. call Salesforce directly using org's credentials, or send your own
# email via smtplib using admin_config["email"]
```

**This meaningfully expands what an uploaded script can do** — it now has every Salesforce org
credential and every configured API key/SMTP password available to it, not just the payload.
This is consistent with the existing trust model (a processor upload is already treated as
equivalent to deploying server code), but it raises the stakes: only upload processors you trust
as much as your own server code.

## Rule engine (GoRules JDM / Zen Engine) — a validation gate, not a processing mode

**Rules** are evaluated by GoRules' open-source [Zen Engine](https://gorules.io) against the JSON
Decision Model (JDM) standard, and decide **whether an event gets processed at all** — they're a
gate that runs *before* whichever processing mode (local/DSSClient/Langflow/custom script) is
configured for that channel, not an alternative to them. A rule is a *declarative decision graph*
(decision tables, expressions, switch nodes), not executable code — build one visually at the free
[editor.gorules.io](https://editor.gorules.io), export the JSON, and paste/upload it from Admin
Configuration → **Rules**.

Assign a rule to a subscribed event channel from Event Configuration → **Route & process** →
**Validation rule**. When an event arrives on that channel:

1. The rule is evaluated against the event payload first, before any processing.
2. Its output must include a boolean **`process`** field (see the built-in example) —
   `true` (or the field simply being absent) lets the event continue to normal processing;
   `false` skips it. The transaction is recorded with status **`skipped`** — it's still visible on
   the Transactions page (with the rule's full output attached), it just never reaches
   `process_payload()` or gets published to Salesforce.
3. If the rule itself fails to evaluate (bad reference, rule deleted, etc.), that's treated as a
   genuine processing **failure** (alerts fire), not a silent skip — a broken gate should be loud,
   not swallow events quietly.

Because a rule is data rather than code, it runs directly in-process (no subprocess isolation
needed the way uploaded scripts require) and can't execute arbitrary code or make network calls —
it only evaluates the decision logic you defined.

- Use the **Test** button (from the Rules tab, or per-rule) to evaluate a rule against a sample
  payload before assigning it to a live channel.
- An invalid decision graph is rejected at save time with a descriptive error.
- Leaving a channel's validation rule unset preserves the original behavior: every event is
  processed, exactly as before this feature existed.

## Event routing

Each **subscribed** event channel (Event Configuration page) has a **Routing** button that opens a
graphical multi-select: pick any number of that org's **publish channels**, any number of
**integration hooks**, and any number of **alert rules** to fan the processed result out to. This
mirrors a typical event-broker architecture (one event in, many consumers out) — each selected
publish channel is delivered to and tracked independently (so one Salesforce org accepting the
event and another rejecting it don't affect each other), and integration/alert dispatch is
restricted to exactly what you picked rather than every integration/alert that happens to match by
trigger/org.

Leaving all three selections empty preserves the original behavior: the first enabled publish
channel for the org, integrations auto-matched by their own trigger/org settings, and alerts
auto-matched by their own scope/org settings — so existing setups keep working unchanged until you
opt into explicit routing.

The same **Route & process** dialog also has an **"Automatically publish the result back to
Salesforce"** toggle (on by default). Turn it off for a channel that should be received and
processed — running through DSSClient/Langflow/a custom script, going through integrations/alerts —
without ever publishing anything back to Salesforce. Useful for one-way "listen and notify" event
types that don't have a meaningful reply. The transaction's terminal status becomes `processed`
instead of `published`/`failed`, and routed (or globally auto-matched) integrations/alerts still
fire off of it.

## Alerts

Admin Configuration → **Alerts** (its own page, alongside Integrations) notifies you through an
existing integration sink when something happens:

| Scope | Fires when |
|---|---|
| `transaction` | Any transaction (or a specific event channel's, via routing) reaches a terminal state — controlled by its own **trigger**: `always`, `on_success`, or `on_failure` (default) |
| `connection_failed` | A Salesforce org's CometD connection goes down — fires once per outage, not on every retry |
| `integration_failed` | An integration dispatch raises an exception |
| `broker_degraded` | The configured RabbitMQ broker fails to connect at startup |

The `transaction` scope can be used for both success and failure notifications (e.g. "notify me
whenever a high-value transaction publishes successfully" as well as "page me when anything
fails") — set its `trigger` when creating or editing the alert. The other three scopes are
inherently single-outcome events with no natural success counterpart.

Alerts deliver through the same sender functions as normal integrations (webhook/Slack/Teams/**email**/custom
API), so any integration you've already configured can double as an alert channel — including a
dedicated email integration for on-call notifications (see "Email" below). If you want a
channel used *only* for alerts — not also receiving normal per-transaction fan-out — mark it
**alert-only** on the Integrations page; otherwise a channel with `trigger="always"` and no org
scope would fire twice for the same outcome (once from normal dispatch, once from the alert). Use
the **Test** button on any alert to confirm delivery before relying on it.

## Per-event processor override

The same **Route & process** dialog also lets an individual subscribed channel pin its own
processing mode (Local / DSSClient / Langflow / Custom uploaded script — and which script) instead
of using the global Admin Configuration default. This is resolved per event at processing time
(`worker.py:_resolve_processing()`); leaving it on "Use global default" preserves existing behavior.
Useful when different event types need different handling — e.g. one channel always uses a specific
custom script while everything else uses the global DSSClient setting. (This is separate from the
channel's **validation rule**, which decides *whether* to process at all — see "Rule engine" above.)

## Reliability & threading

Two things that matter for keeping the server itself healthy under real-world network conditions:

- **CometD reconnects automatically.** Each org's CometD connection runs inside a persistent
  supervisor loop (`cometd_client.py:OrgStreamManager._run_forever()`). Any failure — network blip,
  Salesforce-side restart, an expired token — is caught, logged, and retried with exponential
  backoff (`COMETD_RECONNECT_MIN_DELAY_SECONDS` up to `COMETD_RECONNECT_MAX_DELAY_SECONDS`,
  doubling each attempt by default), resetting back to the minimum delay once a connection succeeds.
  The org just shows as `error`/`connecting` in the admin UI until it recovers — nothing needs to be
  restarted manually.
- **The web app never hangs while events are processing.** `process_payload()`, the Salesforce
  publish call, and every integration dispatch are all potentially slow, blocking I/O (HTTP calls,
  subprocess execution, database client calls). Because the worker runs in the same asyncio event
  loop that serves the admin UI, calling any of that directly would freeze the entire web app for
  the duration of the call. Every such call is routed through `asyncio.to_thread(...)`, so event
  processing runs on a worker thread and the admin UI stays fully responsive and navigable the whole
  time — verified by measuring API response times (consistently single-digit milliseconds) while
  CometD was actively retrying failed connections in the background.
- **Events process concurrently, not one at a time.** The broker hands each message to its own task
  instead of waiting for the previous one to finish before dequeuing the next, bounded by
  `WORKER_MAX_CONCURRENCY` (default 10, applied independently to the inbound and outbound topics) so
  a burst of events can't spawn unlimited threads. Verified by processing a slow event (a 2-second
  custom script) and a fast one back to back: the fast one reached `processed` while the slow one
  was still actively `processing`, instead of waiting for it to finish first.

## Cancelling transactions

Any transaction that hasn't reached a terminal state yet can be cancelled from the Transactions
page (or `POST /api/transactions/{id}/cancel`, operator role or higher). What happens depends on
how far along it is:

- **Not started yet** (`received`/`queued`): cancelled immediately — the worker checks for this the
  moment it would otherwise start work and skips it entirely.
- **A custom-script processor actively running**: killed immediately (`SIGKILL`). This works because
  it's a real, independently killable OS subprocess — verified by cancelling a script mid-way
  through a deliberate 10-second sleep and confirming it was killed in ~1 second, not 10.
- **A DSSClient call actively running**: also killed immediately, same mechanism — `dataikuapi` is a
  sync-only third-party SDK with no async variant, so it runs in its own subprocess
  (`app/dss_runner.py`) purely so it can be hard-cancelled the same way a custom script can.
  Verified with a simulated slow DSS call: killed in ~1 second instead of running to completion.
- **A Langflow call or the Salesforce publish call actively running**: also aborted immediately —
  these are native async (`httpx`), run as a registered `asyncio.Task` that the cancel endpoint
  cancels directly rather than waiting for a poll interval. Verified against real slow servers
  (deliberately sleeping 15 seconds before responding): both were cancelled in well under half a
  second, and the server-side logs confirm the connection was actually torn down client-side — the
  server itself never got to finish handling the request.
- **Local processing**: nothing to cancel — it's instantaneous.
- **Outbound integration/alert dispatch** (webhook, Slack, Teams, email, Snowflake, BigQuery): not
  cancellable, but also not something that needs to be — dispatch only starts once a transaction has
  already reached a terminal state, so there's no "in-flight processing" left to interrupt by the
  time it runs.
- Already-terminal transactions (`published`/`failed`/`skipped`/already `cancelled`) return a 400 —
  there's nothing left to cancel.

**One nuance worth knowing**: if a cancellation lands in the narrow window right as the Salesforce
publish call is completing, Salesforce may have already received the event even though the
transaction ends up marked `cancelled` on this side — the transaction's error message says so
explicitly when that specific case happens.

## Message broker

Admin Configuration → **Message broker** lets you choose between:

- **Internal (default)** — in-process asyncio queues. Zero setup, but a single running instance only,
  and anything still queued is lost if the process restarts.
- **RabbitMQ** — a real broker via `aio-pika`. Durable (messages survive a restart) and the natural
  choice if you'll ever run more than one instance. Configure host/port/username/password/vhost/TLS
  from the same panel.

**Changing this requires a server restart** — saving the setting stores it in SQLite, it does not
hot-swap the broker underneath in-flight messages. On startup, the app reads this setting once
(`broker.py:BrokerProxy.configure_from_settings()`) and connects to RabbitMQ if configured; if that
connection fails, it logs the error and falls back to the internal broker automatically rather than
refusing to start. Both backends implement the same `publish()`/`consume_forever()`/`queue_depth()`
interface, so nothing else in the app (the worker, CometD client, dashboard) needs to know or care
which one is active.

## Configuration backup

Admin Configuration → **Configuration backup** exports the *entire* application configuration as a
single JSON file (`GET /api/admin-config/export`), and imports it back (`POST /api/admin-config/import`)
— here or on a different instance:

- Salesforce orgs, event channels/routing, integrations, alerts, rules (including their JDM), and
  every Admin Configuration setting (DSSClient, Langflow, Email/SMTP, message broker, processing
  mode).
- **Uploaded processor scripts, including their actual code** — not just metadata, so a restored
  instance can run them immediately.
- Records are upserted by their original id, which preserves the links between an event's routing
  selections and the publish channels/integrations/alerts they point to.

**Deliberately excluded: local user accounts.** User management is treated as a separate identity
concern from application configuration — re-importing accounts (especially password hashes) across
environments is a different kind of risk than restoring integration settings, so it's left out on
purpose.

**The export file contains credentials in plaintext** — org client secrets/passwords/security
tokens, integration API keys/webhook signing secrets, DSSClient/Langflow API keys, the SMTP
password, and the RabbitMQ password — because a backup that couldn't restore working connections
wouldn't be useful. Treat the downloaded file exactly like a credentials backup: store it securely,
don't email it around, and delete it once it's no longer needed.

## Admin Configuration: DSSClient (Dataiku DSS)

The **Admin Configuration** section (separate from per-org Salesforce connections) holds one named
configuration block, **DSSClient**: `url` (your Dataiku DSS instance), `project_name`, `llm` (the
DSS LLM connection id), and `api_key`.

- Saving it is an **upsert** — the first save creates the record, every save after that updates it
  in place; the API key field is never blanked out by leaving it empty on a later save (same
  pattern as Salesforce org secrets).
- It's stored in the `admin_settings` SQLite table and is read fresh on every event by
  `worker.py:process_payload()` when processing mode is `dss_client`.
- Under the hood this uses the official `dataikuapi` client
  (`DSSClient(url, api_key, no_check_certificate=True).get_project(project_name).get_llm(llm)`),
  sends `payload["User_Message__c"]` as the prompt, and returns
  `{"Conversation_Id__c": ..., "Status__c": "Ok", "Payload_Json__c": '{"replyText": "..."}'}` shaped
  to match a typical Salesforce conversation-event schema — adjust the field names in
  `worker.py:process_payload()` if your org's platform event uses different ones.
- Certificate verification is disabled for this call (`no_check_certificate=True`) to support
  internally-issued/self-signed DSS certificates. If the call fails, or no URL is configured, a
  local fallback result is used instead so the pipeline never breaks because of a downstream outage.

## Admin Configuration: Langflow

Also under Admin Configuration: **Langflow** — `base_url` (your Langflow instance), `flow_id`,
`api_key` (optional), `input_field` (defaults to `input_value`, matching Langflow's standard chat
input), and an optional `output_path` (dotted path into the response if your flow's output shape
needs a specific field extracted, e.g. `outputs.0.outputs.0.results.message.text`).

- Calls `POST {base_url}/api/v1/run/{flow_id}` with the event payload JSON-encoded into the
  configured input field, `input_type`/`output_type` set to `chat`, and `x-api-key` set if an API
  key is configured.
- If no `output_path` is set, falls back to Langflow's common response shape
  (`outputs[0].outputs[0].results.message.text`); if that path doesn't match your flow's output,
  set `output_path` explicitly.
- Same fallback-to-local-on-failure behavior as DSSClient and custom scripts.
- TLS verification is disabled on this call too, for internally-hosted Langflow instances.

## Admin Configuration: Email

Also under Admin Configuration: **Email** — a single global SMTP configuration (`host`, `port`,
`username`/`password` optional, `use_tls` for STARTTLS, `from_address`) used by any **Email**
integration sink, whether it's firing from normal per-transaction fan-out or from an Alert rule.
Individual email integrations just specify recipients (and an optional subject) — the SMTP server
itself is configured once, here.

## Direct execute API

`POST /api/execute/dss-client` and `POST /api/execute/langflow` (operator role or higher) run
either processor directly against a payload you send, without touching CometD, the broker, or
Salesforce at all — handy for testing a configuration change or for another internal system that
wants to reuse this server's configured AI processor. Unlike the normal pipeline, these do **not**
fall back to a local result on failure — you get the real error back, since you explicitly asked
for that specific processor:

```bash
curl -X POST http://localhost:8000/api/execute/langflow \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"payload": {"User_Message__c": "hello"}}'
```

## Configuration durability

Every configuration change made in the admin UI — Salesforce orgs, event channels, admin users,
DSSClient/broker/processor settings — is written straight to the local SQLite database
(`backend/data/nexus.db`) on every create/update/delete call. SQLite commits each write immediately,
so a change is durable the moment the API call returns, even if the process is killed immediately
afterward (verified by hard-killing the server mid-session and confirming all config survives a
restart).

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
