## Document Control

- **Title:** Nexus AI Server — Administrator Manual
- **Version:** 1.0
- **Classification:** Internal — Restricted
- **Audience:** System administrators, security/compliance reviewers, operations staff
- **Owner:** hector.caban@gmail.com
- **Last updated:** 2026-09-27
- **Review cycle:** Annually, and after any material change to architecture, RBAC, or data-handling behavior

This manual documents the Nexus AI Server ("the system"): a FastAPI/React application that brokers Salesforce Platform Event traffic between Salesforce orgs and downstream integrations. It is written to support day-to-day administration and to serve as evidence during a security or compliance audit. Where the system's current behavior falls short of a control an auditor would look for, this manual says so plainly in the *Known Limitations* section rather than omitting it.

## Table of Contents

1. Document Control
2. Table of Contents
3. Purpose & Scope
4. Glossary
5. System Architecture
6. Roles, Authentication & Access Control
7. Administration Console Reference
8. Security Configuration
9. Data Flow & Event Processing
10. Standard Operating Procedures
11. Backup, Export & Recovery
12. Compliance & Audit Considerations
13. Known Limitations & Technical Debt
14. Appendix: Environment Variable Reference

## Purpose & Scope

This manual explains how to administer the Nexus AI Server: how the system is put together, how to operate it day to day, what security controls exist and where they fall short, and how to back up and restore its configuration. It is intended to be the primary reference an administrator hands to an auditor or a new team member.

It does **not** cover application development (extending the codebase) or Salesforce-side configuration (creating Platform Events, permission sets) beyond what an administrator needs to connect an org. Where a claim in this document depends on reading the source code rather than observing runtime behavior, that is noted — this manual was produced by direct inspection of the codebase, not by vendor documentation, so it reflects what the system actually does rather than what it is intended to do.

## Glossary

- **Org** — A connected Salesforce organization (login credentials, instance URL) that the system subscribes to or publishes Platform Events for.
- **Subscribe Channel / Event Config** — A configured Salesforce Platform Event topic the system listens to via CometD.
- **Publish Channel** — A configured outbound Platform Event topic the system publishes to.
- **CometD** — The Bayeux/long-polling protocol Salesforce uses to stream Platform Events; implemented here via `aiocometd_ng`.
- **Event Pipeline** — A named, independently enabled processing path attached to a subscribe channel. An event can have multiple pipelines; each runs its own flow graph. Introduced to let one inbound event fan out to several independent processing paths (e.g., one pipeline per downstream system).
- **Flow Graph** — The node/edge graph (`{nodes, edges}`) defining what happens to an event once received: rule checks, transforms, processor calls, and publish/integration steps, executed by `flow_walker.run_flow_graph()`.
- **Broker** — The internal message-passing abstraction between the CometD listener and the worker; can run in-process or backed by RabbitMQ.
- **Worker** — The background process (`inbound_worker`) that consumes broker messages and executes the enabled pipeline(s) for that event.
- **Rule / JDM** — A GoRules JSON Decision Model decision graph (`app/rules.py`, via the `zen-engine` library) used as a pass/fail gate before an event is processed.
- **Processor** — A configured integration step (e.g., a Dataiku DSS call, an HTTP call, a SharePoint operation) invocable from a flow graph.
- **Project** — A logical grouping of orgs, events, integrations, and rules in the console; used to scope the UI (see *Known Limitations* for how project scoping is and is not enforced).
- **Role (admin / operator / viewer)** — The three RBAC roles. See *Roles, Authentication & Access Control*.
- **Circuit Breaker** — A per-sink failure-tripping mechanism defined in `app/circuit.py`. Currently present in the codebase but not wired into any call path (see *Known Limitations*).
- **DSS** — Dataiku Data Science Studio; one of the supported processor/payload-processing backends.
- **Alert** — A condition surfaced on the Alerts page and in the topbar notification inbox (e.g., an org disconnected, a pipeline failing repeatedly).
- **JWT** — JSON Web Token; the bearer-token format used for authenticated API sessions.
- **SSO** — Single sign-on; optional external identity-provider login, configured via environment variables (see *Appendix*).

