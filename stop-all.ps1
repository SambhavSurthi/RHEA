<#
.SYNOPSIS
    Stops the entire RHEA - Research Hub for Exploration and Analysis stack with one command.

.DESCRIPTION
    1. Stops the uvicorn process started by start-all.ps1 (tracked in .run/api.pid).
    2. Stops the Streamlit process tracked in .run/streamlit.pid.
    3. As a safety net, stops stray uvicorn / Streamlit processes from this project.
    4. Runs `docker compose down` to stop/remove the Neo4j and Qdrant containers.
       Named volumes (neo4j_data, qdrant_data) are PRESERVED, so ingested data
       survives a restart. Pass -RemoveVolumes to delete them as well.
    4. Docker Desktop itself is left running by default because it may host
       unrelated workloads. Pass -StopDockerDesktop to shut it down too.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\stop-all.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\stop-all.ps1 -RemoveVolumes -StopDockerDesktop
#>
[CmdletBinding()]
param(
    [switch]$RemoveVolumes,
    [switch]$StopDockerDesktop
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$RunDir = Join-Path $Root '.run'
$PidFile = Join-Path $RunDir 'api.pid'
$StPidFile = Join-Path $RunDir 'streamlit.pid'
$ComposeArgs = @('-f', (Join-Path $Root 'infra\docker-compose.yml'))

function Write-Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "    [OK] $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message) { Write-Host "    [WARN] $Message" -ForegroundColor Yellow }
function Write-Info([string]$Message) { Write-Host "    $Message" -ForegroundColor Gray }

Write-Host '============================================================' -ForegroundColor Magenta
Write-Host '  RHEA - Research Hub for Exploration and Analysis - full stack shutdown' -ForegroundColor Magenta
Write-Host '============================================================' -ForegroundColor Magenta

# --- 1. API process from PID file -----------------------------------------
Write-Step 'Stopping the FastAPI process'
$stoppedAny = $false
if (Test-Path $PidFile) {
    $pidValue = (Get-Content $PidFile -Raw).Trim()
    if ($pidValue -match '^\d+$') {
        $proc = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
            Write-Ok "Stopped uvicorn PID $pidValue"
            $stoppedAny = $true
        } else {
            Write-Info "PID $pidValue was not running"
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Info 'No .run\api.pid file found'
}

# --- 2. Safety net: any other uvicorn serving this project ----------------
try {
    $cim = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -match 'uvicorn' -and
            $_.CommandLine -match 'app\.main:app' -and
            $_.ExecutablePath -like "$Root*"
        }
    foreach ($p in $cim) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Ok "Stopped stray API process PID $($p.ProcessId)"
        $stoppedAny = $true
    }
} catch {
    Write-Warn2 "Could not scan for stray processes: $($_.Exception.Message)"
}
if (-not $stoppedAny) { Write-Info 'No API process needed stopping' }

# --- 2. Streamlit frontend -------------------------------------------------
Write-Step 'Stopping the Streamlit frontend'
$stStopped = $false
if (Test-Path $StPidFile) {
    $stPid = (Get-Content $StPidFile -Raw).Trim()
    if ($stPid -match '^\d+$') {
        $stProc = Get-Process -Id ([int]$stPid) -ErrorAction SilentlyContinue
        if ($stProc) {
            Stop-Process -Id ([int]$stPid) -Force -ErrorAction SilentlyContinue
            Write-Ok "Stopped Streamlit PID $stPid"
            $stStopped = $true
        } else {
            Write-Info "PID $stPid was not running"
        }
    }
    Remove-Item $StPidFile -Force -ErrorAction SilentlyContinue
}
if (-not $stStopped) { Write-Info 'No tracked Streamlit process needed stopping' }

# --- 3. Safety net: stray Streamlit servers from this project --------------
try {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -match 'streamlit' -and
            $_.CommandLine -match 'streamlit_app\.py' -and
            ($_.CommandLine -like "*$Root*" -or $_.ExecutablePath -like "$Root*")
        } | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Ok "Stopped stray Streamlit PID $($_.ProcessId)"
        }
} catch {
    Write-Warn2 "Could not scan for stray Streamlit processes: $($_.Exception.Message)"
}

# --- 4. Docker containers --------------------------------------------------
Write-Step 'Stopping Docker containers (Neo4j + Qdrant)'
$dockerAvailable = $false
try {
    $null = & docker info --format '{{.ServerVersion}}' 2>$null
    $dockerAvailable = ($LASTEXITCODE -eq 0)
} catch { $dockerAvailable = $false }

if ($dockerAvailable) {
    if ($RemoveVolumes) {
        & docker compose @ComposeArgs down -v
        Write-Ok 'Containers removed together with neo4j_data / qdrant_data volumes'
    } else {
        & docker compose @ComposeArgs down
        Write-Ok 'Containers removed (data volumes preserved)'
    }
} else {
    Write-Warn2 'Docker daemon is not running; nothing to stop there'
}

# --- 4. Optional: Docker Desktop ------------------------------------------
if ($StopDockerDesktop) {
    Write-Step 'Stopping Docker Desktop'
    $desktop = Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue
    if ($desktop) {
        Stop-Process -Name 'Docker Desktop' -Force -ErrorAction SilentlyContinue
        Write-Ok 'Docker Desktop stopped'
    } else {
        Write-Info 'Docker Desktop was not running'
    }
}

Write-Host "`n============================================================" -ForegroundColor Magenta
Write-Host '  All project services are stopped.' -ForegroundColor Magenta
Write-Host '  Restart with:  .\start-all.ps1' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor Magenta
