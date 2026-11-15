# AXIOM0 Living City v0.6 — local Windows pilot installer (PowerShell 5.1+).
# Does not register an exposed network service or a scheduled task.
param([string]$Admin = 'howard')
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Data = Join-Path $Root 'axiom0_data'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
  & py -3 -m venv (Join-Path $Root '.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required' }
}
& $Python -m pip install -e $Root
if ($LASTEXITCODE -ne 0) { throw 'Python package installation failed' }
& $Python -m axiom0 --data-dir $Data init --admin $Admin
if ($LASTEXITCODE -ne 0) { throw 'AXIOM0 initialization failed' }
$SecretsPath = Join-Path $Data 'axiom0-secrets.ps1'
if (-not (Test-Path $SecretsPath)) {
  $ApiKey = (& $Python -c 'import secrets; print(secrets.token_urlsafe(48))').Trim()
  $ReviewerKey = (& $Python -c 'import secrets; print(secrets.token_urlsafe(48))').Trim()
  @(
    '$env:AXIOM0_API_KEY = "' + $ApiKey + '"'
    '$env:AXIOM0_REVIEWER_KEY = "' + $ReviewerKey + '"'
    '$env:AXIOM0_REVIEWER_ID = "local_reviewer"'
  ) | Set-Content -Encoding ASCII -Path $SecretsPath
  $acl=Get-Acl $SecretsPath
  $acl.SetAccessRuleProtection($true,$false)
  $rule=New-Object System.Security.AccessControl.FileSystemAccessRule([System.Security.Principal.WindowsIdentity]::GetCurrent().Name,'FullControl','Allow')
  $acl.AddAccessRule($rule)
  Set-Acl -Path $SecretsPath -AclObject $acl
}
& $Python -m axiom0 --data-dir $Data doctor
if ($LASTEXITCODE -ne 0) { throw 'AXIOM0 doctor check failed' }
Write-Host 'Local AXIOM0 pilot installed. Start: .\deploy\windows\Start-AXIOM0.ps1'
Write-Host 'Data and secrets are stored locally; do not share or sync the identity private key.'