## System Architecture

The diagram below traces one event through the system end to end.

> **Diagram (event flow, 7 stages):** Salesforce Org → CometD Client → Broker (Inbound) → Worker → Rules + Transform → Broker (Outbound) → Salesforce Org (publish target). The live, illustrated version of this diagram is in the source Claude Doc; this Markdown export shows the stage sequence as text only.

A subscribed org's Platform Event lands on a CometD channel, crosses the broker into the worker, and runs through the event's enabled pipeline(s): a rule gate, a transform, and any processor or integration nodes defined in that pipeline's flow graph. It then exits through the outbound broker to a Salesforce publish target, which may be the same org or a different one. Flow-graph nodes can also fan out to Integrations, SharePoint, or trigger Alerts — those are configured per pipeline and are not drawn as separate stages above.

## Roles, Authentication & Access Control

**Authentication.** Sessions are authenticated with JWTs. Login enforces a configurable lockout: `max_failed_login_attempts` and `lockout_duration_seconds` (see *Appendix*) throttle brute-force attempts against the login endpoint. Optional SSO can be configured via environment variables to delegate login to an external identity provider.

**Roles.** The system defines three roles, enforced per-endpoint with a `require_role(...)` FastAPI dependency:

- **admin** — full access, including Users, Security, Projects, and Admin Configuration.
- **operator** — can create, edit, enable/disable, and delete operational objects (orgs, events, pipelines, rules, processors) but not manage users or global security/admin settings.
- **viewer** — read-only access to dashboards, transactions, and configuration views.

Every mutating route in the routers reviewed (pipelines, events, orgs, rules, processors) carries an explicit `Depends(require_role("operator"))` or stricter, and all routes require an authenticated user via the router-level `Depends(get_current_user)`.

**Project scoping — important gap.** The console groups orgs, events, integrations, and rules under "Projects," and the UI filters what a user sees by their selected project. This is a UI convenience, not an authorization boundary: role checks are global (an operator is an operator for every project), and the API routes reviewed do not verify that a caller's assigned project(s) match the `project_id` of the resource being read or modified. In practice, any authenticated operator or admin can act on any project's resources by addressing them directly through the API, regardless of which project is selected in the UI. This is carried forward into *Known Limitations* and *Compliance & Audit Considerations* below — an auditor evaluating least-privilege or segregation-of-duties controls across projects/tenants should treat this as an open finding, not an implemented control.

## Administration Console Reference

The left navigation is grouped into three sections:

**Monitor** — Dashboard (summary tiles, attention items such as `no_pipeline`, `failed`, `org_down`), Transactions (per-event processing history), System Logs.

**Project** (scoped to the selected project; items marked *admin-only* are hidden from operators/viewers) — Salesforce Orgs, Events & Flows, Integrations *(admin)*, SharePoint *(admin)*, Processors *(admin)*, Rules *(admin)*.

**Administration** (admin role only) — Projects, Alerts, Users, Security, Admin Configuration.

**Admin Configuration** is a tabbed settings page with ten tabs: Processing, DSS (Dataiku), Langflow, Processors, Rules, Message Broker, Database, Email, Docs, and Backup. The Backup tab is where configuration export/import is performed (see *Backup, Export & Recovery*).

**Events & Flows** is where subscribe/publish channels are configured. A subscribe channel now supports multiple named **Event Pipelines**, each independently enabled and each with its own visual flow graph, edited on the Event Flow Designer canvas. The system automatically migrates a legacy single-graph event into a pipeline named "Default" the first time its pipelines are read (`ensure_default_pipeline`), so no manual migration step is required when upgrading.

## Security Configuration

