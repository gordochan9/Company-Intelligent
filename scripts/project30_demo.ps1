param(
  [ValidateSet("start", "stop", "smoke")]
  [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"
$EnvExamplePath = Join-Path $RepoRoot ".env.example"
$script:DemoExitCode = 0

function Set-DemoExitCode($Code) {
  $script:DemoExitCode = $Code
}

function Write-Step($Name, $Status, $Message = "") {
  if ($Message) {
    Write-Host ("[{0}] {1}: {2}" -f $Status, $Name, $Message)
  } else {
    Write-Host ("[{0}] {1}" -f $Status, $Name)
  }
}

function New-LocalSecret {
  $bytes = New-Object byte[] 32
  $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
  try {
    $rng.GetBytes($bytes)
  } finally {
    $rng.Dispose()
  }
  return [Convert]::ToBase64String($bytes).Replace("+", "A").Replace("/", "B").TrimEnd("=")
}

function Read-DotEnv($Path) {
  $values = @{}
  if (-not (Test-Path $Path)) { return $values }
  foreach ($line in Get-Content $Path) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
    $parts = $trimmed.Split("=", 2)
    $values[$parts[0]] = $parts[1]
  }
  return $values
}

function Test-Placeholder($Value) {
  if ($null -eq $Value) { return $true }
  $trimmed = [string]$Value
  return @("", "replace_with_deepseek_api_key", "replace_with_random_local_secret", "replace_with_random_local_webui_secret", "replace_with_random_local_tool_secret", "change_me", "change_me_local_only") -contains $trimmed
}

function Write-DotEnvIfMissing {
  if (Test-Path $EnvPath) { return $false }
  $postgresSecret = New-LocalSecret
  $webuiSecret = New-LocalSecret
  $toolSecret = New-LocalSecret
  $content = @"
# Local-only Project 3.0 demo env. Do not commit this file.
POSTGRES_DB=project3
POSTGRES_USER=project3
POSTGRES_PASSWORD=$postgresSecret
POSTGRES_PORT=5432

ORCHESTRATOR_HOST=0.0.0.0
ORCHESTRATOR_PORT=8003
ORCHESTRATOR_LOG_LEVEL=info
ORCHESTRATOR_API_BASE_URL=http://127.0.0.1:8003

HOST_SHARE_DRIVE_PATH=./demo_share_drive
CONTAINER_ACTIVE_DATASET_ROOT=/app/active_dataset
AUDIT_LOG_DIR=/app/runtime/audit
RUNTIME_LOG_DIR=/app/runtime/logs

LLM_PROVIDER=deepseek
MODEL_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-pro
MODEL_NAME=deepseek-v4-pro
OPENWEBUI_DEMO_MODEL_DISPLAY_NAME=DeepSeek V4 Pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=replace_with_deepseek_api_key

OPENWEBUI_ENABLED=true
OPENWEBUI_PORT=8002
OPENWEBUI_BASE_URL=http://127.0.0.1:8002
OPENWEBUI_WEBUI_SECRET_KEY=$webuiSecret
OPENWEBUI_SHARED_SECRET=$toolSecret
COMPANY_INTELLIGENT_ORCHESTRATOR_URL=http://orchestrator-api:8000
OPENWEBUI_DEMO_ADMIN_EMAIL=admin@demo.com
OPENWEBUI_DEMO_ADMIN_PASSWORD=admin
OPENWEBUI_DEMO_ADMIN_NAME=Project 3.0 Demo Admin
OPENWEBUI_DEMO_USER_EMAIL=user@demo.com
OPENWEBUI_DEMO_USER_PASSWORD=user
OPENWEBUI_DEMO_USER_NAME=Project 3.0 Demo User

PROJECT3_SKIP_BROWSER_OPEN=false
PROJECT3_SKIP_OPENWEBUI_BOOTSTRAP=false
PROJECT3_SKIP_WATCHDOG_START=false
PROJECT3_SKIP_STARTUP_SMOKE=false
PROJECT3_DEMO_NO_PAUSE=false
WATCHDOG_ENABLED=true
"@
  Set-Content -Path $EnvPath -Value $content -Encoding ascii
  return $true
}

function Update-LocalSecretsIfPlaceholder {
  if (-not (Test-Path $EnvPath)) { return $false }
  $content = Get-Content $EnvPath -Raw
  $changed = $false
  foreach ($item in @(
    @("POSTGRES_PASSWORD", "change_me_local_only"),
    @("OPENWEBUI_WEBUI_SECRET_KEY", "replace_with_random_local_webui_secret"),
    @("OPENWEBUI_SHARED_SECRET", "replace_with_random_local_tool_secret")
  )) {
    $name = $item[0]
    $placeholder = $item[1]
    if ($content -match "(?m)^$name=$([Regex]::Escape($placeholder))$") {
      $content = $content -replace "(?m)^$name=$([Regex]::Escape($placeholder))$", "$name=$(New-LocalSecret)"
      $changed = $true
    }
  }
  if ($changed) {
    Set-Content -Path $EnvPath -Value $content -Encoding ascii -NoNewline
  }
  return $changed
}

function Get-ConfigValue($Config, $Name, $Default = "") {
  $processValue = [Environment]::GetEnvironmentVariable($Name)
  if ($processValue) { return $processValue }
  if ($Config.ContainsKey($Name)) { return $Config[$Name] }
  return $Default
}

function Assert-DockerAvailable {
  $docker = Get-Command docker -ErrorAction SilentlyContinue
  if (-not $docker) {
    $bundledDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path $bundledDocker) {
      $env:Path = (Split-Path $bundledDocker) + ";" + $env:Path
      $docker = Get-Command docker -ErrorAction SilentlyContinue
    }
  }
  if (-not $docker) { throw "docker_command_not_found" }
}

