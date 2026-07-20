from pathlib import Path


def test_audit_trace_does_not_create_public_routes_or_workflow_logic() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    audit_files = [
        app_root / "schemas" / "audit_trace.py",
        app_root / "services" / "audit_trace.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in audit_files)

    assert "/openwebui/ask" not in combined
    assert "generate_candidate_sql" not in combined
    assert "retrieve_relevant_chunks" not in combined
    assert "FastAPI(" not in combined