- **Token signing & session settings** — JWT secret/algorithm and expiry are set via environment variables (see *Appendix*); rotate the signing secret on a defined schedule and immediately on suspected compromise.
- **Login throttling** — `max_failed_login_attempts` and `lockout_duration_seconds` bound brute-force attempts; confirm these are set to values consistent with your organization's password policy rather than left at defaults.
- **Database credentials** — configured per backend (SQLite/Postgres/SQL Server/Oracle) in the Database tab / environment variables; the driver for a non-default backend (e.g. `psycopg2-binary` for Postgres) must be installed explicitly, since only the driver for the active `DATABASE_TYPE` is expected to be enabled in `requirements.txt`.
- **SSO** — optional; when unconfigured, all authentication falls back to local username/password plus JWT.
- **Unauthenticated endpoints — by design, but worth reviewing.** `backend/app/routers/health.py` exposes `/healthz`, `/readyz`, and `/metrics` without `Depends(get_current_user)`. This is conventional for Kubernetes liveness/readiness probes and Prometheus scraping, but `/metrics` returns internal circuit-breaker/state snapshot data, so it should sit behind network-level restriction (a cluster-internal network policy, or an API-gateway rule) rather than being reachable from the public internet.
- **Transport security** is not configured at the application layer (no TLS termination in the FastAPI app itself); TLS must be provided by a reverse proxy or load balancer in front of the service.

## Data Flow & Event Processing

1. A subscribe channel's CometD client receives a Platform Event from the connected Salesforce org and hands it to the broker (in-process by default, or RabbitMQ when configured) as a message on an inbound topic.
2. `inbound_worker.handle()` picks up the message and resolves the event's enabled pipelines via `list_enabled_pipelines()`. If the event has never been queried before, `ensure_default_pipeline()` migrates its legacy `flow_graph` into a pipeline named "Default" on first read.
3. When more than one pipeline is enabled, the worker fans out and runs each as an independent child transaction — a failure or rule-gate rejection in one pipeline does not block the others.
4. Each pipeline executes its flow graph via `flow_walker.run_flow_graph()`: an optional rule gate (a GoRules JDM decision graph evaluated by `zen-engine`) can stop the event from proceeding; transform nodes reshape the payload; processor nodes call out to configured integrations (Dataiku DSS, Langflow, SharePoint, generic HTTP, etc.).
5. A pipeline that reaches a publish node hands the resulting payload back to the broker on an outbound topic, which is published to the target Salesforce org (the same org or a different one, depending on configuration).
6. Every stage is recorded to Transactions and, on failure, surfaces on the Dashboard's attention list and the notification inbox; sustained failures can be configured to raise an Alert.

If no pipeline produces a runnable graph, the worker falls back to the legacy single-`flow_graph` execution path for backward compatibility with events that predate the pipelines feature.

## Standard Operating Procedures

**Connect a Salesforce org.** Projects → select project → Salesforce Orgs → add org credentials. Verify the org shows connected on the Dashboard before configuring events against it.

**Add a subscribe channel with a pipeline.** Events & Flows → create the subscribe channel → open its Event Pipelines page → create a named pipeline → open the Flow Designer canvas and build the flow graph (rule gate, transform, processor/integration nodes, publish target) → enable the pipeline. Add further pipelines on the same event for independent processing paths (e.g., one path per downstream system) — each is enabled/disabled independently.

**Disable a pipeline without deleting it.** Event Pipelines page → toggle the pipeline off. A disabled pipeline is skipped by the worker but its flow graph and history are retained.

**Add a user / change a role.** Administration → Users → create or edit the user, assign one of admin / operator / viewer. Because role checks are global rather than project-scoped (see *Roles, Authentication & Access Control*), grant operator/admin only to people who should be able to act on **every** project, not just one.

**Investigate a failing event.** Dashboard → attention list (`failed`, `no_pipeline`, `org_down` items) or the topbar notification inbox → open the linked event/transaction → Transactions page for the detailed history → System Logs for the underlying error.

