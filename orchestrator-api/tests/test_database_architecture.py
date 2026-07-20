from pathlib import Path


DB_ROOT = Path(__file__).resolve().parents[1] / "app" / "db"


def test_db_boundary_does_not_import_workflow_layers() -> None:
    forbidden = {
        "openwebui",
        "company_intelligent",
        "sql_rag",
        "final_answer_composer",
        "watch_active_dataset",
        "rebuild_dataset",
    }
    text = "\n".join(path.read_text(encoding="utf-8") for path in DB_ROOT.rglob("*.py"))

    assert forbidden.isdisjoint(text.split())


def test_migrations_define_required_database_substrate() -> None:
    sql = "\n".join(path.read_text(encoding="utf-8") for path in (DB_ROOT / "migrations").glob("*.sql"))

    for required in [
        "permission_scopes",
        "source_catalog",
        "catalog_entries",
        "document_chunks",
        "rag_chunk_embeddings",
        "structured_resources",
        "structured_resource_columns",
        "approved_join_relationships",
        "audit_events",
        "restricted_runtime_reader",
        "ROW LEVEL SECURITY",
    ]:
        assert required in sql
