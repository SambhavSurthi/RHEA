<#
.SYNOPSIS
    Starts the entire RHEA - Research Hub for Exploration and Analysis stack with one command.

.DESCRIPTION
    1. Ensures .env exists (copies .env.example when missing).
    2. Ensures the Python virtual environment exists with dependencies installed.
    3. Starts Docker Desktop if it is installed but not running.
    4. Starts the Neo4j and Qdrant containers via Docker Compose and waits for them.
       If Docker is unavailable, the API still starts in in-memory fallback mode.
    5. Starts the FastAPI app (uvicorn) as a background process and waits for /health.
    6. Ingests the bundled sample documents (idempotent) so queries work immediately.
    7. Starts the Streamlit frontend on port 8501 and waits for it to become ready.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start-all.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start-all.ps1 -SkipIngest -VerboseOutput
#>
[CmdletBinding()]
param(
    [switch]$SkipDocker,
    [switch]$SkipIngest,
    [switch]$VerboseOutput,
    [int]$DockerWaitSeconds = 180,
    [int]$ApiPort = 8000,
    [int]$StreamlitPort = 8501,
    [string]$ApiHost = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$RunDir = Join-Path $Root '.run'
$EnvFile = Join-Path $Root '.env'
$PidFile = Join-Path $RunDir 'api.pid'
$OutLog = Join-Path $RunDir 'api.log'
$ErrLog = Join-Path $RunDir 'api.err.log'
$StPidFile = Join-Path $RunDir 'streamlit.pid'
$StOutLog = Join-Path $RunDir 'streamlit.log'
$StErrLog = Join-Path $RunDir 'streamlit.err.log'
$DockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$ComposeFile = Join-Path $Root 'infra\docker-compose.yml'
$ComposeArgs = @('-f', $ComposeFile)
$BackendPath = Join-Path $Root 'backend'

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}
function Write-Info([string]$Message) {
    Write-Host "    $Message" -ForegroundColor Gray
}
function Write-Ok([string]$Message) {
    Write-Host "    [OK] $Message" -ForegroundColor Green
}
function Write-Warn2([string]$Message) {
    Write-Host "    [WARN] $Message" -ForegroundColor Yellow
}

function Test-TcpPort([string]$Computer, [int]$Port, [int]$TimeoutMs = 1000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        # PowerShell resolves ConnectAsync to the Task-based overload, so do not
        # call EndConnect here - wait for the task and check its status instead.
        # (IsCompletedSuccessfully is unavailable on older PowerShell/.NET.)
        $task = $client.ConnectAsync($Computer, $Port)
        if ($task.Wait($TimeoutMs) -and $task.Status -eq 'RanToCompletion') { return $true }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-HttpOk([string]$Url, [int]$TimeoutSec = 3) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Wait-Until([scriptblock]$Condition, [int]$TimeoutSeconds, [string]$Description) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

function Test-DockerDaemon {
    try {
        $null = & docker info --format '{{.ServerVersion}}' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Test-OurApi([int]$Port) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
        $names = $r.PSObject.Properties.Name
        return (($names -contains 'vector') -and ($names -contains 'graph') -and ($names -contains 'provider'))
    } catch {
        return $false
    }
}

function Test-OurStreamlit([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
            Select-Object -First 1
        if (-not $conn) { return $false }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn.OwningProcess)"
        return ($proc.CommandLine -like "*$Root*streamlit_app.py*")
    } catch {
        return $false
    }
}

function Get-ComposeHealth([string]$Service) {
    # Returns 'healthy' / 'starting' / 'unhealthy', or $null if no healthcheck.
    try {
        $id = & docker compose @ComposeArgs ps -q $Service 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $id) { return $null }
        $status = & docker inspect --format '{{.State.Health.Status}}' $id 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $status) { return $null }
        return $status.Trim()
    } catch {
        return $null
    }
}

