# Start a Sports HQ GitHub workflow from the laptop, because GitHub runs scheduled workflows hours late (Q-014, Q-029).
# Run by Windows Task Scheduler (user level, folder \SportsHQ\; see ops/designs/Q-014.md "Laptop kick" for the exact
# tasks and how to remove them). No AI, no Claude usage: just `gh workflow run` with the laptop's GitHub sign-in.
#
#   kick.ps1 -Workflow run.yml -FreshMinutes 20   # skip when the site's data was committed in the last 20 minutes
#   kick.ps1 -Workflow model-health.yml            # always start it
#
# Every attempt is logged to %LOCALAPPDATA%\sports-hq-kick.log (last 500 lines kept).
param(
  [string]$Workflow = "run.yml",
  [int]$FreshMinutes = 0
)
$ErrorActionPreference = "Stop"
$repo = "mbryan20/sports-hq"
$log = Join-Path $env:LOCALAPPDATA "sports-hq-kick.log"
$gh = "C:\Program Files\GitHub CLI\gh.exe"
if (-not (Test-Path $gh)) { $gh = "gh" }

function Write-Log([string]$msg) {
  $line = "{0:yyyy-MM-dd HH:mm:ss} {1}: {2}" -f (Get-Date), $Workflow, $msg
  $old = @()
  if (Test-Path $log) { $old = @(Get-Content $log -Tail 499) }
  Set-Content -Path $log -Value ($old + $line) -Encoding utf8
}

try {
  if ($FreshMinutes -gt 0) {
    # status.json changes on every pass of run.yml, so its last commit is the heartbeat of a running loop
    $last = & $gh api "repos/$repo/commits?path=docs/data/status.json&per_page=1" --jq ".[0].commit.committer.date" 2>$null
    if ($LASTEXITCODE -eq 0 -and $last) {
      $age = ((Get-Date).ToUniversalTime() - ([datetime]::Parse($last)).ToUniversalTime()).TotalMinutes
      if ($age -lt $FreshMinutes) {
        Write-Log ("skipped: data committed {0:N0} min ago" -f $age)
        exit 0
      }
    }
  }
  $out = & $gh workflow run $Workflow -R $repo 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Log "FAILED: $out"; exit 1 }
  Write-Log "started"
} catch {
  Write-Log "FAILED: $($_.Exception.Message)"
  exit 1
}
