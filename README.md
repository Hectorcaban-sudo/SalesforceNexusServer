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
- **Pluggable worker/processor** — `app/worker.py:process_payload()` supports three interchangeable
  processing modes, switchable from Admin Configuration: a **local fallback**, a **DSSClient** HTTP
  endpoint, or an **uploaded custom Python script**. Upload a `.py` file that reads a JSON payload
  from stdin and prints a JSON result to stdout; it runs in an isolated subprocess with a timeout.
  See "Custom payload processors" below.
- **Graphical event routing** — for any subscribed event channel, visually select (checkboxes) which
  publish channels *and* which integration hooks the processed result should fan out to, instead of
  one implicit default channel. See "Event routing" below.
- **Salesforce publisher** — publishes the processed result back to Salesforce as a new Platform
  Event using the standard REST `sobjects` endpoint (OAuth password or client-credentials flow).
  A manual "publish test event" action is also available from the admin UI.
- **Transaction reprocessing** — requeue any single transaction, or bulk-requeue every failed one,
  back through the broker without re-sending anything from Salesforce.
- **Outbound integrations** — fan any processed transaction out to a **webhook** (HMAC-signed),
  **Slack**, **Microsoft Teams**, **Snowflake**, **BigQuery**, or a generic **custom API**, each
  independently scoped by org and trigger (always / on success / on failure). See "Integrations"
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
  management, integrations, and a separate **Admin Configuration** section for global settings
  (currently: DSSClient).
- **Local storage only** — everything is stored in a local **SQLite** database
  (`backend/data/nexus.db`). No external database or message broker required to run this.
- **Username/password protected admin** — JWT-based auth, bcrypt-hashed passwords, default
  bootstrap account (`admin` / `admin123` — change this immediately, see below).
- **Structured logging** — every component logs to a rotating file (`backend/logs/nexus.log`) *and*
  into SQLite, so the admin UI's Logs page can filter/search without touching the filesystem.

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
│   │   ├── broker.py             Internal async pub/sub broker (inbound/outbound topics)
│   │   ├── cometd_client.py      Per-org CometD subscription manager
│   │   ├── salesforce_client.py  OAuth login + publish Platform Events via REST
│   │   ├── integrations.py        Outbound fan-out: webhook/Slack/Teams/Snowflake/BigQuery/custom
│   │   ├── processors.py          Uploaded Python processor storage + isolated subprocess execution
│   │   ├── worker.py             The "internal function": processes inbound events
│   │   │                         (via DSSClient/custom script if configured), fans results out to
│   │   │                         selected publish channels + integrations, and handles reprocessing
│   │   ├── transactions.py       Transaction audit-trail helpers
│   │   └── routers/              /api/auth, /api/orgs, /api/events, /api/transactions,
│   │                             /api/logs, /api/dashboard, /api/admin-config, /api/users,
│   │                             /api/integrations, /api/processors
│   ├── dev_tools/
│   │   └── fake_oidc_provider.py  Local fake IdP for testing SSO without a real provider
│   ├── data/                     nexus.db (SQLite) lives here (gitignored)
│   ├── logs/                     Rotating log file lives here (gitignored)
│   ├── requirements.txt
│   └── run.py                    `python run.py` to start the server
└── frontend/
    ├── src/
    │   ├── pages/                Login, SsoCallback, Dashboard, Orgs, EventsConfig,
    │   │                         Transactions, Logs, AdminConfig, Users, Integrations
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

## Tracing (OpenTelemetry)

Tracing is always initialized but exports nowhere by default (near-zero overhead, no collector
required to run the app). To see traces:

- **Console** (quick local debugging): `OTEL_CONSOLE_EXPORTER=true`
- **A real collector** (Jaeger, Grafana Tempo, Honeycomb, Datadog agent, etc.):
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4318`

Every inbound event gets one connected trace across `cometd.receive_event` →
`worker.process_payload` → `worker.publish_to_salesforce` → `integration.<type>` (per sink), plus
automatic spans for every HTTP request the API serves and every outbound `requests` call (Salesforce
OAuth/publish, DSSClient calls, webhook/Slack/Teams calls) — so a single slow or failed transaction
can be traced end-to-end by its `transaction_id` span attribute.

## Integrations (outbound fan-out)

From **Integrations** in the admin console (admin role required), configure any number of sinks
that every processed transaction is fanned out to, independent of the Salesforce publish step:

- **Webhook** — POSTs the full transaction JSON to a URL you provide; optionally HMAC-signs the
  body (`X-Nexus-Signature: sha256=...`) if you set a signing secret.
- **Slack** / **Microsoft Teams** — posts a formatted status card to an incoming webhook URL.
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

## Custom payload processors

From **Admin Configuration** (admin role required), upload a Python script as an alternative to
DSSClient or the local fallback for `process_payload()`. Contract:

```python
import sys, json

def process(payload: dict) -> dict:
    # your logic here
    return {"status": "ok", "echo": payload}

if __name__ == "__main__":
    input_payload = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(process(input_payload)))
```

- Read one JSON object from stdin, print one JSON object to stdout.
- Anything on stderr, a non-zero exit code, or exceeding a 20-second timeout is treated as a
  processing failure (and falls back to local processing so the pipeline never breaks).
- Use the **Test** button to run it against a sample payload before activating it.
- Only one processor is "active" at a time, selected from Admin Configuration's mode selector.

**Security note:** uploaded scripts run in an isolated subprocess (not `exec()`'d in-process), so
they can't directly touch the running server's memory or already-loaded secrets — but they do run
with the same OS-level filesystem/network permissions as the server process. This is not a security
sandbox. Uploading a processor script is admin-only and should be treated like deploying new server
code: only from sources you trust.

## Event routing

Each **subscribed** event channel (Event Configuration page) has a **Routing** button that opens a
graphical multi-select: pick any number of that org's **publish channels** and any number of
**integration hooks** to fan the processed result out to. This mirrors a typical event-broker
architecture (one event in, many consumers out) — each selected publish channel is delivered to
and tracked independently (so one Salesforce org accepting the event and another rejecting it don't
affect each other), and integration dispatch is restricted to exactly the hooks you picked rather
than every integration that happens to match by trigger/org.

Leaving both selections empty preserves the original behavior: the first enabled publish channel
for the org, and integrations auto-matched by their own trigger/org settings — so existing setups
keep working unchanged until you opt into explicit routing.

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
