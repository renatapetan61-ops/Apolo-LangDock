# APOLO LangDock deployment checklist

This guide is a readiness checklist. It does not mean a production deployment has been performed.

## Required decisions before launch

- Choose a managed PostgreSQL service. The current SQLite database is a single-instance development foundation and is not a multi-instance production database.
- Choose a supported web and API hosting target, configure DNS, and terminate TLS at a trusted reverse proxy or platform edge.
- Set the production web origin in CORS_ORIGINS; do not use wildcard CORS with credentials.
- Configure provider API keys only for providers that are intended to be enabled.
- Configure APOLO_MCP_ENCRYPTION_KEY using a secret manager. Generate and back it up securely; never commit it.
- Configure MCP_ALLOWED_HOSTS with exact approved MCP hostnames. Keep stdio aliases administrator-managed.
- Set strong, unique database credentials and persistent encrypted backups.
- Set explicit workspace quotas and API-key rate limits based on expected workload.
- Keep the MCP service bound to localhost or a private network unless protected by TLS, authentication, and network policy.

## Pre-release verification

- Run normal CI and security workflows; resolve all high/critical dependency and secret-scan findings.
- Run API tests against a disposable PostgreSQL database after the database adapter/migrations are implemented.
- Test registration, login, logout, workspace isolation, RBAC, API-key revocation, quota enforcement, MCP approval gates, and credential rotation.
- Verify provider usage records against real provider responses without assuming every provider returns token/cost metadata.
- Verify webhook signatures and retry behavior after webhook delivery is implemented.
- Configure structured logs, metrics, alerting, uptime checks, and incident response contacts.
- Perform an independent security review and backup restore drill.
- Publish a versioned release with migration notes and a rollback procedure.

## Current blockers

- PostgreSQL adapter, migrations, and tested backup/restore are not implemented.
- OAuth 2.1 authorization-code/PKCE for MCP is not implemented; current remote MCP auth is encrypted bearer-token configuration.
- Webhook subscriptions and delivery workers are not implemented.
- Streaming token metering and API-key-specific consumption budgets remain pending.
- Security workflows have been added, but their findings still need to complete and be reviewed.
- No production hosting target, DNS, TLS configuration, or deployment has been applied from this repository yet.
