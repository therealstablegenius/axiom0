# Start the local AXIOM0 server (127.0.0.1:8765 only). Keys are read as data, never executed,
# and are removed from this PowerShell session when the server stops.
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Data = Join-Path $Root 'axiom0_data'
$Secrets = Join-Path $Data 'axiom0-secrets.env'
if (-not (Test-Path $Secrets)) { throw 'Run .\deploy\windows\Install-AXIOM0.ps1 first (no axiom0-secrets.env found)' }

$names = @('AXIOM0_API_KEY', 'AXIOM0_REVIEWER_KEY', 'AXIOM0_REVIEWER_ID')
$found = @{}
foreach ($line in Get-Content -LiteralPath $Secrets) {
  if ($line -match '^(AXIOM0_[A-Z_]+)=([A-Za-z0-9_\-]+)\s*$' -and $names -contains $Matches[1]) {
    $found[$Matches[1]] = $Matches[2]
  }
}
foreach ($n in $names) { if (-not $found[$n]) { throw "axiom0-secrets.env is missing $n; re-run the installer" } }

try {
  foreach ($n in $names) { Set-Item -Path "Env:$n" -Value $found[$n] }
  $env:AXIOM0_DATA_DIR = $Data
  & (Join-Path $Root '.venv\Scripts\python.exe') -m axiom0 --data-dir $Data serve
} finally {
  foreach ($n in $names) { Remove-Item -Path "Env:$n" -ErrorAction SilentlyContinue }
}
