# Start a Sports HQ GitHub workflow from the laptop, because GitHub runs scheduled workflows hours late (Q-014, Q-029).
# Run by Windows Task Scheduler (user level, folder \SportsHQ\; see ops/designs/Q-014.md "The exact tasks" and
# "Sign-in for the scheduled tasks"). No AI, no Claude usage: just `gh workflow run`.
#
#   kick.ps1 -Workflow run.yml -FreshMinutes 20   # skip when the site's data was committed in the last 20 minutes
#   kick.ps1 -Workflow model-health.yml            # always start it
#   kick.ps1 -SaveToken                            # Michael only, once: store the scheduled tasks' GitHub token (below)
#
# Sign-in: gh's own login lives in Windows Credential Manager, which gh can't reach from Task Scheduler (Nov 5). So when
# %LOCALAPPDATA%\sports-hq-kick.token exists (written by -SaveToken, encrypted for Michael's Windows account with DPAPI),
# the token is decrypted into GH_TOKEN for this process and its gh calls only. It is never printed or logged. A Claude
# session must never run -SaveToken, open the token file or print GH_TOKEN.
#
# Every run writes exactly one line to %LOCALAPPDATA%\sports-hq-kick.log (last 500 kept): started / skipped / FAILED.
# If that file can't be written, the line goes to %TEMP%\sports-hq-kick.log instead, so a failure is never silent.
param(
  [string]$Workflow = "run.yml",
  [int]$FreshMinutes = 0,
  [switch]$SaveToken,
  [string]$Gh = "C:\Program Files\GitHub CLI\gh.exe",
  [string]$Log = (Join-Path $env:LOCALAPPDATA "sports-hq-kick.log"),
  [string]$TokenFile = (Join-Path $env:LOCALAPPDATA "sports-hq-kick.token")
)
# no "Stop": in Windows PowerShell 5.1 a native program's stderr turns into errors whose handling differs by host, so
# every gh call is checked by its exit code instead
$ErrorActionPreference = "Continue"
$repo = "mbryan20/sports-hq"
$help = "see ops/designs/Q-014.md, 'Sign-in for the scheduled tasks'"
if (-not (Test-Path $Gh)) { $Gh = "gh" }

function Write-Log([string]$msg) {
  $line = "{0:yyyy-MM-dd HH:mm:ss} {1}: {2}" -f (Get-Date), $Workflow, (($msg -replace "\s+", " ").Trim())
  try {
    $old = @()
    if (Test-Path $Log) { $old = @(Get-Content $Log -Tail 499 -ErrorAction Stop) }
    Set-Content -Path $Log -Value ($old + $line) -Encoding utf8 -ErrorAction Stop
  } catch {
    try { Add-Content -Path (Join-Path $env:TEMP "sports-hq-kick.log") -Value "$line (main log $Log failed: $($_.Exception.Message))" -ErrorAction Stop } catch {}
  }
}

function Invoke-Gh([string[]]$GhArgs) {
  $global:LASTEXITCODE = $null
  try { $out = & $Gh @GhArgs 2>&1 | ForEach-Object { "$_" } } catch { return @{ code = 127; out = $_.Exception.Message } }
  $code = if ($null -eq $LASTEXITCODE) { 127 } else { $LASTEXITCODE }
  return @{ code = $code; out = (@($out) -join " ") }
}

trap { Write-Log "FAILED: $($_.Exception.Message)"; exit 1 }

if ($SaveToken) {
  # interactive, for Michael in his own PowerShell window; the input is hidden and never echoed
  $s = Read-Host "Paste the Sports HQ GitHub token (input hidden)" -AsSecureString
  if ($s.Length -eq 0) { Write-Host "Nothing saved."; exit 1 }
  $s | ConvertFrom-SecureString | Set-Content -Path $TokenFile -Encoding ascii
  Write-Host "Saved, encrypted for your Windows account only: $TokenFile"
  exit 0
}

if (Test-Path $TokenFile) {
  try {
    $sec = (Get-Content $TokenFile -Raw -ErrorAction Stop).Trim() | ConvertTo-SecureString -ErrorAction Stop
    $env:GH_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
  } catch {
    Write-Log "FAILED: the saved token in $TokenFile can't be read (save it again with kick.ps1 -SaveToken; $help)"
    exit 1
  }
}

$auth = Invoke-Gh @("auth", "status", "--hostname", "github.com")
if ($auth.code -ne 0) {
  $why = if ($env:GH_TOKEN) { "GitHub rejected the saved token (expired or revoked?)" } elseif ($auth.code -eq 127) { "gh isn't installed or can't start" } else { "gh is not signed in here and no saved token exists" }
  Write-Log "FAILED: $why; nothing started ($help)"
  exit 2
}

if ($FreshMinutes -gt 0) {
  # status.json changes on every pass of run.yml, so its last commit is the heartbeat of a running loop
  $r = Invoke-Gh @("api", "repos/$repo/commits?path=docs/data/status.json&per_page=1", "--jq", ".[0].commit.committer.date")
  if ($r.code -eq 0 -and $r.out.Trim()) {
    $age = ((Get-Date).ToUniversalTime() - ([datetime]::Parse($r.out.Trim())).ToUniversalTime()).TotalMinutes
    if ($age -lt $FreshMinutes) {
      Write-Log ("skipped: data committed {0:N0} min ago" -f $age)
      exit 0
    }
  }
}

$r = Invoke-Gh @("workflow", "run", $Workflow, "-R", $repo)
if ($r.code -ne 0) { Write-Log "FAILED: gh workflow run: $($r.out)"; exit 1 }
Write-Log "started"
exit 0
