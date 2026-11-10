# Start a Sports HQ GitHub workflow from the laptop, because GitHub runs scheduled workflows hours late (Q-014, Q-029).
# Run by Windows Task Scheduler (user level, folder \SportsHQ\; see ops/designs/Q-014.md "The exact tasks" and
# "Sign-in for the scheduled tasks"). No AI, no Claude usage: just `gh workflow run`.
#
#   kick.ps1 -Workflow run.yml -FreshMinutes 20   # skip when the site's data was committed in the last 20 minutes
#   kick.ps1 -Workflow model-health.yml            # always start it
#   kick.ps1 -SaveToken                            # Michael only, once: store the scheduled tasks' GitHub token (below)
#
# Sign-in: the Claude desktop app is a packaged app, so a gh login made inside it lives in the app's private copy of
# %APPDATA% and doesn't exist for Task Scheduler (Nov 5). Michael signs in outside the app, in his own PowerShell window:
# either gh's normal login, or a one-repo token saved with -SaveToken. When %LOCALAPPDATA%\sports-hq-kick.token exists
# (encrypted for Michael's Windows account with DPAPI), the token is decrypted into GH_TOKEN for this process and its gh
# calls only. It is never printed or logged. A Claude session must never run -SaveToken, open the token file or print
# GH_TOKEN.
#
# Every run writes exactly one line to %LOCALAPPDATA%\sports-hq-kick.log (last 500 kept): started / skipped / FAILED.
# Read it from Michael's own PowerShell window or a scheduled task: a Claude app shell sees the app's private copy.
# If that file can't be written, the line goes to %TEMP%\sports-hq-kick.log, else to the repo's .cache\sports-hq-kick.log
# (gitignored), so a failure is never silent.
#
# A failure also sends ONE phone push per outage (Q-037): title "Sports HQ: laptop can't start GitHub jobs", the reason,
# and the fix doc. The ntfy topic is read from picks\.ntfy_topic next to this script (gitignored) and never logged. What
# was pushed is remembered in %LOCALAPPDATA%\sports-hq-kick.alerted; the same failure again pushes nothing, and a
# working kick clears it, so the next outage pushes again.
param(
  [string]$Workflow = "run.yml",
  [int]$FreshMinutes = 0,
  [switch]$SaveToken,
  [string]$Gh = "C:\Program Files\GitHub CLI\gh.exe",
  [string]$Log = "",
  [string]$TokenFile = "",
  [string]$AlertFile = "",
  [string]$TopicFile = "",
  [string]$NtfyBase = "https://ntfy.sh"
)
# no "Stop": in Windows PowerShell 5.1 a native program's stderr turns into errors whose handling differs by host, so
# every gh call is checked by its exit code instead
$ErrorActionPreference = "Continue"
$repo = "mbryan20/sports-hq"
$help = "see ops/designs/Q-014.md, 'Sign-in for the scheduled tasks'"
# don't trust LOCALAPPDATA to be set (defensive: nothing below may fail before the log works). Nov 5's "missing" lines
# weren't missing: they were in the real folder, which a Claude app shell doesn't see
$local = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath("LocalApplicationData") }
if (-not $local -and $env:USERPROFILE) { $local = Join-Path $env:USERPROFILE "AppData\Local" }
if (-not $Log) { $Log = if ($local) { Join-Path $local "sports-hq-kick.log" } else { "" } }
if (-not $TokenFile) { $TokenFile = if ($local) { Join-Path $local "sports-hq-kick.token" } else { "" } }
if (-not $AlertFile) { $AlertFile = if ($local) { Join-Path $local "sports-hq-kick.alerted" } elseif ($env:TEMP) { Join-Path $env:TEMP "sports-hq-kick.alerted" } else { "" } }
if (-not $TopicFile) { $TopicFile = Join-Path (Split-Path $PSScriptRoot -Parent) "picks\.ntfy_topic" }
# last resorts: TEMP, then the repo's own gitignored .cache folder next to this script
$fallbacks = @($env:TEMP, (Join-Path (Split-Path $PSScriptRoot -Parent) ".cache")) | Where-Object { $_ } |
  ForEach-Object { Join-Path $_ "sports-hq-kick.log" }
if (-not (Test-Path $Gh)) { $Gh = "gh" }

function Write-Log([string]$msg) {
  $line = "{0:yyyy-MM-dd HH:mm:ss} {1}: {2}" -f (Get-Date), $Workflow, (($msg -replace "\s+", " ").Trim())
  $why = "no log folder (LOCALAPPDATA and USERPROFILE empty)"
  if ($Log) {
    try {
      $old = @()
      if (Test-Path $Log) { $old = @(Get-Content $Log -Tail 499 -ErrorAction Stop) }
      Set-Content -Path $Log -Value ($old + $line) -Encoding utf8 -ErrorAction Stop
      return
    } catch { $why = "main log $Log failed: $($_.Exception.Message)" }
  }
  foreach ($f in $fallbacks) {
    try { Add-Content -Path $f -Value "$line ($why)" -ErrorAction Stop; return } catch {}
  }
}

