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
- [x] Additional OpenAI-compatible providers: Groq, DeepSeek, Mistral AI, and xAI (credentials and model discovery)

## Milestone 2 — Identity and workspace
- [x] Registration/login with PBKDF2 password hashes and opaque expiring bearer sessions
- [x] Workspace creation and membership listing (owner role)
- [x] Session logout and revocation endpoint
- [x] Workspace scoping for conversations, messages, agents, workflows, and agent-run history
- [x] Login/register and workspace selection in the web UI
- [x] Scoped public API keys with one-time secret display, expiry, and revocation
- [x] Per-key request throttling and workspace audit log foundation
- [x] Workspace RBAC roles (owner/admin/member), membership administration, and owner protection
- [ ] Email verification, advanced rate limiting, and secrets management for provider credentials
- [ ] Runtime database abstraction and PostgreSQL as the production backend
- [x] One-way SQLite-to-PostgreSQL migration utility with dependency ordering and row-count verification
- [ ] Versioned schema migrations and rollback strategy
- [x] SQLite online snapshot backup, optional Fernet encryption, SHA-256 verification, and tested restore utility
- [ ] Scheduled off-host backups, retention policy, and restore drills

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
- [x] Workspace webhook endpoint registry, encrypted signing secrets, HTTPS host allowlist, HMAC-signed delivery, event hooks, and delivery history
- [x] Durable webhook delivery records, authenticated dispatch worker, exponential retries/backoff (8 attempts), and delivery history API
- [x] Webhook management UI for endpoint creation, test delivery, and delivery history
- [ ] Dead-letter replay controls and additional external integrations

## Milestone 5 — MCP
- [x] MCP client with Streamable HTTP and administrator-allowlisted stdio transports
- [x] Workspace-scoped MCP server registry and tool discovery
- [x] Per-tool explicit approval and revocation before invocation
- [x] Optional bearer token encrypted at rest (Fernet), with rotation and revocation
- [x] Separate read-only APOLO MCP server over Streamable HTTP (local-only Compose binding)
- [x] MCP OAuth authorization-server discovery, PKCE S256 authorization URL, one-time state callback, encrypted token storage, and resource-bound token exchange
- [x] OAuth refresh-token rotation with encrypted token endpoint/client/resource metadata and browser connect/status controls
- [ ] OAuth revocation endpoint integration and external-provider interoperability tests
- [ ] Audit log, quotas, and per-tool policy scopes

## Milestone 6 — Production readiness
- [x] API key scope, expiry, revocation, and per-key rate-limit tests
- [x] Dependabot weekly updates for Python, npm, and GitHub Actions dependencies
- [x] CI security workflow for pip-audit, npm audit, and Gitleaks secret scanning
- [ ] Independent security review, remediation of scanner findings, and runtime penetration tests
- [x] Persistent login rate limiting and baseline API security response headers
- [x] Additional cross-workspace tests for webhook delivery access
- [x] Provider usage metering for upstream-reported prompt/completion/total tokens and latency (non-streaming chat)
- [x] Workspace monthly request/token quotas with owner/admin configuration and audit events
- [x] Workspace usage summary and event history API; provider cost remains null unless upstream reports it
- [x] API-key-specific monthly token/request quotas and usage summary endpoint
- [x] Streaming token usage capture (OpenAI-compatible, Anthropic, Gemini), latency/status recording, and API-key attribution/quotas
- [ ] Provider usage metering, quotas, and cost guardrails
- [ ] Deployment guides and observability
- [ ] Accessibility, localization, and mobile-responsive QA

## Non-negotiable product rules
- APOLO itself has no paid plan or feature paywall.
- Provider API usage is governed by each provider's terms and quota.
- No credential sharing, billing bypass, hidden proxying, or false unlimited-free claims.
- Untrusted tools and MCP servers must never execute without explicit workspace authorization.
