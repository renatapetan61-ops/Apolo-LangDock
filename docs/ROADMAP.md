# APOLO LangDock roadmap

## Milestone 0 — Repository foundation
- [x] Public repository scaffold
- [x] Next.js workspace shell
- [x] FastAPI health, provider catalog, and chat endpoint foundation
- [x] Server-side adapters for OpenAI, Anthropic, Gemini, OpenRouter, and Ollama
- [x] Docker Compose development setup
- [x] CI build checks

## Milestone 1 — Functional multi-model chat
- [ ] Validate provider adapters against real accounts and current API schemas
- [ ] Streaming responses (SSE)
- [ ] Persistent conversations and message branching
- [ ] Model discovery from provider APIs
- [ ] Free-quota and rate-limit metadata; never label paid models as free

## Milestone 2 — Identity and workspace
- [ ] Authentication, user sessions, workspace membership
- [ ] Roles, permissions, audit log, and secrets management
- [ ] Database migrations and backups

## Milestone 3 — Agents and tools
- [ ] Agent builder with instructions and model selection
- [ ] Tool registry with explicit allowlists and approval gates
- [ ] Tool-call execution sandbox and timeouts
- [ ] Agent run history and tracing

## Milestone 4 — Workflow automation
- [ ] Visual node editor
- [ ] Triggers, schedules, conditions, loops, and retries
- [ ] Durable execution queue and run history
- [ ] Webhooks and external integrations

## Milestone 5 — MCP
- [ ] MCP client with stdio and Streamable HTTP transports
- [ ] MCP server publishing for selected APOLO tools
- [ ] Per-server trust settings, authentication, and tool approvals

## Milestone 6 — Production readiness
- [ ] Automated tests, dependency scanning, and security review
- [ ] Rate limits, quotas, and cost guardrails
- [ ] Deployment guides and observability
- [ ] Accessibility, localization, and mobile-responsive QA

## Non-negotiable product rules
- APOLO itself has no paid plan or feature paywall.
- Provider API usage is governed by each provider's terms and quota.
- No credential sharing, billing bypass, hidden proxying, or false unlimited-free claims.
- Untrusted tools and MCP servers must never execute without explicit workspace authorization.
