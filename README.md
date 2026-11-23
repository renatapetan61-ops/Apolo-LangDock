# APOLO LangDock

An independent, open-source AI workspace inspired by the capabilities the project owner wants from LangDock. This project is not affiliated with Langdock GmbH and does not copy proprietary Langdock source code or branding.

## Goals

- One workspace for multiple LLM providers through a provider adapter layer.
- Chat UI with model selection and conversation history.
- Agent definitions and tool execution with explicit permission boundaries.
- Visual workflow authoring and execution.
- MCP client/server integration.
- OpenAI-compatible REST API.
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

This repository is being initialized. The first milestone is a runnable foundation with health checks, provider configuration, and a basic chat interface. Agents, workflows, MCP, persistence, authentication, and production hardening will be delivered incrementally and validated by CI.

## Quick start

Requirements: Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

The API health endpoint will be available at `http://localhost:8000/health`. The web app will be available at `http://localhost:3000`.

## Security

- Keep provider API keys in server-side environment variables or a secrets manager.
- Never expose provider keys to browser code.
- Treat tool execution and MCP servers as untrusted until explicitly configured.
- Use authentication and network isolation before exposing a deployment publicly.

## License

MIT. See [LICENSE](LICENSE).
