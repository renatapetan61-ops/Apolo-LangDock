#!/usr/bin/env python3
"""Create and verify restorable SQLite backups; optional Fernet encryption."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(source: Path, target: Path) -> None:
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        result = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError("SQLite integrity_check failed: " + str(result))
    finally:
        dst.close()
        src.close()


def create_backup(source: Path, output: Path, encryption_key: str | None) -> dict:
    if not source.is_file():
        raise FileNotFoundError(f"SQLite source not found: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apolo-backup-") as temp:
        temp_dir = Path(temp)
        snapshot_path = temp_dir / "database.sqlite3"
        snapshot(source, snapshot_path)
        manifest = {
            "format": "apolo-sqlite-backup-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sha256": sha256_file(snapshot_path),
            "size_bytes": snapshot_path.stat().st_size,
        }
        archive_path = temp_dir / "backup.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot_path, "database.sqlite3")
            archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        payload = archive_path.read_bytes()
        if encryption_key:
            payload = Fernet(encryption_key.encode("ascii")).encrypt(payload)
        output.write_bytes(payload)
    return {**manifest, "encrypted": bool(encryption_key), "backup": str(output)}


def restore_backup(backup: Path, destination: Path, encryption_key: str | None, force: bool) -> dict:
    if destination.exists() and not force:
        raise FileExistsError("Destination exists; use --force only after making a separate copy.")
    payload = backup.read_bytes()
    if encryption_key:
        try:
            payload = Fernet(encryption_key.encode("ascii")).decrypt(payload)
        except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("Backup decryption failed; check APOLO_BACKUP_FERNET_KEY.") from exc
    with tempfile.TemporaryDirectory(prefix="apolo-restore-") as temp:
        archive_path = Path(temp) / "backup.zip"
        archive_path.write_bytes(payload)
        with zipfile.ZipFile(archive_path, "r") as archive:
            if set(archive.namelist()) != {"database.sqlite3", "manifest.json"}:
                raise RuntimeError("Backup archive contents are invalid.")
            archive.extract("database.sqlite3", temp)
            manifest = json.loads(archive.read("manifest.json"))
        snapshot_path = Path(temp) / "database.sqlite3"
        if manifest.get("format") != "apolo-sqlite-backup-v1" or sha256_file(snapshot_path) != manifest.get("sha256"):
            raise RuntimeError("Backup manifest or SHA-256 verification failed.")
        check = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True)
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError("Restored database failed SQLite integrity_check.")
        finally:
            check.close()
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name(destination.name + ".restore-tmp")
        shutil.copy2(snapshot_path, staging)
        os.replace(staging, destination)
    return {"restored": str(destination), "sha256": manifest["sha256"], "integrity_check": "ok"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.getenv("APOLO_DB_PATH", "/data/apolo-langdock.sqlite3"))
    parser.add_argument("--output", help="Backup output path (.zip or encrypted binary)")
    parser.add_argument("--restore", help="Restore from a backup archive")
    parser.add_argument("--destination", help="New SQLite destination path")
    parser.add_argument("--force", action="store_true", help="Replace an existing destination after verification")
    args = parser.parse_args()
    key = os.getenv("APOLO_BACKUP_FERNET_KEY", "").strip() or None
    try:
        if args.restore:
            if not args.destination:
                parser.error("--destination is required with --restore")
            result = restore_backup(Path(args.restore), Path(args.destination), key, args.force)
        else:
            if not args.output:
                parser.error("--output is required when creating a backup")
            result = create_backup(Path(args.source), Path(args.output), key)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"Backup operation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