function Test-DockerReady {
  $previousErrorAction = $ErrorActionPreference
  $ErrorActionPreference = "SilentlyContinue"
  try {
    & docker info --format "{{.ServerVersion}}" *> $null
    return $LASTEXITCODE -eq 0
  } finally {
    $ErrorActionPreference = $previousErrorAction
  }
}

function Wait-DockerReady($Seconds = 180) {
  Assert-DockerAvailable
  if (Test-DockerReady) { return }

  $desktopPaths = @(
    (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
    (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
  ) | Where-Object { Test-Path $_ }
  if ($desktopPaths.Count -gt 0) {
    Write-Step "Docker Desktop" "starting"
    Start-Process -FilePath $desktopPaths[0]
  }

  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    if (Test-DockerReady) { return }
  }
  throw "docker_daemon_not_ready: Start Docker Desktop, complete its first-run setup, then run start-demo.bat again."
}

function Assert-ComposeConfigValid {
  & docker compose config --quiet
  if ($LASTEXITCODE -ne 0) { throw "docker_compose_config_failed" }
}

function Assert-RequiredEnvConfigured($Config) {
  $missing = @()
  foreach ($name in @("POSTGRES_PASSWORD", "DEEPSEEK_API_KEY", "OPENWEBUI_SHARED_SECRET")) {
    if (Test-Placeholder (Get-ConfigValue $Config $name)) { $missing += $name }
  }
  if ($missing.Count -gt 0) {
    throw ("required_env_missing:" + ($missing -join ","))
  }
}

function Wait-HttpOk($Url, $Seconds = 60) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return }
    } catch {
      Start-Sleep -Seconds 2
    }
  }
  throw "http_wait_failed"
}

function Reset-StaleComposeState {
  $previousErrorAction = $ErrorActionPreference
  $ErrorActionPreference = "SilentlyContinue"
  try {
    & docker compose --profile openwebui --profile watchdog down --remove-orphans *> $null
    & docker compose --profile openwebui --profile watchdog rm --stop --force *> $null
  } finally {
    $ErrorActionPreference = $previousErrorAction
  }
}

function Wait-ComposeServiceExitZero($Service, $Seconds = 180) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    $containerId = [string](& docker compose ps -a -q $Service)
    $containerId = $containerId.Trim()
    if ($containerId) {
      $state = [string](& docker inspect --format '{{.State.Status}}|{{.State.ExitCode}}' $containerId)
      if ($LASTEXITCODE -eq 0) {
        $parts = $state.Trim().Split("|", 2)
        if ($parts[0] -eq "exited") {
          if ($parts[1] -eq "0") { return }
          throw "$Service`_failed"
        }
      }
    }
    Start-Sleep -Seconds 2
  }
  throw "$Service`_wait_failed"
}

function Get-OpenWebUiToken($BaseUrl, $Email, $Password) {
  $body = @{ email = $Email; password = $Password } | ConvertTo-Json
  $response = Invoke-RestMethod -Uri ($BaseUrl.TrimEnd("/") + "/api/v1/auths/signin") -Method Post -ContentType "application/json" -Body $body -TimeoutSec 10
  if (-not $response.token) { throw "openwebui_signin_failed" }
  return [string]$response.token
}

function Assert-OpenWebUiModelVisibility($Config, $BaseUrl) {
  foreach ($account in @(
    @((Get-ConfigValue $Config "OPENWEBUI_DEMO_ADMIN_EMAIL" "admin@demo.com"), (Get-ConfigValue $Config "OPENWEBUI_DEMO_ADMIN_PASSWORD" "admin")),
    @((Get-ConfigValue $Config "OPENWEBUI_DEMO_USER_EMAIL" "user@demo.com"), "user")
  )) {
    $token = Get-OpenWebUiToken $BaseUrl $account[0] $account[1]
    $response = Invoke-RestMethod -Uri ($BaseUrl.TrimEnd("/") + "/api/models?refresh=true") -Headers @{ Authorization = "Bearer $token" } -Method Get -TimeoutSec 15
    $modelIds = @($response.data | ForEach-Object { $_.id })
    if ($modelIds.Count -ne 1 -or $modelIds[0] -ne "company_intelligent_pipe") {
      throw "openwebui_model_visibility_failed"
    }
  }
}

