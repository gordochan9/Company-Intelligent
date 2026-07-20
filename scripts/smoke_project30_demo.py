from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


FORBIDDEN_PUBLIC_FIELDS = {
    "raw" + "_sql",
    "raw" + "_chunk",
    "raw_rows",
    "trusted" + "_access_context",
    "runtime" + "_final_bundle",
    "DATABASE_URL",
}


def main() -> int:
    _load_dotenv()
    checks: list[dict[str, str]] = []
    exit_code = 0
    services = _compose_services()
    if services is None:
        checks.append({"component": "docker_compose", "status": "failed", "code": "docker_compose_unavailable"})
        exit_code = 1
    else:
        checks.append({"component": "docker_compose", "status": "ok", "code": "services_listed"})

    health_url = os.getenv("ORCHESTRATOR_API_BASE_URL", "http://127.0.0.1:8003").rstrip("/") + "/health"
    if _http_ok(health_url):
        checks.append({"component": "orchestrator-api", "status": "ok", "code": "health_ok"})
    else:
        checks.append({"component": "orchestrator-api", "status": "failed", "code": "health_unavailable"})
        exit_code = 1

    if os.getenv("OPENWEBUI_ENABLED", "true").lower() == "true":
        openwebui_url = os.getenv("OPENWEBUI_BASE_URL", "http://127.0.0.1:8002")
        openwebui_reachable = _http_reachable(openwebui_url)
        checks.append({"component": "openwebui", "status": "ok" if openwebui_reachable else "skipped", "code": "reachable_or_not_started"})
        if openwebui_reachable:
            visibility_ok = _openwebui_model_visibility_ok(openwebui_url)
            checks.append({"component": "openwebui_model_visibility", "status": "ok" if visibility_ok else "failed", "code": "only_company_intelligent_pipe_selectable" if visibility_ok else "model_visibility_failed"})
            if not visibility_ok:
                exit_code = 1

    bootstrap_ready = (
        os.path.exists("openwebui_bootstrap/bootstrap_openwebui.py")
        and os.path.exists("openwebui_tools/company_intelligent.py")
        and os.path.exists("openwebui_functions/company_intelligent_pipe.py")
    )
    checks.append({"component": "company_intelligent", "status": "ok" if bootstrap_ready else "failed", "code": "bootstrap_assets_present" if bootstrap_ready else "bootstrap_assets_missing"})
    if not bootstrap_ready:
        exit_code = 1

    pipe_reaches_backend = _pipe_mock_reaches_backend()
    checks.append({"component": "company_intelligent_pipe", "status": "ok" if pipe_reaches_backend else "failed", "code": "mock_openwebui_ask_reached" if pipe_reaches_backend else "mock_openwebui_ask_failed"})
    if not pipe_reaches_backend:
        exit_code = 1
    llm_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    llm_ready = bool(llm_key and llm_key != "replace_with_deepseek_api_key")
    checks.append({"component": "llm", "status": "ok" if llm_ready else "failed", "code": "deepseek_env_configured" if llm_ready else "deepseek_env_missing"})
    if not llm_ready:
        exit_code = 1

    output = {"status": "ok" if exit_code == 0 else "failed", "checks": checks}
    text = json.dumps(output, indent=2, sort_keys=True)
    if any(field in text for field in FORBIDDEN_PUBLIC_FIELDS):
        print(json.dumps({"status": "failed", "checks": [{"component": "smoke", "status": "failed", "code": "forbidden_public_field"}]}, indent=2))
        return 1
    print(text)
    return exit_code


def _compose_services() -> list[str] | None:
    try:
        result = subprocess.run(["docker", "compose", "ps", "--services", "--filter", "status=running"], check=False, capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _load_dotenv() -> None:
    if not os.path.exists(".env"):
        return
    with open(".env", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key, value)


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def _http_reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=3).close()
        return True
    except (OSError, urllib.error.URLError):
        return False


def _openwebui_model_visibility_ok(base_url: str) -> bool:
    user_token = _openwebui_signin(
        base_url,
        os.getenv("OPENWEBUI_DEMO_USER_EMAIL", "user@demo.com"),
        "user",
    )
    admin_token = _openwebui_signin(
        base_url,
        os.getenv("OPENWEBUI_DEMO_ADMIN_EMAIL", "admin@demo.com"),
        os.getenv("OPENWEBUI_DEMO_ADMIN_PASSWORD", "admin"),
    )
    if not user_token or not admin_token:
        return False
    return _openwebui_models_are_pipe_only(base_url, user_token) and _openwebui_models_are_pipe_only(base_url, admin_token)


def _openwebui_signin(base_url: str, email: str, password: str) -> str | None:
    try:
        data = json.dumps({"email": email, "password": password}).encode("utf-8")
        request = urllib.request.Request(
            base_url.rstrip("/") + "/api/v1/auths/signin",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        token = payload.get("token")
        return token if isinstance(token, str) and token else None
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def _openwebui_models_are_pipe_only(base_url: str, token: str) -> bool:
    try:
        request = urllib.request.Request(
            base_url.rstrip("/") + "/api/models?refresh=true",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False

    model_ids = [model.get("id") for model in payload.get("data", []) if isinstance(model, dict)]
    return model_ids == ["company_intelligent_pipe"]


def _pipe_mock_reaches_backend() -> bool:
    import asyncio

    from openwebui_functions.company_intelligent_pipe import Pipe

    captured: dict[str, object] = {}
    original_urlopen = urllib.request.urlopen

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps({"final_answer": "ok"}).encode("utf-8")

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    urllib.request.urlopen = urlopen
    try:
        pipe = Pipe()
        pipe.valves.orchestrator_api_base_url = "http://mock-backend"
        result = asyncio.run(
            pipe.pipe(
                {"messages": [{"role": "user", "content": "local smoke"}]},
                __metadata__={"user_prompt": "local smoke"},
            )
        )
    finally:
        urllib.request.urlopen = original_urlopen

    return (
        result == "ok"
        and captured.get("url") == "http://mock-backend/openwebui/ask"
        and captured.get("body") == {"question": "local smoke"}
    )


if __name__ == "__main__":
    sys.exit(main())
