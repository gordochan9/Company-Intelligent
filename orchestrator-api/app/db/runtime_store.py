from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.schemas.dataset_rebuild import ScanRecord


POSTGRES_COLUMN_TYPES = {
    "boolean": "BOOLEAN",
    "integer": "BIGINT",
    "decimal": "NUMERIC",
    "text": "TEXT",
}


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not configured.")
    return value


class PostgresRuntimeStore:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or database_url()

    def replace_dataset(self, records: list[ScanRecord], documents: dict[str, list], structured: dict[str, list]) -> dict[str, int]:
        import psycopg

        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            with conn.transaction():
                self._clear_dataset(conn)
                counts = {"sources_registered": 0, "catalog_entries_written": 0}
                for record in records:
                    source_id = self._insert_source(conn, record)
                    entry_id = self._insert_entry(conn, record, source_id)
                    counts["sources_registered"] += 1
                    counts["catalog_entries_written"] += 1
                    for chunk in documents.get(record.relative_path, []):
                        self._insert_chunk(conn, record, entry_id, chunk)
                    for profile in structured.get(record.relative_path, []):
                        self._insert_structured_resource(conn, record, entry_id, profile)
                return counts

    def refresh_document(self, relative_path: str, permission_scope_key: str, chunks: list[Any]) -> None:
        import psycopg

        record = _watchdog_record(relative_path, permission_scope_key, "rag_document")
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            with conn.transaction():
                self.delete_document(relative_path, conn=conn)
                source_id = self._insert_source(conn, record)
                entry_id = self._insert_entry(conn, record, source_id)
                for chunk in chunks:
                    self._insert_chunk(conn, record, entry_id, chunk)

    def delete_document(self, relative_path: str, *, conn=None) -> None:
        own_conn = None
        if conn is None:
            import psycopg

            own_conn = psycopg.connect(self.url)
            conn = own_conn
        try:
            with conn.transaction():
                conn.execute("DELETE FROM source_catalog WHERE source_uri = %s", ("active-dataset://" + relative_path,))
        finally:
            if own_conn is not None:
                own_conn.close()

    def refresh_structured(self, relative_path: str, permission_scope_key: str, profiles: list[Any]) -> dict[str, Any]:
        import psycopg

        record = _watchdog_record(relative_path, permission_scope_key, "structured_table")
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            with conn.transaction():
                self.delete_structured(relative_path, conn=conn)
                source_id = self._insert_source(conn, record)
                entry_id = self._insert_entry(conn, record, source_id)
                for profile in profiles:
                    self._insert_structured_resource(conn, record, entry_id, profile)
        return {"runtime_relation_validated": True, "columns_changed": True}

    def delete_structured(self, relative_path: str, *, conn=None) -> None:
        own_conn = None
        if conn is None:
            import psycopg

            own_conn = psycopg.connect(self.url, row_factory=dict_row)
            conn = own_conn
        try:
            with conn.transaction():
                rows = conn.execute(
                    """
                    SELECT runtime_relation_name
                    FROM structured_resources
                    WHERE metadata->>'safe_location_path' = %s
                    """,
                    (relative_path,),
                ).fetchall()
                for row in rows:
                    conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(row["runtime_relation_name"])))
                conn.execute(
                    """
                    DELETE FROM structured_resources
                    WHERE metadata->>'safe_location_path' = %s
                    """,
                    (relative_path,),
                )
                conn.execute("DELETE FROM source_catalog WHERE source_uri = %s", ("active-dataset://" + relative_path,))
        finally:
            if own_conn is not None:
                own_conn.close()

    def rename_path(self, source_relative_path: str, relative_path: str) -> None:
        import psycopg

        with psycopg.connect(self.url) as conn:
            with conn.transaction():
                conn.execute(
                    "UPDATE source_catalog SET source_uri = %s, display_name = %s WHERE source_uri = %s",
                    ("active-dataset://" + relative_path, Path(relative_path).name, "active-dataset://" + source_relative_path),
                )
                conn.execute(
                    "UPDATE catalog_entries SET safe_path = %s, title = %s WHERE safe_path = %s",
                    (relative_path, Path(relative_path).name, source_relative_path),
                )

    def list_rag_documents(self) -> list[dict[str, Any]]:
        import psycopg

        query = """
            SELECT ce.entry_id::text AS document_ref, ce.permission_scope_key, ce.title, ce.safe_path,
                   dc.chunk_index, dc.chunk_text, dc.citation
            FROM catalog_entries ce
            JOIN document_chunks dc ON dc.catalog_entry_id = ce.entry_id
            WHERE ce.is_active AND dc.is_active
            ORDER BY ce.safe_path, dc.chunk_index
        """
        documents: dict[str, dict[str, Any]] = {}
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            for row in conn.execute(query):
                document = documents.setdefault(
                    row["document_ref"],
                    {
                        "document_ref": row["document_ref"],
                        "permission_scope_key": row["permission_scope_key"],
                        "rag_namespace": row["permission_scope_key"],
                        "title": row["title"],
                        "safe_path": row["safe_path"],
                        "summary": row["title"],
                        "keywords": [],
                        "headers": [],
                        "safe_row_samples": [],
                        "chunks": [],
                    },
                )
                document["chunks"].append({"text": row["chunk_text"], "citation": row["citation"]})
        return list(documents.values())

    def list_structured_resources(self) -> list[dict[str, Any]]:
        import psycopg

        resources: dict[str, dict[str, Any]] = {}
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT sr.resource_id::text, sr.resource_key, sr.runtime_relation_name, sr.display_name,
                       sr.permission_scope_key, sr.metadata, c.column_id::text, c.column_name,
                       c.data_type, c.safe_description
                FROM structured_resources sr
                JOIN structured_resource_columns c ON c.resource_id = sr.resource_id
                WHERE sr.is_active AND c.is_active
                ORDER BY sr.resource_key, c.ordinal_position
                """
            ).fetchall()
            for row in rows:
                resource = resources.setdefault(
                    row["resource_key"],
                    {
                        "resource_id": row["resource_id"],
                        "resource_key": row["resource_key"],
                        "runtime_relation_name": row["runtime_relation_name"],
                        "display_name": row["display_name"],
                        "permission_scope_key": row["permission_scope_key"],
                        "scope_keys": [row["permission_scope_key"]],
                        "columns": [],
                        "safe_row_samples": [],
                        "column_profiles": {},
                    },
                )
                resource["columns"].append(
                    {
                        "column_id": row["column_id"],
                        "column_key": row["column_id"],
                        "column_name": row["column_name"],
                        "data_type": row["data_type"],
                        "safe_description": row["safe_description"],
                    }
                )
            for resource in resources.values():
                relation = sql.Identifier(resource["runtime_relation_name"])
                samples = conn.execute(sql.SQL("SELECT * FROM {} LIMIT 5").format(relation)).fetchall()
                resource["safe_row_samples"] = [
                    {key: value for key, value in dict(row).items() if key != "permission_scope_key"} for row in samples
                ]
        return list(resources.values())

    def list_active_structured_resources(self, active_dataset_id: str) -> list[dict[str, Any]]:
        return self.list_structured_resources()

    def list_approved_joins(self) -> list[dict[str, Any]]:
        import psycopg

        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT lr.resource_key AS left_resource_key, lc.column_name AS left_column_name,
                           rr.resource_key AS right_resource_key, rc.column_name AS right_column_name,
                           aj.join_type, aj.metadata->>'reason' AS reason
                    FROM approved_join_relationships aj
                    JOIN structured_resources lr ON lr.resource_id = aj.left_resource_id
                    JOIN structured_resource_columns lc ON lc.column_id = aj.left_column_id
                    JOIN structured_resources rr ON rr.resource_id = aj.right_resource_id
                    JOIN structured_resource_columns rc ON rc.column_id = aj.right_column_id
                    WHERE aj.is_active AND aj.validation_status = 'approved'
                    """
                )
            ]

    def replace_approved_joins(self, active_dataset_id: str, joins: list[dict[str, Any]]) -> int:
        import psycopg

        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("DELETE FROM approved_join_relationships")
                for join in joins:
                    conn.execute(
                        """
                        INSERT INTO approved_join_relationships (
                            left_resource_id, left_column_id, right_resource_id, right_column_id,
                            join_type, confidence, validation_source, metadata
                        )
                        VALUES (%s, %s, %s, %s, %s, 'high', 'llm_join_discovery', %s)
                        """,
                        (
                            join["left_resource_id"],
                            join["left_column_id"],
                            join["right_resource_id"],
                            join["right_column_id"],
                            join.get("join_type", "inner"),
                            Jsonb(join.get("metadata", {})),
                        ),
                    )
        return len(joins)

    def execute_read_only_sql(
        self,
        query: str,
        permission_scope_keys: list[str],
        permission_resource_keys: list[str],
    ) -> dict[str, Any]:
        import psycopg

        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute("SET LOCAL ROLE restricted_runtime_reader")
                conn.execute("SELECT set_config('app.permission_scope_keys', %s, true)", (",".join(permission_scope_keys),))
                conn.execute("SELECT set_config('app.permission_resource_keys', %s, true)", (",".join(permission_resource_keys),))
                cur = conn.execute(query)
                rows = cur.fetchall()
                columns = [item.name for item in cur.description or []]
        return {"columns": columns, "rows": [dict(row) for row in rows], "restricted_reader": True, "rls_enforced": True}

    def _clear_dataset(self, conn) -> None:
        rows = conn.execute("SELECT runtime_relation_name FROM structured_resources").fetchall()
        conn.execute("DELETE FROM approved_join_relationships")
        for row in rows:
            conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(row["runtime_relation_name"])))
        conn.execute("DELETE FROM structured_resources")
        conn.execute("DELETE FROM source_catalog")

    def _insert_source(self, conn, record: ScanRecord) -> str:
        row = conn.execute(
            """
            INSERT INTO source_catalog (source_type, source_uri, display_name, permission_scope_key, metadata)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING source_id::text
            """,
            (
                record.file_kind,
                record.source_uri,
                Path(record.relative_path).name,
                record.permission_scope_key,
                Jsonb({"active_dataset_id": "active", "content_hash": record.content_hash, "size_bytes": record.size_bytes}),
            ),
        ).fetchone()
        return str(row["source_id"])

    def _insert_entry(self, conn, record: ScanRecord, source_id: str) -> str:
        row = conn.execute(
            """
            INSERT INTO catalog_entries (
                source_id, entry_type, title, safe_path, permission_scope_key,
                active_dataset_id, source_catalog_version, metadata
            )
            VALUES (%s, %s, %s, %s, %s, 'active', 'active', %s)
            RETURNING entry_id::text
            """,
            (source_id, record.file_kind, Path(record.relative_path).stem, record.relative_path, record.permission_scope_key, Jsonb({})),
        ).fetchone()
        return str(row["entry_id"])

    def _insert_chunk(self, conn, record: ScanRecord, entry_id: str, chunk: Any) -> None:
        conn.execute(
            """
            INSERT INTO document_chunks (catalog_entry_id, chunk_index, chunk_text, citation, permission_scope_key, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                entry_id,
                int(getattr(chunk, "chunk_index", 0)),
                str(getattr(chunk, "chunk_text", "")),
                Jsonb(dict(getattr(chunk, "citation", {}) or {})),
                record.permission_scope_key,
                Jsonb(dict(getattr(chunk, "metadata", {}) or {})),
            ),
        )

    def _insert_structured_resource(self, conn, record: ScanRecord, entry_id: str, profile: Any) -> None:
        metadata = dict(profile.metadata or {})
        row = conn.execute(
            """
            INSERT INTO structured_resources (
                catalog_entry_id, resource_key, runtime_relation_name, display_name, permission_scope_key, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING resource_id::text
            """,
            (
                entry_id,
                profile.resource_key,
                profile.runtime_relation_name,
                profile.display_name,
                record.permission_scope_key,
                Jsonb(metadata),
            ),
        ).fetchone()
        resource_id = row["resource_id"]
        conn.execute(
            """
            INSERT INTO structured_resource_scope_map (resource_id, permission_scope_key)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (resource_id, record.permission_scope_key),
        )
        self._create_runtime_table(
            conn,
            profile.runtime_relation_name,
            profile.resource_key,
            profile.columns,
            record.permission_scope_key,
            profile.rows,
        )
        for index, column in enumerate(profile.columns, start=1):
            conn.execute(
                """
                INSERT INTO structured_resource_columns (
                    resource_id, column_name, data_type, safe_description, ordinal_position, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    resource_id,
                    column["column_name"],
                    column.get("data_type", "text"),
                    column.get("safe_description", ""),
                    index,
                    Jsonb(column.get("metadata", {})),
                ),
            )

    def _create_runtime_table(
        self,
        conn,
        table_name: str,
        resource_key: str,
        columns: list[dict[str, Any]],
        scope: str,
        rows: list[dict[str, Any]],
    ) -> None:
        table = sql.Identifier(table_name)
        try:
            column_defs = [
                sql.SQL("{} {}").format(
                    sql.Identifier(column["column_name"]),
                    sql.SQL(POSTGRES_COLUMN_TYPES[column["data_type"]]),
                )
                for column in columns
            ]
        except KeyError as exc:
            raise ValueError("unsupported_structured_column_type") from exc
        conn.execute(sql.SQL("CREATE TABLE {} (permission_scope_key text NOT NULL, {})").format(table, sql.SQL(", ").join(column_defs)))
        conn.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(table))
        conn.execute(sql.SQL("GRANT SELECT ON {} TO restricted_runtime_reader").format(table))
        policy_name = sql.Identifier(f"{table_name}_scope_read")
        conn.execute(
            sql.SQL(
                "CREATE POLICY {} ON {} FOR SELECT TO restricted_runtime_reader "
                "USING (app_security.can_read_scope(permission_scope_key) OR app_security.can_read_resource_key({}))"
            ).format(
                policy_name,
                table,
                sql.Literal(resource_key),
            )
        )
        column_names = ["permission_scope_key", *[column["column_name"] for column in columns]]
        insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            table,
            sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
            sql.SQL(", ").join(sql.Placeholder() for _ in column_names),
        )
        for row in rows:
            conn.execute(insert_sql, [scope, *[row.get(column["column_name"]) for column in columns]])


def _watchdog_record(relative_path: str, permission_scope_key: str, file_kind: str) -> ScanRecord:
    return ScanRecord(
        relative_path=relative_path,
        source_uri="active-dataset://" + relative_path,
        extension=Path(relative_path).suffix.lower(),
        permission_scope_key=permission_scope_key,
        file_kind=file_kind,
        content_hash="watchdog-refresh",
        size_bytes=0,
    )
