import os
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.migrate import apply_migrations
from app.db.runtime_store import PostgresRuntimeStore


pytest.importorskip("psycopg")


def _database_url() -> str:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("DATABASE_URL is not set")
    return database_url


def test_restricted_runtime_reader_is_non_login_non_bypassrls() -> None:
    import psycopg

    apply_migrations(_database_url())
    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolbypassrls
                FROM pg_roles
                WHERE rolname = 'restricted_runtime_reader'
                """
            )
            assert cur.fetchone() == (False, False, False, False, False, False)


def test_rls_filters_structured_resources_by_backend_scope_context() -> None:
    import psycopg

    database_url = _database_url()
    apply_migrations(database_url)
    marker = f"rls-{uuid4()}"

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO structured_resources (
                    resource_key, runtime_relation_name, display_name, permission_scope_key, metadata
                )
                VALUES
                    (%s, %s, 'Finance table', 'finance', '{"test": true}'::jsonb),
                    (%s, %s, 'HR table', 'hr', '{"test": true}'::jsonb)
                RETURNING resource_id
                """,
                (f"{marker}-finance", f"{marker}_finance", f"{marker}-hr", f"{marker}_hr"),
            )
            finance_id, hr_id = [row[0] for row in cur.fetchall()]
        conn.commit()

        try:
            with conn.cursor() as cur:
                cur.execute("BEGIN READ ONLY")
                cur.execute("SET LOCAL ROLE restricted_runtime_reader")
                cur.execute("SELECT set_config('app.permission_scope_keys', %s, true)", ("finance",))
                cur.execute(
                    """
                    SELECT resource_id
                    FROM structured_resources
                    WHERE resource_id = ANY(%s)
                    ORDER BY display_name
                    """,
                    ([finance_id, hr_id],),
                )
                visible = [row[0] for row in cur.fetchall()]
                cur.execute("ROLLBACK")

            assert visible == [finance_id]
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM structured_resources WHERE resource_key LIKE %s", (f"{marker}%",))
            conn.commit()


def test_restricted_runtime_reader_cannot_write_or_read_internal_tables() -> None:
    import psycopg
    from psycopg import errors

    database_url = _database_url()
    apply_migrations(database_url)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL ROLE restricted_runtime_reader")
            with pytest.raises(errors.InsufficientPrivilege):
                cur.execute("SELECT count(*) FROM app_users")
            cur.execute("ROLLBACK")

        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL ROLE restricted_runtime_reader")
            with pytest.raises(errors.InsufficientPrivilege):
                cur.execute(
                    """
                    INSERT INTO structured_resources (
                        resource_key, runtime_relation_name, display_name, permission_scope_key
                    )
                    VALUES ('blocked', 'blocked', 'blocked', 'finance')
                    """
                )
            cur.execute("ROLLBACK")


