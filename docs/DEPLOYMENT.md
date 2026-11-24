# APOLO LangDock deployment checklist

This guide is a readiness checklist. It does not mean a production deployment has been performed.

## Current state and blockers

- The API runtime still uses SQLite. A one-way SQLite-to-PostgreSQL transfer utility exists, but PostgreSQL is not yet the runtime backend.
- Versioned schema migrations and a production rollback procedure remain open.
- SQLite backup/restore tooling now supports optional Fernet encryption and SHA-256/integrity verification. Off-host scheduling, retention, and restore drills remain open.
- MCP OAuth 2.1 authorization-code/PKCE, refresh-token rotation, and a browser connect/status flow are implemented. Provider revocation integration and external interoperability testing remain open.
- Webhook registry, encrypted secrets, signed delivery, durable retry records, a protected dispatch worker, and a management UI are implemented. The worker still needs a scheduled private runner; dead-letter replay controls remain open.
- Streaming usage is recorded when the provider returns token metadata; missing token counts and costs remain unknown rather than estimated.
- CI and security workflows are active. A successful workflow is not proof of a production deployment.
- No production hosting target, DNS, TLS configuration, or deployment has been applied from this repository.

## Required before production

1. Complete a PostgreSQL runtime adapter and run the full API suite against a disposable PostgreSQL instance.
2. Implement versioned schema migrations, rollback, and PostgreSQL backup/PITR.
3. Choose managed database, API hosting, web hosting, DNS, and TLS.
4. Set exact `CORS_ORIGINS`; never use wildcard CORS with credentials.
5. Configure provider keys only for providers intended to be enabled. Keep all keys server-side.
6. Configure `APOLO_MCP_ENCRYPTION_KEY`, `APOLO_WEBHOOK_WORKER_TOKEN`, and optional `APOLO_BACKUP_FERNET_KEY` in a secret manager.
7. Configure exact `MCP_ALLOWED_HOSTS` and `WEBHOOK_ALLOWED_HOSTS`; do not use broad wildcards.
8. Set `APOLO_MCP_OAUTH_CLIENT_ID` and the HTTPS callback URL when enabling MCP OAuth.
9. Schedule `POST /internal/webhooks/dispatch` through a private job runner and the worker token.
10. Configure structured logs, redaction, error monitoring, database metrics, uptime checks, and alerting.
11. Verify restore, OAuth refresh/rotation, webhook retry, quota enforcement, and provider streaming on staging.
12. Complete independent security review, cross-workspace penetration tests, release notes, and rollback rehearsal.

## Local staging

1. Copy `.env.example` to a private `.env` file.
2. Generate a Fernet key and set `APOLO_MCP_ENCRYPTION_KEY` before configuring MCP or webhook secrets.
3. Set `CORS_ORIGINS` to the exact web origin.
4. Configure provider keys and allowlists only when needed.
5. Run `docker compose up --build` and verify `/health`, `/api/v1/providers`, login, workspace isolation, chat, MCP, and webhook flows.

Do not publish a production release until PostgreSQL runtime, migration, backup, and staging gates are closed. A green CI run alone is not a release approval.