function Invoke-Gh([string[]]$GhArgs) {
  $global:LASTEXITCODE = $null
  try { $out = & $Gh @GhArgs 2>&1 | ForEach-Object { "$_" } } catch { return @{ code = 127; out = $_.Exception.Message } }
  $code = if ($null -eq $LASTEXITCODE) { 127 } else { $LASTEXITCODE }
  return @{ code = $code; out = (@($out) -join " ") }
}

# --- one phone push per outage (Q-037) ---
$authKeys = @("token-unreadable", "token-rejected", "gh-missing", "not-signed-in")

function Get-Alerted {
  if (-not ($AlertFile -and (Test-Path $AlertFile))) { return @() }
  return @(Get-Content $AlertFile -ErrorAction SilentlyContinue | Where-Object { $_ })
}

function Set-Alerted([string[]]$keys) {
  if (-not $AlertFile) { return }
  try {
    if ($keys.Count) { Set-Content -Path $AlertFile -Value $keys -Encoding ascii -ErrorAction Stop }
    elseif (Test-Path $AlertFile) { Remove-Item $AlertFile -ErrorAction Stop }
  } catch {}
}

function Clear-Alerted([string[]]$keys) {
  $old = @(Get-Alerted)
  if ($old.Count) { Set-Alerted @($old | Where-Object { $keys -notcontains $_ }) }
}

function Send-Alert([string]$key, [string]$reason) {
  # returns a note for the log line; never throws, never logs the topic
  $done = @(Get-Alerted)
  if ($done -contains $key) { return "phone alert already sent for this outage" }
  if (-not ($TopicFile -and (Test-Path $TopicFile))) { return "no phone alert (no ntfy topic file)" }
  $topic = ""
  try {
    $topic = (Get-Content $TopicFile -Raw -ErrorAction Stop).Trim()
    if (-not $topic) { return "no phone alert (the ntfy topic file is empty)" }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $short = if ($reason.Length -gt 300) { $reason.Substring(0, 300) + "..." } else { $reason }
    $msg = "$short. Jobs run late on GitHub's own schedule until this is fixed. Fix: ops/designs/Q-014.md"
    $req = @{
      Method = "Post"; Uri = "$NtfyBase/$topic"; UseBasicParsing = $true; TimeoutSec = 20; ErrorAction = "Stop"
      Headers = @{ Title = "Sports HQ: laptop can't start GitHub jobs"; Priority = "4"; Tags = "warning" }
      Body = [Text.Encoding]::UTF8.GetBytes($msg); ContentType = "text/plain; charset=utf-8"
    }
    Invoke-RestMethod @req | Out-Null
  } catch {
    $e = "$($_.Exception.Message)"
    if ($topic) { $e = $e -replace [regex]::Escape($topic), "<topic>" }
    return "phone alert failed: $e"
  }
  Set-Alerted @($done + $key)
  return "phone alert sent"
}

function Stop-Failed([string]$key, [string]$reason, [string]$extra, [int]$code) {
  $note = Send-Alert $key $reason
  Write-Log "FAILED: $reason$extra; $note"
  exit $code
}

trap { Stop-Failed "error:$Workflow" "kick.ps1 error: $($_.Exception.Message)" "" 1 }

if ($SaveToken) {
  # interactive, for Michael in his own PowerShell window; the input is hidden and never echoed
  $s = Read-Host "Paste the Sports HQ GitHub token (input hidden)" -AsSecureString
  if ($s.Length -eq 0) { Write-Host "Nothing saved."; exit 1 }
  $s | ConvertFrom-SecureString | Set-Content -Path $TokenFile -Encoding ascii
  Write-Host "Saved, encrypted for your Windows account only: $TokenFile"
  exit 0
}

if ($TokenFile -and (Test-Path $TokenFile)) {
  try {
    $sec = (Get-Content $TokenFile -Raw -ErrorAction Stop).Trim() | ConvertTo-SecureString -ErrorAction Stop
    $env:GH_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
  } catch {
    Stop-Failed "token-unreadable" "the saved token in $TokenFile can't be read" " (save it again with kick.ps1 -SaveToken; $help)" 1
  }
}

$auth = Invoke-Gh @("auth", "status", "--hostname", "github.com")
if ($auth.code -ne 0) {
  if ($env:GH_TOKEN) { $key = "token-rejected"; $why = "GitHub rejected the saved token (expired or revoked?), or GitHub is down" }
  elseif ($auth.code -eq 127) { $key = "gh-missing"; $why = "gh isn't installed or can't start" }
  else { $key = "not-signed-in"; $why = "gh is not signed in here and no saved token exists" }
  Stop-Failed $key $why "; nothing started ($help)" 2
}
Clear-Alerted $authKeys   # signed in: a sign-in outage (if any) is over

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
if ($r.code -ne 0) { Stop-Failed "dispatch:$Workflow" "gh couldn't start $Workflow ($($r.out))" "" 1 }
Clear-Alerted @("dispatch:$Workflow", "error:$Workflow")
Write-Log "started"
exit 0
