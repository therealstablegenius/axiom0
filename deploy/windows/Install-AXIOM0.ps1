# AXIOM0 Living City v0.7 — local Windows pilot installer (Windows PowerShell 5.1+ or PowerShell 7).
# Does not register an exposed network service or a scheduled task.
#
# Secrets are stored as DATA (axiom0-secrets.env, KEY=value lines), never as a script.
# v0.6 stored them as axiom0-secrets.ps1 and dot-sourced it, which executes whatever the
# file contains; an existing .ps1 is converted by parsing (not running) it, then removed.
param([string]$Admin = 'howard')
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Data = Join-Path $Root 'axiom0_data'
$Python = Join-Path $Root '.venv\Scripts\python.exe'

function Protect-OwnerOnly([string]$Path) {
  $acl = Get-Acl $Path
  $acl.SetAccessRuleProtection($true, $false)           # drop inherited permissions
  foreach ($r in @($acl.Access)) { [void]$acl.RemoveAccessRule($r) }
  $me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
  if ((Get-Item -LiteralPath $Path) -is [System.IO.DirectoryInfo]) {
    # Folders: the rule is inherited by every file AXIOM0 creates inside (database, identity key).
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($me, 'FullControl',
              'ContainerInherit,ObjectInherit', 'None', 'Allow')
  } else {
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($me, 'FullControl', 'Allow')
  }
  $acl.AddAccessRule($rule)
  Set-Acl -Path $Path -AclObject $acl
}

if (-not (Test-Path $Python)) {
  & py -3 -m venv (Join-Path $Root '.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required (install from python.org, tick "py launcher")' }
}
& $Python -m pip install --disable-pip-version-check -q -e $Root
if ($LASTEXITCODE -ne 0) { throw 'Python package installation failed' }
& $Python -m axiom0 --data-dir $Data init --admin $Admin
if ($LASTEXITCODE -ne 0) { throw 'AXIOM0 initialization failed' }

$SecretsPath = Join-Path $Data 'axiom0-secrets.env'
$Legacy = Join-Path $Data 'axiom0-secrets.ps1'
if (-not (Test-Path $SecretsPath)) {
  $values = @{}
  if (Test-Path $Legacy) {
    # Parse the old file as text. Only lines of the exact expected shape are accepted.
    foreach ($line in Get-Content -LiteralPath $Legacy) {
      if ($line -match '^\$env:(AXIOM0_API_KEY|AXIOM0_REVIEWER_KEY|AXIOM0_REVIEWER_ID)\s*=\s*"([A-Za-z0-9_\-]+)"\s*$') {
        $values[$Matches[1]] = $Matches[2]
      }
    }
    Write-Host 'Converted axiom0-secrets.ps1 to axiom0-secrets.env (keys kept).'
  }
  if (-not $values['AXIOM0_API_KEY'])      { $values['AXIOM0_API_KEY']      = (& $Python -c 'import secrets; print(secrets.token_urlsafe(48))').Trim() }
  if (-not $values['AXIOM0_REVIEWER_KEY']) { $values['AXIOM0_REVIEWER_KEY'] = (& $Python -c 'import secrets; print(secrets.token_urlsafe(48))').Trim() }
  if (-not $values['AXIOM0_REVIEWER_ID'])  { $values['AXIOM0_REVIEWER_ID']  = 'local_reviewer' }
  New-Item -ItemType File -Path $SecretsPath -Force | Out-Null
  Protect-OwnerOnly $SecretsPath                        # restrict BEFORE writing the keys
  @(
    'AXIOM0_API_KEY=' + $values['AXIOM0_API_KEY']
    'AXIOM0_REVIEWER_KEY=' + $values['AXIOM0_REVIEWER_KEY']
    'AXIOM0_REVIEWER_ID=' + $values['AXIOM0_REVIEWER_ID']
  ) | Set-Content -Encoding ASCII -Path $SecretsPath
}
if (Test-Path $Legacy) { Remove-Item -LiteralPath $Legacy -Force }
Protect-OwnerOnly $Data

& $Python -m axiom0 --data-dir $Data doctor
if ($LASTEXITCODE -ne 0) { throw 'AXIOM0 doctor check failed' }
Write-Host 'Local AXIOM0 pilot installed. Start: .\deploy\windows\Start-AXIOM0.ps1'
Write-Host 'Dashboard: http://127.0.0.1:8765  (API key: AXIOM0_API_KEY in axiom0_data\axiom0-secrets.env)'
Write-Host 'Data and keys are stored locally and restricted to your Windows account; do not share or sync them.'
