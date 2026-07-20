from app.services.audit_trace import REDACTED, sanitize_metadata


def test_sanitizer_redacts_secret_keys_and_paths() -> None:
    sanitized = sanitize_metadata(
        {
            "authorization": "Bearer token",
            "database_url": "postgresql://user:pass@localhost/db",
            "path": r"C:\Users\Redacted\Share Drive\Finance\a.csv",
            "nested": {"api_key": "sk-test-value"},
        }
    )

    assert sanitized["authorization"] == REDACTED
    assert sanitized["database_url"] == REDACTED
    assert sanitized["path"] == REDACTED
    assert sanitized["nested"]["api_key"] == REDACTED


def test_sanitizer_hashes_sensitive_ids() -> None:
    sanitized = sanitize_metadata({"source_id": "source-123", "chunk_id": "chunk-456"})

    assert sanitized["source_id"].startswith("sha256:")
    assert sanitized["chunk_id"].startswith("sha256:")
