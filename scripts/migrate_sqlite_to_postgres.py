#!/usr/bin/env python3
"""One-way, transactional SQLite -> PostgreSQL migration for APOLO LangDock.

The target PostgreSQL database must be empty. The script never drops target
objects, never logs credentials, and verifies row counts before committing.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict, deque
from pathlib import Path

import psycopg
from psycopg import sql


def quote_identifier(value: str) -> sql.Identifier:
    return sql.Identifier(value)


def table_names(source: sqlite3.Connection) -> list[str]:
    rows = source.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def dependency_order(source: sqlite3.Connection, names: list[str]) -> list[str]:
    known = set(names)
    deps: dict[str, set[str]] = {}
    for name in names:
        refs = {row[2] for row in source.execute(f'PRAGMA foreign_key_list("{name}")')}
        deps[name] = refs & known
    result: list[str] = []
    ready = deque(sorted(name for name in names if not deps[name]))
    while ready:
        name = ready.popleft()
        result.append(name)
        for other in names:
            if name in deps[other]:
                deps[other].remove(name)
                if not deps[other] and other not in result and other not in ready:
                    ready.append(other)
    if len(result) != len(names):
        cycle = sorted(name for name in names if name not in result)
        raise RuntimeError("Foreign-key dependency cycle; manual migration review required: " + ", ".join(cycle))
    return result


def postgres_ddl(sqlite_ddl: str) -> str:
    ddl = re.sub(r"\bAUTOINCREMENT\b", "", sqlite_ddl, flags=re.IGNORECASE)
    ddl = re.sub(r"\bINTEGER\b", "BIGINT", ddl, flags=re.IGNORECASE)
    ddl = re.sub(r"\bREAL\b", "DOUBLE PRECISION", ddl, flags=re.IGNORECASE)
    ddl = re.sub(r"\bBLOB\b", "BYTEA", ddl, flags=re.IGNORECASE)
    ddl = re.sub(r"\s+", " ", ddl).strip()
    return ddl


def migrate(sqlite_path: Path, database_url: str) -> dict:
    source = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    source.execute("PRAGMA foreign_keys=ON")
    names = table_names(source)
    order = dependency_order(source, names)
    indexes = source.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"
    ).fetchall()
    counts = {name: source.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}

    with psycopg.connect(database_url) as target:
        with target.cursor() as cur:
            cur.execute("SELECT current_database()")
            database_name = cur.fetchone()[0]
            cur.execute("""SELECT count(*) FROM information_schema.tables
                WHERE table_schema=current_schema() AND table_type='BASE TABLE'""")
            existing = cur.fetchone()[0]
            if existing:
                raise RuntimeError(
                    f"Target database {database_name!r} is not empty ({existing} tables). "
                    "Choose a fresh database; this migration never overwrites data."
                )
            for name in order:
                row = source.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
                ).fetchone()
                if not row or not row[0]:
                    continue
                ddl = postgres_ddl(row[0])
                cur.execute(ddl)
            for name in order:
                rows = source.execute(f'SELECT * FROM "{name}"').fetchall()
                if not rows:
                    continue
                columns = [item[1] for item in source.execute(f'PRAGMA table_info("{name}")')]
                statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    quote_identifier(name),
                    sql.SQL(", ").join(map(quote_identifier, columns)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                )
                cur.executemany(statement, [tuple(row[column] for column in columns) for row in rows])
            for (index_ddl,) in indexes:
                cur.execute(postgres_ddl(index_ddl))
            for name, expected in counts.items():
                cur.execute(sql.SQL("SELECT count(*) FROM {}").format(quote_identifier(name)))
                actual = cur.fetchone()[0]
                if actual != expected:
                    raise RuntimeError(f"Row-count verification failed for {name}: {actual} != {expected}")
    source.close()
    return {"database": database_name, "tables": len(names), "rows": sum(counts.values()), "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=None, help="SQLite file path (defaults to APOLO_DB_PATH)")
    parser.add_argument("--database-url", default=None, help="PostgreSQL URL (defaults to APOLO_DATABASE_URL)")
    args = parser.parse_args()
    sqlite_path = Path(args.sqlite or __import__("os").getenv("APOLO_DB_PATH", "/data/apolo-langdock.sqlite3"))
    database_url = args.database_url or __import__("os").getenv("APOLO_DATABASE_URL")
    if not sqlite_path.is_file():
        parser.error(f"SQLite database does not exist: {sqlite_path}")
    if not database_url or not database_url.startswith(("postgresql://", "postgres://")):
        parser.error("Set APOLO_DATABASE_URL to a PostgreSQL connection URL.")
    try:
        result = migrate(sqlite_path, database_url)
    except Exception as exc:
        print(f"Migration aborted: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Migration verified: {result['tables']} tables, {result['rows']} rows in {result['database']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