function Get-EnvValue([string]$Name, [string]$Default) {
    if (-not (Test-Path $EnvFile)) { return $Default }
    $match = Select-String -Path $EnvFile -Pattern "^\s*$Name\s*=\s*(.*)$" | Select-Object -Last 1
    if ($match) {
        $value = $match.Matches[0].Groups[1].Value.Trim()
        if ($value) { return $value }
    }
    return $Default
}

if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir -Force | Out-Null }

Write-Host '============================================================' -ForegroundColor Magenta
Write-Host '  RHEA - Research Hub for Exploration and Analysis - full stack startup' -ForegroundColor Magenta
Write-Host '============================================================' -ForegroundColor Magenta

# --- 1. Configuration -----------------------------------------------------
Write-Step 'Checking configuration (.env)'
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Root '.env.example') $EnvFile
    Write-Ok 'Created .env from .env.example'
} else {
    Write-Ok '.env found'
}

# --- 2. Python environment ------------------------------------------------
Write-Step 'Checking Python virtual environment'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Info 'Creating .venv and installing dependencies (first run only)...'
    & py -3 -m venv (Join-Path $Root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create virtual environment. Install Python 3.11+ and retry.' }
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
Write-Ok "Python: $Python"
$env:PYTHONPATH = $BackendPath
$PgPort = 5432
if (Test-TcpPort '127.0.0.1' $PgPort) {
    for ($candidate = $PgPort + 1; $candidate -le ($PgPort + 50); $candidate++) {
        if (-not (Test-TcpPort '127.0.0.1' $candidate)) {
            $PgPort = $candidate
            break
        }
    }
    Write-Ok "PostgreSQL host port 5432 is busy; using $PgPort"
}
$env:RHEA_POSTGRES_HOST_PORT = "$PgPort"
$env:RHEA_POSTGRES_DSN = "postgresql+psycopg://rhea:rhea-demo@localhost:$PgPort/rhea"

# --- 3. Infrastructure (Docker: Neo4j, Qdrant, PostgreSQL) ----------------
$DockerReady = $false
if ($SkipDocker) {
    Write-Step 'Docker skipped by request (-SkipDocker); API will use in-memory stores'
} else {
    Write-Step 'Checking Docker daemon'
    if (-not (Test-DockerDaemon)) {
        if (Test-Path $DockerDesktop) {
            Write-Info 'Docker Desktop is installed but not running. Starting it...'
            Start-Process -FilePath $DockerDesktop | Out-Null
            $DockerReady = Wait-Until { Test-DockerDaemon } $DockerWaitSeconds 'Docker daemon'
        } else {
            Write-Warn2 'Docker Desktop not found at the default location.'
        }
    } else {
        $DockerReady = $true
    }

    if ($DockerReady) {
        Write-Ok 'Docker daemon is ready'
        Write-Step 'Starting Neo4j and Qdrant containers'
        & docker compose @ComposeArgs up -d neo4j qdrant postgres
        if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed. Check docker compose ps and .env.' }
        Write-Info 'Waiting for Neo4j, Qdrant and PostgreSQL to become ready...'
        $InfraOk = Wait-Until {
            $neoHealth = Get-ComposeHealth 'neo4j'
            $neoReady = ($neoHealth -eq 'healthy') -or
                (-not $neoHealth -and (Test-HttpOk 'http://127.0.0.1:7474'))
            $pgHealth = Get-ComposeHealth 'postgres'
            $pgReady = ($pgHealth -eq 'healthy') -or
                (-not $pgHealth -and (Test-TcpPort '127.0.0.1' 5432))
            $neoReady -and $pgReady -and
            (Test-TcpPort '127.0.0.1' 7687) -and
            (Test-HttpOk 'http://127.0.0.1:6333/readyz')
        } 180 'Neo4j, Qdrant and PostgreSQL'
        if ($InfraOk) { Write-Ok 'Neo4j, Qdrant and PostgreSQL are up' }
        else { Write-Warn2 'Infrastructure did not become ready in time; API may use in-memory fallback.' }

        Write-Step 'Applying canonical-store migrations'
        $env:PYTHONPATH = $BackendPath
        & $Python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { Write-Warn2 'Migration failed; canonical store will fall back to memory if configured.' }
        else { Write-Ok 'Canonical schema is up to date' }
    } else {
        Write-Warn2 "Docker daemon did not become ready within $DockerWaitSeconds s."
        Write-Warn2 'Continuing in DEGRADED mode: the API will use in-memory vector/graph stores.'
    }
}

# --- 4. FastAPI application -----------------------------------------------
Write-Step 'Starting FastAPI (uvicorn)'

if (Test-TcpPort $ApiHost $ApiPort) {
    if (Test-OurApi $ApiPort) {
        $AlreadyRunning = $true
        $BaseUrl = "http://$ApiHost`:$ApiPort"
        Write-Ok "API is already running on $BaseUrl (reusing it)"
    } else {
        Write-Warn2 "Port $ApiPort is occupied by a different service; finding a free port..."
        $wanted = $ApiPort
        for ($candidate = $ApiPort + 1; $candidate -le ($ApiPort + 20); $candidate++) {
            if (-not (Test-TcpPort $ApiHost $candidate)) {
                $ApiPort = $candidate
                break
            }
        }
        if ($ApiPort -eq $wanted) { throw "No free API port found near $wanted. Stop the conflicting service." }
        Write-Ok "Using API port $ApiPort instead"
        $AlreadyRunning = $false
    }
} else {
    $AlreadyRunning = $false
}
$BaseUrl = "http://$ApiHost`:$ApiPort"
$HealthUrl = "$BaseUrl/health"

if (-not $AlreadyRunning) {
    $arguments = @('-m', 'uvicorn', 'rhea.main:app', '--host', $ApiHost, '--port', "$ApiPort")
    $proc = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $Root `
        -PassThru -WindowStyle Hidden -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
    $proc.Id | Set-Content $PidFile -NoNewline
    Write-Ok "Started uvicorn as PID $($proc.Id) (logs: .run\api.log, .run\api.err.log)"

    $ApiOk = Wait-Until { Test-HttpOk $HealthUrl } 90 'FastAPI /health'
    if (-not $ApiOk) {
        Write-Warn2 'API did not respond to /health in time. Last error log lines:'
        if (Test-Path $ErrLog) { Get-Content $ErrLog -Tail 20 | Write-Host }
        throw 'Startup failed. Check .run\api.err.log for details.'
    }
    Write-Ok "API is healthy on $BaseUrl"
}

$health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 5

# --- 5. Sample data ingestion ---------------------------------------------
if (-not $SkipIngest) {
    Write-Step 'Ingesting bundled sample documents'
    $writerKey = Get-EnvValue 'API_KEYS_WRITER' 'demo-writer-key'
    try {
        $result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/ingest/sample" `
            -Headers @{ 'X-API-Key' = $writerKey } -TimeoutSec 120
        Write-Ok "Ingested $($result.documents) documents / $($result.chunks) chunks into $($result.backends -join ' + ')"
    } catch {
        Write-Warn2 "Ingestion failed (non-fatal): $($_.Exception.Message)"
    }
}

