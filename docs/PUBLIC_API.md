# APOLO LangDock public API

## Authentication

Create a key in the workspace's **API e chaves** screen or call `POST /api/v1/api-keys` with a user bearer session and `X-Workspace-ID`. The complete key is returned once. Store it in a secrets manager; the database stores only its SHA-256 hash.

Supported scopes:
- `models:read`: query `GET /api/v1/public/models`.
- `chat:completions`: call `POST /api/v1/public/chat/completions`.

Keys are workspace-scoped, can expire in 1–365 days, and can be revoked at any time. The default limit is 60 requests/minute per key; set `APOLO_API_KEY_RPM` on the API server to change it (hard maximum 600).

## Chat completion example

```bash
curl https://YOUR_HOST/api/v1/public/chat/completions \
  -H "X-API-Key: apolo_sk_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"ollama/llama3.2","messages":[{"role":"user","content":"Olá"}]}'
```

## Security and cost

- Never put API keys in browser source, public repositories, or client-side mobile binaries.
- Use TLS for every public deployment.
- Rotate or revoke leaked keys immediately.
- Audit events are available to workspace members at `GET /api/v1/audit-logs`.
- The API rate limit protects the APOLO endpoint; it does not guarantee a free upstream model. Provider billing, free-tier limits, and model availability still apply.
- This initial public API supports chat completions and model discovery only. Tool/MCP execution scopes are intentionally not exposed.
