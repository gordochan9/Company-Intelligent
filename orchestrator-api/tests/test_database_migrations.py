import os

import pytest

from app.db.migrate import apply_migrations, migration_files


pytest.importorskip("psycopg")


def _database_url() -> str:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("DATABASE_URL is not set")
    return database_url


def test_migration_files_are_ordered() -> None:
    names = [path.name for path in migration_files()]

    assert names == sorted(names)
    assert names[-1] == "004_exact_resource_rls.sql"


def test_migrations_apply_and_record_versions() -> None:
    import psycopg

    database_url = _database_url()
    applied = apply_migrations(database_url)
    assert isinstance(applied, list)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations ORDER BY version")
            versions = [row[0] for row in cur.fetchall()]
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            tables = {row[0] for row in cur.fetchall()}

    assert versions == [path.stem.split("_", 1)[0] for path in migration_files()]
    assert {
        "permission_scopes",
        "source_catalog",
        "catalog_entries",
        "document_chunks",
        "rag_chunk_embeddings",
        "structured_resources",
        "approved_join_relationships",
        "audit_events",
    }.issubset(tables)
