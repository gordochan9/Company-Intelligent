param(
  [string]$OutputPath = "",
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SeedPath = if ($OutputPath) { $OutputPath } else { Join-Path $RepoRoot "docker/postgres-init/001_project3_demo_seed.sql.gz" }

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path (Split-Path $SeedPath) | Out-Null

$containerId = (& docker compose ps -q postgres).Trim()
if (-not $containerId) {
  throw "postgres_container_not_running"
}

$dumpCommand = @'
set -eu
pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=plain --no-owner --no-privileges --no-comments --exclude-table-data=audit_events | gzip -c > /tmp/project3_demo_seed.sql.gz
'@

& docker compose exec -T postgres sh -lc $dumpCommand
if ($LASTEXITCODE -ne 0) { throw "pg_dump_failed" }

& docker cp "${containerId}:/tmp/project3_demo_seed.sql.gz" $SeedPath
if ($LASTEXITCODE -ne 0) { throw "docker_cp_seed_failed" }

& docker compose exec -T postgres rm -f /tmp/project3_demo_seed.sql.gz | Out-Null

if (-not $SkipVerify) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "verify_demo_seed.ps1") -SeedPath $SeedPath
  if ($LASTEXITCODE -ne 0) { throw "seed_verify_failed" }
}

Write-Host ("Seed exported: {0}" -f (Resolve-Path $SeedPath))
