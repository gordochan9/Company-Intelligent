from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path


OPENWEBUI_BACKEND_PATH = Path("/app/backend")
if OPENWEBUI_BACKEND_PATH.exists():
    sys.path.insert(0, str(OPENWEBUI_BACKEND_PATH))

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/backend/data"))
DB_PATH = Path(os.getenv("OPENWEBUI_BOOTSTRAP_DB", DATA_DIR / "webui.db"))
TOOL_SOURCE_PATH = Path(os.getenv("OPENWEBUI_BOOTSTRAP_TOOL_SOURCE", "/bootstrap/company_intelligent.py"))
PIPE_SOURCE_PATH = Path(os.getenv("OPENWEBUI_BOOTSTRAP_PIPE_SOURCE", "/function_source/company_intelligent_pipe.py"))
TOOL_ID = "company_intelligent"
PIPE_ID = "company_intelligent_pipe"
MODEL_ID = os.getenv("MODEL_NAME", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
MODEL_DISPLAY_NAME = os.getenv("OPENWEBUI_DEMO_MODEL_DISPLAY_NAME", "DeepSeek V4 Pro").strip() or "DeepSeek V4 Pro"


def env_value(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


DEMO_ADMIN_EMAIL = env_value("OPENWEBUI_DEMO_ADMIN_EMAIL", "admin@demo.com")
DEMO_ADMIN_PASSWORD = env_value("OPENWEBUI_DEMO_ADMIN_PASSWORD", "admin")
DEMO_ADMIN_NAME = env_value("OPENWEBUI_DEMO_ADMIN_NAME", "Project 3.0 Demo Admin")
DEMO_USER_EMAIL = env_value("OPENWEBUI_DEMO_USER_EMAIL", "user@demo.com")
DEMO_USER_PASSWORD = "user"
DEMO_USER_NAME = env_value("OPENWEBUI_DEMO_USER_NAME", "Project 3.0 Demo User")
PIPE_DISPLAY_NAME = env_value("OPENWEBUI_DEFAULT_PIPE_DISPLAY_NAME", "Company Intelligent")
DEFAULT_LOCALE = env_value("OPENWEBUI_DEFAULT_LOCALE", "en-US")


class OpenWebUIBootstrapError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def wait_for_db(timeout_seconds: int = 180) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if DB_PATH.exists():
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute('SELECT 1 FROM "user" LIMIT 1')
                return
            except sqlite3.Error:
                pass
        time.sleep(2)
    raise RuntimeError("Open WebUI database did not become ready.")


def password_hash(password: str) -> str:
    import bcrypt

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def ensure_user(conn: sqlite3.Connection, *, user_id: str, email: str, password: str, name: str, role: str) -> str:
    timestamp = int(time.time())
    existing = conn.execute('SELECT id FROM "user" WHERE email = ?', (email.lower(),)).fetchone()
    resolved = existing[0] if existing else user_id
    if existing is None:
        conn.execute(
            """
            INSERT INTO "user" (id, name, email, role, profile_image_url, last_active_at, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (resolved, name, email.lower(), role, "/user.png", timestamp, timestamp, timestamp),
        )
    else:
        conn.execute('UPDATE "user" SET name = ?, role = ?, updated_at = ? WHERE id = ?', (name, role, timestamp, resolved))

    hashed = password_hash(password)
    auth_exists = conn.execute("SELECT id FROM auth WHERE id = ?", (resolved,)).fetchone()
    if auth_exists is None:
        conn.execute("INSERT INTO auth (id, email, password, active) VALUES (?, ?, ?, 1)", (resolved, email.lower(), hashed))
    else:
        conn.execute("UPDATE auth SET email = ?, password = ?, active = 1 WHERE id = ?", (email.lower(), hashed, resolved))
    return resolved


async def build_tool_specs(content: str) -> tuple[list[dict], dict]:
    from open_webui.utils.plugin import load_tool_module_by_id
    from open_webui.utils.tools import get_tool_specs

    tool_module, frontmatter = await load_tool_module_by_id(TOOL_ID, content=content)
    return get_tool_specs(tool_module), frontmatter


async def build_function_metadata(function_id: str, content: str) -> tuple[object, str, dict]:
    from open_webui.utils.plugin import load_function_module_by_id

    function_module, function_type, frontmatter = await load_function_module_by_id(function_id, content=content)
    return function_module, function_type, frontmatter


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()}


def require_columns(conn: sqlite3.Connection, table_name: str, columns: set[str], code: str) -> None:
    existing = table_columns(conn, table_name)
    if not columns.issubset(existing):
        raise OpenWebUIBootstrapError(code)


def validate_pipe_schema(conn: sqlite3.Connection) -> None:
    require_columns(
        conn,
        "function",
        {
            "id",
            "user_id",
            "name",
            "type",
            "content",
            "meta",
            "valves",
            "is_active",
            "is_global",
            "updated_at",
            "created_at",
        },
        "openwebui_pipe_bootstrap_schema_unknown",
    )
    require_columns(conn, "config", {"id", "data", "updated_at"}, "openwebui_pipe_bootstrap_schema_unknown")
    require_columns(
        conn,
        "model",
        {"id", "user_id", "base_model_id", "name", "params", "meta", "updated_at", "created_at", "is_active"},
        "openwebui_model_visibility_schema_unknown",
    )
    require_columns(
        conn,
        "access_grant",
        {"id", "resource_type", "resource_id", "principal_type", "principal_id", "permission", "created_at"},
        "openwebui_model_visibility_schema_unknown",
    )


def selectable_pipe_model_id(function_id: str, function_module: object) -> str:
    if hasattr(function_module, "pipes"):
        raise OpenWebUIBootstrapError("openwebui_pipe_model_id_unknown")
    return function_id


def set_config_path(data: dict, path: str, value) -> None:
    current = data
    parts = path.split(".")
    for part in parts[:-1]:
        node = current.get(part)
        if not isinstance(node, dict):
            node = {}
            current[part] = node
        current = node
    current[parts[-1]] = value


def upsert_config_values(conn: sqlite3.Connection, values: dict[str, object]) -> None:
    columns = table_columns(conn, "config")
    row = conn.execute("SELECT id, data FROM config ORDER BY id LIMIT 1").fetchone()
    if row:
        try:
            data = json.loads(row[1] or "{}")
        except json.JSONDecodeError:
            data = {}
        for path, value in values.items():
            set_config_path(data, path, value)
        conn.execute("UPDATE config SET data = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (json.dumps(data), row[0]))
        return

    data = {"version": 0, "ui": {}}
    for path, value in values.items():
        set_config_path(data, path, value)

    insert_columns = ["data"]
    placeholders = ["?"]
    params = [json.dumps(data)]
    if "version" in columns:
        insert_columns.append("version")
        placeholders.append("?")
        params.append(0)
    if "created_at" in columns:
        insert_columns.append("created_at")
        placeholders.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        placeholders.append("CURRENT_TIMESTAMP")
    conn.execute(
        f"INSERT INTO config ({', '.join(insert_columns)}) VALUES ({', '.join(placeholders)})",
        tuple(params),
    )


def replace_read_grants(conn: sqlite3.Connection, *, resource_type: str, resource_id: str, user_ids: tuple[str, ...]) -> None:
    conn.execute("DELETE FROM access_grant WHERE resource_type = ? AND resource_id = ?", (resource_type, resource_id))
    for principal_id in ("*", *user_ids):
        conn.execute(
            """
            INSERT INTO access_grant (id, resource_type, resource_id, principal_type, principal_id, permission, created_at)
            VALUES (?, ?, ?, 'user', ?, 'read', ?)
            """,
            (str(uuid.uuid4()), resource_type, resource_id, principal_id, int(time.time())),
        )


def upsert_tool(conn: sqlite3.Connection, *, admin_user_id: str, normal_user_id: str, content: str, specs: list[dict], frontmatter: dict) -> None:
    timestamp = int(time.time())
    valves = {
        "orchestrator_api_base_url": env_value("COMPANY_INTELLIGENT_ORCHESTRATOR_URL", "http://orchestrator-api:8000"),
        "openwebui_shared_secret": env_value("OPENWEBUI_SHARED_SECRET", ""),
        "request_timeout_seconds": 600.0,
        "emit_status_updates": True,
    }
    if not valves["openwebui_shared_secret"]:
        raise RuntimeError("OPENWEBUI_SHARED_SECRET is required for bootstrap.")
    meta = {"description": frontmatter.get("description", "Project 3.0 company_intelligent tool."), "manifest": frontmatter}
    existing = conn.execute("SELECT id FROM tool WHERE id = ?", (TOOL_ID,)).fetchone()
    values = (admin_user_id, "Company Intelligent", content, json.dumps(specs), json.dumps(meta), json.dumps(valves), timestamp)
    if existing is None:
        conn.execute(
            """
            INSERT INTO tool (id, user_id, name, content, specs, meta, valves, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (TOOL_ID, *values, timestamp),
        )
    else:
        conn.execute(
            "UPDATE tool SET user_id = ?, name = ?, content = ?, specs = ?, meta = ?, valves = ?, updated_at = ? WHERE id = ?",
            (*values, TOOL_ID),
        )
    replace_read_grants(conn, resource_type="tool", resource_id=TOOL_ID, user_ids=(admin_user_id, normal_user_id))


def upsert_pipe_function(
    conn: sqlite3.Connection,
    *,
    admin_user_id: str,
    function_id: str,
    display_name: str,
    content: str,
    frontmatter: dict,
) -> None:
    validate_pipe_schema(conn)
    timestamp = int(time.time())
    valves = {
        "orchestrator_api_base_url": env_value("COMPANY_INTELLIGENT_ORCHESTRATOR_URL", "http://orchestrator-api:8000"),
        "openwebui_shared_secret": env_value("OPENWEBUI_SHARED_SECRET", ""),
        "request_timeout_seconds": 600.0,
    }
    if not valves["openwebui_shared_secret"]:
        raise RuntimeError("OPENWEBUI_SHARED_SECRET is required for bootstrap.")

    meta = {"description": frontmatter.get("description", "Project 3.0 company_intelligent pipe."), "manifest": frontmatter}
    existing = conn.execute('SELECT id FROM "function" WHERE id = ?', (function_id,)).fetchone()
    values = (
        admin_user_id,
        display_name,
        "pipe",
        content,
        json.dumps(meta),
        json.dumps(valves),
        1,
        0,
        timestamp,
    )
    if existing is None:
        conn.execute(
            """
            INSERT INTO "function" (id, user_id, name, type, content, meta, valves, is_active, is_global, updated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (function_id, *values, timestamp),
        )
    else:
        conn.execute(
            """
            UPDATE "function"
            SET user_id = ?, name = ?, type = ?, content = ?, meta = ?, valves = ?, is_active = ?, is_global = ?, updated_at = ?
            WHERE id = ?
            """,
            (*values, function_id),
        )


def hide_provider_model_from_chooser(conn: sqlite3.Connection, *, model_id: str, admin_user_id: str) -> None:
    timestamp = int(time.time())
    meta = {"description": "Hidden provider model override for Project 3.0 demo UI."}
    existing = conn.execute("SELECT id FROM model WHERE id = ?", (model_id,)).fetchone()
    values = (admin_user_id, None, MODEL_DISPLAY_NAME, json.dumps({}), json.dumps(meta), timestamp, 0)
    if existing is None:
        conn.execute(
            """
            INSERT INTO model (id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (model_id, *values[:-1], timestamp, values[-1]),
        )
    else:
        conn.execute(
            "UPDATE model SET user_id = ?, base_model_id = ?, name = ?, params = ?, meta = ?, updated_at = ?, is_active = ? WHERE id = ?",
            (*values, model_id),
        )
    conn.execute("DELETE FROM access_grant WHERE resource_type = 'model' AND resource_id = ?", (model_id,))


def upsert_pipe_model_preset(
    conn: sqlite3.Connection,
    *,
    admin_user_id: str,
    normal_user_id: str,
    model_id: str,
    display_name: str,
) -> None:
    timestamp = int(time.time())
    meta = {"description": "Project 3.0 Company Intelligent Pipe.", "capabilities": {"tool_calling": False}}
    existing = conn.execute("SELECT id FROM model WHERE id = ?", (model_id,)).fetchone()
    values = (admin_user_id, model_id, display_name, json.dumps({}), json.dumps(meta), timestamp, 1)
    if existing is None:
        conn.execute(
            """
            INSERT INTO model (id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (model_id, *values[:-1], timestamp, values[-1]),
        )
    else:
        conn.execute(
            "UPDATE model SET user_id = ?, base_model_id = ?, name = ?, params = ?, meta = ?, updated_at = ?, is_active = ? WHERE id = ?",
            (*values, model_id),
        )
    replace_read_grants(conn, resource_type="model", resource_id=model_id, user_ids=(admin_user_id, normal_user_id))


def set_default_model(conn: sqlite3.Connection, model_id: str) -> None:
    upsert_config_values(
        conn,
        {
            "ui.default_models": model_id,
            "ui.default_pinned_models": model_id,
            "ui.model_order_list": [model_id],
            "ui.locale": DEFAULT_LOCALE,
            "ui.language": DEFAULT_LOCALE,
            "openai.enable": False,
            "ollama.enable": False,
            "evaluation.arena.enable": False,
            "task.title.enable": False,
            "task.tags.enable": False,
            "task.follow_up.enable": False,
            "task.autocomplete.enable": False,
        },
    )


def main() -> int:
    wait_for_db()
    content = TOOL_SOURCE_PATH.read_text(encoding="utf-8")
    specs, frontmatter = asyncio.run(build_tool_specs(content))
    if not PIPE_SOURCE_PATH.exists():
        raise OpenWebUIBootstrapError("openwebui_pipe_source_missing")
    pipe_content = PIPE_SOURCE_PATH.read_text(encoding="utf-8")
    pipe_module, pipe_type, pipe_frontmatter = asyncio.run(build_function_metadata(PIPE_ID, pipe_content))
    if pipe_type != "pipe":
        raise OpenWebUIBootstrapError("openwebui_pipe_bootstrap_schema_unknown")
    pipe_model_id = selectable_pipe_model_id(PIPE_ID, pipe_module)
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        validate_pipe_schema(conn)
        admin_id = ensure_user(
            conn,
            user_id="project3-demo-admin",
            email=DEMO_ADMIN_EMAIL,
            password=DEMO_ADMIN_PASSWORD,
            name=DEMO_ADMIN_NAME,
            role="admin",
        )
        user_id = ensure_user(
            conn,
            user_id="project3-demo-user",
            email=DEMO_USER_EMAIL,
            password=DEMO_USER_PASSWORD,
            name=DEMO_USER_NAME,
            role="user",
        )
        upsert_tool(conn, admin_user_id=admin_id, normal_user_id=user_id, content=content, specs=specs, frontmatter=frontmatter)
        upsert_pipe_function(
            conn,
            admin_user_id=admin_id,
            function_id=PIPE_ID,
            display_name=PIPE_DISPLAY_NAME,
            content=pipe_content,
            frontmatter=pipe_frontmatter,
        )
        upsert_pipe_model_preset(
            conn,
            admin_user_id=admin_id,
            normal_user_id=user_id,
            model_id=pipe_model_id,
            display_name=PIPE_DISPLAY_NAME,
        )
        hide_provider_model_from_chooser(conn, model_id=MODEL_ID, admin_user_id=admin_id)
        set_default_model(conn, pipe_model_id)
        conn.commit()
    print("Open WebUI demo bootstrap completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
