# Changelog

## 1.2.6 — 2026-09-28

### Dataiku Phase A
- Reuse one `DSSClient` + LLM handle in-process (no new TLS/import per question)
- Background warmup completion on API start (`DSS_WARMUP_ON_START`, default true)
- Fallback: `DSS_USE_SUBPROCESS=true` restores per-call Popen
- `DSS_TIMEOUT_SECONDS` default 180

## 1.2.5 — 2026-09-28

- Integrations fire only when the flow names them

## 1.2.4 — 2026-09-28

- Restored integrations; `requests_timeout` import

## 1.2.3 — 2026-09-28

- Edit / disable / delete scheduled jobs