# --- 6. Streamlit frontend -------------------------------------------------
Write-Step 'Starting Streamlit frontend'
$StUrl = "http://127.0.0.1:$StreamlitPort"
$StHealthUrl = "$StUrl/_stcore/health"
$StAlreadyRunning = $false
if (Test-TcpPort '127.0.0.1' $StreamlitPort) {
    if (Test-OurStreamlit $StreamlitPort) {
        Write-Ok "Streamlit is already running on $StUrl (reusing it)"
        $StAlreadyRunning = $true
    } else {
        Write-Warn2 "Port $StreamlitPort is used by another service; finding a free port..."
        $wantedSt = $StreamlitPort
        for ($candidate = $StreamlitPort + 1; $candidate -le ($StreamlitPort + 20); $candidate++) {
            if (-not (Test-TcpPort '127.0.0.1' $candidate)) {
                $StreamlitPort = $candidate
                break
            }
        }
        if ($StreamlitPort -eq $wantedSt) { throw "No free Streamlit port found near $wantedSt." }
        $StUrl = "http://127.0.0.1:$StreamlitPort"
        $StHealthUrl = "$StUrl/_stcore/health"
        Write-Ok "Using Streamlit port $StreamlitPort instead"
    }
}
if (-not $StAlreadyRunning) {
    if (-not (Test-Path (Join-Path $Root 'frontend\streamlit_app.py'))) {
        Write-Warn2 'frontend\streamlit_app.py not found; skipping frontend.'
    } else {
        $stArguments = @(
            '-m', 'streamlit', 'run', (Join-Path $Root 'frontend\streamlit_app.py'),
            '--server.port', "$StreamlitPort",
            '--server.address', '127.0.0.1',
            '--server.headless', 'true',
            '--browser.gatherUsageStats', 'false'
        )
        $env:RAG_API_URL = $BaseUrl
        $env:PYTHONPATH = $BackendPath
        $stProc = Start-Process -FilePath $Python -ArgumentList $stArguments -WorkingDirectory $Root `
            -PassThru -WindowStyle Hidden -RedirectStandardOutput $StOutLog -RedirectStandardError $StErrLog
        Remove-Item Env:RAG_API_URL -ErrorAction SilentlyContinue
        $stProc.Id | Set-Content $StPidFile -NoNewline
        Write-Ok "Started Streamlit as PID $($stProc.Id) (logs: .run\streamlit.log)"
        $StOk = Wait-Until { Test-HttpOk $StHealthUrl } 90 'Streamlit frontend'
        if ($StOk) { Write-Ok "Streamlit is ready on $StUrl" }
        else {
            Write-Warn2 'Streamlit did not respond in time. Last error log lines:'
            if (Test-Path $StErrLog) { Get-Content $StErrLog -Tail 20 | Write-Host }
        }
    }
}

# --- 7. Summary ------------------------------------------------------------
Write-Host "`n============================================================" -ForegroundColor Magenta
Write-Host '  STACK STATUS' -ForegroundColor Magenta
Write-Host '============================================================' -ForegroundColor Magenta
Write-Host "  Streamlit UI   : $StUrl" -ForegroundColor White
Write-Host "  API health     : $HealthUrl" -ForegroundColor White
Write-Host "  API docs       : $BaseUrl/docs" -ForegroundColor White
Write-Host "  Vector backend : $($health.vector.backend) (healthy=$($health.vector.healthy))" -ForegroundColor White
Write-Host "  Graph backend  : $($health.graph.backend) (healthy=$($health.graph.healthy))" -ForegroundColor White
Write-Host "  LLM provider   : $($health.provider)" -ForegroundColor White
if ($DockerReady) {
    Write-Host '  Neo4j Browser  : http://localhost:7474  (neo4j / rhea-demo)' -ForegroundColor White
    Write-Host '  Qdrant dashboard: http://localhost:6333/dashboard' -ForegroundColor White
} else {
    Write-Host '  Docker          : NOT running (in-memory fallback mode)' -ForegroundColor Yellow
}
Write-Host '------------------------------------------------------------' -ForegroundColor Magenta
Write-Host '  Chat API       : POST /v1/chat/stream  (SSE: steps, sources, tokens)' -ForegroundColor White
Write-Host '  PDF ingest     : POST /v1/ingest/pdf   (multipart file upload)' -ForegroundColor White
Write-Host '  To shut everything down: .\\stop-all.ps1' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor Magenta
