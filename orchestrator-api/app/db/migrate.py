from __future__ import annotations

import hashlib
import os
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def _psycopg():
    import psycopg

    return psycopg


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migrations(database_url: str | None = None) -> list[str]:
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to apply migrations")

    psycopg = _psycopg()
    applied: list[str] = []
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    name text NOT NULL,
                    checksum text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            conn.commit()

        for path in migration_files():
            version, name = path.stem.split("_", 1)
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            with conn.cursor() as cur:
                cur.execute("SELECT checksum FROM schema_migrations WHERE version = %s", (version,))
                row = cur.fetchone()
                if row:
                    if row[0] != checksum:
                        raise RuntimeError(f"migration checksum mismatch: {path.name}")
                    continue
                with conn.transaction():
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                        (version, name, checksum),
                    )
                applied.append(path.name)
    return applied


def main() -> None:
    for name in apply_migrations():
        print(name)


if __name__ == "__main__":
    main()
