from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_compose_uses_a_stable_v26_project_name():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert compose.startswith("name: company-intelligent-v26\n")


def test_demo_startup_recovers_stale_compose_state_without_host_python():
    startup = (ROOT / "scripts/project30_demo.ps1").read_text(encoding="utf-8")

    assert "docker compose --profile openwebui --profile watchdog down --remove-orphans" in startup
    assert "docker compose --profile openwebui --profile watchdog rm --stop --force" in startup
    assert '$ErrorActionPreference = "SilentlyContinue"' in startup
    assert "& python" not in startup


def test_demo_startup_waits_for_docker_and_openwebui_bootstrap():
    startup = (ROOT / "scripts/project30_demo.ps1").read_text(encoding="utf-8")
    docker_ready = startup.split("function Test-DockerReady", 1)[1].split("function Wait-DockerReady", 1)[0]

    assert "docker info" in startup
    assert "Docker Desktop.exe" in startup
    assert "Docker\\Docker\\resources\\bin\\docker.exe" in startup
    assert '$ErrorActionPreference = "SilentlyContinue"' in docker_ready
    assert 'Wait-ComposeServiceExitZero "openwebui-bootstrap"' in startup
