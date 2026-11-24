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
- [x] Streaming responses (SSE) for OpenAI-compatible, Anthropic, and Gemini adapters
- [x] Persistent conversations and message storage (SQLite foundation)
- [ ] Message branching and provider-native token streaming
- [x] Live model discovery adapters (provider credentials required)
- [ ] Free-quota and rate-limit metadata; never label paid models as free

## Milestone 2 — Identity and workspace
- [x] Registration/login with PBKDF2 password hashes and opaque expiring bearer sessions
- [x] Workspace creation and membership listing (owner role)
- [x] Session logout and revocation endpoint
- [x] Workspace scoping for conversations, messages, agents, workflows, and agent-run history
- [x] Login/register and workspace selection in the web UI
- [ ] Roles, audit log, secrets management, email verification, and rate limiting
- [ ] Database migrations and backups

## Milestone 3 — Agents and tools
- [x] Agent registry API with instructions, model selection, and tool metadata
- [x] Bounded single-agent execution endpoint
- [x] Multi-agent orchestration (maximum 5 agents/steps) with workspace-scoped run tracing
- [x] Agent builder UI with model selection, prompt configuration, and run console
- [ ] Tool registry with explicit allowlists and approval gates
- [ ] Tool-call execution sandbox and timeouts
- [ ] Streaming agent runs and cancellation

## Milestone 4 — Workflow automation
- [x] Workflow definition registry API (JSON nodes/edges storage)
- [x] Visual sequential node editor (input, prompt, model, output)
- [x] Safe workflow execution engine with DAG validation, cycle rejection, and bounded node/edge counts
- [x] Workspace-scoped workflow run history
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
