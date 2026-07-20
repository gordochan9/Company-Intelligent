@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
  echo docker command not found
  exit /b 1
)

docker compose exec -T orchestrator-api python -m app.scripts.smoke_watchdog_runtime --dataset-root /app/active_dataset
exit /b %ERRORLEVEL%
