import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openwebui_bootstrap import bootstrap_openwebui as bootstrap


FUNCTION_SCHEMA = """
CREATE TABLE "function" (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT,
    type TEXT,
    content TEXT,
    meta TEXT,
    valves TEXT,
    is_active INTEGER,
    is_global INTEGER,
    updated_at INTEGER,
    created_at INTEGER
)
"""

MODEL_SCHEMA = """
CREATE TABLE model (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    base_model_id TEXT,
    name TEXT,
    params TEXT,
    meta TEXT,
    updated_at INTEGER,
    created_at INTEGER,
    is_active INTEGER
)
"""

ACCESS_GRANT_SCHEMA = """
CREATE TABLE access_grant (
    id TEXT,
    resource_type TEXT,
    resource_id TEXT,
    principal_type TEXT,
    principal_id TEXT,
    permission TEXT,
    created_at INTEGER
)
"""

TOOL_SCHEMA = """
CREATE TABLE tool (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT,
    content TEXT,
    specs TEXT,
    meta TEXT,
    valves TEXT,
    updated_at INTEGER,
    created_at INTEGER
)
"""


def create_config_table(conn):
    conn.execute(
        """
        CREATE TABLE config (
            id INTEGER PRIMARY KEY,
            data TEXT,
            updated_at TEXT
        )
        """
    )


def create_visibility_tables(conn):
    conn.execute(MODEL_SCHEMA)
    conn.execute(ACCESS_GRANT_SCHEMA)


def test_validate_pipe_schema_accepts_live_verified_shape():
    conn = sqlite3.connect(":memory:")
    conn.execute(FUNCTION_SCHEMA)
    create_config_table(conn)
    create_visibility_tables(conn)

    bootstrap.validate_pipe_schema(conn)


def test_validate_pipe_schema_rejects_unknown_function_shape():
    conn = sqlite3.connect(":memory:")
    conn.execute('CREATE TABLE "function" (id TEXT PRIMARY KEY)')
    create_config_table(conn)
    create_visibility_tables(conn)

    with pytest.raises(bootstrap.OpenWebUIBootstrapError) as exc:
        bootstrap.validate_pipe_schema(conn)

    assert exc.value.code == "openwebui_pipe_bootstrap_schema_unknown"


def test_selectable_pipe_model_id_uses_verified_non_manifold_function_id():
    assert bootstrap.selectable_pipe_model_id("company_intelligent_pipe", object()) == "company_intelligent_pipe"


def test_selectable_pipe_model_id_stops_for_unverified_manifold_pipe():
    with pytest.raises(bootstrap.OpenWebUIBootstrapError) as exc:
        bootstrap.selectable_pipe_model_id("company_intelligent_pipe", SimpleNamespace(pipes=lambda: []))

    assert exc.value.code == "openwebui_pipe_model_id_unknown"