def test_exact_resource_context_allows_only_one_same_scope_runtime_table() -> None:
    import psycopg
    from psycopg import errors, sql

    database_url = _database_url()
    apply_migrations(database_url)
    marker = uuid4().hex[:12]
    table_a = f"rls_exact_a_{marker}"
    table_b = f"rls_exact_b_{marker}"
    resource_a = f"structured:finance:{marker}:a"
    resource_b = f"structured:finance:{marker}:b"
    store = PostgresRuntimeStore(database_url)
    columns = [
        {"column_name": "whole", "data_type": "integer"},
        {"column_name": "amount", "data_type": "decimal"},
        {"column_name": "flag", "data_type": "boolean"},
        {"column_name": "label", "data_type": "text"},
    ]

    with psycopg.connect(database_url) as conn:
        try:
            with conn.transaction():
                store._create_runtime_table(
                    conn, table_a, resource_a, columns, "finance",
                    [{"whole": 1, "amount": Decimal("1.25"), "flag": True, "label": "a"}],
                )
                store._create_runtime_table(
                    conn, table_b, resource_b, columns, "finance",
                    [{"whole": 2, "amount": Decimal("2.50"), "flag": False, "label": "b"}],
                )

            exact = store.execute_read_only_sql(
                f'SELECT whole, amount, flag, label FROM "{table_a}"', [], [resource_a]
            )
            sibling = store.execute_read_only_sql(f'SELECT whole FROM "{table_b}"', [], [resource_a])
            missing = store.execute_read_only_sql(f'SELECT whole FROM "{table_a}"', [], [])
            scoped_a = store.execute_read_only_sql(f'SELECT whole FROM "{table_a}"', ["finance"], [])
            scoped_b = store.execute_read_only_sql(f'SELECT whole FROM "{table_b}"', ["finance"], [])

            assert exact["rows"] == [{"whole": 1, "amount": Decimal("1.25"), "flag": True, "label": "a"}]
            assert sibling["rows"] == []
            assert missing["rows"] == []
            assert scoped_a["rows"] == [{"whole": 1}]
            assert scoped_b["rows"] == [{"whole": 2}]

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s AND column_name <> 'permission_scope_key'
                    ORDER BY ordinal_position
                    """,
                    (table_a,),
                )
                assert cur.fetchall() == [
                    ("whole", "bigint"),
                    ("amount", "numeric"),
                    ("flag", "boolean"),
                    ("label", "text"),
                ]

            with pytest.raises((errors.ReadOnlySqlTransaction, errors.InsufficientPrivilege)):
                store.execute_read_only_sql(f'UPDATE "{table_a}" SET whole = 9', ["finance"], [resource_a])
        finally:
            conn.rollback()
            with conn.transaction():
                conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table_a)))
                conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table_b)))


def test_exact_resource_context_filters_structured_metadata_columns_and_joins() -> None:
    import psycopg

    database_url = _database_url()
    apply_migrations(database_url)
    marker = uuid4().hex
    resource_a = f"{marker}:a"
    resource_b = f"{marker}:b"

    with psycopg.connect(database_url) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO structured_resources (
                        resource_key, runtime_relation_name, display_name, permission_scope_key, metadata
                    ) VALUES
                        (%s, %s, 'A', 'finance', '{"test": true}'::jsonb),
                        (%s, %s, 'B', 'finance', '{"test": true}'::jsonb)
                    RETURNING resource_id
                    """,
                    (resource_a, f"{marker}_a", resource_b, f"{marker}_b"),
                )
                id_a, id_b = [row[0] for row in cur.fetchall()]
                cur.execute(
                    """
                    INSERT INTO structured_resource_columns (
                        resource_id, column_name, data_type, ordinal_position
                    ) VALUES (%s, 'id', 'integer', 1), (%s, 'id', 'integer', 1)
                    RETURNING column_id
                    """,
                    (id_a, id_b),
                )
                column_a, column_b = [row[0] for row in cur.fetchall()]
                cur.execute(
                    """
                    INSERT INTO approved_join_relationships (
                        left_resource_id, left_column_id, right_resource_id, right_column_id,
                        join_type, confidence, validation_source
                    ) VALUES (%s, %s, %s, %s, 'inner', 'high', 'test')
                    """,
                    (id_a, column_a, id_b, column_b),
                )
            conn.commit()

            with conn.cursor() as cur:
                cur.execute("BEGIN READ ONLY")
                cur.execute("SET LOCAL ROLE restricted_runtime_reader")
                cur.execute("SELECT set_config('app.permission_scope_keys', '', true)")
                cur.execute("SELECT set_config('app.permission_resource_keys', %s, true)", (resource_a,))
                cur.execute("SELECT resource_id FROM structured_resources WHERE resource_id = ANY(%s)", ([id_a, id_b],))
                assert [row[0] for row in cur.fetchall()] == [id_a]
                cur.execute("SELECT resource_id FROM structured_resource_columns WHERE resource_id = ANY(%s)", ([id_a, id_b],))
                assert [row[0] for row in cur.fetchall()] == [id_a]
                cur.execute("SELECT count(*) FROM approved_join_relationships WHERE left_resource_id = %s", (id_a,))
                assert cur.fetchone()[0] == 0
                cur.execute("SELECT set_config('app.permission_resource_keys', %s, true)", (f"{resource_a},{resource_b}",))
                cur.execute("SELECT count(*) FROM approved_join_relationships WHERE left_resource_id = %s", (id_a,))
                assert cur.fetchone()[0] == 1
                cur.execute("ROLLBACK")
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM structured_resources WHERE resource_key IN (%s, %s)", (resource_a, resource_b))
            conn.commit()
