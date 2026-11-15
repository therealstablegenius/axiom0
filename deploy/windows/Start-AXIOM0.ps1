$ErrorActionPreference='Stop'
$Root=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$env:AXIOM0_DATA_DIR=Join-Path $Root 'axiom0_data'
$Secrets=Join-Path $env:AXIOM0_DATA_DIR 'axiom0-secrets.ps1'
if (-not (Test-Path $Secrets)) { throw 'Install-AXIOM0.ps1 first (no credentials file found)' }
. $Secrets
& (Join-Path $Root '.venv\Scripts\python.exe') -m axiom0 --data-dir $env:AXIOM0_DATA_DIR serve
