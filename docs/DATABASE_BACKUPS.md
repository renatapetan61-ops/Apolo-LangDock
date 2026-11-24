# Database backups and restore

## Create a backup

The backup utility uses SQLite's online backup API, checks `PRAGMA integrity_check`, writes a manifest with SHA-256, and packages the snapshot in a ZIP archive.

```bash
python scripts/backup_database.py --source /data/apolo-langdock.sqlite3 --output /backups/apolo-$(date -u +%Y%m%dT%H%M%SZ).zip
```

For encryption, generate a Fernet key and set `APOLO_BACKUP_FERNET_KEY` in the backup runner's secret store. The resulting file is encrypted; the key is never stored in the archive or repository.

## Restore

Restore to a new path first. The utility decrypts (when configured), checks archive contents, verifies SHA-256 and SQLite integrity, and refuses to overwrite an existing destination unless `--force` is explicit.

```bash
python scripts/backup_database.py --restore /backups/apolo-backup.zip --destination /data/restore-check.sqlite3
```

Do not use `--force` on the live database as a routine restore procedure. Validate the restored copy, stop application writes, preserve the current database separately, then perform a planned cutover.

## Production requirements still open

- Schedule backups outside the API process and store them off-host.
- Define retention, access control, encryption-key rotation, and recovery-point objectives.
- Test restore on a separate environment and document recovery-time objectives.
- PostgreSQL runtime migration and PostgreSQL-native backup/PITR are not yet implemented.
