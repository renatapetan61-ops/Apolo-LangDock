# APOLO LangDock

An independent, open-source AI workspace inspired by the capabilities the project owner wants from LangDock. This project is not affiliated with Langdock GmbH and does not copy proprietary Langdock source code or branding.

## Goals

- One workspace for multiple LLM providers through a provider adapter layer.
- Chat UI with model selection and conversation history.
- Agent definitions and tool execution with explicit permission boundaries.
- Visual workflow authoring and execution.
- MCP client/server integration.
- OpenAI-compatible REST API with workspace-scoped API keys and per-key rate limits.
- Admin controls, usage accounting, and provider quota visibility.
- Self-hostable deployment with no APOLO subscription or paid feature tiers.

## Important cost and availability policy

APOLO LangDock software is intended to be free and open source. Model inference is a separate service: commercial frontier models (including GPT, Claude, and some Gemini tiers) are not universally or indefinitely free. The app must only advertise a model as free when its provider currently grants a free quota or when the model is run locally. It must never bypass provider billing, share private API keys, or claim unlimited free access to paid models.

## Initial architecture

- `apps/web`: Next.js web workspace.
- `apps/api`: FastAPI backend and OpenAI-compatible API.
- `packages/providers`: provider adapters and model catalog.
- `packages/agents`: agent and tool runtime.
- `packages/workflows`: workflow schema and executor.
- `packages/mcp`: MCP integration.
- `infra`: local development and deployment configuration.

## Development status

The repository now includes multi-provider chat, persistent workspace data, bearer authentication, agent and workflow execution foundations, and an initial MCP client/server integration. Production hardening, provider validation, OAuth credentials, quotas, and deployment review remain in progress.

## Quick start

Requirements: Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

The API health endpoint will be available at `http://localhost:8000/health`. The web app will be available at `http://localhost:3000`.

## MCP integration (initial)

- The API uses the official MCP Python SDK for Streamable HTTP and stdio clients.
- Remote HTTP servers must use HTTPS and an exact hostname in `MCP_ALLOWED_HOSTS`.
- Stdio processes must be defined by the administrator in `MCP_STDIO_SERVERS_JSON`; workspace users cannot submit commands or arguments.
- Discovered tools are denied by default. A workspace must explicitly approve each tool before invocation.
- The separate read-only APOLO MCP server is bound to `127.0.0.1:8765` by Docker Compose. Do not expose it publicly without authentication, TLS, rate limits, and an audit policy.
- Optional bearer tokens for remote HTTP servers are encrypted at rest with `APOLO_MCP_ENCRYPTION_KEY` (Fernet); rotate or revoke them from the MCP workspace screen. OAuth flows and production authorization remain pending.

## Security

- Keep provider API keys in server-side environment variables or a secrets manager.
- Never expose provider keys to browser code.
- Treat tool execution and MCP servers as untrusted until explicitly configured.
- Use authentication and network isolation before exposing a deployment publicly.

## License

MIT. See [LICENSE](LICENSE).
