# Database migration: SQLite to PostgreSQL

## Current state

The API runtime still uses SQLite. The repository now includes a guarded, one-way migration utility at `scripts/migrate_sqlite_to_postgres.py`. This is a data-transfer tool, not a claim that the running API has switched to PostgreSQL.

## Safe migration procedure

1. Stop API writes and create a filesystem snapshot of the SQLite database.
2. Provision a new, empty PostgreSQL database and a least-privilege application role.
3. Set `APOLO_DB_PATH` to the snapshot path and `APOLO_DATABASE_URL` to the PostgreSQL connection URL in a secure environment (never commit either secret).
4. Install API dependencies and run `python scripts/migrate_sqlite_to_postgres.py`.
5. Confirm the reported table and row counts, then run application-level cross-workspace, API-key, webhook, MCP OAuth, and usage tests against PostgreSQL before any runtime cutover.
6. Keep the SQLite snapshot read-only until the PostgreSQL deployment has passed restore and rollback drills.

The utility refuses a target database that already contains tables, creates schema objects and data in foreign-key dependency order, recreates explicit indexes, and verifies every table's row count inside one PostgreSQL transaction. It does not drop or overwrite target objects.

## Important limitations before production cutover

- The API still opens SQLite connections directly; setting `APOLO_DATABASE_URL` alone does not change runtime storage.
- SQLite-specific SQL, PRAGMA-based compatibility migrations, transaction semantics, and concurrent-write behavior still need a reviewed database abstraction and integration tests.
- PostgreSQL migration should be performed against a fresh target and a quiesced source to avoid missing writes.
- Versioned schema migrations, automated backups, encryption/key retention, and a tested point-in-time restore procedure remain required before production.