**Rotate credentials.** Update the Salesforce org's stored credentials on the Orgs page, and rotate the JWT signing secret and any integration API keys via environment variables/Admin Configuration, on a defined schedule and immediately after any suspected exposure.

## Backup, Export & Recovery

Admin Configuration → Backup provides a full configuration export/import (`backend/app/routers/admin_config.py`, `EXPORT_VERSION = 3`). Export produces a versioned JSON bundle; import applies an upsert-by-id pass per table (existing rows are updated in place by id, new rows are inserted — nothing is deleted by an import).

As of this manual's writing, export/import covers all configuration tables, including **Event Pipelines** and saved **Flow Templates** — a gap where both were silently omitted was found and fixed (see the changelog note below).

**Recommended cadence.** Take a configuration export before any bulk change (rules, pipeline restructuring, processor reconfiguration) and on a routine schedule (e.g., daily or weekly depending on change velocity). Store exports outside the application host, and treat the exported JSON as containing sensitive configuration (connection strings, integration settings) — handle it with the same access controls as production credentials.

**What backup/restore does not cover.** This mechanism backs up *configuration* (orgs, events, pipelines, rules, processors, users, etc.), not the underlying database engine's data files, and not Salesforce-side data. A full disaster-recovery plan needs a separate database-level backup (per your configured `DATABASE_TYPE`) in addition to this export.

**Changelog note for auditors.** A recent code review found that `event_pipelines` and `flow_templates` were missing from the export/import table list, meaning a restore performed after upgrading to the multi-pipeline feature would silently drop all non-Default pipelines and any saved flow templates. This was fixed and shipped in pull request #4 to the project's GitHub repository; confirm that fix is deployed before relying on backup/restore for pipelines created after the multi-pipeline feature was introduced.

## Compliance & Audit Considerations

This section maps the system's actual behavior to control areas a general IT or security audit (SOC 2, ISO 27001, CMMC, or similar) typically examines. It is a starting point for a control-mapping exercise, not a certification claim — no framework-specific control mapping has been performed, and the target framework should be confirmed before this section is relied on as evidence (see the open question at the end of this document).

**Access control.** Authentication is required on every route (JWT + `get_current_user`); role-based checks (`require_role`) gate mutating operations. Login lockout limits brute-force attempts. **Gap:** authorization is role-based but not project-scoped — see *Roles, Authentication & Access Control*. An auditor testing least-privilege or multi-tenant segregation should expect this to fail as currently implemented.

**Audit logging.** `log_event()` calls are made throughout the routers reviewed (pipeline creation, org changes, etc.) and are visible on the System Logs page. **Gap:** logging coverage was not exhaustively verified against every mutating endpoint in this review; confirm log retention settings (see *Appendix*, settings log rotation variables) meet your required retention period before citing this as a complete audit trail.

**Configuration change control.** The Backup/export mechanism (see previous section) provides a point-in-time, versioned configuration snapshot that can support change-control evidence, but it is manually triggered — there is no automatic export on every configuration change, so evidentiary value depends on operators following the recommended backup cadence.

**Data protection in transit.** TLS is not terminated by the application itself and must be supplied by infrastructure in front of it (see *Security Configuration*). Confirm this is in place in your deployment before treating data-in-transit as protected.

**Vulnerability/patch management.** Dependency versions are pinned in `requirements.txt`; there is no automated dependency-scanning or patch-management process evident in the codebase itself — this is an operational process that must exist outside the application.

**Known technical gaps relevant to an audit** are detailed in full in the next section; the most audit-relevant are the project-authorization gap above, unauthenticated `/metrics` exposure, and an incomplete database-migration tool (Alembic scaffold).

## Known Limitations & Technical Debt

These were found by direct code inspection and are listed here so they are documented rather than discovered for the first time during an audit.