function Invoke-DemoSmoke($Config, $OpenWebUiEnabled) {
  $healthBaseUrl = Get-ConfigValue $Config "ORCHESTRATOR_API_BASE_URL" "http://127.0.0.1:8003"
  Wait-HttpOk ($healthBaseUrl.TrimEnd("/") + "/health")
  if ($OpenWebUiEnabled) {
    $openWebUiBaseUrl = Get-ConfigValue $Config "OPENWEBUI_BASE_URL" "http://127.0.0.1:8002"
    Wait-HttpOk $openWebUiBaseUrl 180
    Wait-ComposeServiceExitZero "openwebui-bootstrap"
    Assert-OpenWebUiModelVisibility $Config $openWebUiBaseUrl
  }
  Write-Step "Project 3.0 smoke" "ok"
}

function Write-DockerDiagnostics {
  & docker compose ps -a
  foreach ($service in @("openwebui", "openwebui-bootstrap", "orchestrator-api", "postgres")) {
    Write-Step "docker logs" "info" $service
    & docker compose logs --tail 120 $service
  }
}

function Start-Demo {
  Set-Location $RepoRoot
  $created = Write-DotEnvIfMissing
  if ($created) {
    Write-Step ".env" "created" "Fill DEEPSEEK_API_KEY, then run start-demo.bat again."
    Set-DemoExitCode 2
    return
  }
  if (Update-LocalSecretsIfPlaceholder) {
    Write-Step ".env" "updated" "Generated local-only Docker/OpenWebUI secrets."
  }
  $config = Read-DotEnv $EnvPath
  Wait-DockerReady
  Assert-RequiredEnvConfigured $config
  Assert-ComposeConfigValid
  Reset-StaleComposeState
  $openWebUiEnabled = (Get-ConfigValue $config "OPENWEBUI_ENABLED" "false") -eq "true"
  $watchdogEnabled = (Get-ConfigValue $config "WATCHDOG_ENABLED" "true") -eq "true" -and (Get-ConfigValue $config "PROJECT3_SKIP_WATCHDOG_START" "false") -ne "true"
  if ($openWebUiEnabled) {
    if ($watchdogEnabled) {
      & docker compose --profile openwebui --profile watchdog up -d --build
    } else {
      & docker compose --profile openwebui up -d --build
    }
  } elseif ($watchdogEnabled) {
    & docker compose --profile watchdog up -d --build
  } else {
    & docker compose up -d --build
  }
  if ($LASTEXITCODE -ne 0) {
    Write-DockerDiagnostics
    throw "docker_compose_up_failed"
  }
  if ((Get-ConfigValue $config "PROJECT3_SKIP_STARTUP_SMOKE" "false") -ne "true") {
    try {
      Invoke-DemoSmoke $config $openWebUiEnabled
    } catch {
      Write-DockerDiagnostics
      throw
    }
  }
  if ($openWebUiEnabled -and (Get-ConfigValue $config "PROJECT3_SKIP_BROWSER_OPEN" "false") -ne "true") {
    Start-Process (Get-ConfigValue $config "OPENWEBUI_BASE_URL" "http://127.0.0.1:8002")
  }
  Write-Step "Project 3.0 demo" "ok" "Startup coordinator finished."
  Set-DemoExitCode 0
}

function Stop-Demo {
  Set-Location $RepoRoot
  Wait-DockerReady
  & docker compose stop
  if ($LASTEXITCODE -ne 0) { throw "docker_compose_stop_failed" }
  Write-Step "Project 3.0 demo" "stopped" "Docker volumes and source files were preserved."
  Set-DemoExitCode 0
}

function Smoke-Demo {
  Set-Location $RepoRoot
  $config = Read-DotEnv $EnvPath
  Wait-DockerReady
  Assert-RequiredEnvConfigured $config
  Assert-ComposeConfigValid
  $openWebUiEnabled = (Get-ConfigValue $config "OPENWEBUI_ENABLED" "false") -eq "true"
  Invoke-DemoSmoke $config $openWebUiEnabled
  Set-DemoExitCode 0
}

try {
  switch ($Action) {
    "start" { Start-Demo }
    "stop" { Stop-Demo }
    "smoke" { Smoke-Demo }
  }
  exit $script:DemoExitCode
} catch {
  $message = [string]$_.Exception.Message
  $message = $message -replace [Regex]::Escape($RepoRoot), "[repo]"
  Write-Step "Project 3.0 demo" "failed" $message
  exit 1
}
