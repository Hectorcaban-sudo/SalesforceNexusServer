# Flowise on the Nexus Docker network

## URLs

| From | URL |
|------|-----|
| Browser | http://localhost:3000 |
| Nexus container / other services | http://flowise:3000 |
| Prediction API | `POST http://flowise:3000/api/v1/prediction/{chatflowId}` |

## Company OpenAI-compatible gateway (custom header + CA)

1. Copy your PEM into `./certs/` (e.g. `CA03_Base64_FullRootChain.pem`).
2. In `.env`:
   ```
   FLOWISE_NODE_EXTRA_CA_CERTS=/certs/CA03_Base64_FullRootChain.pem
   ```
3. Restart: `docker compose up -d flowise`

### ChatOpenAI node settings

- **Credential**: OpenAI API key = your company API key  
- **Additional Parameters → Base Path**: your gateway base (often `https://…/v1`)  
- **Base Options** (JSON), if they require the `apikey` header:

```json
{
  "headers": {
    "apikey": "YOUR_KEY"
  }
}
```

If TLS still fails, the CA is not trusted yet — confirm the file is mounted and `NODE_EXTRA_CA_CERTS` points at the **container** path.

## Optional UI auth

```
FLOWISE_USERNAME=admin
FLOWISE_PASSWORD=change_me
```

## Deploy

```bash
docker compose up -d --build
# or Windows: deploy-wsl.bat
```

Flowise data (flows, credentials, logs) persists in volume `nexus-flowise-data`.