1. **Project-level authorization is not enforced (see *Roles, Authentication & Access Control*).** Role checks are global, not scoped to a user's assigned project(s). Any operator/admin can act on any project's resources via the API. Recommended remediation: add project-membership checks alongside the existing role checks on project-scoped routes.
2. **`/healthz`, `/readyz`, `/metrics` are unauthenticated.** Intentional for probe/scraping tooling, but `/metrics` exposes internal circuit-breaker state. Recommended: restrict at the network layer (internal-only route, gateway rule) rather than authenticating in-app, to avoid breaking probes.
3. **The Alembic migration scaffold is non-functional.** `backend/alembic.ini` points to a hardcoded Postgres connection string, `alembic/versions/001_baseline.py` is an empty no-op (`upgrade`/`downgrade` both `pass`), there is no `env.py`, and the `alembic` package is not even listed in `requirements.txt`. Running `alembic upgrade head` would fail immediately. There is currently no working, version-controlled schema-migration tool for this project — schema changes must be tracked and applied manually. An auditor checking for controlled schema-change management should treat this as unimplemented, not as a broken instance of an otherwise-working control.
4. **`app/circuit.py` (per-sink circuit breaker) references configuration that does not exist.** It reads `settings.circuit_open_seconds` and `settings.circuit_fail_threshold`, neither of which is defined in `backend/app/config.py`. It would raise `AttributeError` if invoked. Currently it has no callers anywhere in the codebase, so it is inert — but it is a landmine for whoever wires it into the dispatch path in the future without also adding the missing settings.
5. **`app/http_timeouts.py` has the same pattern.** It references `settings.http_connect_timeout`, `settings.http_read_timeout`, and `settings.http_write_timeout`, none of which exist in `config.py`, and also currently has no callers. Same recommendation as above: add the missing settings before either module is wired in, or remove the modules if they are not planned for use.
6. **Two verified functional bugs in the Event Pipelines feature were found and fixed this cycle** (flow\_graph clobbering on multi-pipeline events; missing export/import coverage for pipelines and flow templates) — shipped as pull request #4. Confirm that PR is merged and deployed; the *Backup, Export & Recovery* section above depends on it.

None of items 1–5 are exploitable defects in the sense of a live vulnerability being actively triggered by normal use — items 3–5 are dead or unimplemented code paths, and item 2 is a common, deliberate pattern. They are listed because an audit should document known gaps rather than have them surface as surprises.

## Appendix: Environment Variable Reference

From `backend/app/config.py`'s `Settings` class, grouped by area. Exact defaults should be read from that file at deploy time; this appendix documents what exists and its purpose, not current values.

**Authentication / JWT** — JWT secret key, signing algorithm, and token expiry settings; `max_failed_login_attempts` and `lockout_duration_seconds` for login throttling.

**Database** — `DATABASE_TYPE` (sqlite / postgres / sqlserver / oracle) and the corresponding connection settings for whichever backend is active. Only the driver for the active type needs to be installed (see *Security Configuration*).

**Logging** — log level and log-rotation settings (file size/backup-count style rotation), governing how long System Logs history is retained on disk.

**Message broker** — broker mode (in-process vs. RabbitMQ) and RabbitMQ connection settings when that mode is selected.

**Worker / CometD tuning** — settings controlling CometD client reconnect/timeout behavior and worker concurrency.

**Processing** — `processor_timeout_seconds`, bounding how long a single processor/integration call in a flow graph is allowed to run before timing out.

**Server (uvicorn)** — host/port/worker-process settings for the ASGI server.

**OpenTelemetry** — optional tracing exporter settings (OTLP endpoint, service name); safe to leave unconfigured, in which case tracing is simply inactive.

**SSO** — optional identity-provider settings for delegated login; unset by default, falling back to local authentication.

For the authoritative, current list of every variable, its default, and any validation applied to it, read `backend/app/config.py` directly — this appendix is a map of what to look for there, not a substitute for it.