def test_upsert_pipe_function_is_idempotent_and_does_not_guess_grants(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute(FUNCTION_SCHEMA)
    create_config_table(conn)
    create_visibility_tables(conn)
    monkeypatch.setenv("OPENWEBUI_SHARED_SECRET", "shared")

    bootstrap.upsert_pipe_function(
        conn,
        admin_user_id="admin",
        function_id="company_intelligent_pipe",
        display_name="Company Intelligent",
        content="first",
        frontmatter={"description": "Pipe description"},
    )
    conn.execute('UPDATE "function" SET valves = ? WHERE id = ?', (json.dumps({"request_timeout_seconds": 60.0}), "company_intelligent_pipe"))
    bootstrap.upsert_pipe_function(
        conn,
        admin_user_id="admin",
        function_id="company_intelligent_pipe",
        display_name="Company Intelligent",
        content="second",
        frontmatter={"description": "Pipe description"},
    )

    rows = conn.execute(
        'SELECT id, user_id, name, type, content, meta, valves, is_active, is_global FROM "function"'
    ).fetchall()
    grants = conn.execute("SELECT * FROM access_grant").fetchall()

    assert len(rows) == 1
    row = rows[0]
    assert row[:5] == (
        "company_intelligent_pipe",
        "admin",
        "Company Intelligent",
        "pipe",
        "second",
    )
    assert json.loads(row[5])["description"] == "Pipe description"
    assert json.loads(row[6])["openwebui_shared_secret"] == "shared"
    assert json.loads(row[6])["request_timeout_seconds"] == 600.0
    assert row[7:] == (1, 0)
    assert grants == []


def test_upsert_tool_overwrites_existing_timeout_valve(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute(TOOL_SCHEMA)
    conn.execute(ACCESS_GRANT_SCHEMA)
    monkeypatch.setenv("OPENWEBUI_SHARED_SECRET", "shared")

    bootstrap.upsert_tool(
        conn,
        admin_user_id="admin",
        normal_user_id="normal",
        content="first",
        specs=[],
        frontmatter={},
    )
    conn.execute("UPDATE tool SET valves = ? WHERE id = ?", (json.dumps({"request_timeout_seconds": 60.0}), "company_intelligent"))
    bootstrap.upsert_tool(
        conn,
        admin_user_id="admin",
        normal_user_id="normal",
        content="second",
        specs=[],
        frontmatter={},
    )

    row = conn.execute("SELECT content, valves FROM tool WHERE id = ?", ("company_intelligent",)).fetchone()
    assert row[0] == "second"
    assert json.loads(row[1])["request_timeout_seconds"] == 600.0


def test_upsert_pipe_model_preset_grants_admin_and_user_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute(MODEL_SCHEMA)
    conn.execute(ACCESS_GRANT_SCHEMA)

    for name in ("Company Intelligent", "Company Intelligent"):
        bootstrap.upsert_pipe_model_preset(
            conn,
            admin_user_id="admin",
            normal_user_id="normal",
            model_id="company_intelligent_pipe",
            display_name=name,
        )

    rows = conn.execute(
        "SELECT id, user_id, base_model_id, name, is_active FROM model WHERE id = ?",
        ("company_intelligent_pipe",),
    ).fetchall()
    grants = conn.execute(
        "SELECT resource_type, resource_id, principal_type, principal_id, permission FROM access_grant WHERE resource_id = ? ORDER BY principal_id",
        ("company_intelligent_pipe",),
    ).fetchall()

    assert rows == [("company_intelligent_pipe", "admin", "company_intelligent_pipe", "Company Intelligent", 1)]
    assert grants == [
        ("model", "company_intelligent_pipe", "user", "*", "read"),
        ("model", "company_intelligent_pipe", "user", "admin", "read"),
        ("model", "company_intelligent_pipe", "user", "normal", "read"),
    ]


def test_hide_provider_model_marks_deepseek_inactive_and_revokes_grants():
    conn = sqlite3.connect(":memory:")
    conn.execute(MODEL_SCHEMA)
    conn.execute(ACCESS_GRANT_SCHEMA)
    conn.execute(
        "INSERT INTO model (id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 1)",
        ("deepseek-v4-pro", "admin", None, "DeepSeek V4 Pro", "{}", "{}",),
    )
    conn.execute(
        "INSERT INTO access_grant (id, resource_type, resource_id, principal_type, principal_id, permission, created_at) VALUES ('g1', 'model', 'deepseek-v4-pro', 'user', '*', 'read', 1)"
    )

    bootstrap.hide_provider_model_from_chooser(conn, model_id="deepseek-v4-pro", admin_user_id="admin")

    row = conn.execute("SELECT base_model_id, is_active FROM model WHERE id = ?", ("deepseek-v4-pro",)).fetchone()
    grants = conn.execute("SELECT * FROM access_grant WHERE resource_type = 'model' AND resource_id = 'deepseek-v4-pro'").fetchall()

    assert row == (None, 0)
    assert grants == []


def test_set_default_model_uses_verified_model_id_when_config_row_exists():
    conn = sqlite3.connect(":memory:")
    create_config_table(conn)
    conn.execute(
        "INSERT INTO config (id, data, updated_at) VALUES (1, ?, CURRENT_TIMESTAMP)",
        (
            json.dumps(
                {
                    "task": {
                        "title": {"enable": True},
                        "tags": {"enable": True},
                        "follow_up": {"enable": True},
                        "autocomplete": {"enable": True},
                    }
                }
            ),
        ),
    )

    bootstrap.set_default_model(conn, "company_intelligent_pipe")

    data = json.loads(conn.execute("SELECT data FROM config WHERE id = 1").fetchone()[0])
    assert data["ui"]["default_models"] == "company_intelligent_pipe"
    assert data["ui"]["default_pinned_models"] == "company_intelligent_pipe"
    assert data["ui"]["model_order_list"] == ["company_intelligent_pipe"]
    assert data["ui"]["locale"] == "en-US"
    assert data["ui"]["language"] == "en-US"
    assert data["openai"]["enable"] is False
    assert data["ollama"]["enable"] is False
    assert data["evaluation"]["arena"]["enable"] is False
    assert data["task"] == {
        "title": {"enable": False},
        "tags": {"enable": False},
        "follow_up": {"enable": False},
        "autocomplete": {"enable": False},
    }


def test_set_default_model_creates_config_row_when_missing():
    conn = sqlite3.connect(":memory:")
    create_config_table(conn)

    bootstrap.set_default_model(conn, "company_intelligent_pipe")

    data = json.loads(conn.execute("SELECT data FROM config").fetchone()[0])
    assert data["ui"]["default_models"] == "company_intelligent_pipe"
    assert data["ui"]["locale"] == "en-US"
    assert data["task"]["title"]["enable"] is False
    assert data["task"]["tags"]["enable"] is False
    assert data["task"]["follow_up"]["enable"] is False
    assert data["task"]["autocomplete"]["enable"] is False


def test_demo_user_password_default_is_user():
    assert bootstrap.DEMO_USER_PASSWORD == "user"
