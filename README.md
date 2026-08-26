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
- **CometD platform event subscriber** (`aiocometd`) — subscribes to any Platform Event / CDC /
  custom streaming channel you configure, per org.
- **Internal message broker** — an in-process async broker (`app/broker.py`) decouples the
  Salesforce listener from the processing logic and the Salesforce publisher. It's written behind
  a small interface so it can be swapped for Kafka/RabbitMQ/SQS later without touching callers.
- **Pluggable worker/processor** — `app/worker.py:process_payload()` is the single place to plug in
  your real business logic or AI model; it receives the raw event payload and returns the result to
  publish back.
- **Salesforce publisher** — publishes the processed result back to Salesforce as a new Platform
  Event using the standard REST `sobjects` endpoint (OAuth password or client-credentials flow).
  A manual "publish test event" action is also available from the admin UI.
- **Admin console (React)** — dashboard, org management, per-org subscribe/publish channel
  configuration, full transaction history with payload/result inspection, and a live log viewer.
- **Local storage only** — everything is stored in **TinyDB** (`backend/data/nexus_db.json`), a
  local JSON document database. No external database or message broker required to run this.
- **Username/password protected admin** — JWT-based auth, bcrypt-hashed passwords, default
  bootstrap account (`admin` / `admin123` — change this immediately, see below).
- **Structured logging** — every component logs to a rotating file (`backend/logs/nexus.log`) *and*
  into TinyDB, so the admin UI's Logs page can filter/search without touching the filesystem.

## Project layout

```
sfnexus/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, lifespan startup, serves the built React app
│   │   ├── config.py            Settings (env-driven)
│   │   ├── database.py          TinyDB tables
│   │   ├── models.py            Pydantic schemas
│   │   ├── auth.py               JWT auth + bcrypt password hashing
│   │   ├── logging_config.py     File + TinyDB logging sink
│   │   ├── broker.py             Internal async pub/sub broker (inbound/outbound topics)
│   │   ├── cometd_client.py      Per-org CometD subscription manager
│   │   ├── salesforce_client.py  OAuth login + publish Platform Events via REST
│   │   ├── worker.py             The "internal function": processes inbound events,
│   │   │                         publishes results to the outbound topic
│   │   ├── transactions.py       Transaction audit-trail helpers
│   │   └── routers/              /api/auth, /api/orgs, /api/events, /api/transactions,
│   │                             /api/logs, /api/dashboard
│   ├── data/                     TinyDB JSON file lives here (gitignored)
│   ├── logs/                     Rotating log file lives here (gitignored)
│   ├── requirements.txt
│   └── run.py                    `python run.py` to start the server
└── frontend/
    ├── src/
    │   ├── pages/                Login, Dashboard, Orgs, EventsConfig, Transactions, Logs
    │   ├── components/           Layout (sidebar/topbar), shared UI bits
    │   └── lib/api.js            Axios client with JWT handling
    └── dist/                     Production build output (served by FastAPI) — run `npm run build`
```

## Running it

### 1. Backend

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

### 2. Frontend (only needed if you're changing the UI)

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
