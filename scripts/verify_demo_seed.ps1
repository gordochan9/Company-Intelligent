param(
  [string]$SeedPath = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ResolvedSeedPath = if ($SeedPath) { Resolve-Path $SeedPath } else { Resolve-Path (Join-Path $RepoRoot "docker/postgres-init/001_project3_demo_seed.sql.gz") }
$TempSql = Join-Path ([IO.Path]::GetTempPath()) ("project3_demo_seed_{0}.sql" -f ([Guid]::NewGuid().ToString("N")))

$patterns = [ordered]@{
  "github_pat" = ("github" + "_pat_")
  "ghp" = ("gh" + "p_")
  "sk_key" = ("sk-" + "[A-Za-z0-9_-]{20,}")
  "google_api_key" = ("AI" + "za")
  "private-key" = ("BEGIN " + ".*" + "PRIVATE " + "KEY")
  "refresh-token" = ("refresh" + "_" + "token")
  "access-token" = ("access" + "_" + "token")
  "client-secret" = ("client" + "_" + "secret")
  "gordon_windows_path" = [Regex]::Escape(("C:" + "\Users\Gordon"))
  "gordon_unix_path" = ("/Users/" + "Gordon")
  "runtime_audit" = ("runtime" + "/audit")
  "runtime_logs" = ("runtime" + "/logs")
  "openwebui_session" = "openwebui.*(session|auth|user)"
}

try {
  $inputStream = [IO.File]::OpenRead($ResolvedSeedPath)
  try {
    $gzip = [IO.Compression.GzipStream]::new($inputStream, [IO.Compression.CompressionMode]::Decompress)
    try {
      $outputStream = [IO.File]::Create($TempSql)
      try {
        $gzip.CopyTo($outputStream)
      } finally {
        $outputStream.Dispose()
      }
    } finally {
      $gzip.Dispose()
    }
  } finally {
    $inputStream.Dispose()
  }

  $failed = $false
  foreach ($item in $patterns.GetEnumerator()) {
    $match = Select-String -Path $TempSql -Pattern $item.Value -CaseSensitive:$false | Select-Object -First 1
    if ($match) {
      Write-Host ("forbidden_pattern_found: {0}: line {1}" -f $item.Key, $match.LineNumber)
      $failed = $true
    }
  }
  if ($failed) { exit 1 }
  Write-Host "Seed safety scan passed."
} finally {
  Remove-Item -LiteralPath $TempSql -Force -ErrorAction SilentlyContinue
}
